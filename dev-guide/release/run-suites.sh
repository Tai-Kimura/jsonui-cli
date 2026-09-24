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
# 🔻 WHICH TREE THIS RUN MEASURED, not just which commit it is on. A branch can
# be green on its own base while the tree that ships has moved: on 2026-09-09 a
# lane's gate ran three times on a worktree whose base was the previous release,
# so it never saw two commits already on `main` — one of which adds a leg to
# THIS file, changing the leg count the run prints. The gate was working; the
# target was wrong.
#
# ⚠️ THE FOURTH TIME THAT DAY. The others: a suite that resolved its package to
# `~/.jsonui-cli` and passed against the previous release; a CI run green on the
# tree from before a history rewrite; an arm red because its fixture could not
# hold the reported shape. In all four the instrument was correct and the
# SUBJECT was not — so the fix is not a stricter gate, it is printing what the
# gate looked at.
#
# 🚨 COMPARE AGAINST BOTH `main` AND `origin/main`, AND SAY WHICH IS WHICH.
# The first cut compared only against `origin/main` — and the release commits
# are UNPUSHED by design (the tag goes up with them, atomically), so a branch
# four commits behind the shipping tree reported "ahead by 0". The detector for
# "measured the wrong target" measured the wrong target. `main` is the tree that
# ships; `origin/main` is what other machines can see. They are different
# numbers and they answer different questions.
#
# Silent about a ref that does not exist rather than reporting zero: a fresh
# clone has no local `main`, a detached CI checkout may have neither, and a
# missing ref is not a base of zero.
for _ref in main origin/main; do
  if ! git -C "$C" rev-parse --verify --quiet "$_ref" >/dev/null; then
    say "== BASE vs $_ref: SKIPPED, no such ref here (not a base of zero)"
    continue
  fi
  _n=$(git -C "$C" rev-list --count "HEAD..$_ref" 2>/dev/null)
  _s=$(git -C "$C" rev-parse "$_ref")
  # "behind by 0" reads as a finding to someone skimming; "at" does not. The
  # number is printed either way — it is the count that carries the information.
  if [ "$_n" = 0 ]; then
    say "== BASE vs $_ref: AT $_s (behind by 0)"
  else
    say "== BASE vs $_ref: BEHIND $_s by $_n commit(s) — this run did NOT see them"
  fi
done

