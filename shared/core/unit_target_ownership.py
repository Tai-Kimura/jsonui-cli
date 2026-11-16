"""Which screens own a unit target — derived from the specs, not from where
the declaration happens to sit.

Ownership and declaration site had been the same thing: `discover_unit_contracts`
reads a target from whichever `*.spec.json` carries it and files it under that
file's basename. So "this is declared in the wrong place" could not be checked,
because the place WAS the definition, and a target belonging to no single screen
had to be filed under an unrelated one.

The specs already carry the facts; nothing was reading them:

    repository   `required: ["name", "methods"]` — "Repository class name"
    useCase      `required: ["name", "methods"]` — "UseCase class name"
    viewModel    carries NO name — but `jui build` generates the class as
                 `f"{spec.name}ViewModel"`, so the screen name determines it
                 ⚠️ `spec` there is the extracted `ScreenSpec` OBJECT, not the
                 JSON. Its `.name` is assigned `metadata.get("name", "")`
                 (`jui_cli/core/spec_extractor.py:404`). A spec file has no
                 top-level `name` field, so reading this as one finds None and
                 makes the rule look inapplicable — measured 2026-09-08, that
                 reading cost another lane a decision it could not close.
    component    a screen's `structure.customComponents[].specFile`,
                 resolved to that component spec's `metadata.name` —
                 required, and PascalCase-validated. Ruled 2026-09-08;
                 see below for why that took a ruling

⚠️ The viewModel case is the one that looks absent and is not. Reading only
`dataFlow.viewModel` shows `description`/`methods`/`vars` and no identifier,
which invites the conclusion that a ViewModel has no derivable owner. It has
one: the generator's own naming rule. A predicate built without it reports
every ViewModel as owned by nobody — that is, as app-owned — which is the
opposite of the truth and arrives as a plausible larger count of app-owned
targets rather than as an error.

⚠️ A component's owner is the screen that DECLARES it, not the layouts that
USE it. The two disagree today, and the component reconciliation check reports
that disagreement — but "the other side is broken" is not the reason to prefer
declaration, because that check reports BOTH directions and the argument would
cut equally either way. The reason is purity: a declaration is the spec's own
statement, readable from the spec set already in hand, while usage needs the
layout tree. Ownership stays a property of the specs.

🚨 SCOPE — `screens` must be ONE app's screens. A repository holding several
apps (`--app admin:… --app user:…`) that share a target name would report two
owners and call the target app-owned, and then no single app's contracts spec
could hold it. Ownership closes inside an app. Note the asymmetry this sits
on: discovery has no app concept (one `spec_directory` per project) while the
doc generator keys by app (`unit_by_app`), so the CALLER supplies the frame
and this module cannot check it.

⭐ THE COMPONENT SOURCE IS RULED, AND THE RULE WAS OLDER THAN THE QUESTION.
Ruled 2026-09-08: a component's identity IS its spec's `metadata.name`, and
the field is required. The history is kept because it explains the shape of
the answer, and because a reader who finds only the conclusion cannot tell a
ruling from an invention.

At v1.8.52 this docstring asserted that NO convention defined a component's
class name. Measured then:

    build_cmd.py references to `custom_components`      0
    `specFile` anywhere in jui_cli                      0
    any component → class-name convention in jui_tools  0

Those zeros are real, and they are also SCOPED — every one of them was
measured inside `jui_tools`, and the claim was written as though it covered
the toolchain. It did not. `document_tools`' validator has required a
component's `metadata.name` and enforced PascalCase on it since the initial
commit:

    _validate_required_fields(metadata, ["name", "displayName",
                                         "description"], "metadata", result)
    if name and not re.match(r"^[A-Z][a-zA-Z0-9]*$", name):  # class-shaped

So a convention existed the whole time, on the validating side, while the
GENERATING side never consumed it. "No fact exists" was the wrong reading of
"the generator does not use one". ⚠️ The lesson is not about components: a
zero says as much about where you looked as about what is there, and this one
was quoted into a decision before anyone asked what its scan root was.

What made `metadata.name` look unusable was its readers: every producer that
DISPLAYS it substitutes a default — `"Component"`, `"Screen"`, `""`, and in
two places the file's own stem — and a defaulted string cannot be an identity,
because unnamed components collapse onto one target and the stem fallback
merges distinct components sharing a filename.

But display is not the only reader, and the codebase already drew the line.
The one reader that uses the name for MATCHING supplies no default and
declines instead (`document_tools/.../cli.py`, component-usage search):

    name = ((data.get("metadata") or {}).get("name") ...)
    if not isinstance(name, str) or not name:
        return None            # "cannot answer", never a substitute

Display may substitute; matching may not. The ruling follows that line rather
than crossing it, which is why it required the field instead of blessing a
default — and why source 1 is sound on the same footing: `spec.name` is read
as `metadata.get("name", "")`, but the validator requires `metadata.name` on
a screen spec too, so the default is a reader's fallback and not the identity.

⚠️ A zero owner count still stays `UNDETERMINED` when the map is not supplied.
`None` and `{}` are different facts: `None` means the component specs could
not be read, `{}` means they were read and the project declares none. A caller
that reports both with one word turns a missing distribution into a clean
project.

This module is PURE: resolving `specFile` to `metadata.name` reads component
specs, so the caller does that and passes the result in; see
`components_declared_by_screen` on `owner_screens`.
"""

