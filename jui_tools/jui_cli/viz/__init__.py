"""``jui viz`` — a local browser view of the Claude Code sessions on this machine.

The server (``server.py``) listens on 127.0.0.1 only, collects hook events,
``claude agents --json`` and files under ``~/.claude/``, and streams state
slices to the page over a WebSocket. See dev-guide for the design.
"""
