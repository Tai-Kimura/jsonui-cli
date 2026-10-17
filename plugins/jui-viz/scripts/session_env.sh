#!/bin/sh
# SessionStart: give the web test runner the folder jui viz reads progress from.
# A plugin cannot set environment variables itself; a SessionStart hook can, by
# appending export lines to CLAUDE_ENV_FILE (Claude Code runs them before each
# Bash command of the session).
if [ -n "$CLAUDE_ENV_FILE" ]; then
  printf 'export JSONUI_TEST_PROGRESS_DIR="%s"\n' "$HOME/.jsonui-cli/viz/test-progress" >> "$CLAUDE_ENV_FILE"
fi
exit 0
