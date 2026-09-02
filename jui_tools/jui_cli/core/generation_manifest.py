"""Which tool version wrote each generated file, recorded per project.

A face that regenerates cannot otherwise answer "which version produced
what is on disk". After a defective 1.8.2 shipped and 1.8.3 fixed it, every
consumer was told to regenerate if their tree came from 1.8.2 — and none of
them could read that from their own files. One approximated with mtimes,
which say when a file was written and not by what; translating that into a
version needed the release lane's distribution timetable.

WHAT THIS DOES NOT ANSWER. It records which version wrote a file. It does
not say whether that version's defects reach this project — that is a
property of the layouts, measured on the input side, and it is usually the
stronger evidence. The same investigation that prompted this closed on
"zero declarations meet the condition", not on a version stamp.

WHY NOT A STAMP IN EACH FILE. A version line in every `@generated` header
puts a diff in every generated file on every release, which destroys the
attribution method those releases depend on — reading a regeneration diff
line by line and asking whether it is only the warning sites. The noise
would bury the substance. One manifest keeps the churn in one file.

WHAT "WROTE" MEANS, EXACTLY. An entry is recorded for a file this run
actually touched on disk (new, or changed content, or an advanced mtime).
Files the run did not touch keep their previous entry, including its older
version — a partial regeneration must not claim the new version for files
it never looked at. A record is trusted in a way a guess is not, so a
manifest that overstates is worse than no manifest.

The cost of that choice, stated rather than hidden: a tool that regenerates
a file, finds byte-identical content and skips the write leaves the earlier
version in place. The manifest records WRITES, not verifications, and the
success line names both numbers so a partial run is visible as one.

FRESHNESS. Every entry describes the last generation, not the present. The
file is not touched by hand-editing or by anything but a generation run, so
an entry can be arbitrarily old and still be returned as fact. It answers
"what wrote this, when it was last written" — never "is this current".
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

#: Sibling of sync-meta.json, deliberately not the same file: that one
#: records a SYNC (which toolchain copy a project holds), this one records a
#: GENERATION (which version wrote an output). A project can sync without
#: generating and generate without syncing, so one file cannot answer both.
MANIFEST_DIRNAME = ".jsonui-cli"
MANIFEST_FILENAME = "generation-manifest.json"

_COMMENT = (
    "Which jsonui-cli version last WROTE each generated file, and when. "
    "An entry appears only for a file some run has written with content "
    "different from what was there, so a partial regeneration leaves the "
    "rest at their earlier version rather than claiming the new one, and a "
    "rebuild that produces identical bytes changes nothing here at all. "
    "'summary' names the gap that follows from this: a generated file with "
    "no entry has not been written since this file started being kept — "
    "which is NOT the same as having been written by an old version, and "
    "the two cannot be told apart from here. This says what wrote a file; "
    "it does not say whether that version's defects reach this project "
    "(measure the layouts for that), and it is not evidence of freshness."
)


def real_case(path: Path) -> Path:
    """A path spelled the way the filesystem spells it.

    Case-insensitive filesystems accept — and hand back — whatever casing
    they were given, so a glob pattern's spelling can travel all the way
    into a record and only fail somewhere else, on a machine nobody ran.
    Each component is matched against the real directory entries; a
    component that is not there is kept as given, since the path may simply
    not exist yet and inventing a spelling would be worse than echoing the
    one asked for.
    """
    p = Path(path)
    if not p.is_absolute():
        return p
    fixed = Path(p.anchor)
    for part in p.relative_to(p.anchor).parts:
        try:
            entries = os.listdir(fixed)
        except OSError:
            return fixed.joinpath(*_remaining(p, fixed))
        if part in entries:
            fixed = fixed / part
            continue
        lowered = part.lower()
        match = next((e for e in entries if e.lower() == lowered), None)
        fixed = fixed / (match if match is not None else part)
    return fixed


def _remaining(full: Path, prefix: Path) -> tuple:
    try:
        return full.relative_to(prefix).parts
    except ValueError:
        return full.parts


def _migrate_key(project_root: Path, key: str) -> str:
    """An existing key, re-spelled the way the current normaliser spells it.

    Only the spelling moves. A key naming a file that is genuinely absent
    normalises to itself (real_case keeps components it cannot find), so it
    still fails the presence test and is still dropped.
    """
    root = Path(project_root)
    candidate = real_case(root / key)
    try:
        return candidate.relative_to(real_case(root)).as_posix()
    except ValueError:
        return key


def manifest_path(project_root: Path) -> Path:
    return Path(project_root) / MANIFEST_DIRNAME / MANIFEST_FILENAME


@dataclass(frozen=True)
class FileState:
    """What decides "written" from "left alone": the content, and only that.

    An earlier version paired the hash with an mtime and treated either
    moving as a write. Generators rewrite unconditionally, so every build
    touched every timestamp and the manifest re-stamped files whose bytes
    had not changed — measured at 89 entries moving between two consecutive
    builds with nothing edited in between, and 448 lines of churn on one
    project, which is why that project stopped tracking the file at all. A
    record that changes when nothing changed is noise, and noise is what
    gets ignored.
    """

    sha256: str


@dataclass
class GenerationRun:
    """Snapshot a tree, run a generator, record only what moved."""

    project_root: Path
    version: str
    #: Paths considered, keyed relative to project_root.
    before: dict[str, FileState] = field(default_factory=dict)

    def observe(self, paths) -> None:
        """Record the pre-run state of every path a run could write."""
        for path in paths:
            state = _state_of(path)
            if state is not None:
                self.before[self._key(path)] = state

    def written(self, paths, known: set | None = None) -> list[str]:
        """The keys this run records or corrects in the manifest.

        NOT the files it wrote to disk, and the difference is not small:
        the second rule below admits files whose bytes never moved, so this
        count runs above the writes on a first build and below them on a
        later one. The line reporting it says "recorded/updated" for that
        reason; the name here means written to the RECORD.

        Two ways in, and the second one is what makes the record able to
        exist at all:

        CONTENT CHANGED. The run produced different bytes than were there.

        NO ENTRY YET. The file has no record of who wrote it, so this run —
        which just produced exactly these bytes — is the honest answer, and
        the only one available. Without this an idempotent build records
        nothing forever: a project whose generated output is stable never
        gets a first entry, and `0 of 223` with an empty file is what
        it reports on every build. Measured downstream: a run that wrote 83
        files reported 0, because every one came back byte-identical.

        This rule is also what reaches the outputs no rule based on writing
        could. Generated DTOs are written through a writer that SKIPS the
        write when content matches, while generated views are rewritten
        unconditionally by the platform tools — so a project's manifest held
        210 view entries and zero DTO entries, under both the timestamp rule
        and the content rule, for the same reason: nobody ever wrote them
        again. An asymmetry in how outputs are written should not decide
        which of them the record can describe.

        Once a file has an entry, an unchanged rebuild leaves it alone, so
        the churn this replaced does not return. The two rules converge:
        the first build fills the record, later ones only correct it.
        """
        known = known if known is not None else set()
        touched = []
        for path in paths:
            key = self._key(path)
            after = _state_of(path)
            if after is None:
                # Generated last time, absent now: the run did not write it,
                # and neither does the manifest claim it did. The stale entry
                # is dropped by `save` rather than left naming a missing file.
                continue
            prior = self.before.get(key)
            if prior is None or prior.sha256 != after.sha256 or key not in known:
                touched.append(key)
        return touched

    def _key(self, path) -> str:
        """The project-relative path, spelled the way the disk spells it.

        NOT `Path.resolve()`. That normalises per platform — on macOS it
        keeps whatever casing it was handed, so the manifest recorded one
        spelling while the file walk produced another, and the two sides
        disagreed about the same file. Measured on two projects, in
        opposite directions: one had `src/generated` in the manifest and
        `src/Generated` from the walk, the other the reverse. Either way a
        consumer asking about a real path got "not recorded", forever, and
        the check looked like it ran. On a case-sensitive filesystem not one
        key would have resolved.

        Disk spelling is canonical, and every path entering the manifest
        goes through this one function so the two sides cannot drift again.
        """
        p = real_case(Path(path))
        root = real_case(Path(self.project_root))
        try:
            return p.relative_to(root).as_posix()
        except ValueError:
            return p.as_posix()


def _state_of(path) -> FileState | None:
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError:
        return None
    return FileState(hashlib.sha256(data).hexdigest())


def load(project_root: Path) -> dict:
    path = manifest_path(project_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_migrated(project_root: Path) -> dict:
    """The recorded entries, keyed the way the current normaliser spells them.

    Everything that needs the existing keys goes through here. The caller
    that decides which files are new, and the save that prunes and rewrites,
    were reading the same file and building keys from different spellings:
    the caller took them raw, so every entry whose spelling the normaliser
    changes looked like a file with no record. The bootstrap rule then fired
    on all of them and re-stamped 327 entries with the current version —
    counts intact, dropped zero, and the versions gone, which is the one
    thing this record exists to keep.

    Two call sites normalising separately is what let those spellings
    diverge, so there is one function and both use it.
    """
    files = dict(load(project_root).get("files") or {})
    migrated: dict = {}
    for key, value in files.items():
        migrated.setdefault(_migrate_key(project_root, key), value)
    return migrated


def save(
    project_root: Path,
    version: str,
    written_keys: list[str],
    *,
    present_keys: list[str] | None = None,
    generated_by: str = "jui build",
    scope: dict | None = None,
) -> dict:
    """Merge this run's writes into the manifest and write it back.

    `present_keys`, when given, is every generated file the run could see;
    entries naming a file that is no longer there are dropped, so the
    manifest does not keep asserting a version for something absent.
    """
    files = load_migrated(project_root)

    # Migration happens in load_migrated, BEFORE the prune below. The prune
    # drops any key not currently present, and it compares strings — so when
    # the spelling of a key changed, every entry written under the old
    # spelling looked like a file that no longer exists. One project lost
    # 198 records in a single build that way: the same files, the same disk,
    # a different spelling.
    #
    # Re-running each stored key through the current normaliser is what
    # separates "spelled differently" from "gone". An entry that maps onto a
    # present file keeps ITS OWN version — which is the whole point, because
    # this record exists to find files written by a particular release, and
    # a restore that re-stamps them with today's version answers that
    # question wrongly while looking repaired.
    dropped: list[str] = []
    if present_keys is not None:
        present = set(present_keys)
        dropped = sorted(k for k in files if k not in present)
        files = {k: v for k, v in files.items() if k in present}

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for key in written_keys:
        files[key] = {"version": version, "generatedAt": stamp, "generatedBy": generated_by}

    manifest = {
        "_comment": _COMMENT,
        "schemaVersion": 1,
        # The denominator, inside the file. Without it a reader compares the
        # entry count against the number in the build log, finds a gap of a
        # hundred-odd, and reads it as records that went missing — measured:
        # a run reporting "112 of 233" wrote a file holding 112 entries, and
        # nothing in the file said the other 121 were simply never written.
        "summary": {
            "tracked": len(present_keys) if present_keys is not None else len(files),
            "recorded": len(files),
            "unrecorded": (
                max(len(present_keys) - len(files), 0)
                if present_keys is not None else 0
            ),
            # Which directories `tracked` came from. A bare total is a number
            # a reader cannot reconcile against their own tree, and one who
            # tried got 127 by hand against a reported 223 with no way to
            # find the difference.
            "trackedByDirectory": scope or {},
            # Entries this run removed because the file is no longer there.
            # A run that drops records while printing "untouched files keep
            # the version that last wrote them" is describing the opposite
            # of what it did.
            "dropped": len(dropped),
            "droppedKeys": dropped[:20],
        },
        "files": {k: files[k] for k in sorted(files)},
    }
    path = manifest_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def coverage_line(
    written: int, total: int, version: str, distributed: int | None = None,
    dropped: int = 0,
) -> str:
    """`generation manifest: recorded/updated 3 of 44 tracked file(s)`.

    Both numbers, because a partial run is the normal case and a line that
    reported only the numerator would read the same as a full one.

    THE VERB IS PART OF THE CLAIM. This said "wrote", and the number it
    reports is not a count of files written — it is a count of entries this
    run recorded or corrected. Measured on one project, the same word
    counted two different things and matched the writes in neither
    direction: `wrote 223 of 223` on a run that wrote 83 files (the rest
    were entries being bootstrapped), and `wrote 0 of 223` on a --clean run
    that also wrote 83 (nothing on record had changed). Naming the
    denominator, which is what this line was added for, does not help when
    the verb is wrong about what is being counted.

    "tracked" is load-bearing. The denominator is what the manifest speaks
    about, which is not every file a build distributes — a reader took the
    larger number for the manifest's scope and concluded that hundreds of
    files had gone unrecorded. When the distributed count is known it is
    reported beside it, as a different number with its own name, rather
    than left for someone to infer.

    The limitation rides along too: a reader who takes this for "this
    project is on 3.0.0" has read it as freshness, which it is not.
    """
    line = (
        f"generation manifest: recorded/updated {written} of {total} "
        f"tracked generated file(s) as {version}"
    )
    if distributed is not None and distributed != total:
        line += f" ({distributed} file(s) distributed in total)"
    if dropped:
        # Saying "untouched files keep their version" while removing records
        # describes the opposite of what happened.
        line += f", dropped {dropped} entr(y/ies) whose file is gone"
    # The ending used to read "records writes, not currency". It was there
    # to deny freshness, and a reader took it as confirmation that the
    # number counts writes, which the number does not do. The denial it
    # exists to make is kept; the word that made the other claim is gone.
    return line + (
        " — untouched files keep the version that last generated them "
        "(a version stamp, not a freshness check)"
    )
