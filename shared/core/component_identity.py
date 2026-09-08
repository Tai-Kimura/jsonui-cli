"""What a custom component's IDENTITY is, and how a screen's declarations resolve to it.

Ruled 2026-09-08 (user): **a component's identity is its own spec's
`metadata.name`, and that field is REQUIRED.**

Until this ruling `unit_target_ownership.owner_screens` took
`components_declared_by_screen` and no production caller passed it, because
nothing in the toolchain defined what a component contributes to an owner
set. That gap was not an oversight — it was refused deliberately, because
every reader of `metadata.name` in this repo supplies a default:

    html_generator.py:1994 / :2165      default "Component"
    html_generator.py:91 / :1082        default "Screen"
    markdown_generator.py:74            default "Screen"
    test_doc/html/screen.py:39          default file_path.stem
    test_doc/markdown/generator.py:41   default file_path.stem
    validator.py:473 / :3433            default ""
    production reading a REQUIRED metadata["name"]:  0 sites

⭐ The precedent that resolves it was already in the codebase. The one reader
that uses the name for MATCHING rather than display supplies no default and
declines instead (`document_tools/jsonui_doc_cli/cli.py`, component-usage
search):

    name = ((data.get("metadata") or {}).get("name") ...)
    if not isinstance(name, str) or not name:
        return None            # "cannot answer", never a substitute
    needle = f'"{name}"'

So the split was already practised: **display may substitute, matching may
not.** This module makes that the rule instead of a habit, which is why
`identity_of` returns None rather than a stem, a display name, or
`"Component"`. A default here would merge every unnamed component onto one
target and every same-named file across directories onto each other — and
the merge would be invisible, because a wrong owner set still classifies.

⚠️ **A screen's `customComponents[]` entry carries its OWN `name` beside
`specFile`.** That is a second spelling of the same fact, so this module
reports disagreement rather than picking a winner: two spellings that can
drift are how one rule becomes two implementations. The component spec is
the identity; the screen's entry is checked against it.

📌 **Direction matters here.** Adding this source can only RAISE an owner
count. That makes the screen-level direction (`>= 2 owners`) safe either
way, and it is what finally makes the app-level direction sound: the hint
it emitted was untrustworthy precisely because a missing source could turn
a true 2 into a reported 1. With this wired, that descent is gone.

This module is PURE. Resolving an identity means reading component spec
files, so the caller supplies a reader; nothing here touches the filesystem.
"""

from __future__ import annotations

#: The component spec field that IS the identity. Named once so a check and a
#: generator cannot disagree about where to look.
IDENTITY_PATH = ("metadata", "name")

#: `specFile` values are resolved against `component_spec_directory` from
#: jui.config.json, as a bare file name. Measured on the two shapes that
#: exist: one face keeps screens and components in the SAME directory, and
#: another keeps `../docs/user/screens/json` and `../docs/user/components/json`
#: apart while still naming `headermenu.component.json` with no path. So the
#: screen's directory is NOT the frame — the configured component directory is.
SPEC_FILE_SUFFIX = ".component.json"

#: A declaration whose component spec could not be read at all.
UNREADABLE = "unreadable"
#: A component spec that exists but declares no identity.
NO_IDENTITY = "no_identity"
#: The screen's entry and the component spec name it differently.
DISAGREES = "disagrees"
#: The entry names no `specFile`, so there is nothing to resolve.
NO_SPEC_FILE = "no_spec_file"


def identity_of(component_spec) -> str | None:
    """The identity *component_spec* declares, or None if it declares none.

    ⚠️ None is "this component has no identity", never a placeholder. Callers
    must not substitute the file stem: two components named `picker.component
    .json` in different directories are different components, and folding them
    together produces an owner set that is wrong in a way nothing reports.
    """
    if not isinstance(component_spec, dict):
        return None
    section = component_spec
    for key in IDENTITY_PATH[:-1]:
        section = section.get(key) if isinstance(section, dict) else None
        if not isinstance(section, dict):
            return None
    name = section.get(IDENTITY_PATH[-1])
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip()


def declared_components(screen_spec) -> list[dict]:
    """`structure.customComponents[]` of *screen_spec*, entries only.

    Returns [] for every shape that is not a list of dicts, so a malformed
    section contributes nothing rather than raising inside an ownership sweep.
    """
    if not isinstance(screen_spec, dict):
        return []
    structure = screen_spec.get("structure")
    if not isinstance(structure, dict):
        return []
    entries = structure.get("customComponents")
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def resolve_declared_identities(screen_specs, read_component):
    """``(components_declared_by_screen, problems)`` for one app.

    *screen_specs* maps screen name to its merged spec, exactly as
    `unit_target_ownership.owner_screens` expects.
    *read_component* is called with a `specFile` value and returns the parsed
    component spec, or None when it cannot be read. Keeping it a callable is
    what keeps this module pure — and it lets a test drive the whole rule
    without a directory.

    *problems* is a list of ``(kind, screen, spec_file, detail)`` tuples using
    the constants above. They are returned rather than raised: a face with one
    unnamed component must still get an ownership answer for its other
    components, and the caller decides the severity of each kind.

    ⚠️ A screen with an unresolvable declaration contributes NOTHING for that
    entry — it is not silently given the entry's own `name`. Falling back to
    the screen's spelling would make the disagreement it is meant to catch
    unobservable, because both sides would then read the same value.
    """
    declared: dict[str, list[str]] = {}
    problems: list[tuple] = []
    for screen in sorted(screen_specs or {}):
        identities: list[str] = []
        for entry in declared_components((screen_specs or {}).get(screen)):
            spec_file = entry.get("specFile")
            entry_name = entry.get("name")
            if not isinstance(spec_file, str) or not spec_file.strip():
                problems.append((NO_SPEC_FILE, screen, None, entry_name))
                continue
            spec_file = spec_file.strip()
            component = read_component(spec_file)
            if component is None:
                problems.append((UNREADABLE, screen, spec_file, entry_name))
                continue
            identity = identity_of(component)
            if identity is None:
                problems.append((NO_IDENTITY, screen, spec_file, entry_name))
                continue
            if isinstance(entry_name, str) and entry_name.strip() and entry_name.strip() != identity:
                problems.append((DISAGREES, screen, spec_file,
                                 (entry_name.strip(), identity)))
            if identity not in identities:
                identities.append(identity)
        declared[screen] = identities
    return declared, problems
