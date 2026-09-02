"""The manifest records which version WROTE each generated file.

A defective 1.8.2 shipped and 1.8.3 fixed it; every consumer was told to
regenerate if their tree came from 1.8.2, and none could read that from
their own files. One approximated with mtimes — which say when, not by
what — and translating that into a version needed the release lane's
timetable.

The property that makes it worth having is that it does not overstate. A
partial regeneration must leave untouched files at the version that last
wrote them: a manifest claiming the current version for a file it never
looked at is worse than no manifest, because a record is trusted in a way a
guess is not.

Each test below is one of the three arms that a half-done implementation
would fail differently:
  (a) a full run records every file;
  (b) a partial run records only what it touched, and the rest keep their
      older version;
  (c) a file that disappeared stops being claimed at all.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from jui_cli.core import generation_manifest as gm


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.gen = self.root / "gen"
        self.gen.mkdir()
        self.files = []
        for name in ("A.kt", "B.kt", "C.kt"):
            path = self.gen / name
            path.write_text(f"// {name} v1\n", encoding="utf-8")
            self.files.append(path)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, version):
        run = gm.GenerationRun(project_root=self.root, version=version)
        run.observe(self.files)
        return run

    def _save(self, run, present=None):
        # Called the way build_cmd calls it, `known` included. A helper that
        # drops an argument production passes is a helper that tests a
        # different function — which is how the observation-window defect
        # stayed green here while churning on a real project.
        paths = present if present is not None else self.files
        known = set(gm.load(self.root).get("files") or {})
        written = run.written(paths, known=known)
        gm.save(self.root, run.version, written,
                present_keys=[run._key(p) for p in paths])
        return written

    def _versions(self):
        data = json.loads(gm.manifest_path(self.root).read_text(encoding="utf-8"))
        return {k: v["version"] for k, v in data["files"].items()}

    # (a) ---------------------------------------------------------------
    def test_a_full_run_records_every_file(self):
        run = self._run("1.8.4")
        for path in self.files:
            path.write_text("// rewritten by 1.8.4\n", encoding="utf-8")
        written = self._save(run)

        self.assertEqual(3, len(written))
        self.assertEqual(
            {"gen/A.kt": "1.8.4", "gen/B.kt": "1.8.4", "gen/C.kt": "1.8.4"},
            self._versions(),
        )

    # (b) ---------------------------------------------------------------
    def test_a_partial_run_leaves_untouched_files_at_their_old_version(self):
        first = self._run("1.8.3")
        for path in self.files:
            path.write_text("// written by 1.8.3\n", encoding="utf-8")
        self._save(first)
        self.assertEqual({"gen/A.kt": "1.8.3", "gen/B.kt": "1.8.3",
                          "gen/C.kt": "1.8.3"}, self._versions())

        # Regenerate one file only, as `jui g project --file <spec>` does.
        second = self._run("1.8.4")
        self.files[0].write_text("// rewritten by 1.8.4\n", encoding="utf-8")
        written = self._save(second)

        self.assertEqual(["gen/A.kt"], written)
        self.assertEqual(
            {"gen/A.kt": "1.8.4", "gen/B.kt": "1.8.3", "gen/C.kt": "1.8.3"},
            self._versions(),
            "a file this run never wrote must not be claimed for its version",
        )

    def test_the_line_names_both_numbers(self):
        # A partial run reporting only its numerator reads like a full one.
        line = gm.coverage_line(1, 3, "1.8.4")
        self.assertIn("wrote 1 of 3", line)
        self.assertIn("1.8.4", line)
        # And says what it is not, since a reader's next move depends on it.
        self.assertIn("records writes, not currency", line)

    # (c) ---------------------------------------------------------------
    def test_a_file_that_disappeared_is_no_longer_claimed(self):
        first = self._run("1.8.3")
        for path in self.files:
            path.write_text("// written by 1.8.3\n", encoding="utf-8")
        self._save(first)

        self.files[1].unlink()
        remaining = [self.files[0], self.files[2]]
        second = gm.GenerationRun(project_root=self.root, version="1.8.4")
        second.observe(remaining)
        self._save(second, present=remaining)

        versions = self._versions()
        self.assertNotIn("gen/B.kt", versions,
                         "the manifest kept asserting a version for a file "
                         "that is not there")
        self.assertEqual({"gen/A.kt", "gen/C.kt"}, set(versions))

    # The limitation, pinned so it cannot be quietly lost -----------------
    def test_rewriting_identical_content_is_not_a_write(self):
        # Generators rewrite unconditionally, so a build moves every mtime.
        # Deciding on the timestamp made every build re-stamp files whose
        # bytes had not changed — 89 entries moved between two consecutive
        # builds of an unedited project, and one project saw 448 lines of
        # churn and stopped tracking the file. Content is the only thing
        # that decides.
        first = self._run("1.8.3")
        for path in self.files:
            path.write_text("// stable output\n", encoding="utf-8")
        self._save(first)
        before = gm.manifest_path(self.root).read_bytes()

        second = self._run("1.8.4")
        for path in self.files:
            # Same bytes, new timestamp: what a rebuild actually does.
            path.write_text("// stable output\n", encoding="utf-8")
            os.utime(path, (time.time() + 5, time.time() + 5))
        written = self._save(second)

        self.assertEqual([], written)
        self.assertEqual({"gen/A.kt": "1.8.3", "gen/B.kt": "1.8.3",
                          "gen/C.kt": "1.8.3"}, self._versions())
        self.assertEqual(before, gm.manifest_path(self.root).read_bytes(),
                         "an unchanged rebuild rewrote the manifest")

    def test_changed_content_still_updates(self):
        # The control for the test above: if nothing were ever recorded,
        # "byte-identical manifest" would pass for the wrong reason.
        first = self._run("1.8.3")
        for path in self.files:
            path.write_text("// v1\n", encoding="utf-8")
        self._save(first)

        second = self._run("1.8.4")
        self.files[0].write_text("// v2\n", encoding="utf-8")
        written = self._save(second)

        self.assertEqual(["gen/A.kt"], written)
        self.assertEqual("1.8.4", self._versions()["gen/A.kt"])

    def test_the_file_names_the_gap_between_tracked_and_recorded(self):
        # A run reporting "112 of 233" wrote a file holding 112 entries, and
        # nothing in the file said the other 121 had simply never been
        # written. A reader compared the two numbers and concluded records
        # had gone missing.
        #
        # The gap is narrower now that a file with no entry is recorded on
        # sight: what is left is a tracked path the run could not read —
        # discovered, then gone before the manifest was written. That still
        # has to be visible rather than rounded away.
        run = self._run("1.8.4")
        vanished = self.gen / "D.kt"
        tracked = self.files + [vanished]        # discovered, never readable
        self._save(run, present=tracked)

        data = json.loads(gm.manifest_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(4, data["summary"]["tracked"])
        self.assertEqual(3, data["summary"]["recorded"])
        self.assertEqual(1, data["summary"]["unrecorded"])
        self.assertEqual(len(data["files"]), data["summary"]["recorded"])
        # And the file says what an absent entry means, since "never
        # written" and "written by an old version" are not the same claim.
        self.assertIn("has not been written since", data["_comment"])

    def test_the_manifest_is_not_the_sync_record(self):
        # Two different facts: which toolchain copy a project holds, and
        # which version wrote its outputs. One file cannot answer both.
        self.assertEqual("generation-manifest.json", gm.MANIFEST_FILENAME)
        self.assertNotEqual("sync-meta.json", gm.MANIFEST_FILENAME)




class PathSpellingTests(unittest.TestCase):
    """Keys are spelled the way the filesystem spells them.

    Two projects measured the same defect from opposite sides: one had
    `src/generated` in the manifest and `src/Generated` from the file walk,
    the other the reverse. `Path.resolve()` was the cause — it keeps
    whatever casing it is handed on a case-insensitive filesystem, so a
    glob pattern's spelling travelled into the record. Every key named a
    path that exists on macOS and on no case-sensitive filesystem, which
    turns "which version wrote this?" into a question that always answers
    "not recorded" while looking like it ran.

    macOS cannot show that by opening the file — the assertions below
    compare STRINGS, which is the check a case-sensitive filesystem would
    perform for us.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "src" / "generated" / "hooks").mkdir(parents=True)
        self.file = self.root / "src" / "generated" / "hooks" / "useColorMode.ts"
        self.file.write_text("export {}\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_miscased_input_is_recorded_with_the_real_spelling(self):
        miscased = self.root / "src" / "Generated" / "hooks" / "useColorMode.ts"
        run = gm.GenerationRun(project_root=self.root, version="1.8.8")
        self.assertEqual("src/generated/hooks/useColorMode.ts", run._key(miscased))

    def test_the_key_matches_the_walk_byte_for_byte(self):
        # The comparison a consumer makes, and the one macOS will not make
        # for us: exact string equality against what os.walk reports.
        import os as _os
        walked = {
            _os.path.relpath(_os.path.join(r, f), self.root)
            for r, _d, fs in _os.walk(self.root / "src")
            for f in fs
        }
        run = gm.GenerationRun(project_root=self.root, version="1.8.8")
        self.assertIn(run._key(self.file), walked)

    def test_a_spelling_that_is_not_on_disk_is_not_invented(self):
        # The negative arm: a path with no real counterpart keeps what it
        # was given rather than being silently mapped onto something else.
        absent = self.root / "src" / "generated" / "hooks" / "Missing.ts"
        run = gm.GenerationRun(project_root=self.root, version="1.8.8")
        self.assertEqual("src/generated/hooks/Missing.ts", run._key(absent))

    def test_keys_relative_to_a_platform_root_are_spelled_correctly_too(self):
        # The reporting project's real manifest keys start at `src/`, not
        # at a platform directory — its jui.config.json sits inside the web
        # project, so project_root IS that root. My fixture used the
        # prefixed shape, which is a different input: the origin of the
        # relative path is what differs, and canonicalisation has to hold
        # from either origin.
        project = self.root / "src" / "generated"
        run = gm.GenerationRun(project_root=self.root, version="1.8.8")
        miscased = self.root / "SRC" / "Generated" / "hooks" / "useColorMode.ts"
        self.assertEqual("src/generated/hooks/useColorMode.ts", run._key(miscased))
        self.assertTrue(project.is_dir())

    def test_the_line_separates_tracked_from_distributed(self):
        # A reader took the distributed total for the manifest's scope and
        # concluded hundreds of files were unrecorded. Two names, two
        # numbers.
        line = gm.coverage_line(198, 200, "1.8.8", distributed=507)
        self.assertIn("198 of 200 tracked generated file(s)", line)
        self.assertIn("507 file(s) distributed in total", line)

    def test_the_line_omits_the_second_number_when_it_adds_nothing(self):
        line = gm.coverage_line(4, 4, "1.8.8", distributed=4)
        self.assertNotIn("distributed in total", line)


if __name__ == "__main__":
    unittest.main()


class BootstrapTests(unittest.TestCase):
    """A stable project still gets a first entry.

    Deciding on content alone stopped the churn and introduced a worse
    failure: a build whose output is byte-identical to what was there
    records nothing, so a project whose generation is idempotent never gets
    a first entry at all. Measured downstream — a run that wrote 83 files
    reported `wrote 0 of 223` with an empty file, on every build, because
    each file came back the same.

    A file with no entry is recorded whatever its bytes did: this run
    produced exactly those bytes, which is both true and the only answer
    available. The two rules converge — the first build fills the record,
    later ones only correct it — so the churn does not come back.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.gen = self.root / "gen"
        self.gen.mkdir()
        self.files = []
        for name in ("A.kt", "B.kt"):
            path = self.gen / name
            path.write_text("stable\n", encoding="utf-8")
            self.files.append(path)

    def tearDown(self):
        self._tmp.cleanup()

    def _build(self, version):
        """One build that regenerates identical bytes, as a stable one does."""
        known = set(gm.load(self.root).get("files") or {})
        run = gm.GenerationRun(project_root=self.root, version=version)
        run.observe(self.files)
        for path in self.files:
            path.write_text("stable\n", encoding="utf-8")
        written = run.written(self.files, known=known)
        gm.save(self.root, version, written,
                present_keys=[run._key(p) for p in self.files])
        return written

    def test_the_first_build_records_even_when_nothing_changed(self):
        self.assertEqual(2, len(self._build("1.8.10")))
        data = json.loads(gm.manifest_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(2, data["summary"]["recorded"])
        self.assertEqual(0, data["summary"]["unrecorded"])

    def test_the_second_build_records_nothing(self):
        # The control that keeps the churn fix honest: bootstrapping must
        # not turn into "record everything, every time".
        self._build("1.8.10")
        before = gm.manifest_path(self.root).read_bytes()
        self.assertEqual([], self._build("1.8.11"))
        self.assertEqual(before, gm.manifest_path(self.root).read_bytes())

    def test_a_file_added_later_is_recorded_on_the_build_that_finds_it(self):
        self._build("1.8.10")
        extra = self.gen / "C.kt"
        extra.write_text("stable\n", encoding="utf-8")
        self.files.append(extra)
        self.assertEqual(["gen/C.kt"], self._build("1.8.11"))

    def test_the_summary_says_which_directories_were_counted(self):
        run = gm.GenerationRun(project_root=self.root, version="1.8.10")
        keys = [run._key(p) for p in self.files]
        gm.save(self.root, "1.8.10", keys, present_keys=keys,
                scope={"gen": 2})
        data = json.loads(gm.manifest_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual({"gen": 2}, data["summary"]["trackedByDirectory"])


class KeyMigrationTests(unittest.TestCase):
    """Records written under an older spelling survive; gone files do not.

    Fixing the key spelling silently destroyed the records it was meant to
    protect: `save` prunes entries whose key is not in the present set, and
    it compares strings, so every entry written as `src/Generated/…` looked
    like a file that no longer exists once keys became `src/generated/…`.
    One project lost 198 in a single build — same files, same disk, a
    different spelling.

    Restoring them by re-recording is not a fix. This record exists to find
    files written by a particular release; re-stamping them with today's
    version answers that question wrongly while looking repaired. So the
    entry keeps ITS OWN version and only its key moves.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "src" / "generated").mkdir(parents=True)
        self.file = self.root / "src" / "generated" / "ColorManager.ts"
        self.file.write_text("export {}\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, key: str, version: str) -> None:
        gm.manifest_path(self.root).parent.mkdir(parents=True, exist_ok=True)
        gm.manifest_path(self.root).write_text(json.dumps({
            "schemaVersion": 1,
            "files": {key: {"version": version, "generatedAt": "2026-09-03T00:00:00Z",
                            "generatedBy": "jui build"}},
        }, indent=2), encoding="utf-8")

    def _save_with_present(self, present_keys):
        return gm.save(self.root, "1.8.10", [], present_keys=present_keys)

    def test_an_entry_written_under_the_old_spelling_survives(self):
        self._seed("src/Generated/ColorManager.ts", "1.8.7")
        manifest = self._save_with_present(["src/generated/ColorManager.ts"])
        self.assertIn("src/generated/ColorManager.ts", manifest["files"])
        self.assertEqual(
            "1.8.7",
            manifest["files"]["src/generated/ColorManager.ts"]["version"],
            "the record was restored under today's version, which answers "
            "'which release wrote this' wrongly",
        )
        self.assertEqual(0, manifest["summary"]["dropped"])

    def test_an_entry_whose_file_is_gone_is_still_dropped(self):
        # The control for the migration: it must not resurrect everything.
        self._seed("src/Generated/GONE.ts", "1.8.7")
        manifest = self._save_with_present(["src/generated/ColorManager.ts"])
        self.assertEqual({}, manifest["files"])
        self.assertEqual(1, manifest["summary"]["dropped"])

    def test_dropping_is_announced(self):
        self._seed("src/Generated/GONE.ts", "1.8.7")
        manifest = self._save_with_present(["src/generated/ColorManager.ts"])
        self.assertIn("src/generated/GONE.ts", manifest["summary"]["droppedKeys"])
        line = gm.coverage_line(0, 1, "1.8.10", dropped=1)
        self.assertIn("dropped 1", line)


class CleanRebuildTests(unittest.TestCase):
    """A `--clean` build records what it regenerated.

    The reproduction the pre-distribution smoke never ran: it only ever
    exercised an unedited tree, so it checked the "wrote nothing" side and
    called an empty-but-stable manifest a pass. A project deleting its
    output and regenerating it reported `wrote 0 of 223` with an empty file
    while 83 files were written.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.gen = self.root / "src" / "generated"
        self.gen.mkdir(parents=True)
        self.files = [self.gen / n for n in ("A.ts", "B.ts", "C.ts")]
        for f in self.files:
            f.write_text("generated\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _build(self, version):
        known = set(gm.load(self.root).get("files") or {})
        run = gm.GenerationRun(project_root=self.root, version=version)
        run.observe(self.files)
        for f in self.files:            # --clean: remove, then regenerate
            f.unlink()
        for f in self.files:
            f.write_text("generated\n", encoding="utf-8")
        written = run.written(self.files, known=known)
        gm.save(self.root, version, written,
                present_keys=[run._key(f) for f in self.files])
        return written

    def test_a_clean_rebuild_does_not_record_nothing(self):
        self.assertEqual(3, len(self._build("1.8.10")))
        data = json.loads(gm.manifest_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(3, data["summary"]["recorded"])

    def test_a_second_clean_rebuild_adds_no_churn(self):
        self._build("1.8.10")
        before = gm.manifest_path(self.root).read_bytes()
        self.assertEqual([], self._build("1.8.11"))
        self.assertEqual(before, gm.manifest_path(self.root).read_bytes())
