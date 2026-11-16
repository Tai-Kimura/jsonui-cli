"""A new screen's web UseCase and Repository scaffolds type-check (the pinned
tsc, strict) once the models they name exist — written by `jui g project`
before the API sync wrote those models, as in the report, and given their imports by
`jui build`. Ticket jui-g-project-new-screen-stubs-do-not-compile.

The ViewModel is not here: it extends the Base rjui generates (Ruby), which
_new_screen_stubs.py does not run.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests import _new_screen_stubs as ns
from tests.test_emitted_typescript_compiles import _tsc


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    return ns.write_project(tmp_path_factory.mktemp("stubs") / "app")


def test_the_web_usecase_and_repository_scaffolds_type_check(project, tmp_path):
    config = ns.tsconfig(project, tmp_path / "next-router.d.ts")
    run = subprocess.run([str(_tsc()), "-p", str(config)], cwd=project / "web", capture_output=True, text=True,
                         timeout=300, env={**os.environ})
    errors = sorted({line for line in run.stdout.splitlines() if "error TS" in line})
    assert (run.returncode == 0) == (not errors), f"rc={run.returncode}\n{run.stdout[-2000:]}"
    assert errors == []
    listed = subprocess.run([str(_tsc()), "-p", str(config), "--listFilesOnly"], cwd=project / "web",
                            capture_output=True, text=True, timeout=300).stdout
    assert "src/usecase/StubIntroUseCase.ts" in listed and "src/repository/StubRepository.ts" in listed   # it looked


def test_the_web_scaffolds_name_the_app_types_they_import(project):
    """The arm reaches the shape: the UseCase names the models it now imports."""
    uc = (project / "web/src/usecase/StubIntroUseCase.ts").read_text(encoding="utf-8")
    assert "Promise<StubStartResult>" in uc and 'import type { StubStartResult } from "@/model/StubModels";' in uc
