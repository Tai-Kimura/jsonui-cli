"""The call dialog's Codex tab with a model of a local server (local_models.py, callcmd.codex_command's local): the models
LM Studio / Ollama list, the command that runs one with --oss, and the session that shows it."""
from __future__ import annotations

import json
import shlex
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jui_cli.viz import callcmd, local_models
from jui_cli.viz.ingest import World
from jui_cli.viz.sources.codex_app_server import Translator
from jui_cli.viz.state import VizState


def test_a_servers_models_are_one_line_ids_each_once():
    body = json.dumps({"data": [{"id": "qwen3-coder-next"}, {"id": "qwen3-coder-next"}, {"id": "bad\nid"}, {"id": ""},
                                {"id": "x" * 201}, {"nope": 1}, {"id": "openai/gpt-oss-120b"}]}).encode()
    assert local_models.parse(body) == ["qwen3-coder-next", "openai/gpt-oss-120b"]
    assert local_models.parse(b"<html>") is None and local_models.parse(b'{"data": 3}') is None


def test_fetch_reads_v1_models_on_127_0_0_1_and_a_closed_port_is_not_ok():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"object": "list", "data": [{"id": "qwen3-coder-next", "object": "model"}]}).encode()
            self.send_response(200 if self.path == "/v1/models" else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert local_models.fetch(srv.server_address[1]) == ["qwen3-coder-next"]
    finally:
        srv.shutdown()
    assert local_models.fetch(srv.server_address[1], timeout=0.3) is None   # closed now


def test_the_listing_names_every_provider_in_order():
    got = local_models.listing(lambda port: ["m1"] if port == 1234 else None)
    assert [(p["id"], p["ok"], p["models"]) for p in got] == [("lmstudio", True, ["m1"]), ("ollama", False, [])]


def test_a_local_model_runs_codex_in_its_servers_own_home_with_the_model_as_one_word():
    line = callcmd.codex_command("/work/app", "review", "", {"provider": "lmstudio", "model": "-qwen3 coder"}, "/u/.codex-local/lmstudio")
    prompt = callcmd.sh_quote(callcmd.prompt_of("review", ""))   # $'…' for its newline: shlex cannot read that part
    assert line.endswith(" " + prompt) and "--oss" not in line   # --oss would not attach to the daemon
    words = shlex.split(line[: -len(prompt)])
    assert words[:7] == ["cd", "/work/app", "&&", "jui", "viz", "codex-local", "ensure"] and words[7] == "lmstudio"
    assert "CODEX_HOME=/u/.codex-local/lmstudio" in words and words[-3:] == ["CODEX_HOME=/u/.codex-local/lmstudio", "codex", "--model=-qwen3 coder"]
    assert "codex-local" not in callcmd.codex_command("/work/app", "review", "")   # Codex's default model, ~/.codex
    for bad in ({"provider": "vllm", "model": "m"}, {"provider": "ollama", "model": "a\nb"}, {"provider": "ollama"}, "m"):
        assert callcmd.check_local(bad) is not None


def test_a_servers_home_names_its_provider_and_copies_features_and_mcp_servers_once(monkeypatch, tmp_path):
    import tomllib

    from jui_cli.viz import codex_homes

    monkeypatch.setenv("HOME", str(tmp_path))
    main = {"model": "gpt-6.1-sol", "features": {"multi_agent": True},
            "mcp_servers": {"jui-tools": {"command": "node", "args": ["/a b/index.js"], "env": {"JUI_X": "1"}},
                            "odd name": {"command": "x", "startup_timeout_sec": 20}},
            "projects": {"/work/app": {"trust_level": "trusted"}}}
    home, made = codex_homes.ensure("lmstudio", main)
    assert made and home == tmp_path / ".codex-local" / "lmstudio"
    got = tomllib.loads((home / "config.toml").read_text())
    assert got == {"model_provider": "lmstudio", "features": {"multi_agent": True}, "mcp_servers": main["mcp_servers"]}
    (home / "config.toml").write_text("model_provider = \"lmstudio\"\n# the person's own edit\n")
    assert codex_homes.ensure("lmstudio", main) == (home, False)   # never rewritten
    assert "own edit" in (home / "config.toml").read_text()
    assert codex_homes.homes() == [("lmstudio", home)]


def test_a_session_started_with_oss_carries_its_model_and_provider():
    state = VizState()
    world = World(state)
    tr = Translator()
    world.apply_codex(tr.thread_seen({"id": "01a1-0001", "cwd": "/work/app", "model": "qwen3-coder-next",
                                      "modelProvider": "lmstudio"}), {}, 1)
    world.publish()
    [s] = state.slices["sessions"]
    assert (s["model"], s["modelProvider"], s["cli"]) == ("qwen3-coder-next", "lmstudio", "codex")
