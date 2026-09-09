#!/bin/zsh
#
# Run the six suites the release procedure requires, and say WHICH TREE each
# one examined and HOW IT EXITED — not only what its last line was.
#
# Why this exists (1.8.41): the document_tools suite refuses to run when
# `jsonui_test_cli` resolves to the installed copy under ~/.jsonui-cli instead
# of this checkout (exit 4 with a message saying so — the right behaviour),
# and the ad-hoc runner piped it through `tail -1`, which turned that refusal
# into a blank line under a green-looking header. A pipe returns something
# that looks like an answer even when the left side died: `tail -1` → an empty
# line, `shasum` → the sha of the empty string, `wc -l` → 0.
#
# So every suite here prints (a) the resolved path of the package it imports,
# (b) its own summary line, and (c) its exit code, with `pipefail` on.
#
# Usage: dev-guide/release/run-suites.sh [checkout]   (default: repo of this script)
set -u
set -o pipefail
C=${1:-$(cd "$(dirname "$0")/../.." && pwd)}
export RBENV_VERSION=${RBENV_VERSION:-3.2.2}
export JAVA_HOME=${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}
export ANDROID_HOME=${ANDROID_HOME:-$HOME/Library/Android/sdk}
fail=0
say() { printf '%s\n' "$*"; }
bad() { fail=$((fail+1)); say "!! $*"; }

say "== start $(date -u +%FT%TZ) / $(date +%H:%M:%S) local"
say "== HEAD $(git -C "$C" rev-parse HEAD) porcelain_lines=$(git -C "$C" status --porcelain | wc -l | tr -d ' ')"

