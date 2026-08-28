"""JsonUI Test CLI - Validate and generate documentation for JsonUI test files."""

from pathlib import Path

# `--version` is how a consumer decides whether the tool they are running is
# the one they synced. A literal here answers with the version this package
# was written at, not the toolchain it currently belongs to, which is how a
# stale copy on PATH went on claiming a plausible number while serving code
# from months earlier. Read the toolchain's VERSION instead; the literal
# survives only for a tree installed without it.
_FALLBACK_VERSION = "1.7.0"


def _toolchain_version() -> str:
    try:
        text = (Path(__file__).resolve().parents[2] / "VERSION").read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        return _FALLBACK_VERSION
    return text or _FALLBACK_VERSION


__version__ = _toolchain_version()
