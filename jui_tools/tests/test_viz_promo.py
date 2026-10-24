"""tools/viz_promo/ (ticket 2026-10-21-viz-promo-replay-and-capture-tool): the parts that need no server and no browser.

The script: every event inside its chapter, the preludes untimed, every kind and target one the driver knows, every
session it names one of the floor's; the words: ja and en of the same shape; the frames: (end - start) x 30 from the
promo's timeline.json, whose ids and bounds the script was written for; the terminal's text cleaned of colour codes
and of the copy's own path; a missing feature named before a server starts; the rooms: demo-shop a fresh git workdir
of one commit by a neutral author, English labels from the project's own generators.
"""

from __future__ import annotations

import asyncio
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
        bounds = T.STANDALONE[c.id] if c.id in T.STANDALONE else T.BOUNDS[T.BOARDS.get(c.id, c.id)]   # a board: its chapter's
        assert (c.start, c.end) == bounds, (lang, c.id)
        for ev in c.events:
            assert ev.at is not None and c.start <= ev.at < c.end, (lang, c.id, ev)
            if ev.kind == "wheel":
                assert ev.at + ev.args["dur"] <= c.end, (lang, c.id, ev)
        assert all(ev.at is None for ev in c.prelude), (lang, c.id)
        ats = [ev.at for ev in c.events]
        assert ats == sorted(ats), (lang, c.id, "the events are written in their order")


def test_the_chapters_are_the_promos_viz_chapters():
    assert set(T.chapters("ja")) == set(T.CHAPTER_IDS) | set(T.BOARDS) | set(T.STANDALONE)
    assert set(T.BOUNDS) == set(T.CHAPTER_IDS) | set(T.TERM_CHAPTER_IDS) | set(T.T_CHAPTER_IDS)
    assert set(T.BOARDS.values()) <= set(T.TERM_CHAPTER_IDS)


def test_chapter_4s_2d_plays_the_payment_flow_again_with_auto_on():
    """The room drawn again in 2D stops the flow: it is pressed again there, after 自動 is ticked, so its light keeps
    moving to the chapter's end (requester 10-23)."""
    for lang in ("ja", "en"):
        ev = T.chapters(lang)["4"].events
        at = lambda css: [e.at for e in ev if e.kind == "click" and css in e.args["target"].get("css", "")]  # noqa: E731
        pays, auto, flat = at("data-sr-flow='payment'"), at("data-sr-fp='auto'"), at("#sr-mode-2d")
        assert len(pays) == 2 and len(auto) == 1 and len(flat) == 1, lang
        assert pays[0] < auto[0] < flat[0] < pays[1] < T.chapters(lang)["4"].end, lang


def test_every_chapter_that_shows_a_room_folds_its_robot_list_first():
    """2.3.20's この部屋のロボット covered the room and its task board on camera: a chapter that enters a room (before
    frame 0 or on camera) folds the list with the page's own button before frame 0."""
    for lang in ("ja", "en"):
        for cid, c in T.chapters(lang).items():
            enters = any(ev.kind == "click" and "room_tag" in ev.args.get("target", {}) for ev in c.prelude + c.events)
            if enters:
                assert any(ev.kind == "dbg" and ev.args.get("call") == "rosterFold" for ev in c.prelude), (lang, cid)


