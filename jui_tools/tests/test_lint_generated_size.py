"""Size gate + waiver ratchet in `jui lint-generated`.

The per-function bound is iOS-calibrated (SwiftUI type-metadata depth on a
1MB device stack); Android's real constraint (the dex method limit) is a
hard compile error, so standing waivers there are informational. What IS a
failure signal on every platform is the waiver set GROWING — the ratchet.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from jui_cli.commands.lint_generated_cmd import (
    BASELINE_FILENAME,
    EXIT_HEALTH,
    EXIT_OK,
    EXIT_RATCHET,
    _exit_code,
    _oversized_functions,
    _ratchet_size_baseline,
    cmd_lint_generated,
)


def _write_view(tmp_path: Path, name: str, depth: int, lines: int) -> Path:
    body = []
    body.append("@ViewBuilder private func big() -> some View {")
    for i in range(depth):
        body.append("    " * (i + 1) + "VStack {")
    body.append("    " * (depth + 1) + 'Text("x")')
    filler = lines - len(body) - depth - 1
    for _ in range(max(filler, 0)):
        body.append("    " * (depth + 1) + '.padding(1)')
    for i in range(depth, 0, -1):
        body.append("    " * i + "}")
    body.append("}")
    path = tmp_path / name
    path.write_text("\n".join(body), encoding="utf-8")
    return path


class TestOversizedFunctions:
    def test_deep_function_is_reported_with_body_depth(self, tmp_path):
        path = _write_view(tmp_path, "AGeneratedView.swift", depth=8, lines=20)
        found = list(_oversized_functions(path, 5, 250))
        assert found and found[0][0] == "big"
        assert found[0][1] == 8  # body depth excludes the decl's own brace

    def test_bounded_function_is_silent(self, tmp_path):
        path = _write_view(tmp_path, "AGeneratedView.swift", depth=4, lines=30)
        assert list(_oversized_functions(path, 5, 250)) == []

    def test_braces_in_strings_do_not_count(self, tmp_path):
        path = tmp_path / "SGeneratedView.swift"
        path.write_text(
            '@ViewBuilder private func s() -> some View {\n'
            '    Text("{ { { deep-looking } } }")\n'
            '}\n',
            encoding="utf-8",
        )
        assert list(_oversized_functions(path, 5, 250)) == []

    def test_kotlin_receiver_extension_names_resolve(self, tmp_path):
        path = tmp_path / "KGeneratedView.kt"
        inner = "\n".join("    " * (i + 1) + "Column {" for i in range(7))
        close = "\n".join("    " * i + "}" for i in range(7, 0, -1))
        path.write_text(
            "@Composable\n"
            "private fun androidx.compose.foundation.layout.RowScope.Section3(\n"
            "    data: D,\n    viewModel: V\n) {\n"
            f"{inner}\n        Text(\"x\")\n{close}\n}}\n",
            encoding="utf-8",
        )
        found = list(_oversized_functions(path, 5, 250))
        assert found and found[0][0] == "Section3"


class TestRatchet:
    def _oversized(self, tmp_path):
        return [(tmp_path / "A.kt", "Section1", 7, 100),
                (tmp_path / "B.kt", "Section2", 2, 400)]

    def test_no_baseline_means_informational_only(self, tmp_path):
        assert _ratchet_size_baseline(tmp_path, self._oversized(tmp_path), update=False) == []

    def test_update_writes_and_subsequent_run_is_clean(self, tmp_path):
        oversized = self._oversized(tmp_path)
        assert _ratchet_size_baseline(tmp_path, oversized, update=True) == []
        assert (tmp_path / BASELINE_FILENAME).is_file()
        assert _ratchet_size_baseline(tmp_path, oversized, update=False) == []

    def test_new_entry_is_flagged(self, tmp_path):
        oversized = self._oversized(tmp_path)
        _ratchet_size_baseline(tmp_path, oversized, update=True)
        grown = oversized + [(tmp_path / "C.kt", "Section9", 8, 300)]
        new = _ratchet_size_baseline(tmp_path, grown, update=False)
        assert new == ["C.kt Section9"]

    def test_shrinking_is_free(self, tmp_path):
        oversized = self._oversized(tmp_path)
        _ratchet_size_baseline(tmp_path, oversized, update=True)
        assert _ratchet_size_baseline(tmp_path, oversized[:1], update=False) == []

    def test_wobbling_numbers_do_not_trip_the_ratchet(self, tmp_path):
        oversized = self._oversized(tmp_path)
        _ratchet_size_baseline(tmp_path, oversized, update=True)
        wobbled = [(p, n, d + 1, l + 30) for p, n, d, l in oversized]
        assert _ratchet_size_baseline(tmp_path, wobbled, update=False) == []


class TestExitCodes:
    """A permanently-red gate is ignored like a permanent warning, so the two
    signals get distinct codes and either can gate alone
    (jui-lint-generated-exit-code-cannot-gate-the-size-ratchet).
    """

    def test_clean_is_zero(self):
        assert _exit_code("any", {"size-ratchet": False, "health": False}) == EXIT_OK

    def test_ratchet_and_health_have_distinct_codes(self):
        assert _exit_code(
            "any", {"size-ratchet": True, "health": False}) == EXIT_RATCHET
        assert _exit_code(
            "any", {"size-ratchet": False, "health": True}) == EXIT_HEALTH

    def test_health_alone_does_not_mask_the_ratchet(self):
        assert _exit_code(
            "size-ratchet", {"size-ratchet": False, "health": True}) == EXIT_OK
        assert _exit_code(
            "size-ratchet", {"size-ratchet": True, "health": True}) == EXIT_RATCHET

    def test_ratchet_alone_does_not_mask_health(self):
        assert _exit_code(
            "health", {"size-ratchet": True, "health": False}) == EXIT_OK
        assert _exit_code(
            "health", {"size-ratchet": True, "health": True}) == EXIT_HEALTH

    def test_non_gating_finding_is_announced(self, capsys):
        _exit_code("size-ratchet", {"size-ratchet": False, "health": True})
        assert "Not gating on" in capsys.readouterr().out


class TestCommandExitCodes:
    """End to end: a real project tree, straight through the command."""

    def _project(self, tmp_path: Path) -> Path:
        (tmp_path / "jui.config.json").write_text(json.dumps({
            "platforms": {"web": {"root": "web"}},
        }), encoding="utf-8")
        gen = tmp_path / "web" / "src" / "generated" / "hooks"
        gen.mkdir(parents=True)
        (gen / "useThing.ts").write_text(
            "// @generated AUTO-GENERATED FILE — DO NOT EDIT\n"
            "export const thing = 1;\n"
            "// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══\n",
            encoding="utf-8",
        )
        return tmp_path

    def _run(self, root: Path, **overrides) -> int:
        args = argparse.Namespace(
            fix=False, verbose=False, max_depth=5, max_lines=250,
            update_size_baseline=False, fail_on="any",
        )
        for key, value in overrides.items():
            setattr(args, key, value)
        cwd = os.getcwd()
        os.chdir(root)
        try:
            return cmd_lint_generated(args)
        finally:
            os.chdir(cwd)

    def test_healthy_project_exits_zero(self, tmp_path):
        assert self._run(self._project(tmp_path)) == EXIT_OK

    def test_missing_sentinel_exits_health(self, tmp_path):
        root = self._project(tmp_path)
        hook = root / "web" / "src" / "generated" / "hooks" / "useThing.ts"
        hook.write_text("export const thing = 1;\n", encoding="utf-8")
        assert self._run(root) == EXIT_HEALTH

    def test_missing_sentinel_does_not_gate_a_ratchet_run(self, tmp_path):
        """The reported failure: one stale sentinel made every run exit
        non-zero, so the ratchet's own verdict was invisible."""
        root = self._project(tmp_path)
        hook = root / "web" / "src" / "generated" / "hooks" / "useThing.ts"
        hook.write_text("export const thing = 1;\n", encoding="utf-8")
        assert self._run(root, fail_on="size-ratchet") == EXIT_OK
