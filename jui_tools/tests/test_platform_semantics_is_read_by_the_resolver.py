"""`shared/core/platform_semantics.json` is read, not only declared.

Measured 2026-09-10 (ticket canon-declares-fifteen-keys-nobody-reads): no
module loads this file — `git grep platform_semantics` finds no loader — and
mutating every string leaf under its six rule-shaped keys, then running the
whole gate list, moved nothing. Three of those keys ARE implemented, by
hand-mirrors in Python that nothing tied to the declaration:

    nodeDirective.stringForm.tokens     ≡ platform_resolver.PLATFORM_LANG_MAP
    nodeDirective.objectForm (detection) ≡ platform_resolver.VALID_PLATFORMS
    layoutRootPlatforms.attribute       ≡ build_cmd.ROOT_PLATFORMS_KEY

A mirror without a link drifts in silence: rename a token in the canon and
the resolver keeps the old one, every suite green — the shape v1.8.63's
`diagram.nodeSource` had. These arms take their EXPECTED value from the
canon, so an edit on either side turns them red. Until today nothing
imported PlatformResolver from a test at all, so the behavioural arms below
are also the first pins of the filter and the merge.

Mutations these were fired against (each red under exactly the arm named):
  canon tokens.ios gains "objc"            → test_the_token_table_is_the_canons
  PLATFORM_LANG_MAP["web"] loses "react"   → test_the_token_table_is_the_canons
  canon layoutRootPlatforms.attribute → "targets"  → test_the_root_whitelist_key_is_the_canons
  build_cmd.ROOT_PLATFORMS_KEY → "platform"        → test_the_root_whitelist_key_is_the_canons
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "jui_tools"))

from jui_cli.commands import build_cmd  # noqa: E402
from jui_cli.core import platform_resolver as pr  # noqa: E402

CANON_PATH = REPO_ROOT / "shared" / "core" / "platform_semantics.json"


def _canon() -> dict:
    return json.loads(CANON_PATH.read_text(encoding="utf-8"))


class TheStringFormIsTheCanons(unittest.TestCase):
    def setUp(self):
        self.canon = _canon()
        self.tokens = self.canon["nodeDirective"]["stringForm"]["tokens"]

    def test_the_token_table_is_the_canons(self):
        # Sets on both sides: the canon lists, the resolver keeps a set, and
        # order is not part of the rule.
        self.assertEqual({k: set(v) for k, v in self.tokens.items()},
                         {k: set(v) for k, v in pr.PLATFORM_LANG_MAP.items()})

    def test_the_platform_names_are_the_canons(self):
        self.assertEqual(set(self.tokens), set(pr.VALID_PLATFORMS))

    def test_a_canon_token_keeps_the_node_and_a_foreign_one_drops_it(self):
        # Behaviour driven by the canon's own table: the second token of each
        # platform (never the platform name itself, so the alias path is the
        # one exercised).
        for platform, toks in self.tokens.items():
            with self.subTest(platform=platform):
                own = toks[1]
                other = next(t[1] for p, t in self.tokens.items() if p != platform)
                r = pr.PlatformResolver(platform)
                kept = r.resolve_tree({"type": "View", "platform": own, "child": []})
                dropped = r.resolve_tree({"type": "View", "platform": other, "child": []})
                self.assertIsNotNone(kept, (platform, own))
                self.assertIsNone(dropped, (platform, other))
                self.assertNotIn("platform", kept, "the directive is consumed, not distributed")

    def test_comma_separated_tokens_are_each_honoured(self):
        # canon stringForm.summary: "Comma-separated tokens allowed".
        ios, android = self.tokens["ios"][0], self.tokens["android"][0]
        node = {"type": "View", "platform": f"{ios}, {android}"}
        self.assertIsNotNone(pr.PlatformResolver("ios").resolve_tree(dict(node)))
        self.assertIsNotNone(pr.PlatformResolver("android").resolve_tree(dict(node)))
        self.assertIsNone(pr.PlatformResolver("web").resolve_tree(dict(node)))


class ResponsiveIsLeftForTheRuntime(unittest.TestCase):
    """canon vsResponsive: `responsive` is resolved at RUNTIME; `platform` at
    distribution. So the resolver must pass `responsive` through untouched on
    every platform while consuming `platform`."""

    def test_responsive_is_left_for_the_runtime(self):
        responsive = {"compact": {"orientation": "vertical"}, "regular": {"orientation": "horizontal"}}
        for platform in _canon()["nodeDirective"]["stringForm"]["tokens"]:
            with self.subTest(platform=platform):
                node = {"type": "View", "platform": platform, "responsive": json.loads(json.dumps(responsive))}
                out = pr.PlatformResolver(platform).resolve_tree(node)
                self.assertEqual(out["responsive"], responsive)
                self.assertNotIn("platform", out)


class TheObjectFormIsTheCanons(unittest.TestCase):
    def setUp(self):
        self.canon = _canon()
        self.platforms = list(self.canon["nodeDirective"]["stringForm"]["tokens"])

    def test_a_map_keyed_by_the_canons_platforms_is_an_override_map(self):
        self.assertTrue(pr.PlatformResolver._is_override_map({p: {"h": 1} for p in self.platforms}))

    def test_a_stray_key_makes_it_not_an_override_map(self):
        # canon objectForm.detection: "ONLY when every key is one of ios/android/web"
        m = {self.platforms[0]: {"h": 1}, "class": "x"}
        self.assertFalse(pr.PlatformResolver._is_override_map(m))

    def test_the_override_wins_for_the_matching_platform_only(self):
        node = {"type": "View", "height": 200,
                "platform": {p: {"height": 100 + i} for i, p in enumerate(self.platforms)}}
        for i, p in enumerate(self.platforms):
            with self.subTest(platform=p):
                out = pr.PlatformResolver(p).resolve_tree(json.loads(json.dumps(node)))
                self.assertEqual(out["height"], 100 + i)
                self.assertNotIn("platform", out)


class TheRootWhitelistIsTheCanons(unittest.TestCase):
    def test_the_root_whitelist_key_is_the_canons(self):
        self.assertEqual(build_cmd.ROOT_PLATFORMS_KEY,
                         _canon()["layoutRootPlatforms"]["attribute"])


CANONS = ("screen_identity", "platform_semantics", "binding_semantics", "attribute_semantics")
#: Derived from the tree, not listed by hand: a path is checked when its first
#: segment is a directory at the repository root.
TOP_LEVEL_DIRS = {p.name for p in REPO_ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")}


class EveryReadByNamesAFileThatExists(unittest.TestCase):
    """The declaration form is prose (the canon's own `readBy` / `<key>ReadBy`
    convention); the least it can promise is that every path it names is in
    the tree. Over all four canons, so a declaration that names a file which
    is later moved or deleted goes red here rather than pointing at nothing."""

    @staticmethod
    def _declarations() -> list[tuple[str, str, str]]:
        found: list[tuple[str, str, str]] = []

        def walk(canon, o, where=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    if (k == "readBy" or k.endswith("ReadBy")) and isinstance(v, str):
                        for m in re.findall(r"[\w./-]+\.(?:py|rb|ts)", v):
                            # Only paths that start inside this repository are
                            # claims about this tree; a driver or library file
                            # named as "outside this repository" is prose.
                            if m.split("/", 1)[0] in TOP_LEVEL_DIRS:
                                found.append((canon, f"{where}.{k}" if where else k, m))
                    walk(canon, v, f"{where}.{k}" if where else k)
            elif isinstance(o, list):
                for v in o:
                    walk(canon, v, where)

        for canon in CANONS:
            walk(canon, json.loads((REPO_ROOT / "shared" / "core" / f"{canon}.json").read_text(encoding="utf-8")))
        return found

    def test_every_readby_path_exists(self):
        decls = self._declarations()
        # Floor, not a count: 3 in platform_semantics + 4 in binding_semantics
        # added 2026-09-10, plus whatever screen_identity carried before.
        self.assertGreaterEqual(len(decls), 9, decls)
        missing = [(c, w, p) for c, w, p in decls if not (REPO_ROOT / p).is_file()]
        self.assertEqual(missing, [])

    def test_the_walk_sees_more_than_one_canon(self):
        # Control on the instrument: an empty walk over three canons would
        # make the arm above green for nothing.
        self.assertGreaterEqual(len({c for c, _, _ in self._declarations()}), 2)


class EveryDeclaredVectorExists(unittest.TestCase):
    """A binding rule that is pinned by executable vectors names them
    (`vectors` / `<key>Vectors`), and every named id must be a case in
    `shared/core/binding_vectors.json` — the file the SwiftJsonUI and
    KotlinJsonUI suites vendor and run. The link canon→vector is verified
    here; vector→behaviour is verified there."""

    VECTORS = REPO_ROOT / "shared" / "core" / "binding_vectors.json"

    @classmethod
    def _declared(cls) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []

        def walk(o, where=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    if (k == "vectors" or k.endswith("Vectors")) and isinstance(v, list):
                        out.extend((f"{where}.{k}" if where else k, i) for i in v)
                    walk(v, f"{where}.{k}" if where else k)
            elif isinstance(o, list):
                for v in o:
                    walk(v, where)

        walk(json.loads((REPO_ROOT / "shared" / "core" / "binding_semantics.json").read_text(encoding="utf-8")))
        return out

    def test_every_declared_vector_is_a_case(self):
        ids = {c["id"] for c in json.loads(self.VECTORS.read_text(encoding="utf-8"))["cases"]}
        declared = self._declared()
        self.assertGreaterEqual(len(declared), 20, declared)  # 6 + 9 + 1 + 4 declared 2026-09-10
        self.assertEqual([(w, i) for w, i in declared if i not in ids], [])

    def test_the_declarations_span_more_than_one_key(self):
        self.assertGreaterEqual(len({w for w, _ in self._declared()}), 4)


if __name__ == "__main__":
    unittest.main()


class ADeclarationSitsBesideTheKeyItDescribes(unittest.TestCase):
    """`<key>ReadBy` and `<key>Vectors` must have `<key>` as a sibling.

    The existence arms above check that a readBy names a real file and that
    a vector id names a real case — neither checks WHICH key a declaration
    hangs under. Measured 2026-09-10: `embedParamsTypesVectors` and
    `embedParamsTypesReadBy` landed inside `collectionCellScope` (the insert
    anchored on a neighbour) while `embedParamsTypes` itself is top-level,
    and 13 arms stayed green. Position is the definition of ownership, so a
    detector that reads only position cannot see this; the independent fact
    is the suffix convention, and this arm holds it.
    """

    SUFFIXES = ("ReadBy", "Vectors")

    def test_every_suffixed_declaration_has_its_key_as_a_sibling(self):
        from pathlib import Path
        import json
        core = Path(__file__).resolve().parents[2] / "shared" / "core"
        orphans = []

        def walk(node, path):
            if not isinstance(node, dict):
                return
            for key, value in node.items():
                for suffix in self.SUFFIXES:
                    if key.endswith(suffix) and len(key) > len(suffix):
                        base = key[: -len(suffix)]
                        if base not in node:
                            orphans.append(f"{path}.{key} (no sibling {base!r})")
                walk(value, f"{path}.{key}")

        checked = 0
        for name in ("screen_identity.json", "platform_semantics.json",
                     "binding_semantics.json", "attribute_semantics.json"):
            walk(json.loads((core / name).read_text(encoding="utf-8")), name)
            checked += 1
        self.assertEqual(checked, 4)
        self.assertEqual(orphans, [], "\n".join(orphans))