def test_the_board_ends_on_a_worktrees_spec_tagged_with_its_branch(tmp_path):
    """1b-board (2.3.21): the worktree is made before frame 0 (a new spec and the cart's spec changed), its session
    starts after the main spec is written, and the new spec is opened from the list once its row shows its branch.
    The terminal beside it keeps its 16 s of gates."""
    import subprocess
    from types import SimpleNamespace
    from viz_promo import capture, term
    for lang in ("ja", "en"):
        c = T.chapters(lang)["1b-board"]
        made = [ev for ev in c.prelude if ev.kind == "worktree"]
        assert len(made) == 1 and set(made[0].args["changes"]) == {T.WORKTREE["new"], T.WORKTREE["cart"]}, lang
        start = next(ev for ev in c.events if ev.kind == "wt_session")
        opened = next(ev for ev in c.events if ev.kind == "click" and "#wb-side-list" in ev.args["target"]["css"])
        last_write = max(ev.at for ev in c.events if ev.kind == "spec_write")
        assert last_write < start.at < opened.at < c.end and opened.args["expect"] == "wbtitle:" + T.WORDS[lang]["wt_spec"], lang
        assert opened.args["target"]["text"].startswith("⎇ " + T.WORKTREE["branch"]), "the tagged row, not the worktree room's own"
        assert any(ev.kind == "dbg" and ev.args.get("call") == "setProject" for ev in c.prelude), "the list scoped to the room"
        follow = [ev for ev in c.events if ev.kind == "hover" and ev.at > opened.at]
        assert follow and "aria-current" in follow[0].args["target"]["css"], "the cursor follows the opened row"
    assert term.TERM_SPAN["1b"] == 16.0 and T.BOUNDS["1b"][1] - T.BOUNDS["1b"][0] > 16.0
    # the worktree as the stage makes it: on its branch, the new file written, the cart's description edited, nothing committed
    room = tmp_path / "room"
    (room / "docs/screens/json").mkdir(parents=True)
    (room / T.WORKTREE["cart"]).write_text(json.dumps({"metadata": {"name": "Cart", "description": "old"}}))
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=room, check=True, capture_output=True, env=env)
    st = SimpleNamespace(home=tmp_path / "home", rooms={"demo-shop": room}, hook_env=env, worktrees={})
    capture.Stage.make_worktree(st, "demo-shop", T.WORKTREE["branch"], T.WORKTREE["name"], T.worktree_files(T.WORDS["ja"]))
    wt = st.worktrees[T.WORKTREE["name"]]
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=wt, capture_output=True, text=True, env=env).stdout.strip()
    assert branch == T.WORKTREE["branch"]
    assert json.loads((wt / T.WORKTREE["new"]).read_text())["metadata"]["displayName"] == T.WORDS["ja"]["wt_spec"]
    assert json.loads((wt / T.WORKTREE["cart"]).read_text())["metadata"] == {"name": "Cart", "description": T.WORDS["ja"]["wt_cart"]}
    assert json.loads((room / T.WORKTREE["cart"]).read_text())["metadata"]["description"] == "old", "the room's own copy is untouched"


def test_a_board_writes_its_spec_section_by_section_in_the_sheets_order():
    """1b-board: the file starts with its metadata; each write adds one section, each once, in the order the sheet
    shows them (30-source-live.js SPEC_KEYS), and the board is taken at the split's size."""
    order = ["structure", "stateManagement", "dataFlow", "userActions", "transitions", "branchContracts"]
    for lang in ("ja", "en"):
        c = T.chapters(lang)["1b-board"]
        reset = [ev for ev in c.prelude if ev.kind == "spec_reset"]
        assert len(reset) == 1 and reset[0].args["keep"] == ["type", "version", "metadata"], lang
        adds = [ev.args["add"] for ev in c.events if ev.kind == "spec_write"]
        assert adds == order, (lang, adds)
        assert c.viewport == T.SPLIT_VIEWPORT
        assert any(ev.kind == "dbg" and ev.args.get("call") == "openSpec" for ev in c.prelude), lang


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
        assert set(T.WORK.values()) <= set(T.WORDS[lang]["prompts"]) | set(T.WORDS[lang]["prompts2"])
        assert all(T.prompt(T.WORDS[lang], k) for k in keys)
        assert T.WORDS[lang]["answer"] in [o["label"] for o in T.WORDS[lang]["question"]["options"]]
        names = list(T.WORDS[lang]["names"].values())
        assert len(set(names)) == len(names), "a talk row is found by its name"


