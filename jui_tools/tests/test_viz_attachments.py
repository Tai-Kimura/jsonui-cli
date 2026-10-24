"""Files attached to a prompt typed in the page (ticket 2026-10-20-jui-viz-prompt-attach-files-and-paste-images).

The first arms run attachments.Attachments on a temporary folder: where a file goes, its name and mode, what is refused
(a session id or a folder that leads elsewhere, the limits), and that removal never follows a symlink. The last arms
run a real `jui viz start` in a temporary HOME (the fixture of test_viz_send_prompt): POST /api/attach under the checks
of /api/prompt, and a prompt naming the ids gets one line per file with its path. Nothing here starts claude.
"""
from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest

from jui_cli.viz import attachments as att
from jui_cli.viz.attachments import Attachments, Refused
from jui_cli.viz.ingest import World, attachment_line
from jui_cli.viz.state import VizState
from tests.test_viz_send_prompt import S_NEW, S_NONE, S_OLD, _taken, viz  # noqa: F401 — viz is the fixture

SID = "e2e00000-0000-4000-8000-00000000b001"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def _mode(p: Path) -> int:
    return stat.S_IMODE(os.lstat(p).st_mode)


@pytest.fixture()
def store(tmp_path):
    home = tmp_path / "viz-home"
    return Attachments(home=home), home


# ---------------------------------------------------------------- where and how a file is kept


def test_a_file_is_kept_in_the_private_folder_under_a_name_the_server_made(store):
    a, home = store
    rec = a.save(SID, "スクリーンショット 1.png", "image/png", PNG)
    folder = home / "uploads" / SID
    assert Path(rec["path"]).parent == folder
    assert Path(rec["path"]).name == f"{rec['id']}.png" and len(rec["id"]) == 16
    assert Path(rec["path"]).read_bytes() == PNG
    assert _mode(folder) == 0o700 and _mode(home / "uploads") == 0o700
    assert _mode(Path(rec["path"])) == 0o600
    assert (rec["name"], rec["media"], rec["size"]) == ("スクリーンショット 1.png", "image/png", len(PNG))


def test_the_name_the_person_gave_never_becomes_part_of_a_path(store, tmp_path):
    a, home = store
    for name in ("../../escape.txt", "/etc/passwd", "a/../../b.txt", "..\\..\\c.txt", "x\x00y.txt", "evil\n.txt"):
        rec = a.save(SID, name, "", b"hello")
        assert Path(rec["path"]).parent == home / "uploads" / SID, name
        assert Path(rec["path"]).name in (f"{rec['id']}.txt", f"{rec['id']}.bin"), name   # the server's name, never the person's
        assert "/" not in rec["name"] and "\\" not in rec["name"] and "\n" not in rec["name"] and "\x00" not in rec["name"]
    assert not (tmp_path / "escape.txt").exists()
    assert sorted(p.name for p in (home / "uploads").iterdir()) == [SID]


@pytest.mark.viz_ja
def test_an_image_name_keeps_its_extension_only_when_its_bytes_are_that_image(store):
    a, _ = store
    assert a.save(SID, "photo.png", "image/png", PNG)["path"].endswith(".png")
    assert a.save(SID, "photo.png", "image/png", b"<script>")["path"].endswith(".bin")
    assert a.save(SID, "", "image/png", PNG)["name"] == "貼り付けた画像.png"   # pasted: no name of its own
    assert a.save(SID, "tool.exe", "", b"MZ")["path"].endswith(".bin")


def test_a_session_id_that_is_not_a_plain_name_is_refused(store, tmp_path):
    a, _ = store
    for sid in ("../x", "a/b", "", ".", "..", "x" * 65, "-lead"):
        with pytest.raises(Refused):
            a.save(sid, "a.txt", "", b"x")
    assert not (tmp_path / "x").exists()


