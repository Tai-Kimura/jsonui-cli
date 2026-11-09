"""A stand-in for a session's relay channel (jui_cli/viz/channel.py) in the browser e2e: its hello, then polls kept going as
channel.py keeps them, until closed.

A channel the server has not heard from for CHANNEL_DEAD_MS (60 s, permissions.py) is dropped, and the page then says
the session has no relay. A stand-in that only said hello lived 60 s: on a loaded machine a suite took longer than that
before the step that reads the relay, and went red (ticket 2026-11-06-viz-e2e-full-run-red-under-load, card-waits in
2.5.18's whole run; the same on v2.5.17 with a 65 s pause after the hello). Polling, the stand-in stays as long as the
suite needs it, as a real session's channel does.

What its polls are handed (verdicts, prompts) is kept in `.verdicts` / `.prompts`, as channel.py takes them.
"""

from __future__ import annotations

import http.client
import json
import threading

POLL_TIMEOUT_SEC = 35   # the server holds a poll up to 25 s (channel.py's own)


class StandInChannel:
    def __init__(self, port: int, token: str, session_id: str, *, ppid: int = 1, cwd: str = "/"):
        self.port, self.token, self.session_id = port, token, session_id
        self.hello_body = {"ppid": ppid, "cwd": cwd, "sessionId": session_id, "version": "2", "accepts": ["prompt"], "via": "plugin"}
        self.channel_id: str | None = None
        self.status: int | None = None
        self.reply = ""
        self.polls = 0
        self.lost = False          # the server answered 404: it no longer knows the channel
        self.verdicts: list = []
        self.prompts: list = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _call(self, method: str, path: str, body: dict | None, timeout: float):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            headers = {"X-Jui-Viz-Token": self.token}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            r = conn.getresponse()
            return r.status, r.read().decode()
        finally:
            conn.close()

    def open(self) -> "StandInChannel":
        """Say hello and start polling. The hello's status and reply are kept (.status, .reply)."""
        self.status, self.reply = self._call("POST", "/channel/hello", self.hello_body, 10)
        if self.status == 200:
            try:
                self.channel_id = json.loads(self.reply).get("channelId")
            except ValueError:
                self.channel_id = None
        if self.channel_id:
            self._thread = threading.Thread(target=self._poll, name=f"stand-in channel {self.session_id[-4:]}", daemon=True)
            self._thread.start()
        return self

    def _poll(self) -> None:
        while not self._stop.is_set():
            try:
                status, text = self._call("GET", f"/channel/poll?channelId={self.channel_id}", None, POLL_TIMEOUT_SEC)
            except OSError:
                if self._stop.wait(0.5):   # the server is stopping, or busy: try again, as channel.py does
                    return
                continue
            if status == 404:
                self.lost = True
                return
            if status == 200:
                self.polls += 1
                try:
                    got = json.loads(text)
                except ValueError:
                    got = {}
                self.verdicts += got.get("verdicts") or []
                self.prompts += got.get("prompts") or []
            elif self._stop.wait(0.5):
                return

    def close(self) -> None:
        """Stop polling (a poll the server holds ends by itself within POLL_TIMEOUT_SEC; the thread is a daemon)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