def test_thirty_robots_on_one_floor_and_no_room_crowded():
    rooms = [room for _, _, room in T.SESSIONS]
    assert len(rooms) == 30 and set(rooms) == set(T.ROOMS)
    assert len(T.ROOMS) <= 6, "a floor holds six rooms"
    assert max(rooms.count(r) for r in T.ROOMS) <= 10, "a room of more than ten drops its decor"


def test_the_segments_lie_inside_their_chapter_and_its_events_come_after():
    for seg, (chapter, s, e, rel) in T.SEGMENTS.items():
        cs, ce = T.BOUNDS[chapter]
        assert cs <= s < e <= ce and T.frame_count(s, e) == 90 and rel.startswith("docs/infra/load/")
        assert seg in T.CAPTURE_IDS
        for lang in T.WORDS:
            assert all(ev.at >= e for ev in T.chapters(lang)[chapter].events), (lang, seg)


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
        if launcher.startswith("!"):
            assert shown.split()[0] == launcher[1:]
            continue
        assert (root / launcher).is_file(), launcher
        assert shown.split()[0] == Path(launcher).name
    assert abs(sum(sec for _, sec in term.GENERATED + term.HAND_WRITTEN) + term.SPEC_HTML[2] - (T.BOUNDS["1a"][1] - T.BOUNDS["1a"][0])) < 1e-9
    # verify finds the drift, the layout is restored, verify passes (requester 10-22: drift caught is the message)
    assert [g[0].split()[:2] for g in term.GATES[:3]] == [["jui", "verify"], ["git", "restore"], ["jui", "verify"]]
    assert term.GATES[1][1][-1] == term.DRIFT[0] and term.GATES[0][2] and term.GATES[2][2]
    branch = [g for g in term.GATES if "branch-tests" in g[0]]
    assert len(term.GATES) == 5 and len(branch) == 1 and "-p" not in branch[0][1], "branch-tests on the web only"


def test_the_drift_is_one_undeclared_binding_and_a_gated_verify(tmp_path):
    from viz_promo import term
    rel, was, now = term.DRIFT
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text('{"text": "%s"}' % was)
    (tmp_path / "jui.config.json").write_text('{"verify": {"x": 1}}')
    term.make_drift(tmp_path)
    assert now in (tmp_path / rel).read_text() and was not in (tmp_path / rel).read_text()
    assert json.loads((tmp_path / "jui.config.json").read_text())["verify"] == {"x": 1, "external": "gate"}


def test_1a_ends_on_the_spec_document_held_long_enough_to_read(tmp_path):
    """The spec document comes last, under the subtitle "you fix the spec" (12–16 s), for at least 4 s, and stops
    at its parts (requester 10-22: it went by too fast to read)."""
    from viz_promo import term
    for rel, _ in term.GENERATED + term.HAND_WRITTEN:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("// @generated\n" if "Generated" in rel or rel.endswith(".json") else "body\n")
    files = term.read_files(tmp_path, "<html><body>doc</body></html>")
    assert [f["path"] for f in files][-2:] == [term.HAND_WRITTEN[0][0], term.SPEC_HTML[1]]
    assert files[-1]["html"].startswith("<html>") and not files[-2]["generated"]
    assert files[-1]["sec"] >= 4.0 and files[-1]["stops"]
    start = T.BOUNDS["1a"][1] - files[-1]["sec"]
    assert start - T.BOUNDS["1a"][0] <= 8.0, "the spec document is on screen for the whole of 1a's last subtitle (its last 4 s)"
    assert "html" not in files[0]


def test_the_stand_in_sessions_are_launched_as_the_plugins_sessions_are():
    # the page reads a session's argv (sources/launch.py): the stand-in's must classify as a session the plugin's
    # channel hands a prompt to, with no "start it with ..." reason on its cards
    from jui_cli.viz.sources import launch
    from viz_promo import capture
    argv = ["/usr/bin/python3", *capture.STANDIN_ARGV]
    assert launch.classify(argv, "cli", "plugin") == "dev"
    assert launch.classify(["/usr/bin/python3", "-I", "-S", "-c", "x"], "cli", "plugin") == "no-flag"


