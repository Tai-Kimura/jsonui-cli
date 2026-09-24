#!/bin/zsh
#
# Judge a tag that has been CUT BUT NOT PUSHED.
#
# 🔻 TIMING IS PART OF THE CONTRACT. Five of these checks need the tag OBJECT,
# so "get a green and then tag" is not executable. Run it after `git tag -a`
# and before `git push --atomic`.
#
# 🔻 THIS IS DELIBERATELY NOT THE ONLY TAG GATE. A second one lives in the
# triage lane and derives its expectations from `prev-main` instead of from
# the working tree. What makes the two independent is not their file paths but
# WHERE EACH GETS ITS EXPECTED VALUES — merging them, or deleting one as a
# duplicate, collapses two sources into one and the agreement of the survivors
# stops meaning anything. If this file looks redundant, that is the point.
#
# ⚠️ WHAT WAS REMOVED AND WHY. An earlier version took the branch's tree OID as
# an argument, "passed in, not re-derived here". It caught nothing: the caller
# reads it from the same repository this script reads, so the comparison was
# tautological — and it cost a false red when a 12-hex prefix was extended from
# memory to 16. `tag peels to the branch` already carries the real claim.
#
# ⚠️ WHAT IS STILL HANDED IN, AND SAYS SO. The words that must survive in the
# tag body cannot be derived from the body without circularity: derive them and
# the check moves with whatever the body says, so it is green by construction.
# They are typed by the caller, and the output labels them HAND-SUPPLIED so
# nobody reads that line as a derivation.
#
# Usage: check-tag.sh <repo> <prev-tag> <tag> <branch> <version> <words,comma> <remote> [remote-branch]
#
# <remote-branch> (default: <branch>) is the branch on <remote> that must be an
# ancestor of the tag. Pass it when the release was assembled on a worktree
# branch (rel/vX.Y.Z) that the remote has never seen: 2026-09-19 the check
# "remote branch is an ancestor" reddened three times for `origin/rel/v1.8.106`
# not existing, while the claim that matters — origin/main is behind the tag —
# was true and had to be re-run by hand. A missing ref is not a failed claim.
set -u
R=${1:?repo}; PREV=${2:?prev tag}; TAG=${3:?new tag}; BRANCH=${4:?branch}
VER=${5:?version}
MSGWORDS=${6:?comma-separated words that must survive in the tag body}
REMOTE=${7:?remote}
REMOTE_BRANCH=${8:-$BRANCH}
g() { git -C "$R" "$@"; }
pass=0; fail=0; n=0
ck() { n=$((n+1)); if [ "$2" = "$3" ]; then pass=$((pass+1)); printf '  %2d PASS %-46s %s\n' "$n" "$1" "$2"
       else fail=$((fail+1)); printf '  %2d FAIL %-46s got=%s want=%s\n' "$n" "$1" "$2" "$3"; fi; }

echo "== tag gate  repo=$R  $PREV..$TAG on $BRANCH"
echo "   words to look for are HAND-SUPPLIED, not derived: $MSGWORDS"
ck "tag object exists"            "$(g cat-file -t "$TAG" 2>/dev/null)" "tag"
ck "tag peels to $BRANCH"         "$(g rev-parse "$TAG^{}")" "$(g rev-parse "$BRANCH")"
ck "tag object != peel (annotated)" "$([ "$(g rev-parse "$TAG")" != "$(g rev-parse "$TAG^{}")" ] && echo yes)" "yes"
# The version stamp lives in `VERSION` (jsonui-cli, SwiftJsonUI) or in
# gradle.properties' `version=` (KotlinJsonUI). Read whichever the branch has,
# and say which was read: a repo with neither must fail, not pass on an empty
# string (2026-09-19: KotlinJsonUI reddened "got=v" on a VERSION it never had).
# ⚠️ `${BRANCH}` with braces: zsh reads `$BRANCH:gradle.properties` as a
# history modifier and hands git `mainadle.properties` (measured, same day).
if g cat-file -e "${BRANCH}:VERSION" 2>/dev/null; then
  STAMP=$(g show "${BRANCH}:VERSION" | tr -d '[:space:]'); STAMP_FROM=VERSION
elif g show "${BRANCH}:gradle.properties" 2>/dev/null | grep -q '^version='; then
  STAMP=$(g show "${BRANCH}:gradle.properties" | sed -n 's/^version=//p' | tr -d '[:space:]'); STAMP_FROM=gradle.properties