# --- Python: the package each suite imports must live in THIS checkout ------
py_suite() {
  local dir=$1 pkg=$2; shift 2
  local where
  where=$(cd "$C/$dir" && PYTHONPATH="$C/test_tools" python3 -c "import $pkg, os; print(os.path.dirname($pkg.__file__))" 2>&1)
  say "== $dir ($pkg from: $where)"
  case "$where" in
    "$C"/*) ;;
    *) bad "$dir: $pkg resolves outside the checkout — the suite would examine another tree" ;;
  esac
  (cd "$C/$dir" && PYTHONPATH="$C/test_tools" python3 -m pytest -q "$@" 2>&1 | tail -3)
  local rc=$?
  say "   exit=$rc"
  [ "$rc" = 0 ] || bad "$dir: pytest exit $rc"
}
# 🚨 THE SAME `--ignore` CI USES, AND FOR THE SAME REASON. Reported by a
# triage lane 2026-09-08 after their gate went red on a branch that touched
# no Python at all:
#
#   ci.yml:184  pytest --ignore=tests/test_stub_name_tables_reach_a_compiler.py
#   ci.yml:207  stub-identifier-tables:  runs-on: macos-15 + `brew install kotlin`
#   this runner  no --ignore
#
# That arm FAILS (deliberately, not skips) when `CI` is set and `kotlinc` is
# absent — a skipped gate gates nothing. This machine has no kotlinc, so
# `CI=1 run-suites.sh` was red for everyone, structurally, forever.
#
# ⚠️ The check does not disappear: the macos-15 job still owns it. What
# changes is that this runner stops pretending to be its owner.
#
# ⚠️ DO NOT "fix" this by unsetting CI. That drops the arm into the skipped
# count, where it vanishes into a green summary — and this runner's own
# reports said "1635 passed, 1 skipped" for three candidates without anyone
# asking WHICH ONE. The denominator of a gate is CI's job list.
say "== CI=${CI:-(unset)} — the test_tools leg mirrors ci.yml:184's --ignore"
py_suite test_tools jsonui_test_cli \
    --ignore=tests/test_stub_name_tables_reach_a_compiler.py
py_suite document_tools jsonui_doc_cli
py_suite jui_tools jui_cli

# --- Ruby ------------------------------------------------------------------
rb_suite() {
  local dir=$1 cmd=$2
  say "== $dir ($cmd, ruby $(cd "$C/$dir" && ruby -v 2>/dev/null | cut -d' ' -f2))"
  # Only rspec's own summary and failure header: the suites deliberately print
  # "Error: …" lines from the code under test, which are not failures.
  (cd "$C/$dir" && eval "$cmd" 2>&1 | grep -E "^[0-9]+ examples, |^Failures:" | tail -3)
  local rc=$?
  say "   exit=$rc"
  [ "$rc" = 0 ] || bad "$dir: rspec exit $rc"
}
rb_suite sjui_tools "rspec"                 # no Gemfile: plain rspec
rb_suite kjui_tools "bundle exec rspec"
rb_suite rjui_tools "bundle exec rspec"

# --- Ruby 2.6: the consumer floor, and a CI leg this runner did not have ----
# CI runs every rspec suite on 2.6 as well as 3.3. 1.8.43's first candidate
# went red there (Array#filter_map, 2.7+) after six green suites here on
# 3.2.2 — the local denominator was smaller than CI's. Same recipe as the
# 2.6 arm: system ruby, the gems under ~/.gem/ruby/2.6.0, no bundler (kjui's
# lockfile pins gems 2.6 cannot materialize). When the toolchain is missing
# the leg is reported as NOT RUN and counted as a failure, never as green.
RB26=/usr/bin/ruby
RSPEC26=$HOME/.gem/ruby/2.6.0/bin/rspec
rb26_suite() {
  local dir=$1; shift
  say "== $dir (ruby 2.6 leg: $RB26 -S $RSPEC26 $*)"
  if ! "$RB26" -v 2>/dev/null | grep -q ' 2\.6\.' || [ ! -x "$RSPEC26" ]; then
    bad "$dir: ruby 2.6 leg NOT RUN (need $RB26 = 2.6.x and $RSPEC26)"; return
  fi
  (cd "$C/$dir" && "$RB26" -S "$RSPEC26" "$@" 2>&1 | grep -E "^[0-9]+ examples, |^Failures:" | tail -3)
  local rc=$?
  say "   exit=$rc"
  [ "$rc" = 0 ] || bad "$dir: ruby 2.6 rspec exit $rc"
}
rb26_suite sjui_tools --exclude-pattern 'spec/**/*{watch,file_watcher}*_spec.rb'
rb26_suite kjui_tools --exclude-pattern 'spec/xml/**/*_spec.rb,spec/cli/commands/generate_xml_spec.rb'
rb26_suite rjui_tools

# --- fixture freshness: CI's ssot-guards leg ---------------------------------
# `jui conformance generate` must rewrite nothing. 1.8.43's first candidate
# failed here on one line: the manifest's generatedFrom digest had not
# followed a one-line change to attribute_definitions.json.
say "== fixture freshness (jui conformance generate produces zero diff)"
(cd "$C/jui_tools" && PYTHONPATH="$C/jui_tools" python3 -c "import sys; from jui_cli.cli import main; sys.exit(main(['conformance','generate']))" 2>&1 | tail -1)
rc=$?; [ "$rc" = 0 ] || bad "conformance generate: exit $rc"
fresh=$(git -C "$C" status --porcelain -- conformance/ | wc -l | tr -d ' ')
say "   files changed by generate: $fresh"
[ "$fresh" = 0 ] || { git -C "$C" diff --stat -- conformance/ | tail -3; bad "conformance fixtures are stale (generate changed $fresh file(s))"; }

# --- the rest of CI's ssot-guards job --------------------------------------
# The second 1.8.43 candidate went red on "Vendored ruby attr tables match
# fresh emit": the generated rjui table carries each attribute's description
# as a comment, so a one-line description change in the SSoT moves it, and
# the committed copy had not followed. Same job, same order as ci.yml.
say "== attr-bindings determinism (two runs emit identical output)"
gen_attr() { (cd "$C/jui_tools" && PYTHONPATH="$C/jui_tools" python3 -c "import sys; from jui_cli.cli import main; sys.exit(main(['generate','attr-bindings','--lang','all']))" >/dev/null 2>&1); }
gen_attr; rc=$?; [ "$rc" = 0 ] || bad "attr-bindings run 1: exit $rc"
rm -rf "$C/build/attr_codegen.run1"; cp -R "$C/build/attr_codegen" "$C/build/attr_codegen.run1"
gen_attr; rc=$?; [ "$rc" = 0 ] || bad "attr-bindings run 2: exit $rc"
d=$(diff -r "$C/build/attr_codegen.run1" "$C/build/attr_codegen" | wc -l | tr -d ' ')
rm -rf "$C/build/attr_codegen.run1"
say "   run1 vs run2 diff lines: $d"; [ "$d" = 0 ] || bad "attr-bindings emit is not deterministic ($d diff lines)"

say "== vendored ruby attr tables match fresh emit"
d=$(diff -r -x README.md "$C/build/attr_codegen/ruby" "$C/rjui_tools/lib/core/generated/attributes" | wc -l | tr -d ' ')
say "   diff lines: $d"; [ "$d" = 0 ] || { diff -r -x README.md "$C/build/attr_codegen/ruby" "$C/rjui_tools/lib/core/generated/attributes" | head -5; bad "vendored ruby attr tables are stale (regenerate: jui generate attr-bindings --lang ruby, then copy build/attr_codegen/ruby/*.rb into rjui_tools/lib/core/generated/attributes/)"; }

say "== attr-codegen manifest freshness (committed manifest matches fresh emit)"
m=$(git -C "$C" status --porcelain -- build/attr_codegen/manifest.json | wc -l | tr -d ' ')
say "   manifest changed by emit: $m"; [ "$m" = 0 ] || bad "build/attr_codegen/manifest.json is stale (commit the regenerated manifest)"

say "== attribute coverage ratchet (declared attributes each platform reads)"
(cd "$C/jui_tools" && PYTHONPATH="$C/jui_tools" python3 -c "import sys; from jui_cli.cli import main; sys.exit(main(['conformance','coverage']))" 2>&1 | tail -1)
rc=$?; say "   exit=$rc"; [ "$rc" = 0 ] || bad "coverage ratchet: exit $rc"

say "== canonical sync (mock schema bytes, condition keys per driver)"
CANON=${JSONUI_CANONICAL_CHECKOUT:-$HOME/resource/jsonui-test-runner}
if [ -d "$CANON" ]; then
  (cd "$C" && python3 dev-guide/ci/check-canonical-sync.py "$CANON" 2>&1 | tail -1)
  rc=$?; say "   exit=$rc"; [ "$rc" = 0 ] || bad "canonical sync: exit $rc"
else
  bad "canonical sync NOT RUN (no checkout at $CANON — set JSONUI_CANONICAL_CHECKOUT)"
fi

# --- emitted Kotlin compiles ------------------------------------------------
say "== emitted kotlin"
bash "$C/dev-guide/release/compile-emitted-kotlin.sh" 2>&1 | tail -1
rc=$?; say "   exit=$rc"; [ "$rc" = 0 ] || bad "emitted kotlin: exit $rc"

# --- misfiled tickets -------------------------------------------------------
# The inbox scan is `docs/bugs/*.md` and README excludes `reports/` from it, so
# a ticket dropped into `reports/` is invisible to the pipeline rather than
# merely unread. Two were found there on 2026-09-08, one of them FOUR DAYS old
# and 47KB, because nothing counted this.
#
# Discriminator: a ticket carries `id:` AND `status:` (README's format); the
# batch reports that legitimately live here carry `batch:`/`fixed_bugs:` and no
# `status:`. Measured before choosing — "status: open" misses a ticket left at
# `investigating`, and "name does not match YYYY-MM-DD-" flags 51 of this
# lane's own version reports.
#
# 🚨 THE GLOB MUST BE (N), AND THE MISSING DIRECTORY MUST SAY SO. Reported by
# a triage lane against this leg's first version, measured in a worktree:
# `docs/` is gitignored, so a worktree or a clean clone HAS NO `docs/bugs/`.
# zsh's default NOMATCH made `for f in "$C"/docs/bugs/reports/*.md` fatal —
# the runner EXITED HERE, and `== shared/core parity` and the closing
# `failures=` line never printed. A leg that cannot find its corpus took the
# whole gate with it, and the abort looked like a short run rather than a
# failure. The "12 legs" measured before that report were the shared
# checkout's 12.
#
# ⚠️ `scanned 0` and `no corpus` must not print the same thing: `misfiled=0`
# is produced both by "nothing is misfiled" and by "nothing was looked at".
# The absent-directory case is named SKIPPED rather than counted.
say "== misfiled tickets (a ticket under reports/ is invisible to the inbox scan)"
if [ ! -d "$C/docs/bugs/reports" ]; then
  say "   SKIPPED: no docs/bugs/reports in this checkout (docs/ is gitignored,"
  say "            so a worktree or fresh clone does not have it)"
else
mis=0
unjudgeable=0
scanned=0
readme=0
# 🚨 RECURSIVE AS OF 2026-09-09. The glob used to be one level deep, and
# `reports/closed/` sat underneath it — invisible to the inbox scan AND to
# this leg. A better hiding place than the one this leg was written to guard.
#
# ⚠️ THE DEPTH CHANGED AND THE PREDICATE DID NOT, deliberately. Widening both
# at once would have turned two files red the moment the glob reached them,
# and for whoever goes red the cheapest repair is always to loosen the
# predicate. Those two were moved back to `docs/bugs/` first — they were live
# tickets misfiled into `closed/`, not reports whose frontmatter had gone
# stale, and the first ruling (write `status: closed` onto them) would have
# closed two tickets whose own bodies say they are not fixed.
#
# ⚠️ `**/*.md` ALREADY INCLUDES THE TOP LEVEL. Pairing it with `*.md` counted
# 405 files twice — measured, 833 for a corpus of 428.
#
# ⚠️ AND THE PREDICATE HAS A BLIND SPOT WIDENING CANNOT REACH: it is an AND,
# so a file with `status:` and no `id:` falls out. Measured under `closed/`:
# one such file, carrying `status: closed`.
#
# 🚫 UNJUDGEABLE IS NOT "HAS NO `id:`". Nearly every report here is a RELEASE
# report with no frontmatter at all — 398 of 426 — and counting those would
# report the corpus, not a gap. It is the files shaped like tickets that
# cannot be judged: one frontmatter field present and the other absent.
# Measured: both 27, status-only 1, id-only 0, neither 398.
#
# 🚫 Do not widen the predicate to swallow that one. It is correctly closed in
# an older format; reaching for it trades a named silence for an unnamed false
# positive. Naming the count is the fix — a live ticket in that shape would
# raise K, and K is read.
for f in "$C"/docs/bugs/reports/**/*.md(N); do
  [ -f "$f" ] || continue
  scanned=$((scanned+1))
  case "$(basename "$f")" in README.md) readme=$((readme+1)); continue ;; esac
  has_id=$(head -20 "$f" | grep -c '^id:')
  has_st=$(head -20 "$f" | grep -cE '^status:')
  if [ "$has_id" = 0 ] && [ "$has_st" = 0 ]; then
    continue                      # a release report, not a ticket
  fi
  if [ "$has_id" = 0 ] || [ "$has_st" = 0 ]; then
    say "   UNJUDGEABLE (half a ticket frontmatter): ${f#$C/docs/bugs/reports/}"
    unjudgeable=$((unjudgeable+1))
    continue
  fi
  # `id:` AND an UNRESOLVED status. Presence of `status:` alone is not enough:
  # a closed investigation's report legitimately keeps ticket-style frontmatter
  # (measured — the 2026-09-04 a11y bench report does, and its own body said
  # "status: closed" while the frontmatter said open, which is how it looked
  # like an unprocessed ticket for four days).
  if head -20 "$f" | grep -qE '^status: *(open|investigating)'; then
    say "   MISFILED: ${f#$C/docs/bugs/reports/}"
    mis=$((mis+1))
  fi
