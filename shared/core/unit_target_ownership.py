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
    component    ⚠️ NO SUCH FACT EXISTS YET — see the warning below

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

🚨 THE COMPONENT SOURCE IS UNDEFINED, NOT MERELY UNWIRED. An earlier
version of this docstring said a component is `structure.customComponents[]
.specFile` "resolved to the component spec's `metadata.name`". That was
written without reading the generator, and it is wrong twice over. Measured
2026-09-08 at v1.8.52:

    build_cmd.py references to `custom_components`      0
    `specFile` anywhere in jui_cli                      0
    any component → class-name convention              0
    (positive control: `specFile` IS present in document_tools, so the
     search was working and these zeros are real)

Nothing in this toolchain decides what a component contributes to an owner
set. Compare source 1, which HAS such a fact: `jui build` writes
`f"{spec.name}ViewModel"`, and that generator rule is what makes a
ViewModel's owner derivable at all.

`metadata.name` cannot be taken as that identity AS IT IS READ TODAY. Every
producer that displays it supplies a default — `"Component"`, `"Screen"`,
`""`, and in two places the file's own stem — and a string with a default
cannot be an identity: unnamed components would collapse onto one target, and
the stem fallback would merge distinct components sharing a filename. No
production site reads it as a required `metadata["name"]`.

⭐ But the codebase already draws the line this rule needs. The one reader
that uses the name for MATCHING rather than display supplies no default and
declines instead (`document_tools/.../cli.py`, component-usage search):

    name = ((data.get("metadata") or {}).get("name") ...)
    if not isinstance(name, str) or not name:
        return None            # "cannot answer", never a substitute
    needle = f'"{name}"'

while the sibling that reconciles DECLARATIONS matches by file name and never
opens `metadata.name` at all. So the split is already practised: display may
substitute, matching may not. A decision to make this source real would
follow that precedent — require the field where it carries identity — rather
than invent a convention.

So `components_declared_by_screen` stays a parameter with no production
caller, and a zero owner count stays `UNDETERMINED` rather than a permission.
Ruled 2026-09-08: inventing a convention here would add a third spelling to
the toolchain, so the limit is named instead of filled. Wiring this source
needs a spec decision about what a component's identity IS — not an
implementation.

This module is PURE: whatever that identity turns out to be, resolving it
needs to read component specs, so the caller would do that and pass the
result in; see `components_declared_by_screen` on `owner_screens`.
"""

from __future__ import annotations

#: `jui build` names a screen's ViewModel class this way
#: (`commands/build_cmd.py`, `f"{spec.name}ViewModel"`). Stated here so the
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
