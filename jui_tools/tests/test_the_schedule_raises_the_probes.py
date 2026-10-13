"""The weekly scheduled conformance-mobile run raises every opt-in probe.

The schedule has no inputs, so `inputs.ios_probes` / `image_probes` /
`android_probes` are empty there. Until jsonui-cli 1.9.27 every switch read
`inputs.X && 'true' || 'false'`, so the one run nobody dispatches ran with all
of them off — the opt-in probes, most of the iOS probe classes among them,
never ran on the schedule, and the "every raised probe ran" check was skipped
with them. Each switch now reads `(inputs.X || github.event_name ==
'schedule')`.

These arms do not match the spelling: they take every `${{ … }}` expression
in the workflow that reads one of the three inputs and evaluate it for a
scheduled run, a default dispatch and a dispatch that lowered the input. A
switch that stays down on the schedule, or that the schedule raises past a
dispatch's `false`, is red whatever it looks like.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "conformance-mobile.yml"
PROBE_INPUTS = ("ios_probes", "image_probes", "android_probes")
EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)


def _strings(node, where=()):
    """Every string in the workflow with the path that leads to it."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, where + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, where + (str(i),))
    elif isinstance(node, str):
        yield where, node


def _python(expr: str) -> str:
    """A GitHub Actions expression of the shapes this workflow uses, as Python:
    && || ! == literals, inputs.*, github.event_name, cancelled() and always().
    Anything else is refused, so a new shape cannot be evaluated wrongly."""
    out = expr.strip()
    if re.search(r"[^\w\s.!=&|()'-]", out):
        raise ValueError(f"unsupported expression: {expr!r}")
    out = re.sub(r"\binputs\.(\w+)", r"inputs.get('\1')", out)
    out = out.replace("github.event_name", "event_name")
    out = out.replace("cancelled()", "False").replace("always()", "True")
    out = out.replace("&&", " and ").replace("||", " or ")
    out = re.sub(r"!(?!=)", " not ", out)
    # Bare literals, outside the quoted strings ('true' stays a string).
    parts = out.split("'")
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"\btrue\b", "True", parts[i])
        parts[i] = re.sub(r"\bfalse\b", "False", parts[i])
        parts[i] = re.sub(r"\bnull\b", "None", parts[i])
    return "'".join(parts)


def _eval(expr: str, event: str, inputs: dict) -> object:
    return eval(_python(expr), {"__builtins__": {}}, {"inputs": inputs, "event_name": event})


def _on(value: object) -> bool:
    """How the consumer reads it: an env value '1' / 'true', or a truthy if:."""
    if isinstance(value, str):
        return value in ("1", "true")
    return bool(value)


SCHEDULE = ("schedule", {})
DISPATCH_DEFAULT = ("workflow_dispatch", {name: True for name in PROBE_INPUTS})


def _dispatch_lowered(name: str):
    return "workflow_dispatch", {n: (n != name) for n in PROBE_INPUTS}


