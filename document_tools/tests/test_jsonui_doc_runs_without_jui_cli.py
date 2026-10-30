"""jsonui-doc runs where jui_cli is not importable.

jsonui-doc is installed on its own (`pip install git+…#subdirectory=document_tools`,
as a consumer's CI does) and run from the distribution's launcher with a
project's own python; neither carries jui_cli. 2.3.33's initial-value check
imported jui_cli's collection reading, so every `validate spec` and `generate
spec` there ended in ModuleNotFoundError, rc 1 — a spec with no initial value
too, since the type was read before the value (tickets
jsonui-doc-validate-imports-jui-cli-when-installed-alone and
2026-10-30-jsonui-doc-launcher-crashes-without-jui-cli-on-path).

Each run here is a child python in which importing jui_cli fails, whatever is
installed beside it (a meta-path finder refuses it; the control below shows
it does), through both entry points: the launcher script and the package's
`jsonui_doc_cli.cli:main`. The spec carries a variable with no initial value
and two collections, a `[K: V]` given `{}` and a list of them given `[]`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

DOCUMENT_TOOLS = Path(__file__).resolve().parents[1]
LAUNCHER = DOCUMENT_TOOLS / "jsonui-doc"

# Run in the child: refuse jui_cli, then hand over to the entry point named in argv[1].
CHILD = r'''
import runpy, sys
class NoJuiCli:
    def find_spec(self, name, path=None, target=None):
        if name == "jui_cli" or name.startswith("jui_cli."):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None
sys.meta_path.insert(0, NoJuiCli())
for loaded in [m for m in sys.modules if m == "jui_cli" or m.startswith("jui_cli.")]:
    del sys.modules[loaded]
entry, rest = sys.argv[1], sys.argv[2:]
if entry == "probe":
    import jui_cli  # the control: must fail
elif entry == "launcher":
    sys.argv = [rest[0]] + rest[1:]
    runpy.run_path(rest[0], run_name="__main__")
else:
    sys.argv = ["jsonui-doc"] + rest
    from jsonui_doc_cli.cli import main
    sys.exit(main())
'''


def _spec(variables) -> dict:
    return {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Probe", "displayName": "Probe", "description": "d"},
        "structure": {"components": [{"id": "title_label", "type": "Label", "description": "the title"}],
                      "layout": {"root": "title_label", "children": []}},
        "stateManagement": {"uiVariables": variables},
    }


NO_VALUE = [{"name": "title", "type": "String", "description": "no initial value"}]
COLLECTIONS = NO_VALUE + [
    {"name": "counts", "type": "[String: Int]", "description": "a dictionary", "defaultValue": "{}"},
    {"name": "rows", "type": "[[String: Int]]", "description": "a list of dictionaries", "defaultValue": "[]"},
]


# A consumer's CI installs exactly test_tools, document_tools (--no-deps),
# PyYAML and markdown-it-py — no jui_tools (the docs site's, run 41065092124,
# stopped at its jsonui-doc-validate gate). The "ci" entry starts python with
# -I -S and a path of the standard library and those four only, so jui_cli is
# absent the way it is there, with no finder standing in for it.
CI_CHILD = r'''
import sys
sys.path[:] = [p for p in sys.argv[1].split("\n") if p]
entry, rest = sys.argv[2], sys.argv[3:]
if entry == "probe":
    import yaml, markdown_it, jsonui_doc_cli, jsonui_test_cli  # all four present
    import jui_cli  # the control: must fail
sys.argv = ["jsonui-doc"] + rest
from jsonui_doc_cli.cli import main
sys.exit(main())
'''


def _ci_path() -> str:
    import sysconfig

    import markdown_it
    import yaml
    stdlib = [sysconfig.get_paths()["stdlib"], sysconfig.get_paths()["platstdlib"]]
    dynload = [p for p in sys.path if p.endswith("lib-dynload")]
    sites = {str(Path(m.__file__).resolve().parents[1]) for m in (yaml, markdown_it)}
    return "\n".join([str(DOCUMENT_TOOLS), str(DOCUMENT_TOOLS.parent / "test_tools"), *stdlib, *dynload, *sorted(sites)])


def _child(tmp_path: Path, entry: str, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(DOCUMENT_TOOLS), "HOME": str(tmp_path)}
    if entry.startswith("ci"):
        command = [sys.executable, "-I", "-S", "-c", CI_CHILD, _ci_path(), "probe" if entry == "ci-probe" else "run", *args]
    else:
        command = [sys.executable, "-c", CHILD, entry, *args]
    return subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)


def test_the_child_cannot_import_jui_cli(tmp_path):
    r = _child(tmp_path, "probe")
    assert r.returncode != 0 and "No module named 'jui_cli'" in r.stderr, r.stderr


def test_the_ci_child_has_the_four_packages_and_no_jui_cli(tmp_path):
    r = _child(tmp_path, "ci-probe")
    assert r.returncode != 0 and "No module named 'jui_cli'" in r.stderr, r.stderr
    assert "yaml" not in r.stderr.split("No module named")[0], r.stderr


@pytest.mark.parametrize("entry", ["launcher", "package", "ci"])
@pytest.mark.parametrize("variables", [NO_VALUE, COLLECTIONS], ids=["no initial value", "collections"])
def test_validate_and_generate_spec_run_without_jui_cli(tmp_path, entry, variables):
    spec = tmp_path / "probe.spec.json"
    spec.write_text(json.dumps(_spec(variables)), encoding="utf-8")
    head = [str(LAUNCHER)] if entry == "launcher" else []

    validated = _child(tmp_path, entry, *head, "validate", "spec", str(spec))
    out = validated.stdout + validated.stderr
    assert "ModuleNotFoundError" not in out and "Traceback" not in out, out
    assert validated.returncode == 0 and "Result: PASSED" in out, out
    assert "is not a value of" not in out, out

    html = tmp_path / "probe.html"
    generated = _child(tmp_path, entry, *head, "generate", "spec", str(spec), "--format", "html", "-o", str(html))
    out = generated.stdout + generated.stderr
    assert "Traceback" not in out, out
    assert generated.returncode == 0 and html.is_file() and html.stat().st_size > 0, out
