"""Web ViewModelBase generation — initializeEventHandlers must only touch
members that exist in the rjui-generated <Name>Data interface.

Regression of `jui-viewmodelbase-initializes-handlers-not-in-layout-data`:
spec-only methods (lifecycle/fetch helpers, cell handlers) written into the
``updateData`` Partial<XxxData> literal are a TS2353 in the consumer.
"""
import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.spec_extractor import MethodDef, ScreenSpec, ViewModelDef
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.web_generator import (
    WebGenerator,
    collect_layout_event_names,
    resolve_layout_path,
)


def _spec(methods: list[str]) -> ScreenSpec:
    return ScreenSpec(
        name="SlotSelect",
        display_name="Slot Select",
        description="",
        layout_file="slot_select",
        view_model=ViewModelDef(
            methods=[MethodDef(name=m, is_async=False) for m in methods],
        ),
    )


def _generator(root: Path) -> WebGenerator:
    return WebGenerator(root, {"root": "web"}, TypeMapper(None))


class CollectLayoutEventNamesTest(unittest.TestCase):
    def _write_layout(self, tmp: str, layout: dict) -> Path:
        path = Path(tmp) / "slot_select.json"
        path.write_text(json.dumps(layout), encoding="utf-8")
        return path

    def test_collects_data_section_names_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_layout(tmp, {
                "type": "View",
                "data": [{"name": "onProceedTap", "class": "(() -> Void)?"}],
                "child": [
                    {"type": "View",
                     "data": [{"name": "isProceedEnabled", "class": "Bool"}]},
                ],
            })
            names = collect_layout_event_names(path)
        self.assertEqual(names, {"onProceedTap", "isProceedEnabled"})

    def test_collects_onclick_selector_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_layout(tmp, {
                "type": "Button", "onclick": "onRegisterTap",
            })
            names = collect_layout_event_names(path)
        self.assertEqual(names, {"onRegisterTap"})

    def test_collects_component_event_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_layout(tmp, {
                "type": "View",
                "child": [
                    {"type": "Segment", "onValueChange": "@{onModeTabChanged}"},
                    {"type": "SelectBox", "onValueChanged": "@{onSizeSelected}"},
                    # Button onClick is NOT in the Data membership set —
                    # only `onclick` selector strings land there.
                    {"type": "Button", "onClick": "@{notInData}"},
                ],
            })
            names = collect_layout_event_names(path)
        self.assertEqual(names, {"onModeTabChanged", "onSizeSelected"})

    def test_derives_textfield_onchange_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_layout(tmp, {
                "type": "View",
                "child": [{"type": "TextField", "text": "@{email}"}],
            })
            names = collect_layout_event_names(path)
        self.assertIn("onEmailChange", names)

    def test_missing_layout_returns_none(self):
        self.assertIsNone(
            collect_layout_event_names(Path("/nonexistent/x.json"))
        )


class InitializeEventHandlersFilterTest(unittest.TestCase):
    def test_spec_only_methods_are_not_initialized(self):
        spec = _spec(["loadStalls", "onSlotSelected", "onProceedTap"])
        with tempfile.TemporaryDirectory() as tmp:
            out = _generator(Path(tmp)).generate_viewmodel_protocol(
                spec, layout_event_names={"onProceedTap"},
            )
        self.assertIn("onProceedTap: () => {},", out)
        self.assertNotIn("loadStalls", out)
        self.assertNotIn("onSlotSelected", out)

    def test_none_layout_names_initializes_all_methods(self):
        spec = _spec(["loadStalls", "onProceedTap"])
        with tempfile.TemporaryDirectory() as tmp:
            out = _generator(Path(tmp)).generate_viewmodel_protocol(
                spec, layout_event_names=None,
            )
        self.assertIn("loadStalls: () => {},", out)
        self.assertIn("onProceedTap: () => {},", out)

    def test_empty_intersection_emits_placeholder_comment(self):
        spec = _spec(["loadStalls"])
        with tempfile.TemporaryDirectory() as tmp:
            out = _generator(Path(tmp)).generate_viewmodel_protocol(
                spec, layout_event_names=set(),
            )
        self.assertIn("// no methods declared", out)
        self.assertNotIn("loadStalls: () => {},", out)


class ResolveLayoutPathTest(unittest.TestCase):
    def test_uses_layout_file_with_subdir(self):
        spec = _spec([])
        spec.layout_file = "mypage/change_email_sheet"
        self.assertEqual(
            resolve_layout_path(Path("/layouts"), spec),
            Path("/layouts/mypage/change_email_sheet.json"),
        )

    def test_falls_back_to_snake_case_name(self):
        spec = _spec([])
        spec.layout_file = ""
        self.assertEqual(
            resolve_layout_path(Path("/layouts"), spec),
            Path("/layouts/slot_select.json"),
        )


if __name__ == "__main__":
    unittest.main()
