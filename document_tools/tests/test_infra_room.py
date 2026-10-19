"""Reading a room's infra model (room.py; boundary §2, §5.2): where from (jui.config.json's infra), which files, how
(inside the room, no symlink, no FIFO held), how much (LIMITS), and the reason when nothing can be read. And
`jsonui-doc validate infra`: 0 no error, 1 errors, 2 nothing read. Everything under tmp_path.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import room as R

FIX = Path(__file__).resolve().parent / "fixtures" / "infra"
OK = {"version": 0, "nodes": [{"id": "api", "category": "compute.container"}]}


def _room(tmp_path, files=None, config=None, folder="docs/infra") -> Path:
    root = tmp_path / "room"
    (root / folder).mkdir(parents=True)
    for name, data in (files or {"main.json": OK}).items():
        (root / folder / name).write_text(data if isinstance(data, str) else json.dumps(data))
    if config is not None:
        (root / "jui.config.json").write_text(json.dumps(config))
    return root


def test_the_default_folder_and_the_configured_one(tmp_path):
    assert R.read(_room(tmp_path))["files"] == ["main.json"]
    root = _room(tmp_path / "b", config={"infra": {"dir": "ops/model"}}, folder="ops/model")
    got = R.read(root)
    assert got["ok"] and got["dir"] == "ops/model" and R.counts(root) == {"files": 1, "dir": "ops/model"}


@pytest.mark.parametrize("folder", ["/etc", "../outside", "docs/../../x", "https://example.com/infra", "", 3])
def test_a_folder_outside_the_room_is_bad_config(tmp_path, folder):
    root = _room(tmp_path, config={"infra": {"dir": folder}})
    got = R.read(root)
    assert got == {"ok": False, "reason": "bad_config", "message": got["message"], "short": got["short"]}
    assert R.counts(root)["files"] == 0


def test_a_symlinked_folder_or_file_is_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.json").write_text(json.dumps(OK))
    root = _room(tmp_path, files={"main.json": OK})
    os.symlink(outside / "secret.json", root / "docs" / "infra" / "link.json")
    got = R.read(root)
    assert got["files"] == ["main.json"]                                   # the symlink is not a regular file here
    shutil.rmtree(root / "docs" / "infra")
    os.symlink(outside, root / "docs" / "infra")
    assert R.read(root)["reason"] == "no_infra" and R.counts(root)["files"] == 0


def test_a_fifo_in_the_folder_never_holds_the_read(tmp_path):
    root = _room(tmp_path)
    os.mkfifo(root / "docs" / "infra" / "pipe.json")
    out = []
    t = threading.Thread(target=lambda: out.append(R.read(root)), daemon=True)
    t.start()
    t.join(5)
    assert not t.is_alive() and out[0]["files"] == ["main.json"]


def test_hidden_files_and_check_reports_are_not_the_model(tmp_path):
    root = _room(tmp_path, files={"main.json": OK, ".draft.json": "{", "x.check-report.json": "{}", "notes.txt": "x"})
    got = R.read(root)
    assert got["files"] == ["main.json"] and got["problems"] == [] and R.counts(root)["files"] == 1


def test_the_limits(tmp_path, monkeypatch):
    monkeypatch.setitem(R.LIMITS, "files", 2)
    root = _room(tmp_path, files={f"f{i}.json": {"version": 0} for i in range(3)})
    assert R.read(root)["reason"] == "too_many_files"
    monkeypatch.setitem(R.LIMITS, "files", 50)
    monkeypatch.setitem(R.LIMITS, "total_bytes", 30)
    assert R.read(root)["reason"] == "too_large"
    monkeypatch.setitem(R.LIMITS, "total_bytes", 16_000_000)
    monkeypatch.setitem(R.LIMITS, "file_bytes", 15)
    big = _room(tmp_path / "b", files={"big.json": OK, "small.json": {"version": 0}})
    got = R.read(big)
    assert got["files"] == ["small.json"] and [p["code"] for p in got["problems"]] == ["read.too_large"]


def test_no_room_and_no_files(tmp_path):
    assert R.read(tmp_path / "nowhere")["reason"] == "no_infra"
    assert R.read(_room(tmp_path), is_room=False)["reason"] == "not_a_room"
    empty = tmp_path / "e"
    (empty / "docs" / "infra").mkdir(parents=True)
    assert R.read(empty)["reason"] == "no_infra"
    assert set(R.REASONS) == {"not_a_room", "no_infra", "bad_config", "too_many_files", "too_large", "invalid", "unreadable"}


def test_icons_inside_the_room_only(tmp_path):
    icons = {"service:aws/rds.mysql": "docs/infra/icons/rds.svg", "provider:aws": "docs/infra/icons/aws.png",
             "category:cache": "docs/infra/icons/missing.svg", "service:aws/s3": "https://example.com/s3.svg",
             "category:quantum": "docs/infra/icons/rds.svg", "aws/rds": "docs/infra/icons/rds.svg",
             "provider:gcp": "../outside.svg", "provider:azure": "docs/infra/icons/azure.gif"}
    root = _room(tmp_path, config={"infra": {"icons": icons}})
    (root / "docs" / "infra" / "icons").mkdir()
    (root / "docs" / "infra" / "icons" / "rds.svg").write_text("<svg/>")
    (root / "docs" / "infra" / "icons" / "aws.png").write_bytes(b"\x89PNG")
    got = R.read(root)
    assert got["icons"] == {"service:aws/rds.mysql": "docs/infra/icons/rds.svg", "provider:aws": "docs/infra/icons/aws.png"}
    codes = sorted(p["code"] for p in got["problems"])
    assert codes == ["config.icon"] * 5 + ["read.icon"], codes
    assert any("URL is not read" in p["message"] for p in got["problems"])
    assert R.read_icon(root, "docs/infra/icons/rds.svg") == (b"<svg/>", "image/svg+xml")
    assert R.read_icon(root, "../x.svg") is None


def test_counts_opens_no_model_file(tmp_path, monkeypatch):
    root = _room(tmp_path, files={"a.json": OK, "b.json": OK})
    opened = []
    real = R.read_capped
    monkeypatch.setattr(R, "read_capped", lambda r, rel, cap: (opened.append(rel), real(r, rel, cap))[1])
    assert R.counts(root) == {"files": 2, "dir": "docs/infra"}
    assert opened == ["jui.config.json"]


def test_the_examples_read_as_the_page_takes_them():
    got = R.read(FIX / "compose-and-cloud")
    assert got["ok"] and got["dir"] == "infra/model" and len(got["nodes"]) == 7 and set(got["icons"]) == {"service:gcp/run", "category:cache"}
    assert set(got) >= {"ok", "dir", "files", "version", "environments", "groups", "nodes", "edges", "problems", "icons", "readMs"}


@pytest.mark.parametrize("room, rc", [("aws-three-tier", 0), ("large-multi-provider", 0), ("invalid/refs", 1), ("nowhere", 2)])
def test_validate_infra_exit_codes(room, rc):
    tools = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "validate", "infra", str(FIX / room), "--json"],
                       cwd=tools, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    assert r.returncode == rc, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is (rc != 2) and "nodes" not in out


# ---------------------------------------------------------------- the short lines the page shows (boundary §5.2)

def test_a_broken_json_says_its_file_and_line(tmp_path):
    root = _room(tmp_path, files={"prod.json": '{\n "version": 0,\n "nodes": [,]\n}'})
    got = R.read(root)
    assert got["ok"] is False and got["reason"] == "invalid" and R.REASONS["invalid"] == 422
    assert got["short"] == "docs/infra/prod.json: 3 行目の JSON が壊れています"
    assert got["problems"][0]["line"] == 3 and got["problems"][0]["short"] == got["short"]


def test_a_usable_room_with_a_bad_file_is_ok_with_short_lines(tmp_path):
    root = _room(tmp_path, files={"main.json": OK, "prod.json": "{"})
    got = R.read(root)
    assert got["ok"] and got["files"] == ["main.json"] and [p["short"] for p in got["problems"]] == [
        "docs/infra/prod.json: 1 行目の JSON が壊れています"]


@pytest.mark.parametrize("reason, make", [
    ("no_infra", lambda tmp: tmp / "nowhere"),
    ("bad_config", lambda tmp: _room(tmp, config={"infra": {"dir": "/etc"}})),
])
def test_every_failure_has_a_short_line(tmp_path, reason, make):
    got = R.read(make(tmp_path))
    assert got["reason"] == reason and got["short"] and "\n" not in got["short"]
    assert {k for k in got} >= {"ok", "reason", "message", "short"}
    assert all(R._short_refused(k, "docs/infra") for k in R.REASONS if k != "invalid")


@pytest.mark.parametrize("fixture", sorted(p.name for p in (FIX / "invalid" / "single").glob("secret-*.json")))
def test_a_secret_never_reaches_the_short_line_nor_the_full_text(tmp_path, fixture):
    from jsonui_doc_cli.infra import model as M
    raw = (FIX / "invalid" / "single" / fixture).read_text()
    values = [v for _p, v in M._walk_strings(json.loads(raw), "") if M.secret_findings(v)]
    assert values
    for files in ({"leak.json": raw}, {"main.json": OK, "leak.json": raw}):
        got = R.read(_room(tmp_path / fixture / str(len(files)), files=files))
        text = json.dumps(got, ensure_ascii=False)
        assert "秘密の形" in text
        for v in values:
            assert v not in text, (fixture, v)
