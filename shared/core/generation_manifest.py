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
    "Which jsonui-cli version last WROTE each generated file, and when. A "
    "file gets an entry when a run produces content different from what "
    "was there, and also the first time it is seen with no entry at all — "
    "without the second rule a project whose generation is idempotent "
    "would never get a record. So a partial regeneration leaves the rest "
    "at their earlier version rather than claiming the new one, and once a "
    "file has an entry, a rebuild producing identical bytes changes "
    "nothing here. "
    "'summary' names the gap that follows: a generated file with no entry "
    "has not been written since this file started being kept — which is "
    "NOT the same as having been written by an old version, and the two "
    "cannot be told apart from here. "
    "There is a second gap, and unlike the first it reads as an answer "
    "rather than a blank: an entry whose record was lost and then re-made "
    "by that first-sighting rule carries the version of the run that "
    "re-made it, not the version that generated the file. Two projects "
    "hold 488 such entries between them, from a release that pruned "
    "records whose key spelling had changed. Nothing here marks them, and "
    "restoring the old records was declined because their contents could "
    "not be shown to match what that version wrote — so the number in "
    "those entries is a claim this file cannot support. "
    "This says what wrote a file; it does not say whether that version's "
    "defects reach this project (measure the layouts for that), and it is "
    "not evidence of freshness. "
    "'tracked' HERE MEANS TRACKED BY THIS MANIFEST, NOT BY GIT. "
    "'summary.tracked' and 'summary.trackedByDirectory' count generated "
    "files this record knows about; git is not consulted for either. The "
    "only git-sense number in this file is "
    "'summary.run.gitTrackedDirectories', which is spelled differently for "
    "that reason. The two senses can return the SAME count on a project "
    "where every generated file happens to be committed — measured on one "
    "face at 220 and 220 — so a reader who takes 'tracked' for git gets a "
    "true sentence there and no signal that the reading is wrong. That "
    "face's own copy of this file was untracked while it said tracked: "
    "220. "
    "'summary.run' is the record of the last 'jsonui-doc generate html' run "
    "— what it found and wrote outside its output — and names its writer and "
    "time inside it ('recordedBy', 'recordedAt'). 'jui build' carries that "
    "block forward unchanged, so it can be older than the entries around it; "
    "only a doc run replaces it, and a doc run that found nothing removes it. "
    "Inside 'summary.run' a zero is explicit — 'leftovers: 0', 'outsideOutput.directories: []' — meaning counted and found none; a key "
    "that is missing means the record predates that key, never zero."
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


class NotObserved(RuntimeError):
    """A claim was asked of a run that never looked at the tree.

    `0 tracked` and `nothing was scanned` are different facts, and every
    ticket in the record series since 1.8.8 is one of them wearing the
    other's number. A ledger that was never handed a scan refuses to
    answer rather than answering 0.
    """


