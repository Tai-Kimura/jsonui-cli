#!/bin/sh
# UserPromptSubmit hook for the orchestrator's session in the jsonui-cli checkout: names every red ticket of the daily
# watch (docs/bugs/*-cc-dependency-watch-red*.md) that nobody has seen yet, so it lands in the session's context.
# A ticket is unseen while its status line starts with "status: open"; `watch.py seen <ticket>` rewrites it.
# Nothing to report -> no output. The cost when there is no red ticket is one glob in this shell (no process).
# Usage: red_ticket_hook.sh [<repo>]   (default: $CLAUDE_PROJECT_DIR, else the working folder)
repo="${1:-${CLAUDE_PROJECT_DIR:-.}}"
set -- "$repo"/docs/bugs/*-cc-dependency-watch-red*.md
[ -e "$1" ] || exit 0
unseen=""
for f in "$@"; do
  if grep -q '^status: open' "$f"; then unseen="$unseen ${f##*/}"; fi
done
[ -n "$unseen" ] || exit 0
echo "cc-dependency-watch: Claude Code の依存の見張りが赤の票を起こした（未読）:$unseen"
echo "docs/bugs で読み、手の空いた JsonUI のセッションに振る。読んだら: python3 jui_tools/tools/cc_watch/watch.py seen docs/bugs/<票>"