from __future__ import annotations

#: `jui build` names a screen's ViewModel class this way
#: (`commands/build_cmd.py:2447`, `f"{spec.name}ViewModel"`, where `spec.name`
#: is the JSON's `metadata.name` — see METADATA_NAME_PATH). Stated here so the
#: ownership rule and the generator cannot disagree about what a ViewModel is
#: called; the paired test compares this against the generator's own source.
VIEW_MODEL_SUFFIX = "ViewModel"

#: Exactly one screen owns it. It must be declared in that screen's spec.
SCREEN_OWNED = "screen_owned"

#: No screen owns it, or several do. An app-level declaration site is the only
#: one that records this truthfully.
APP_OWNED = "app_owned"

#: Nothing owns it AND nothing in the project defines it — a misspelled target
#: reaches zero screens exactly as a shared utility does. Kept apart from
#: `APP_OWNED` because collapsing them turns a typo into a permission.
UNRESOLVED = "unresolved"

#: The inputs needed to tell `APP_OWNED` from `UNRESOLVED` were not supplied.
#: Never silently folded into either: a caller that has not resolved the
#: components each screen DECLARES would otherwise see every component-owned
#: target as app-owned.
#:
#: What is missing is `components_declared_by_screen` — the screens'
#: the component identity a screen's `structure.customComponents[]`
#: declares — ⚠️ which nothing in this toolchain defines yet; read the
#: module docstring before building it. It is NOT a layout closure: nothing
#: here needs to read layouts, and a caller that goes looking for one is
#: answering a question this rule stopped asking.
UNDETERMINED = "undetermined"


#: Where the generator gets the name it puts in front of `ViewModel`.
#:
#: 🚨 Added 2026-09-08 after two consumer faces measured that nothing resolved.
#: `jui build` derives the ViewModel from `extract_screen_spec`, whose `name`
#: is `metadata.get("name", "")` — while the ownership caller keyed its
#: `screens` dict by the spec FILE NAME. On a face whose files are snake_case
#: and whose `metadata.name` is PascalCase, those never match, so EVERY
#: ViewModel-owned target resolved to zero owners:
#:
#:     widget_detail.spec.json + metadata.name "WidgetDetail"
#:       generator     -> "WidgetDetailViewModel"
#:       ownership was -> "widget_detailViewModel"
#:
#: Measured: one face 25 of 25 unowned, another 36 of 44, and 0 of 56 file
#: stems equal to their `metadata.name`.
#:
#: ⚠️ This stayed invisible because the paired test asserted the SUFFIX and
#: nothing else. The docstring claimed it "compares this against the
#: generator's own source"; it compared the string "ViewModel".
METADATA_NAME_PATH = ("metadata", "name")