def test_a_symlink_where_a_folder_should_be_is_never_followed(store, tmp_path):
    a, home = store
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "uploads").mkdir(parents=True)
    os.symlink(outside, home / "uploads" / SID)
    with pytest.raises(OSError):
        a.save(SID, "a.txt", "", b"x")
    assert list(outside.iterdir()) == []
    # the same with uploads itself a symlink
    b_home = tmp_path / "home2"
    b_home.mkdir()
    os.symlink(outside, b_home / "uploads")
    with pytest.raises(OSError):
        Attachments(home=b_home).save(SID, "a.txt", "", b"x")
    assert list(outside.iterdir()) == []


def test_an_existing_name_is_never_written_through(store, tmp_path, monkeypatch):
    """O_EXCL | O_NOFOLLOW: a symlink planted under the name the server picks is refused, its target untouched."""
    a, home = store
    target = tmp_path / "target.txt"
    target.write_text("keep")
    (home / "uploads" / SID).mkdir(parents=True, mode=0o700)
    os.symlink(target, home / "uploads" / SID / "aaaaaaaaaaaaaaaa.txt")
    monkeypatch.setattr(att.secrets, "token_hex", lambda n: "aaaaaaaaaaaaaaaa")
    with pytest.raises(FileExistsError):
        a.save(SID, "a.txt", "", b"overwrite")
    assert target.read_text() == "keep"


def test_a_folder_left_open_to_others_is_closed_to_0700(store):
    a, home = store
    (home / "uploads" / SID).mkdir(parents=True)
    os.chmod(home / "uploads" / SID, 0o777)
    a.save(SID, "a.txt", "", b"x")
    assert _mode(home / "uploads" / SID) == 0o700


# ---------------------------------------------------------------- limits


def test_the_limits(store, monkeypatch):
    a, _ = store
    with pytest.raises(Refused) as e:
        a.save(SID, "big.bin", "", b"x" * (att.FILE_MAX + 1))
    assert e.value.status == 413
    with pytest.raises(Refused) as e:
        a.save(SID, "empty.txt", "", b"")
    assert e.value.status == 400
    assert a.save(SID, "edge.bin", "", b"x" * att.FILE_MAX)["size"] == att.FILE_MAX
    monkeypatch.setattr(att, "SESSION_FILES_MAX", 3)
    a.save(SID, "2.txt", "", b"x")
    a.save(SID, "3.txt", "", b"x")
    with pytest.raises(Refused) as e:
        a.save(SID, "4.txt", "", b"x")
    assert e.value.status == 413


def test_the_session_byte_cap(store, monkeypatch):
    a, _ = store
    monkeypatch.setattr(att, "SESSION_BYTES_MAX", 10)
    a.save(SID, "a.txt", "", b"x" * 6)
    with pytest.raises(Refused):
        a.save(SID, "b.txt", "", b"x" * 5)
    a.save(SID, "c.txt", "", b"x" * 4)


def test_a_prompt_names_at_most_ten_and_only_this_sessions_own(store):
    a, _ = store
    ids = [a.save(SID, f"{i}.txt", "", b"x")["id"] for i in range(11)]
    assert len(a.take(SID, ids[:10])) == 10
    with pytest.raises(Refused) as e:
        a.take(SID, ids)
    assert e.value.status == 400
    other = "e2e00000-0000-4000-8000-00000000b002"
    with pytest.raises(Refused) as e:
        a.take(other, ids[:1])
    assert e.value.status == 404
    for bad in (["../x"], ["0" * 16], [1], "abc"):
        with pytest.raises(Refused):
            a.take(SID, bad)


def test_a_file_swapped_for_a_symlink_after_it_was_kept_is_refused(store, tmp_path):
    a, _ = store
    rec = a.save(SID, "a.txt", "", b"hello")
    os.unlink(rec["path"])
    (tmp_path / "secret").write_text("hello")
    os.symlink(tmp_path / "secret", rec["path"])
    with pytest.raises(Refused) as e:
        a.take(SID, [rec["id"]])
    assert e.value.status == 409


# ---------------------------------------------------------------- removal