def test_a_relayed_permission_request_has_the_channels_shape(tmp_path):
    from viz_promo import capture
    stage = type("S", (), {})()
    relay = capture.Relay(stage)
    sent = []
    relay._call = lambda method, path, body=None, timeout=5: sent.append((method, path, body)) or (204, b"")
    relay.request("s03", "Bash", {"command": "jui build --ios-only", "description": "build"})
    assert sent == [] and relay.pending[0][0] == "s03", "before the channel connects it waits, as channel.py's outbox"
    relay.ids["s03"] = "ch1"
    relay.request("s03", "Bash", {"command": "jui build --ios-only"})
    method, path, body = sent[0]
    assert (method, path, body["channelId"], body["tool_name"]) == ("POST", "/channel/request", "ch1", "Bash")
    assert len(body["request_id"]) == 5 and body["request_id"].isalpha() and "l" not in body["request_id"]
    assert json.loads(body["input_preview"]) == {"command": "jui build --ios-only"}


DEMO_SHOP = Path(os.environ.get("JUI_PROMO_DEMO_SHOP", Path.home() / "resource" / "jsonui-demo-shop"))


def test_a_flows_time_counts_moves_nodes_and_the_longest_lane():
    flow = {"id": "f", "steps": [
        {"from": "a", "to": "b"}, {"at": "b", "label": "say"},
        {"branch": {"label": "?", "default": "x", "choices": [
            {"id": "x", "steps": [{"parallel": [[{"from": "b", "to": "c"}], [{"from": "b", "to": "d"}, {"from": "d", "to": "b"}]]}]},
            {"id": "y", "steps": [{"from": "b", "to": "e"}]}]}},
        {"from": "b", "to": "a"}]}
    assert T.flow_segments(flow, ["x"]) == [T.MOVE_MS + T.NODE_MS, 2 * T.MOVE_MS + T.MOVE_MS]
    assert T.flow_segments(flow, ["y"]) == [T.MOVE_MS + T.NODE_MS, 2 * T.MOVE_MS]
    ch = T.Chapter("t", 0, 10, [T.P("dbg", call="srFlowSpeed", speed=2)], [
        T.E(1.0, "click", target={"css": "#sr-board [data-sr-flow='f']"}),
        T.E(1.2, "click", target={"css": "#sr-choices [data-sr-choice='x']"}, arg="x")])
    got = T.flow_budget(ch, flow)
    # to the branch 0.675 s at 2x: the press at 1.2 waits until 1.675, then 1.35 s more
    assert got["speed"] == 2.0 and got["choices"] == [("x", 1.675)] and got["end"] == pytest.approx(3.025)


@pytest.mark.skipif(not (DEMO_SHOP / "docs" / "infra" / "system.json").is_file(), reason="the demo-shop workdir is not on this machine")
def test_chapter_4_starts_close_on_the_order_flow_then_pulls_back_to_the_whole_system():
    """2.3.19's room, small to large: the order flow plays up close and its two choices are pressed as their branches
    come (a press that waits long shows a stopped light), then the camera pulls back once both are taken, and the
    payment flow is pressed in the wide view."""
    flows = {f["id"]: f for f in json.loads((DEMO_SHOP / "docs" / "infra" / "system.json").read_text(encoding="utf-8"))["flows"]}
    for lang in T.WORDS:
        ch = T.chapters(lang)["4"]
        # the speed changes after the first choice: the second branch is 3.6 s at 1x after it
        first = T.flow_budget(ch, flows["order"])
        assert [p for p, _ in first["choices"]][:1] == ["hit"] and abs(first["choices"][0][1] - (ch.start + 4.0)) <= 0.5, first
        hit = first["choices"][0][1]
        second = next(ev.at for ev in ch.events if ev.args.get("arg") == "in")
        assert abs(hit + 3.6 - second) <= 0.5, (hit, second)
        dolly = next(ev for ev in ch.events if ev.kind == "dolly")
        assert dolly.at > second and dolly.at + dolly.args["dur"] <= ch.end and dolly.args["factor"] > 1
        pay = next(ev.at for ev in ch.events if ev.kind == "click" and "data-sr-flow='payment'" in ev.args["target"]["css"])
        assert pay >= dolly.at + dolly.args["dur"], "the payment flow plays in the wide view"


