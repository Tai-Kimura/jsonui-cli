"""A case other targets declare too, implemented by a test no target's name
places, is shown as `unattributed` — not as this target's implementation,
and not as unwritten.

`unit_contract_pages()` judges a (target, case) pair; for a case name several
targets declare, a test whose class, outermost describe and file name no
target cannot be told apart from the others' (`PAIR_UNATTRIBUTED`). The page
has to carry that state, and its per-face roll-up has to keep adding up.
"""
from __future__ import annotations

import re
import unittest

from jsonui_doc_cli.test_doc.html.unit import generate_unit_html


def _target() -> dict:
    return {
        "target": "BetaViewModel",
        "screens": ["beta"],
        "spec_files": ["beta.spec.json"],
        "cases": [
            {"name": "own", "intent": "", "platforms": ["ios"],
             "status": {"ios": "implemented"}},
            {"name": "shared", "intent": "", "platforms": ["ios"],
             "status": {"ios": "unattributed"}},
        ],
        "faces": {"ios": {"declared": ["own", "shared"], "implemented": ["own"],
                          "missing": [], "never_runs": [], "unattributed": ["shared"],
                          "files": []}},
    }


class UnattributedOnTheTargetPage(unittest.TestCase):
    def test_it_has_a_badge_of_its_own(self):
        html = generate_unit_html(_target(), ["ios"])
        self.assertIn("class='status status-unattributed'>unattributed<", html)
        self.assertNotIn("class='status status-missing'", html)

    def test_the_roll_up_adds_up_with_it(self):
        html = generate_unit_html(_target(), ["ios"])
        header = re.search(r"<tr><th>Face</th>(.*?)</tr>", html).group(1)
        self.assertEqual(re.findall(r"<th>(.*?)</th>", header),
                         ["Declared", "Implemented", "Missing", "Never runs", "Unattributed"])
        row = re.search(r"<tr><td><code>ios</code></td>(.*?)</tr>", html).group(1)
        declared, *parts = [int(n) for n in re.findall(r">(\d+)</td>", row)]
        self.assertEqual((declared, parts), (2, [1, 0, 0, 1]))
        self.assertEqual(declared, sum(parts))