done
# 🚫 `scanned` IS COUNTED BY THE LOOP, NOT BY A SECOND GLOB. It used to be
# `ls -1 <same glob> | wc -l`, which is the same rule written twice: it counted
# README.md and the loop did not, so the printed denominator was 428 while the
# frontmatter tally three comments up says 426. Two implementations of one
# population disagree silently, and the reader cannot tell which is the corpus.
# Now the loop is the only counter, and what it drops is printed beside it.
say "   misfiled=$mis  unjudgeable=$unjudgeable  (scanned $scanned, README skipped $readme, recursive)"
[ "$scanned" != 0 ] || bad "misfiled leg scanned 0 reports in a checkout that HAS the directory"
[ "$mis" = 0 ] || bad "misfiled tickets under reports/: $mis — move them to docs/bugs/"
fi

# --- shared/core mirrors ----------------------------------------------------
# ⚠️ NOT `diff -rq | grep -v "Only in"`. That filter deleted a whole DIRECTION
# of the comparison — a file deleted from one mirror and a new shared/core file
# nobody mirrors BOTH show up only as `Only in`, and both were dropped, so the
# leg printed `parity IDENTICAL` over 88 unread lines (33/27/28 on a clean
# tree at both a4c0e06b and 46fad0cb; 34/28/29 if measured AFTER a run, because
# the Python suites
# leave a shared/core/__pycache__ — the count moved with the MOMENT of the
# measurement as well as the tree, which is why the checker below takes its
# population from `shared/core/*.rb` and cannot see build droppings at all).
# It compares bytes on the intersection AND presence on both sides, taking the
# expected mirror set from each tool's own shared_core_mirror_spec.rb.
say "== shared/core parity (bytes AND presence, both directions)"
python3 "$C/dev-guide/release/check-shared-core-parity.py" "$C"
rc=$?; say "   exit=$rc"; [ "$rc" = 0 ] || bad "shared/core parity: exit $rc"

# --- MCP snapshot drift -----------------------------------------------------
# 🔻 REPORTS, NEVER FAILS. The mcp-server's bundled snapshot can only be
# re-pinned AFTER a release exists to pin to, so between a shared/core change
# and the next bump the two ARE different, every time, by construction. A gate
# that is red by construction gets switched off, and a switched-off gate does
# not report that it is off. So this runs under `say` and the release report
# carries the line — the report is the only exit it has.
#
# ⚠️ The snapshot is the LAST fallback in `spec_loader.ts`
# (JSONUI_CLI_PATH > ./.jsonui-cli/ > ~/.jsonui-cli/ > data/), so drift here
# never reaches a machine that has the CLI installed. The COUNT is the
# information; "stale" is not, because "stale" is true on every release.
say "== mcp snapshot drift (reports only — never fails this run)"
python3 "$C/dev-guide/release/check-mcp-snapshot-drift.py" "$C"
say "   exit=$? (informational; this leg does not add to failures)"

say "== end $(date -u +%FT%TZ) HEAD $(git -C "$C" rev-parse HEAD) porcelain_lines=$(git -C "$C" status --porcelain | wc -l | tr -d ' ') failures=$fail"
exit $fail