FAKE_LOCK = """import json, os
def hold(path=None, say_every=30.0, poll=0.5, say=print, only=None, priority=None):
    with open(os.environ["PROMO_LOCK_LOG"], "a") as f:
        f.write(json.dumps({"step": "lock", "priority": priority, "only": only}) + "\\n")
    return os.open(os.devnull, os.O_RDONLY)
"""


def _fake_tree(tmp_path, with_lock=True):
    root = tmp_path / "cli"
    (root / "jui_tools" / "bin").mkdir(parents=True)
    (root / "jui_tools" / "bin" / "jui").write_text("")
    if with_lock:
        (root / "jui_tools" / "tools" / "viz_e2e").mkdir(parents=True)
        (root / "jui_tools" / "tools" / "viz_e2e" / "e2e_lock.py").write_text(FAKE_LOCK)
    return root


def test_run_takes_the_trees_lock_before_any_serve(tmp_path, monkeypatch):
    from viz_promo import run
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("PROMO_LOCK_LOG", str(log))
    monkeypatch.setenv("JUI_VIZ_E2E_PRIORITY", "1")   # the environment never makes it a priority ticket

    async def serves(a):   # where the captures start their servers and browsers
        with open(log, "a") as f:
            f.write(json.dumps({"step": "serve"}) + "\n")
        return 0
    monkeypatch.setattr(run, "main_async", serves)
    assert run.main(["--lang", "ja", "--chapters", "hook,2", "--jui-root", str(_fake_tree(tmp_path))]) == 0
    steps = [json.loads(line) for line in log.read_text().splitlines()]
    assert [s["step"] for s in steps] == ["lock", "serve"], steps
    assert steps[0]["priority"] is False and steps[0]["only"] == ["viz_promo ja hook,2"]


def test_run_without_the_trees_lock_says_so(tmp_path, monkeypatch, capsys):
    from viz_promo import run
    monkeypatch.setattr(run, "main_async", lambda a: asyncio.sleep(0, result=0))
    assert run.main(["--lang", "en", "--chapters", "6", "--jui-root", str(_fake_tree(tmp_path, with_lock=False))]) == 0
    assert "running without the machine's queue" in capsys.readouterr().out


def test_run_with_no_lock_takes_no_lock(tmp_path, monkeypatch):
    """--no-lock: the capture runs beside a running e2e when told to (its own HOME, server and port either way)."""
    from viz_promo import run
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("PROMO_LOCK_LOG", str(log))

    async def serves(a):
        with open(log, "a") as f:
            f.write(json.dumps({"step": "serve"}) + "\n")
        return 0
    monkeypatch.setattr(run, "main_async", serves)
    assert run.main(["--lang", "ja", "--chapters", "2", "--no-lock", "--jui-root", str(_fake_tree(tmp_path))]) == 0
    assert [json.loads(line)["step"] for line in log.read_text().splitlines()] == ["serve"]


def test_chapter_2_opens_sorts_by_state_and_folds_the_robot_list():
    for lang in ("ja", "en"):
        ev = [e for e in T.chapters(lang)["2"].events if "roster" in json.dumps(e.args)]
        assert [(e.kind, e.args.get("value"), e.args.get("expect")) for e in ev] == [
            ("click", None, "roster_open"), ("select", "state", "roster_state"), ("click", None, "roster_folded")], lang
        idle = next(e.at for e in T.chapters(lang)["2"].events if e.kind == "idle")
        assert idle < ev[0].at and ev[-1].at < T.chapters(lang)["2"].end


