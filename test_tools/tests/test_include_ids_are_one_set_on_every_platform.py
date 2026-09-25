"""One layout set, the same ids on every platform (design U8, the ticket's ask 2).

shared/core/include_ids_fixture.json holds specimens — a screen and the
partials it includes, and the ids the expanded screen carries (`expected`, a
sorted list: duplicates are part of the answer). Each specimen goes through
the Python expander and the three codegens, and the ids each one EMITS are
read back in its own spelling:

  python  `jui_cli.core.layout_facts` (the spec validator's, coverage's and
          the layout-id gate's expander)
  sjui    the generated SwiftUI view's `.accessibilityIdentifier("…")`
  kjui    the generated Compose view's `testTag("…")`
  rjui    the generated components, with the prefix on, bundled by esbuild
          with a React stand-in that records every element's `id`, and
          RENDERED by node — so the helper and the include sites' prefixes are
          evaluated as a browser would

Every one must equal `expected`, count included (conservation: the ids read
back are as many as the fixture names). The SwiftJsonUI / KotlinJsonUI
dynamic expanders read the same file from their own tests.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((REPO / "shared/core/include_ids_fixture.json").read_text(encoding="utf-8"))
SPECIMENS = sorted(FIXTURE["specimens"])
SCREEN = FIXTURE["screen"]
ESBUILD = Path(os.environ.get("JSONUI_TEST_ESBUILD")
               or REPO / "rjui_tools/spec/support/node_modules/.bin/esbuild")
ENV = {**os.environ, "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}

SJUI = r"""
require 'json'
require 'swiftui/json_to_swiftui_converter'
JSON.parse(ARGV[0]).each do |root|
  SjuiTools::SwiftUI::IncludeExpander.layouts_root = File.join(root, 'layouts')
  SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_file(
    File.join(root, 'layouts', ARGV[1]), File.join(root, 'screen.swift'))
end
"""

KJUI = r"""
require 'json'
require 'compose/compose_builder'
JSON.parse(ARGV[0]).each do |root|
  cfg = { 'source_directory' => '', 'layouts_directory' => 'layouts', 'view_directory' => 'kjui_views' }
  KjuiTools::Core::ConfigManager.define_singleton_method(:load_config) { cfg }
  KjuiTools::Core::ProjectFinder.define_singleton_method(:get_full_source_path) { root }
  KjuiTools::Core::ProjectFinder.define_singleton_method(:get_package_name) { 'com.example.app' }
  Dir.chdir(root) do
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.build_file(File.join(builder.instance_variable_get(:@layouts_dir), ARGV[1]))
  end
end
"""

RJUI = r"""
require 'json'
require 'fileutils'
require 'react/react_generator'
require 'cli/commands/build_command'
JSON.parse(ARGV[0]).each do |root|
  layouts, out = File.join(root, 'layouts'), File.join(root, 'web', 'gen')
  cfg = { 'typescript' => true, 'use_tailwind' => true, '_include_id_prefix' => true,
          'generated_directory' => out }
  Dir.glob(File.join(layouts, '**', '*.json')).sort.each do |f|
    rel = f.sub(layouts + '/', '').sub(/\.json\z/, '')
    sub = File.dirname(rel) == '.' ? '' : File.dirname(rel)
    name = File.basename(rel).split('_').map(&:capitalize).join
    code = RjuiTools::React::ReactGenerator.new(cfg.dup).generate(name, JSON.parse(File.read(f)), subdir: sub)
    dest = File.join(out, 'components', sub, "#{name}.tsx")
    FileUtils.mkdir_p(File.dirname(dest))
    File.write(dest, code)
  end
  helper = RjuiTools::CLI::Commands::BuildCommand.allocate
  helper.instance_variable_set(:@config, cfg)
  helper.send(:emit_include_id_helper)
