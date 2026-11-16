"""Load docs/hotload/config.json with sensible defaults."""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "server": {
        "host": "0.0.0.0",
        "port": 8081,
        "wsPath": "/ws",
    },
    "client": {
        "ip": "",
        "fallbackToLocalhost": True,
    },
    "watch": {
        "paths": [
            "docs/screens/layouts",
            "docs/screens/styles",
        ],
        "ignored": [
            "**/node_modules/**",
            "**/.git/**",
            "**/.DS_Store",
        ],
    },
}


@dataclass
class HotloadConfig:
    host: str
    port: int
    ws_path: str
    client_ip: str
    fallback_to_localhost: bool
    watch_paths: list[Path]
    ignored_patterns: list[str]
    project_root: Path
    layouts_dir: Path
    styles_dir: Path
    raw: dict[str, Any] = field(default_factory=dict)

    def resolve_client_ip(self) -> str:
        """Return the IP that runtime clients should connect to.

        Uses ``client.ip`` when set, otherwise auto-detects the primary
        non-loopback IPv4 address, falling back to ``127.0.0.1`` when
        ``fallback_to_localhost`` is true.
        """
        if self.client_ip:
            return self.client_ip
        detected = _detect_local_ip()
        if detected:
            return detected
        if self.fallback_to_localhost:
            return "127.0.0.1"
        return "0.0.0.0"


def load_config(project_root: Path) -> HotloadConfig:
    """Load ``docs/hotload/config.json`` from *project_root*.

    Missing file or missing keys fall back to ``DEFAULT_CONFIG``. The
    layouts / styles paths are resolved from the jui.config.json
    ``layouts_directory`` / ``styles_directory`` settings when present.
    """
    raw = _deep_merge(DEFAULT_CONFIG, _read_hotload_json(project_root))

    layouts_dir, styles_dir = _resolve_spec_dirs(project_root)
    watch_paths = [
        (project_root / p).resolve()
        for p in raw["watch"]["paths"]
    ]
    # Always include the spec dirs in case config.json wasn't tailored.
    for d in (layouts_dir, styles_dir):
        if d not in watch_paths:
            watch_paths.append(d)

    return HotloadConfig(
        host=raw["server"]["host"],
        port=int(raw["server"]["port"]),
        ws_path=raw["server"]["wsPath"],
        client_ip=raw["client"].get("ip", ""),
        fallback_to_localhost=bool(raw["client"].get("fallbackToLocalhost", True)),
        watch_paths=watch_paths,
        ignored_patterns=list(raw["watch"]["ignored"]),
        project_root=project_root,
        layouts_dir=layouts_dir,
        styles_dir=styles_dir,
        raw=raw,
    )


def write_default_config(project_root: Path) -> Path:
    """Create ``docs/hotload/config.json`` with defaults if missing."""
    path = project_root / "docs" / "hotload" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return path


def _read_hotload_json(project_root: Path) -> dict[str, Any]:
    path = project_root / "docs" / "hotload" / "config.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_spec_dirs(project_root: Path) -> tuple[Path, Path]:
    """Pick layouts / styles dirs from jui.config.json if available."""
    jui_config = project_root / "jui.config.json"
    layouts_rel = "docs/screens/layouts"
    styles_rel = "docs/screens/styles"
    if jui_config.exists():
        try:
            with open(jui_config, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            layouts_rel = cfg.get("layouts_directory", layouts_rel)
            styles_rel = cfg.get("styles_directory", styles_rel)
        except (json.JSONDecodeError, OSError):
            pass
    return (project_root / layouts_rel).resolve(), (project_root / styles_rel).resolve()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in base.items():
        if key in override:
            ov = override[key]
            if isinstance(value, dict) and isinstance(ov, dict):
                result[key] = _deep_merge(value, ov)
            else:
                result[key] = ov
        else:
            result[key] = value
    for key, value in override.items():
        if key not in result:
            result[key] = value
    return result


def _detect_local_ip() -> str:
    """Best-effort: return the IP a LAN device would use to reach this host."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()
