"""A new screen's scaffold, as `jui g project` and `jui build` leave it, for the
compiler arms (ticket jui-g-project-new-screen-stubs-do-not-compile).

The order is the reporting consumer's (three new screens, 2.3.19): `jui
init` for the three faces, the specs, `jui g project`, then the app types the
specs name — the consumer's came from the API model sync, which runs inside `jui build`
— and then the three protocol syncs `jui build` runs (ViewModel, UseCase,
Repository). So a scaffold is written before the types it names exist, as it
was there.

`jui build` also runs sjui / kjui / rjui (Ruby); what they write that the
scaffold touches is stood in for, one line a screen: the `{Name}Data` each
writes (Swift struct, Kotlin data class in `<package>.data`). The web
ViewModel extends rjui's generated Base, so the web arm compiles the UseCase,
the Repository and the models — the two files that had no import — and not
the ViewModel. Everything runs in subprocesses with the project as their cwd:
nothing here changes this process's directory.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JUI = REPO / "jui_tools" / "bin" / "jui"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "new_screen_stubs"
PACKAGE = "com.example.stubfix"
KOTLIN = Path("android/app/src/main/kotlin") / PACKAGE.replace(".", "/")
SWIFT = Path("ios/ios")
SCREENS = {"StubBox": {}, "StubIntro": {"agree": "Bool"}, "StubSettings": {}}   # each Data's fields (the layouts' data)

#: The app types the specs name, written where the API model sync puts them.
MODELS = {
    "swift": (SWIFT / "Model" / "StubModels.swift",
              "// the app types the specs name (a consumer's: written by the API model sync)\n"
              "struct StubItem {}\nstruct StubStartResult {}\n"),
    "kotlin": (KOTLIN / "model" / "StubModels.kt",
               f"package {PACKAGE}.model\n\nclass StubItem\nclass StubStartResult\n"),
    "ts": (Path("web/src/model/StubModels.ts"),
           "export interface StubItem { id: string }\nexport interface StubStartResult { ok: boolean }\n"),
}
#: The web network layer the Repository scaffold imports by default (rjui.config.json can point it elsewhere).
NETWORK = {
    Path("web/src/core/network/apiClient.ts"): 'export type HttpMethod = "GET" | "POST";\nexport class ApiClient {}\n',
    Path("web/src/core/network/apiEndpoints.ts"): "export interface ApiEndpoint { path: string }\n",
}

_SYNCS = """
import argparse, sys
sys.path.insert(0, {jt!r})
from pathlib import Path
from jui_cli.commands import build_cmd as b
from jui_cli.core.config_manager import ConfigManager
mgr = ConfigManager(Path('jui.config.json').resolve())
config = mgr.load()
specs = b._load_all_specs(mgr)
args = argparse.Namespace(dry_run=False, ios_only=False, android_only=False, web_only=False, platform=None)
for sync in (b._sync_viewmodel_protocols, b._sync_usecase_protocols, b._sync_repository_protocols):
    if sync(mgr, config, config.get('platforms', {{}}), args, specs=specs) is False:
        sys.exit(f'{{sync.__name__}} failed')
