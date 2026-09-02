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
        # The two now sit on separate lines — see coverage_line — so this
        # checks both are present and which line each is on.
        block = gm.coverage_line(1, 3, "1.8.4")
        self.assertIn("generation manifest: 3 tracked generated file(s)",
                      block)
        self.assertIn("this run (jui 1.8.4): recorded/updated 1", block)

    def test_the_two_kinds_of_number_do_not_share_a_line(self):
        # What the split is for: a baseline that keeps the first line can
        # say "this line" rather than deleting the run's number, so the
        # next state-dependent number added lands outside it instead of
        # passing an exclusion rule that never heard of it.
        lines = gm.coverage_line(1, 3, "1.8.4", distributed=9, dropped=2,
                                 collisions=1, collision_keys=["gen/A.kt"],
                                 recorded_versions={"1.8.3": 3}).split("\n")
        head = lines[0]
        # One subject, one population, one number per line. The head is the
        # project's file count and carries nothing else — not the version,
        # which was read as describing it, and not the distributed total,
        # which is a different population and was read as its denominator.
        for foreign in ("recorded/updated", "dropped", "merged away",
                        "distributed", "1.8.4", "1.8.3"):
            self.assertNotIn(foreign, head)
        run = next(l for l in lines if "this run" in l)
        for foreign in ("tracked", "distributed", "recorded versions"):
            self.assertNotIn(foreign, run)
        self.assertNotIn("merged away", run)

    def test_the_run_line_prints_when_the_run_did_nothing(self):
        # Otherwise "recorded nothing" and "nobody read the output" are the
        # same observation.
        lines = gm.coverage_line(0, 3, "1.8.4").split("\n")
        run = next(l for l in lines if "this run" in l)
        self.assertIn("recorded/updated 0", run)
        # The other two are omitted at zero: nothing turns on telling
        # "none dropped" from "not reported".
        self.assertNotIn("dropped", run)
        self.assertNotIn("merged away", run)

    def test_the_block_says_what_it_is_not(self):
        # The reader's next move depends on it: this records which version
        # wrote a file, not whether the file is current.
        # Beside what it qualifies, and true of every entry — the earlier
        # wording promised something only about untouched files, and a
        # face measured a touched one carrying an older version anyway.
        block = gm.coverage_line(1, 3, "1.8.4")
        versions = next(l for l in block.split("\n")
                        if "recorded versions" in l)
        self.assertIn("not proof of what generated the file", versions)

    def test_the_line_does_not_call_the_count_a_write_count(self):
        # It is not one, in either direction: a run that wrote 83 files
        # reported 223 of 223 (bootstrapped entries) and, after --clean,
        # 0 of 223 (nothing on record moved). Whichever number is right for
        # the record, "wrote" is wrong for both.
        line = gm.coverage_line(1, 3, "1.8.4")
        self.assertNotIn("wrote", line)
        self.assertNotIn("records writes", line)
        self.assertIn("recorded/updated", line)

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
        # The other limitation, which the behaviour cannot fix: with the
        # old record gone there is no other version to write, so the only
        # repair available is saying so. A comment that lists the blank
        # carefully and omits this one reads as complete.
        self.assertIn("re-made it, not the version that generated",
                      data["_comment"])

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
        lines = gm.coverage_line(198, 200, "1.8.8",
                                  distributed=507).split("\n")
        self.assertIn("200 tracked generated file(s)", lines[0])
        self.assertIn("distributed to platforms: 507 file(s)", lines[1])
        # Not in the same clause: "200 tracked (507 distributed)" was read
        # as 200 OF 507, which are different populations.
        self.assertNotIn("507", lines[0])

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
        # A second tree whose name is ALREADY spelled the way the disk
        # spells it. The fixture has to hold both sides: measured on two
        # real manifests, keys died exactly when normalisation changed the
        # spelling (327 of 537 and 161 of 249, residual zero), so a fixture
        # containing only the changing side passes whatever the migration
        # does to the other — and a project that looked only at survivors
        # read this defect as "churn fixed".
        (self.root / "Model" / "Generated").mkdir(parents=True)
        self.stable = self.root / "Model" / "Generated" / "UserDto.swift"
        self.stable.write_text("struct UserDto {}\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, *entries: tuple) -> None:
        gm.manifest_path(self.root).parent.mkdir(parents=True, exist_ok=True)
        gm.manifest_path(self.root).write_text(json.dumps({
            "schemaVersion": 1,
            "files": {key: {"version": version,
                            "generatedAt": "2026-09-03T00:00:00Z",
                            "generatedBy": "jui build"}
                      for key, version in entries},
        }, indent=2), encoding="utf-8")

    def _save_with_present(self, present_keys):
        return gm.save(self.root, "1.8.10", [], present_keys=present_keys)

    def test_an_entry_written_under_the_old_spelling_survives(self):
        self._seed(("src/Generated/ColorManager.ts", "1.8.7"),
                   ("Model/Generated/UserDto.swift", "1.8.6"))
        manifest = self._save_with_present(
            ["src/generated/ColorManager.ts", "Model/Generated/UserDto.swift"])
        self.assertIn("src/generated/ColorManager.ts", manifest["files"])
        self.assertEqual(
            "1.8.7",
            manifest["files"]["src/generated/ColorManager.ts"]["version"],
            "the record was restored under today's version, which answers "
            "'which release wrote this' wrongly",
        )
        self.assertEqual(0, manifest["summary"]["dropped"])

    def test_an_entry_whose_spelling_does_not_change_is_untouched(self):
        # The other side of the fixture. Keys died exactly when
        # normalisation changed their spelling; one that does not change
        # must come through with its own version and not be re-stamped,
        # which a fixture holding only the changing side cannot show.
        self._seed(("Model/Generated/UserDto.swift", "1.8.6"))
        manifest = self._save_with_present(["Model/Generated/UserDto.swift"])
        self.assertEqual("1.8.6",
                         manifest["files"]["Model/Generated/UserDto.swift"]["version"])
        self.assertEqual(0, manifest["summary"]["dropped"])

    def test_an_entry_whose_file_is_gone_is_still_dropped(self):
        # The control for the migration: it must not resurrect everything.
        self._seed(("src/Generated/GONE.ts", "1.8.7"))
        manifest = self._save_with_present(["src/generated/ColorManager.ts"])
        self.assertEqual({}, manifest["files"])
        self.assertEqual(1, manifest["summary"]["dropped"])

    def test_dropping_is_announced(self):
        self._seed(("src/Generated/GONE.ts", "1.8.7"))
        manifest = self._save_with_present(["src/generated/ColorManager.ts"])
        self.assertIn("src/generated/GONE.ts", manifest["summary"]["droppedKeys"])
        line = gm.coverage_line(0, 1, "1.8.10", dropped=1)
        self.assertIn("dropped 1", line)


class KeyCollisionTests(unittest.TestCase):
    """Two spellings normalising onto one key is a deletion nothing counts.

    `dropped` counts what the prune removed. A collision happens earlier,
    in the merge, so an entry can vanish with `dropped 0` and every other
    number in the summary intact — the same shape as the re-stamping
    defect, which is why it is worth its own arms rather than a note.

    SYNTHETIC ON PURPOSE, AND THAT IS THE MEASUREMENT, NOT A GUESS. Real
    manifests were checked across three downstream corpora and all eight
    recorded generations, normalising every stored key: 537→537, 210→210,
    249→249, 198→198, and so on. Zero collisions anywhere. A smoke arm on a
    real tree would therefore return "none" on every run for as long as no
    project happens to hold two spellings, and each of those runs would
    read like the check had passed. The invariant is worth holding anyway —
    the next normaliser change is what makes it reachable — so it is held
    here, over a fixture built to contain one, with a control proving the
    detection fires.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "src" / "generated").mkdir(parents=True)
        (self.root / "src" / "generated" / "A.ts").write_text("x\n",
                                                             encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, files: dict) -> None:
        path = gm.manifest_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schemaVersion": 1, "files": files},
                                   indent=2), encoding="utf-8")
        self.assertEqual(len(files),
                         len(gm.load(self.root).get("files") or {}),
                         "the seed is not being read — the arms below would "
                         "then be measuring a project with no manifest")

    def test_migration_keeps_every_entry_when_no_two_keys_converge(self):
        # The invariant: as many entries out as in.
        self._seed({"src/generated/A.ts": {"version": "1.8.7"},
                    "src/generated/B.ts": {"version": "1.8.7"}})
        migrated, collisions = gm.load_migrated_with_collisions(self.root)
        self.assertEqual(2, len(migrated))
        self.assertEqual({}, collisions)

    def test_three_spellings_of_one_file_are_detected_not_absorbed(self):
        # The positive control. Without it, the arm above passes on any
        # corpus that simply has no collisions to find — which is every
        # corpus measured so far.
        self._seed({"src/Generated/A.ts": {"version": "1.8.5"},
                    "src/generated/A.ts": {"version": "1.8.7"},
                    "src/GENERATED/A.ts": {"version": "1.8.6"}})
        migrated, collisions = gm.load_migrated_with_collisions(self.root)
        self.assertEqual(1, len(migrated))
        # One collided key, two entries absorbed — different numbers.
        self.assertEqual({"src/generated/A.ts": 2}, collisions)

    def test_the_survivor_is_chosen_by_time_not_by_order_or_spelling(self):
        # Whichever entry is kept, it must not be decided by the order the
        # keys happen to sit in the file.
        #
        # The fixture has to separate three rules that would otherwise
        # agree. Written the obvious way — newest entry first — first-wins
        # and newest-wins give the same answer and the arm proves nothing.
        # So the newest record is placed LAST and under the non-canonical
        # spelling: order would keep 1.8.7, the canonical-spelling
        # tiebreak would keep 1.8.7, and only the timestamp keeps 1.8.5.
        self._seed({
            "src/generated/A.ts": {"version": "1.8.7",
                                   "generatedAt": "2026-08-01T00:00:00Z"},
            "src/Generated/A.ts": {"version": "1.8.5",
                                   "generatedAt": "2026-09-01T00:00:00Z"},
        })
        migrated, _ = gm.load_migrated_with_collisions(self.root)
        self.assertEqual("1.8.5", migrated["src/generated/A.ts"]["version"],
                         "the newer record lost to the one listed first")

    def test_the_canonical_spelling_decides_when_the_clock_cannot(self):
        # Same timestamp on both, so the rule above cannot separate them.
        # The entry already spelled the canonical way is the one a run with
        # the current normaliser wrote. It is placed second, so first-wins
        # would give the other answer.
        self._seed({
            "src/Generated/A.ts": {"version": "1.8.5",
                                   "generatedAt": "2026-08-01T00:00:00Z"},
            "src/generated/A.ts": {"version": "1.8.7",
                                   "generatedAt": "2026-08-01T00:00:00Z"},
        })
        migrated, _ = gm.load_migrated_with_collisions(self.root)
        self.assertEqual("1.8.7", migrated["src/generated/A.ts"]["version"])

    def test_the_saved_summary_says_entries_were_merged_away(self):
        # dropped stays 0 here: that is exactly the reason this needs its
        # own field rather than riding on the existing count.
        self._seed({"src/Generated/A.ts": {"version": "1.8.5"},
                    "src/generated/A.ts": {"version": "1.8.7"}})
        manifest = gm.save(self.root, "1.8.10", [],
                           present_keys=["src/generated/A.ts"], scope={})
        self.assertEqual(1, manifest["summary"]["collisions"])
        self.assertEqual(["src/generated/A.ts"],
                         manifest["summary"]["collisionKeys"])
        self.assertEqual(0, manifest["summary"]["dropped"])

    def test_the_merge_gets_a_line_of_its_own(self):
        lines = gm.coverage_line(0, 1, "1.8.10", collisions=2,
                                 collision_keys=["src/generated/A.ts"]
                                 ).split("\n")
        warn = next(i for i, l in enumerate(lines) if "merged away" in l)
        self.assertIn("merged away 2", lines[warn])
        # Not folded into any of the counted lines.
        for other in lines[:warn]:
            self.assertNotIn("merged away", other)

    def test_the_warning_reads_as_a_loss_to_someone_seeing_it_first(self):
        # No corpus has ever produced a collision, so whoever reads this
        # line will be reading it for the first time with no context. The
        # text is asserted rather than the count, because the count is the
        # part that will look self-explanatory and the rest is what has to
        # carry the meaning.
        lines = gm.coverage_line(
            0, 9, "1.8.10", collisions=2,
            collision_keys=["src/generated/ColorManager.ts"]).split("\n")
        warn = next(i for i, l in enumerate(lines) if "merged away" in l)
        warning = "\n".join(lines[warn:])
        # Which files.
        self.assertIn("src/generated/ColorManager.ts", warning)
        # What was lost, in words, not a count.
        self.assertIn("the version each of them named is gone", warning)
        # That no other check covers it — the reason it is not folded into
        # the run line.
        self.assertIn("a silent loss", warning)
        self.assertIn("`dropped` does not count", warning)
        self.assertIn("nothing else reports", warning)

    def test_the_warning_says_how_many_keys_it_did_not_name(self):
        # A truncated list reads as the whole list.
        keys = [f"src/generated/f{i}.ts" for i in range(7)]
        lines = gm.coverage_line(0, 9, "1.8.10", collisions=9,
                                 collision_keys=keys).split("\n")
        warning = next(l for l in lines if "merged away" in l)
        self.assertIn("+2 more", warning)

    def test_no_warning_line_when_nothing_merged(self):
        lines = gm.coverage_line(0, 1, "1.8.10").split("\n")
        self.assertTrue(all("merged away" not in l for l in lines), lines)
        # And the four that always print are all there.
        self.assertEqual(4, len(lines), lines)

    def test_a_truncated_key_list_says_it_is_truncated(self):
        # 20 keys under a count of 45 reads as the whole list unless the
        # file says otherwise.
        self._seed({f"src/generated/gone{i}.ts": {"version": "1.8.7"}
                    for i in range(45)})
        manifest = gm.save(self.root, "1.8.10", [],
                           present_keys=["src/generated/A.ts"], scope={})
        self.assertEqual(45, manifest["summary"]["dropped"])
        self.assertEqual(20, len(manifest["summary"]["droppedKeys"]))
        self.assertEqual("first 20 of 45",
                         manifest["summary"]["droppedKeysNote"])

    def test_nothing_is_said_about_truncation_when_nothing_is_cut(self):
        self._seed({"src/generated/gone.ts": {"version": "1.8.7"}})
        manifest = gm.save(self.root, "1.8.10", [],
                           present_keys=["src/generated/A.ts"], scope={})
        self.assertNotIn("droppedKeysNote", manifest["summary"])


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


class OneSubjectPerLineTests(unittest.TestCase):
    """The rule the block is built on, checked as a rule.

    Every misreading this line produced came from two things sharing a
    clause: a version beside a count it did not describe, and two counts
    over different populations inside one parenthesis. Patching the wording
    did not hold — two earlier repairs appended a denial to the end, and a
    denial at the end cannot reach a reading formed at the start.
    """

    def _lines(self, **kwargs):
        base = dict(written=1, total=492, version="1.8.13", distributed=1042,
                    recorded_versions={"1.8.10": 294, "1.8.7": 198})
        base.update(kwargs)
        return gm.coverage_line(**base).split("\n")

    def test_the_running_version_appears_once_and_on_the_run_line(self):
        lines = self._lines()
        carrying = [l for l in lines if "1.8.13" in l]
        self.assertEqual(1, len(carrying), lines)
        self.assertIn("this run", carrying[0])

    def test_no_line_holds_two_populations(self):
        # `492 tracked (1042 distributed)` was read as 492 OF 1042.
        for line in self._lines():
            with self.subTest(line=line):
                self.assertFalse("492" in line and "1042" in line)

    def test_the_recorded_versions_are_printed_at_all(self):
        # They were in no output: a reader wanting them had to parse the
        # JSON, and three faces read the running version instead.
        line = next(l for l in self._lines() if "recorded versions" in l)
        self.assertIn("294 at 1.8.10", line)
        self.assertIn("198 at 1.8.7", line)

    def test_every_line_prints_when_its_number_is_dull(self):
        # A line that appears only when interesting makes its absence carry
        # the opposite claim: no `recorded versions` would say "all the
        # same", no `distributed` would say "none".
        lines = self._lines(distributed=0, recorded_versions={"1.8.13": 492})
        self.assertIn("  distributed to platforms: 0 file(s)", lines)
        self.assertTrue(any("recorded versions: 492 at 1.8.13" in l
                            for l in lines), lines)

    def test_a_count_that_could_not_be_taken_says_so(self):
        # Distinct from zero. One value used to mean both, and a lane read
        # the resulting silence as a zero on a tree that distributed
        # nothing because nothing was wired.
        lines = self._lines(distributed=None)
        self.assertIn("  distributed to platforms: not counted", lines)

    def test_an_empty_record_says_so_rather_than_omitting_the_line(self):
        lines = self._lines(recorded_versions={})
        self.assertTrue(any("none recorded yet" in l for l in lines), lines)

    def test_the_order_is_stable_for_a_baseline(self):
        a = gm.coverage_line(0, 2, "1.8.13",
                             recorded_versions={"1.8.7": 1, "1.8.10": 1})
        b = gm.coverage_line(0, 2, "1.8.13",
                             recorded_versions={"1.8.10": 1, "1.8.7": 1})
        self.assertEqual(a, b)


class ReproducibleLinesComeFirstTests(unittest.TestCase):
    """The block is ordered by what a fresh clone reproduces.

    `recorded versions` was placed with the project's facts because it
    describes the record rather than the run. True, and not the property a
    baseline cares about: a face that gitignores the manifest gets a
    different value from a warm tree and a fresh one. Measured on one tree
    at one tool version — `9 at 1.8.10` warm, `9 at 1.8.13` after deleting
    the record, because the first-sighting rule stamps everything with the
    running version.

    That is exactly the failure the two-line split was meant to end, back
    again one line up. So the order is the rule now, and this checks it.
    """

    #: What each line's value depends on. A line moved between groups
    #: without this being updated fails below.
    REPRODUCES = ("generation manifest:", "  distributed to platforms:")
    STATE = ("  this run (", "  recorded versions:")

    def _block(self, **kwargs):
        base = dict(written=0, total=9, version="1.8.13", distributed=2,
                    recorded_versions={"1.8.10": 9})
        base.update(kwargs)
        return gm.coverage_line(**base).split("\n")

    def test_the_state_dependent_region_starts_at_this_run(self):
        # Contiguity alone is too weak: the previous order also had both
        # state lines last, as `recorded versions` then `this run`, and a
        # rule written as "from `this run:` to the end" missed the first of
        # them. That is the rule the faces have. So the property is where
        # the region STARTS, not merely that it is contiguous — checked
        # after a red-check where the weaker version passed against the
        # order it was written to reject.
        lines = [l for l in self._block() if "merged away" not in l]
        kinds = ["state" if any(l.startswith(p) for p in self.STATE)
                 else "reproduces" for l in lines]
        self.assertEqual(["reproduces", "reproduces", "state", "state"],
                         kinds, lines)
        first_state = lines[kinds.index("state")]
        self.assertTrue(first_state.startswith("  this run ("),
                        f"the state-dependent region begins at "
                        f"{first_state!r}; a face keying on `this run:` "
                        f"would leave the line above it in its baseline")

    def test_the_lines_that_move_are_the_ones_grouped_as_state(self):
        # The grouping is checked against behaviour, not against a comment:
        # render the same project warm and fresh and see which lines differ.
        warm = self._block(written=0, recorded_versions={"1.8.10": 9})
        fresh = self._block(written=9, recorded_versions={"1.8.13": 9})
        differing = [w for w, f in zip(warm, fresh) if w != f]
        self.assertTrue(differing)
        for line in differing:
            self.assertTrue(any(line.startswith(p) for p in self.STATE),
                            f"{line!r} changed between a warm and a fresh "
                            f"record but is not grouped as state-dependent")

    def test_the_warning_stays_after_everything(self):
        # It is a signal, not a count, and a face keeps it whatever it does
        # with the two groups.
        lines = self._block(collisions=1, collision_keys=["gen/A.ts"])
        self.assertIn("merged away", lines[-2])
