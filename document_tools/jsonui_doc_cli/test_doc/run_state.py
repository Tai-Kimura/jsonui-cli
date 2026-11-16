"""Every per-run ledger, registered where it is defined and cleared in one place.

A "per-run ledger" is module-level state that accumulates during one
`generate html` and must be empty at the start of the next one: pages
written, warnings already reported, counters, the slot-sharing notice's
dedupe set.

🔻 REGISTERED AT THE DEFINITION, NOT LISTED IN THE RESET. The reset used to
carry a hand-written list, and a tenth ledger
(`html/sidebar.py:_REPORTED_SHARED_SLOTS`) was added without being added to
it — so it cleared itself inside one test file instead, which reaches only
the arms that remembered. A hand-written population carries the author's
blind spot into the thing meant to find it. Here you cannot create a ledger
without registering it, because `ledger()` IS the creation.

⚠️ THE NAME IS PART OF THE REGISTRATION. `ledger()` takes the namespace and
the name as well as the factory, so `tests/test_every_per_run_ledger_is_reset_in_one_place.py`
can read the module's source with `ast` and check that what is registered
matches what is defined. That check derives its population from the SOURCE,
not from this registry: a check that shared the registry's derivation would
agree with it no matter what either one said.
"""
from __future__ import annotations

from typing import Any, Callable, NamedTuple


class Entry(NamedTuple):
    """One registered ledger. `namespace` is the defining module's globals."""
    namespace: dict
    name: str
    factory: Callable[[], Any]
    reset: Callable[[], None] | None


_REGISTRY: list[Entry] = []


def ledger(namespace: dict, name: str, factory: Callable[[], Any]) -> Any:
    """Create a per-run ledger and register it. Returns the new value.

    Call it in the assignment that defines the ledger:

        _pages_written: set = run_state.ledger(globals(), "_pages_written", set)
    """
    _REGISTRY.append(Entry(namespace, name, factory, None))
    return factory()


def external(reset: Callable[[], None], label: str) -> None:
    """Register per-run state that resets itself (`run_log.reset`).

    Kept in the same registry so `reset_per_run_ledgers()` is the whole
    answer to "what does a fresh run start from", rather than the answer for
    the ledgers this module happens to own.
    """
    _REGISTRY.append(Entry({}, label, lambda: None, reset))


def registered_names(namespace: dict) -> set[str]:
    """The names registered from one module's globals. For the check."""
    return {e.name for e in _REGISTRY if e.namespace is namespace}


def all_registered_names() -> set[str]:
    """Every registered name, whichever module defined it."""
    return {e.name for e in _REGISTRY}


def entries() -> tuple[Entry, ...]:
    """The registry, for the arm that clears every ledger and looks."""
    return tuple(_REGISTRY)


def reset_per_run_ledgers() -> None:
    """Start a fresh accounting run: empty every registered ledger.

    🔻 CLEARED IN PLACE WHERE THE OBJECT SUPPORTS IT. Rebinding would give
    the module a new object while any caller holding the old one kept
    writing to a ledger nothing reads. Only values without `.clear()` (the
    integer counters) are rebound from their factory.
    """
    for entry in _REGISTRY:
        if entry.reset is not None:
            entry.reset()
            continue
        current = entry.namespace.get(entry.name)
        clear = getattr(current, "clear", None)
        if callable(clear):
            clear()
        else:
            entry.namespace[entry.name] = entry.factory()
