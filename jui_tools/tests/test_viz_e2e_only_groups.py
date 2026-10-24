"""An --only that is a group says what it runs and stops without --group-ok (tools/viz_e2e/only_groups.py, 10-21:
--only live, meant as one suite, ran 49 minutes of nearly every suite and held the machine's line)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"
sys.path.insert(0, str(E2E))
import only_groups as G  # noqa: E402

RUN = (E2E / "run.py").read_text(encoding="utf-8")


def _choices() -> list[str]:
    m = re.search(r'"--only", action="append", choices=\[([^\]]*)\]', RUN)
    return re.findall(r'"([a-z0-9-]+)"', m.group(1))


def test_a_group_alone_is_said_and_stops():
    lines, stop = G.check(["live"], group_ok=False)
    live = G.suites_of("live")
    assert stop and len(live) > 40 and "gitbox" in live and "server-room" in live
    assert lines[0] == f"--only live = {len(live)} suites: {', '.join(live)}"
    assert lines[-1].startswith("stopped: a group runs most of the e2e") and "--group-ok" in lines[-1]
    lines, stop = G.check(["gitbox", "demo"], group_ok=False)   # one group among names is enough to stop
    demo = G.suites_of("demo")   # counted, not written: a suite added to the group keeps this true
    assert stop and len(demo) >= 2 and demo[0] == "demo" and lines[0] == f"--only demo = {len(demo)} suites: {', '.join(demo)}"


def test_a_group_with_group_ok_is_said_and_runs():
    lines, stop = G.check(["live"], group_ok=True)
    assert not stop and lines == [f"--only live = {len(G.suites_of('live'))} suites: {', '.join(G.suites_of('live'))}"]


def test_one_suites_name_runs_as_before_saying_nothing():
    """Every --only choice but the three groups names one suite: nothing said, nothing stopped."""
    singles = [c for c in _choices() if c not in ("live", "demo", "en-reps")]
    assert len(singles) > 40 and G.check(singles, group_ok=False) == ([], False)
    assert all(G.suites_of(c) == [c] for c in singles), [c for c in singles if G.suites_of(c) != [c]]
    assert G.check(None, group_ok=False) == ([], False)   # no --only: the whole run before a distribution


def test_run_py_checks_the_group_before_it_takes_a_ticket():
    assert RUN.index("only_groups.check(a.only, a.group_ok)") < RUN.index("e2e_lock.hold(") < RUN.index("asyncio.run(go())")
    assert '"--group-ok"' in RUN and re.search(r"if stop:\n\s+return 2", RUN)


EN_REPS = ["demo", "live", "ask", "notify", "history", "usage", "server-room", "data-server", "cost-bill", "talk-ui",
           "lang-checks", "denied", "devices"]


def test_en_reps_is_the_english_representatives_and_nothing_else():
    """The gate's English step (ticket 2026-10-21-viz-english-screen-checks §5: one suite per family of the page, run
    in English; lang-checks reads the page in the run's language): --only en-reps runs those blocks, each once, and
    is a group (said, and stopped without --group-ok)."""
    assert G.suites_of("en-reps") == EN_REPS
    lines, stop = G.check(["en-reps"], group_ok=False)
    assert stop and lines[0] == f"--only en-reps = {len(EN_REPS)} suites: {', '.join(EN_REPS)}"
    assert "en-reps" in _choices()


def test_lang_says_the_runs_language_before_the_japanese_default():
    """--lang en sets JUI_VIZ_LANGUAGE outright; without it the run keeps the Japanese its checks were written on."""
    assert '"--lang"' in RUN
    assert RUN.index('os.environ["JUI_VIZ_LANGUAGE"] = a.lang') < RUN.index('os.environ.setdefault("JUI_VIZ_LANGUAGE", "ja")')
    assert 'print(f"language: {os.environ[\'JUI_VIZ_LANGUAGE\']}"' in RUN