@dataclass
class GenerationRun:
    """THE RUN LEDGER: one value, built once per run, that every claim is
    derived from.

    Before 2026-09-11 this held only the pre-run snapshot, and each claim
    the record made — `tracked`, `recorded`, `dropped`, `collisions`, the
    closing lines — was a scalar computed at its own print site and passed
    by hand: `coverage_line` took eleven numbers, `jui build` read three of
    them back out of the manifest it had just written, and `jsonui-doc`
    assembled seventeen `facts[...]` entries by hand. Observation and claim
    were different variables, so a claim never carried WHICH tree, WHICH
    roots, or HOW MANY directories it stood on. That is the mechanism
    behind about sixty trains and thirty tickets of "the record said more
    than it saw" (1.8.68: six tickets, 1.8.69: eight, 1.8.70: eight).

    Now the ledger owns the observation AND the vocabulary. Callers hand it
    COLLECTIONS at the point of observation (`observe`, `written`,
    `note_distributed`, `record_*`); counts, truncated lists and notes are
    derived here, once, in `claims()` and `run_facts()`. `save` and
    `coverage_line` take the ledger and nothing else — there is no number
    to forget to pass, and no second definition of a quantity's name.

    "Not observed" is a value, not a zero: `observed is None` means no scan
    ran, and a claim asked of such a ledger raises `NotObserved`.
    """

    project_root: Path
    version: str
    #: Paths considered, keyed relative to project_root.
    before: dict[str, FileState] = field(default_factory=dict)

    # --- what the scan covered ------------------------------------------
    #: Project-relative roots the scan walked. None = the caller declared
    #: nothing (the record says "not declared"); `()` = declared and empty,
    #: under which every present key stands outside the scan. Two states
    #: that used to share one value — the ticket's 0 ≠ not-observed, on the
    #: directory axis (found by triage's probe, 2026-09-11).
    roots: tuple | None = None
    #: How many paths `observe` was handed. None = observe never ran.
    observed: int | None = None

    # --- what the run found afterwards ---------------------------------
    present: list | None = None       # keys present after the run
    written_keys: list | None = None  # keys this run records or corrects
    absent_after: list = field(default_factory=list)
    #: Present keys not under any declared root (empty when roots are ()).
    outside_roots: list = field(default_factory=list)
    #: Files the build distributed to platforms; None = not counted.
    distributed: int | None = None

    # --- what `save` learned against the previous record ---------------
    dropped: list | None = None
    untracked: list | None = None
    dropped_versions: dict | None = None
    untracked_versions: dict | None = None
    collisions: dict | None = None
    recorded_versions: dict | None = None

    #: Run facts, only ever set through `record_*`. None = this producer
    #: has no run facts (jui build); a dict = it does (jsonui-doc).
    _facts: dict | None = None

    # ------------------------------------------------------------------
    # observation
    # ------------------------------------------------------------------
    def observe(self, paths, *, roots=None) -> None:
        """Record the pre-run state of every path a run could write."""
        paths = list(paths)
        self.roots = None if roots is None else tuple(self._key(r) for r in roots)
        self.observed = len(paths)
        for path in paths:
            state = _state_of(path)
            if state is not None:
                self.before[self._key(path)] = state

    def observe_written(self, keys, *, roots=None) -> None:
        """A producer that has no before/after — it knows what it wrote.

        `jsonui-doc generate html` registers each page as it is written;
        the pages are its observation. Recorded as both the scan and the
        writes, with `present` left None so `tracked` falls back to the
        record's own size, as it always has for this producer.
        """
        # THROUGH `_key`, like every other path that enters the manifest. The
        # first cut kept the caller's spelling verbatim, so a key whose case
        # differed from the disk (`DOCS/y.html`) would have been recorded as
        # given — the drift `_key` exists to prevent, bypassed by one of the
        # two producers. Found by triage's probe before it shipped.
        keys = sorted(self._key(Path(self.project_root) / k) for k in keys)
        self.roots = None if roots is None else tuple(self._key(r) for r in roots)
        self.observed = len(keys)
        self.written_keys = keys
        self._refuse_outside_roots(keys)

    def written(self, paths, known: set | None = None,
                bootstrap: bool = True) -> list[str]:
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

        `bootstrap=False` drops the second rule, for a run that did not
        finish. Its warrant is "this run produced exactly these bytes",
        which a build that stopped part-way cannot claim — and the rule
        does not go quiet on its own there: measured, a run that wrote
        nothing at all still claims every unrecorded file, because the
        rule fires on the absence of a record, not on having written.
        A halted run has one kind of direct evidence, a content change
        inside its window, so that is all it may record.

        Stored on the ledger as well as returned: `present`, `written_keys`
        and `absent_after` are what `save` and `coverage_line` read.
        """
        if self.observed is None:
            raise NotObserved("written() asked of a run that never observed the tree")
        known = known if known is not None else set()
        touched = []
        present = []
        absent = []
        for path in paths:
            key = self._key(path)
            after = _state_of(path)
            if after is None:
                # Generated last time, absent now: the run did not write it,
                # and neither does the manifest claim it did. The stale entry
                # is dropped by `save` rather than left naming a missing file.
                absent.append(key)
                continue
            present.append(key)
            prior = self.before.get(key)
            changed = prior is None or prior.sha256 != after.sha256
            if changed or (bootstrap and key not in known):
                touched.append(key)
        # Recorded, not refused: `jui build`'s scan is a union of enumerations
        # (collected targets, view targets, generated dirs), so a present key
        # outside the DIRECTORIES it walked is normal. The count says how
        # much of the claim stands outside the declared scan — a reader can
        # see it instead of inferring it. The doc generator's scope is a real
        # boundary, and `observe_written` refuses there.
        self.outside_roots = [k for k in present
                              if not self._under_roots(Path(self.project_root) / k)]
        self.present = present
        self.written_keys = touched
        self.absent_after = absent
        return touched

    def note_distributed(self, paths) -> None:
        """Files placed under the platforms' layout dirs. None = not counted."""
        self.distributed = None if paths is None else sum(1 for _ in paths)

    # ------------------------------------------------------------------
    # run facts (the doc generator's observations). Collections in,
    # counts out — the vocabulary below is the only place these names live.
    # ------------------------------------------------------------------
    def _facts_dict(self) -> dict:
        if self._facts is None:
            self._facts = {}
        return self._facts

    def record_leftovers(self, stale, stale_outside, *, walked_dirs,
                         colliding_sources, referrers: dict) -> None:
        """Pages found that this run did not write.

        `stale`: under -o. `stale_outside`: (path, copies) pairs in the
        directories the run wrote outside -o; only those under this
        ledger's roots are listed, the rest are counted as `Elsewhere` so a
        scoped 0 cannot read as "the scan found nothing". `walked_dirs` is
        the directories that scan walked; its length is the denominator —
        a 0 with a 0 denominator is not the same answer as a 0 with one.
        Collections in, counts out: nothing here is handed a number.
        """
        f = self._facts_dict()
        stale = list(stale)
        f["leftovers"] = len(stale)
        f["leftoverPaths"] = [str(p) for p in stale[:20]]
        if len(stale) > 20:
            f["leftoverPathsNote"] = f"first 20 of {len(stale)}"
        mine = [(p, copies) for p, copies in stale_outside
                if self._under_roots(p)]
        f["leftoversOutside"] = len(mine)
        f["leftoversOutsideElsewhere"] = len(list(stale_outside)) - len(mine)
        f["leftoversOutsideScanned"] = len(list(walked_dirs))
        f["collidingSourceNames"] = list(colliding_sources)
        f["leftoverOutsidePaths"] = [str(p) for p, _c in mine[:20]]
        f["leftoverOutsideSiteCopies"] = [str(c) for _p, copies in mine[:20] for c in copies]
        f["leftoverOutsideReferencedBy"] = {
            str(p): len(referrers.get(Path(p).resolve(), [])) for p, _c in mine[:20]}
        if len(mine) > 20:
            f["leftoverOutsidePathsNote"] = f"first 20 of {len(mine)}"

    def record_outside_output(self, block: dict | None) -> None:
        if block:
            self._facts_dict()["outsideOutput"] = dict(block)

    def record_document_slots(self, *, paths: int, declarations: int,
                              shared_keys) -> None:
        """The document-slot facts, derived HERE from the collections.

        The producer hands over what it observed — how many output paths,
        how many declarations, and the full list of paths more than one
        declaration resolved to — and the ledger derives the count, the
        first-20 listing and the "first 20 of N" note. Until 1.8.73 the
        producer truncated the list and wrote the note itself, which was the
        last `facts[...]`-shaped line left after the fold: a claim assembled
        beside the ledger instead of by it (closure of the record-claims
        ticket, 2026-09-11). An empty list is recorded as an explicit zero;
        "the pass did not run" is the caller's to say by not calling this.
        """
        keys = sorted(shared_keys)
        slots = {
            "paths": int(paths),
            "declarations": int(declarations),
            "sharedPaths": len(keys),
            "sharedPathKeys": keys[:20],
        }
        if len(keys) > 20:
            slots["sharedPathKeysNote"] = f"first 20 of {len(keys)}"
        self._facts_dict()["documentSlots"] = slots

    def record_apps(self, apps) -> None:
        self._facts_dict()["apps"] = list(apps)

    def record_time(self, recorded_at: str) -> None:
        self._facts_dict()["recordedAt"] = recorded_at

    def record_manifest_visibility(self, *, tracked, ignored) -> None:
        f = self._facts_dict()
        f["manifestIsGitTracked"] = tracked
        f["manifestIsGitIgnored"] = ignored

    def run_facts(self) -> dict | None:
        """The run block, or None when this producer records none."""
        return None if self._facts is None else dict(self._facts)

    # ------------------------------------------------------------------
    # claims — derived, never passed
    # ------------------------------------------------------------------
    def claims(self) -> dict:
        """Every number the record and the closing lines may state.

        ONE derivation. `save` writes `summary` from this and
        `coverage_line` prints from this, so a quantity cannot have two
        definitions, and a caller cannot hand either of them a number.
        Asked of a ledger that never observed, it refuses.
        """
        if self.observed is None:
            raise NotObserved("claims() asked of a run that never observed the tree")
        written = self.written_keys or []
        present = self.present
        recorded = self.recorded_count if self.recorded_count is not None else len(written)
        tracked = len(present) if present is not None else recorded
        dropped = self.dropped or []
        untracked = self.untracked or []
        collisions = self.collisions or {}
        return {
            "scan": {
                "roots": "not declared" if self.roots is None else list(self.roots),
                "observed": self.observed,
                "outsideDeclaredRoots": len(self.outside_roots),
            },
            "summary": {
                "tracked": tracked,
                "recorded": recorded,
                "unrecorded": max(tracked - recorded, 0) if present is not None else 0,
                "trackedByDirectory": tracked_scope(
                    present if present is not None else (self.recorded_keys or written)),
                "dropped": len(dropped),
                "droppedKeys": list(dropped[:20]),
                "untracked": len(untracked),
                "untrackedKeys": list(untracked[:20]),
                "droppedVersions": dict(sorted((self.dropped_versions or {}).items())),
                "untrackedVersions": dict(sorted((self.untracked_versions or {}).items())),
                "collisions": sum(collisions.values()),
                "collisionKeys": sorted(collisions)[:20],
            },
            "run": {
                "version": self.version,
                "written": len(written),
                "distributed": self.distributed,
                "recordedVersions": dict(self.recorded_versions or {}),
            },
        }

    #: Set by `save`: the record's size and keys after the merge, so
    #: `recorded` is the file's own count and not a re-count elsewhere.
    recorded_count: int | None = None
    recorded_keys: list | None = None

    # ------------------------------------------------------------------
    def _under_roots(self, path) -> bool:
        """Under one of the declared roots, compared as RESOLVED paths.

        Not as key strings: a root spelled `.` would match everything, and
        a root outside the project (a split docs tree) is stored absolute
        while keys under the project are relative, so a string prefix test
        compares two spellings of the same thing and gets it wrong both
        ways. Measured 2026-09-11: every leftover counted as "mine" and
        `leftoversOutsideElsewhere` was 0 on a two-face tree.
        """
        if self.roots is None:
            return True                      # nothing declared: nothing to be outside of
        base = real_case(Path(self.project_root))
        # `..` is collapsed before the comparison; `real_case` keeps it, and
        # `docs/../evil/x.html` has `/docs` among its textual parents.
        target = real_case(Path(os.path.normpath(Path(path))))
        for r in self.roots:
            rp = Path(r)
            rp = real_case(Path(os.path.normpath(rp if rp.is_absolute() else base / rp)))
            if target == rp or rp in target.parents:
                return True
        return False

    def _refuse_outside_roots(self, keys) -> None:
        """A key outside every declared root is a claim wider than the scan."""
        if self.roots is None:
            return
        outside = [k for k in keys if not self._under_roots(Path(self.project_root) / k)]
        if outside:
            raise ValueError(
                f"{len(outside)} key(s) lie outside the declared scan roots "
                f"{list(self.roots)}: {outside[:5]} — the record would claim "
                "more than the run looked at")

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