def test_removal_unlinks_through_the_folder_and_never_follows_a_symlink(store, tmp_path):
    a, home = store
    rec = a.save(SID, "a.txt", "", b"x")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    os.symlink(outside, home / "uploads" / SID / "link")            # a symlink to a folder inside ours
    os.symlink(outside / "keep.txt", home / "uploads" / SID / "f")   # and to a file
    a.drop(SID)
    assert not (home / "uploads" / SID).exists()
    assert (outside / "keep.txt").read_text() == "keep"
    assert not Path(rec["path"]).exists()


def test_removal_of_a_folder_that_is_a_symlink_leaves_its_target(store, tmp_path):
    a, home = store
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    (home / "uploads").mkdir(parents=True)
    os.symlink(outside, home / "uploads" / SID)
    a.files[SID] = {}
    a.drop(SID)
    assert (outside / "keep.txt").read_text() == "keep"


def test_the_x_removes_one_file(store):
    a, _ = store
    keep, gone = a.save(SID, "a.txt", "", b"x"), a.save(SID, "b.txt", "", b"y")
    assert a.remove(SID, gone["id"]) is True
    assert not Path(gone["path"]).exists() and Path(keep["path"]).exists()
    assert a.remove(SID, gone["id"]) is False
    with pytest.raises(Refused):
        a.take(SID, [gone["id"]])


def test_files_go_an_hour_after_the_session_ended_and_stay_if_it_resumes(tmp_path):
    w = World(VizState())
    w.attachments = Attachments(home=tmp_path / "h")
    hook = lambda kind, at: w.apply_hook({"hook_event_name": kind, "session_id": SID, "cwd": "/w"}, at)  # noqa: E731
    hook("SessionStart", 1000)
    rec = w.attachments.save(SID, "a.txt", "", b"x")
    hook("SessionEnd", 2000)
    w.tick(2000 + att.KEEP_MS - 1)
    assert Path(rec["path"]).exists()
    hook("SessionStart", 3000)   # resumed within the hour
    w.tick(2000 + att.KEEP_MS + 10)
    assert Path(rec["path"]).exists()
    hook("SessionEnd", 5000)
    w.tick(5000 + att.KEEP_MS)
    assert not Path(rec["path"]).parent.exists()
    assert SID not in w.attachments.files


def test_at_start_old_folders_are_swept_and_new_ones_and_symlinks_left(store, tmp_path):
    a, home = store
    old = a.save(SID, "a.txt", "", b"x")
    new_sid = "e2e00000-0000-4000-8000-00000000b003"
    new = a.save(new_sid, "b.txt", "", b"y")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    link = "e2e00000-0000-4000-8000-00000000b004"
    os.symlink(outside, home / "uploads" / link)
    past = time.time() - att.KEEP_MS / 1000 - 60
    os.utime(home / "uploads" / SID, (past, past))
    os.utime(home / "uploads" / link, (past, past), follow_symlinks=False)
    gone = Attachments(home=home).sweep_private(time.time())
    assert gone == [SID]
    assert not Path(old["path"]).exists() and Path(new["path"]).exists()
    assert (outside / "keep.txt").read_text() == "keep"


def test_the_prompt_line_names_the_absolute_path():
    rec = {"path": "/s/uploads/x/0123456789abcdef.png", "name": "a.png", "media": "image/png", "size": 2048}
    assert attachment_line(rec) == "attached: /s/uploads/x/0123456789abcdef.png (a.png, image/png, 2 KB)"