elif g show "${BRANCH}:jsonuitestrunner/build.gradle.kts" 2>/dev/null | grep -q 'coordinates('; then
  # The Android test driver stamps its version in the vanniktech coordinates()
  # call and nowhere else (reference: jsonui-test-runner-android, 1.15.x).
  STAMP=$(g show "${BRANCH}:jsonuitestrunner/build.gradle.kts" | sed -nE 's/.*coordinates\([^,]*,[^,]*,[[:space:]]*"([^"]+)"\).*/\1/p' | head -1); STAMP_FROM=coordinates
elif g cat-file -e "${BRANCH}:package.json" 2>/dev/null; then
  # An npm package (jsonui-mcp-server) stamps its version in package.json only;
  # `npm version` keeps package-lock.json in step. Read the top-level "version"
  # with a JSON parser, not a regex: dependencies carry "version" keys too.
  STAMP=$(g show "${BRANCH}:package.json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))'); STAMP_FROM=package.json
else
  STAMP=""; STAMP_FROM="(no VERSION / gradle.properties version= / coordinates() / package.json)"
fi
# Driver tags carry no `v` (1.15.5); library tags do (v1.8.106). Compare in the tag's spelling.
case "$TAG" in v*) TAGSTAMP="v$STAMP";; *) TAGSTAMP="$STAMP";; esac
ck "version stamp ($STAMP_FROM) == tag" "$TAGSTAMP" "$TAG"
ck "version stamp ($STAMP_FROM) == arg" "$STAMP" "$VER"
ck "working tree clean"           "$(g status --porcelain | wc -l | tr -d ' ')" "0"
# Red-check xxxi (design §6.1, P3a): validate announces, one release ahead,
# the release from which it gates on contracts coverage, and switches on at
# it. The version is a literal set when the announcing release is cut; this
# holds it to the tag — a release that can follow it when announcing; at or
# below the tag only if the PREVIOUS tag announced that same literal (else
# the gate would start in a release that announced nothing); FAIL when unset
# or naming anything else. A tree without the constant passes as n/a.
GATE_SRC=test_tools/jsonui_test_cli/contracts_coverage.py
GATE_VERDICT=$(python3 "$(dirname "$0")/validate_gate_version.py" "$VER" \
  <(g show "${BRANCH}:$GATE_SRC" 2>/dev/null) <(g show "${PREV}:$GATE_SRC" 2>/dev/null))
echo "     validate gate version: $GATE_VERDICT"
ck "validate gate version (xxxi)"  "${GATE_VERDICT%% *}" "ok"

# RANGE: the line and its contents must come from the SAME range.
CNT=$(g rev-list --count "$PREV..$BRANCH")
BODY=$(g tag -l --format='%(contents)' "$TAG")
ck "tag body states the commit count" "$(printf '%s' "$BODY" | grep -cE "RANGE: $CNT commits? since $PREV")" "1"
# 🔻 THE SHORT-SHA LENGTH IS THE REPOSITORY'S, NOT A CONSTANT. git picks the
# abbreviation from object count, so `%h` is 7 in SwiftJsonUI and 8 in
# jsonui-cli. This check was written against one repo and hard-coded 8, so the
# first time it ran on another one it reported "lists 0 of 4" for a body that
# listed all four — a red that says nothing about the tag. The claim being
# checked is "one line per commit", so the width is 7..12 and the COUNT is
# what is judged.
LISTED=$(printf '%s' "$BODY" | grep -cE '^  [0-9a-f]{7,12} ')
ck "tag body lists exactly that many" "$LISTED" "$CNT"
for h in $(g log --format=%h "$PREV..$BRANCH"); do
  ck "  range commit $h is in the body" "$(printf '%s' "$BODY" | grep -cF "$h")" "1"
done

