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
# Usage: check-tag.sh <repo> <prev-tag> <tag> <branch> <version> <words,comma> <remote>
set -u
R=${1:?repo}; PREV=${2:?prev tag}; TAG=${3:?new tag}; BRANCH=${4:?branch}
VER=${5:?version}
MSGWORDS=${6:?comma-separated words that must survive in the tag body}
REMOTE=${7:?remote}
g() { git -C "$R" "$@"; }
pass=0; fail=0; n=0
ck() { n=$((n+1)); if [ "$2" = "$3" ]; then pass=$((pass+1)); printf '  %2d PASS %-46s %s\n' "$n" "$1" "$2"
       else fail=$((fail+1)); printf '  %2d FAIL %-46s got=%s want=%s\n' "$n" "$1" "$2" "$3"; fi; }

echo "== tag gate  repo=$R  $PREV..$TAG on $BRANCH"
echo "   words to look for are HAND-SUPPLIED, not derived: $MSGWORDS"
ck "tag object exists"            "$(g cat-file -t "$TAG" 2>/dev/null)" "tag"
ck "tag peels to $BRANCH"         "$(g rev-parse "$TAG^{}")" "$(g rev-parse "$BRANCH")"
ck "tag object != peel (annotated)" "$([ "$(g rev-parse "$TAG")" != "$(g rev-parse "$TAG^{}")" ] && echo yes)" "yes"
ck "VERSION == tag"               "v$(g show "$BRANCH:VERSION" | tr -d '[:space:]')" "$TAG"
ck "VERSION == arg"               "$(g show "$BRANCH:VERSION" | tr -d '[:space:]')" "$VER"
ck "working tree clean"           "$(g status --porcelain | wc -l | tr -d ' ')" "0"

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
ck "remote branch is an ancestor of the tag" \
   "$(g merge-base --is-ancestor "$REMOTE/$BRANCH" "$TAG^{}" 2>/dev/null && echo yes)" "yes"
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
ck "the window enumerated the tag's own commits" \
   "$(printf '%s\n' "$ONTAG" | grep -c .)" "$CNT"
ck "no commit made since $PREV is off the tag" "$(printf '%s\n' "$OFF" | grep -c .)" "0"
[ -n "$OFF" ] && g log --format='       OFF-TAG %h %s' --all --since="$SINCE" --not "$PREV" | head -10

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
ck "historical marks unchanged (set digest)" \
   "$(printf '%s' "$B" | shasum | cut -c1-16)" "$(printf '%s' "$A" | shasum | cut -c1-16)"

echo "== $pass/$n pass, $fail fail"
exit $([ "$fail" -eq 0 ] && echo 0 || echo 1)