def test_the_history_reads_the_english_line_and_the_japanese_one_of_older_transcripts():
    """The line is English from 2.3.13 (the terminal's words are English); a transcript written before has the Japanese
    form, and 55-history.js's histAttachMatch (run in node) reads both into the same parts. Its own text is no file."""
    import shutil
    import subprocess
    from tests.test_viz_bundle import web_text
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    src = web_text("js", "55-history.js")
    start, end = src.index("const HIST_ATTACH_LINES"), src.index("\n", src.index("const histAttachMatch"))
    rec = {"path": "/s/uploads/ab-1/0123456789abcdef.png", "name": "a, (b).png", "media": "image/png", "size": 2048}
    lines = [attachment_line(rec), "添付: /s/uploads/ab-1/0123456789abcdef.png（a, (b).png、image/png、2 KB）",
             "attached: see the file", "添付: なし"]
    out = subprocess.run([node, "-"], input=src[start:end] + f"\nprocess.stdout.write(JSON.stringify({json.dumps(lines)}"
                          ".map((l) => { const m = histAttachMatch(l); return m && m.slice(1); })));",
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    parts = ["/s/uploads/ab-1/0123456789abcdef.png", "ab-1", "0123456789abcdef", "png", "a, (b).png", "image/png", "2 KB"]
    assert json.loads(out.stdout) == [parts, parts, None, None]


def test_a_prompt_of_files_only_is_marked_arrived_by_the_servers_line():
    """Only files, no text: the receiver's transcript shows the server's lines (attachment_line), and 55-history.js's
    composeArrived (run in node) marks the prompt arrived from them; another session's item or an older one does not."""
    import shutil
    import subprocess
    from tests.test_viz_bundle import web_text
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    src = web_text("js", "55-history.js")
    norm = src[src.index("const composeNorm"):src.index("\n", src.index("const composeNorm"))]
    start = src.index("function composeArrived(")
    arrived = src[start:src.index("\n}\n", start) + 3]
    line = attachment_line({"path": "/s/uploads/ab-1/0123456789abcdef.png", "name": "a.png", "media": "image/png",
                            "size": 2048})
    script = norm + "\n" + arrived + f"""
let painted = 0; const composePaint = () => {{ painted += 1; }};
const run = (items) => {{ HIST.sent = {{ id: 's1', text: '', at: 100000 }}; composeArrived(items); return !!HIST.sent.arrivedAt; }};
const HIST = {{ id: 's1', sent: null }};
const mine = {{ kind: 'channel', server: 'plugin:jui-viz:jui-viz', text: {json.dumps(line)}, at: 100500 }};
process.stdout.write(JSON.stringify([run([mine]), run([{{ ...mine, server: 'other' }}]), run([{{ ...mine, at: 1000 }}]), painted]));"""
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [True, False, False, 1]


def test_the_module_has_no_other_place_and_widens_nothing():
    """The requester's ruling (10-20, via cd): the private folder only; viz never writes the receiver's settings or
    permission rules and adds nothing like --add-dir."""
    src = Path(att.__file__).read_text(encoding="utf-8")
    code = src.split('"""', 2)[2]
    for word in ("scratchpad", "add-dir", "additionalDirectories", "settings.json", "permissions"):
        assert word not in code, word


# ---------------------------------------------------------------- the server's route


def _attach(v, data: bytes, sid=S_NEW, name="a.png", media="image/png", **over):
    h = v.page_headers(**{"Content-Type": "application/octet-stream", "X-Jui-Viz-Session": sid,
                          "X-Jui-Viz-Name": name, "X-Jui-Viz-Media": media, **over})
    status, text = v.raw("POST", "/api/attach", h, data)
    return status, (json.loads(text) if status == 200 else text)


def test_attach_has_the_checks_of_the_prompt(viz):
    assert _attach(viz, PNG, **{"X-Jui-Viz-Token": None})[0] == 401
    assert _attach(viz, PNG, Origin="http://evil.example")[0] == 403
    assert _attach(viz, PNG, Origin=None)[0] == 403
    assert _attach(viz, PNG, Host=f"localhost:{viz.port}")[0] == 403
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "application/json", None):
        assert _attach(viz, PNG, **{"Content-Type": ctype})[0] == 415, ctype
    h = viz.page_headers(**{"Content-Type": "application/octet-stream", "X-Jui-Viz-Session": S_NEW})
    assert viz.raw("GET", "/api/attach", h)[0] == 405
    assert not (viz.state / "uploads").exists()


