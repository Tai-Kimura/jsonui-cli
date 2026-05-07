"""Web (TypeScript / ReactJsonUI) file generator.

Output layout follows the rjui convention:

    {generated_viewmodels_directory}/{Name}ViewModelBase.ts   (autogen)
    {viewmodels_directory}/{Name}ViewModel.ts                 (user impl)
    src/repository/{Name}Repository.ts                        (single file)
    src/usecase/{Name}UseCase.ts                              (single file)

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
from ..core.generated_marker import comment_header, comment_footer
from ..core.spec_validator import resolve_platforms


class WebGenerator:
    """Generates TypeScript files for ReactJsonUI projects."""

    has_separate_protocol = False

    def __init__(self, root: Path, config: dict, type_mapper: TypeMapper):
        self._root = root
        self._config = config
        self._type_mapper = type_mapper
        rjui_config = self._load_rjui_config()
        self._generated_vm_dir = root / rjui_config.get(
            "generated_viewmodels_directory", "src/generated/viewmodels"
        )
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

    def viewmodel_protocol_path(self, name: str, subdir: str = "") -> Path:
        """Path of the auto-generated base class (regenerated every build)."""
        base = self._generated_vm_dir
        if subdir:
            base = base / _subdir_to_pascal(subdir)
        return base / f"{name}ViewModelBase.ts"

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

    def generate_viewmodel_protocol(
        self,
        spec: ScreenSpec,
        impl_source: str | None = None,  # web ignores impl markers — accepted for signature parity
    ) -> str:
        """Generate the ViewModel base class (auto-regenerated).

        ``dataFlow.viewModel.methods`` entries whose ``platforms`` excludes
        ``"web"`` are filtered out. Non-observable ``vars`` (those the Impl
        wants on the Base directly) are emitted as public fields;
        observable vars live inside ``<Name>Data`` and aren't re-emitted.

        Marker blocks (``@jui:protocol``) are not consulted for Web — the
        Base has a fixed ``getter + initializeEventHandlers`` shape.
        """
        del impl_source  # noqa — documented; web is spec-only.

        data_type = f"{spec.name}Data"
        vm = spec.view_model
        web_methods = [
            m for m in vm.methods
            if not m.platforms or "web" in m.platforms
        ]
        web_vars_base = [
            v for v in vm.vars
            if "web" in resolve_platforms(v.platforms) and not v.observable
        ]

        event_defaults = "\n".join(
            f"      {m.name}: () => {{}}," for m in web_methods
        )
        event_body = event_defaults if event_defaults else "      // no methods declared"

        header = comment_header(
            source=f"docs/screens/json/{_to_snake(spec.name)}.spec.json",
            generator="jui build",
        )
        # Collect extra TS imports for custom types used in non-observable
        # vars. TypeMapper's `imports` hint carries per-type module paths
        # (e.g. ``"imports": ["@/types/ItemImage"]``).
        seen_imports: set[str] = set()
        extra_import_lines: list[str] = []
        for v in web_vars_base:
            for imp in self._type_mapper.resolve_imports(v.type, "web"):
                line = f'import {{ {_TS_TYPE_OVERRIDES.get(v.type, v.type)} }} from "{imp}";'
                if line in seen_imports:
                    continue
                seen_imports.add(line)
                extra_import_lines.append(line)

        lines = [
            header,
            "",
            'import { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";',
            f'import {{ {data_type} }} from "{self._data_import_base}/{data_type}";',
            *extra_import_lines,
            "",
            f"export class {spec.name}ViewModelBase {{",
            "  protected router: AppRouterInstance;",
            f"  protected _getData: () => {data_type};",
            f"  protected _setData: (data: {data_type} | ((prev: {data_type}) => {data_type})) => void;",
        ]
        # Non-observable vars emitted as public fields on the Base class.
        # Observable vars live inside <Name>Data (uiVariables handle that).
        for v in web_vars_base:
            lines.append(self._var_base_declaration(v))
        lines += [
            "",
            f"  get data(): {data_type} {{",
            "    return this._getData();",
            "  }",
            "",
            "  constructor(",
            "    router: AppRouterInstance,",
            f"    getData: () => {data_type},",
            f"    setData: (data: {data_type} | ((prev: {data_type}) => {data_type})) => void",
            "  ) {",
            "    this.router = router;",
            "    this._getData = getData;",
            "    this._setData = setData;",
            "  }",
            "",
            "  // Update data and trigger re-render",
            f"  updateData = (updates: Partial<{data_type}>) => {{",
            "    this._setData((prev) => ({ ...prev, ...updates }));",
            "  };",
            "",
            "  // Set external variables (e.g., route params, props from parent)",
            f"  setVars = (vars: Partial<{data_type}>) => {{",
            "    this.updateData(vars);",
            "  };",
            "",
            "  // Initialize event handlers — call this in subclass constructor",
            "  protected initializeEventHandlers = () => {",
            "    this.updateData({",
            event_body,
            "    });",
            "  };",
            "}",
            "",
            comment_footer(),
            "",
        ]
        return "\n".join(lines)

    def generate_viewmodel_impl(self, spec: ScreenSpec) -> str:
        """Generate the user-editable ViewModel subclass."""
        data_type = f"{spec.name}Data"
        uc_name = f"{spec.name}UseCase"
        has_uc = any(uc.name == uc_name for uc in spec.use_cases)

        subdir = _layout_subdir(spec.layout_file)
        base_import = self._generated_vm_import_base
        if subdir:
            base_import = f"{base_import}/{_subdir_to_pascal(subdir).as_posix()}"

        lines = [
            f"// ViewModel for {spec.name}",
            'import { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";',
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
            "    router: AppRouterInstance,",
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
        lines = [
            "// Generated by jui - edit the implementation as needed",
            'import { ApiClient, HttpMethod } from "@/core/network/apiClient";',
            'import { ApiEndpoint } from "@/core/network/apiEndpoints";',
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

    def _var_base_declaration(self, var) -> str:
        """TypeScript public-field declaration for a non-observable var.

        Observable vars are part of ``<Name>Data`` so they're not re-emitted
        here. Closure types (containing ``->``) are translated to TS arrow
        syntax.
        """
        type_str = _to_ts_type(var.type)
        if var.optional:
            return f"  public {var.name}?: {type_str};"
        return f"  public {var.name}: {type_str};"

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


_TS_TYPE_OVERRIDES = {
    "String": "string",
    "Int": "number",
    "Double": "number",
    "Bool": "boolean",
    "Void": "void",
}


def _to_ts_type(spec_type: str) -> str:
    """Best-effort spec-type → TypeScript translation.

    - Closure types: Swift ``() -> Void`` → TS ``() => void``; ``Void`` inside
      the return position becomes ``void``
    - Known primitives via ``_TS_TYPE_OVERRIDES``
    - Otherwise pass through (custom types author wrote in TS form)
    """
    if "->" in spec_type:
        ts = spec_type.replace("->", "=>").replace("Void", "void")
        return ts
    return _TS_TYPE_OVERRIDES.get(spec_type, spec_type)
