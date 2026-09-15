"""The CI chapter's job list, budgets and gate flags are derived, not recalled.

2026-09-15: chapter 08 said the conformance report job runs
`jui conformance gate --env ci --parity`. It actually runs that plus
`--cross-effect --inert-complete --value-discrimination`. A reader — this
one — concluded from the chapter that `--inert-complete` was not in CI at
all, and therefore that a green CI said nothing about the inert ledger.

The truth was worse in a way the chapter could not have corrected: the flag
IS passed, and under `--env ci` those three checks are DOWNGRADED TO NOTICES
because activeness and inert verdicts are asserted local-env. So CI is green
while 33 ledger entries are stale and 12 inert verdicts are unaccounted, and
the only lane that would say so is a developer running `--env local` after
rendering all three platforms locally.

Three more drifts were sitting in the same chapter, measured the same hour:
ios pinned Xcode 26.3 (chapter said 16.4), the android job budget is 270
minutes (chapter said 150), and the ci.yml table listed 4 of the 9 jobs.

Prose carrying a number has no gate — the grammar checks and the test suite
both pass over it — so it stays wrong until someone acts on it. This test is
that gate. It derives the population from the workflow files; it never
carries its own copy of a job name, a budget or a flag.

⚠️ Scope, stated so the green is not read as more than it is:

* Job names are matched as SUBSTRINGS. `publication-hygiene` is distinctive
  and this test really does force it into the chapter; `ios`, `web`,
  `android` and `report` are common words that the chapter contains for
  unrelated reasons, so for those four the name check passes whatever the
  chapter says. The budget check is what carries force there.
* A budget is only compared when the chapter states one on a line naming the
  job. A job the chapter never gives a number to is not caught.
* It cannot check that the surrounding sentence is true — only that the
  numbers and flags embedded in it match the workflow.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CHAPTER = REPO_ROOT / "dev-guide" / "08-testing-conformance.md"

#: The two workflows the chapter's CI section describes.
DESCRIBED = ("ci.yml", "conformance-mobile.yml")

#: Keys that are workflow plumbing rather than a described job.
NOT_A_JOB = {"push", "schedule", "workflow_dispatch", "pull_request"}


def _jobs(path: Path) -> dict[str, dict]:
    """``{job_name: job_body}`` from a workflow, via a real YAML parse.

    Regex over YAML was the first thing tried and it invented a `schedule`
    job out of the `on:` block — the same hand-rolled-population mistake this
    test exists to stop.
    """
    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = doc.get("jobs") or {}
    return {k: v for k, v in jobs.items() if k not in NOT_A_JOB}


def _gate_flags(body: str) -> set[str]:
    """Every ``--flag`` the report job hands `jui conformance gate`."""
    return set(re.findall(r"'(--[a-z-]+)'", body))


class CiChapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert CHAPTER.is_file(), f"no chapter at {CHAPTER}"
        cls.text = CHAPTER.read_text(encoding="utf-8")
        cls.jobs = {}
        for name in DESCRIBED:
            path = WORKFLOWS / name
            assert path.is_file(), f"no workflow at {path}"
            cls.jobs[name] = _jobs(path)

    # -- controls ---------------------------------------------------------

    def test_the_parse_found_jobs_in_both_workflows(self):
        # Positive control. An empty parse makes every assertion below vacuous
        # — "no job is missing" is trivially true of no jobs.
        for name in DESCRIBED:
            self.assertGreaterEqual(
                len(self.jobs[name]), 3,
                f"{name}: parsed {len(self.jobs[name])} jobs — the parse is "
                "broken, and a broken parse passes every check in this file",
            )

    def test_the_chapter_is_searchable(self):
        # Positive control on the other side: an empty or mis-encoded read
        # makes every job look undocumented.
        self.assertIn("conformance-mobile.yml", self.text)

    def test_a_job_that_is_not_there_is_reported_missing(self):
        # Boundary: the same predicate, on a name the chapter cannot contain.
        # Without this, a check that accepts everything looks identical to a
        # check that is satisfied.
        self.assertNotIn("zzz-nonexistent-job", self.text)

    # -- the contract -----------------------------------------------------

    def test_every_job_is_named_in_the_chapter(self):
        missing = sorted(
            f"{wf}:{job}"
            for wf, jobs in self.jobs.items()
            for job in jobs
            if job not in self.text
        )
        self.assertEqual(
            [], missing,
            "these CI jobs run but the chapter never names them, so a reader "
            "sizing or trusting CI works from a short list: "
            f"{missing}. Add each to the chapter's CI section.",
        )

    def test_every_stated_budget_matches_the_workflow(self):
        wrong = []
        for wf, jobs in self.jobs.items():
            for job, body in jobs.items():
                budget = (body or {}).get("timeout-minutes")
                if budget is None:
                    continue
                # The lines where the chapter talks about this job.
                lines = [ln for ln in self.text.splitlines() if job in ln]
                stated = {
                    int(m) for ln in lines for m in re.findall(r"(\d+)m\b", ln)
                }
                if stated and budget not in stated:
                    wrong.append(
                        f"{wf}:{job} workflow={budget}m chapter={sorted(stated)}"
                    )
        self.assertEqual(
            [], wrong,
            "the chapter states a budget the workflow does not carry — the "
            "number a person would use to size a fixture expansion: "
            f"{wrong}",
        )

    def test_every_gate_flag_the_report_job_passes_is_in_the_chapter(self):
        report = self.jobs["conformance-mobile.yml"].get("report")
        self.assertIsNotNone(report, "conformance-mobile.yml has no report job")
        body = "\n".join(
            str(step.get("run", "")) for step in (report.get("steps") or [])
        )
        flags = _gate_flags(body)
        self.assertIn(
            "--inert-complete", flags,
            "control: the report job is expected to pass --inert-complete; if "
            "it no longer does, this test is checking the wrong command",
        )
        missing = sorted(f for f in flags if f not in self.text)
        self.assertEqual(
            [], missing,
            "the report job passes these gate flags and the chapter does not "
            f"mention them: {missing}. A flag missing from the chapter reads "
            "as a check CI does not run — which is how a green CI got taken "
            "as evidence about the inert ledger.",
        )


if __name__ == "__main__":
    unittest.main()