"""


#: This checkout's platform tools, put first on PATH for `jui init` (which runs `sjui init`, `kjui init`, `rjui
#: init` by name): the arm tests this tree's tools, and a CI runner has none of its own on PATH — the arm went red
#: there with "'sjui' not found in PATH" while green on a machine that had them installed.
TOOL_BINS = [REPO / f"{tool}_tools" / "bin" for tool in ("sjui", "kjui", "rjui")]


def _run(cmd: list[str], cwd: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("JUI_VIZ")}
    env["PATH"] = os.pathsep.join([*map(str, TOOL_BINS), env.get("PATH", "")])
    run = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600, env=env)
    assert run.returncode == 0, f"{' '.join(map(str, cmd[:3]))} … rc={run.returncode}\n{(run.stdout + run.stderr)[-3000:]}"


def write_project(root: Path) -> Path:
    """The project as the consumer had it after `jui g project` and one `jui build`."""
    root.mkdir(parents=True, exist_ok=True)
    _run([sys.executable, str(JUI), "init", "--project-name", "StubFix", "--ios", "ios", "--android", "android",
          "--package-name", PACKAGE, "--web", "web", "--no-sync-tools"], root)
    specs = root / "docs/screens/json"
    specs.mkdir(parents=True, exist_ok=True)
    for spec in sorted(FIXTURE.glob("*.spec.json")):
        (specs / spec.name).write_text(spec.read_text(encoding="utf-8"), encoding="utf-8")
    _run([sys.executable, str(JUI), "g", "project"], root)
    for rel, text in [*MODELS.values(), *NETWORK.items()]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _run([sys.executable, "-c", _SYNCS.format(jt=str(REPO / "jui_tools"))], root)
    for name, fields in SCREENS.items():   # what sjui / kjui write for each layout
        swift = "".join(f"    var {f}: {t} = false\n" for f, t in fields.items())
        # kjui's shape: a screen with no data fields gets one placeholder (a data class needs a parameter)
        kotlin = ", ".join(f"var {f}: Boolean = false" for f in fields) or 'val placeholder: String = "placeholder"'
        (root / SWIFT / "Data").mkdir(parents=True, exist_ok=True)
        (root / SWIFT / "Data" / f"{name}Data.swift").write_text(f"struct {name}Data {{\n{swift}}}\n", encoding="utf-8")
        (root / KOTLIN / "data").mkdir(parents=True, exist_ok=True)
        (root / KOTLIN / "data" / f"{name}Data.kt").write_text(
            f"package {PACKAGE}.data\n\ndata class {name}Data({kotlin})\n", encoding="utf-8")
    return root


def swift_sources(root: Path) -> list[Path]:
    return sorted(p for d in ("ViewModel", "UseCase", "Repository", "Data", "Model") for p in (root / SWIFT / d).rglob("*.swift"))


def kotlin_sources(root: Path) -> list[Path]:
    return sorted(p for d in ("viewmodels", "viewmodel", "usecase", "repository", "data", "model")
                  for p in (root / KOTLIN / d).rglob("*.kt"))


#: SwiftJsonUI as a module with nothing in it: the scaffolds import it and use no name from it.
SWIFTJSONUI_SHIM = "public enum SwiftJsonUIStandIn {}\n"

#: The libraries the Kotlin scaffolds import, as stand-ins in their real packages, so a scaffold that forgets an
#: import fails as it would against the real ones (kotlinc alone: CI's compiler job has no Gradle cache).
KOTLIN_SHIMS = {
    "Lifecycle.kt": "package androidx.lifecycle\nabstract class ViewModel\n",
    "Hilt.kt": "package dagger.hilt.android.lifecycle\nannotation class HiltViewModel\n",
    "Inject.kt": "package javax.inject\nannotation class Inject\nannotation class Singleton\n",
    "Flow.kt": (
        "package kotlinx.coroutines.flow\n"
        "interface StateFlow<out T> { val value: T }\n"
        "interface MutableStateFlow<T> : StateFlow<T> { override var value: T }\n"
        "fun <T> MutableStateFlow(value: T): MutableStateFlow<T> = object : MutableStateFlow<T> { override var value: T = value }\n"
        "fun <T> MutableStateFlow<T>.asStateFlow(): StateFlow<T> = this\n"
        "inline fun <T> MutableStateFlow<T>.update(function: (T) -> T) { value = function(value) }\n"),
}


def tsconfig(root: Path, next_shim: Path) -> Path:
    """strict, the project's `@/` paths; next's router type stood in for (no next install)."""
    next_shim.write_text("export interface AppRouterInstance { push(href: string): void }\n", encoding="utf-8")
    path = root / "web" / "tsconfig.stubs.json"
    path.write_text(json.dumps({
        "compilerOptions": {"strict": True, "noEmit": True, "target": "ES2022", "module": "ESNext",
                            "moduleResolution": "bundler", "skipLibCheck": True, "baseUrl": ".",
                            "paths": {"@/*": ["src/*"],
                                      "next/dist/shared/lib/app-router-context.shared-runtime": [str(next_shim)]}},
        "include": ["src/usecase/**/*.ts", "src/repository/**/*.ts", "src/model/**/*.ts", "src/core/**/*.ts"],
    }), encoding="utf-8")
    return path
