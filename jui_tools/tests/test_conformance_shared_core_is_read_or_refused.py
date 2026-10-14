"""A gate or bake that cannot read ``shared/core`` beside its conformance dir
says so and stops, instead of judging on nothing.

THE DEFECT THIS EXISTS FOR

Three readers resolve ``shared/core`` as a sibling of the conformance dir, and
each one reads a missing file as empty, silently. Run on a copy of the
directory (``--dir`` outside the repo), the same artifacts of run 38620808116
gave 16 unrecorded / 55 stale cross-effect findings where the repo gave 21 /
25. The difference was reported as a CI-vs-local input difference, because
nothing in the output said a file had not been read. A bake from such a copy
would carve nothing into ``hashes_by_os``.

Each arm puts the SAME corpus on both sides of the boundary — once with the
two files beside it, once without — so a refusal that fired always (or never)
fails one side.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests._shared_core import conformance_with_shared_core

from jui_cli.conformance import shared_core
from jui_cli.conformance.baseline import BaselineError, update_baseline
from jui_cli.conformance.gate import evaluate

try:
    from PIL import Image

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover
    HAVE_PILLOW = False

REPO = Path(__file__).resolve().parents[2]


def _copy_committed_conformance(root: Path) -> Path:
    conf = root / "conformance"
    shutil.copytree(
        REPO / "conformance", conf, ignore=shutil.ignore_patterns("hosts", "artifacts", "fixtures")
    )
    return conf


def _missing_problems(problems: list[str]) -> list[str]:
    return [p for p in problems if "and it is not there" in p]


class TheGateRefusesCrossEffectWithoutSharedCoreTests(unittest.TestCase):
    def _gate(self, conf: Path, *, cross_effect: bool = True) -> list[str]:
        out = conf.parent / "REPORT.md"
        return evaluate(
            conf, ["web", "ios", "android"], out_path=out, visual=True,
            cross_effect=cross_effect, env="ci",
        ).problems

    def test_without_either_file_both_are_named(self) -> None:
        conf = _copy_committed_conformance(Path(tempfile.mkdtemp()))
        missing = _missing_problems(self._gate(conf))
        self.assertEqual(len(missing), 2, missing)
        self.assertIn(str(conf.parent / "shared" / "core" / shared_core.SEMANTICS), missing[0])
        self.assertIn(str(conf.parent / "shared" / "core" / shared_core.DEFINITIONS), missing[1])
        self.assertTrue(all(m.startswith("--cross-effect reads ") for m in missing))

    def test_each_file_alone_is_named_alone(self) -> None:
        for present, absent in (
            (shared_core.SEMANTICS, shared_core.DEFINITIONS),
            (shared_core.DEFINITIONS, shared_core.SEMANTICS),
        ):
            with self.subTest(present=present):
                root = Path(tempfile.mkdtemp())
                conf = _copy_committed_conformance(root)
                (root / "shared" / "core").mkdir(parents=True)
                shutil.copy(REPO / "shared" / "core" / present, root / "shared" / "core" / present)
                missing = _missing_problems(self._gate(conf))
                self.assertEqual(len(missing), 1, missing)
                self.assertIn(absent, missing[0])

    def test_with_both_files_beside_it_nothing_is_refused(self) -> None:
        """The boundary: the same copy, with the files, is judged."""
        root = Path(tempfile.mkdtemp())
        conf = _copy_committed_conformance(root)
        (root / "shared" / "core").mkdir(parents=True)
        for name in (shared_core.SEMANTICS, shared_core.DEFINITIONS):
            shutil.copy(REPO / "shared" / "core" / name, root / "shared" / "core" / name)
        self.assertEqual(_missing_problems(self._gate(conf)), [])

    def test_a_gate_not_asked_for_cross_effect_does_not_ask_for_the_files(self) -> None:
        conf = _copy_committed_conformance(Path(tempfile.mkdtemp()))
        self.assertEqual(_missing_problems(self._gate(conf, cross_effect=False)), [])

    def test_the_repo_itself_has_both(self) -> None:
        """From the repo root (CI's shape) the check never fires."""
        self.assertEqual(
            shared_core.missing_for(
                REPO / "conformance", [shared_core.SEMANTICS, shared_core.DEFINITIONS], asked="x"
            ),
            [],
        )


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class TheBakeRefusesWithoutDefinitionsTests(unittest.TestCase):
    """The carve-out is what the definitions feed: a glass picture must land
    under hashes_by_os, never in the OS-agnostic table."""

    GLASS_DEFS = {"common": {"glass": {"type": "boolean", "description": "UIGlassEffect, #available(iOS 26)"}}}

    def _corpus(self, root: Path) -> Path:
        conf = root / "conformance"
        art = conf / "artifacts" / "ios"
        art.mkdir(parents=True)
        (conf / "baselines" / "local").mkdir(parents=True)
        (conf / "manifest.json").write_text(json.dumps({"fixtures": [{"id": "common/glass__true"}, {"id": "Label/text__a"}]}))
        for name, shade in (("common_glass__true.png", 0), ("Label_text__a.png", 90)):
            img = Image.new("RGB", (64, 64), (255, 255, 255))
            for x in range(0, 64, 4):
                for y in range(32):
                    img.putpixel((x, y), (shade, shade, shade))
            img.save(art / name)
        return conf

    def test_without_definitions_nothing_is_written(self) -> None:
        conf = self._corpus(Path(tempfile.mkdtemp()))
        with self.assertRaises(BaselineError) as caught:
            update_baseline(conf, "ios", env="local", os_key="ios-26.2")
        self.assertIn("a bake reads ", str(caught.exception))
        self.assertIn("hashes_by_os", str(caught.exception))
        self.assertFalse((conf / "baselines" / "local" / "ios.hashes.json").exists())

    def test_with_definitions_the_glass_picture_is_carved(self) -> None:
        """The boundary, and the reason the refusal exists: with the file the
        same corpus files glass under the OS; the OS-agnostic table never has it."""
        root = Path(tempfile.mkdtemp())
        conf = self._corpus(root)
        conformance_with_shared_core(root, definitions=self.GLASS_DEFS)
        update_baseline(conf, "ios", env="local", os_key="ios-26.2")
        written = json.loads((conf / "baselines" / "local" / "ios.hashes.json").read_text())
        self.assertEqual(sorted(written["hashes"]), ["Label_text__a.png"])
        self.assertEqual(sorted(written["hashes_by_os"]["ios-26.2"]), ["common_glass__true.png"])


class TheInputDigestNamesWhatMovedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.conf = conformance_with_shared_core(self.root)
        (self.conf / "manifest.json").write_text("{}")
        (self.conf / "results").mkdir()
        (self.conf / "results" / "web.results.json").write_text('{"a": 1}')
        (self.conf / "artifacts" / "web").mkdir(parents=True)
        (self.conf / "artifacts" / "web" / "x.png").write_bytes(b"x")

    def _fields(self) -> dict[str, str]:
        line = shared_core.input_digest(self.conf)
        self.assertTrue(line.startswith("conformance inputs: "))
        out, key = {}, None
        for token in line[len("conformance inputs: "):].split(" "):
            if "=" in token and token.split("=", 1)[0].isidentifier():
                key, value = token.split("=", 1)
                out[key] = value
            else:
                out[key] += " " + token
        return out

    def test_the_same_inputs_print_the_same_line(self) -> None:
        self.assertEqual(shared_core.input_digest(self.conf), shared_core.input_digest(self.conf))

    def test_a_changed_input_moves_its_own_field_and_no_other(self) -> None:
        for change, field in (
            (lambda: (self.conf / "results" / "web.results.json").write_text('{"a": 2}'), "results"),
            (lambda: (self.conf / "artifacts" / "web" / "x.png").write_bytes(b"y"), "artifacts"),
            (lambda: (self.conf / "manifest.json").write_text("{ }"), "manifest"),
            (lambda: (self.root / "shared" / "core" / "attribute_semantics.json").write_text("{}"), "semantics"),
        ):
            with self.subTest(field=field):
                before = self._fields()
                change()
                after = self._fields()
                self.assertEqual([k for k in before if before[k] != after[k]], [field])

    def test_a_missing_sibling_is_printed_as_missing(self) -> None:
        (self.root / "shared" / "core" / "attribute_definitions.json").unlink()
        self.assertTrue(self._fields()["definitions"].endswith(" MISSING"))
        self.assertFalse(self._fields()["semantics"].endswith(" MISSING"))


class TheCommandsPrintTheDigestOnceTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> list[str]:
        import contextlib
        import io

        from jui_cli.cli import main

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(argv)
        return [l for l in buf.getvalue().splitlines() if l.startswith("conformance inputs: ")]

    def test_the_gate_prints_it_once(self) -> None:
        conf = _copy_committed_conformance(Path(tempfile.mkdtemp()))
        lines = self._run(["conformance", "gate", "--platform", "web", "--no-visual", "--dir", str(conf),
                           "--out", str(conf.parent / "R.md")])
        self.assertEqual(len(lines), 1, lines)
        self.assertIn(f"dir={conf.resolve()}", lines[0])

    @unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
    def test_a_bake_prints_it_once_even_when_it_refuses(self) -> None:
        conf = TheBakeRefusesWithoutDefinitionsTests._corpus(None, Path(tempfile.mkdtemp()))
        lines = self._run(["conformance", "baseline", "update", "--platform", "ios", "--env", "local",
                           "--dir", str(conf)])
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].endswith(" MISSING"), lines[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
