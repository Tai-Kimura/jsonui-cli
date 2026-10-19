"""jui viz: the data flow diagram on the whiteboard is the one document_tools' spec page draws (2.3.5).

sheet.dataflow_mermaid reaches document_tools' html_generator by jui's own routes (core/document_tools_import) and
uses its rule — ``dataFlow.diagram`` when the spec has one, else ``_build_dataflow_mermaid`` — so there is one copy
of the builder. These arms compare it with the text the generated spec page puts in its ``<pre class="mermaid">``.
"""

from __future__ import annotations

import re

import pytest

from jui_cli.viz import sheet

SPEC = {
    "type": "screen_spec", "version": "1.0",
    "metadata": {"name": "twoFactor", "displayName": "二要素認証 <script>x</script>", "description": "d"},
    "dataFlow": {
        "viewModel": {"methods": [{"name": "verify", "description": "v"}, "resend()"], "vars": [{"name": "code", "type": "String"}]},
        "useCases": [{"name": "VerifyCodeUseCase", "repositories": ["AuthRepository"], "methods": [{"name": "run", "calls": ["AuthRepository.verify"]}]}],
        "repositories": [{"name": "AuthRepository", "methods": [{"name": "verify", "endpoint": "POST /auth/2fa"}]}],
        "apiEndpoints": [{"method": "POST", "path": "/auth/2fa", "summary": "verify"}, {"method": "GET", "path": "/auth/2fa/resend"}],
    },
}


def page_diagram(spec: dict) -> str | None:
    gen = sheet._doc_html()
    m = re.search(r'<pre class="mermaid">\n(.*?)\n</pre>', gen.generate_spec_html(spec), re.S)
    return m.group(1) if m else None


def test_document_tools_is_reached():
    assert sheet._doc_html() is not None, "html_generator not importable by jui's routes"


def test_the_diagram_is_the_spec_pages():
    text = sheet.dataflow_mermaid(SPEC)
    assert text.startswith("flowchart LR") and "AuthRepository" in text and "VerifyCodeUseCase" in text
    assert text == page_diagram(SPEC)


def test_a_diagram_the_spec_writes_is_used_as_it_is():
    spec = {**SPEC, "dataFlow": {**SPEC["dataFlow"], "diagram": "flowchart TD\n  A[\"自分で書いた図\"] --> B"}}
    assert sheet.dataflow_mermaid(spec) == "flowchart TD\n  A[\"自分で書いた図\"] --> B" == page_diagram(spec)


@pytest.mark.parametrize("spec", [{}, {"dataFlow": {}}, {"dataFlow": "x"}, {"dataFlow": {"notes": "only notes"}}])
def test_no_data_flow_no_diagram(spec):
    assert sheet.dataflow_mermaid(spec) == ""


def test_too_long_or_unreadable_gives_the_boxes():
    long = {"dataFlow": {"diagram": "flowchart LR\n" + "  A --> B\n" * 10_000}}
    assert sheet.dataflow_mermaid(long) == ""
    odd = {"metadata": {"name": "x"}, "dataFlow": {"repositories": "not a list", "viewModel": {"methods": 3}}}
    assert sheet.dataflow_mermaid(odd) == ""


def test_the_sheet_carries_it():
    doc = sheet.build_doc(SPEC, [], [], {"total": 0, "done": 0})
    assert doc["flowMermaid"] == sheet.dataflow_mermaid(SPEC)
    assert sheet.build_doc({}, [], [], {"total": 0, "done": 0})["flowMermaid"] == ""
