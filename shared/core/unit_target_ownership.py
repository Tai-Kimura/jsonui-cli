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
    component    reached through the layout's `include` closure

⚠️ The viewModel case is the one that looks absent and is not. Reading only
`dataFlow.viewModel` shows `description`/`methods`/`vars` and no identifier,
which invites the conclusion that a ViewModel has no derivable owner. It has
one: the generator's own naming rule. A predicate built without it reports
every ViewModel as owned by nobody — that is, as face-owned — which is the
opposite of the truth and arrives as a plausible larger count of face-owned
targets rather than as an error.

This module is PURE. The include closure needs to read layouts, so the caller
computes it and passes it in; see `components_by_screen` on `owner_screens`.
"""

from __future__ import annotations

#: `jui build` names a screen's ViewModel class this way
#: (`commands/build_cmd.py`, `f"{spec.name}ViewModel"`). Stated here so the
#: ownership rule and the generator cannot disagree about what a ViewModel is
#: called; the paired test compares this against the generator's own source.
VIEW_MODEL_SUFFIX = "ViewModel"

#: Exactly one screen owns it. It must be declared in that screen's spec.
SCREEN_OWNED = "screen_owned"

#: No screen owns it, or several do. A face-level declaration site is the only
#: one that records this truthfully.
FACE_OWNED = "face_owned"

#: Nothing owns it AND nothing in the project defines it — a misspelled target
#: reaches zero screens exactly as a shared utility does. Kept apart from
#: `FACE_OWNED` because collapsing them turns a typo into a permission.
UNRESOLVED = "unresolved"

#: The inputs needed to tell `FACE_OWNED` from `UNRESOLVED` were not supplied.
#: Never silently folded into either: a caller that has not computed the layout
#: closure would otherwise see every component-owned target as face-owned.
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
    components_by_screen: dict | None = None,
) -> list[str]:
    """Every screen that owns *target*, sorted.

    `screens` maps screen name to its merged spec dict. `components_by_screen`
    maps screen name to the set of targets its layout reaches through the
    `include` closure; ``None`` means the closure was not computed, and the
    component source is then simply absent from the answer — which is why
    `classify` refuses to call a zero result `FACE_OWNED` in that case.
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
        if components_by_screen and target in (components_by_screen.get(screen) or ()):
            owners.add(screen)
    return sorted(owners)


def classify(
    target: str,
    screens: dict,
    components_by_screen: dict | None = None,
    known_targets=None,
) -> tuple:
    """``(kind, owners)`` for *target*.

    `known_targets` is every symbol the project actually defines. Without it a
    target owned by no screen cannot be told from one that does not exist, so
    the answer is `UNDETERMINED` rather than a guess in either direction.
    """
    owners = owner_screens(target, screens, components_by_screen)
    if len(owners) == 1:
        return SCREEN_OWNED, owners
    if len(owners) >= 2:
        # Several screens own it, so no single screen's spec records the truth.
        # Unlike the zero case this needs no extra input: the target plainly
        # exists, because screens name it.
        return FACE_OWNED, owners
    if components_by_screen is None or known_targets is None:
        return UNDETERMINED, owners
    if target in known_targets:
        return FACE_OWNED, owners
    return UNRESOLVED, owners


def face_level_allowed(
    target: str,
    screens: dict,
    components_by_screen: dict | None = None,
    known_targets=None,
) -> bool:
    """May *target* be declared at face level?

    True only for `FACE_OWNED`. `UNDETERMINED` and `UNRESOLVED` are both false:
    a question that was not answered is not a permission.
    """
    kind, _ = classify(target, screens, components_by_screen, known_targets)
    return kind == FACE_OWNED
