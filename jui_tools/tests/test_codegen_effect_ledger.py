"""The codegen-differential ledger, and the gate that reads it.

Plan 41 measured 280 defects and left the judgements report-only, because a
gate that is red on arrival teaches people to ignore it. The queue has since
been consumed, so the judgements go on the gate — and the ledger has to work
in BOTH directions or it rots the way every freeze list before it did:

  * a defect nobody recorded fails, so new ones cannot arrive quietly
  * an entry the measurement no longer supports fails, so fixing a defect
    forces its row out instead of leaving an alibi behind
  * an entry with no owner or reason fails, because an accepted defect
    nobody owns is a permanent one (plan 50 measured that the attribution
    column is the only thing that stops a freeze from outliving its reason)

These run on the pure functions: the probes need ruby and the three tool
trees, which the pin does not, and the point here is the judgement, not the
measurement.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import codegen_effect as ce


def _finding(component="Label", attribute="text", platform="web", check="C0",
             finding_class="unread-spelling") -> ce.Finding:
    return ce.Finding(
        component=component,
        attribute=attribute,
        platform=platform,
        check=check,
        host="Label",
        detail="nothing reads the spelling",
        finding_class=finding_class,
    )


def _result(*findings, errors=()) -> ce.EffectResult:
    return ce.EffectResult(findings=list(findings), errors=list(errors))


def _entry(finding, owner="A", reason="converter fix queued") -> dict:
    return {
        "component": finding.component,
        "attribute": finding.attribute,
        "platform": finding.platform,
        "check": finding.check,
        "class": finding.finding_class,
        "owner": owner,
        "reason": reason,
        "note": "",
    }


class LedgerVerdictTest(unittest.TestCase):
    def test_unrecorded_defect_fails(self):
        f = _finding()
        verdict = ce.check_ledger(_result(f), {}, platforms=("web",))
        self.assertFalse(verdict.ok)
        self.assertEqual(len(verdict.unrecorded), 1)
        self.assertIn("Label.text", verdict.unrecorded[0])

    def test_recorded_defect_passes(self):
        f = _finding()
        ledger = {ce.entry_key(f): _entry(f)}
        verdict = ce.check_ledger(_result(f), ledger, platforms=("web",))
        self.assertTrue(verdict.ok, verdict)
        self.assertEqual(verdict.accepted, 1)

    def test_entry_the_measurement_no_longer_supports_fails(self):
        """The direction that keeps the ledger honest as defects get fixed."""
        f = _finding()
        ledger = {ce.entry_key(f): _entry(f)}
        verdict = ce.check_ledger(_result(), ledger, platforms=("web",))
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.stale, ["Label.text [web/rjui_tools] C0"])

    def test_entry_without_owner_or_reason_fails(self):
        f = _finding()
        for field in ("owner", "reason"):
            entry = _entry(f)
            entry[field] = ""
            verdict = ce.check_ledger(_result(f), {ce.entry_key(f): entry},
                                      platforms=("web",))
            self.assertFalse(verdict.ok, field)
            self.assertEqual(len(verdict.incomplete), 1)
            self.assertIn(field, verdict.incomplete[0])
            self.assertEqual(verdict.accepted, 0)

    def test_unmeasured_platform_is_neither_stale_nor_accepted(self):
        """An ios run says nothing about android's rows, either way."""
        f = _finding(platform="android")
        ledger = {ce.entry_key(f): _entry(f)}
        verdict = ce.check_ledger(_result(), ledger, platforms=("web",))
        self.assertTrue(verdict.ok, verdict)
        self.assertEqual(verdict.stale, [])

    def test_probe_error_fails_and_no_entry_can_cover_it(self):
        """A converter that raised emitted nothing, so nothing was judged."""
        f = _finding()
        ledger = {ce.entry_key(f): _entry(f)}
        verdict = ce.check_ledger(_result(errors=(f,)), ledger, platforms=("web",))
        self.assertFalse(verdict.ok)
        self.assertEqual(len(verdict.errors), 1)

    def test_advisories_are_never_ledgered(self):
        """value-is-default says the FIXTURE discriminates nothing.

        It is re-derived from C2 every run, so a stored entry would go stale
        the moment a representative value changed.
        """
        advisory = _finding(finding_class="value-is-default")
        result = _result(advisory)
        self.assertEqual(result.defects, [])
        verdict = ce.check_ledger(result, {}, platforms=("web",))
        self.assertTrue(verdict.ok, verdict)
        self.assertEqual(ce.update_ledger({}, result, platforms=("web",)), {})


