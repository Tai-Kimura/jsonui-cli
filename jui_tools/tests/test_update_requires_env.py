"""`--update` refuses to write a ledger without knowing which env it measures.

The screenshot comparisons behind cross-effect, effect and inert-audit pick
their chrome bands by env: `ci` crops the android status bar, `local` must
not. The default is `local`, so `--update` against CI artifacts with the
flag forgotten records the android clock — 43 findings on the run-4
artifacts, every one inside the band — and the ledger keeps them with
nothing to say why.

Reads stay unguarded on purpose. A wrong env on a read shows wrong numbers
a reader can question; a wrong env on a write becomes the record.
"""
from __future__ import annotations

import argparse
import unittest

from jui_cli.commands.conformance_cmd import (
    _cmd_cross_effect,
    _cmd_effect,
    _cmd_inert_audit,
    _require_env_for_update,
)


def _args(**kw) -> argparse.Namespace:
    ns = argparse.Namespace(update=False, env=None)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


class GuardTest(unittest.TestCase):
    def test_update_without_env_is_refused(self):
        self.assertEqual(_require_env_for_update(_args(update=True)), 2)

    def test_update_with_env_passes(self):
        for env in ("local", "ci"):
            self.assertIsNone(_require_env_for_update(_args(update=True, env=env)))

    def test_reading_needs_no_env(self):
        """The default `local` is unchanged for reads."""
        self.assertIsNone(_require_env_for_update(_args(update=False)))


class CommandsAreWiredTest(unittest.TestCase):
    """Each writing command returns 2 before touching anything.

    The Namespace carries nothing but the two flags, so if a command got
    past the guard it would crash on the missing attributes — returning 2
    is proof the guard ran first, before any file was opened.
    """

    def test_all_three_refuse(self):
        for cmd in (_cmd_cross_effect, _cmd_effect, _cmd_inert_audit):
            self.assertEqual(cmd(_args(update=True)), 2, cmd.__name__)


if __name__ == "__main__":
    unittest.main()
