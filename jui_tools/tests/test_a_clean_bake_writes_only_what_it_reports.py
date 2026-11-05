"""A bake writes what it reported, and a bake that reported nothing does not write.

THE DEFECT THIS EXISTS FOR

`baseline update --fail-on-moved` passed with `moved 0` and still rewrote the
manifest through the wholesale path. Measured 2026-11-05 on v2.5.4 with run
42011943298's artifacts, with the README's ci recipe: ios took 13 insertions /
16 deletions (unstable hashes, ink of pictures that did not move, and
`rendered_by` blanked), web 1 insertion / 4 deletions with all 975 entries
`same`. A commit that means "these two entries" could not be told from the rest.

The readers of the artifact bytes are stubbed, per file: the python-suite runner
has no Pillow on purpose, and the distances are the quantity under test.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tests._shared_core import conformance_with_shared_core

from jui_cli.cli import main as cli_main
from jui_cli.conformance import baseline

HASHER = "pillow-12"
WIDTH = baseline.HASH_SIZE * baseline.HASH_SIZE // 4
INDICATOR = "Indicator_color__static.png"
STABLE = "Label_text__static.png"
OTHER = "View_background__static.png"


def _digest(seed: int) -> str:
    return f"{seed:0{WIDTH}x}"


class Bake(unittest.TestCase):
    """Committed: three entries, provenance, a stored threshold of 12."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = conformance_with_shared_core(self._tmp.name)
        (self.dir / "fixtures").mkdir()
        self.art = self.dir / "artifacts" / "ios"
        self.art.mkdir(parents=True)
        (self.dir / "baselines" / "ci").mkdir(parents=True)
        layout = "fixtures/indicator.layout.json"
        (self.dir / layout).write_text(
            json.dumps({"type": "View", "id": "root", "child": [{"type": "Indicator"}]}),
            encoding="utf-8",
        )
        (self.dir / "manifest.json").write_text(
            json.dumps({"fixtures": [{"id": "Indicator/color__static", "layout": layout}]}),
            encoding="utf-8",
        )
        self.path = self.dir / "baselines" / "ci" / "ios.hashes.json"
        self.committed = {
            "_generated": baseline.json_marker(
                source="conformance/artifacts/ios", generator=baseline.GENERATOR_NAME
            ),
            "platform": "ios",
            "environment": "ci",
            "algorithm": baseline.ALGORITHM,
            baseline.HASHER_FIELD: HASHER,
            "threshold": 12,
            "rendered_by": {"swiftjsonui.src": "abc"},
            "hashes": {INDICATOR: _digest(0b1111), OTHER: _digest(0xF0), STABLE: _digest(0xF00)},
            "hashes_by_os": {},
            "ink": {INDICATOR: 10, OTHER: 20, STABLE: 30},
            "ink_by_os": {},
            "vhashes": {INDICATOR: _digest(1), OTHER: _digest(2), STABLE: _digest(4)},
            "vhashes_by_os": {},
        }
        self._commit()
        # This run: the Indicator wobbles 1 bit under the threshold, and the
        # ink of a picture whose hashes did not move was re-measured.
        self.h = {INDICATOR: _digest(0b1110), OTHER: _digest(0xF0), STABLE: _digest(0xF00)}
        self.v = {INDICATOR: _digest(1), OTHER: _digest(2), STABLE: _digest(4)}
        self.i = {INDICATOR: 11, OTHER: 21, STABLE: 30}

    def _commit(self) -> None:
        self.path.write_text(
            json.dumps(self.committed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        self.before = self.path.read_bytes()

    def _patched(self):
        for name in set(self.h):
            (self.art / name).write_bytes(b"not a real png")
        for png in self.art.glob("*.png"):
            if png.name not in self.h:
                png.unlink()

        def _no_pillow():
            raise AssertionError("an artifact was opened through a reader these arms do not patch")

        return (
            mock.patch.object(baseline, "dhash_file", side_effect=lambda p, c=(0, 0): self.h[Path(p).name]),
            mock.patch.object(baseline, "vdhash_file", side_effect=lambda p, c=(0, 0): self.v[Path(p).name]),
            mock.patch.object(baseline, "ink_file", side_effect=lambda p, c=(0, 0): self.i[Path(p).name]),
            mock.patch.object(baseline, "hasher_identity", return_value=HASHER),
            mock.patch.object(baseline, "_load_pillow", _no_pillow),
        )

    def _bake(self, **kw):
        a, b, c, d, e = self._patched()
        with a, b, c, d, e:
            return baseline.update_baseline(self.dir, "ios", env="ci", **kw)

    def _cli(self, *extra: str) -> tuple[int, str]:
        a, b, c, d, e = self._patched()
        out = io.StringIO()
        with a, b, c, d, e, redirect_stdout(out):
            rc = cli_main([
                "conformance", "baseline", "update", "--platform", "ios", "--env", "ci",
                "--dir", str(self.dir), "--artifacts", str(self.art), *extra,
            ])
        return rc, out.getvalue()

    def _after(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))


class NothingMoved(Bake):
    def test_the_file_keeps_its_bytes(self) -> None:
        summary = self._bake(refuse_if_moved=True)
        self.assertEqual(summary.moved, ())
        self.assertEqual([n for n, _, _ in summary.tolerated], [INDICATOR], "the arm needs a wobble")
        self.assertTrue(summary.unchanged)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_the_file_is_not_even_opened_for_writing(self) -> None:
        """Bytes that come out equal could still have been rewritten by another format."""
        self.path.write_text(json.dumps(self.committed) + "\n", encoding="utf-8")
        compact = self.path.read_bytes()
        self._bake(refuse_if_moved=True)
        self.assertEqual(self.path.read_bytes(), compact)

    def test_the_same_run_without_the_flag_still_rewrites(self) -> None:
        """The boundary: an explicit wholesale bake is still the door for everything."""
        summary = self._bake()
        self.assertFalse(summary.unchanged)
        after = self._after()
        self.assertEqual(after["hashes"][INDICATOR], self.h[INDICATOR])
        self.assertEqual(after["ink"][OTHER], 21)
        self.assertEqual(after["rendered_by"], {})

    def test_a_named_library_is_recorded_and_nothing_else(self) -> None:
        self._bake(refuse_if_moved=True, rendered_by={"swiftjsonui.src": "def"})
        after = self._after()
        self.assertEqual(after["rendered_by"], {"swiftjsonui.src": "def"})
        for key in ("hashes", "vhashes", "ink", "threshold"):
            self.assertEqual(after[key], self.committed[key], key)

    def test_a_new_entry_goes_in_and_the_committed_ones_stay(self) -> None:
        name = "New_fixture__static.png"
        self.h[name], self.v[name], self.i[name] = _digest(7), _digest(8), 99
        summary = self._bake(refuse_if_moved=True)
        self.assertEqual(summary.new, (name,))
        after = self._after()
        self.assertEqual(after["hashes"][name], _digest(7))
        self.assertEqual(after["ink"][name], 99)
        self.assertEqual(after["threshold"], 12)
        self.assertEqual(after["rendered_by"], self.committed["rendered_by"])
        del after["hashes"][name], after["vhashes"][name], after["ink"][name]
        for key in ("hashes", "vhashes", "ink"):
            self.assertEqual(after[key], self.committed[key], key)

    def test_a_dropped_entry_goes_out_and_the_committed_ones_stay(self) -> None:
        del self.h[OTHER], self.v[OTHER], self.i[OTHER]
        summary = self._bake(refuse_if_moved=True)
        self.assertEqual(summary.dropped, (OTHER,))
        after = self._after()
        self.assertNotIn(OTHER, after["hashes"])
        self.assertNotIn(OTHER, after["vhashes"])
        self.assertNotIn(OTHER, after["ink"])
        self.assertEqual(after["hashes"][INDICATOR], self.committed["hashes"][INDICATOR])
        self.assertEqual(after["ink"][STABLE], 30)

    def test_a_missing_vertical_hash_is_filled_only_where_the_hash_matches(self) -> None:
        """The README's "the next bake writes them", without pairing two renders."""
        self.committed["vhashes"] = {}
        self.committed["ink"] = {}
        self._commit()
        self._bake(refuse_if_moved=True)
        after = self._after()
        self.assertEqual(after["vhashes"].get(STABLE), self.v[STABLE])
        self.assertEqual(after["ink"].get(OTHER), 21)
        self.assertNotIn(INDICATOR, after["vhashes"], "its committed hash is from another render")
        self.assertNotIn(INDICATOR, after["ink"], "its committed hash is from another render")
        self.assertEqual(after["hashes"][INDICATOR], self.committed["hashes"][INDICATOR])

    def test_the_first_bake_still_writes_everything(self) -> None:
        self.path.unlink()
        summary = self._bake(refuse_if_moved=True)
        self.assertFalse(summary.unchanged)
        self.assertEqual(self._after()["hashes"], self.h)

    def test_the_cli_says_it_did_not_write(self) -> None:
        rc, out = self._cli("--fail-on-moved")
        self.assertEqual(rc, 0, out)
        self.assertIn("baseline not written, nothing to change", out)
        self.assertNotIn("baseline written to", out)
        self.assertEqual(self.path.read_bytes(), self.before)


class TakeNamedEntries(Bake):
    """Two entries moved, one is named: the shape of the 2.5.4 autoFocus bake."""

    def setUp(self) -> None:
        super().setUp()
        self.h[STABLE], self.v[STABLE], self.i[STABLE] = _digest(0xABC), _digest(0xDEF), 77
        self.h[OTHER] = _digest(0x123)

    def test_only_the_named_entry_changes(self) -> None:
        summary = self._bake(take=[STABLE])
        self.assertEqual(summary.taken, (STABLE,))
        after = self._after()
        self.assertEqual(after["hashes"][STABLE], _digest(0xABC))
        self.assertEqual(after["vhashes"][STABLE], _digest(0xDEF))
        self.assertEqual(after["ink"][STABLE], 77)
        self.committed["hashes"][STABLE] = _digest(0xABC)
        self.committed["vhashes"][STABLE] = _digest(0xDEF)
        self.committed["ink"][STABLE] = 77
        self.assertEqual(after, self.committed, "anything but the named entry moved")

    def test_with_the_flag_a_moved_entry_not_named_refuses(self) -> None:
        with self.assertRaises(baseline.BaselineMoved) as caught:
            self._bake(refuse_if_moved=True, take=[STABLE])
        self.assertEqual([n for n, _ in caught.exception.moved], [OTHER])
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_with_the_flag_and_every_moved_entry_named_it_writes_only_those(self) -> None:
        self._bake(refuse_if_moved=True, take=[STABLE, OTHER])
        after = self._after()
        self.assertEqual(after["hashes"][OTHER], self.h[OTHER])
        self.assertEqual(after["hashes"][STABLE], self.h[STABLE])
        self.assertEqual(after["hashes"][INDICATOR], self.committed["hashes"][INDICATOR])
        self.assertEqual(after["ink"][INDICATOR], 10)
        self.assertEqual(after["rendered_by"], self.committed["rendered_by"])

    def test_a_name_not_in_the_run_is_refused(self) -> None:
        with self.assertRaisesRegex(baseline.BaselineError, "not in this run"):
            self._bake(take=["Typo.png"])
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_a_name_that_did_not_change_is_refused(self) -> None:
        self.h[STABLE], self.v[STABLE] = self.committed["hashes"][STABLE], self.committed["vhashes"][STABLE]
        with self.assertRaisesRegex(baseline.BaselineError, "nothing to take"):
            self._bake(take=[STABLE])
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_it_does_not_combine_with_the_other_doors(self) -> None:
        for other in ({"only_new": True}, {"rehash": True}):
            with self.assertRaisesRegex(baseline.BaselineError, "does not combine"):
                self._bake(take=[STABLE], **other)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_the_cli_reaches_it(self) -> None:
        rc, out = self._cli("--take", STABLE, "--take", OTHER, "--fail-on-moved")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"MOVED    {STABLE}", out)
        self.assertIn("-> TAKEN", out)
        self.assertEqual(self._after()["hashes"][STABLE], self.h[STABLE])
        self.assertEqual(self._after()["ink"][INDICATOR], 10)

    def test_the_cli_refuses_a_moved_entry_not_named(self) -> None:
        rc, out = self._cli("--take", STABLE, "--fail-on-moved")
        self.assertEqual(rc, 1, out)
        self.assertIn(f"MOVED    {OTHER}", out)
        self.assertIn("--take <name>.png", out)
        self.assertEqual(self.path.read_bytes(), self.before)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
