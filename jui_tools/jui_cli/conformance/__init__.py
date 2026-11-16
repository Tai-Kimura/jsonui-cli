"""Conformance harness: fixture generation + cross-platform report.

Generates "component x attribute" test fixtures (Layout JSON + jsonui-test-runner
screen tests) from ``shared/core/attribute_definitions.json`` and merges per-platform
results into a compatibility matrix (``REPORT.md``).

Modules:

- :mod:`rules` — declarative attribute classification + representative values
- :mod:`fixture_generator` — layout / test / manifest emission
- :mod:`report` — results merge + REPORT.md
"""
