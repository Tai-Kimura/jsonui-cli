"""The sorting factory (viz/slack_room.py): the Slack intake's room, its robot, the task board's states and the two prompts.
Design: docs/plans/2026-11-02-viz-slack-intake-design.md §5–§7."""
from __future__ import annotations

import asyncio
import json
import os
import stat

import pytest

from jui_cli.viz import paths, slack_room
from jui_cli.viz.slack import config as slack_config
from jui_cli.viz.ingest import World
from jui_cli.viz.rooms import Rooms, tilde
from jui_cli.viz.state import VizState


class FakeWorld:
    """What SlackRoom reads of the World: sessions, rooms, prompt_refusal and submit_prompt."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.rooms = Rooms()
        self.sent: list[tuple[str, str]] = []
        self.no_channel: set[str] = set()

    def add(self, sid, cwd, status="idle", started=0, label=None, title=""):
        project = self.rooms.project_for(os.path.expanduser(cwd))
        self.sessions[sid] = {"id": sid, "label": label or sid[:2], "cwd": tilde(cwd), "status": status, "startedAt": started,
                              "projectId": project["id"], "title": title}

    def prompt_refusal(self, sid):
        s = self.sessions.get(sid)
        if s is None or s["status"] == "ended":
            return 404, "no such session"
        return (409, "no channel") if sid in self.no_channel else None

    async def submit_prompt(self, sid, text, at, attached=None):
        refused = self.prompt_refusal(sid)
        if refused is None:
            self.sent.append((sid, text))
        return refused


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("JUI_VIZ_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    paths.viz_home().mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def factory(home):
    root = home / "orch"
    (root / "projects" / "shop").mkdir(parents=True)
    (root / "tasks").mkdir()
    slack_config.save({"orchestrationDir": "~/orch", "source": {"workspaces": [{"name": "w", "token": "x"}]},
                       "router": {"adapter": "haiku", "prompt": {"instructions": "old", "projects": {}}}})
    return root


def message(root, project, name, text="hello", **extra):
    path = root / "projects" / project / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"workspace": "w", "channel": "C1", "user": "U1", "ts": "1.0", "text": text,
                                "router": {"adapter": "haiku", "choice": project, "confidence": 0.9}, **extra}))
    return f"projects/{project}/{name}"


def task(root, tid, status="draft", **extra):
    data = {"id": tid, "title": "T " + tid, "projectId": "shop", "sources": [], "prompt": "do it",
            "target": {"sessionName": "", "sessionId": None}, "launchCommand": None, "status": status, "createdAt": 1, **extra}
    (root / "tasks" / f"{tid}.json").write_text(json.dumps(data))
    return data


def room_for(world):
    room = slack_room.SlackRoom(world)
    room.load()
    world.rooms.set_factory_dir(str(room.root))
    return room


def run(coro):
    return asyncio.run(coro)


# ---- the room of its own ------------------------------------------------------------------------------------------

def test_a_session_in_the_folder_is_in_the_factorys_room_and_no_project_is(home, factory):
    world = World(VizState())
    world._session("before", str(factory / "projects"), 1)        # seen before the folder was known
    world._session("shop", str(home / "shop"), 1)
    world.set_factory_dir(str(factory), 2)
    world._session("after", str(factory), 3)
    pid = {sid: s["projectId"] for sid, s in world.sessions.items()}
    assert pid["before"] == pid["after"] != pid["shop"]
    assert world.rooms.projects[pid["after"]].get("factory") is True
    assert "factory" not in world.rooms.projects[pid["shop"]]
    world.set_factory_dir(str(home / "elsewhere"), 4)           # the folder moved: back to a room of its own walk
    assert "factory" not in world.rooms.projects[world.sessions["before"]["projectId"]]


def test_the_robot_is_the_session_in_the_folder_and_never_a_target(home, factory):
    world = FakeWorld()
    world.add("bot1", "~/orch", started=1)
    world.add("bot2", "~/orch/projects", started=2)
    world.add("dev", "~/shop", started=3, title="shop work")
    world.add("gone", "~/shop", status="ended")
    room = room_for(world)
    assert room.robot() == "bot2"                                  # the newest
    world.no_channel.add("bot2")
    assert room.robot() == "bot1"                                  # one that can take a prompt first
    assert [t["sessionId"] for t in room.targets()] == ["dev"]
    with pytest.raises(slack_room.Refused):
        room._target({"sessionId": "bot1"})


# ---- telling the robot ------------------------------------------------------------------------------------------

def test_new_messages_are_told_once_when_the_robot_is_idle(home, factory):
    world = FakeWorld()
    world.add("bot", "~/orch", status="busy")
    world.add("dev", "~/shop")
    a = message(factory, "shop", "1-w-C1.json")
    b = message(factory, "shop", "2-w-C1.json")
    task(factory, "t1", sources=[b])                               # already in a task: not told
    room = room_for(world)
    assert room.pending() == [a]
    assert run(room.tell_robot(100_000)) is False and room.note == "busy"
    world.sessions["bot"]["status"] = "idle"
    assert run(room.tell_robot(100_000)) is True
    sid, text = world.sent[-1]
    assert sid == "bot" and a in text and b not in text and "sessionId=dev" in text and slack_room.LAUNCH_COMMAND in text
    room.load()
    assert room.pending() == []
    assert run(room.tell_robot(200_000)) is False and len(world.sent) == 1
    saved = json.loads((factory / ".state" / "board.json").read_text())
    assert saved["notified"] == [a]
    c = message(factory, "shop", "3-w-C1.json")
    room.load()
    assert run(room.tell_robot(100_000 + slack_room.NOTIFY_GAP_MS - 1)) is False   # too soon after the last
    assert run(room.tell_robot(100_000 + slack_room.NOTIFY_GAP_MS)) is True and c in world.sent[-1][1]


def test_no_robot_or_no_channel_tells_nobody_and_says_why(home, factory):
    world = FakeWorld()
    message(factory, "shop", "1-w-C1.json")
    room = room_for(world)
    assert run(room.tell_robot(1)) is False and room.note == "no-robot"
    world.add("bot", "~/orch")
    world.no_channel.add("bot")
    assert run(room.tell_robot(1)) is False and room.note == "no-channel" and world.sent == []


def test_the_task_prompt_from_the_config_goes_with_the_notice(home, factory):
    cfg = json.loads(slack_room.config_path().read_text())
    slack_config.save({**cfg, "taskPrompt": "MY TASK RULES"})
    world = FakeWorld()
    world.add("bot", "~/orch")
    message(factory, "shop", "1-w-C1.json")
    room = room_for(world)
    run(room.tell_robot(10**6))
    assert world.sent[-1][1].startswith("MY TASK RULES")


# ---- the board ----------------------------------------------------------------------------------------------------

def test_draft_ready_start_ended_done(home, factory):
    world = FakeWorld()
    world.add("bot", "~/orch")
    world.add("dev", "~/shop", label="a3", title="shop work")
    task(factory, "t1")
    room = room_for(world)
    with pytest.raises(slack_room.Refused) as no:
        run(room.act({"id": "t1", "op": "start", "target": {"sessionId": "dev"}}, 5))
    assert no.value.status == 409                                  # a draft is not started
    run(room.act({"id": "t1", "op": "save", "prompt": "edited prompt", "target": {"sessionId": "dev"}}, 5))
    run(room.act({"id": "t1", "op": "ready"}, 6))
    run(room.act({"id": "t1", "op": "start"}, 7))
    assert world.sent == [("dev", "edited prompt")]
    t = json.loads((factory / "tasks" / "t1.json").read_text())
    assert t["status"] == "working" and t["startedAt"] == 7 and t["target"] == {"sessionName": "shop work", "sessionId": "dev"}
    with pytest.raises(slack_room.Refused):
        run(room.act({"id": "t1", "op": "save", "prompt": "late"}, 8))   # not edited once started
    room.load()
    assert room.follow(8) is False                                 # still idle: the prompt is not taken yet
    world.sessions["dev"]["status"] = "busy"
    room.load()
    assert room.follow(9) is False
    world.sessions["dev"]["status"] = "idle"
    room.load()
    assert room.follow(10) is True
    t = json.loads((factory / "tasks" / "t1.json").read_text())
    assert t["status"] == "ended" and t["endedAt"] == 10
    run(room.act({"id": "t1", "op": "done"}, 11))
    t = json.loads((factory / "tasks" / "t1.json").read_text())
    assert t["status"] == "done" and t["doneAt"] == 11 and t["prompt"] == "edited prompt"


def test_a_started_task_whose_session_is_gone_is_ended(home, factory):
    world = FakeWorld()
    task(factory, "t1", status="working", target={"sessionName": "x", "sessionId": "gone"}, startedAt=1)
    room = room_for(world)
    room.board["started"]["t1"] = 1                                # sent with 開始
    assert room.follow(5) is False                                 # not heard of yet: a server just started
    assert room.follow(5 + slack_room.GONE_GRACE_MS - 1) is False
    assert room.follow(5 + slack_room.GONE_GRACE_MS) is True
    assert json.loads((factory / "tasks" / "t1.json").read_text())["status"] == "ended"


def test_a_started_task_whose_session_ended_is_ended_at_once(home, factory):
    world = FakeWorld()
    world.add("dev", "~/shop", status="ended")
    task(factory, "t1", status="working", target={"sessionName": "x", "sessionId": "dev"}, startedAt=1)
    room = room_for(world)
    room.board["started"]["t1"] = 1
    assert room.follow(5) is True
    assert json.loads((factory / "tasks" / "t1.json").read_text())["status"] == "ended"


def test_a_start_the_session_refuses_stays_ready(home, factory):
    world = FakeWorld()
    world.add("dev", "~/shop")
    world.no_channel.add("dev")
    task(factory, "t1", status="ready")
    room = room_for(world)
    with pytest.raises(slack_room.Refused) as no:
        run(room.act({"id": "t1", "op": "start", "target": {"sessionId": "dev"}}, 5))
    assert no.value.status == 409
    assert json.loads((factory / "tasks" / "t1.json").read_text())["status"] == "ready"


def test_revise_asks_the_robot_and_changes_nothing(home, factory):
    world = FakeWorld()
    task(factory, "t1")
    room = room_for(world)
    with pytest.raises(slack_room.Refused):
        run(room.act({"id": "t1", "op": "revise", "text": "shorter"}, 1))   # no robot
    world.add("bot", "~/orch")
    run(room.act({"id": "t1", "op": "revise", "text": "shorter"}, 2))
    assert world.sent[-1][0] == "bot" and "tasks/t1.json" in world.sent[-1][1] and "shorter" in world.sent[-1][1]
    assert json.loads((factory / "tasks" / "t1.json").read_text())["status"] == "draft"


@pytest.mark.parametrize("tid", ["../x", "", "a/b", ".hidden", "x" * 81, 7])
def test_a_task_id_that_is_not_one_is_refused(home, factory, tid):
    room = room_for(FakeWorld())
    with pytest.raises(slack_room.Refused) as no:
        run(room.act({"id": tid, "op": "done"}, 1))
    assert no.value.status == 400


def test_the_slice_says_what_the_page_shows(home, factory):
    world = FakeWorld()
    world.add("bot", "~/orch", label="a1")
    message(factory, "shop", "1-w-C1.json", text="line one\n  and two")
    (factory / "projects" / "shop" / "2-w-C1.json").write_text("{broken")
    (factory / "_unsorted").mkdir()
    (factory / "_unsorted" / "x.json").write_text("{}")
    task(factory, "t1", status="odd")
    room = room_for(world)
    s = room.slice()
    assert s["dir"] == "~/orch" and s["dirExists"] is True and s["robot"]["label"] == "a1"
    assert s["arrivals"]["total"] == 2 and s["arrivals"]["broken"] == 1 and s["arrivals"]["unsorted"] == 1
    assert s["arrivals"]["byProject"] == {"shop": 2} and s["arrivals"]["pending"] == 1
    assert any(r.get("head") == "line one and two" for r in s["arrivals"]["recent"])
    assert s["tasks"][0]["status"] == "draft"                    # a status that is not one shows as a draft
    assert s["robotLaunch"] == f"cd ~/orch && {slack_room.LAUNCH_COMMAND}"
    assert s["prompts"]["instructions"] == "old"


def test_no_folder_yet_is_an_empty_room(home):
    room = room_for(FakeWorld())
    s = room.slice()
    assert s["dir"] == slack_room.DEFAULT_DIR and s["dirExists"] is False and s["config"]["state"] == "missing"
    assert s["tasks"] == [] and s["arrivals"]["total"] == 0


# ---- the two prompts ----------------------------------------------------------------------------------------------

def test_saving_the_prompts_keeps_every_other_key_and_0600(home, factory):
    prompts = slack_room.clean_prompts({"instructions": "sort well", "chitchat": "lunch talk", "taskPrompt": "make tasks",
                                        "projects": {"shop": "the shop app", "site": "the booking site"}})
    slack_room.save_prompts(prompts)
    cfg = json.loads(slack_room.config_path().read_text())
    assert cfg["source"] == {"workspaces": [{"name": "w", "token": "x"}]} and cfg["router"]["adapter"] == "haiku"
    assert "schedule" not in cfg                                  # stage 1's defaults are not written in
    assert cfg["router"]["prompt"] == {"instructions": "sort well", "projects": {"shop": "the shop app", "site": "the booking site"}, "chitchat": "lunch talk"}
    assert cfg["taskPrompt"] == "make tasks"
    assert stat.S_IMODE(slack_room.config_path().stat().st_mode) == 0o600


def test_a_broken_config_is_not_overwritten(home):
    slack_room.config_path().write_text("{not json")
    with pytest.raises(slack_room.Refused):
        slack_room.save_prompts(slack_room.clean_prompts({"instructions": "", "chitchat": "", "taskPrompt": "", "projects": {}}))
    assert slack_room.config_path().read_text() == "{not json"


@pytest.mark.parametrize("body", [
    {"instructions": 1, "chitchat": "", "taskPrompt": "", "projects": {}},
    {"instructions": "", "chitchat": "", "taskPrompt": "", "projects": []},
    {"instructions": "", "chitchat": "", "taskPrompt": "", "projects": {"a/b": "x"}},
    {"instructions": "", "chitchat": "", "taskPrompt": "", "projects": {"chitchat": "x"}},
    {"instructions": "", "chitchat": "", "taskPrompt": "", "projects": {"tasks": "x"}},
    {"instructions": "", "chitchat": "", "taskPrompt": "", "projects": {"_unsorted": "x"}},
    {"instructions": "", "chitchat": "", "taskPrompt": "", "projects": {"has space": "x"}},
    {"instructions": "x" * (slack_room.PROMPT_MAX + 1), "chitchat": "", "taskPrompt": "", "projects": {}},
])
def test_a_prompts_body_that_is_not_right_is_refused(body):
    with pytest.raises(slack_room.Refused):
        slack_room.clean_prompts(body)


# ---- the routes, on a real server ------------------------------------------------------------------------------------

@pytest.fixture()
def served(tmp_path, monkeypatch):
    from tests.test_viz_clock_out import DROP, Viz

    home = tmp_path / "home"
    for k in DROP:
        monkeypatch.delenv(k, raising=False)
    orch = home / "orch"
    (orch / "tasks").mkdir(parents=True)
    (orch / "projects" / "shop").mkdir(parents=True)
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True)
    (state / "slack.json").write_text(json.dumps({"orchestrationDir": "~/orch", "source": {"mode": "api"}, "schedule": {"everyHours": 0, "at": "09:00"}}))
    (state / "slack.json").chmod(0o600)                              # stage 1 reads it only so
    task(orch, "t1")
    message(orch, "shop", "1-w-C1.json")
    v = Viz(home)
    v.orch = orch
    try:
        yield v
    finally:
        v.stop()


def _post(viz, route, body, **over):
    return viz.raw("POST", route, viz.page_headers(**over), json.dumps(body).encode())


def test_the_server_gives_the_room_its_slice_and_its_robot_a_room_of_its_own(served):
    served.wait(lambda: (served.snapshot()["slices"].get("slackRoom") or {}).get("tasks"), "the room's slice")
    s = served.snapshot()["slices"]["slackRoom"]
    assert s["dir"] == "~/orch" and [t["id"] for t in s["tasks"]] == ["t1"] and s["arrivals"]["total"] == 1
    for sid, cwd in (("f1000000-0000-4000-8000-000000000001", served.orch), ("f1000000-0000-4000-8000-000000000002", served.home / "shop")):
        (served.home / "shop").mkdir(exist_ok=True)
        status, _ = served.local("POST", "/hook", {"hook_event_name": "SessionStart", "session_id": sid, "cwd": str(cwd), "source": "startup"})
        assert status in (200, 204)
    served.wait(lambda: len(served.snapshot()["slices"].get("projects") or []) == 2, "two rooms")
    rooms = {p["displayRoot"]: p for p in served.snapshot()["slices"]["projects"]}
    assert rooms["~/orch"].get("factory") is True and "factory" not in rooms["~/shop"]
    served.wait(lambda: (served.snapshot()["slices"]["slackRoom"].get("robot") or {}).get("sessionId") == "f1000000-0000-4000-8000-000000000001", "the robot")


def test_the_board_routes_take_the_pages_checks_and_write(served):
    assert _post(served, "/api/slack-room/task", {"id": "t1", "op": "ready"}, **{"X-Jui-Viz-Token": "wrong"})[0] == 401
    assert _post(served, "/api/slack-room/task", {"id": "t1", "op": "ready"}, Origin="http://evil.example")[0] == 403
    assert served.raw("GET", "/api/slack-room/task", served.page_headers())[0] == 405
    assert json.loads((served.orch / "tasks" / "t1.json").read_text())["status"] == "draft"
    status, text = _post(served, "/api/slack-room/task", {"id": "t1", "op": "ready"})
    assert status == 200, text
    assert json.loads((served.orch / "tasks" / "t1.json").read_text())["status"] == "ready"
    assert _post(served, "/api/slack-room/task", {"id": "t1", "op": "start", "target": {"sessionId": "nobody"}})[0] == 404
    status, text = _post(served, "/api/slack-room/prompts", {"instructions": "i", "chitchat": "c", "taskPrompt": "t", "projects": {"shop": "s"}})
    assert status == 200, text
    cfg = json.loads((served.state / "slack.json").read_text())
    assert cfg["source"] == {"mode": "api"} and cfg["schedule"]["everyHours"] == 0 and cfg["taskPrompt"] == "t" and cfg["router"]["prompt"]["projects"] == {"shop": "s"}
    served.wait(lambda: served.snapshot()["slices"]["slackRoom"]["prompts"]["taskPrompt"] == "t", "the prompts in the slice")


# ---- talking, grouping, a prompt changed by hand, short ids (11-02 additions) ----------------------------------------

def test_a_talking_task_is_raised_to_a_draft_by_hand_only_from_talking(home, factory):
    world = FakeWorld()
    task(factory, "T-0001", status="talking", prompt="")
    task(factory, "T-0002", status="draft")
    room = room_for(world)
    run(room.act({"id": "T-0001", "op": "draft"}, 1))
    assert json.loads((factory / "tasks" / "T-0001.json").read_text())["status"] == "draft"
    with pytest.raises(slack_room.Refused):
        run(room.act({"id": "T-0002", "op": "draft"}, 1))
    with pytest.raises(slack_room.Refused):
        run(room.act({"id": "T-0001", "op": "start", "target": {"sessionId": None}}, 1))   # a draft is not started


def test_a_prompt_saved_by_hand_is_marked_with_the_sources_it_had(home, factory):
    world = FakeWorld()
    a = message(factory, "shop", "1-w-C1.json")
    task(factory, "T-0001", sources=[a], prompt="robot's words")
    room = room_for(world)
    run(room.act({"id": "T-0001", "op": "save", "prompt": "robot's words"}, 1))      # unchanged: not marked
    assert "promptEditedByUser" not in json.loads((factory / "tasks" / "T-0001.json").read_text())
    run(room.act({"id": "T-0001", "op": "save", "prompt": "my words"}, 2))
    t = json.loads((factory / "tasks" / "T-0001.json").read_text())
    assert t["promptEditedByUser"] is True and t["sourcesAtEdit"] == [a] and t["prompt"] == "my words"


def test_the_notice_lists_the_open_tasks_and_the_next_short_id(home, factory):
    world = FakeWorld()
    world.add("bot", "~/orch")
    task(factory, "T-0007", status="talking", title="still talking", threads=["111.1"])
    task(factory, "T-0012", status="ready", promptEditedByUser=True)
    task(factory, "T-0003", status="done", title="FINISHED-XYZ")
    task(factory, "legacy-name", status="draft")
    message(factory, "shop", "1-w-C1.json")
    room = room_for(world)
    assert room.next_id() == "T-0013"
    run(room.tell_robot(10**6))
    text = world.sent[-1][1]
    assert "T-0007 [talking] still talking threads=111.1" in text and "T-0012 [ready]" in text and "promptEditedByUser" in text
    assert "FINISHED-XYZ" not in text and "T-0013" in text


def test_the_slice_gives_each_tasks_source_messages(home, factory):
    a = message(factory, "shop", "1-w-C1.json", text="first")
    b = message(factory, "shop", "2-w-C1.json", text="reply", threadTs="1.0")
    task(factory, "T-0001", sources=[a, b, "projects/shop/gone.json"], threads=["1.0"])
    s = room_for(FakeWorld()).slice()
    assert s["sourceHeads"][a]["head"] == "first" and s["sourceHeads"][b]["threadTs"] == "1.0"
    assert "projects/shop/gone.json" not in s["sourceHeads"]
    assert s["tasks"][0]["threads"] == ["1.0"]


def test_the_default_task_prompt_says_how_to_group_talk_split_and_merge(home):
    from jui_cli.viz import i18n
    for lang in ("ja", "en"):
        words = i18n.bundled(lang)["srv.slack.task_prompt"]
        for must in ("threadTs", "relatedTaskId", "talking", "promptEditedByUser", "sources", "threads"):
            assert must in words, (lang, must)
        assert "{next}" in i18n.bundled(lang)["srv.slack.notify"] and "{tasks}" in i18n.bundled(lang)["srv.slack.notify"]


@pytest.mark.parametrize("how", ["0644", "symlink"])
def test_a_config_stage_1_would_refuse_is_neither_read_nor_written(home, factory, how):
    """Stage 1 refuses slack.json readable by others or a symlink (slack/config.load): so does the room."""
    path = slack_room.config_path()
    if how == "0644":
        path.chmod(0o644)
    else:
        real = home / "real-slack.json"
        real.write_text(path.read_text())
        real.chmod(0o600)
        path.unlink()
        path.symlink_to(real)
    before = path.read_text()
    room = room_for(FakeWorld())
    assert room.slice()["config"]["state"] not in ("ok", "missing")
    with pytest.raises(slack_room.Refused):
        slack_room.save_prompts(slack_room.clean_prompts({"instructions": "", "chitchat": "", "taskPrompt": "x", "projects": {}}))
    assert path.read_text() == before


# ---- the trial's fixes (11-02): a task's messages whole, the start command for a viz in another folder ----------------

def test_a_tasks_messages_come_whole_in_thread_order_and_only_from_projects(home, factory):
    reply = message(factory, "shop", "3-w-C1.json", text="the reply\nline two", ts="20.5", threadTs="10.0",
                    permalink="https://acme.slack.com/archives/C1/p205")
    parent = message(factory, "shop", "1-w-C1.json", text="x" * 30_000, ts="10.0", permalink="javascript:alert(1)")
    other = message(factory, "shop", "2-w-C1.json", text="another thread", ts="15.0")
    (home / "secret.json").write_text(json.dumps({"text": "outside"}))
    task(factory, "T-0001", sources=[reply, other, parent, "../secret.json", "projects/shop/gone.json"])
    got = room_for(FakeWorld()).messages("T-0001")
    assert [m["path"] for m in got["messages"]] == [parent, reply, other]       # thread 10.0 (parent, reply), then 15.0
    assert got["messages"][1]["text"] == "the reply\nline two" and got["messages"][1]["permalink"].startswith("https://")
    assert got["messages"][0]["permalink"] == "" and len(got["messages"][0]["text"]) == slack_room.MESSAGE_MAX
    assert got["missing"] == ["../secret.json", "projects/shop/gone.json"]
    with pytest.raises(slack_room.Refused):
        room_for(FakeWorld()).messages("../x")


def test_the_start_command_names_this_vizs_folder_when_it_is_not_the_default(home, monkeypatch):
    assert slack_room.home_prefix() == "" and slack_room.with_home("claude --channels x") == "claude --channels x"
    monkeypatch.setenv("JUI_VIZ_HOME", str(home / "other viz"))
    want = "JUI_VIZ_HOME=~/'other viz' "                                                     # from ~, not the home's path
    assert slack_room.home_prefix() == want
    assert slack_room.with_home("claude --channels x") == want + "claude --channels x"
    assert slack_room.with_home("cd ~/work/docs && claude --channels x") == f"cd ~/work/docs && {want}claude --channels x"
    assert slack_room.with_home(f"cd a && {want}claude x") == f"cd a && {want}claude x"            # once
    room = room_for(FakeWorld())
    s = room.slice()
    assert s["robotLaunch"] == f"cd {slack_room._sh(str(room.root).replace(str(home), '~', 1))} && {want}{slack_room.LAUNCH_COMMAND}"
    assert s["launch"] == want + slack_room.LAUNCH_COMMAND
    monkeypatch.setenv("JUI_VIZ_HOME", "/srv/viz")                                              # outside the home: as it is
    assert slack_room.home_prefix() == "JUI_VIZ_HOME=/srv/viz "


def test_the_slice_never_carries_the_homes_path(home, factory, monkeypatch):
    """The talk e2e reads /api/snapshot for the home's path: the factory's folder, the targets' cwd, the start commands
    (the robot's own, written from the full path, too) and the config's refusal are all written from ~."""
    cfg = json.loads(slack_room.config_path().read_text())
    monkeypatch.setenv("JUI_VIZ_HOME", str(home / "other viz"))
    slack_config.save(cfg)
    world = FakeWorld()
    world.add("d1" * 18, str(home / "work" / "shop"))
    task(factory, "T-0001", launchCommand=f"cd {home}/work/docs && claude --channels x")
    room = room_for(world)
    room.cfg_why = f"{home}/.local/state/jui-viz/slack.json is readable by others"
    text = json.dumps(room.slice(), ensure_ascii=False)
    assert str(home) not in text
    assert "dirFull" not in text and "~/work/shop" in text and "cd ~/work/docs && JUI_VIZ_HOME=~/'other viz' claude" in text



# ---- the status select, and done tasks removed (11-02) --------------------------------------------------------------

def test_a_status_chosen_by_hand_sends_nothing_and_is_not_followed(home, factory):
    world = FakeWorld()
    world.add("dev", "~/shop")
    task(factory, "T-0001", status="draft", target={"sessionName": "dev", "sessionId": "dev"})
    room = room_for(world)
    run(room.act({"id": "T-0001", "op": "status", "status": "working"}, 5))
    t = json.loads((factory / "tasks" / "T-0001.json").read_text())
    assert t["status"] == "working" and t["startedAt"] == 5 and world.sent == []
    world.sessions["dev"]["status"] = "busy"
    room.load()
    room.follow(6)
    world.sessions["dev"]["status"] = "idle"
    room.load()
    assert room.follow(7) is False and json.loads((factory / "tasks" / "T-0001.json").read_text())["status"] == "working"
    for want in ("talking", "ready", "ended", "done", "draft"):
        run(room.act({"id": "T-0001", "op": "status", "status": want}, 8))
        assert json.loads((factory / "tasks" / "T-0001.json").read_text())["status"] == want
    assert "doneAt" not in json.loads((factory / "tasks" / "T-0001.json").read_text())   # out of done: no time to go by
    with pytest.raises(slack_room.Refused):
        run(room.act({"id": "T-0001", "op": "status", "status": "gone"}, 9))


def test_a_done_task_goes_with_its_messages_after_the_retention_but_a_shared_one_stays(home, factory):
    cfg = json.loads(slack_room.config_path().read_text())
    slack_config.save({**cfg, "doneRetentionMinutes": 10})
    own = message(factory, "shop", "1-w-C1.json")
    shared = message(factory, "shop", "2-w-C1.json")
    task(factory, "T-0001", status="draft", sources=[own, shared])
    task(factory, "T-0002", status="draft", sources=[shared], relatedTaskId="T-0001")
    world = FakeWorld()
    room = room_for(world)
    run(room.act({"id": "T-0001", "op": "status", "status": "done"}, 1_000))
    room.load()
    assert room.slice()["tasks"][0]["purgeAt"] == 1_000 + 10 * 60_000
    assert room.purge(1_000 + 10 * 60_000 - 1) == []
    assert room.purge(1_000 + 10 * 60_000) == ["T-0001"]
    assert not (factory / "tasks" / "T-0001.json").exists() and not (factory / own).exists()
    assert (factory / shared).exists()                                       # T-0002 still names it
    assert json.loads((factory / "tasks" / "T-0002.json").read_text())["relatedTaskId"] is None


def test_a_task_moved_out_of_done_in_time_is_kept_and_done_again_starts_its_time_again(home, factory):
    own = message(factory, "shop", "1-w-C1.json")
    task(factory, "T-0001", status="draft", sources=[own])
    room = room_for(FakeWorld())
    hour = slack_room.DONE_RETENTION_MIN * 60_000
    run(room.act({"id": "T-0001", "op": "status", "status": "done"}, 0))
    run(room.act({"id": "T-0001", "op": "status", "status": "ended"}, hour - 5))
    room.load()
    assert room.purge(hour + 1) == [] and (factory / "tasks" / "T-0001.json").exists()
    run(room.act({"id": "T-0001", "op": "status", "status": "done"}, hour + 2))
    room.load()
    assert room.purge(2 * hour) == [] and room.purge(2 * hour + 2) == ["T-0001"] and not (factory / own).exists()
