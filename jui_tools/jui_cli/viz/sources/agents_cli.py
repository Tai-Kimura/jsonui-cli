"""``claude agents --json`` every few seconds: the sessions running on this machine.

Fills in sessions no hook has named yet (started before the hooks were
installed). Stops itself — and says why in the server slice — when ``claude``
is not on PATH. The output format is a research preview: a shape it cannot
read is reported once and skipped, never fatal.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
from typing import Callable

TIMEOUT_SEC = 2.0


def parse(stdout: bytes) -> list[dict] | None:
    try:
        data = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if isinstance(data, dict):
        data = data.get("agents", data.get("sessions"))
    if not isinstance(data, list):
        return None
    return [row for row in data if isinstance(row, dict)]


async def poll_once(claude: str) -> list[dict] | None:
    # A session of its own, so a timeout can end the whole group this call
    # started: a grandchild holding stdout would otherwise keep the pipe —
    # and this wait — open until it exits.
    proc = await asyncio.create_subprocess_exec(
        claude, "agents", "--json",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT_SEC)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # the group started just above
        except ProcessLookupError:
            pass
        # A grandchild that left the group (setsid) can still hold stdout,
        # and asyncio's wait() lasts until every pipe closes: drop our end of
        # the pipes and bound the wait, or one poll takes as long as it lives.
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            transport.close()
        try:
            await asyncio.wait_for(proc.wait(), 1.0)
        except asyncio.TimeoutError:
            pass
        return None
    if proc.returncode != 0:
        return None
    return parse(stdout)


async def run(interval: float, on_rows: Callable[[list[dict]], None], on_status: Callable[[str, str | None], None],
              which: Callable[[str], str | None] = shutil.which) -> None:
    claude = which("claude")
    if claude is None:
        on_status("stopped", "claude が PATH にありません（セッション一覧の取得を止めました）")
        return
    on_status("running", None)
    failures = 0
    while True:
        rows = await poll_once(claude)
        if rows is None:
            failures += 1
            if failures == 1:
                on_status("degraded", "claude agents --json を読めませんでした（続けて試します）")
        else:
            if failures:
                on_status("running", None)
            failures = 0
            on_rows(rows)
        await asyncio.sleep(interval)
