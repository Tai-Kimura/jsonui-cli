"""Configuration manager for jui.config.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "project_name": "",
    "spec_directory": "docs/screens/json",
    "layouts_directory": "docs/screens/layouts",
    "styles_directory": "docs/screens/styles",
    "images_directory": "docs/screens/images",
    "component_spec_directory": "docs/components/json",
    "strings_file": "",
    "type_map_file": ".jsonui-type-map.json",
    "document_tools_path": "",
    "platforms": {},
}


class ConfigManager:
    """Manages jui.config.json read/write."""

    CONFIG_FILENAME = "jui.config.json"

    def __init__(self, config_path: Path | None = None):
        if config_path:
            self._path = Path(config_path)
        else:
            self._path = self._find_config()

    def _find_config(self) -> Path:
        """Search upward for jui.config.json."""
        current = Path.cwd()
        while True:
            candidate = current / self.CONFIG_FILENAME
            if candidate.exists():
                return candidate
            parent = current.parent
            if parent == current:
                break
            current = parent
        return Path.cwd() / self.CONFIG_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    @property
    def project_root(self) -> Path:
        return self._path.parent

    def exists(self) -> bool:
        return self._path.exists()

    def load(self) -> dict[str, Any]:
        """Load config. Returns default if file doesn't exist."""
        if not self._path.exists():
            return dict(DEFAULT_CONFIG)
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, config: dict[str, Any]) -> None:
        """Save config to file."""
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")

    # --- Convenience properties ---

    def _platform_config(self, platform: str) -> dict[str, Any] | None:
        config = self.load()
        return config.get("platforms", {}).get(platform)

    @property
    def ios_root(self) -> Path | None:
        p = self._platform_config("ios")
        return self.project_root / p["root"] if p and "root" in p else None

    @property
    def android_root(self) -> Path | None:
        p = self._platform_config("android")
        return self.project_root / p["root"] if p and "root" in p else None

    @property
    def web_root(self) -> Path | None:
        p = self._platform_config("web")
        return self.project_root / p["root"] if p and "root" in p else None

    @property
    def layouts_directory(self) -> Path:
        config = self.load()
        return self.project_root / config.get("layouts_directory", "docs/screens/layouts")

    @property
    def spec_directory(self) -> Path:
        config = self.load()
        return self.project_root / config.get("spec_directory", "docs/screens/json")

    @property
    def images_directory(self) -> Path:
        config = self.load()
        return self.project_root / config.get("images_directory", "docs/screens/images")

    @property
    def styles_directory(self) -> Path:
        config = self.load()
        return self.project_root / config.get("styles_directory", "docs/screens/styles")

    @property
    def component_spec_directory(self) -> Path:
        config = self.load()
        return self.project_root / config.get("component_spec_directory", "docs/components/json")

    @property
    def strings_file(self) -> Path | None:
        config = self.load()
        sf = config.get("strings_file", "")
        return self.project_root / sf if sf else None

    @property
    def type_map_file(self) -> Path | None:
        config = self.load()
        tmf = config.get("type_map_file", "")
        return self.project_root / tmf if tmf else None

    @property
    def document_tools_path(self) -> Path | None:
        config = self.load()
        dtp = config.get("document_tools_path", "")
        if not dtp:
            return None
        p = Path(dtp)
        if p.is_absolute():
            return p
        return self.project_root / p

    def ensure_document_tools_importable(self) -> None:
        """Add document_tools_path to sys.path if configured."""
        import sys
        dtp = self.document_tools_path
        if dtp and dtp.exists() and str(dtp) not in sys.path:
            sys.path.insert(0, str(dtp))
