"""JsonUI Document CLI - Generate documentation for JsonUI projects."""

from pathlib import Path

# See the note in jsonui_test_cli/__init__.py: `--version` has to name the
# toolchain the code belongs to, or it cannot be used to tell a synced copy
# from a stale one.
_FALLBACK_VERSION = "1.7.30"


def _toolchain_version() -> str:
    try:
        text = (Path(__file__).resolve().parents[2] / "VERSION").read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        return _FALLBACK_VERSION
    return text or _FALLBACK_VERSION


__version__ = _toolchain_version()
