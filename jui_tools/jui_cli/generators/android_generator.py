"""Android (Kotlin) file generator."""
from __future__ import annotations

import re
from pathlib import Path

from ..core.spec_extractor import (
    ScreenSpec, RepositoryDef, UseCaseDef, MethodDef, VarDef,
)
from ..core.type_mapper import TypeMapper
from ..core.generated_marker import comment_header, comment_footer
from ..core.protocol_sync import (
    collect_protocol_members, SyncResult, _kotlin_optional,
)


class AndroidGenerator:
    """Generates Kotlin files (Interface + Implementation) for Android."""

    has_separate_protocol = True

    def __init__(self, root: Path, config: dict, type_mapper: TypeMapper):
        self._root = root
        self._config = config
        self._type_mapper = type_mapper
        self._package = self._resolve_package(config)
        # Derive source dir from package
        pkg_path = self._package.replace(".", "/")
        self._src_base = root / "app/src/main/kotlin" / pkg_path
        # Lazily-built symbol index (type name -> fully-qualified class name)
        self._symbol_index: dict[str, str] | None = None

    def _build_symbol_index(self) -> dict[str, str]:
        """Scan Kotlin source files and map *top-level* declarations to their FQN.

        Nested types (``class Foo { enum class Bar }``) are deliberately
        skipped — their qualified name is ``Foo.Bar`` and the symbol-lookup
        path elsewhere in this generator only consults the top-level token
        for imports. Indexing them as if they were top-level would emit
        bogus ``import <pkg>.Bar`` lines that resolve to nothing.

        Used to auto-generate imports for response/request types referenced
        in Repository / UseCase method signatures.
        """
        index: dict[str, str] = {}
        kotlin_roots = [
            self._root / "app/src/main/kotlin",
            self._root / "app/src/main/java",
        ]
        pkg_re = re.compile(r"^\s*package\s+([\w.]+)", re.MULTILINE)
        decl_re = re.compile(
            r"\b(?:data\s+|sealed\s+|open\s+|abstract\s+)?"
            r"(?:class|interface|object|enum\s+class|typealias)\s+(\w+)"
        )
        for kroot in kotlin_roots:
            if not kroot.exists():
                continue
            for kfile in kroot.rglob("*.kt"):
                try:
                    text = kfile.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                pkg_match = pkg_re.search(text)
                package = pkg_match.group(1) if pkg_match else ""

                # Walk lines tracking `{` / `}` depth. Only declarations
                # found while depth == 0 are top-level. This is a coarse
                # parser — it doesn't strip string literals or block
                # comments — but it's good enough for typical Kotlin source
                # and avoids a full lexer dependency.
                depth = 0
                for raw_line in text.split("\n"):
                    line = raw_line.split("//", 1)[0]
                    if depth == 0:
                        m = decl_re.search(line)
                        if m:
                            type_name = m.group(1)
                            if type_name not in index:
                                fqn = (
                                    f"{package}.{type_name}"
                                    if package else type_name
                                )
                                index[type_name] = fqn
                    depth += line.count("{") - line.count("}")
                    if depth < 0:
                        depth = 0
        return index

    def _get_symbol_index(self) -> dict[str, str]:
        if self._symbol_index is None:
            self._symbol_index = self._build_symbol_index()
        return self._symbol_index

    # Kotlin built-ins that never need an import.
    _KOTLIN_BUILTINS = {
        "Any", "Unit", "Nothing", "Boolean", "Byte", "Short", "Int", "Long",
        "Float", "Double", "Char", "String", "Array", "List", "Map", "Set",
        "MutableList", "MutableMap", "MutableSet", "Pair", "Triple",
    }

    def _imports_for_methods(
        self, methods: list[MethodDef], current_package: str = ""
    ) -> list[str]:
        """Return `import ...` lines needed to resolve types used in signatures.

        Combines two sources:
        - type_map ``imports`` hints (e.g. ``Flow`` → ``kotlinx.coroutines.flow.Flow``)
        - Project symbol index scan (e.g. ``AuthResponse`` → its FQN)
        """
        spec_types: list[str] = []
        extra_refs: set[str] = set()
        for method in methods:
            for p in method.params:
                spec_types.append(p.type)
            if method.return_type:
                spec_types.append(method.return_type)
        return self._build_imports(spec_types, extra_refs, current_package)

    def _imports_for_names(
        self,
        spec_types: list[str] | None = None,
        names: list[str] | None = None,
        current_package: str = "",
    ) -> list[str]:
        """Compute imports for a mix of spec-typed values and bare class names.

        *spec_types* are resolved through the type mapper so generic
        patterns and import hints apply. *names* are looked up directly
        in the project symbol index (for things like ``{Name}Data``).
        """
        return self._build_imports(spec_types or [], set(names or []), current_package)

    def _build_imports(
        self,
        spec_types: list[str],
        extra_refs: set[str],
        current_package: str,
    ) -> list[str]:
        imports: list[str] = []
        seen: set[str] = set()

        def _add(line: str) -> None:
            if line and line not in seen:
                seen.add(line)
                imports.append(line)

        # 1. type_map-declared imports
        for st in spec_types:
            for imp in self._type_mapper.resolve_imports(st, "android"):
                _add(f"import {imp}")

        # 2. Symbol-index resolution — for both resolved class tokens and
        #    explicitly provided names (e.g. XxxData, XxxUseCase).
        refs: set[str] = set(extra_refs)
        # ``Parent.Child`` (nested type) reaches its `Child` member through
        # the `Parent` import, so for symbol-lookup purposes only the
        # top-level (leftmost) segment of each PascalCase chain matters.
        # Picking up every PascalCase token would look ``Child`` up in the
        # symbol index and emit a bogus ``import <pkg>.Child`` line.
        chain_re = re.compile(r"[A-Z]\w*(?:\.[A-Z]\w*)+|[A-Z]\w*")
        for st in spec_types:
            resolved = self._type_mapper.resolve_class(st, "android")
            for chain in chain_re.findall(resolved or ""):
                refs.add(chain.split(".", 1)[0])

        index = self._get_symbol_index()
        package = current_package or self._package
        for ref in sorted(refs):
            if ref in self._KOTLIN_BUILTINS:
                continue
            fqn = index.get(ref)
            if not fqn:
                continue
            if fqn.rsplit(".", 1)[0] == package:
                continue
            _add(f"import {fqn}")

        return imports

    def _resolve_package(self, config: dict) -> str:
        """Resolve package name from kjui.config.json, falling back to jui config."""
        kjui_config = self._root / "kjui.config.json"
        if kjui_config.exists():
            import json
            with open(kjui_config, "r", encoding="utf-8") as f:
                data = json.load(f)
            pkg = data.get("package_name", "")
            if pkg:
                return pkg
        return config.get("package_name", "com.example.app")

    def _detect_existing_package(self, dir_path: Path, default: str) -> str:
        """Read the `package` line from any existing .kt file in dir_path.

        Returns the dominant package declaration so new scaffold output stays
        consistent with files that were generated by other tools (e.g. the
        kjui_tools Ruby Compose builder, which emits ``<pkg>.viewmodels``
        even when the physical directory is named ``viewmodel``). Falls back
        to ``default`` if no .kt files exist or none declare a package.
        """
        if not dir_path.exists() or not dir_path.is_dir():
            return default
        pkg_re = re.compile(r"^\s*package\s+([\w.]+)", re.MULTILINE)
        counts: dict[str, int] = {}
        for kt in dir_path.glob("*.kt"):
            try:
                text = kt.read_text(encoding="utf-8")
            except OSError:
                continue
            m = pkg_re.search(text)
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
        if not counts:
            return default
        # Pick the most common one (ties broken alphabetically for stability).
        return max(sorted(counts.keys()), key=lambda k: counts[k])

    def _viewmodel_impl_package(self) -> str:
        return self._detect_existing_package(
            self._src_base / "viewmodel",
            f"{self._package}.viewmodel",
        )

    def _viewmodel_protocol_package(self) -> str:
        return self._detect_existing_package(
            self._src_base / "viewmodel" / "protocol",
            f"{self._package}.viewmodel.protocol",
        )

    # --- Path helpers ---

    def viewmodel_protocol_path(self, name: str, subdir: str = "") -> Path:
        # Subdir is intentionally ignored for Android:
        # Kotlin package structure must match the declared package, and the
        # file's `package` line is fixed. Supporting subdirs here without
        # also adjusting the package declaration would cause compile errors.
        del subdir
        return self._src_base / "viewmodel" / "protocol" / f"{name}ViewModelProtocol.kt"

    def viewmodel_impl_path(self, name: str, subdir: str = "") -> Path:
        del subdir
        return self._src_base / "viewmodel" / f"{name}ViewModel.kt"

    def viewmodel_protocol_fqn(self, name: str) -> str:
        """Fully-qualified class name for ``<name>ViewModelProtocol``.

        Used by build-time inheritance patching to add the matching
        ``import`` line on the Impl side, since Impl and Protocol live
        in different packages. Detected from existing files so a project
        that uses an unconventional layout (e.g. ``<pkg>.viewmodels`` plural
        for Impl, ``<pkg>.viewmodel.protocol`` singular for Protocol) keeps
        producing self-consistent scaffolds.
        """
        return f"{self._viewmodel_protocol_package()}.{name}ViewModelProtocol"

    def repository_protocol_path(self, name: str) -> Path:
        return self._src_base / "repository" / "protocol" / f"{name}.kt"

    def repository_impl_path(self, name: str) -> Path:
        return self._src_base / "repository" / f"{name}Impl.kt"

    def usecase_protocol_path(self, name: str) -> Path:
        return self._src_base / "usecase" / "protocol" / f"{name}Protocol.kt"

    def usecase_impl_path(self, name: str) -> Path:
        return self._src_base / "usecase" / f"{name}.kt"

    # --- ViewModel ---

    def generate_viewmodel_protocol(
        self,
        spec: ScreenSpec,
        impl_source: str | None = None,
        *,
        sync_result: SyncResult | None = None,
    ) -> str:
        """Render the ViewModel interface.

        Hard-coded ``val data: <Name>Data`` comes first. ``dataFlow.viewModel``
        vars + methods follow. Marker blocks from the Impl merge in as usual.
        """
        data_class = f"{spec.name}Data"
        pkg = self._viewmodel_protocol_package()

        if sync_result is None:
            sync_result = collect_protocol_members(
                spec, platform="android", impl_source=impl_source,
                method_signature_builder=self._method_proto_signature,
                var_signature_builder=self._var_proto_signature,
            )

        # Collect every custom type referenced by the methods/vars that will
        # land in the Interface so the corresponding `import` statements are
        # emitted. Without this, Protocol declarations reference types like
        # `ItemImage` / `Candidate` without any import and the Kotlin
        # compiler fails with "Unresolved reference".
        vm = spec.view_model
        proto_types: list[str] = []
        for m in vm.methods:
            for p in m.params:
                proto_types.append(p.type)
            if m.return_type:
                proto_types.append(m.return_type)
        for v in vm.vars:
            proto_types.append(v.type)
        imports = self._imports_for_names(
            spec_types=proto_types,
            names=[data_class],
            current_package=pkg,
        )
        # The Compose convention emits `val data: StateFlow<XData>` on the
        # Impl side (kjui's ViewModel template + every project mirror).
        # Declaring `val data: XData` on the Protocol forces a type
        # mismatch + missing `override` — kotlinc reports
        # "data hides member of supertype" on every ViewModel. Mirror the
        # Impl shape here so the inheritance is consistent.
        state_flow_import = "import kotlinx.coroutines.flow.StateFlow"
        if state_flow_import not in imports:
            imports.append(state_flow_import)

        header = comment_header(
            source=f"dataFlow.viewModel + {spec.name}ViewModel marker sync",
            generator="jui build",
        )
        footer = comment_footer()
        lines = [
            header,
            "",
            f"package {pkg}",
            "",
        ]
        if imports:
            lines.extend(imports)
            lines.append("")
        lines += [
            f"interface {spec.name}ViewModelProtocol {{",
            f"    val data: StateFlow<{data_class}>",
        ]
        for var in sync_result.vars:
            for sig_line in (var.signature.splitlines() or [var.signature]):
                lines.append(f"    {sig_line}" if sig_line else "")
        for method in sync_result.methods:
            for sig_line in (method.signature.splitlines() or [method.signature]):
                lines.append(f"    {sig_line}" if sig_line else "")
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

        pkg = self._viewmodel_impl_package()
        names = [data_class, f"{spec.name}ViewModelProtocol"]
        imports = self._imports_for_names(names=names, current_package=pkg)
        if has_uc:
            uc_import = f"import {self._package}.usecase.{uc_name}"
            if uc_import not in imports:
                imports.append(uc_import)

        vm = spec.view_model
        android_methods = [
            m for m in vm.methods
            if not m.platforms or "android" in m.platforms
        ]
        android_vars = [
            v for v in vm.vars if "android" in resolve_platforms(v.platforms)
        ]

        lines = [
            f"package {pkg}",
            "",
            "import androidx.lifecycle.ViewModel",
            "import dagger.hilt.android.lifecycle.HiltViewModel",
            "import kotlinx.coroutines.flow.MutableStateFlow",
            "import kotlinx.coroutines.flow.StateFlow",
            "import kotlinx.coroutines.flow.asStateFlow",
            "import javax.inject.Inject",
        ]
        if imports:
            lines.extend(imports)
        lines += [
            "",
            "// NOTE: Add `// @jui:protocol <signature>` above any public member you",
            "// want on the ViewModel Protocol (beyond dataFlow.viewModel entries,",
            "// which are auto-imported). Consecutive marker lines form a multi-line",
            "// signature block for async/suspend/generic APIs. Examples:",
            "//     // @jui:protocol suspend fun fetchUser(): User",
            "//     override suspend fun fetchUser(): User = ...",
            "//",
            "//     // @jui:protocol var selectedIndex: Int",
            "//     override var selectedIndex: Int = 0",
            "",
            "@HiltViewModel",
            f"class {spec.name}ViewModel @Inject constructor(",
        ]
        if has_uc:
            lines.append(f"    private val useCase: {uc_name}")
        lines += [
            f") : ViewModel(), {spec.name}ViewModelProtocol {{",
            f'    val jsonFileName = "{json_name}"',
            f"    // _data is a `var` so a parent ViewModel can swap it in via",
            f"    // `bind(parentFlow:)` below. This gives sheet stub VMs the same",
            f"    // \"writes propagate to the parent\" semantics that iOS's",
            f"    // SwiftUI Binding<T> already provides — without it,",
            f"    // ModalBottomSheet content writes land in the stub VM's local",
            f"    // flow and the parent never sees them.",
            f"    private var _data: MutableStateFlow<{data_class}> = MutableStateFlow({data_class}())",
            f"    override val data: StateFlow<{data_class}> get() = _data.asStateFlow()",
        ]

        for v in android_vars:
            lines.append(self._var_impl_declaration(v))

        lines += [
            "",
            "    /**",
            "     * Re-route this VM's data flow to a parent-owned MutableStateFlow.",
            "     * Idempotent: a no-op when the same flow is already bound.",
            "     *",
            "     * Typical usage from a parent View hosting a ModalBottomSheet:",
            "     * ```",
            "     * val sheetVm: " + spec.name + "ViewModel = viewModel()",
            "     * sheetVm.bind(parentVm.mutable" + spec.name + "Data)",
            "     * ```",
            "     */",
            f"    fun bind(parentFlow: MutableStateFlow<{data_class}>) {{",
            "        if (_data === parentFlow) return",
            "        _data = parentFlow",
            "    }",
            "",
            "    // >>> GENERATED_DISPLAY_LOGIC_START",
            "    // >>> GENERATED_DISPLAY_LOGIC_END",
            "",
            "    init {",
            "        setupActionHandlers()",
            "    }",
            "",
            "    fun setupActionHandlers() {",
            "        // TODO: Implement event handlers",
            "    }",
            "",
        ]
        for m in android_methods:
            sig = self._method_proto_signature(m)
            lines += [
                f"    override {sig} {{",
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
        """Kotlin Impl-side var declaration with ``override``."""
        type_str = _kotlin_optional(self._map_type(var.type), var.optional)
        keyword = "val" if var.read_only else "var"
        init = self._var_default_value(var)
        prefix = "override "
        if init is None:
            return f"    {prefix}{keyword} {var.name}: {type_str}"
        return f"    {prefix}{keyword} {var.name}: {type_str} = {init}"

    # --- Repository ---

    def generate_repository_protocol(self, name: str, repo: RepositoryDef) -> str:
        pkg = f"{self._package}.repository.protocol"
        imports = self._imports_for_methods(repo.methods, current_package=pkg)
        header = comment_header(
            source=f"aggregated repositories from docs/screens/json/*.spec.json ({name})",
            generator="jui g project",
        )
        footer = comment_footer()
        lines = [
            header,
            f"package {pkg}",
            "",
        ]
        if imports:
            lines.extend(imports)
            lines.append("")
        lines.append(f"interface {name} {{")
        for method in repo.methods:
            sig = self._kotlin_method_signature(method)
            lines.append(f"    {sig}")
        lines += ["}", "", footer, ""]
        return "\n".join(lines)

    def generate_repository_impl(self, name: str, repo: RepositoryDef) -> str:
        pkg = f"{self._package}.repository"
        imports = self._imports_for_methods(repo.methods, current_package=pkg)
        lines = [
            f"package {pkg}",
            "",
            f"import {self._package}.repository.protocol.{name}",
            "import javax.inject.Inject",
            "import javax.inject.Singleton",
        ]
        if imports:
            lines.extend(imports)
        lines += [
            "",
            "@Singleton",
            f"class {name}Impl @Inject constructor(",
            f") : {name} {{",
        ]
        for method in repo.methods:
            sig = self._kotlin_method_signature(method, override=True)
            lines.append(f"    {sig} {{")
            lines.append(f'        TODO("Implement {method.name}")')
            lines.append("    }")
            lines.append("")
        lines += ["}", ""]
        return "\n".join(lines)

    # --- UseCase ---

    def generate_usecase_protocol(self, name: str, uc: UseCaseDef) -> str:
        pkg = f"{self._package}.usecase.protocol"
        imports = self._imports_for_methods(uc.methods, current_package=pkg)
        header = comment_header(
            source=f"aggregated use cases from docs/screens/json/*.spec.json ({name})",
            generator="jui g project",
        )
        footer = comment_footer()
        lines = [
            header,
            f"package {pkg}",
            "",
        ]
        if imports:
            lines.extend(imports)
            lines.append("")
        lines.append(f"interface {name}Protocol {{")
        for method in uc.methods:
            sig = self._kotlin_method_signature(method)
            lines.append(f"    {sig}")
        lines += ["}", "", footer, ""]
        return "\n".join(lines)

    def generate_usecase_impl(self, name: str, uc: UseCaseDef) -> str:
        pkg = f"{self._package}.usecase"
        imports = self._imports_for_methods(uc.methods, current_package=pkg)
        # Repository dependencies live in {package}.repository.protocol.{Name}
        repo_imports = [
            f"import {self._package}.repository.protocol.{dep}"
            for dep in uc.repositories
        ]
        lines = [
            f"package {pkg}",
            "",
            f"import {self._package}.usecase.protocol.{name}Protocol",
            "import javax.inject.Inject",
        ]
        if repo_imports:
            lines.extend(repo_imports)
        if imports:
            lines.extend(imports)
        lines += [
            "",
            f"class {name} @Inject constructor(",
        ]
        for dep in uc.repositories:
            prop_name = _lower_first(dep)
            lines.append(f"    private val {prop_name}: {dep},")
        lines += [
            f") : {name}Protocol {{",
        ]
        for method in uc.methods:
            sig = self._kotlin_method_signature(method, override=True)
            lines.append(f"    {sig} {{")
            lines.append(f'        TODO("Implement {method.name}")')
            lines.append("    }")
            lines.append("")
        lines += ["}", ""]
        return "\n".join(lines)

    # --- Helpers ---

    def _kotlin_method_signature(self, method: MethodDef, override: bool = False) -> str:
        params = ", ".join(
            f"{p.name}: {self._type_mapper.resolve_class(p.type, 'android')}"
            for p in method.params
        )
        prefix = "override " if override else ""
        suspend = "suspend " if method.is_async else ""
        sig = f"{prefix}{suspend}fun {method.name}({params})"
        if method.return_type:
            rt = self._type_mapper.resolve_class(method.return_type, "android")
            sig += f": {rt}"
        return sig

    def _method_proto_signature(self, method: MethodDef) -> str:
        """Kotlin Protocol signature for a ``view_model.methods`` entry."""
        params = ", ".join(
            f"{p.name}: {self._map_type(p.type)}"
            for p in method.params
        )
        suspend = "suspend " if method.is_async else ""
        sig = f"{suspend}fun {method.name}({params})"
        if method.return_type:
            sig += f": {self._map_type(method.return_type)}"
        return sig

    def _var_proto_signature(self, var: VarDef) -> str:
        """Kotlin Protocol signature for a ``view_model.vars`` entry."""
        type_str = _kotlin_optional(self._map_type(var.type), var.optional)
        keyword = "val" if var.read_only else "var"
        return f"{keyword} {var.name}: {type_str}"

    def _map_type(self, spec_type: str) -> str:
        """Resolve a spec type to Kotlin.

        Closure/lambda types (containing ``->``) walk through the type
        mapper for each sub-expression so authors can write spec-side
        notation (``Bool``, ``Array(Foo)``, ``[Foo]``) inside callback
        signatures and have it translated (``Boolean``, ``List<Foo>``).
        Plain names take the fast path.
        """
        if "->" in spec_type:
            return self._type_mapper.resolve_in_string(spec_type, "android")
        return self._type_mapper.resolve_class(spec_type, "android")

    def _var_default_value(self, var: VarDef) -> str | None:
        """Kotlin initializer value for the Impl scaffold."""
        if var.optional:
            return "null"
        if "->" in var.type:
            return None
        try:
            default = self._type_mapper.resolve_default(var.type, "android")
        except Exception:  # pragma: no cover
            return None
        if default is None:
            return None
        return _kotlin_literal(default)


def _to_snake(name: str) -> str:
    return re.sub(r"([A-Z])", r"_\1", name).lower().lstrip("_")


def _lower_first(name: str) -> str:
    return name[0].lower() + name[1:] if name else name


def _kotlin_literal(value) -> str:
    """Render a Python default-value as a Kotlin literal for Impl scaffolds."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "listOf(" + ", ".join(_kotlin_literal(v) for v in value) + ")"
    return str(value)


