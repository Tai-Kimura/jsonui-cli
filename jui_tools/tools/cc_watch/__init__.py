"""Watching what this repository relies on in Claude Code (ticket 2026-10-19-claude-dependency-watch).

* ``ledger.json`` — one entry per thing we rely on: what it is, the files that use it, the probe that checks it, what
  breaks when it changes. External users (outside this repository) are written as ``~/...`` paths.
* ``marks.py`` — the marks that say a file relies on Claude Code, and the scan the ledger gate runs
  (tests/test_cc_dependency_ledger.py: CI and the full suite).
* ``probes.py`` — one probe per entry: it reads the CLI's current shape (help text, a recorded session's
  transcript and hook inputs) into a small JSON shape that the watcher compares with the shape saved last time.
* ``watch.py`` — the daily run (a user LaunchAgent): versions, the CHANGELOG lines only when the version moved, every
  probe against the saved shapes; on red a ticket in docs/bugs and a notice to the orchestrator, on green a log line.
"""
