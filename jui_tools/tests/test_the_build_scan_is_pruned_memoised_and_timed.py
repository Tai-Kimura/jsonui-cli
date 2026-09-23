"""`jui build` does not re-walk what it throws away, and says where its time goes.

Reported 2026-09-23 from a three-platform face on 1.8.110: after the last
platform tool finished, the build sat at 100% CPU with no child process and
printed nothing for over a minute. Measured with the same functions called
read-only on that face (1,459 generated files, 227 scan roots):

    scan before the build (`_generated_scan`)     4.78 s    28,460 listdir
    observe                                         0.94 s    28,017
    scan after the build                            4.67 s    28,460
    load_migrated                                   0.76 s    24,107
    written()                                      63.15 s    2,488,684
    ----------------------------------------------------------------
    after this change, same face, same calls        1.19 s in total, 1,555 listdir

Three mechanisms, and each has an arm here:

1. `_view_targets` / `_collect_targets` rglob'd the whole platform root and
   dropped `build/`, `node_modules` … AFTER walking them (126,442 of the iOS
   root's 128,983 files were under `build/`). They now prune before
   descending. The reference for "the same set" is the old derivation
   itself — `rglob` plus the `_is_excluded` filter, on the running
   interpreter — so the arm cannot agree with the new code by sharing its
   idea of a match.
2. `real_case` listed every ancestor from `/` for every path, with no
   memory between calls. A batch now shares one listing memo.
3. `written()` re-canonicalised all 227 roots for each of 1,459 keys —
   most of the 2.5 million calls. The roots are canonicalised once per
   batch. The budget arm counts `listdir` calls, so a regression back to
   keys × roots fails it by an order of magnitude rather than by a timing.

And the stage clock: a line when a stage starts, a table at the end whose
rows and gap add up to the total, printed above the coverage and closing
lines so the last lines of a build are unchanged.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jui_cli.commands.build_cmd as build_cmd  # noqa: E402
from jui_cli.commands import lint_generated_cmd as lg  # noqa: E402
from jui_cli.core import generation_manifest as gm  # noqa: E402
from jui_cli.core.config_manager import ConfigManager  # noqa: E402

#: The build's own warning-count expression (see the lint-strings comment in
#: `build_cmd.cmd_build`). Progress lines must never match it.
WARNING_COUNT = re.compile(r"warning \[|warning:|\[warn|⚠", re.IGNORECASE)


def _touch(path: Path, text: str = "x\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fixture(root: Path) -> ConfigManager:
    """Matches inside and outside excluded dirs, plus the entry kinds a
    pattern can hit: hidden dirs, a symlink to a file, a broken symlink, a
    directory whose NAME matches, and a symlinked directory (not descended,
    by `rglob` or by the walk)."""
    (root / "jui.config.json").write_text(json.dumps({
        "platforms": {
            "ios": {"root": "ios", "layoutsDir": "Layouts"},
            "web": {"root": "web", "layoutsDir": "src/Layouts"},
        },
        "lint": {"exclude_dir_names": ["skipme"]},
    }), encoding="utf-8")
    ios, web = root / "ios", root / "web"
    _touch(ios / "App" / "View" / "Home" / "HomeGeneratedView.swift")
    # Case differs from the pattern. A DIFFERENT stem on purpose: on a
    # case-insensitive filesystem `HomeGeneratedview.swift` would be the same
    # file as the match above, and the negative arm would be vacuous.
    _touch(ios / "App" / "View" / "Home" / "OtherGeneratedview.swift")
    _touch(ios / "build" / "View" / "X" / "XGeneratedView.swift")        # excluded
    _touch(ios / "Pods" / "Generated" / "p.swift")                       # excluded
    _touch(ios / "skipme" / "Generated" / "s.swift")                     # excluded by config
    _touch(ios / ".hidden" / "ZGeneratedView.swift")
    _touch(ios / ".hidden" / "Generated" / "a.swift")
    (ios / "App" / "DirGeneratedView.swift").mkdir(parents=True)
    _touch(ios / "App" / "generated" / "g.swift")
    _touch(ios / "App" / "Generated2" / "Nested" / "Generated" / "n.swift")
    _touch(ios / "real" / "Generated" / "r.swift")
    _touch(ios / "real" / "RGeneratedView.swift")
    _touch(ios / "Layouts" / "a.json", "{}\n")
    (ios / "linkdir").symlink_to(ios / "real", target_is_directory=True)
    (ios / "LinkGeneratedView.swift").symlink_to(
        ios / "App" / "View" / "Home" / "HomeGeneratedView.swift")
    (ios / "BrokenGeneratedView.swift").symlink_to(root / "nonexistent")
    _touch(web / "src" / "generated" / "hooks" / "h.ts")
    _touch(web / "node_modules" / "pkg" / "Generated" / "m.ts")          # excluded
    _touch(web / "node_modules" / "pkg" / "MGeneratedView.kt")           # excluded
    _touch(web / "src" / "Layouts" / "b.json", "{}\n")
    return ConfigManager(root / "jui.config.json")


def _reference_view_targets(cm) -> set:
    """The 1.8.110 derivation, verbatim in shape: rglob, then filter."""
    out = set()
    for root in [r for r in (cm.ios_root, cm.android_root, cm.web_root)
                 if r is not None and r.is_dir()]:
        for pattern in ("*GeneratedView.swift", "*GeneratedView.kt"):
            out |= {p for p in root.rglob(pattern)
                    if not lg._is_excluded(p, lg.DEFAULT_EXCLUDED_DIR_NAMES)}
    return out


def _reference_generated_dirs(cm, excluded) -> set:
    out = set()
    for root in lg._platform_roots(cm):
        if root is None or not root.exists():
            continue
        out |= {g for g in root.rglob("Generated") if not lg._is_excluded(g, excluded)}
    return out


def _reference_collect_targets(cm) -> list:
    """`_collect_targets` as 1.8.110 shipped it (step 2 rglob'd, then filtered)."""
    config = cm.load()
    lint_cfg = config.get("lint", {}) if isinstance(config, dict) else {}
    extra = lint_cfg.get("exclude_dir_names", []) if isinstance(lint_cfg, dict) else []
    excluded_names = lg.DEFAULT_EXCLUDED_DIR_NAMES | frozenset(extra)
    targets = []
    for platform_layouts in sorted(lg._layout_distribution_dirs(cm)):
        for jf in platform_layouts.rglob("*.json"):
            if lg._is_resource_or_style(jf) or lg._is_excluded(jf, excluded_names):
                continue
            targets.append(("json", jf))
    for root in lg._platform_roots(cm):
        if root is None or not root.exists():
            continue
        for generated in root.rglob("Generated"):
            if lg._is_excluded(generated, excluded_names):
                continue
            if generated.is_dir():
                for tgt in lg._scan_code_tree(generated):
                    if not lg._is_excluded(tgt[1], excluded_names):
                        targets.append(tgt)
        for sub in ("src/generated/hooks", "src/generated/viewmodels",
                    "src/generated/data", "src/generated/components"):
            sub_path = root / sub
            if sub_path.exists() and not lg._is_excluded(sub_path, excluded_names):
                for tgt in lg._scan_code_tree(sub_path):
                    if not lg._is_excluded(tgt[1], excluded_names):
                        targets.append(tgt)
    seen, unique = set(), []
    for kind, path in targets:
        try:
            st = path.stat()
        except OSError:
            continue
        if (st.st_dev, st.st_ino) in seen:
            continue
        seen.add((st.st_dev, st.st_ino))
        unique.append((kind, path))
    return unique


class PrunedWalkMatchesTheOldDerivationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # resolve(): macOS's temp dir is a symlink, and `real_case` does not
        # follow it — compare like with like.
        self.root = Path(self._tmp.name).resolve()
        self.cm = _fixture(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_view_targets_are_the_set_rglob_and_the_filter_gave(self):
        expected = _reference_view_targets(self.cm)
        got = set(lg._view_targets(self.cm))
        self.assertEqual(expected, got)
        # Not an agreement between two empty sets, and the excluded match
        # exists to be dropped: the fixture is a control, not decoration.
        names = {p.name for p in got}
        self.assertIn("HomeGeneratedView.swift", names)
        self.assertIn("ZGeneratedView.swift", names)          # hidden dir
        self.assertIn("LinkGeneratedView.swift", names)       # symlink to a file
        self.assertIn("BrokenGeneratedView.swift", names)     # broken symlink
        self.assertIn("DirGeneratedView.swift", names)        # a directory's name
        self.assertNotIn("XGeneratedView.swift", names)       # under build/
        self.assertNotIn("MGeneratedView.kt", names)          # under node_modules/
        self.assertNotIn("OtherGeneratedview.swift", names)   # case differs
        self.assertTrue((self.root / "ios/App/View/Home/OtherGeneratedview.swift").exists())
        # Through the symlinked dir: neither rglob nor the walk descends.
        self.assertFalse(any("linkdir" in p.parts for p in got))

    def test_collected_generated_dirs_are_the_set_rglob_and_the_filter_gave(self):
        # Per level with the interpreter's own glob, so whichever answer
        # this Python gives for `generated` vs `Generated`, both sides give it.
        excluded = lg.DEFAULT_EXCLUDED_DIR_NAMES | frozenset({"skipme"})
        expected = _reference_generated_dirs(self.cm, excluded)
        got = {generated
               for root in lg._platform_roots(self.cm)
               if root is not None and root.exists()
               for directory, _names in lg._pruned_dirs(root, excluded)
               for generated in directory.glob("Generated")
               if not lg._is_excluded(generated, excluded)}
        self.assertEqual(expected, got)
        self.assertTrue(expected, "no Generated dir found: the arm compares nothing")

    def test_collect_targets_keeps_its_set(self):
        # The whole function against the 1.8.110 one, spellings included —
        # the de-duplication by inode keeps the first spelling it meets, so
        # this also holds the routes' relative order where it matters.
        expected = {(k, str(p)) for k, p in _reference_collect_targets(self.cm)}
        got = {(k, str(p)) for k, p in lg._collect_targets(self.cm)}
        self.assertEqual(expected, got)
        names = {Path(p).name for _k, p in got}
        self.assertTrue({"a.swift", "r.swift", "n.swift", "h.ts", "a.json", "b.json"} <= names)
        self.assertFalse({"m.ts", "s.swift", "p.swift"} & names)

    def test_the_walk_never_enters_an_excluded_directory(self):
        # The point of the change. Without the prune the sets above would
        # still agree — the filter catches everything — so this is the arm
        # that fails if the prune is lost.
        excluded = lg.DEFAULT_EXCLUDED_DIR_NAMES | frozenset({"skipme"})
        for root in (self.root / "ios", self.root / "web"):
            for directory, _names in lg._pruned_dirs(root, excluded):
                below = directory.relative_to(root).parts
                self.assertFalse(set(below) & excluded,
                                 f"walked into {directory}")


class RealCaseMemoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        for rel in ("Web/src/Generated/a.ts", "Web/src/Generated/b.ts",
                    "Web/src/other/c.ts", "ios/View/Home/HomeView.swift"):
            _touch(self.root / rel)

    def tearDown(self):
        self._tmp.cleanup()

    def _probes(self):
        r = self.root
        return [r / "Web/src/Generated/a.ts", r / "web/SRC/generated/b.ts",
                r / "WEB/src/other/c.ts", r / "ios/view/home/HomeView.swift",
                r / "ios/View/Missing/x.swift", r / "nope/deeper/y",
                Path("relative/stays/as/is"), r]

    def test_the_memo_changes_nothing_but_the_number_of_listings(self):
        memo = gm.listing_memo()
        for probe in self._probes():
            self.assertEqual(gm.real_case(probe), gm.real_case(probe, listings=memo),
                             probe)

    def test_a_directory_is_listed_once_per_batch(self):
        calls = []
        original = os.listdir

        def counting(path="."):
            calls.append(str(path))
            return original(path)

        memo = gm.listing_memo()
        os.listdir = counting
        try:
            for _ in range(3):
                for probe in self._probes():
                    gm.real_case(probe, listings=memo)
        finally:
            os.listdir = original
        self.assertTrue(calls)
        self.assertEqual(len(calls), len(set(calls)),
                         "a directory was listed twice inside one batch")


class WrittenStaysWithinAListingBudgetTests(unittest.TestCase):
    """keys × roots is what cost 63 s; the budget is the distinct directories."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.files = [_touch(self.root / "gen" / f"d{i:02d}" / "F.swift")
                      for i in range(40)]
        self.roots = [f.parent for f in self.files]

    def tearDown(self):
        self._tmp.cleanup()

    def _count(self, fn):
        calls = []
        original = os.listdir

        def counting(path="."):
            calls.append(str(path))
            return original(path)

        os.listdir = counting
        try:
            fn()
        finally:
            os.listdir = original
        return len(calls)

    def test_written_lists_each_directory_at_most_once(self):
        run = gm.GenerationRun(project_root=self.root, version="t")
        run.observe(self.files, roots=self.roots)
        n = self._count(lambda: run.written(self.files, known=set()))
        distinct = {str(a) for f in self.files for a in f.parents} | {str(self.root)}
        # 1.8.110 made about keys × (roots + 1) × depth calls here: > 10,000.
        self.assertLessEqual(n, len(distinct), f"{n} listdir calls")
        self.assertEqual([], run.outside_roots)
        self.assertEqual(40, len(run.present))

    def test_written_canonicalises_the_roots_once_not_once_per_key(self):
        # The memo alone does not catch this one: once listings are
        # memoised, re-canonicalising every root for every key costs no
        # `listdir` at all, and the listdir budget above stays green. It is
        # still keys × roots of Python work — measured on the reported face
        # with only this call site reverted, `written()` went from 0.28 s to
        # 16 s. So this arm counts `real_case` calls, which that mistake
        # multiplies and the memo does not hide.
        rule = gm._MODULE              # the shared module, where the calls resolve
        original = rule.real_case
        calls = []

        def counting(path, **kw):
            calls.append(1)
            return original(path, **kw)

        run = gm.GenerationRun(project_root=self.root, version="t")
        run.observe(self.files, roots=self.roots)
        rule.real_case = counting
        try:
            run.written(self.files, known=set())
        finally:
            rule.real_case = original
        keys, roots = len(self.files), len(self.roots)
        # Per key: the key and the project root in `_key`, the target in
        # `_under_roots`. Per batch: the base and each root once.
        self.assertLessEqual(len(calls), 3 * keys + roots + 1,
                             f"{len(calls)} real_case calls for {keys} keys "
                             f"under {roots} roots")

    def test_the_precomputed_roots_answer_as_the_per_call_ones_do(self):
        run = gm.GenerationRun(project_root=self.root, version="t")
        run.observe(self.files, roots=self.roots[:5])
        roots = run._canonical_roots()
        probes = self.files + [self.root / "gen" / "d00" / ".." / "d39" / "F.swift",
                               self.root / "GEN" / "D01" / "F.swift",
                               self.root / "elsewhere.txt"]
        for probe in probes:
            self.assertEqual(run._under_roots(probe),
                             run._under_roots(probe, canonical_roots=roots), probe)
        self.assertEqual(5, sum(run._under_roots(p) for p in self.files))


class StageClockTests(unittest.TestCase):
    def test_the_table_closes(self):
        clock = build_cmd._StageClock()
        with contextlib.redirect_stdout(io.StringIO()):
            with clock.stage("a"):
                pass
            with clock.stage("b", announce=False):
                sum(range(20000))
        lines = clock.summary_lines()
        total = float(re.search(r"\(([\d.]+)s in total\)", lines[0]).group(1))
        rows = [float(re.match(r"\s*([\d.]+)s", line).group(1)) for line in lines[1:]]
        self.assertEqual(3, len(rows))                  # a, b, (between stages)
        self.assertIn("(between stages)", lines[-1])
        # Each figure is rounded to 0.1 s on its own.
        self.assertAlmostEqual(total, sum(rows), delta=0.05 * (len(rows) + 1))

    def test_announce_prints_a_start_line_and_only_when_asked(self):
        clock = build_cmd._StageClock()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with clock.stage("scan generated files (before build)"):
                pass
            with clock.stage("iOS: sjui build", announce=False):
                pass
        self.assertEqual(["[jui build] scan generated files (before build) ..."],
                         out.getvalue().splitlines())

    def test_a_stage_that_raises_is_named_as_unfinished_and_re_raised(self):
        clock = build_cmd._StageClock()
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyError):
                with clock.stage("API model sync"):
                    raise KeyError("x")
        self.assertEqual("API model sync (did not finish)", clock.rows[0][0])

    def test_no_progress_line_is_counted_as_a_warning(self):
        clock = build_cmd._StageClock()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for label in _stage_labels():
                with clock.stage(label):
                    pass
            with contextlib.suppress(ValueError):
                with clock.stage("unfinished"):
                    raise ValueError
            clock.print_summary()
        text = out.getvalue()
        self.assertTrue(text.strip())
        self.assertEqual([], [line for line in text.splitlines()
                              if WARNING_COUNT.search(line)])


def _stage_labels() -> list:
    """Every label `cmd_build` passes to `clock.stage`, read from the source."""
    labels = []
    for node in ast.walk(ast.parse(Path(build_cmd.__file__).read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "stage" and node.args
                and isinstance(node.args[0], ast.Constant)):
            labels.append(node.args[0].value)
    return labels


class TheBuildPrintsTheTableAboveItsLastLinesTests(unittest.TestCase):
    """Driven through `cmd_build`, with the platform tools stubbed out."""

    def setUp(self):
        self._cwd = Path.cwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "web" / "src" / "Layouts").mkdir(parents=True)
        _touch(self.root / "web" / "src" / "generated" / "A.ts")
        (self.root / "jui.config.json").write_text(json.dumps({
            "platforms": {"web": {"root": "web", "layoutsDir": "src/Layouts"}},
        }), encoding="utf-8")

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _build(self, **stubs):
        os.chdir(self.root)
        originals = {name: getattr(build_cmd, name) for name in stubs}
        for name, fn in stubs.items():
            setattr(build_cmd, name, fn)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                with contextlib.suppress(BaseException):
                    build_cmd.cmd_build(argparse.Namespace(
                        clean=False, ios_only=False, android_only=False,
                        web_only=False, platform=None, lint_strings=False,
                        normalize_layouts=None))
        finally:
            for name, fn in originals.items():
                setattr(build_cmd, name, fn)
        return out.getvalue().splitlines()

    def test_success_path(self):
        lines = self._build(_run_tool=lambda *_a, **_k: True)
        table = lines.index(next(l for l in lines if "time by stage" in l))
        coverage = lines.index(next(l for l in lines if l.startswith("generation manifest:")))
        self.assertLess(table, coverage)
        self.assertTrue([l for l in lines if l.strip()][-1].startswith(
            "Build completed successfully"), lines[-3:])
        for label in ("scan generated files (before build)",
                      "scan generated files (after build)",
                      "record generation manifest"):
            self.assertIn(f"[jui build] {label} ...", lines)
        self.assertTrue(any(l.endswith("Web: rjui build") for l in lines[table:coverage]))

    def test_halted_path_names_the_stage_that_did_not_finish(self):
        def raiser(*_a, **_k):
            raise ValueError("halted")
        lines = self._build(_sync_api_models=raiser)
        table = lines.index(next(l for l in lines if "time by stage" in l))
        coverage = lines.index(next(l for l in lines if l.startswith("generation manifest:")))
        self.assertLess(table, coverage)
        self.assertTrue(any(l.endswith("API model sync (did not finish)")
                            for l in lines[table:coverage]))


if __name__ == "__main__":
    unittest.main()
