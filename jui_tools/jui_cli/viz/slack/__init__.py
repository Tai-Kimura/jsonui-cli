"""Slack intake for jui viz (stage 1: fetch -> filter -> route).

Design: jsonui-cli docs/plans/2026-11-02-viz-slack-intake-design.md, chapters 1-4 and 7.

    fetch (api | connector)  ->  <orchestrationDir>/inbox/<ts>-<workspace>-<channel>.json   raw, local only
    watcher                  ->  filter adapter (builtin | a .py file)                       machine only, nothing leaves
                             ->  router adapter (haiku | jev | a .py file)                   sees the filtered text only
                             ->  projects/<id>/  |  _unsorted/  |  deleted (chitchat, no trace)

The config is <viz_home>/slack.json, mode 0600 (it holds keys).
"""
