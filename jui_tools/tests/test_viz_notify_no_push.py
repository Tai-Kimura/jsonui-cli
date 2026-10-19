"""The browser notifications are the Notification API only, while a page is open (requester 10-19: 「開いている間でいい」):
no service worker is registered and no push subscription is made anywhere — in the page's sources or in any /app.js the
server builds (live, demo, the e2e hook) — so nothing about a session ever goes through a browser maker's push service."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from jui_cli.viz import bundle

WEB = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "web"
FORBIDDEN = re.compile(r"serviceWorker|PushManager|pushManager|showNotification|\.subscribe\(\s*\{\s*userVisibleOnly")


def test_no_page_source_registers_a_service_worker_or_subscribes_to_push():
    hits = [f"{p.relative_to(WEB)}:{n}" for p in sorted(WEB.rglob("*")) if p.is_file() and p.suffix in (".js", ".html", ".mjs")
            and "vendor" not in p.parts for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if FORBIDDEN.search(line)]
    assert hits == []


@pytest.mark.parametrize("mode", bundle.MODES)
@pytest.mark.parametrize("e2e", [False, True])
def test_no_bundle_does_either(mode, e2e, monkeypatch):
    if e2e:
        monkeypatch.setenv("JUI_VIZ_E2E", "1")
    else:
        monkeypatch.delenv("JUI_VIZ_E2E", raising=False)
    assert not FORBIDDEN.search(bundle.build(mode))


def test_the_notification_is_made_in_one_place():
    src = (WEB / "js" / "50-panel.js").read_text(encoding="utf-8")
    everything = "".join(p.read_text(encoding="utf-8") for p in sorted((WEB / "js").glob("*.js")))
    assert everything.count("new Notification(") == 1 and "function notifyOut(" in src
