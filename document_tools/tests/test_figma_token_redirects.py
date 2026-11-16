"""X-Figma-Token goes to the Figma API and nowhere else (ticket 2026-10-21-figma-token-follows-redirects).

urllib carries a request's own headers to where a redirect points, so the calls that carry the token follow no
redirect (any host, the same one included), and send nothing to a URL that is not the Figma API. Nothing here reaches
the network: two HTTP servers on 127.0.0.1, and urllib's HTTPS handler stood in for (api.figma.com). The token is a
fake value.
"""
from __future__ import annotations

import email.message
import http.server
import io
import json
import threading
import urllib.request
import urllib.response

import pytest

from jsonui_doc_cli.figma import api_client as C

TOKEN = "figd_" + "FAKE-not-a-real-token-0000"
ANSWER = {"document": {}, "nodes": {}, "meta": {"images": {}}, "images": {}, "err": None}


class _Server:
    """An HTTP server on 127.0.0.1 that records the X-Figma-Token of each request; ``to`` set: it answers 302 there."""

    def __init__(self, to: str | None = None):
        self.got, self.to = [], to
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.got.append((self.path, self.headers.get("X-Figma-Token")))
                if outer.to and len(outer.got) == 1:
                    self.send_response(302)
                    self.send_header("Location", outer.to if "://" in outer.to else outer.url + outer.to)
                    self.end_headers()
                    return
                body = json.dumps(ANSWER).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture()
def sink():
    s = _Server()
    yield s
    s.close()


def test_the_opener_follows_no_redirect_between_two_local_servers(sink):
    """The first server answers 302 to the second: the opener the token's calls use stops there, the second server
    gets nothing, and the failure's words do not hold the token."""
    first = _Server(to=sink.url + "/elsewhere")
    try:
        req = urllib.request.Request(first.url + "/v1/files/KEY", headers={"X-Figma-Token": TOKEN})
        with pytest.raises(C.FigmaAPIError) as e:
            C.opener()(req, timeout=5)
        assert [t for _, t in first.got] == [TOKEN] and sink.got == []
        assert "not followed" in str(e.value) and TOKEN not in str(e.value) and e.value.status_code == 302
    finally:
        first.close()


def test_a_redirect_to_the_same_server_is_not_followed_either():
    """Not even to the same host and port: no "same host" judgement to get wrong."""
    s = _Server(to="/v1/files/OTHER")
    try:
        req = urllib.request.Request(s.url + "/v1/files/KEY", headers={"X-Figma-Token": TOKEN})
        with pytest.raises(C.FigmaAPIError):
            C.opener()(req, timeout=5)
        assert len(s.got) == 1
    finally:
        s.close()


def _figma_redirects_to(monkeypatch, where: str) -> list:
    """api.figma.com, stood in for: it answers 302 to ``where``; the URLs it was asked are returned."""
    asked = []

    def https_open(self, req):
        asked.append((req.full_url, req.get_header("X-figma-token")))
        msg = email.message.Message()
        msg["Location"] = where
        r = urllib.response.addinfourl(io.BytesIO(b""), msg, req.full_url, 302)
        r.msg = "Found"
        return r
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", https_open)
    # plain HTTP too: a URL the check let through by mistake ("http://api.figma.com/…") is recorded, not sent
    monkeypatch.setattr(urllib.request.HTTPHandler, "http_open", https_open)
    return asked


CALLS = {
    "fetch_file": lambda: C.fetch_file("KEY", TOKEN),
    "fetch_nodes": lambda: C.fetch_nodes("KEY", TOKEN, ["1:2"]),
    "fetch_file_images": lambda: C.fetch_file_images("KEY", TOKEN),
    "fetch_image_renders": lambda: C.fetch_image_renders("KEY", TOKEN, ["1:2"]),
}


@pytest.mark.parametrize("name", sorted(CALLS))
def test_each_call_with_the_token_stops_at_a_redirect(monkeypatch, sink, name):
    """The four calls that carry the token (measured before the fix: each sent it on to the redirect's server)."""
    asked = _figma_redirects_to(monkeypatch, sink.url + "/elsewhere")
    with pytest.raises(C.FigmaAPIError) as e:
        CALLS[name]()
    assert len(asked) == 1 and asked[0][0].startswith(C.FIGMA_API_BASE + "/") and asked[0][1] == TOKEN
    assert sink.got == [] and "not followed" in str(e.value) and TOKEN not in str(e.value)


def test_a_url_that_is_not_the_figma_api_is_not_sent(monkeypatch):
    """Another host, plain HTTP, a host that only begins like Figma's, another API version: not sent at all."""
    asked = _figma_redirects_to(monkeypatch, "unused")
    for url in ("https://elsewhere.example/v1/files/KEY", "http://api.figma.com/v1/files/KEY",
                "https://api.figma.com.example/v1/files/KEY", "https://api.figma.com/v2/files/KEY"):
        with pytest.raises(C.FigmaAPIError) as e:
            C._open(urllib.request.Request(url, headers={"X-Figma-Token": TOKEN}), 5)
        assert "is not the Figma API" in str(e.value) and TOKEN not in str(e.value), url
    assert asked == []


def test_the_figma_api_answering_is_read_with_the_token_in_its_header(monkeypatch):
    asked = []

    def https_open(self, req):
        asked.append((req.full_url, req.get_header("X-figma-token")))
        r = urllib.response.addinfourl(io.BytesIO(json.dumps(ANSWER).encode()), email.message.Message(), req.full_url, 200)
        r.msg = "OK"
        return r
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", https_open)
    assert C.fetch_file("KEY", TOKEN) == ANSWER
    assert asked == [(C.FIGMA_API_BASE + "/files/KEY", TOKEN)]