def test_attach_refuses_a_session_a_prompt_cannot_reach_and_an_oversized_body(viz):
    for sid in (S_NONE, S_OLD, "e2e00000-0000-4000-8000-0000000000ff", "../x"):
        assert _attach(viz, PNG, sid=sid)[0] in (404, 409), sid
    assert _attach(viz, b"x" * (att.FILE_MAX + 1))[0] == 413
    h = viz.page_headers(**{"Content-Type": "application/octet-stream", "X-Jui-Viz-Session": S_NEW})
    assert viz.raw("POST", "/api/attach", h, b"x" * (att.FILE_MAX + 1), chunked=True)[0] == 413
    assert not (viz.state / "uploads").exists()


def test_a_prompt_with_attachments_carries_each_files_path_and_the_file_is_there(viz):
    status, one = _attach(viz, PNG, name="%E8%B2%BC%E3%82%8A%E4%BB%98%E3%81%91.png")
    assert status == 200, one
    status, two = _attach(viz, b"hello\n", name="notes.txt", media="text/plain")
    assert status == 200, two
    assert set(one) == {"id", "name", "media", "size"}   # the path goes only into the prompt
    body = json.dumps({"sessionId": S_NEW, "text": "見て", "attachments": [one["id"], two["id"]]}, ensure_ascii=False).encode()
    status, text = viz.prompt(body=body)
    assert status == 200, text
    got = _taken(viz, "new")[0]["text"].split("\n")
    folder = viz.state / "uploads" / S_NEW
    assert got[0] == "見て"
    assert got[1] == f"attached: {folder / (one['id'] + '.png')} (貼り付け.png, image/png, {len(PNG)} B)"
    assert got[2] == f"attached: {folder / (two['id'] + '.txt')} (notes.txt, text/plain, 6 B)"
    assert (folder / f"{one['id']}.png").read_bytes() == PNG
    assert (folder / f"{two['id']}.txt").read_bytes() == b"hello\n"


def test_a_prompt_of_files_only_is_taken_and_unknown_ids_are_refused(viz):
    _, one = _attach(viz, PNG)
    status, text = viz.prompt(body=json.dumps({"sessionId": S_NEW, "text": "", "attachments": [one["id"]]}).encode())
    assert status == 200, text
    assert _taken(viz, "new")[0]["text"].startswith("attached: /")
    assert viz.prompt(body=json.dumps({"sessionId": S_NEW, "text": "x", "attachments": ["f" * 16]}).encode())[0] == 404
    assert viz.prompt(body=json.dumps({"sessionId": S_NEW, "text": "", "attachments": []}).encode())[0] == 400


def test_a_real_start_sweeps_old_folders_and_keeps_new_ones(tmp_path, monkeypatch):
    """viz_cmd calls sweep_private before it serves: a folder older than the hour is gone, a fresh one stays."""
    from tests.test_viz_send_prompt import ISOLATE, Viz
    home = tmp_path / "home"
    for k in ISOLATE:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(home))
    uploads = home / ".local" / "state" / "jui-viz" / "uploads"
    old, new = uploads / SID, uploads / "e2e00000-0000-4000-8000-00000000b005"
    for d in (old, new):
        d.mkdir(parents=True, mode=0o700)
        (d / "0123456789abcdef.txt").write_text("x")
    past = time.time() - att.KEEP_MS / 1000 - 60
    os.utime(old, (past, past))
    v = Viz(home)
    try:
        assert not old.exists() and (new / "0123456789abcdef.txt").exists()
    finally:
        v.stop()


# ---------------------------------------------------------------- an attached image, read back for the history (2.3.9)


def test_a_kept_image_is_read_back_and_a_gone_one_is_404(store):
    a, home = store
    rec = a.save(SID, "a.png", "image/png", PNG)
    fid = rec["id"]
    assert a.read_image(SID, fid, "png") == ("image/png", PNG)
    os.unlink(rec["path"])
    with pytest.raises(Refused) as e:
        a.read_image(SID, fid, "png")
    assert e.value.status == 404
    with pytest.raises(Refused) as e:
        Attachments(home=home).read_image("e2e00000-0000-4000-8000-00000000b0ff", fid, "png")   # no folder at all
    assert e.value.status == 404


