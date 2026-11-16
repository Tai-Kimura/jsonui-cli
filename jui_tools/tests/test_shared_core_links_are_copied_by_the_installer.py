"""Every file a tool's lib/ reaches through a link into shared/core is copied there by the installer.

In the repository sjui_tools / kjui_tools / rjui_tools link attribute_definitions.json, type_synonyms.json and
retired_attribute_spellings.json from shared/core; the installed tree holds the files themselves, which
installer/bootstrap.sh copies (`for shared_json in …`). A link the list leaves out ships as a link to nothing: the tool
installed in a consumer reads no file there (2.3.22: retired_attribute_spellings.json was added to the list with the
links, and no test said the two must agree).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ("sjui_tools", "kjui_tools", "rjui_tools")
SHARED = (ROOT / "shared" / "core").resolve()
BOOTSTRAP = ROOT / "installer" / "bootstrap.sh"


def _links() -> dict:
    """tool -> {file name} of the links under its lib/ that resolve into shared/core."""
    out = {}
    for tool in TOOLS:
        names = set()
        for path in (ROOT / tool / "lib").rglob("*"):
            if path.is_symlink() and path.resolve().parent == SHARED:
                names.add(path.name)
        out[tool] = names
    return out


def _copied() -> set:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    m = re.search(r"^for shared_json in ([^;]+); do$", text, flags=re.M)
    assert m, "installer/bootstrap.sh has no `for shared_json in …; do` loop"
    return set(m.group(1).split())


def test_every_link_into_shared_core_is_in_the_installers_copy_list_and_back():
    links, copied = _links(), _copied()
    linked = set().union(*links.values())
    assert "attribute_definitions.json" in linked, f"the scan found none of the links it is about: {links}"
    assert not linked - copied, f"linked into a tool, not copied by bootstrap.sh: {sorted(linked - copied)}"
    assert not copied - linked, f"copied by bootstrap.sh, linked from no tool: {sorted(copied - linked)}"
    uneven = {tool: sorted(copied - names) for tool, names in links.items() if names != copied}
    assert not uneven, f"a tool lacks a link the others have: {uneven}"


def test_the_copy_loop_reaches_every_tool():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    m = re.search(r"for tool_dir in ([^;]+); do", text)
    assert m and set(m.group(1).split()) == set(TOOLS), m and m.group(1)
    for name in _copied():
        assert (SHARED / name).is_file(), f"bootstrap.sh copies {name}, which shared/core does not hold"