class TheScheduleRaisesTheProbes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        cls.sites = []
        for where, text in _strings(cls.wf.get("jobs", {}), ("jobs",)):
            for expr in EXPR.findall(text):
                read = [n for n in PROBE_INPUTS if f"inputs.{n}" in expr]
                if read:
                    cls.sites.append(("/".join(where), expr, read))

    def test_the_sites_are_where_the_probes_are_raised_and_checked(self):
        places = sorted((s[0].split("/")[1], s[2][0]) for s in self.sites)
        self.assertEqual(places, sorted(
            [(job, "image_probes") for job in ("ios", "ios-codegen") for _ in range(2)]
            + [(job, "ios_probes") for job in ("ios", "ios-codegen")]
            + [(job, "ios_probes") for job in ("ios-merge", "ios-codegen-merge")]
            + [("android-library-tests", "android_probes")]), self.sites)

    def test_a_scheduled_run_raises_every_switch_and_runs_every_check(self):
        for where, expr, _ in self.sites:
            self.assertTrue(_on(_eval(expr, *SCHEDULE)), f"{where}: off on the schedule — {expr.strip()}")

    def test_a_dispatch_is_what_it_was(self):
        for where, expr, read in self.sites:
            self.assertTrue(_on(_eval(expr, *DISPATCH_DEFAULT)), f"{where}: off on a default dispatch")
            for name in read:
                self.assertFalse(_on(_eval(expr, *_dispatch_lowered(name))),
                                 f"{where}: {name}=false on a dispatch does not lower it — {expr.strip()}")

    def test_the_raised_ios_switches_feed_the_export_and_the_check(self):
        # IOS_PROBES is what the suite step reads to export the switches; the
        # merge's check step is the gate that every raised probe ran.
        for job in ("ios", "ios-codegen"):
            steps = self.wf["jobs"][job]["steps"]
            suite = [s for s in steps if "IOS_PROBES" in (s.get("env") or {})]
            self.assertEqual(len(suite), 1, job)
            self.assertIn('if [ "$IOS_PROBES" = true ]', suite[0]["run"])
            self.assertIn("ios_probe_gates.py exports", suite[0]["run"])
        for job in ("ios-merge", "ios-codegen-merge"):
            check = [s for s in self.wf["jobs"][job]["steps"] if "ios_probe_gates.py check" in s.get("run", "")]
            self.assertEqual(len(check), 1, job)
            self.assertTrue(_on(_eval(EXPR.findall(check[0]["if"])[0], *SCHEDULE)), job)


class TheScheduleRunsTheShardsAndTheMerges(unittest.TestCase):
    """The shards, the merges that prove they are the whole run, and the
    report all start on the schedule (their `if:` reads inputs that are empty
    there) — so the merge's gate holds on the schedule as on a dispatch."""

    def test_every_ios_job_and_the_report_run_on_the_schedule(self):
        wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        for job in ("ios", "ios-codegen", "ios-merge", "ios-codegen-merge", "report"):
            cond = wf["jobs"][job].get("if", "true")
            expr = EXPR.findall(cond)[0] if "${{" in cond else cond
            self.assertTrue(_eval(expr, *SCHEDULE), f"{job} does not run on the schedule: {cond}")
            self.assertTrue(_eval(expr, *DISPATCH_DEFAULT), f"{job} does not run on a default dispatch: {cond}")
        merge_steps = wf["jobs"]["ios-merge"]["steps"]
        merge = [s for s in merge_steps if "ios_shards.py merge" in s.get("run", "")]
        self.assertEqual(len(merge), 1)
        self.assertNotIn("if", merge[0], "the merge itself must not be conditional")


class TheEvaluatorItself(unittest.TestCase):
    """The arms above are only as good as this translation."""

    def test_known_shapes(self):
        self.assertEqual(_eval("inputs.a && '1' || '0'", "workflow_dispatch", {"a": True}), "1")
        self.assertEqual(_eval("inputs.a && '1' || '0'", "schedule", {}), "0")
        self.assertEqual(_eval("(inputs.a || github.event_name == 'schedule') && 'true' || 'false'", "schedule", {}), "true")
        self.assertFalse(_eval("!cancelled() && inputs.a", "schedule", {}))
        self.assertTrue(_eval("!cancelled() && (inputs.a || github.event_name == 'schedule')", "schedule", {}))
        self.assertTrue(_eval("github.event_name != 'schedule'", "workflow_dispatch", {}))
        self.assertIs(_eval("inputs.a || true", "workflow_dispatch", {"a": False}), True)
        self.assertEqual(_eval("false && 'true' || 'false'", "schedule", {}), "false")

    def test_refuses_what_it_cannot_read(self):
        with self.assertRaises(ValueError):
            _python("contains(github.ref, 'x')")


if __name__ == "__main__":
    unittest.main()