def test_only_an_image_is_read_back_never_through_a_symlink_or_out_of_the_folder(store, tmp_path):
    a, home = store
    txt = a.save(SID, "notes.txt", "", b"hello")
    with pytest.raises(Refused) as e:
        a.read_image(SID, txt["id"], "txt")
    assert e.value.status == 415
    fake = a.save(SID, "x.bin", "", b"<html>not a png</html>")
    os.rename(fake["path"], Path(fake["path"]).with_suffix(".png"))   # an image's name, other bytes
    with pytest.raises(Refused) as e:
        a.read_image(SID, fake["id"], "png")
    assert e.value.status == 415
    outside = tmp_path / "secret.png"
    outside.write_bytes(PNG)
    link_id = "abcdefabcdefabcd"
    os.symlink(outside, home / "uploads" / SID / f"{link_id}.png")
    with pytest.raises(Refused) as e:
        a.read_image(SID, link_id, "png")
    assert e.value.status == 404
    for sid, fid in (("../x", txt["id"]), (SID, "../../secret"), (SID, "0123")):
        with pytest.raises(Refused):
            a.read_image(sid, fid, "png")


def _attach_image(v, body: dict, **over):
    h = v.page_headers(**over)
    return v.raw("POST", "/api/attach-image", h, json.dumps(body).encode())


def test_attach_image_has_the_checks_and_serves_the_kept_image(viz):
    status, one = _attach(viz, PNG)
    assert status == 200, one
    body = {"sessionId": S_NEW, "id": one["id"], "ext": "png"}
    assert _attach_image(viz, body, **{"X-Jui-Viz-Token": None})[0] == 401
    assert _attach_image(viz, body, Origin="http://evil.example")[0] == 403
    assert _attach_image(viz, body, **{"Content-Type": None})[0] == 415
    assert viz.raw("GET", "/api/attach-image", viz.page_headers())[0] == 405
    conn = __import__("http.client").client.HTTPConnection("127.0.0.1", viz.port, timeout=10)
    try:
        data = json.dumps(body).encode()
        conn.putrequest("POST", "/api/attach-image", skip_host=True, skip_accept_encoding=True)
        for k, v in {**viz.page_headers(), "Content-Length": str(len(data))}.items():
            conn.putheader(k, v)
        conn.endheaders()
        conn.send(data)
        res = conn.getresponse()
        got, ctype, nosniff = res.read(), res.getheader("Content-Type"), res.getheader("X-Content-Type-Options")
    finally:
        conn.close()
    assert (res.status, got, ctype, nosniff) == (200, PNG, "image/png", "nosniff")
    (viz.state / "uploads" / S_NEW / f"{one['id']}.png").unlink()
    assert _attach_image(viz, body) == (200, '{"gone": true}')   # not an error: the browser logs every 404


def test_a_save_sums_a_copy_of_the_sessions_files(tmp_path):
    book = Attachments(home=tmp_path)
    sid = "s1"
    first = book.save(sid, "a.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"0" * 8)

    class Removing(dict):
        """A record whose size, read while the files are summed, takes another file off (remove() in another thread)."""
        def __getitem__(self, key):
            if key == "size":
                book.files[sid].pop(first["id"], None)
            return dict.__getitem__(self, key)
    book.files[sid]["zz"] = Removing(size=1)
    book.files[sid]["zz2"] = {"size": 1}
    got = book.save(sid, "b.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"1" * 8)
    assert got["id"] in book.files[sid] and first["id"] not in book.files[sid]
    kept = {"x": Removing(size=1), "y": {"size": 1}}
    first = {"id": "y"}
    book.files[sid] = kept
    with pytest.raises(RuntimeError, match="changed size during iteration"):
        sum(f["size"] for f in kept.values())       # the old sum