def test_the_english_copy_keeps_the_loads_written_by_hand(tmp_path):
    """make_load.py --lang en writes the loads it knows; the rows added by hand for the migration plans' nodes are put
    back (numbers only), so the English plans' months are the Japanese ones."""
    from viz_promo.rooms import keep_hand_loads
    (tmp_path / "a.json").write_text(json.dumps({"label": "An ordinary month", "loads": [{"node": "api", "quantities": {"q": 1}}]}))
    by_hand = {"a.json": {"label": "普段の月", "loads": [{"node": "api", "quantities": {"q": 9}}, {"node": "reco-fn", "quantities": {"q": 2}}]},
               "gone.json": {"loads": [{"node": "x"}]}}
    assert keep_hand_loads(tmp_path, by_hand) == 1
    doc = json.loads((tmp_path / "a.json").read_text())
    assert doc["label"] == "An ordinary month" and doc["loads"] == [{"node": "api", "quantities": {"q": 1}}, {"node": "reco-fn", "quantities": {"q": 2}}]
    assert not (tmp_path / "gone.json").exists()


def test_frame_intervals_are_summed_as_percentiles():
    from viz_promo import capture
    got = capture.percentiles([16.0] * 8 + [50.0, 120.0])
    assert got == {"frames": 11, "p50": 16.0, "p90": 50.0, "max": 120.0}
    assert capture.percentiles([])["p50"] is None


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
    assert "askWaitSec" not in cfg and cfg["notifyPresenceSec"] >= 600, "the top bar shows the question window: the default"
    out = subprocess.run([str(paths["bin"] / "xcrun"), "simctl", "list", "devices", "booted", "-j"], capture_output=True, text=True)
    assert json.loads(out.stdout) == {"devices": {}}
    work = {n: (tmp_path / "work" / n) for n in T.ROOMS}
    tr = rooms.write_sessions(paths, work, "en")
    assert set(tr) == {k for k, _, _ in T.SESSIONS}
    entry = json.loads((paths["sessions"] / f"{T.session_pid('s01')}.json").read_text())
    assert entry["name"] == T.WORDS["en"]["names"]["s01"] and entry["sessionId"] == T.session_id("s01")
    assert tr["s10"].parent.name == rooms.project_slug(work["demo-admin"])


def test_2_3_23_adds_the_spec_diff_the_flow_views_and_chapter_t():
    """2.3.23's re-take (requester 10-25): 1b-board ends on ベースとの差分 of the worktree's cart spec; chapter 4's last
    seconds show 今関係 and 範囲で寄る after the 2D payment flow; Ta4 shows the two screen tests chapter T-a runs; the
    chapters after 1b are moved on the new clock and every event stays inside its chapter."""
    for lang in ("ja", "en"):
        cs = T.chapters(lang)
        board = cs["1b-board"]
        assert (board.start, board.end) == (18, 46)
        diff = [e for e in board.events if e.kind == "click" and e.args["target"].get("css") == "#wb-diff"]
        assert len(diff) == 1 and diff[0].args["expect"] == "specdiff" and diff[0].at < board.end - 3
        four = cs["4"]
        assert (four.start, four.end) == T.BOUNDS["4"]
        flat = max(e.at for e in four.events if e.kind == "click" and "data-sr-flow='payment'" in e.args["target"].get("css", ""))
        now = [e.at for e in four.events if e.kind == "click" and "data-sr-fp-show='now'" in e.args["target"].get("css", "")]
        drag = [e for e in four.events if e.kind == "drag"]
        assert now and flat < now[0] and drag and now[0] < drag[0].at < four.end
        ta4 = cs["Ta4"]
        assert [e.args["name"] for e in ta4.events if e.kind == "tests_case"] == [n for _, _, n in T.T_CASES]
        for cid, c in cs.items():
            if cid in T.BOUNDS:
                assert (c.start, c.end) == tuple(T.BOUNDS[cid]), cid
                assert all(c.start <= e.at < c.end for e in c.events), cid