# --- Python: the package each suite imports must live in THIS checkout ------
# Every tool directory in the checkout, joined for PYTHONPATH. DERIVED from
# the tree, like the suite-side guard in document_tools/tests/conftest.py, so
# a tool added tomorrow is on the path without editing this file.
#
# 🚨 WHY THIS IS NOT JUST test_tools. It was, and `jui_cli` therefore resolved
# to ~/.jsonui-cli/jui_tools — an editable install pointing at the DISTRIBUTED
# copy. `jsonui_doc_cli/cli.py` imports ConfigManager from there, so this
# runner was reading a released config resolver while reporting on the
# checkout. Measured 2026-09-09; the suite-side guard now refuses the run.
#
# ⚠️ cwd STILL WINS over these entries (`python -m` puts it at sys.path[0]),
# which is what keeps each leg's own `tests` package its own: jui_tools/tests
# and test_tools/tests are both importable as `tests`, and the leg's own copy
# is the one that resolves. Verified before widening this.
py_path() {
  local out=""
  for d in "$C"/*_tools; do
    [ -d "$d" ] || continue
    out="${out:+$out:}$d"
  done
  printf '%s' "$out"
}

py_suite() {
  local dir=$1 pkg=$2; shift 2
  local where pp
  pp=$(py_path)
  where=$(cd "$C/$dir" && PYTHONPATH="$pp" python3 -c "import $pkg, os; print(os.path.dirname($pkg.__file__))" 2>&1)
  say "== $dir ($pkg from: $where)"
  case "$where" in
    "$C"/*) ;;
    *) bad "$dir: $pkg resolves outside the checkout — the suite would examine another tree" ;;
  esac
  # `-rs` names every skip, and the filter keeps those lines plus the summary.
  # `tail -3` kept only the summary, so a skipped arm was a number with no
  # name — and a number is not something anyone can go and fix.
  #
  # The summary is matched by its shape (`N passed … in Ns`), NOT by the `=`
  # band: jui_tools runs pytest-subtests, whose summary has no band, and a
  # filter anchored on `^=+` dropped that leg's count in every log (1.8.73
  # candidate, 2026-09-11). pytest writes to a file so `rc` is pytest's own —
  # a pipe into grep reports grep's exit under pipefail, which is 1 whenever
  # a passing run has no skip to name.
  local log; log=$(mktemp "${TMPDIR:-/tmp}/run-suites.$dir.XXXXXX")
  (cd "$C/$dir" && PYTHONPATH="$pp" python3 -m pytest -q -rs "$@" >"$log" 2>&1)
  local rc=$?
  local closing='[0-9]+ (passed|failed|error|skipped|xfailed|xpassed|deselected|warning)s?.* in [0-9.]+s'
  grep -E "^(SKIPPED|FAILED|ERROR) |$closing" "$log"
  local n; n=$(grep -c -E "$closing" "$log")
  say "   exit=$rc"
  [ "$rc" = 0 ] || bad "$dir: pytest exit $rc (full log: $log)"
  [ "$n" = 1 ] || bad "$dir: pytest printed $n closing line(s), expected 1 — the count is unreadable (full log: $log)"
  [ "$rc" = 0 ] && [ "$n" = 1 ] && rm -f "$log"
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
# rjui's fold and type-check arms need the toolchain pinned under
# rjui_tools/spec/support (tsc + esbuild). Without it they SKIP through
# mark_skipped! — visible as `pending` in the summary line, invisible to the
# `failures=` count this runner ends with. Measured 2026-09-10: 6 pending,
# every one of them an arm for that day's fix. A skipped gate gates nothing,
# so the install is a leg, and a leg that cannot install is a failure.
say "== rjui_tools spec support (npm ci --prefix rjui_tools/spec/support)"
(cd "$C" && npm ci --prefix rjui_tools/spec/support --prefer-offline --no-audit --no-fund 2>&1 | tail -1)
rc=$?; say "   exit=$rc"; [ "$rc" = 0 ] || bad "rjui_tools: spec support not installed — the fold and tsc arms would skip"
# 🚨 AND IT RUNS BEFORE test_tools, NOT JUST BEFORE rjui. test_tools' TypeScript
# compile arms resolve `tsc` at that same rjui_tools/spec/support/node_modules
# path — not on PATH. On a fresh worktree this leg used to sit after the
# Python suites, so test_tools ran with no tsc and 6 arms skipped; the runner
# printed `1654 passed, 6 skipped` under a green header and nobody could say
# why, because `| tail -3` had already thrown the reasons away. Measured
# 2026-09-11: worktree created 15:02:22, test_tools ran 15:02:35–15:03:33,
# npm ci created tsc at 15:06:47. Order is the defect; this is the fix.
say "== CI=${CI:-(unset)} — the test_tools leg mirrors ci.yml:184's --ignore"
py_suite test_tools jsonui_test_cli \
    --ignore=tests/test_stub_name_tables_reach_a_compiler.py
py_suite document_tools jsonui_doc_cli
# ⚠️ THE GATE RUNS IN A DETACHED WORKTREE, AND THAT MOVES WHAT IS BESIDE IT.
#
# `jui_tools/tests/test_component_metadata_platform_truth.py` asks the two
# sibling library checkouts — SwiftJsonUI and KotlinJsonUI — whether the
# canon's claims about their emit are true. It finds them BESIDE this repo,
# and skips with a named reason when they are absent, which is right for a
# bare CI clone.
#
# 🚨 This runner has always used a worktree under a scratchpad directory, and
# nothing is beside THAT. So the four cross-repo arms — the ones that catch
# SSoT divergence between the canon and the two libraries — were skipped in
# every release this runner has gated. Measured 2026-09-11 across three
# trains in one night: `1897 passed, 5 skipped` here, `1902 passed` in the
# shared checkout, same commit. The runner spent the night reporting
# `failures=0` beside five arms it never ran, which is the exact shape it was
# built to find.
#
# The repos are lent by path, the same way rjui's toolchain is installed, and
# the lending is PRINTED: a leg that silently succeeds at nothing is what
# this whole file exists to stop.
# ⚠️ "Beside this repo" is not "beside this worktree". A worktree lives in a
# scratchpad and has nothing beside it — which is the whole defect. The
# siblings sit next to the MAIN working tree, and `--git-common-dir` is what
# names it from inside a worktree (`--show-toplevel` would answer with the
# worktree). Measured: the first cut of this repair resolved `$C/..`, printed
# `NOT FOUND beside <scratchpad>`, and would have lent nothing while looking
# like it had.
_common="$(git -C "$C" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
_siblings="$(cd "${_common:-$C/.git}/../.." 2>/dev/null && pwd)"
for _sib in SwiftJsonUI KotlinJsonUI; do
  # 🔻 `~~`, AND THE PREFIX WAS MEASURED, NOT PICKED. Every line this script
  # prints with `==` is counted by readers as a leg (`grep -c '^== '` — four
  # release reports carry the resulting number, "26"). These three lines are
  # informational: they say what this run BORROWED, not that a suite ran.
  # Printing them with `==` moved a number that ships in the report from 26 to
  # 28, with no suite added and no way for the reader to see why.
  #
  # ⚠️ THE FIRST FIX PICKED `--` WITHOUT MEASURING, AND `--` IS TAKEN: pytest
  # emits `-- Docs: https://docs.pytest.org/...` on any run with warnings. So
  # `grep -c '^-- '` would have counted three borrow lines where two were
  # printed. Across a full 26-leg run (82 lines) the taken prefixes are `== `
  # (28) and `-- ` (1); `~~ `, `>> `, `++ `, `%% `, `@@ `, `|| `, `:: `, `## `
  # were all zero. `~~` was chosen from that measurement.
  #
  # 🔻 RE-MEASURE BEFORE CHANGING THIS. A prefix that is free in a green run
  # can be taken by a tool that only prints on failure.
  _env_name="JSONUI_$(printf '%s' "$_sib" | tr '[:lower:]' '[:upper:]')_PATH"
  eval "_have=\${$_env_name:-}"
  if [ -n "$_have" ]; then
    say "~~ $_sib: using $_env_name=$_have"
  elif [ -d "$_siblings/$_sib" ]; then
    say "~~ $_sib: lending $_siblings/$_sib (not beside this worktree)"
    eval "export $_env_name=\"$_siblings/$_sib\""
  else
    say "~~ $_sib: NOT FOUND beside $_siblings — the cross-repo arms will skip"
  fi
done
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
# ⚠️ THE LABEL HAS TO BE EARNED. This read `git status` AFTER the generate and
# called the result "files changed by generate" — so a file that was ALREADY
# dirty got attributed to the generator. Measured 2026-09-15: two hand-edited
# ledger files (`control_diff.json` / `cross_effect.json`, which the generator
# does not write at all — verified, md5 unchanged across a generate) were
# reported as "conformance fixtures are stale". That is the wrong diagnosis in
# the expensive direction: it sends someone to look at the generator when the
# generator is a fixed point and the tree simply has work in it.
#
# The set before and the set after are both taken, and the difference is what
# the generator did. The pre-existing dirt is PRINTED rather than subtracted
# silently — a release must not be cut from a dirty tree either, and the tag
# gate is what refuses that.
_dirty_before=$(git -C "$C" status --porcelain -- conformance/ | awk '{print $2}' | sort)
(cd "$C/jui_tools" && PYTHONPATH="$C/jui_tools" python3 -c "import sys; from jui_cli.cli import main; sys.exit(main(['conformance','generate']))" 2>&1 | tail -1)
rc=$?; [ "$rc" = 0 ] || bad "conformance generate: exit $rc"
_dirty_after=$(git -C "$C" status --porcelain -- conformance/ | awk '{print $2}' | sort)
_by_generate=$(comm -13 <(printf '%s\n' "$_dirty_before" | grep .) <(printf '%s\n' "$_dirty_after" | grep .))
fresh=$(printf '%s\n' "$_by_generate" | grep -c .)
_pre=$(printf '%s\n' "$_dirty_before" | grep -c .)
say "   files changed by generate: $fresh   (already dirty before this leg: $_pre)"
[ "$_pre" = 0 ] || printf '%s\n' "$_dirty_before" | grep . | sed 's|^|     pre-existing |'
[ "$fresh" = 0 ] || { printf '%s\n' "$_by_generate" | sed 's|^|     BY GENERATE |'; bad "conformance fixtures are stale (generate changed $fresh file(s))"; }

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
# ⚠️ `d=0` IS PRODUCED BY TWO DIFFERENT FACTS: "the two runs agree" and
# "there was nothing to compare". `diff -r` on a missing or empty tree writes
# its complaint to stderr and NOTHING to stdout, so `wc -l` says 0 and this leg
# goes green. Measured 2026-09-11 against these exact lines: an emit that
# returns 0 and writes no file leaves BOTH this leg and the vendored-tables leg
# below at fail=0. Worse than a one-sided zero — in a TWO-VERSION comparison a
# dead predicate returns "identical", which is an ACTIVE claim of no drift.
# So count the denominator BEFORE the rm, and let it speak.
n=$(find "$C/build/attr_codegen.run1" -type f 2>/dev/null | wc -l | tr -d ' ')
rm -rf "$C/build/attr_codegen.run1"
say "   compared $n file(s); run1 vs run2 diff lines: $d"
[ "$n" -gt 0 ] || bad "attr-bindings determinism compared 0 file(s) — the emit wrote nothing"
[ "$d" = 0 ] || bad "attr-bindings emit is not deterministic ($d diff lines)"

say "== vendored ruby attr tables match fresh emit"
d=$(diff -r -x README.md "$C/build/attr_codegen/ruby" "$C/rjui_tools/lib/core/generated/attributes" | wc -l | tr -d ' ')
# Same hole as the leg above, and this one is easy to think is covered because
# it HAS gone red before (1.8.43's second candidate). Going red once is history,
# not a guard: with build/attr_codegen/ruby missing, `d` is 0 and this is green.
# The count must name THE SET THE DIFF COMPARES, not a tidier-sounding subset:
# `-name '*.rb'` says 31 while `diff -x README.md` is looking at 32 (the 31
# tables plus skipped_attributes.json). Same exclusion here as on the diff.
n=$(find "$C/build/attr_codegen/ruby" -type f ! -name README.md 2>/dev/null | wc -l | tr -d ' ')
say "   compared $n file(s); diff lines: $d"
[ "$n" -gt 0 ] || bad "vendored ruby attr tables leg compared 0 file(s) — build/attr_codegen/ruby is empty or missing"
[ "$d" = 0 ] || { diff -r -x README.md "$C/build/attr_codegen/ruby" "$C/rjui_tools/lib/core/generated/attributes" | head -5; bad "vendored ruby attr tables are stale (regenerate: jui generate attr-bindings --lang ruby, then copy build/attr_codegen/ruby/*.rb into rjui_tools/lib/core/generated/attributes/)"; }

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
# --------------------------------------------------------------------------
# The gate that RUNS the emitted branch runtime, not the one that reads it.
#
# 🔴 FOUR RELEASES MEASURED THE WRONG GATE. 1.8.96..1.8.99 drove
# `swiftc -typecheck` on the emitted JsonuiBranchRuntime.swift to zero in three
# configurations; a consumer then RAN it under Swift 6 and 127 of 248 tests
# died with `signal trap`. The swizzled `@objc` session getters were still at
# the target's default isolation — MainActor — and the ObjC runtime calls them
# from whatever thread asked for a session.
#
# ⚠️ The repro only discriminates if it calls that getter FROM A BACKGROUND
# QUEUE; a version that drove the harness on the main actor passed with the
# defect present.
say "== emitted branch runtime, EXECUTED (swift 6 + defaultIsolation MainActor)"
if command -v swift >/dev/null 2>&1; then
  python3 -c "import sys; sys.path.insert(0, sys.argv[1] + '/test_tools'); from jsonui_test_cli.branch_tests import SWIFT_RUNTIME; open(sys.argv[1] + '/dev-guide/release/runtime-gate/Tests/RTTests/JsonuiBranchRuntime.swift', 'w').write(SWIFT_RUNTIME)" "$C"
  out=$( cd "$C/dev-guide/release/runtime-gate" && swift test 2>&1 )
  rc=$?
  say "   $(printf '%s' "$out" | grep -E 'Executed [0-9]+ test|signal|error:' | tail -1)"
  say "   exit=$rc"
  [ "$rc" = 0 ] || bad "emitted runtime traps when executed: exit $rc"
else
  say "   SKIPPED — no swift on PATH (this leg needs a toolchain, not a checkout)"
fi

say "== misfiled tickets (a ticket under reports/ is invisible to the inbox scan)"
if [ ! -d "$C/docs/bugs/reports" ]; then
  say "   SKIPPED: no docs/bugs/reports in this checkout (docs/ is gitignored,"
  say "            so a worktree or fresh clone does not have it)"
else
mis=0
unjudgeable=0
relrep=0
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
# 🚫 UNJUDGEABLE IS NOT "HAS NO `id:`". Nearly every report here is a RELEASE
# report with no frontmatter at all, and counting those would report the
# corpus, not a gap.
#
# 🔴 AND THE `id:` AND `status:` CONJUNCTION WAS WRONG (fixed 2026-09-16).
# The note that used to stand here said "status-only: 1 file, correctly closed
# in an older format — naming the count is the fix". That number was measured
# once and then aged: the CLOSING ROUTINE PRODUCES THAT SHAPE. Every closed
# ticket is an inbox file moved under `closed/` with its frontmatter edited,
# and an inbox ticket has no `id:` — the filename is the id. Re-measured the
# day this was noticed: 12 files, one per closed ticket, all correct.
#
# ⚠️ AND THE COUNT WAS READ THROUGH A FILTER THAT HID IT. The release log was
# grepped with a pattern containing `red`, which matched exactly the two lines
# whose PATHS contain "measu(red)" and "decla(red)" — so a 12-line bucket was
# read as 2. The printed data contained the reader's own token.
#
# So the predicate is now `status:` alone, which is the whole question this leg
# asks. `release:` names a release report that carries a status. What is left
# in UNJUDGEABLE is the one shape that genuinely cannot be judged: an `id:`
# with no `status:` at all.
for f in "$C"/docs/bugs/reports/**/*.md(N); do
  [ -f "$f" ] || continue
  scanned=$((scanned+1))
  case "$(basename "$f")" in README.md) readme=$((readme+1)); continue ;; esac
  has_id=$(head -20 "$f" | grep -c '^id:')
  has_st=$(head -20 "$f" | grep -cE '^status:')
  has_rel=$(head -20 "$f" | grep -c '^release:')
  if [ "$has_id" = 0 ] && [ "$has_st" = 0 ]; then
    continue                      # a release report, not a ticket
  fi
  # 🔻 A RELEASE REPORT CAN CARRY `status:` TOO (`release: v1.8.66` /
  # `status: shipped`). `release:` names the kind and no ticket has it.
  if [ "$has_rel" != 0 ]; then
    relrep=$((relrep+1))
    continue
  fi
  # 🔴 JUDGE ON `status:` ALONE. This used to require `id:` AND `status:` and
  # call everything else unjudgeable — but a CLOSED TICKET is exactly that
  # shape: the closing routine moves the inbox file under `closed/` and edits
  # its frontmatter, and an inbox ticket never had an `id:` (the filename is
  # the id). So the bucket filled with correctly-closed tickets: measured
  # 2026-09-16, 12 of them, and the comment that used to stand here said "1".
  # `id:` is not needed to answer this leg's question — `status:` is the whole
  # predicate. A file claiming ticket identity with NO status still cannot be
  # judged, and that is the only thing left in the bucket.
  if [ "$has_st" = 0 ]; then
    say "   UNJUDGEABLE (id: present, status: absent): ${f#$C/docs/bugs/reports/}"
    unjudgeable=$((unjudgeable+1))
    continue
  fi
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
say "   misfiled=$mis  unjudgeable=$unjudgeable  release-reports=$relrep  (scanned $scanned, README skipped $readme, recursive)"
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
# --- the python suite, IN CI'S SHAPE ----------------------------------------
# 🔴 THE GATE THAT WAS MISSING WHEN v1.8.85 WENT OUT RED. Every other leg here
# runs the suite in THIS tree, which has 206 tags, Pillow installed and an
# untracked `docs/`. CI has none of those: `actions/checkout@v4` is depth-1 and
# `--no-tags`, the job installs without the [conformance] extra, and `docs/` is
# gitignored so no checkout ever has it. A skip that only happens in CI is
# therefore INVISIBLE to a release gate that runs here — not unlikely to be
# caught, structurally incapable of being caught. v1.8.85 was tagged and pushed
# green and CI failed on exactly that: one arm skipped for a reason the
# repository had not declared, because the arm needs a release tag.
#
# So this leg builds a checkout shaped like CI's and runs the suite plus the
# collection census in it. Reproduced 2026-09-15 against run 34954953718:
# testcases 2597, skipped 88 (86 Pillow + 1 docs + 1 undeclared) — the runner's
# own numbers, to the unit.
#
# ⚠️ THE SHAPE IS ASSERTED, NOT ASSUMED. A clone that quietly kept its tags, or
# a Pillow shim that did not take, would run a DIFFERENT suite and report a
# green this leg did not earn. The four facts are measured and printed.
#
# 🔻 NOT REPRODUCED, AND SAID SO: CI sparse-checks-out the two sibling
# libraries, so those arms read a few named files while this leg points at the
# full local checkouts. A sparse pattern too narrow for an arm shows up in CI
# as a FAILURE (the arms fail on a named-but-absent file, by construction), not
# as a skip — which is what this leg is for.
say "== python suite in CI's shape (depth 1, no tags, no docs/, WITH Pillow)"
CISHAPE=$(mktemp -d)
git clone -q --depth 1 --no-tags "file://$C" "$CISHAPE/repo" 2>/dev/null
CI_TAGS=$(git -C "$CISHAPE/repo" tag -l 2>/dev/null | wc -l | tr -d ' ')
CI_DEPTH=$(git -C "$CISHAPE/repo" rev-list --count HEAD 2>/dev/null)
CI_DOCS=$([ -d "$CISHAPE/repo/docs" ] && echo present || echo absent)
# 🔻 PILLOW IS NOW PART OF CI'S SHAPE, AND THAT IS A CHANGE. Until 1.8.87 the
# python-suite job installed the bare package while the other two jui_tools
# installs took `[conformance]`, so 86 arms skipped there — including both
# files covering the gates 1.8.85 shipped. This leg faithfully reproduced that
# by shadowing PIL, which meant the leg could not run them either: the arms
# existed, passed on a developer tree, and were absent from every CI mouth.
# ci.yml now installs the extra, so fidelity means Pillow PRESENT. If the extra
# is ever dropped again the assertion below fails rather than quietly skipping.
CI_PIL=$(python3 -c 'try:
    from PIL import Image
    print("importable")
except ImportError:
    print("blocked")' 2>/dev/null)
# 🔻 THE SVG→PDF CONVERTERS ARE PART OF CI'S SHAPE TOO (1.8.112). ci.yml
# installs librsvg2-bin and cairosvg so the iOS image arms run there; this
# leg therefore needs both present, and ci.yml has to still install them —
# the same pair of facts as Pillow above, for the same reason.
CI_RSVG=$(command -v rsvg-convert >/dev/null 2>&1 && echo present || echo absent)
CI_CAIROSVG=$(python3 -c 'try:
    import cairosvg, cairocffi
    print("importable")
except (ImportError, OSError):
    print("blocked")' 2>/dev/null)
say "   shape: sha=$(git -C "$CISHAPE/repo" rev-parse --short HEAD 2>/dev/null) tags=$CI_TAGS depth=$CI_DEPTH docs=$CI_DOCS pillow=$CI_PIL rsvg=$CI_RSVG cairosvg=$CI_CAIROSVG"
if [ "$CI_TAGS" != "0" ] || [ "$CI_DEPTH" != "1" ] || [ "$CI_DOCS" != "absent" ] || [ "$CI_PIL" != "importable" ]; then
    bad "CI shape: the checkout does not look like CI's — this leg would measure the wrong thing"
elif ! grep -q "pip install -e '.\[conformance\]'" "$CISHAPE/repo/.github/workflows/ci.yml"; then
    bad "CI shape: ci.yml no longer installs [conformance] — this leg would run arms CI skips"
elif [ "$CI_RSVG" != "present" ] || [ "$CI_CAIROSVG" != "importable" ]; then
    bad "CI shape: rsvg-convert / cairosvg missing here, and CI has both — the iOS image arms would skip in this leg only"
elif ! grep -q "apt-get install -y -qq librsvg2-bin" "$CISHAPE/repo/.github/workflows/ci.yml" \
     || ! grep -q "pip install cairosvg" "$CISHAPE/repo/.github/workflows/ci.yml"; then
    bad "CI shape: ci.yml no longer installs librsvg2-bin / cairosvg — the iOS image arms would skip in CI"
else
    ( cd "$CISHAPE/repo/jui_tools" \
      && PYTHONPATH="$CISHAPE/repo/jui_tools" \
         JSONUI_SWIFTJSONUI_PATH="${JSONUI_SWIFTJSONUI_PATH:-$(cd "$C/.." && pwd)/SwiftJsonUI}" \
         JSONUI_KOTLINJSONUI_PATH="${JSONUI_KOTLINJSONUI_PATH:-$(cd "$C/.." && pwd)/KotlinJsonUI}" \
         python3 -m pytest -q --junitxml="$CISHAPE/report.xml" -p no:cacheprovider ) > "$CISHAPE/pytest.log" 2>&1
    rc=$?
    say "   $(grep -E '^[0-9]+ (passed|failed)|passed,' "$CISHAPE/pytest.log" | tail -1)  exit=$rc"
    [ "$rc" = 0 ] || { bad "CI-shaped pytest: exit $rc"; grep -E '^FAILED|^ERROR' "$CISHAPE/pytest.log" | head -10; }
    ( cd "$CISHAPE/repo/jui_tools" && python3 tools/check_pytest_collection.py "$CISHAPE/report.xml" ) > "$CISHAPE/census.log" 2>&1
    rc=$?
    sed 's/^/   /' "$CISHAPE/census.log" | grep -E 'collection|error' | head -8
    say "   collection census exit=$rc"
    [ "$rc" = 0 ] || bad "CI-shaped collection census: exit $rc"
fi
rm -rf "$CISHAPE"

# --- which python files changed only their prose ----------------------------
# 🔻 "THIS RELEASE CHANGES NO CODE" IS THE CLAIM NOBODY CHECKS. Gates read
# grammar and tests; a sentence in a notice is believed because reading the
# diff is tedious and because the obvious way to read it is WRONG — a
# predicate that skips `^[-+]\s*#` still counts every changed docstring line
# as code, since a docstring is not a `#` comment. A person skimming makes the
# same mistake. Measured on v1.8.89..v1.8.90, where the claim was true for
# parity.py and false for the release as a whole (the version stamps ARE code).
#
# So it is DERIVED and PRINTED every run, never asked for: the notice can cite
# the line instead of a human impression. Informational — a release is allowed
# to change code — but a prose-only claim that this contradicts is now visible
# before it ships.
say "== prose-only classification (python files in the range)"
PREVTAG_P=$(git -C "$C" tag -l 'v*' --sort=-v:refname | head -1)
if [ -z "$PREVTAG_P" ]; then
    say "   NOT EXERCISED: no release tag to compare against"
elif [ "$(git -C "$C" rev-list --count "$PREVTAG_P..HEAD")" = 0 ]; then
    say "   NOT EXERCISED: HEAD is at $PREVTAG_P, so there is nothing to classify"
else
    python3 "$C/jui_tools/tools/check_prose_only.py" "$PREVTAG_P" HEAD "$C" | sed 's|^|   |'
    rc=$?; [ "$rc" = 0 ] || bad "prose-only classification: exit $rc"
fi

# --- cited ticket paths ------------------------------------------------------
# 🔻 NO OTHER GATE CAN EVER SEE THESE. `docs/` is gitignored, so a path written
# into tracked prose points at a file no CI checkout has — and the ticket
# routine MOVES every ticket when it closes (inbox -> reports/ -> closed/), so
# the citations rot structurally, one per closure. Measured 2026-09-15: a lane
# named ONE dead path in the baselines README; deriving the whole set found
# FOUR dead of seven, across six files, only one of which was that README.
# Fixing the named instance would have left three.
#
# ⚠️ IT IS ALSO THE ONE CHECK THAT MUST NOT FAIL ON A TREE WITHOUT `docs/`.
# On a fresh clone every cited path is missing for a reason that says nothing
# about the citations, so it reports NOT EXERCISED instead of turning red — the
# same shape as the empty-range case below.
say "== cited ticket paths resolve (docs/ is gitignored, so no CI job checks these)"
if [ ! -d "$C/docs/bugs" ]; then
    say "   NOT EXERCISED: $C/docs/bugs does not exist (gitignored; this tree has no tickets)"
else
    CITED=$(git -C "$C" grep -ohE 'docs/bugs/[A-Za-z0-9/._-]+\.md' -- . | sort -u)
    NCITED=$(printf '%s\n' "$CITED" | grep -c . )
    DEAD=""
    while read -r _p; do
        [ -z "$_p" ] && continue
        [ -f "$C/$_p" ] || DEAD="$DEAD$_p\n"
    done <<< "$CITED"
    NDEAD=$(printf "$DEAD" | grep -c . )
    say "   $NCITED path(s) cited by tracked files, $NDEAD unresolved"
    # A derivation that found nothing to check looks exactly like a clean tree.
    if [ "$NCITED" = 0 ]; then
        bad "cited ticket paths: the derivation matched 0 paths — the predicate is dead, not the repo clean"
    elif [ "$NDEAD" != 0 ]; then
        printf "$DEAD" | sed 's|^|     DEAD |'
        bad "cited ticket paths: $NDEAD path(s) point at files that are not there"
    fi
fi

# --- the notice's surface classification ------------------------------------
# 🔻 THIS LEG EXISTS TO EARN A SKIP ELSEWHERE. `what_moved.py` exits 1 on a
# path whose surface nobody has named, which is how a new top-level artifact
# gets a line in the release notice instead of being dropped from it. The arm
# that runs it in the python suite SKIPS in CI, because `actions/checkout@v4`
# is depth-1 with no tags and the check needs a released range to classify.
# Allowing that skip is only honest if the property is checked where it
# matters, and this is that place: a release cannot be announced from a tree
# whose suites did not run, and these run from a full checkout with tags.
say "== notice surfaces (every changed path has a named surface)"
PREVTAG=$(git -C "$C" tag -l 'v*' --sort=-v:refname | head -1)
if [ -z "$PREVTAG" ]; then
    bad "notice surfaces: no release tag in $C — cannot classify a range"
else
    python3 "$C/dev-guide/release/what_moved.py" "$PREVTAG" HEAD > /tmp/what_moved.$$ 2>&1
    rc=$?
    RANGEN=$(git -C "$C" rev-list --count "$PREVTAG..HEAD")
    NPATH=$(grep -c '^      ' /tmp/what_moved.$$ | tr -d ' ')
    say "   range $PREVTAG..HEAD: $RANGEN commit(s), $NPATH path(s) classified, exit=$rc"
    # ⚠️ AN EMPTY RANGE EXITS 0 AND CLASSIFIES NOTHING, which reads exactly
    # like a clean pass. That is the state right after a tag is cut — HEAD is
    # AT the newest tag — so the leg says out loud that it was not exercised
    # rather than reporting a green it did not earn.
    if [ "$RANGEN" = 0 ]; then
        say "   NOT EXERCISED: HEAD is at $PREVTAG, so there was nothing to classify"
    fi
    [ "$rc" = 0 ] || { bad "notice surfaces: exit $rc"; grep -A5 'UNCLASSIFIED' /tmp/what_moved.$$; }
    rm -f /tmp/what_moved.$$
fi

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
