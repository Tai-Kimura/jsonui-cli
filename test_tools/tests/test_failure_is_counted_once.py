"""Every line that reports a failure reports the same failure.

Three separate lines have to agree about whether a run failed, and each of
them learned about the mock gate separately:

| line                    | before                                      |
|-------------------------|---------------------------------------------|
| `Drift detected: …`     | counted 4 buckets; `has_drift` read 6       |
| `Result: PASSED/FAILED` | patched to read the mock gate after a bug   |
| `Errors: N`             | the next line down, never patched           |

Measured on a consumer: a run gated by `absent_generated` printed

    Drift detected: 0 missing, 0 orphaned, 0 drifted, 0 stale body(ies)
    exit 1

and, on the other command, `Result: FAILED` directly above `Errors: 0`.

The second shape is the dangerous one. A wholly broken report is noticed; a
report where the headline is right and the number under it is zero lets the
reader explain the contradiction away — "FAILED but zero errors, must be
some other category" — and the consumer who found this had those lines on
screen during a release acceptance and read past them.

So these tests do not assert the counts of the buckets that exist today.
They assert the lines agree with each other, and that the set of gating
buckets is derived from one declaration — the two properties that survive
the next category being added.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import fields
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import GATING_BUCKETS, CheckReport

ROOT = Path(__file__).parent.parent

#: Buckets a reader is shown but which never fail the check. Listed so that
#: adding a field to `CheckReport` has to be classified as one or the other
#: — the failure mode here is a category arriving with no home.
NON_GATING_FIELDS = {
    "bodies",            # split into `errors` (gating) and `stale_generated`
    "unmatched",         # denominator; its gating subset is a separate field
    "misnamed",
    "warnings",
    "out_of_scope",
    "no_schema",
    "non_json",
    "malformed",
    "absent_handwritten",
}


def _blank_report(**kwargs) -> CheckReport:
    base = dict(missing=[], orphaned=[], drifted=[], bodies=[], unmatched=[])
    base.update(kwargs)
    return CheckReport(**base)


class TestTheGatingSetIsDeclaredOnce:
    def test_every_bucket_is_classified(self):
        """Both directions. A new list on `CheckReport` is either gating or
        explicitly not; it cannot be neither, which is how the two added on
        2026-09-01 reached a release with no counter."""
        listish = {f.name for f in fields(CheckReport)
                   if "list" in str(f.type)}
        declared = {name for name, _ in GATING_BUCKETS if name != "errors"}
        assert listish == declared | NON_GATING_FIELDS

    def test_errors_is_gating_and_is_not_a_field(self):
        """`errors` is the gating half of `bodies`, so it is named in
        GATING_BUCKETS as a property rather than a field."""
        assert "errors" in dict(GATING_BUCKETS)
        assert "errors" not in {f.name for f in fields(CheckReport)}

    @pytest.mark.parametrize("bucket", [name for name, _ in GATING_BUCKETS])
    def test_each_bucket_alone_fails_the_check_and_is_counted(self, bucket):
        """The red check the design asks for, run once per category: a
        bucket that gates has to appear in the line that explains the gate.
        A hand-written summary passes this only by coincidence."""
        if bucket == "errors":
            from jsonui_test_cli.mock.generate import BodyDrift
            report = _blank_report(bodies=[BodyDrift(
                rel="a.mock.json", scenario="default",
                missing=[".id"], extra=[])])
        else:
            report = _blank_report(**{bucket: ["a.mock.json  x: finding"]})

        assert report.has_drift, f"{bucket} does not fail the check"
        label = dict(GATING_BUCKETS)[bucket]
        assert f"1 {label}" in report.drift_summary
        # And the total the caller reports as `Errors:` counts it.
        assert sum(count for _, count in report.gating) == 1

    def test_an_empty_report_is_green_and_says_so_with_zeroes(self):
        report = _blank_report()
        assert not report.has_drift
        assert re.fullmatch(r"Drift detected: (0 [^,]+)(, 0 [^,]+)*",
                            report.drift_summary)


class TestTheThreeLinesAgree:
    """End-to-end, because the disagreement was between printed lines.

    Reading the properties cannot catch it: `has_drift` was always right.
    """

    def _project(self, tmp_path, extra_scenario=None):
        spec = {"openapi": "3.0.3", "paths": {"/api/items": {"get": {
            "operationId": "listItems",
            "responses": {
                "200": {"content": {"application/json": {"schema": {
                    "type": "object", "required": ["id"],
                    "properties": {"id": {"type": "string"}}}}}},
                "404": {"content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {"error": {"type": "string"}}}}}},
            }}}}}
        (tmp_path / "api.json").write_text(json.dumps(spec), encoding="utf-8")
        (tmp_path / "jui.config.json").write_text(json.dumps({
            "mock": {"swagger": ["api.json"], "mockDir": "tests/mocks"},
            "test": {"testDir": "tests/screens"},
        }), encoding="utf-8")
        (tmp_path / "tests/screens").mkdir(parents=True)
        (tmp_path / "tests/screens/home.test.json").write_text(json.dumps({
            "type": "screen",
            "source": {"layout": "home.json"},
            "metadata": {"name": "home", "description": "d"},
            "cases": [{"name": "c", "description": "d",
                       "steps": [{"action": "wait", "ms": 10}]}],
        }), encoding="utf-8")
        self._run(tmp_path, "mock", "generate")
        return tmp_path

    def _run(self, cwd, *args):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", *args],
            cwd=cwd, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT)})
        return proc.returncode, proc.stdout + proc.stderr

    def _delete_a_declared_scenario(self, project):
        """The consumer's probe: the state that gates through a bucket the
        summary line did not know about."""
        gen = next((project / "tests/mocks/generated").rglob("*.mock.json"))
        doc = json.loads(gen.read_text(encoding="utf-8"))
        victim = next(k for k in doc["scenarios"] if k != "default")
        del doc["scenarios"][victim]
        gen.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return victim

    def test_check_prints_a_non_zero_count_when_it_exits_non_zero(self, tmp_path):
        project = self._project(tmp_path)
        self._delete_a_declared_scenario(project)

        rc, out = self._run(project, "mock", "generate", "--check")

        assert rc == 1
        line = next(ln for ln in out.splitlines()
                    if ln.startswith("Drift detected:"))
        counts = [int(n) for n in re.findall(r"\b(\d+) ", line)]
        assert any(counts), f"exit {rc} but every count is zero: {line}"

    def test_validate_prints_a_non_zero_error_count_when_it_says_failed(self, tmp_path):
        """The consumer's predicate, and a better one than 'the new category
        appears': it stays true however the categories are counted."""
        project = self._project(tmp_path)
        self._delete_a_declared_scenario(project)

        rc, out = self._run(project, "validate", "tests/screens")

        assert rc == 1
        assert "Result: FAILED" in out
        errors = int(re.search(r"Errors: (\d+)", out).group(1))
        assert errors > 0, f"Result: FAILED directly above Errors: {errors}"

    def test_validate_shows_the_finding_it_failed_on(self, tmp_path):
        """The gate printed "Mock contract drift:" and then nothing at all,
        because its printer knew four categories and the gate read six."""
        project = self._project(tmp_path)
        victim = self._delete_a_declared_scenario(project)

        _, out = self._run(project, "validate", "tests/screens")

        body = out.split("Mock contract drift:")[1]
        assert victim in body

    def test_a_clean_run_still_passes_with_zero(self, tmp_path):
        """The control. Without it, every assertion above could hold because
        the gate had started failing on everything."""
        project = self._project(tmp_path)

        rc, out = self._run(project, "validate", "tests/screens")

        assert rc == 0
        assert "Result: PASSED" in out
        assert "Errors: 0" in out
