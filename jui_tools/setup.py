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
    # The iOS home-indicator template the conformance gate compares against.
    package_data={"jui_cli.conformance": ["data/*.png"]},
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
        #
        # 🔻 Capped below 13: every committed hash (baselines/ci, baselines/
        # local, codegen parity) was computed with Pillow 12, and 13 resamples
        # the 9x8 LANCZOS reduction differently. conformance-mobile run
        # 39012627109 installed 13.0.0 and its gate read 99 iOS screenshots
        # as visual regressions whose bytes were identical (md5) to run
        # 38958247680's, which 12.3.0 judged with 0. Same inputs replayed
        # locally: 12.x 0, 13.0.0 99. Raising the cap means re-baking every
        # baseline with the new version in the same commit.
        "conformance": ["Pillow>=10.0.0,<13"],
    },
    entry_points={
        "console_scripts": [
            "jui=jui_cli.cli:main",
        ],
    },
)
