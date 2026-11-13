"""A ViewModel protocol's imports come out in one order whether or not the screen's Data file exists yet.

Ticket kotlin-protocol-import-order-settles-on-the-second-build-after-a-screen-removal (2.5.33): on a consumer copy,
a layout directory was deleted that also held a living screen's layout. The first `jui build` wrote that screen's
protocol while its `<Screen>Data.kt` was still there — the symbol index knew it, and its import took its place in
name order; then kjui removed the Data file (its layout was gone). The second build found no Data in the index, and
the fallback import went to the END: the protocol changed with nothing in the project changing. A third build was
quiet. The fallback now takes the index's place.

Measured on the generator with and without the Data file, through the generator the build uses. Nothing else in the
family reorders on a file's presence (the table in the ticket): the Repository and UseCase imports, the web's type
imports and iOS's fixed list only gain or lose a line.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.spec_extractor import extract_screen_spec
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.android_generator import AndroidGenerator

PKG = "com.example.app"
SRC = f"app/src/main/kotlin/{PKG.replace('.', '/')}"


def _spec():
    return extract_screen_spec({
        "type": "screen_spec",
        "metadata": {"name": "DateTimePicker", "displayName": "Date"},
        "structure": {"components": []},
        "dataFlow": {"viewModel": {"vars": [{"name": "mode", "type": "DateTimePickerMode"}], "methods": []}},
    }, Path("date_time_picker.spec.json"))


def _imports(root: Path) -> list[str]:
    gen = AndroidGenerator(root, {"package_name": PKG, "source_directory": "src/main"}, TypeMapper(None))
    return gen.viewmodel_type_imports(_spec(), current_package=f"{PKG}.viewmodel.protocol")


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / SRC / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ProtocolImportOrder(unittest.TestCase):
    def test_the_same_imports_with_and_without_the_data_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root, "viewmodels/DateTimePickerMode.kt", f"package {PKG}.viewmodels\n\nenum class DateTimePickerMode {{ DATE }}\n")
            data = _write(root, "data/DateTimePickerData.kt", f"package {PKG}.data\n\ndata class DateTimePickerData(val x: Int = 0)\n")
            with_data = _imports(root)
            data.unlink()
            without = _imports(root)
            self.assertEqual(with_data, [
                f"import {PKG}.data.DateTimePickerData",
                f"import {PKG}.viewmodels.DateTimePickerMode",
            ])
            self.assertEqual(without, with_data)

    def test_the_data_import_is_written_once_and_not_into_its_own_package(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            gen = AndroidGenerator(root, {"package_name": PKG, "source_directory": "src/main"}, TypeMapper(None))
            same = gen.viewmodel_type_imports(_spec(), current_package=f"{PKG}.data")
            self.assertFalse(any(line.endswith(".DateTimePickerData") for line in same))
            other = gen.viewmodel_type_imports(_spec(), current_package=f"{PKG}.viewmodel.protocol")
            self.assertEqual(sum(line.endswith(".DateTimePickerData") for line in other), 1)


if __name__ == "__main__":
    unittest.main()
