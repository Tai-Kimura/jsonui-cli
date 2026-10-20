"""tools/viz_promo/ (ticket 2026-10-21-viz-promo-replay-and-capture-tool): the parts that need no server and no browser.

The script: every event inside its chapter, the preludes untimed, every kind and target one the driver knows, every
session it names one of the floor's; the words: ja and en of the same shape; the frames: (end - start) x 30 from the
promo's timeline.json, whose ids and bounds the script was written for; the terminal's text cleaned of colour codes
and of the copy's own path; a missing feature named before a server starts; the rooms: demo-shop a fresh git workdir
of one commit by a neutral author, English labels from the project's own generators.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from viz_promo import timeline as T  # noqa: E402

PROMO = Path(os.environ.get("JUI_PROMO_DIR", Path.home() / "resource" / "jsonui-promo"))


def all_chapters():
    return [(lang, c) for lang in T.WORDS for c in T.chapters(lang).values()]


def test_every_event_is_inside_its_chapter_and_the_preludes_are_untimed():
    for lang, c in all_chapters():
        assert (c.start, c.end) == T.BOUNDS[c.id], (lang, c.id)
        for ev in c.events:
            assert ev.at is not None and c.start <= ev.at < c.end, (lang, c.id, ev)
            if ev.kind == "wheel":
                assert ev.at + ev.args["dur"] <= c.end, (lang, c.id, ev)
        assert all(ev.at is None for ev in c.prelude), (lang, c.id)
        ats = [ev.at for ev in c.events]
        assert ats == sorted(ats), (lang, c.id, "the events are written in their order")


def test_the_chapters_are_the_promos_viz_chapters():
    assert set(T.chapters("ja")) == set(T.CHAPTER_IDS)
    assert set(T.BOUNDS) == set(T.CHAPTER_IDS) | set(T.TERM_CHAPTER_IDS)


def test_every_kind_target_and_session_is_one_the_driver_knows():
    from viz_promo import capture
    keys = {k for k, _, _ in T.SESSIONS}
    for lang, c in all_chapters():
        for ev in c.prelude + c.events:
            assert ev.kind in T.KINDS, (c.id, ev)
            for name in ("key", "frm", "to"):
                if name in ev.args:
                    assert ev.args[name] in keys, (c.id, ev)
            if "target" in ev.args:
                assert set(ev.args["target"]) <= T.TARGETS, (c.id, ev)
            if ev.args.get("expect"):
                assert ev.args["expect"].partition(":")[0] in capture.EXPECT, (c.id, ev)
        assert set(c.needs) <= set(capture.FEATURES), c.id


def test_a_tool_that_ends_was_opened_and_a_question_answered_was_asked():
    for lang, c in all_chapters():
        opened, asked = set(), set()
        for ev in c.prelude + c.events:
            a = ev.args
            if ev.kind in ("tool", "tests_start"):
                opened.add(a["key"])
            elif ev.kind in ("tool_end", "tests_end"):
                assert a["key"] in opened, (c.id, ev)
                opened.discard(a["key"])
            elif ev.kind == "ask":
                asked.add(a["use_id"])
            elif ev.kind == "ask_answered":
                assert a["use_id"] in asked, (c.id, ev)


def test_the_words_are_the_same_shape_in_both_languages():
    def shape(v):
        if isinstance(v, dict):
            return {k: shape(x) for k, x in v.items()}
        if isinstance(v, list):
            return [shape(x) for x in v]
        return type(v).__name__
    assert shape(T.WORDS["ja"]) == shape(T.WORDS["en"])
    keys = {k for k, _, _ in T.SESSIONS}
    for lang in T.WORDS:
        assert set(T.WORDS[lang]["names"]) == keys
        assert set(T.WORK.values()) <= set(T.WORDS[lang]["prompts"])
        assert T.WORDS[lang]["answer"] in [o["label"] for o in T.WORDS[lang]["question"]["options"]]
        names = list(T.WORDS[lang]["names"].values())
        assert len(set(names)) == len(names), "a talk row is found by its name"


def test_session_ids_carry_their_labels_and_are_distinct():
    ids = [T.session_id(k) for k, _, _ in T.SESSIONS]
    assert len(set(ids)) == len(ids) and len({i[:2] for i in ids}) == len(ids)
    for (k, label, room), sid in zip(T.SESSIONS, ids):
        assert sid.startswith(label) and room in T.ROOMS and len(sid) == 36


def test_frame_counts():
    assert T.frame_count(54, 74) == 600 and T.frame_count(0, 4) == 120 and T.frame_count(88, 96) == 240
    assert T.frame_time(54, 0) == 54 and T.frame_time(54, 30) == 55
    # the clock steps of capture.py: 33 or 34 ms, exactly 1000 over 30 frames
    steps = [round((i + 1) * 1000 / T.FPS) - round(i * 1000 / T.FPS) for i in range(T.FPS * 3)]
    assert set(steps) <= {33, 34} and sum(steps) == 3000


@pytest.mark.skipif(not (PROMO / "src" / "timeline.json").is_file(), reason="the jsonui-promo project is not on this machine")
def test_the_promos_timeline_matches_the_script():
    promo = T.promo_timeline(PROMO)
    assert set(promo) == set(T.BOUNDS)
    assert T.check_bounds(promo) == []
    for cid, (s, e) in promo.items():
        assert T.frame_count(s, e) == round((e - s) * 30)


def test_check_bounds_names_a_moved_chapter():
    moved = {c: tuple(float(x) for x in b) for c, b in T.BOUNDS.items()}
    moved["4"] = (54.0, 72.0)
    assert [x.split(":")[0] for x in T.check_bounds(moved)] == ["4"]


def test_a_missing_feature_is_named(tmp_path):
    from viz_promo import capture
    viz = tmp_path / "jui_tools" / "jui_cli" / "viz"
    (viz / "web" / "js").mkdir(parents=True)
    (viz / "rooms.py").write_text("")
    (viz / "web" / "js" / "56-server-room.js").write_text("")
    got = capture.missing_features(tmp_path, ("rooms", "server_room", "flows"), "ja")
    assert len(got) == 1 and got[0].startswith("flows (jui_cli/viz/web/js/59-sr-flows.js")
    got = capture.missing_features(tmp_path, ("rooms",), "en")
    assert len(got) == 1 and got[0].startswith("i18n")
    assert capture.missing_features(Path(__file__).resolve().parents[2], ("rooms", "server_room"), "en") == []


def test_the_terminal_text_is_the_output_without_colours_or_the_copys_path(tmp_path):
    from viz_promo import term
    root = tmp_path / "work" / "demo-shop"
    raw = f"\x1b[32m✓\x1b[0m built {root}/ios/ios/View/Cart/CartGeneratedView.swift\r\nprogress 10%\rprogress 100%\nin {root}\n"
    assert term.clean(raw, root) == "✓ built ios/ios/View/Cart/CartGeneratedView.swift\nprogress 100%\nin .\n"


def test_the_gates_and_files_are_there():
    from viz_promo import term
    root = Path(__file__).resolve().parents[2]
    for shown, (launcher, *_), _keep in term.GATES:
        assert (root / launcher).is_file(), launcher
        assert shown.split()[0] == Path(launcher).name
    assert sum(sec for _, sec in term.GENERATED + term.HAND_WRITTEN) <= T.BOUNDS["1a"][1] - T.BOUNDS["1a"][0]
    assert "verify" in term.GATES[1][0] and term.GATES[1][2]


def test_the_term_pages_carry_their_data():
    from viz_promo import term
    doc = term.page_html("1b", [{"shown": "jui build", "output": "ok", "keep": None}], 16, 32)
    assert '"shown": "jui build"' in doc and "__DATA__" not in doc and "__PROMPT__" not in doc and '"demo-shop $ "' in doc
    doc = term.page_html("1a", [{"path": "a.json", "sec": 1, "text": "{}", "generated": False}], 4, 16)
    assert '"path": "a.json"' in doc and "__T0__" not in doc


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")).stdout


def _fake_shop(tmp_path) -> Path:
    src = tmp_path / "src-shop"
    (src / "tools").mkdir(parents=True)
    (src / "docs" / "infra" / "load").mkdir(parents=True)
    (src / "jui.config.json").write_text("{}")
    (src / "docs" / "infra" / "system.json").write_text('{"label": "ja"}\n')
    (src / ".gitignore").write_text("build/\n")
    (src / "build").mkdir()
    (src / "build" / "junk.txt").write_text("not tracked")
    gen = ("import argparse, pathlib\nap = argparse.ArgumentParser(); ap.add_argument('--lang'); ap.add_argument('--out')\n"
           "a = ap.parse_args(); o = pathlib.Path(a.out); o.mkdir(parents=True, exist_ok=True)\n"
           "(o / '{name}').write_text('{{\"label\": \"' + a.lang + '\"}}\\n')\n")
    (src / "tools" / "make_infra.py").write_text(gen.format(name="system.json"))
    (src / "tools" / "make_load.py").write_text(gen.format(name="ordinary.json"))
    _git(src, "init", "-q", "-b", "main")
    _git(src, "add", "-A")
    _git(src, "-c", "user.name=Someone Real", "-c", "user.email=real@example.invalid", "commit", "-q", "-m", "x")
    return src


def test_the_rooms_are_fresh_git_workdirs_by_a_neutral_author(tmp_path):
    from viz_promo import rooms
    src = _fake_shop(tmp_path)
    made = rooms.make_rooms(tmp_path / "ja" / "work", "ja", src)
    assert list(made) == list(T.ROOMS) and all(p.name == n for n, p in made.items())
    shop = made["demo-shop"]
    assert not (shop / "build").exists() and (shop / "jui.config.json").is_file()
    assert _git(shop, "log", "--format=%an <%ae>") == "demo <demo@example.invalid>\n"
    assert _git(shop, "status", "--porcelain") == ""
    assert json.loads((shop / "docs" / "infra" / "system.json").read_text()) == {"label": "ja"}
    assert (made["demo-admin"] / "README.md").read_text() == T.WORDS["ja"]["room_readme"]["demo-admin"]

    made = rooms.make_rooms(tmp_path / "en" / "work", "en", src)
    shop = made["demo-shop"]
    assert json.loads((shop / "docs" / "infra" / "system.json").read_text()) == {"label": "en"}
    assert json.loads((shop / "docs" / "infra" / "load" / "ordinary.json").read_text()) == {"label": "en"}
    assert _git(shop, "status", "--porcelain") == "" and len(_git(shop, "log", "--format=%an").split()) == 2


def test_the_home_has_the_settings_the_stand_ins_and_the_sessions(tmp_path):
    from viz_promo import rooms
    paths = rooms.make_home(tmp_path / "home")
    cfg = json.loads((paths["viz"] / "config.json").read_text())
    assert cfg["askWaitSec"] >= 600 and cfg["notifyPresenceSec"] >= 600
    out = subprocess.run([str(paths["bin"] / "xcrun"), "simctl", "list", "devices", "booted", "-j"], capture_output=True, text=True)
    assert json.loads(out.stdout) == {"devices": {}}
    work = {n: (tmp_path / "work" / n) for n in T.ROOMS}
    tr = rooms.write_sessions(paths, work, "en")
    assert set(tr) == {k for k, _, _ in T.SESSIONS}
    entry = json.loads((paths["sessions"] / f"{T.session_pid('s01')}.json").read_text())
    assert entry["name"] == T.WORDS["en"]["names"]["s01"] and entry["sessionId"] == T.session_id("s01")
    assert tr["s10"].parent.name == rooms.project_slug(work["demo-admin"])
