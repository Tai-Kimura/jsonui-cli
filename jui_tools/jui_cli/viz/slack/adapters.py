"""Run a function of a user's adapter file in a child ``python -I`` (filter and router adapters given as a path).

The child gets the arguments as JSON on stdin and prints the result as JSON; a crash, an exit or a hang stays in
the child (a hang is killed after the timeout). The file is never imported into the viz server.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TIMEOUT_SEC = 60.0
OUT_MAX = 4 * 1024 * 1024

_HOST = r"""
import importlib.util, json, sys
path, func = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("jui_viz_slack_adapter", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
args = json.loads(sys.stdin.read())
got = getattr(mod, func)(*args)
out = json.dumps({"ok": got}, ensure_ascii=False)
sys.stdout.write("\n@@jui-viz-adapter@@" + out)
"""


class AdapterError(Exception):
    pass


def resolve(path_text: str) -> Path:
    path = Path(os.path.expanduser(path_text))
    if not path.is_absolute():
        raise AdapterError(f"{path_text}: an adapter path must be absolute (or start with ~)")
    if not path.is_file():
        raise AdapterError(f"{path_text}: no such file")
    return path


def run_file(path_text: str, func: str, args: list, timeout: float = TIMEOUT_SEC) -> object:
    path = resolve(path_text)
    try:
        proc = subprocess.run([sys.executable, "-I", "-c", _HOST, str(path), func],
                              input=json.dumps(args, ensure_ascii=False), capture_output=True, text=True,
                              timeout=timeout, cwd=str(path.parent), start_new_session=True)
    except subprocess.TimeoutExpired:
        raise AdapterError(f"{path.name}: {func} did not answer in {timeout:g} s") from None
    except OSError as exc:
        raise AdapterError(f"{path.name}: {exc}") from None
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-1:] or [f"exit {proc.returncode}"]
        raise AdapterError(f"{path.name}: {func} failed: {tail[0][:300]}")
    out = proc.stdout or ""
    if len(out) > OUT_MAX:
        raise AdapterError(f"{path.name}: {func} printed more than {OUT_MAX} bytes")
    marker = out.rfind("\n@@jui-viz-adapter@@")
    if marker < 0:
        raise AdapterError(f"{path.name}: {func} returned nothing")
    try:
        return json.loads(out[marker + len("\n@@jui-viz-adapter@@"):])["ok"]
    except (ValueError, KeyError, TypeError):
        raise AdapterError(f"{path.name}: {func} returned something that is not JSON") from None
