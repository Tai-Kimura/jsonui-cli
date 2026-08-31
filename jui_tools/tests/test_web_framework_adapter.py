"""The web scaffold asks the project's declaration instead of assuming Next.

Two literals in the scaffold guaranteed a red build for anyone whose layout
or framework differs: the network-layer import paths, and Next's router
type. The reported cost was not the red itself but its ATTRIBUTION — a
build that cannot compile the moment it is generated looks exactly like a
mistake by whoever ran the generator, and on the reporting day it was read
that way by someone else.

The framework half is not a missing option, it is a bypassed one.
`rjui.config.json` already carries `web_framework`, and rjui_tools'
`Core::Frameworks` resolves every framework-specific string from it —
"Emitters stay framework-neutral and ask the adapter". This generator was
a second implementation of that decision, so a project that declared a
custom adapter got a scaffold contradicting its own config.

NOTE ON EVIDENCE: no consumer declares `web_framework` today, so every real
corpus resolves to Next and would pass whatever this code did. The
non-default paths are therefore exercised here with planted declarations —
a green corpus is not evidence that the net is live.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jui_cli.core.spec_extractor import ScreenSpec, RepositoryDef, MethodDef
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.web_framework import WebFrameworkError, resolve
from jui_cli.generators.web_generator import (
    DEFAULT_API_CLIENT_MODULE, WebGenerator,
)

NEXT_ROUTER_IMPORT = (
    'import { AppRouterInstance } from '
    '"next/dist/shared/lib/app-router-context.shared-runtime";'
)


class TheAdapterMirrorsTheRubyResolution(unittest.TestCase):
    """Vectors from `Core::Frameworks.for`. The Python side reads only two
    of the adapter's fields, but it has to resolve them the same way — a
    mirror that drifts is how one tool starts disagreeing with the other
    about what the project declared."""

    def test_an_absent_declaration_means_next(self):
        self.assertEqual(resolve({})["router_type"], "AppRouterInstance")
        self.assertEqual(resolve(None)["router_type"], "AppRouterInstance")
        self.assertEqual(resolve({})["router_type_import"], NEXT_ROUTER_IMPORT)

    def test_a_builtin_name_resolves(self):
        self.assertEqual(resolve({"web_framework": "next"})["router_type"],
                         "AppRouterInstance")

    def test_an_unknown_builtin_name_is_an_error(self):
        with self.assertRaises(WebFrameworkError) as caught:
            resolve({"web_framework": "svelte"})
        self.assertIn("Unknown web_framework 'svelte'", str(caught.exception))

    def test_a_custom_adapter_takes_neutral_defaults(self):
        # CustomAdapter::DEFAULTS — no import, untyped router. A framework
        # the registry has never heard of is configurable, not blocked.
        values = resolve({"web_framework": {"name": "remix"}})
        self.assertEqual(values["router_type"], "any")
        self.assertEqual(values["router_type_import"], "")

    def test_a_custom_adapter_overrides_what_it_declares(self):
        values = resolve({"web_framework": {
            "name": "remix",
            "router_type_import": "import { NavigateFunction } from 'react-router-dom';",
            "router_type": "NavigateFunction",
        }})
        self.assertEqual(values["router_type"], "NavigateFunction")
        self.assertIn("react-router-dom", values["router_type_import"])

    def test_unknown_and_non_string_keys_are_errors(self):
        # Validated even for keys this generator never reads: a typo the
        # other tool rejects and this one accepts makes the two disagree
        # about whether the config is valid.
        with self.assertRaises(WebFrameworkError):
            resolve({"web_framework": {"routerType": "X"}})
        with self.assertRaises(WebFrameworkError):
            resolve({"web_framework": {"router_type": 7}})

    def test_a_wrong_shaped_declaration_is_an_error(self):
        with self.assertRaises(WebFrameworkError):
            resolve({"web_framework": ["next"]})


class TheScaffoldFollowsTheDeclaration(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _generator(self, rjui: dict | None = None) -> WebGenerator:
        if rjui is not None:
            (self.root / "rjui.config.json").write_text(
                json.dumps(rjui), encoding="utf-8")
        return WebGenerator(self.root, {}, TypeMapper())

    @staticmethod
    def _spec() -> ScreenSpec:
        return ScreenSpec(name="Home", display_name="Home",
                          description="fixture", layout_file="home")

    @staticmethod
    def _repo() -> RepositoryDef:
        return RepositoryDef(name="ItemRepository", methods=[
            MethodDef(name="getItems", params=[], return_type="Bool",
                      is_async=True)])

    # --- framework ---------------------------------------------------- #

    def test_an_undeclared_project_still_gets_next_byte_for_byte(self):
        # Every consumer today. The change must be invisible to them.
        content = self._generator().generate_viewmodel_impl(self._spec())
        self.assertIn(NEXT_ROUTER_IMPORT, content)
        self.assertIn("router: AppRouterInstance,", content)

    def test_a_custom_adapter_reaches_the_scaffold(self):
        content = self._generator({"web_framework": {
            "name": "remix",
            "router_type_import": "import { NavigateFunction } from 'react-router-dom';",
            "router_type": "NavigateFunction",
        }}).generate_viewmodel_impl(self._spec())
        self.assertIn("import { NavigateFunction } from 'react-router-dom';",
                      content)
        self.assertIn("router: NavigateFunction,", content)
        # and Next's dialect is gone, not merely joined
        self.assertNotIn("AppRouterInstance", content)

    def test_an_adapter_with_no_router_import_emits_no_line(self):
        # EmitHelpers suppresses the line and all — an empty declaration
        # must not leave a blank line where the import was.
        content = self._generator({"web_framework": {"name": "plain"}}
                                  ).generate_viewmodel_impl(self._spec())
        self.assertNotIn("next/dist", content)
        self.assertNotIn("\n\nimport", content.split("// ViewModel")[1][:200])
        self.assertIn("router: any,", content)

    # --- network layer ------------------------------------------------ #

    def test_an_undeclared_project_keeps_the_historical_paths(self):
        content = self._generator().generate_repository_impl(
            "ItemRepository", self._repo())
        self.assertIn(f'from "{DEFAULT_API_CLIENT_MODULE}"', content)

    def test_declared_modules_are_used(self):
        content = self._generator({
            "api_client_module": "@/lib/http/client",
            "api_endpoints_module": "@/lib/http/endpoints",
        }).generate_repository_impl("ItemRepository", self._repo())
        self.assertIn('from "@/lib/http/client"', content)
        self.assertIn('from "@/lib/http/endpoints"', content)
        self.assertNotIn("@/core/network", content)

    def test_the_default_is_announced_only_while_it_is_a_default(self):
        defaulted = self._generator().generate_repository_impl(
            "ItemRepository", self._repo())
        self.assertIn("are defaults", defaulted)
        self.assertIn("api_client_module", defaulted)

        declared = self._generator({
            "api_client_module": "@/lib/http/client",
            "api_endpoints_module": "@/lib/http/endpoints",
        }).generate_repository_impl("ItemRepository", self._repo())
        # A note telling the reader to declare a key they HAVE declared
        # sends them to change something already changed.
        self.assertNotIn("are defaults", declared)

    def test_declaring_only_one_still_says_so(self):
        # Half-declared is still partly defaulted, and the reader needs to
        # know which half they are looking at.
        content = self._generator({"api_client_module": "@/lib/http/client"}
                                  ).generate_repository_impl(
            "ItemRepository", self._repo())
        self.assertIn('from "@/lib/http/client"', content)
        self.assertIn("are defaults", content)


if __name__ == "__main__":
    unittest.main()