#: The name the ticket used. Same object.
RunLedger = GenerationRun


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
    return load_migrated_with_collisions(project_root)[0]


def load_migrated_with_collisions(project_root: Path) -> tuple[dict, dict]:
    """`load_migrated`, plus how many entries each collision absorbed.

    The second value maps a canonical key to the number of records lost to
    it, because those are different numbers: three spellings of one file
    are one collided key and two lost entries. Returning both from the one
    place that merges keeps the caller from deriving either — recomputing
    "how many were there before" from a second read of the file would put
    two sources under one number.

    A collision is a silent deletion. Two records naming the same file in
    two spellings collapse into one, and `dropped` cannot report it: that
    counts what the prune removed, and this happens before the prune, in
    the merge. So the summary reads `dropped 0` while the file holds fewer
    entries than it did — the same shape as the re-stamping defect, where
    every number looked like a healthy build.

    NOT REACHABLE IN TODAY'S REAL DATA, AND MEASURED, NOT ASSUMED: across
    three downstream corpora, every generation of every recorded manifest
    normalised without collapsing (537→537, 210→210, 249→249, 198→198, and
    so on through eight generations). A smoke test on a real tree would
    therefore report "no collisions" forever and prove only that it ran.
    The coverage for this lives in synthetic fixtures with a positive
    control, and belongs there.
    """
    files = dict(load(project_root).get("files") or {})
    migrated: dict = {}
    winner: dict = {}
    collisions: dict = {}
    for key, value in files.items():
        canonical = _migrate_key(project_root, key)
        if canonical not in migrated:
            migrated[canonical] = value
            winner[canonical] = key
            continue
        collisions[canonical] = collisions.get(canonical, 0) + 1
        if _supersedes(key, value, winner[canonical], migrated[canonical],
                       canonical):
            migrated[canonical] = value
            winner[canonical] = key
    return migrated, collisions