def screen_name_from_spec(spec, file_stem: str) -> tuple[str, bool]:
    """``(name, used_fallback)`` — the name the GENERATOR would use.

    Returns the spec's `metadata.name` when it has one, else *file_stem* with
    ``used_fallback=True``.

    ⚠️ The flag exists because a silent fallback rebuilds the defect it is
    fixing, one spec at a time. A face where two of thirty specs fall back
    gets two unowned targets mixed in with every other unowned target, and
    nothing distinguishes them — which is exactly how the whole-face version
    of this went unnoticed until a face happened to show 25 of 25. The caller
    must SAY that it fell back; see the note it prints.
    """
    if isinstance(spec, dict):
        section = spec.get(METADATA_NAME_PATH[0])
        if isinstance(section, dict):
            name = section.get(METADATA_NAME_PATH[1])
            if isinstance(name, str) and name.strip():
                return name.strip(), False
    return file_stem, True


def view_model_name(screen: str) -> str:
    """The ViewModel class `jui build` generates for *screen*."""
    return f"{screen}{VIEW_MODEL_SUFFIX}"


def _declared_names(section) -> list[str]:
    """`name` of every entry in a `dataFlow` list section."""
    if not isinstance(section, list):
        return []
    out = []
    for entry in section:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                out.append(name.strip())
    return out


def owner_screens(
    target: str,
    screens: dict,
    components_declared_by_screen: dict | None = None,
) -> list[str]:
    """Every screen in ONE app that owns *target*, sorted.

    `screens` maps screen name to its merged spec dict, for a SINGLE app —
    see the scope warning in the module docstring.
    `components_declared_by_screen` maps screen name to the component
    identities that screen DECLARES. ⚠️ No production caller passes it,
    because nothing defines what that identity is — see the module
    docstring. ``None`` means it was not computed, and the component source
    is then absent from the answer, which is why `classify` refuses to call a
    zero result `APP_OWNED` then.
    """
    target = (target or "").strip()
    if not target:
        return []
    owners = set()
    for screen, spec in sorted(screens.items()):
        if target == view_model_name(screen):
            owners.add(screen)
        flow = (spec or {}).get("dataFlow") or {}
        if isinstance(flow, dict):
            if target in _declared_names(flow.get("repositories")):
                owners.add(screen)
            if target in _declared_names(flow.get("useCases")):
                owners.add(screen)
        if components_declared_by_screen and target in (components_declared_by_screen.get(screen) or ()):
            owners.add(screen)
    return sorted(owners)


def classify(
    target: str,
    screens: dict,
    components_declared_by_screen: dict | None = None,
    known_targets=None,
) -> tuple:
    """``(kind, owners)`` for *target*.

    `known_targets` is every symbol the project actually defines. Without it a
    target owned by no screen cannot be told from one that does not exist, so
    the answer is `UNDETERMINED` rather than a guess in either direction.
    """
    owners = owner_screens(target, screens, components_declared_by_screen)
    if len(owners) == 1:
        return SCREEN_OWNED, owners
    if len(owners) >= 2:
        # Several screens own it, so no single screen's spec records the truth.
        # Unlike the zero case this needs no extra input: the target plainly
        # exists, because screens name it.
        return APP_OWNED, owners
    if components_declared_by_screen is None or known_targets is None:
        return UNDETERMINED, owners
    if target in known_targets:
        return APP_OWNED, owners
    return UNRESOLVED, owners


def app_level_allowed(
    target: str,
    screens: dict,
    components_declared_by_screen: dict | None = None,
    known_targets=None,
) -> bool:
    """May *target* be declared at app level?

    True only for `APP_OWNED`. `UNDETERMINED` and `UNRESOLVED` are both false:
    a question that was not answered is not a permission.
    """
    kind, _ = classify(target, screens, components_declared_by_screen, known_targets)
    return kind == APP_OWNED
