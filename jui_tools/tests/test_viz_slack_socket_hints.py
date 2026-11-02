"""The sorting factory's hints (57-slack-room.js ``sfFetchHint``) for what a Socket Mode line can say (slack/socket_mode.py):
every error the connection can leave — no appToken, apps.connections.open's Slack errors and HTTP statuses, aiohttp's and
the OS's words, the connection closed, disconnect: link_disabled — has the hint that says what to do, and a fetch's
errors keep theirs. The function is cut out of the file served and run under node, its tl() giving the key back.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from importlib import resources

import pytest

WEB = resources.files("jui_cli.viz").joinpath("web")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

SOCKET = {
    "no appToken": "appTokenMissing",
    "apps.connections.open: invalid_auth": "appToken",
    "apps.connections.open: missing_scope": "appToken",
    "apps.connections.open: not_allowed_token_type": "appToken",
    "apps.connections.open: not_authed": "appToken",
    "apps.connections.open: token_revoked": "appToken",
    "apps.connections.open: token_expired": "appToken",
    "apps.connections.open: account_inactive": "appToken",
    "apps.connections.open: ratelimited": "socketRetry",
    "apps.connections.open: internal_error": "socketRetry",
    "apps.connections.open: fatal_error": "socketRetry",
    "apps.connections.open: service_unavailable": "socketRetry",
    "apps.connections.open: request_timeout": "socketRetry",
    "apps.connections.open: HTTP 429": "socketRetry",
    "apps.connections.open: HTTP 503": "socketRetry",
    "apps.connections.open: not JSON": "socketRetry",
    "the connection closed": "socketRetry",
    "401, message='Invalid response status', url='wss://wss-primary.slack.com/link/'": "socketRetry",
    "disconnect: link_disabled (Socket Mode is off for the app)": "socketOff",
    "apps.connections.open: Cannot connect to host slack.com:443 ssl:default [nodename nor servname provided, or not known]": "network",
    "apps.connections.open: TimeoutError": "network",
    "apps.connections.open: Connection timeout to host https://slack.com/api/apps.connections.open": "network",
    "Cannot connect to host wss-primary.slack.com:443 ssl:default [Network is unreachable]": "network",
    "Server disconnected": "network",
    "TimeoutError": "network",
    "Timeout on reading data from socket": "network",
    "[Errno 54] Connection reset by peer": "network",
}
FETCH = {   # a fetch's errors ("<workspace>/<channel>: <method>: <Slack's error>") keep their hints
    "acme/D02HXM5RE: conversations.history: missing_scope": "im",
    "acme/G02HXM5RE: conversations.history: missing_scope": "groups",
    "acme/C02HXM5RE: conversations.history: missing_scope": "channels",
    "acme/C02HXM5RE: conversations.history: not_in_channel": "invite",
    "acme/C02HXM5RE: conversations.history: not_authed": "token",
    "acme: no token": "token",
    "acme/C02HXM5RE: conversations.history: something_new": "",
}


def hint_of(texts: list[str]) -> list[str]:
    js = WEB.joinpath("js", "57-slack-room.js").read_text(encoding="utf-8")
    m = re.search(r"^function sfFetchHint\(text\) \{\n.*?^\}\n", js, re.S | re.M)
    assert m, "57-slack-room.js: no sfFetchHint"
    prog = "const tl = (k) => k;\n" + m.group(0) + f"\nprocess.stdout.write(JSON.stringify({json.dumps(texts)}.map(sfFetchHint)));"
    out = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=30, check=True).stdout
    return json.loads(out)


def test_every_error_a_socket_line_can_say_has_its_hint_and_a_fetchs_errors_keep_theirs():
    cases = {**SOCKET, **FETCH}
    got = dict(zip(cases, hint_of(list(cases))))
    want = {t: ("sf.intake.hint." + k if k else "") for t, k in cases.items()}
    assert got == want


def test_the_new_hints_are_in_both_languages_and_say_where_the_fix_is():
    for lang in ("ja", "en"):
        d = json.loads(WEB.joinpath("i18n", f"{lang}.json").read_text(encoding="utf-8"))
        for k in ("appTokenMissing", "socketOff", "socketRetry", "network"):
            assert d.get("sf.intake.hint." + k), (lang, k)
        miss = d["sf.intake.hint.appTokenMissing"]
        assert "Basic Information" in miss and "App-Level Tokens" in miss and "xapp-" in miss
        assert "connections:write" in miss and "slack.json" in miss and "workspaces[].appToken" in miss
        assert "Socket Mode" in d["sf.intake.hint.socketOff"]
