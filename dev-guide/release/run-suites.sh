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
py_suite test_tools jsonui_test_cli
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

# --- emitted Kotlin compiles ------------------------------------------------
say "== emitted kotlin"
bash "$C/dev-guide/release/compile-emitted-kotlin.sh" 2>&1 | tail -1
rc=$?; say "   exit=$rc"; [ "$rc" = 0 ] || bad "emitted kotlin: exit $rc"

# --- shared/core mirrors ----------------------------------------------------
say "== shared/core parity"
p=0
for t in sjui_tools kjui_tools rjui_tools; do
  d=$(diff -rq "$C/shared/core" "$C/$t/lib/core" 2>&1 | grep -v "Only in" | wc -l | tr -d ' ')
  say "   $t differs=$d"; p=$((p+d))
done
[ "$p" = 0 ] && say "   parity IDENTICAL" || bad "parity DIFFERS ($p)"

say "== end $(date -u +%FT%TZ) HEAD $(git -C "$C" rev-parse HEAD) porcelain_lines=$(git -C "$C" status --porcelain | wc -l | tr -d ' ') failures=$fail"
exit $fail