def _supersedes(new_key, new_value, old_key, old_value, canonical) -> bool:
    """Of two records for one file, which one to keep.

    There is one entry per file and no way to hold both, so something is
    lost either way; what must not happen is losing it by dict order, which
    is the manifest's own byte order and means nothing. The stored
    timestamp decides — these are `%Y-%m-%dT%H:%M:%SZ`, so string order is
    time order, and a missing one sorts oldest. When that cannot separate
    them, the entry already spelled the canonical way is the one a run
    using the current normaliser wrote, so it wins.
    """
    new_at = (new_value or {}).get("generatedAt") or ""
    old_at = (old_value or {}).get("generatedAt") or ""
    if new_at != old_at:
        return new_at > old_at
    return new_key == canonical and old_key != canonical


def save(ledger: GenerationRun, *, generated_by: str = "jui build",
         clear_run_facts: bool = False) -> dict:
    """Merge this run's writes into the manifest and write it back.

    TAKES THE LEDGER AND NOTHING ELSE. Before 2026-09-11 this took the
    written keys, the present keys, a scope and a run-facts dict as four
    separate arguments, and every one of them was a place to hand the
    record a number the run had not observed. `jui build` passed a scope
    it had computed with the same function this file exports; `jsonui-doc`
    passed seventeen hand-assembled facts. Now the keys come from the
    ledger's own `written()` / `observe_written()`, the breakdown is
    derived from the same keys `tracked` is, and the run block is whatever
    `record_*` put on the ledger.

    What this function learns against the PREVIOUS record — entries whose
    file is gone (`dropped`), entries that left the tracked set with the
    file still there (`untracked`), spellings that normalised onto one key
    (`collisions`), and which versions the surviving entries carry — is
    written back onto the ledger, so `coverage_line` reads it from the
    same place `summary` was written from, instead of re-reading the JSON
    this function just wrote (which is what `jui build` did).

    Run facts: None on the ledger means this producer has none and the
    previous producer's block is CARRIED FORWARD (dropping it made "no
    outside writes" and "no record" the same absence — measured 2026-09-10,
    a spec-only commit deleted 43 lines of manifest). A dict, even an empty
    one, is this run's own finding and replaces it. `clear_run_facts=True`
    is the explicit way to say "found nothing" from a producer that has no
    `record_*` calls.
    """
    if ledger.observed is None:
        raise NotObserved("save() asked of a run that never observed the tree")
    project_root = ledger.project_root
    version = ledger.version
    written_keys = list(ledger.written_keys or [])
    present_keys = ledger.present
    run_facts = {} if clear_run_facts else ledger.run_facts()

    files, collisions = load_migrated_with_collisions(project_root)
    # The previous writer's run record, kept when this caller has none.
    carried_run = None
    if run_facts is None:
        carried_run = (load(project_root).get("summary") or {}).get("run")

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
    #
    # TWO REASONS AN ENTRY LEAVES, AND THEY ARE NOT THE SAME NEWS. The prune
    # removes every key the current scan did not return, and this reported
    # all of them as "whose file is gone". Once the scan could also shrink,
    # entries left with their files sitting right there, and the line said
    # the build had deleted 231 of them. The file itself is the
    # discriminator, so it is asked rather than assumed.
    dropped: list[str] = []
    untracked: list[str] = []
    dropped_versions: dict = {}
    untracked_versions: dict = {}
    if present_keys is not None:
        present = set(present_keys)
        for key in sorted(k for k in files if k not in present):
            entry = files.get(key) or {}
            name = entry.get("version") or "unknown"
            if (Path(project_root) / key).exists():
                untracked.append(key)
                untracked_versions[name] = untracked_versions.get(name, 0) + 1
            else:
                dropped.append(key)
                dropped_versions[name] = dropped_versions.get(name, 0) + 1
        files = {k: v for k, v in files.items() if k in present}

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for key in written_keys:
        files[key] = {"version": version, "generatedAt": stamp, "generatedBy": generated_by}

    # Back onto the ledger — the only place these quantities are defined.
    ledger.dropped = dropped
    ledger.untracked = untracked
    ledger.dropped_versions = dropped_versions
    ledger.untracked_versions = untracked_versions
    ledger.collisions = dict(collisions)
    ledger.recorded_count = len(files)
    ledger.recorded_keys = sorted(files)
    versions: dict = {}
    for entry in files.values():
        name = (entry.get("version") if isinstance(entry, dict) else None) or "unknown"
        versions[name] = versions.get(name, 0) + 1
    ledger.recorded_versions = versions

    claims = ledger.claims()
    manifest = {
        "_comment": _COMMENT,
        "schemaVersion": 1,
        # The denominator, inside the file. Without it a reader compares the
        # entry count against the number in the build log, finds a gap of a
        # hundred-odd, and reads it as records that went missing.
        "summary": dict(claims["summary"]),
        "files": {k: files[k] for k in sorted(files)},
    }
    # What the scan covered, in the record itself. "not declared" is a
    # value: a reader can tell an undeclared scope from an empty one.
    manifest["summary"]["scan"] = claims["scan"]
    # Three states, none of them silence: a dict with facts is this run's
    # block; an EMPTY dict is this run saying it found nothing (no block,
    # and the previous one is not carried); None is a producer with no facts
    # of its own, whose predecessor's block is carried forward.
    if run_facts:
        run = dict(run_facts)
        run.setdefault("recordedBy", generated_by)
        run.setdefault("recordedAt", stamp)
        manifest["summary"]["run"] = run
    elif run_facts is None and carried_run:
        run = dict(carried_run)
        # A block written before the stamp existed (1.8.66's doc run) carries
        # no recordedBy, and a reader who takes that absence as "no doc run"
        # is wrong twice. It is named once, as what it is.
        run.setdefault("recordedBy", "an earlier release (unstamped, before 1.8.67)")
        manifest["summary"]["run"] = run
    # A list silently cut at 20 reads as the whole list. Said only when it
    # applies, so the common case stays quiet.
    for field_name, total in (("droppedKeys", len(dropped)),
                              ("untrackedKeys", len(untracked)),
                              ("collisionKeys", len(collisions))):
        if total > 20:
            manifest["summary"][field_name + "Note"] = f"first 20 of {total}"
    path = manifest_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def tracked_scope(keys) -> dict:
    """Per top-level directory, how many of *keys* live there.

    The breakdown `summary.trackedByDirectory` carries. `tracked: 223` on its
    own is a number a reader cannot reconcile with their own tree, and one who
    tried got 127 by hand against a reported 223 with no way to find the
    difference; the breakdown says which directories the total came from, so a
    disagreement points at a place. One rule, here, for every producer — it
    lived in `jui build` alone, and the second producer had no breakdown to
    pass and passed none.
    """
    scope: dict[str, int] = {}
    for key in keys:
        head = key.split("/", 1)[0] if "/" in key else "."
        scope[head] = scope.get(head, 0) + 1
    return dict(sorted(scope.items(), key=lambda kv: (-kv[1], kv[0])))