# Words that a shell accident (backticks in -m) would silently delete.
for w in ${(s:,:)MSGWORDS}; do
  # PRESENCE, not count. The failure this guards against is a word being
  # deleted by a shell accident, so "at least one" is the claim; requiring
  # exactly one made the gate red for a word used twice on purpose.
  #
  # 🔴 AND WHITESPACE IS NORMALISED FIRST. A tag body is hard-wrapped, so a
  # two-word phrase lands across a line break often enough — "ZERO places" did
  # on v1.8.92 — and a contiguous substring test then reports the word as GONE
  # when it is right there. That is the gate being wrong, not the body: what is
  # being checked is that the word survived, not how it was wrapped.
  #
  # ⚠️ Case-insensitive by default, decided after four consecutive reds that
  # were all my own capitalisation. If a check ever needs the case itself,
  # spell that one -F and say why on the same line — otherwise the pressure is
  # to relax the default rather than the one check.
  # 🔻 AND WHITESPACE IS ALSO REMOVED, not only collapsed. Collapsing turns a
  # hard wrap into a space, which is right for English (the break sits between
  # words) and WRONG for Japanese (it sits inside one). Measured 2026-09-16:
  # the ruling "タグは全部終わったあとに打たないと" wrapped after "タグ", so the
  # collapsed body read "タグ は全部…" and the gate called a present phrase GONE
  # — the same false red as the "ZERO places" wrap that made this check
  # normalise in the first place, one layer down.
  #
  # 🚨 AND `tr -d '[:space:]'` CANNOT DO IT. tr is byte-oriented here: stripping
  # a UTF-8 body with it cut "タグ" after its first byte-run, so the stripped
  # text no longer contained the word at all and the second chance was worse
  # than the first. The comparison runs in python, which is character-oriented.
  #
  # ⚠️ The stripped comparison strips the SEARCH WORD too, so an English phrase
  # still has to appear in order; what stops mattering is how it was wrapped.
  ck "body still carries '$w'" \
     "$(BODY="$BODY" NEEDLE="$w" python3 -c '
import os, re, sys
body = os.environ["BODY"]
needle = os.environ["NEEDLE"]
collapsed = re.sub(r"\s+", " ", body).lower()
stripped = re.sub(r"\s+", "", body).lower()
n_collapsed = needle.lower()
n_stripped = re.sub(r"\s+", "", needle).lower()
print("present" if (n_collapsed in collapsed or n_stripped in stripped) else "")
')" "present"
done

# Nothing on the remote branch ahead of this tag, and nothing of ours left off.
g fetch -q "$REMOTE" 2>/dev/null
ck "$REMOTE/$REMOTE_BRANCH exists" "$(g rev-parse --verify --quiet "$REMOTE/$REMOTE_BRANCH" >/dev/null && echo yes)" "yes"
ck "$REMOTE/$REMOTE_BRANCH is an ancestor of the tag" \
   "$(g merge-base --is-ancestor "$REMOTE/$REMOTE_BRANCH" "$TAG^{}" 2>/dev/null && echo yes)" "yes"
# 🔻 THE WINDOW IS TIME, NOT REACHABILITY. `--all --not $PREV` enumerates
# everything not reachable from the tag, which on a repo with old branches is
# the whole divergent history — measured here: 986. The claim is about commits
# CREATED since the previous tag, so the window is the previous tag's commit
# DATE, and the comparison is by patch-id because a cherry-pick has a different
# SHA and the same change.
SINCE=$(g log -1 --format=%cI "$PREV")
pid() { while read c; do g show "$c" 2>/dev/null | g patch-id --stable | cut -d' ' -f1; done | sort -u; }
ONTAG=$(g log --format=%H "$PREV..$BRANCH" | pid)
MADE=$(g log --format=%H --all --since="$SINCE" --not "$PREV" 2>/dev/null | pid)
OFF=$(comm -23 <(printf '%s\n' "$MADE" | grep .) <(printf '%s\n' "$ONTAG" | grep .))
# Positive control in the same output: a window that enumerated nothing would
# report 0 off-tag commits and look identical to a clean release.
echo "     off-tag window: since $SINCE, $(printf '%s\n' "$MADE" | grep -c .) patch-id(s) made, $(printf '%s\n' "$ONTAG" | grep -c .) on the tag"
# 🔻 COMMITS AND PATCH-IDS ARE NOT ONE-TO-ONE. A merge train (v1.8.101: three
# face branches merged, two of the merges resolving the same coverage.json
# line) gave 9 commits and 7 patch-ids — one merge has no diff at all, two
# carry the identical resolution. Comparing the on-tag patch-id count to
# `rev-list --count` therefore reddened a clean release. The claim this
# control makes is that the TIME window actually enumerated the release's
# own commits — so judge containment: every on-tag patch-id is inside the
# window, and the on-tag set is not empty. A window that enumerated nothing
# now reports "missing = <all of them>" instead of a count mismatch.
MISSING=$(comm -13 <(printf '%s\n' "$MADE" | grep .) <(printf '%s\n' "$ONTAG" | grep .) | grep -c .)
ck "the window enumerated the tag's own commits (missing)" "$MISSING" "0"
ck "the tag's own patch-id set is not empty" "$([ "$(printf '%s\n' "$ONTAG" | grep -c .)" -gt 0 ] && echo yes)" "yes"
ck "no commit made since $PREV is off the tag" "$(printf '%s\n' "$OFF" | grep -c .)" "0"
# 🔻 THE LIST IS THE OFF SET, NOT THE WINDOW. This printed every commit in the
# window under OFF-TAG, capped at 10 (v1.8.115: got=3, nine lines, six of
# them on the tag) — the count was right and the names beside it said
# otherwise, and a real off-tag commit past the tenth was never named. Name
# the commits whose patch-id is in OFF, and require every OFF patch-id to
# have been named, so the list and the count cannot disagree again.
if [ -n "$OFF" ]; then
  NAMED=""
  g log --format=%H --all --since="$SINCE" --not "$PREV" 2>/dev/null | while read c; do
    p=$(g show "$c" 2>/dev/null | g patch-id --stable | cut -d' ' -f1)
    [ -n "$p" ] || continue
    printf '%s\n' "$OFF" | grep -qxF "$p" || continue
    g log -1 --format='       OFF-TAG %h %s' "$c"
    NAMED="$NAMED$p"$'\n'
  done
  ck "every off-tag patch-id is named above (unnamed)" \
     "$(comm -23 <(printf '%s\n' "$OFF" | grep .) <(printf '%s' "$NAMED" | grep . | sort -u) | grep -c .)" "0"
