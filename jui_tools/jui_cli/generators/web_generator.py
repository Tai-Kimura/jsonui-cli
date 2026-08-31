"""Web (TypeScript / ReactJsonUI) file generator.

Output layout follows the rjui convention:

    {viewmodels_directory}/{Name}ViewModel.ts                 (user impl)
    src/repository/{Name}Repository.ts                        (single file)
    src/usecase/{Name}UseCase.ts                              (single file)

``{Name}ViewModelBase.ts`` is deliberately absent from that list: rjui_tools
owns it (see ``VIEWMODEL_BASE_OWNER``). This module used to generate it too,
which is what made every build round-trip the file.

Unlike iOS/Android there is no separate protocol/interface file —
``has_separate_protocol = False`` signals to generate_cmd.py that
protocol generation should be skipped.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..core.spec_extractor import (
    ScreenSpec, RepositoryDef, UseCaseDef, MethodDef,
)
from ..core.type_mapper import TypeMapper
from .web_framework import resolve as resolve_web_framework


#: `<Name>ViewModelBase.ts` belongs to rjui_tools, not to jui_tools.
#:
#: Both tools wrote that path. `rjui build` regenerates it from the Layout and
#: runs *after* protocol sync inside `jui build`, so everything written here
#: was overwritten before the build finished — every build reported work it
#: had not durably done ("updated N protocol(s)" on an unchanged tree), and
#: once var declarations were added the build warned about a declaration that
#: did not survive to the artifact.
#:
#: The condition is the project's existing `platforms.web` declaration rather
#: than a new flag: these commands only visit a platform that is declared, so
#: reaching a `"web"` iteration *is* that declaration.
#:
#: rjui_tools emits no var declarations at all — its Base is a fixed template
#: with no `vars` branch — because in the rjui contract a `observable: false`
#: var is Impl-private state. That is a declared contract, not an accident of
#: the Ruby implementation, and it is why this is ownership rather than a
#: merge: the two tools disagree about what belongs in the file.
#: Where the scaffold imports the network layer from when the project does
#: not say. The historical literals, so an existing project sees no change.
DEFAULT_API_CLIENT_MODULE = "@/core/network/apiClient"
DEFAULT_API_ENDPOINTS_MODULE = "@/core/network/apiEndpoints"

VIEWMODEL_BASE_OWNER = {"web": "rjui_tools"}


def owns_viewmodel_base(platform: str) -> bool:
    """True when jui_tools generates `<Name>ViewModelBase` for *platform*."""
    return platform not in VIEWMODEL_BASE_OWNER


class WebGenerator:
    """Generates TypeScript files for ReactJsonUI projects."""

    has_separate_protocol = False

    def __init__(self, root: Path, config: dict, type_mapper: TypeMapper):
        self._root = root
        self._config = config
        self._type_mapper = type_mapper
        rjui_config = self._load_rjui_config()
        self._impl_vm_dir = root / rjui_config.get(
            "viewmodels_directory", "src/viewmodels"
        )
        self._data_import_base = rjui_config.get(
            "data_directory", "src/generated/data"
        ).replace("src/", "@/")
        self._generated_vm_import_base = rjui_config.get(
            "generated_viewmodels_directory", "src/generated/viewmodels"
        ).replace("src/", "@/")
        self._repo_dir = root / "src" / "repository"
        self._usecase_dir = root / "src" / "usecase"
        self._framework = resolve_web_framework(rjui_config)
        # Where this project keeps its network layer. The scaffold used to
        # write these two paths as literals, so a project that arranges its
        # network layer differently got a file that cannot compile the
        # moment it is generated — and a red build that looks exactly like
        # a mistake by whoever ran the generator.
        self._api_client_module = rjui_config.get("api_client_module")
        self._api_endpoints_module = rjui_config.get("api_endpoints_module")

    def _load_rjui_config(self) -> dict:
        """Read rjui.config.json if present."""
        rjui_config = self._root / "rjui.config.json"
        if rjui_config.exists():
            try:
                return json.loads(rjui_config.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    # --- Path helpers ---

    def viewmodel_impl_path(self, name: str, subdir: str = "") -> Path:
        """Path of the user-authored implementation (never overwritten)."""
        base = self._impl_vm_dir
        if subdir:
            base = base / _subdir_to_pascal(subdir)
        return base / f"{name}ViewModel.ts"

    def repository_protocol_path(self, name: str) -> Path:
        """Web doesn't split protocol/impl — return the impl path."""
        return self.repository_impl_path(name)

    def repository_impl_path(self, name: str) -> Path:
        return self._repo_dir / f"{name}.ts"

    def usecase_protocol_path(self, name: str) -> Path:
        return self.usecase_impl_path(name)

    def usecase_impl_path(self, name: str) -> Path:
        return self._usecase_dir / f"{name}.ts"

    # --- ViewModel ---

    def generate_viewmodel_impl(self, spec: ScreenSpec) -> str:
        """Generate the user-editable ViewModel subclass."""
        data_type = f"{spec.name}Data"
        uc_name = f"{spec.name}UseCase"
        has_uc = any(uc.name == uc_name for uc in spec.use_cases)

        subdir = _layout_subdir(spec.layout_file)
        base_import = self._generated_vm_import_base
        if subdir:
            base_import = f"{base_import}/{_subdir_to_pascal(subdir).as_posix()}"

        router_type = self._framework["router_type"]
        lines = [f"// ViewModel for {spec.name}"]
        if self._framework["router_type_import"]:
            lines.append(self._framework["router_type_import"])
        lines += [
            f'import {{ {data_type} }} from "{self._data_import_base}/{data_type}";',
            f'import {{ {spec.name}ViewModelBase }} from "{base_import}/{spec.name}ViewModelBase";',
        ]
        if has_uc:
            lines.append(f'import {{ {uc_name} }} from "@/usecase/{uc_name}";')
        lines += [
            "",
            f"export class {spec.name}ViewModel extends {spec.name}ViewModelBase {{",
        ]
        if has_uc:
            lines.append(f"  private readonly useCase: {uc_name};")
            lines.append("")
        lines += [
            "  constructor(",
            f"    router: {router_type},",
            f"    getData: () => {data_type},",
            f"    setData: (data: {data_type} | ((prev: {data_type}) => {data_type})) => void",
            "  ) {",
            "    super(router, getData, setData);",
        ]
        if has_uc:
            lines.append(f"    this.useCase = new {uc_name}();")
        lines += [
            "    this.initializeEventHandlers();",
            "  }",
            "",
            "  protected initializeEventHandlers = () => {",
            "    this.updateData({",
            "      // TODO: Implement event handlers",
            "    });",
            "  };",
            "}",
            "",
        ]
        return "\n".join(lines)

    # --- Repository (single file, no protocol) ---

    def generate_repository_protocol(self, name: str, repo: RepositoryDef) -> str:
        """Not used — web has no protocol file. Same content as impl."""
        return self.generate_repository_impl(name, repo)

    def generate_repository_impl(self, name: str, repo: RepositoryDef) -> str:
        client = self._api_client_module or DEFAULT_API_CLIENT_MODULE
        endpoints = self._api_endpoints_module or DEFAULT_API_ENDPOINTS_MODULE
        lines = ["// Generated by jui - edit the implementation as needed"]
        # Said only when it is true. A note about a key that IS declared
        # would send the reader to change something already changed.
        if not (self._api_client_module and self._api_endpoints_module):
            lines.append(
                "// Network-layer imports below are defaults — declare "
                "api_client_module / api_endpoints_module in "
                "rjui.config.json to point them elsewhere."
            )
        lines += [
            f'import {{ ApiClient, HttpMethod }} from "{client}";',
            f'import {{ ApiEndpoint }} from "{endpoints}";',
            "",
            f"export class {name} {{",
        ]
        for method in repo.methods:
            sig = self._ts_method_signature(method, with_async=True)
            lines.append(f"  {sig} {{")
            lines.append(f'    throw new Error("TODO: Implement {method.name}");')
            lines.append("  }")
            lines.append("")
        lines += ["}", ""]
        return "\n".join(lines)

    # --- UseCase (single file, no protocol) ---

    def generate_usecase_protocol(self, name: str, uc: UseCaseDef) -> str:
        return self.generate_usecase_impl(name, uc)

    def generate_usecase_impl(self, name: str, uc: UseCaseDef) -> str:
        imports = []
        for dep in uc.repositories:
            imports.append(f'import {{ {dep} }} from "@/repository/{dep}";')

        lines = [f"// UseCase: {name}"] + imports + [
            "",
            f"export class {name} {{",
        ]

        if uc.repositories:
            for dep in uc.repositories:
                prop_name = _lower_first(dep)
                lines.append(f"  private readonly {prop_name}: {dep};")
            lines.append("")
            lines.append("  constructor() {")
            for dep in uc.repositories:
                prop_name = _lower_first(dep)
                lines.append(f"    this.{prop_name} = new {dep}();")
            lines.append("  }")
            lines.append("")

        for method in uc.methods:
            sig = self._ts_method_signature(method, with_async=True)
            lines.append(f"  {sig} {{")
            lines.append(f'    throw new Error("TODO: Implement {method.name}");')
            lines.append("  }")
            lines.append("")

        lines += ["}", ""]
        return "\n".join(lines)

    # --- Helpers ---

    def _ts_method_signature(self, method: MethodDef, with_async: bool = False) -> str:
        params = ", ".join(
            f"{p.name}: {self._type_mapper.resolve_class(p.type, 'web')}"
            for p in method.params
        )
        async_prefix = "async " if with_async and method.is_async else ""
        sig = f"{async_prefix}{method.name}({params})"
        if method.return_type:
            rt = self._type_mapper.resolve_class(method.return_type, "web")
            if method.is_async:
                sig += f": Promise<{rt}>"
            else:
                sig += f": {rt}"
        return sig


def _to_snake(name: str) -> str:
    return re.sub(r"([A-Z])", r"_\1", name).lower().lstrip("_")


def _lower_first(name: str) -> str:
    return name[0].lower() + name[1:] if name else name


def _layout_subdir(layout_file: str) -> str:
    """Extract the directory portion of a layout file path (without filename)."""
    if not layout_file or "/" not in layout_file:
        return ""
    return "/".join(layout_file.split("/")[:-1])


def _subdir_to_pascal(subdir: str) -> Path:
    """Convert a subdir path (e.g. 'my_page/settings') to PascalCase Path."""
    parts = [
        "".join(word.capitalize() for word in segment.split("_"))
        for segment in subdir.split("/") if segment
    ]
    return Path(*parts) if parts else Path()
