"""`jui build` gives an old scaffold the imports a fresh one carries, and nothing else
(ticket jui-g-project-new-screen-stubs-do-not-compile). The scaffold is written once by
`jui g project`, before the API sync writes the models it names; the compiler arms are
test_tools/tests/test_new_screen_stubs_*.py, these are the rules under them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jui_cli.commands.build_cmd import _ensure_impl_imports
from jui_cli.core.impl_updater import ensure_ts_imports, kotlin_has_simple_name
from jui_cli.core.spec_extractor import MethodDef, MethodParam as ParamDef
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.web_generator import WebGenerator

ARGS = argparse.Namespace(dry_run=False)


def test_a_ts_line_is_added_once_after_the_last_import():
    src = '// UseCase: X\nimport { Repo } from "@/repository/Repo";\n\nexport class X {}\n'
    line = 'import type { Item } from "@/models/Item";'
    once = ensure_ts_imports(src, [line])
    assert once == '// UseCase: X\nimport { Repo } from "@/repository/Repo";\n' + line + '\n\nexport class X {}\n'
    assert ensure_ts_imports(once, [line]) == once


def test_a_ts_name_the_file_already_binds_is_not_imported_again():
    for src in ('import { Item } from "@/elsewhere";\n', 'import { Item as I } from "@/x";\n',
                'import type { Other, Item } from "@/models";\n', "export interface Item { id: string }\n"):
        assert ensure_ts_imports(src, ['import type { Item } from "@/models/Item";']) == src, src


def test_a_file_with_no_import_gets_the_line_after_its_leading_comments():
    assert ensure_ts_imports("// a\n// b\nexport class X {}\n", ['import type { T } from "@/t";']) \
        == '// a\n// b\nimport type { T } from "@/t";\nexport class X {}\n'


def test_kotlin_skips_a_simple_name_already_taken():
    assert kotlin_has_simple_name("package a\nimport b.Foo\n", "c.Foo")            # imported from elsewhere
    assert kotlin_has_simple_name("package a\nimport b.Bar as Foo\n", "c.Foo")     # an alias
    assert kotlin_has_simple_name("package a\ndata class Foo(val x: Int)\n", "c.Foo")   # declared here
    assert not kotlin_has_simple_name("package a\nimport b.Foo\n", "b.Foo")        # the same one: ensure_kotlin_import's no-op
    assert not kotlin_has_simple_name("package a\nimport b.FooBar\n", "c.Foo")


def test_the_sync_adds_only_imports_and_a_second_run_changes_nothing(tmp_path):
    impl = tmp_path / "StubIntroUseCase.kt"
    body = ("package com.example.usecase\n\nimport javax.inject.Inject\n\nclass StubIntroUseCase @Inject constructor() {\n"
            "    suspend fun start(): StubStartResult { TODO() }\n}\n")
    impl.write_text(body, encoding="utf-8")
    lines = ["import com.example.model.StubStartResult", "import com.example.model.StubItem"]
    assert _ensure_impl_imports("android", impl, lines, ARGS) is True
    after = impl.read_text(encoding="utf-8")
    assert after == body.replace("import javax.inject.Inject\n",
                                 "import javax.inject.Inject\nimport com.example.model.StubStartResult\n")
    assert _ensure_impl_imports("android", impl, lines, ARGS) is False and impl.read_text(encoding="utf-8") == after
    assert _ensure_impl_imports("ios", impl, lines, ARGS) is False   # Swift: one module, nothing to import
    dry = tmp_path / "Dry.kt"
    dry.write_text(body, encoding="utf-8")
    assert _ensure_impl_imports("android", dry, lines, argparse.Namespace(dry_run=True)) is True
    assert dry.read_text(encoding="utf-8") == body


def _web(root: Path, type_map: dict | None = None) -> WebGenerator:
    path = None
    if type_map is not None:
        path = root / ".jsonui-type-map.json"
        path.write_text(json.dumps(type_map), encoding="utf-8")
    return WebGenerator(root, {}, TypeMapper(path))


def test_the_web_imports_come_from_the_type_map_hint_then_the_projects_export(tmp_path):
    (tmp_path / "src/models").mkdir(parents=True)
    (tmp_path / "src/models/Item.ts").write_text("export interface Item { id: string }\n", encoding="utf-8")
    (tmp_path / "src/models/index.ts").write_text("export type Batch = { n: number }\n", encoding="utf-8")
    gen = _web(tmp_path, {"version": "1.0", "types": {"Photo": {"class": "Photo", "web": {"class": "Photo", "imports": ["@/types/Photo"]}}}})
    method = MethodDef(name="load", params=[ParamDef(name="p", type="Photo")], return_type="[Item]", is_async=True)
    other = MethodDef(name="batch", params=[], return_type="Batch", is_async=True)
    missing = MethodDef(name="later", params=[], return_type="NotWrittenYet", is_async=True)
    assert gen.type_imports([method, other, missing], "@/usecase/X") == [
        'import type { Photo } from "@/types/Photo";',
        'import type { Item } from "@/models/Item";',
        'import type { Batch } from "@/models";',          # an index file is its folder
    ]   # a name found nowhere gets no line: it may yet be written, and a guessed path would not compile either
    assert gen.type_imports([MethodDef(name="d", params=[], return_type="Date", is_async=False)], "@/x") == []   # a global


def test_the_sync_leaves_a_name_the_impl_already_has_from_elsewhere(tmp_path):
    impl = tmp_path / "X.kt"
    body = "package com.example.usecase\n\nimport com.example.legacy.StubItem\n\nclass X\n"
    impl.write_text(body, encoding="utf-8")
    assert _ensure_impl_imports("android", impl, ["import com.example.model.StubItem"], ARGS) is False
    assert impl.read_text(encoding="utf-8") == body
    ts = tmp_path / "X.ts"
    ts.write_text('import { StubItem } from "@/legacy";\n', encoding="utf-8")
    assert _ensure_impl_imports("web", ts, ['import type { StubItem } from "@/model/StubModels";'], ARGS) is False


def test_a_type_only_a_method_the_impl_lacks_names_is_not_imported(tmp_path):
    """An old Impl that holds some of the spec's methods only: the types of the others would be unused imports
    (measured on a consumer: 38 of 108 added lines, each a no-unused-vars warning in the author's file)."""
    kt = tmp_path / "Repo.kt"
    kt.write_text("package a.repository\n\nimport javax.inject.Inject\n\nclass Repo {\n"
                  "    // returns a StubItem one day\n    suspend fun list(): List<StubItem> = TODO()\n}\n", encoding="utf-8")
    assert _ensure_impl_imports("android", kt, ["import a.model.StubItem", "import a.model.StubStartResult"], ARGS) is True
    text = kt.read_text(encoding="utf-8")
    assert "import a.model.StubItem\n" in text and "StubStartResult" not in text
    ts = tmp_path / "repo.ts"
    ts.write_text('import { ApiClient } from "@/core/network/apiClient";\n\nexport class Repo {\n'
                  '  /* Batch is for later */\n  async list(): Promise<Item[]> { throw new Error(""); }\n}\n', encoding="utf-8")
    assert _ensure_impl_imports("web", ts, ['import type { Item } from "@/models/Item";',
                                            'import type { Batch } from "@/models/Batch";'], ARGS) is True
    text = ts.read_text(encoding="utf-8")
    assert 'import type { Item } from "@/models/Item";' in text and "@/models/Batch" not in text


def test_a_type_the_body_names_is_imported_and_a_qualified_use_needs_none(tmp_path):
    kt = tmp_path / "Uc.kt"
    kt.write_text("package a.usecase\n\nclass Uc {\n    suspend fun start(): StubStartResult = TODO()\n"
                  "    val other: a.model.StubItem? = null\n}\n", encoding="utf-8")
    assert _ensure_impl_imports("android", kt, ["import a.model.StubStartResult", "import a.model.StubItem"], ARGS) is True
    text = kt.read_text(encoding="utf-8")
    assert "import a.model.StubStartResult\n" in text and "import a.model.StubItem" not in text
    nothing = tmp_path / "None.kt"
    nothing.write_text("package a\n\nclass N\n", encoding="utf-8")
    assert _ensure_impl_imports("android", nothing, ["import a.model.StubItem"], ARGS) is False
