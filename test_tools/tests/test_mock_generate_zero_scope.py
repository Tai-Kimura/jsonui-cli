"""Zero endpoints in scope is a legitimate state that must stay servable.

A new sub-project whose API face is not in the shared swagger yet (the
backend pushes its realm later) matches 0 of the shared swagger's
endpoints. `mock generate` reported "Generated 0 mock file(s) into
tests/mocks/generated/" and exited 0, but deferred the mkdir to the
first file write — so the directory it had just named did not exist,
and `mock serve` refused with "run 'jsonui-test mock generate' first":
a hint pointing at the command that had just succeeded without changing
anything. The consumer's mock-independent tests (its BFF security
regressions) could not run at all until the directory was dug by hand.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import generate
from jsonui_test_cli.mock.scope import PathScope
from jsonui_test_cli.mock.server import MockStore

SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/user/items": {"get": {
            "operationId": "listUserItems",
            "responses": {"200": {"content": {"application/json": {
                "schema": {"type": "object",
                           "properties": {"id": {"type": "string"}}}}}}},
        }},
    },
}

ADMIN_SCOPE = PathScope(include=("/api/admin/*",))


@pytest.fixture
def swagger(tmp_path):
    path = tmp_path / "shared.json"
    path.write_text(json.dumps(SPEC), encoding="utf-8")
    return str(path)


def test_generate_with_zero_in_scope_creates_the_directory_it_reports(
        swagger, tmp_path):
    mock_dir = tmp_path / "tests" / "mocks"
    report = generate([swagger], mock_dir, scope=ADMIN_SCOPE)
    assert report.created == []
    assert len(report.out_of_scope) == 1
    assert (mock_dir / "generated").is_dir()


def test_the_empty_tree_survives_a_rerun(swagger, tmp_path):
    # _clear_generated prunes directories that emptied out; the rerun must
    # end in the same servable state, not oscillate.
    mock_dir = tmp_path / "tests" / "mocks"
    generate([swagger], mock_dir, scope=ADMIN_SCOPE)
    generate([swagger], mock_dir, scope=ADMIN_SCOPE)
    assert (mock_dir / "generated").is_dir()


def test_the_store_loads_from_the_empty_tree(swagger, tmp_path):
    # What `mock serve` does with the result: an empty store is a servable
    # state (mock-independent suites need the server up), not an error.
    mock_dir = tmp_path / "tests" / "mocks"
    generate([swagger], mock_dir, scope=ADMIN_SCOPE)
    store = MockStore.load(mock_dir)
    assert store.endpoints == {} or not store.endpoints
