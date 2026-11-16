"""A method may be a bare signature string, and the schema says so.

`dataFlow.repositories[].methods[]` is declared
`oneOf[string, repositoryMethod]` — "Method signatures (string or structured
object)". Two functions read that list. `_format_method_html` branched on the
type; `_collect_method_endpoints` was annotated `method: dict` and called
`.get` unconditionally, so a spec using the string form killed its own page
with `'str' object has no attribute 'get'` and took `generate html` to exit 1.

Measured 2026-09-05 on a consumer corpus: 38 spec files use the string form,
5 of them crashed, and the discriminator was `dataFlow.diagram` — present, and
the spec never reaches the mermaid builder. So 33 files were one deleted
field away from the same crash. That is why the arms below go through the
declaration rather than through the five file names.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonui_doc_cli.spec_doc import html_generator as hg
from jsonui_doc_cli.spec_doc import screen_spec_schema as sch


def _repo_method_items_schema():
    """The declaration itself, walked — not a copy of it."""
    defs = getattr(sch, "SCREEN_SPEC_SCHEMA", None) or getattr(sch, "SCHEMA", None)
    if defs is None:
        for name in dir(sch):
            v = getattr(sch, name)
            if isinstance(v, dict) and "$defs" in v:
                defs = v
                break
    assert defs is not None, "could not find the screen spec schema object"
    return json.dumps(defs)


def test_the_schema_really_declares_the_string_form():
    # If this ever stops being true the guard below is no longer required
    # behaviour, and this arm should be the one that says so.
    text = _repo_method_items_schema()
    assert "Method signatures (string or structured object)" in text


def test_a_string_signature_contributes_no_endpoints():
    sig = "getList(params: Record<string, string | number>): Promise<X>"
    assert hg._collect_method_endpoints(sig) == []


def test_a_dict_method_still_yields_its_endpoints():
    assert hg._collect_method_endpoints({"endpoint": "GET /labels"}) == ["GET /labels"]
    assert hg._collect_method_endpoints(
        {"endpoints": ["GET /a", "POST /b"]}) == ["GET /a", "POST /b"]
    assert hg._collect_method_endpoints(
        {"endpoint": "GET /a", "endpoints": ["POST /b"]}) == ["GET /a", "POST /b"]


def test_the_two_consumers_of_the_list_agree_about_the_type():
    """Both read `methods[]`; neither may raise on a shape the other accepts.

    This is the actual defect: not that a string is unhandled, but that ONE
    of two readers of the same list had read the declaration.
    """
    for method in ("someCall(): Promise<void>", {"name": "x"}, None, 42, []):
        hg._collect_method_endpoints(method)   # must not raise
        hg._format_method_html(method)         # must not raise


def test_a_string_signature_declares_no_calls_either():
    """The SECOND site, found only by re-running the corpus after the first fix.

    `useCases[].methods[]` is declared `oneOf[string, ...]` too (schema line
    664), and the mermaid builder read `m.get("calls")` unguarded. Fixing
    only the endpoints site left one spec of the five still crashing — the
    same defect, a different field. All three method containers
    (viewModel 566 / repository 644 / useCase 664) allow the string form, so
    both readers are guarded rather than the one the traceback named.
    """
    assert hg._collect_method_calls("run(): Promise<void>") == []
    assert hg._collect_method_calls({"calls": ["Repo.getList", 7]}) == ["Repo.getList"]
    assert hg._collect_method_calls({}) == []


def test_all_three_method_containers_accept_the_string_form():
    spec = {
        "metadata": {"screenName": "S", "platforms": ["web"]},
        "dataFlow": {
            "viewModel": {"name": "SVM", "methods": ["load(): Promise<void>"]},
            "useCases": [{"name": "SUC", "methods": ["run(): Promise<void>"]}],
            "repositories": [{"name": "SRepo", "methods": ["getList(): Promise<X>"]}],
        },
    }
    html = hg.generate_spec_html(spec)   # must not raise
    assert "SRepo" in html


def test_a_spec_using_the_string_form_renders_without_a_diagram():
    """The end-to-end shape, built the way the report describes it.

    No `dataFlow.diagram`, so generation reaches `_build_dataflow_mermaid` —
    the path that crashed. A spec WITH a diagram never got there, which is
    exactly why only 5 of 38 files showed the symptom.
    """
    spec = {
        "metadata": {"screenName": "Sample", "platforms": ["web"]},
        "dataFlow": {
            "repositories": [{
                "name": "SampleRepository",
                "methods": [
                    "getList(params: Record<string, string>): Promise<Item[]>",
                    {"name": "getDetail", "endpoint": "GET /items/{id}"},
                ],
            }],
        },
    }
    assert "dataFlow" in spec and "diagram" not in spec["dataFlow"]
    html = hg.generate_spec_html(spec)
    assert "SampleRepository" in html
    # The dict method's endpoint still reaches the diagram; the string one
    # simply contributes nothing.
    assert "getDetail" in html