fi

# HISTORICAL MARKS: prose that names a PAST version must not be rewritten by a
# release. Judged as a set digest of (path + matching line TEXT) — line numbers
# move for innocent reasons. The count is printed, never compared: a swap
# (one rewritten + one added) leaves it unchanged, which is the exact edit the
# check exists to catch.
# ⚠️ `git grep <rev>` prefixes every line with the REV, so stripping only
# `path:lineno:` leaves the ref name inside the string and the digest differs
# for two identical trees. Measured: 14 marks either side, every line
# byte-identical, digests apart. Strip the rev first, then the line number.
marks() { g grep -I -n -E "As of [0-9]+\.[0-9]+\.[0-9]+|since [0-9]+\.[0-9]+\.[0-9]+" "$1" -- . 2>/dev/null \
          | sed -e "s|^$(printf '%s' "$1" | sed 's/[][\\.*^$|]/\\&/g'):||" -e 's/^\([^:]*\):[0-9]*:/\1\t/' | sort; }
A=$(marks "$PREV"); B=$(marks "$TAG^{}")
# The normalisation is the thing most likely to be wrong, so control it: the
# same ref read twice must agree, and the set must not be empty.
ck "marks extractor is not empty"  "$([ "$(printf '%s' "$A" | grep -c .)" -gt 0 ] && echo yes)" "yes"
ck "marks extractor is stable on one ref" \
   "$(printf '%s' "$(marks "$PREV")" | shasum | cut -c1-16)" "$(printf '%s' "$A" | shasum | cut -c1-16)"
echo "     historical marks: $PREV=$(printf '%s' "$A" | grep -c .)  $TAG=$(printf '%s' "$B" | grep -c .)  (counts printed, not judged)"
# 🔻 THE CLAIM IS "NO HISTORICAL MARK WAS REWRITTEN", NOT "THE SET DID NOT
# MOVE". A release that ADDS a mark ("a cross-platform object since 1.8.101")
# is exactly what the marks are for, and the digest equality reddened
# v1.8.101 on two such additions with nothing removed. So the judgement is
# containment — every mark present at the previous tag is still present,
# byte-identical, at this one — and the additions are printed, not judged.
REMOVED=$(comm -23 <(printf '%s\n' "$A" | grep .) <(printf '%s\n' "$B" | grep .))
echo "     marks added since $PREV: $(comm -13 <(printf '%s\n' "$A" | grep .) <(printf '%s\n' "$B" | grep .) | grep -c .)  (printed, not judged)"
[ -n "$REMOVED" ] && printf '%s\n' "$REMOVED" | sed 's/^/     REWRITTEN OR REMOVED: /'
ck "no historical mark rewritten or removed" "$(printf '%s' "$REMOVED" | grep -c .)" "0"

echo "== $pass/$n pass, $fail fail"
exit $([ "$fail" -eq 0 ] && echo 0 || echo 1)