end
"""

# The web side's stand-ins: React records every element, the string manager
# answers nothing — the ids are what is read, and ids are not strings.json keys.
REACT_STUB = """
const createElement = (type, props, ...children) => ({ type, props: { ...(props || {}), children } });
export default { createElement, Fragment: 'fragment' };
"""
STRING_MANAGER_STUB = (
    "export const useStringManager = (): any => "
    "new Proxy({}, { get: () => new Proxy({}, { get: () => '' }) });\n")
ENTRY = """
import {{ {component} }} from '@/generated/components/{component}';
const ids: string[] = [];
const render = (el: any): void => {{
  if (el == null || typeof el !== 'object') return;
  if (Array.isArray(el)) {{ el.forEach(render); return; }}
  if (typeof el.type === 'function') {{ render(el.type(el.props)); return; }}
  if (el.props && typeof el.props.id === 'string') ids.push(el.props.id);
  render(el.props && el.props.children);
}};
render(({component} as any)({{}}));
console.log(JSON.stringify(ids));
"""


def _missing(what: str, install: str) -> None:
    """A missing tool: in CI this FAILS — a gate that skips gates nothing, and
    29 skips would sit in a green summary. Locally it skips, counted and
    named, as the emitted-TypeScript arm does."""
    if os.environ.get("CI"):
        pytest.fail(f"{what} is not available and this is CI — the include-id agreement "
                    f"would be unmeasured. {install}")
    pytest.skip(f"{what} is not available — the include-id agreement is UNMEASURED here "
                f"({install})")


def _pascal(stem: str) -> str:
    return "".join(p.capitalize() for p in stem.split("_"))


@pytest.fixture(scope="module")
def roots(tmp_path_factory):
    base = tmp_path_factory.mktemp("include_ids")
    out = {}
    for name in SPECIMENS:
        root = base / name
        for rel, tree in FIXTURE["specimens"][name]["layouts"].items():
            path = root / "layouts" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(tree), encoding="utf-8")
        out[name] = root
    return out


def _ruby(tool: str, script: str, roots: dict) -> None:
    if shutil.which("ruby") is None:
        _missing("ruby", "install ruby")
    result = subprocess.run(
        ["ruby", "-I", str(REPO / tool / "lib"), "-e", script,
         json.dumps([str(r) for r in roots.values()]), SCREEN],
        capture_output=True, text=True, env=ENV, cwd=str(REPO))
    assert result.returncode == 0, f"{tool}: {result.stderr[-2000:]}"


@pytest.fixture(scope="module")
def emitted(roots):
    """{platform: {specimen: [ids read back]}} — each codegen runs once."""
    _ruby("sjui_tools", SJUI, roots)
    _ruby("kjui_tools", KJUI, roots)
    _ruby("rjui_tools", RJUI, roots)
    out = {"sjui": {}, "kjui": {}, "rjui": {}}
    for name, root in roots.items():
        swift = (root / "screen.swift").read_text(encoding="utf-8")
        out["sjui"][name] = re.findall(r'\.accessibilityIdentifier\("([^"]*)"\)', swift)
        kotlin = next(root.glob("kjui_views/**/*GeneratedView.kt")).read_text(encoding="utf-8")
        out["kjui"][name] = re.findall(r'testTag\("([^"]*)"\)', kotlin)
        out["rjui"][name] = _render_web(root)
    return out


def _render_web(root: Path) -> list:
    if shutil.which("node") is None or not ESBUILD.exists():
        _missing("node / esbuild", "npm ci --prefix rjui_tools/spec/support")
    web = root / "web"
    (web / "react_stub.js").write_text(REACT_STUB, encoding="utf-8")
    (web / "gen" / "StringManager.ts").write_text(STRING_MANAGER_STUB, encoding="utf-8")
    (web / "tsconfig.json").write_text(json.dumps({"compilerOptions": {
        "baseUrl": ".", "jsx": "react",
        "paths": {"@/generated/*": ["gen/*"], "react": ["react_stub.js"]}}}), encoding="utf-8")
    (web / "entry.tsx").write_text(ENTRY.format(component=_pascal(Path(SCREEN).stem)),
                                   encoding="utf-8")
    bundle = subprocess.run(
        [str(ESBUILD), "entry.tsx", "--bundle", "--format=esm", "--platform=node",
         "--tsconfig=tsconfig.json", "--outfile=out.mjs", "--log-level=error"],
        capture_output=True, text=True, cwd=web, env=ENV)
    assert bundle.returncode == 0, bundle.stderr
    run = subprocess.run(["node", "out.mjs"], capture_output=True, text=True, cwd=web, env=ENV)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_the_fixture_is_well_formed():
    for name in SPECIMENS:
        specimen = FIXTURE["specimens"][name]
        assert SCREEN in specimen["layouts"], name
        assert specimen["expected"] == sorted(specimen["expected"]), name
        assert all(rel.endswith(".json") for rel in specimen["layouts"]), name


@pytest.mark.parametrize("name", SPECIMENS)
def test_python_expander(roots, name):
    from jui_cli.core.layout_facts import layout_facts
    facts = layout_facts({"metadata": {"layoutFile": Path(SCREEN).stem}}, None,
                         layouts_dir=roots[name] / "layouts", styles_dir=roots[name] / "layouts")
    got = sorted(facts.id_counts.elements())
    expected = FIXTURE["specimens"][name]["expected"]
    assert len(got) == len(expected), f"python: read back {len(got)}, the fixture names {len(expected)}"
    assert got == expected, f"python disagrees on {name}"


@pytest.mark.parametrize("platform", ["sjui", "kjui", "rjui"])
@pytest.mark.parametrize("name", SPECIMENS)
def test_codegen(emitted, platform, name):
    got = sorted(emitted[platform][name])
    expected = FIXTURE["specimens"][name]["expected"]
    assert len(got) == len(expected), \
        f"{platform}: read back {len(got)} ids, the fixture names {len(expected)} ({name})"
    assert got == expected, f"{platform} disagrees on {name}"
