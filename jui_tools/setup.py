"""Setup for jui_tools."""
from setuptools import setup, find_packages

setup(
    name="jui-tools",
    version="0.2.0",
    description="JsonUI cross-platform project tool",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "watchdog>=4.0.0",
        "aiohttp>=3.9.0",
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
