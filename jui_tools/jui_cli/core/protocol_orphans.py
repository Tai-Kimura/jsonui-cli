"""The protocol files `jui build` / `jui g project` derive from screen specs, left behind when the spec is gone.

Ticket jui-build-leaves-orphan-protocol-and-kjui-view-after-screen-removal (2.5.33): a screen's spec and layout
were deleted and `jui build` removed its Data, its GeneratedView, its web outputs and its distributed layouts — the
layout-side sweep (shared/core/generated_orphans.rb) — but kept its ViewModelProtocol on both OS, and a Repository
or UseCase protocol that only that spec declared. Nothing in the build looks at a protocol whose spec is gone: the
three syncs walk the specs that exist. A kept ViewModelProtocol names the deleted <Screen>Data, so the next compile
fails.

The rule here, per kind (ViewModel, Repository, UseCase) and per platform with a separate protocol file (iOS,
Android; the web's repository and use case are the implementation itself, and its ViewModel base is rjui's):

  A file is DELETED only when all of these hold:
    1. it is in the directory the generator writes that kind of protocol to (for an iOS ViewModel, any
       `Protocol` directory under `ViewModel/`, since a screen in a layout subdirectory gets its own) and has
       the name the generator gives that kind;
    2. its first lines carry the @generated sentinel AND the `Source:` line that generator writes for that kind,
       naming this file's own name (`dataFlow.viewModel + <Name>ViewModel marker sync`, `aggregated repositories
       from ... (<Name>)`, `aggregated use cases from ... (<Name>)`);
    3. the path is not one the current specs give: no spec has that screen (at that subdirectory), and no spec
       declares that repository or use case.

  Nothing is deleted when a spec file could not be read (bad JSON, a type this build does not know): its
  screen is missing from the set for a reason that is not "deleted", and its protocols would be taken as
  orphans. The run says so instead. Nothing is deleted when no spec was loaded either — an empty set cannot
  tell "every screen was deleted" from "this is not the spec directory" (the layout sweep's guard).

A file without the banner is the user's and is left alone without a word: a hand-written protocol for a screen
that never had a spec is the user's business, and naming it on every build would bury the warnings that matter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .generated_marker import SENTINEL

HEAD_LINES = 12


@dataclass
class Kind:
    label: str
    # Every candidate file of this kind on this platform.
    candidates: Callable[[], Iterable[Path]]
    # The name the generator wrote the file for, from its path (None: not this kind's name).
    name_of: Callable[[Path], str | None]
    # What the generator's banner says for <name>, every piece of which must be in the file's first lines.
    marks: Callable[[str], list[str]]
    expected: set[Path] = field(default_factory=set)


def _head(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            return "".join(line for _, line in zip(range(HEAD_LINES), f))
    except OSError:
        return ""


def owned(path: Path, kind: Kind) -> bool:
    name = kind.name_of(path)
    if not name:
        return False
    head = _head(path)
    return SENTINEL in head and all(m in head for m in kind.marks(name))


def sweep(kinds: Iterable[Kind], *, dry_run: bool = False) -> list[Path]:
    """Delete (or, dry, list) every owned candidate whose path the specs no longer give."""
    removed: list[Path] = []
    for kind in kinds:
        expected = {p.resolve() for p in kind.expected}
        for path in sorted(set(kind.candidates())):
            if not path.is_file() or path.resolve() in expected:
                continue
            if not owned(path, kind):
                continue
            if not dry_run:
                path.unlink()
            removed.append(path)
    return removed


def _strip(stem: str, suffix: str) -> str | None:
    return stem[: -len(suffix)] if stem.endswith(suffix) and len(stem) > len(suffix) else None


def kinds_for(platform: str, generator, *, screens: list[tuple[str, str]], repositories: Iterable[str],
              use_cases: Iterable[str]) -> list[Kind]:
    """The three kinds on one platform, their candidates found where `generator` writes them.

    screens: (screen name, layout subdirectory) for every loaded spec.
    """
    if platform not in ("ios", "android"):
        return []
    ext = ".swift" if platform == "ios" else ".kt"
    vm_proto_dir = generator.viewmodel_protocol_path("X").parent
    if platform == "ios":
        # ViewModel/Protocol and ViewModel/<Sub>/Protocol (a screen whose layout sits in a subdirectory).
        vm_root = vm_proto_dir.parent

        def vm_candidates():
            if not vm_root.is_dir():
                return []
            return [p for p in vm_root.rglob(f"*ViewModelProtocol{ext}") if p.parent.name == "Protocol"]
    else:
        def vm_candidates():
            return vm_proto_dir.glob(f"*ViewModelProtocol{ext}") if vm_proto_dir.is_dir() else []

    repo_dir = generator.repository_protocol_path("X").parent
    uc_dir = generator.usecase_protocol_path("X").parent
    repo_suffix = "Protocol" if generator.repository_protocol_path("X").stem == "XProtocol" else ""
    uc_suffix = "Protocol" if generator.usecase_protocol_path("X").stem == "XProtocol" else ""

    def in_dir(d: Path):
        return (lambda: d.glob(f"*{ext}") if d.is_dir() else [])

    def name_by_suffix(suffix: str):
        def name_of(p: Path) -> str | None:
            if p.suffix != ext:
                return None
            return _strip(p.stem, suffix) if suffix else p.stem
        return name_of

    vm = Kind(
        label="ViewModel",
        candidates=vm_candidates,
        name_of=lambda p: _strip(p.stem, "ViewModelProtocol") if p.suffix == ext else None,
        marks=lambda name: [f"dataFlow.viewModel + {name}ViewModel marker sync"],
        expected={generator.viewmodel_protocol_path(name, subdir) for name, subdir in screens},
    )
    # An aggregated kind's banner ends its Source line with `(<Name>)`, the file's own declaration.
    repo = Kind(
        label="Repository",
        candidates=in_dir(repo_dir),
        name_of=name_by_suffix(repo_suffix),
        marks=lambda name: ["aggregated repositories from", f"({name})"],
        expected={generator.repository_protocol_path(n) for n in repositories},
    )
    uc = Kind(
        label="UseCase",
        candidates=in_dir(uc_dir),
        name_of=name_by_suffix(uc_suffix),
        marks=lambda name: ["aggregated use cases from", f"({name})"],
        expected={generator.usecase_protocol_path(n) for n in use_cases},
    )
    return [vm, repo, uc]