class LedgerRoundTripTest(unittest.TestCase):
    def test_update_preserves_owner_and_reason(self):
        f = _finding()
        existing = {ce.entry_key(f): _entry(f, owner="B", reason="known, plan 52")}
        merged = ce.update_ledger(existing, _result(f), platforms=("web",))
        self.assertEqual(merged[ce.entry_key(f)]["owner"], "B")
        self.assertEqual(merged[ce.entry_key(f)]["reason"], "known, plan 52")

    def test_update_leaves_other_platforms_alone(self):
        web = _finding(platform="web")
        android = _finding(platform="android")
        existing = {ce.entry_key(android): _entry(android)}
        merged = ce.update_ledger(existing, _result(web), platforms=("web",))
        self.assertIn(ce.entry_key(android), merged)
        self.assertIn(ce.entry_key(web), merged)

    def test_new_entries_are_marked_unreviewed(self):
        f = _finding()
        merged = ce.update_ledger({}, _result(f), platforms=("web",))
        self.assertEqual(merged[ce.entry_key(f)]["reason"], ce.UNREVIEWED)

    def test_render_load_round_trip_is_stable(self):
        f = _finding()
        merged = ce.update_ledger({}, _result(f), platforms=("web",))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ce.LEDGER_NAME
            path.write_text(ce.render_ledger(merged), encoding="utf-8")
            self.assertEqual(ce.load_ledger(path), merged)
            # Deterministic: same input, byte-identical output.
            self.assertEqual(
                ce.render_ledger(ce.load_ledger(path)), path.read_text(encoding="utf-8")
            )

    def test_class_change_keeps_the_recorded_reason(self):
        """bound-dropped becoming bound-frozen is the same attribute, still broken.

        Keying on the class would drop the reason on the floor and read as a
        brand-new defect, which is how a ledger loses its history.
        """
        dropped = _finding(finding_class="bound-dropped", check="C1")
        frozen = _finding(finding_class="bound-frozen", check="C1")
        existing = {ce.entry_key(dropped): _entry(dropped, owner="C", reason="tracked")}
        merged = ce.update_ledger(existing, _result(frozen), platforms=("web",))
        self.assertEqual(len(merged), 1)
        entry = merged[ce.entry_key(frozen)]
        self.assertEqual(entry["owner"], "C")
        self.assertEqual(entry["class"], "bound-frozen")


class CommittedLedgerTest(unittest.TestCase):
    """The ledger in the repo has to satisfy its own rules."""

    LEDGER = Path(__file__).resolve().parents[2] / "conformance" / ce.LEDGER_NAME

    @unittest.skipUnless(LEDGER.is_file(), "no committed ledger yet")
    def test_every_entry_has_an_owner_and_a_reason(self):
        for entry in json.loads(self.LEDGER.read_text(encoding="utf-8"))["entries"]:
            for field in ce.REQUIRED_FIELDS:
                self.assertTrue(
                    entry.get(field),
                    f"{entry.get('component')}.{entry.get('attribute')} "
                    f"[{entry.get('platform')}] has no {field}",
                )

    @unittest.skipUnless(LEDGER.is_file(), "no committed ledger yet")
    def test_no_advisory_class_is_recorded(self):
        for entry in json.loads(self.LEDGER.read_text(encoding="utf-8"))["entries"]:
            self.assertNotIn(entry.get("class"), ce.ADVISORY_CLASSES)


if __name__ == "__main__":
    unittest.main()