def coverage_line(ledger: GenerationRun) -> str:
    """One line per subject, one population, one number — all from the ledger.

    Eleven scalar parameters used to arrive here, three of them read back
    out of the manifest `save` had just written. Every number below is now
    `ledger.claims()`; nothing can be passed, so nothing can be passed
    wrong, and a ledger that never observed prints NOT OBSERVED instead of
    the 0 that "no scan" and "no files" used to share.

    ```
    generation manifest: 492 tracked generated file(s)      # reproduces
      distributed to platforms: 1042 file(s)                # reproduces
      this run (jui 1.8.13): recorded/updated 0             # state
      recorded versions: 294 at 1.8.10, 198 at 1.8.7 — ...  # state
    ```

    ORDERED BY WHETHER A FRESH CLONE REPRODUCES IT, not by subject. The
    first two follow from the project and come out the same for anyone who
    clones and builds. The last two depend on what the record already held,
    and a face that gitignores the manifest gets different values from a
    warm tree and a fresh one: measured on the same tree at the same tool
    version, `9 at 1.8.10` warm and `9 at 1.8.13` after deleting the
    record, because the first-sighting rule stamps everything with the
    running version.

    That is the failure the split into two lines was meant to end, and it
    came back here — `recorded versions` was put with the project's facts
    because it describes the record rather than the run, which is true and
    is not the property that matters to a baseline. Grouping by subject
    made the block readable; grouping by reproducibility is what lets a
    face keep one region and replace the other.

    THE RULE IS THE POINT, not the wording. Every misreading this line has
    produced came from two numbers, or a number and a version, sharing a
    clause. `wrote N of M as V` was read as V describing M once N moved to
    its own line. `492 tracked (1042 distributed)` was read as "492 of
    1042", which are different populations. Three faces read the head alone
    and took the running version for the version the entries carry — one
    of them wrote that into its own ledger as an independent fact and
    committed on it, before anyone had said anything about this line.

    Patching the wording did not hold: the docstring records two earlier
    repairs, both made by appending a denial to the end, and the head kept
    being read the same way. A denial at the end cannot reach a reading
    formed at the start.

    So the version now appears once, on the line about the run it belongs
    to, and nothing else shares a line with a number that is not its own.
    What the entries actually carry is printed instead of left to be
    inferred — it was in no output at all before, so a reader wanting it
    had to parse the JSON.

    EVERY LINE IS PRINTED, ALWAYS. A line that appears only when its number
    is interesting makes its absence carry the opposite claim: no
    `recorded versions` line would say "they are all the same", and no
    `distributed` line would say "none were". Both were proposed and both
    are refused for the same reason the rest of this file refuses silence
    as a value.

    Parsers are better off, not worse: each line has a stable prefix, so
    the number can be found by it rather than by matching around
    neighbouring words.
    """
    if ledger.observed is None:
        return ("generation manifest: NOT OBSERVED — no scan ran, so this run "
                "makes no claim about the tree")
    c = ledger.claims()
    s, r = c["summary"], c["run"]
    lines = [f"generation manifest: {s['tracked']} tracked generated file(s)"]

    # "not counted" rather than nothing, and 0 rather than "not counted".
    # The count returned None for both "the walk failed" and "there were
    # none", and the line then omitted itself for both — plus for the case
    # where it equalled `tracked`. Three states, one silence, and a lane
    # reading its own output took the absence for a zero.
    if r["distributed"] is None:
        lines.append("  distributed to platforms: not counted")
    else:
        lines.append(f"  distributed to platforms: {r['distributed']} file(s)")

    run = f"  this run (jui {r['version']}): recorded/updated {r['written']}"
    if s["dropped"]:
        # Stays on this line: a dropped entry means a generated file was
        # deleted, and those are tracked, so a diff shows it.
        run += (f", dropped {s['dropped']} entr(y/ies) whose file is gone"
                f"{_left_at(s['droppedVersions'])}")
    if s["untracked"]:
        # Deliberately not the same words. Reported as a drop, this reads
        # as the build having deleted them, and on a face that keeps the
        # manifest in git that explanation goes into the commit message.
        run += (f", released {s['untracked']} entr(y/ies) that left the tracked "
                f"set{_left_at(s['untrackedVersions'])} (their files are still "
                f"there)")
    lines.append(run)

    # What the entries actually carry, printed instead of left to be
    # inferred — three faces read the running version off the head and
    # took it for this.
    lines.append(
        f"  recorded versions: {_versions_phrase(r['recordedVersions'])}"
        " — the version of the run that stamped each entry, not proof of"
        " what generated the file"
    )

    if s["collisions"]:
        lines.extend(_collision_warning(s["collisions"], s["collisionKeys"]))
    return "\n".join(lines)


