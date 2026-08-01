"""Setup for jui_tools."""
from pathlib import Path

from setuptools import setup, find_packages

# Single-source toolchain version: the VERSION file at the jsonui-cli root.
# Present in both install layouts (git checkout and the bootstrap-cloned
# ~/.jsonui-cli, whose cleanup keeps root files other than the installer's).
_VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()

setup(
    name="jui-tools",
    version=_VERSION,
    description="JsonUI cross-platform project tool",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "watchdog>=4.0.0",
        "aiohttp>=3.9.0",
        # YAML swagger input (`jui build` api-model sync). Imported lazily
        # by openapi_loader with a guided halt when missing, so consumers
        # on the rsync/sync_tool path (no pip re-run) don't break.
        "PyYAML>=6.0",
    ],
    extras_require={
        # Screenshot baseline hashing (`jui conformance baseline` + the
        # visual-regression section of `jui conformance report`). Optional:
        # everything else works without it, baseline features raise a clear
        # error pointing here when Pillow is missing.
        "conformance": ["Pillow>=10.0.0"],
    },
    entry_points={
        "console_scripts": [
            "jui=jui_cli.cli:main",
        ],
    },
)
