"""iOS (Swift) file generator."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..core.spec_extractor import (
    ScreenSpec, RepositoryDef, UseCaseDef, MethodDef, MethodParam, VarDef,
)
from ..core.type_mapper import TypeMapper
from ..core.generated_marker import comment_header, comment_footer
from ..core.protocol_sync import (
    collect_protocol_members, SyncResult,
    _swift_optional,
)


class IosGenerator:
    """Generates Swift files (Protocol + Implementation) for iOS."""

    has_separate_protocol = True

    def __init__(self, root: Path, config: dict, type_mapper: TypeMapper):
        self._root = root
        self._config = config
        self._type_mapper = type_mapper
        # Resolve source base from sjui.config.json
        self._src_base = self._resolve_source_base()

    def _resolve_source_base(self) -> Path:
        """Read sjui.config.json to find source_directory."""
        sjui_config = self._root / "sjui.config.json"
        if sjui_config.exists():
            import json
            with open(sjui_config, "r", encoding="utf-8") as f:
                data = json.load(f)
            source_dir = data.get("source_directory", "")
            if source_dir:
                return self._root / source_dir
        return self._root

    # --- Path helpers ---

    def viewmodel_protocol_path(self, name: str, subdir: str = "") -> Path:
        base = self._src_base / "ViewModel"
        if subdir:
            base = base / _subdir_to_pascal(subdir)
        return base / "Protocol" / f"{name}ViewModelProtocol.swift"

    def viewmodel_impl_path(self, name: str, subdir: str = "") -> Path:
        base = self._src_base / "ViewModel"
        if subdir:
            base = base / _subdir_to_pascal(subdir)
        return base / f"{name}ViewModel.swift"

    def repository_protocol_path(self, name: str) -> Path:
        return self._src_base / "Repository" / "Protocol" / f"{name}Protocol.swift"

    def repository_impl_path(self, name: str) -> Path:
        return self._src_base / "Repository" / f"{name}.swift"

    def usecase_protocol_path(self, name: str) -> Path:
        return self._src_base / "UseCase" / "Protocol" / f"{name}Protocol.swift"

    def usecase_impl_path(self, name: str) -> Path:
        return self._src_base / "UseCase" / f"{name}.swift"

    # --- ViewModel ---

    def generate_viewmodel_protocol(
        self,
        spec: ScreenSpec,
        impl_source: str | None = None,
        *,
        sync_result: SyncResult | None = None,
    ) -> str:
        """Render the ViewModel protocol.

        When called from ``jui build``'s protocol-sync step, the caller
        passes either ``impl_source`` (we compute the merge here) or a
        pre-computed ``sync_result``. The hard-coded ``var data: <Name>Data``
        is always emitted first; spec.view_model.vars + method entries
        follow.

        The emitted file carries the standard ``@generated`` marker.
        """
        data_class = f"{spec.name}Data"

        if sync_result is None:
            sync_result = collect_protocol_members(
                spec, platform="ios", impl_source=impl_source,
                method_signature_builder=self._method_proto_signature,
                var_signature_builder=self._var_proto_signature,
            )

        header = comment_header(
            source=f"dataFlow.viewModel + {spec.name}ViewModel marker sync",
            generator="jui build",
        )
        footer = comment_footer()
        base_imports = [
            "import Foundation",
            "import Combine",
            "import UIKit",
            "import SwiftUI",
        ]
        # Extra `import` lines driven by TypeMapper's `imports` field on
        # custom types referenced by viewModel methods/vars. For iOS this
        # typically means Swift Package module imports (e.g. `import Models`).
        extra_imports = self._collect_protocol_imports(spec.view_model, base_imports)
        lines = [
            header,
            "",
            *base_imports,
            *extra_imports,
            "",
            f"protocol {spec.name}ViewModelProtocol: ObservableObject {{",
            f"    var data: {data_class} {{ get set }}",
        ]
        for var in sync_result.vars:
            for line in _split_indented(var.signature):
                lines.append(line)
        for method in sync_result.methods:
            for line in _split_indented(method.signature):
                lines.append(line)
        lines += [
            "}",
            "",
            footer,
            "",
        ]
        return "\n".join(lines)

    def generate_viewmodel_impl(self, spec: ScreenSpec) -> str:
        from ..core.spec_validator import resolve_platforms
        data_class = f"{spec.name}Data"
        json_name = _to_snake(spec.name)

        uc_name = f"{spec.name}UseCase"
        has_uc = any(uc.name == uc_name for uc in spec.use_cases)

        vm = spec.view_model
        ios_methods = [
            m for m in vm.methods
            if not m.platforms or "ios" in m.platforms
        ]
        ios_vars = [
            v for v in vm.vars if "ios" in resolve_platforms(v.platforms)
        ]

        lines = [
            "import Foundation",
            "import Combine",
            "import UIKit",
            "import SwiftUI",
            "import SwiftJsonUI",
            "",
            "// NOTE: Add `// @jui:protocol <signature>` above any public member you",
            "// want on the ViewModel Protocol (beyond dataFlow.viewModel entries,",
            "// which are auto-imported). Consecutive marker lines form a multi-line",
            "// signature block for async / generic APIs. Examples:",
            "//     // @jui:protocol func fetchUser() async throws -> User",
            "//     func fetchUser() async throws -> User { ... }",
            "//",
            "//     // @jui:protocol var selectedIndex: Int { get set }",
            "//     @Published var selectedIndex: Int = 0",
            "",
            f"class {spec.name}ViewModel: ObservableObject, {spec.name}ViewModelProtocol {{",
            f'    let jsonFileName = "{json_name}"',
            f"    @Published var data = {data_class}()",
        ]

        for v in ios_vars:
            lines.append(self._var_impl_declaration(v))

        if has_uc:
            lines.append(f"    private let useCase = {uc_name}()")

        lines += [
            "",
            "    // >>> GENERATED_DISPLAY_LOGIC_START",
            "    // >>> GENERATED_DISPLAY_LOGIC_END",
            "",
            "    init() {",
            "        setupActionHandlers()",
            "    }",
            "",
            "    func setupActionHandlers() {",
            "        // TODO: Implement event handlers",
            "    }",
            "",
        ]
        for m in ios_methods:
            sig = self._method_proto_signature(m)
            lines += [
                f"    {sig} {{",
                f"        // TODO: Implement {m.name}",
                "    }",
                "",
            ]
        lines += [
            "}",
            "",
        ]
        return "\n".join(lines)

    def _var_impl_declaration(self, var: VarDef) -> str:
        """Impl-side var declaration. Observable vars get ``@Published``."""
        type_str = _swift_optional(self._map_type(var.type), var.optional)
        prefix = "@Published " if var.observable else ""
        keyword = "let" if var.read_only else "var"
        init = self._var_default_value(var)
        if init is None:
            return f"    {prefix}{keyword} {var.name}: {type_str}"
        return f"    {prefix}{keyword} {var.name}: {type_str} = {init}"

    # --- Repository ---

    def generate_repository_protocol(self, name: str, repo: RepositoryDef) -> str:
        header = comment_header(
            source=f"aggregated repositories from docs/screens/json/*.spec.json ({name})",
            generator="jui g project",
        )
        footer = comment_footer()
        lines = [
            header,
            "",
            "import Foundation",
            "import UIKit",
            "import SwiftUI",
            "",
            f"protocol {name}Protocol {{",
        ]
        for method in repo.methods:
            sig = self._swift_method_signature(method)
            lines.append(f"    {sig}")
        lines += ["}", "", footer, ""]
        return "\n".join(lines)

    def generate_repository_impl(self, name: str, repo: RepositoryDef) -> str:
        lines = [
            "import Foundation",
            "import UIKit",
            "import SwiftUI",
            "",
            f"class {name}: {name}Protocol {{",
        ]
        for method in repo.methods:
            sig = self._swift_method_signature(method)
            lines.append(f"    {sig} {{")
            lines.append(f'        fatalError("TODO: Implement {method.name}")')
            lines.append("    }")
            lines.append("")
        lines += ["}", ""]
        return "\n".join(lines)

    # --- UseCase ---

    def generate_usecase_protocol(self, name: str, uc: UseCaseDef) -> str:
        header = comment_header(
            source=f"aggregated use cases from docs/screens/json/*.spec.json ({name})",
            generator="jui g project",
        )
        footer = comment_footer()
        lines = [
            header,
            "",
            "import Foundation",
            "import UIKit",
            "import SwiftUI",
            "",
            f"protocol {name}Protocol {{",
        ]
        for method in uc.methods:
            sig = self._swift_method_signature(method)
            lines.append(f"    {sig}")
        lines += ["}", "", footer, ""]
        return "\n".join(lines)

    def generate_usecase_impl(self, name: str, uc: UseCaseDef) -> str:
        lines = [
            "import Foundation",
            "import UIKit",
            "import SwiftUI",
            "",
            "@MainActor",
            f"class {name}: {name}Protocol {{",
        ]

        # Repository dependencies
        for dep in uc.repositories:
            prop_name = _lower_first(dep)
            lines.append(f"    private let {prop_name}: {dep}Protocol")
        lines.append("")

        # Init with DI
        init_params = []
        init_assignments = []
        for dep in uc.repositories:
            prop_name = _lower_first(dep)
            init_params.append(f"{prop_name}: {dep}Protocol? = nil")
            init_assignments.append(
                f"        self.{prop_name} = {prop_name} ?? {dep}()"
            )

        if init_params:
            lines.append(f"    init({', '.join(init_params)}) {{")
            lines.extend(init_assignments)
            lines.append("    }")
            lines.append("")

        # Method stubs
        for method in uc.methods:
            sig = self._swift_method_signature(method)
            lines.append(f"    {sig} {{")
            lines.append(f'        fatalError("TODO: Implement {method.name}")')
            lines.append("    }")
            lines.append("")

        lines += ["}", ""]
        return "\n".join(lines)

    # --- Helpers ---

    def _swift_method_signature(self, method: MethodDef) -> str:
        """Generate Swift method signature."""
        params = ", ".join(
            _swift_param_decl(p, self._type_mapper.resolve_class(p.type, 'ios'))
            for p in method.params
        )
        sig = f"func {method.name}({params})"
        if method.is_async:
            sig += " async throws"
        if method.return_type:
            rt = self._type_mapper.resolve_class(method.return_type, "ios")
            sig += f" -> {rt}"
        return sig

    def _method_proto_signature(self, method: MethodDef) -> str:
        """Swift Protocol signature for a ``view_model.methods`` entry."""
        params = ", ".join(
            _swift_param_decl(p, self._map_type(p.type))
            for p in method.params
        )
        sig = f"func {method.name}({params})"
        if method.is_async:
            sig += " async throws"
        if method.return_type:
            sig += f" -> {self._map_type(method.return_type)}"
        return sig

    def _var_proto_signature(self, var: VarDef) -> str:
        """Swift Protocol signature for a ``view_model.vars`` entry."""
        type_str = _swift_optional(self._map_type(var.type), var.optional)
        accessors = "{ get }" if var.read_only else "{ get set }"
        return f"var {var.name}: {type_str} {accessors}"

    def _collect_protocol_imports(
        self,
        vm,
        base_imports: list[str],
    ) -> list[str]:
        """Collect additional ``import`` lines for custom types referenced by
        the viewModel methods/vars, driven by TypeMapper's ``imports`` hint.
        """
        seen = set(base_imports)
        extra: list[str] = []
        referenced: list[str] = []
        for m in vm.methods:
            for p in m.params:
                referenced.append(p.type)
            if m.return_type:
                referenced.append(m.return_type)
        for v in vm.vars:
            referenced.append(v.type)
        for t in referenced:
            for imp in self._type_mapper.resolve_imports(t, "ios"):
                line = f"import {imp}"
                if line in seen:
                    continue
                seen.add(line)
                extra.append(line)
        return extra

    def _map_type(self, spec_type: str) -> str:
        """Resolve a spec type to Swift. Closure types (containing ``->``)
        walk through the type mapper for each sub-expression — spec-side
        notation like ``Array(Foo)`` becomes ``[Foo]`` even when nested
        inside a callback signature. Plain names take the fast path.
        """
        if "->" in spec_type:
            return self._type_mapper.resolve_in_string(spec_type, "ios")
        return self._type_mapper.resolve_class(spec_type, "ios")

    def _var_default_value(self, var: VarDef) -> str | None:
        """Produce an initializer value for the Impl scaffold.

        - Optional closure / reference: ``nil``
        - Use TypeMapper's ``defaultValue`` when present
        - Otherwise no initializer (the generated property is bare and must
          be populated in ``init``)
        """
        if var.optional:
            return "nil"
        if "->" in var.type:
            return None
        try:
            default = self._type_mapper.resolve_default(var.type, "ios")
        except Exception:  # pragma: no cover — defensive; TypeMapper is total
            return None
        if default is None:
            return None
        return _swift_literal(default)


def _swift_param_decl(p: MethodParam, resolved_type: str) -> str:
    """Format a Swift parameter declaration, honouring ``p.label``.

    - ``label is None`` → ``name: Type`` (external label defaults to ``name``)
    - ``label == "_"`` → ``_ name: Type`` (suppress external label)
    - other label → ``label name: Type`` (explicit external label)
    """
    if p.label is None:
        return f"{p.name}: {resolved_type}"
    if p.label == "_":
        return f"_ {p.name}: {resolved_type}"
    return f"{p.label} {p.name}: {resolved_type}"


def _to_snake(name: str) -> str:
    return re.sub(r"([A-Z])", r"_\1", name).lower().lstrip("_")


def _lower_first(name: str) -> str:
    return name[0].lower() + name[1:] if name else name


def _subdir_to_pascal(subdir: str) -> Path:
    """Convert a subdir path (e.g. 'my_page/settings') to PascalCase Path."""
    parts = [
        "".join(word.capitalize() for word in segment.split("_"))
        for segment in subdir.split("/")
        if segment
    ]
    return Path(*parts) if parts else Path()


def _split_indented(signature: str, indent: str = "    ") -> list[str]:
    """Split a (possibly multi-line) signature and indent each line by
    *indent*. Empty lines pass through bare.
    """
    out: list[str] = []
    for line in signature.splitlines() or [signature]:
        out.append(f"{indent}{line}" if line else "")
    return out


def _swift_literal(value) -> str:
    """Render a Python value as a Swift literal for Impl scaffolds."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "[" + ", ".join(_swift_literal(v) for v in value) + "]"
    return str(value)