def _left_at(versions) -> str:
    """` — 215 at 1.8.12, 16 at 1.8.10`, or nothing when unknown.

    The quantity the two lines share. Without it, a version disappearing
    from `recorded versions` has no explanation anywhere in the block: the
    count of what left is on one line, the tally of what remains is on
    another, and the join between them — which versions left — is on
    neither. Reported by one face, which had to compute it separately to
    read its own build output.

    Not a denial appended to a line, which this file has tried twice and
    which does not reach a reading already formed. A missing number.
    """
    if not versions:
        return ""
    ordered = sorted(dict(versions).items(), key=lambda kv: (-kv[1], kv[0]))
    return " — " + ", ".join(f"{n} at {name}" for name, n in ordered)


def _versions_phrase(recorded_versions) -> str:
    """`294 at 1.8.10, 198 at 1.8.7`, or what to say when there are none.

    Ordered by count and then by version so two runs over the same record
    render identically; a baseline comparing this line needs that.
    """
    if not recorded_versions:
        return "none recorded yet"
    counts = dict(recorded_versions)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]),
                     reverse=False)
    return ", ".join(f"{count} at {name}" for name, count in ordered)


def _collision_warning(collisions: int, keys) -> list[str]:
    """The one loss here that nothing else would surface.

    ON ITS OWN LINE, NOT INSIDE THE RUN LINE. A dropped entry corresponds
    to a deleted generated file, and those are tracked, so a reader has a
    diff to find it in. A collision has no such shadow: two records fold
    into one, the file simply holds fewer entries, and in a diff that looks
    like a key being removed — indistinguishable from a drop, and nobody is
    watching for either. Counted across the seven faces that keep a
    manifest, none has a check that would catch it, including the four that
    track the file: tracking gives you the ability to look afterwards, and
    looking afterwards only ever happens on the runs where nothing went
    wrong.

    It also cannot ride along inside the run line, because the baselines
    that read this output are moving to replacing that line's values while
    keeping the line — so a count folded into it would be replaced along
    with the rest and never differ anywhere.

    NOT AN ERROR. The build is fine and stopping it would help nobody; the
    point is that the loss cannot pass unread. Same call as leaving
    `verify`'s exit code alone when it started naming its denominator.

    Exposure is zero today: no collision exists in any recorded generation
    of any corpus, and a downstream check of 234 entries found no two keys
    that fold together. A line nobody has seen is a line nobody has
    proof-read, which is why a test renders this one and asserts on the
    text a reader would actually get.
    """
    shown = list(keys)[:5]
    more = len(list(keys)) - len(shown)
    named = ", ".join(shown) if shown else "(keys not reported)"
    if more > 0:
        named += f", +{more} more"
    # Indented to sit under the run line, matching the shape the faces
    # were told to keep out of their baselines.
    return [
        f"  ⚠️  merged away {collisions} entr(y/ies): records that now "
        f"spell the same key were combined — {named}",
        "      the version each of them named is gone — a silent loss that "
        "`dropped` does not count and nothing else reports.",
    ]
