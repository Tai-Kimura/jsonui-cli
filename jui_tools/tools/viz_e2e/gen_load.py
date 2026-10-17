"""A load recording for `jui viz serve --replay` (plan 10 §7): 20 sessions in 6 folders, each with two subagents
(60 robots), and tool calls at 50 events a second (PreToolUse / PostToolUse pairs) for --seconds.

    python tools/viz_e2e/gen_load.py --out /tmp/viz-load.jsonl [--seconds 120] [--rate 50]

Measure (plan 10 §7): play it with `jui viz serve --replay FILE`, open the page with ?fps=1 in an ordinary Chrome
and watch the corner for a minute; sample `ps -o %cpu= -p <serve pid>` once a second.
Tasks and specs (P4) are not in it.
"""

from __future__ import annotations

import argparse
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import hooks  # noqa: E402

FOLDERS = ["shop-app", "jsonui-cli", "JsonUIDocument", "admin-web", "client-ios", "tools"]
ROLES = ["jsonui-define", "jsonui-implement", "jsonui-test", "jsonui-navigation-ios", "jsonui-debug", "Explore"]
TOOLS = [("Read", lambda r: {"file_path": f"{r}/docs/screens/json/s{random.randrange(300)}.spec.json"}),
         ("Edit", lambda r: {"file_path": f"{r}/docs/screens/layouts/s{random.randrange(300)}.json", "old_string": "a", "new_string": "b"}),
         ("Bash", lambda r: {"command": random.choice(["jui build", "jui verify", "npm test", "xcodebuild test -scheme App"]), "description": "run"}),
         ("Grep", lambda r: {"pattern": "onTextChange", "path": r})]


def generate(seconds: int, rate: int, seed: int = 7):
    random.seed(seed)
    items, n = [], 0
    sessions = []
    for i in range(20):
        sid = f"{i:02x}{random.getrandbits(32):08x}-0000-4000-8000-{i:012x}"
        root = f"/work/{FOLDERS[i % len(FOLDERS)]}"
        subs = [(f"{sid[:2]}s{k}{random.getrandbits(40):010x}", random.choice(ROLES)) for k in range(2)]
        sessions.append((sid, root, subs))
        items.append((i * 0.05, hooks.base(sid, root, "SessionStart", source="startup")))
        for k, sub in enumerate(subs):
            items.append((1 + i * 0.05 + k * 0.01, hooks.base(sid, root, "SubagentStart", agent_id=sub[0], agent_type=sub[1])))
    start = 2.0
    total = seconds * rate
    open_calls = []
    for j in range(total):
        t = start + j / rate
        if open_calls and (j % 2 or len(open_calls) > 40):
            sid, root, tool, ti, num, agent = open_calls.pop(0)
            items.append((t, hooks.post(sid, root, tool, ti, num, agent)))
            continue
        sid, root, subs = random.choice(sessions)
        agent = random.choice([None, *subs])
        tool, make = random.choice(TOOLS)
        n += 1
        ti = make(root)
        items.append((t, hooks.pre(sid, root, tool, ti, n, agent)))
        open_calls.append((sid, root, tool, ti, n, agent))
    return items


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--rate", type=int, default=50, help="events a second")
    a = ap.parse_args(argv)
    items = generate(a.seconds, a.rate)
    hooks.write(items, a.out)
    print(f"{a.out}: {len(items)} hook bodies, 20 sessions, 60 robots, {a.rate}/s for {a.seconds}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
