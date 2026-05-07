"""Centralized JsonUI hotloader.

Watches ``docs/screens/layouts/`` and ``docs/screens/styles/``, resolves
``style`` merges and ``include`` expansions, filters platform-specific
fields, and serves the resulting flat layout JSON to iOS and Android
runtime clients over HTTP + WebSocket.

This package replaces the legacy ``sjui hotload`` (Node.js server.js) and
``kjui hotload`` (Node.js server.js) implementations.
"""
