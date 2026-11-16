#!/bin/sh
# SessionStart: give the web test runner the folder jui viz reads progress from.
# A plugin cannot set environment variables itself; a SessionStart hook can, by
# appending export lines to CLAUDE_ENV_FILE (Claude Code runs them before each
# Bash command of the session).
#
# The folder is jui viz's runtime folder plus test-progress. ⚠️ The rule of
# jui_cli/viz/paths.py viz_home(): $JUI_VIZ_HOME, else $XDG_STATE_HOME/jui-viz,
# each only when absolute, else $HOME/.local/state/jui-viz.
case "$JUI_VIZ_HOME" in
  /*) viz_home="$JUI_VIZ_HOME" ;;
  *)
    case "$XDG_STATE_HOME" in
      /*) viz_home="$XDG_STATE_HOME/jui-viz" ;;
      *) viz_home="$HOME/.local/state/jui-viz" ;;
    esac
    ;;
esac
if [ -n "$CLAUDE_ENV_FILE" ]; then
  printf 'export JSONUI_TEST_PROGRESS_DIR="%s"\n' "$viz_home/test-progress" >> "$CLAUDE_ENV_FILE"
fi
exit 0
