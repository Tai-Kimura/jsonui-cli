"""Pull test artifacts (screenshots / recordings) into the project artifacts dir.

Sources:
  - iOS:     the newest .xcresult bundle (explicit path, glob, or DerivedData
             discovery), exported via `xcrun xcresulttool export attachments`.
  - Android: on-device artifact directories pulled via adb.

Configured under the `test.artifacts` block of jui.config.json:

    "artifacts": {
      "dir": "tests/artifacts",
      "ios": { "xcresult": null },
      "android": { "appId": "com.example.app", "serial": null }
    }

All subprocess calls go through `_run` and all "current time" stamps through
`_now_stamp` so tests can monkeypatch them.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_ARTIFACTS_DIR = "tests/artifacts"
DERIVED_DATA_XCRESULT_GLOB = "~/Library/Developer/Xcode/DerivedData/*/Logs/Test/*.xcresult"

SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg", ".heic"}
RECORDING_EXTS = {".mp4", ".mov", ".webm"}

# Characters unsafe in file names (keep '/', it is handled as a separator).
_SANITIZE_RE = re.compile(r'[<>:"|?*\\\x00-\x1f]')

# xcresulttool appends `_<n>_<UUID>` to attachment names on export
# ("Failure_login_0_CE5BA648-… .png") — strip it so filenames stay readable.
_EXPORT_SUFFIX_RE = re.compile(
    r"_\d+_[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)


def _strip_export_suffix(name: str) -> str:
    p = Path(str(name))
    stem = _EXPORT_SUFFIX_RE.sub("", p.stem)
    return (stem or p.stem) + p.suffix


class ArtifactsConfigError(Exception):
    """Raised when the test.artifacts config block is missing required keys."""


@dataclass
class PullResult:
    platform: str
    files: list = field(default_factory=list)
    skipped: list = field(default_factory=list)  # human-readable skip reasons
    stamp_dir: str | None = None


# -- small seams for tests -------------------------------------------------

def _run(cmd, **kw) -> subprocess.CompletedProcess:
    """Single subprocess seam; tests monkeypatch this."""
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(cmd, **kw)


def _now_stamp() -> str:
    """Current-time stamp; tests monkeypatch this."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# -- config resolution ------------------------------------------------------

def _artifacts_cfg(test_cfg: dict) -> dict:
    return test_cfg.get("artifacts", {}) or {}


def resolve_out_root(test_cfg: dict, project_root, override=None) -> Path:
    """Artifacts output root: --out override > test.artifacts.dir > default."""
    raw = override or _artifacts_cfg(test_cfg).get("dir", DEFAULT_ARTIFACTS_DIR)
    p = Path(os.path.expanduser(str(raw)))
    if not p.is_absolute():
        p = Path(project_root) / p
    return p.resolve()


# -- shared helpers ---------------------------------------------------------

def _sanitize(name: str) -> str:
    cleaned = _SANITIZE_RE.sub("_", str(name)).strip().strip(".")
    return cleaned or "unnamed"


def _test_id_to_relpath(test_id: str) -> Path:
    """Map a test identifier ('Suite/testCase()') to nested directories."""
    segments = [_sanitize(s) for s in str(test_id).split("/") if s.strip()]
    return Path(*segments) if segments else Path("unknown_test")


def _classify(suffix: str) -> str:
    s = suffix.lower()
    if s in SCREENSHOT_EXTS:
        return "screenshots"
    if s in RECORDING_EXTS:
        return "recordings"
    return "other"


def _dedupe(dest: Path, used: set) -> Path:
    """Avoid clobbering a file placed earlier in the SAME pull.

    Files left over from a previous pull of the same stamp dir are
    intentionally overwritten (re-pulls of the same run stay stable).
    """
    candidate = dest
    n = 1
    while str(candidate) in used:
        candidate = dest.with_name(f"{dest.stem}_{n}{dest.suffix}")
        n += 1
    used.add(str(candidate))
    return candidate


def _first(entry: dict, keys, default=None):
    for k in keys:
        v = entry.get(k)
        if v:
            return v
    return default


def collect_files(directory) -> list:
    """Absolute paths of every file under `directory` (sorted)."""
    root = Path(directory)
    if not root.is_dir():
        return []
    return sorted(str(p.resolve()) for p in root.rglob("*") if p.is_file())


def update_latest_symlink(out_root, platform: str, stamp_dir):
    """Create/replace <out_root>/<platform>/latest -> <stamp dir name>."""
    link = Path(out_root) / platform / "latest"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        return  # a real file/dir named 'latest' — leave it alone
    try:
        link.symlink_to(Path(stamp_dir).name)
    except OSError:
        pass  # symlinks unavailable (exotic filesystems) — non-fatal


# -- iOS ---------------------------------------------------------------------

def find_xcresult(ios_cfg: dict, override=None):
    """Locate the xcresult bundle: override > cfg path/glob > DerivedData.

    Returns a Path or None. Glob candidates resolve to the newest mtime match.
    """
    candidates = []
    if override:
        candidates = [Path(override)] if Path(override).exists() else \
            [Path(m) for m in glob.glob(os.path.expanduser(str(override)))]
    elif ios_cfg.get("xcresult"):
        raw = os.path.expanduser(str(ios_cfg["xcresult"]))
        candidates = [Path(raw)] if Path(raw).exists() else \
            [Path(m) for m in glob.glob(raw)]
    else:
        pattern = os.path.expanduser(DERIVED_DATA_XCRESULT_GLOB)
        candidates = [Path(m) for m in glob.glob(pattern)]
    candidates = [c for c in candidates if c.exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load_manifest(export_dir: Path):
    """Parse manifest.json from an xcresulttool export. None -> flat fallback."""
    manifest_path = export_dir / "manifest.json"
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Defensive: some xcresulttool versions wrap the array.
        for key in ("tests", "testAttachments", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return None


def pull_ios(test_cfg: dict, project_root, out_root, xcresult_override=None) -> PullResult:
    """Export attachments from the newest xcresult into <out_root>/ios/<stamp>/."""
    result = PullResult(platform="ios")
    ios_cfg = _artifacts_cfg(test_cfg).get("ios", {}) or {}

    xcresult = find_xcresult(ios_cfg, xcresult_override)
    if xcresult is None:
        result.skipped.append("no .xcresult bundle found (set test.artifacts.ios.xcresult or --xcresult)")
        return result

    export_dir = Path(tempfile.mkdtemp(prefix="jsonui-xcresult-"))
    try:
        try:
            proc = _run(["xcrun", "xcresulttool", "export", "attachments",
                         "--path", str(xcresult), "--output-path", str(export_dir)])
        except FileNotFoundError:
            result.skipped.append("xcrun not found (Xcode command line tools required)")
            return result
        if proc.returncode != 0:
            stderr = (getattr(proc, "stderr", "") or "").strip()
            result.skipped.append(
                f"xcresulttool export failed (exit {proc.returncode})"
                + (f": {stderr}" if stderr else ""))
            return result

        # Stamp from the xcresult's mtime so re-pulls of the same run are stable.
        stamp = datetime.fromtimestamp(xcresult.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
        stamp_dir = Path(out_root) / "ios" / stamp
        stamp_dir.mkdir(parents=True, exist_ok=True)

        manifest = _load_manifest(export_dir)
        used: set = set()
        if manifest is None:
            unsorted_dir = stamp_dir / "unsorted"
            unsorted_dir.mkdir(parents=True, exist_ok=True)
            for src in sorted(p for p in export_dir.iterdir() if p.is_file()):
                dest = _dedupe(unsorted_dir / _sanitize(src.name), used)
                shutil.copy2(src, dest)
                result.files.append(str(dest))
        else:
            for entry in manifest:
                if not isinstance(entry, dict):
                    continue
                test_id = _first(entry, ("testIdentifier", "testId"), "unknown_test")
                test_dir = stamp_dir / _test_id_to_relpath(test_id)
                for att in entry.get("attachments") or []:
                    if not isinstance(att, dict):
                        continue
                    exported = _first(att, ("exportedFileName", "fileName"))
                    if not exported:
                        continue
                    src = export_dir / exported
                    if not src.is_file():
                        continue
                    human = _first(att, ("suggestedHumanReadableName", "humanReadableName"))
                    dest_name = _sanitize(_strip_export_suffix(human)) if human else _sanitize(exported)
                    ext = Path(exported).suffix
                    if not Path(dest_name).suffix and ext:
                        dest_name += ext
                    dest_dir = test_dir / _classify(Path(dest_name).suffix)
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest = _dedupe(dest_dir / dest_name, used)
                    shutil.copy2(src, dest)
                    result.files.append(str(dest))

        result.stamp_dir = str(stamp_dir)
        update_latest_symlink(out_root, "ios", stamp_dir)
        return result
    finally:
        shutil.rmtree(export_dir, ignore_errors=True)


# -- Android ------------------------------------------------------------------

def _android_roots(app_id: str) -> list:
    return [
        f"/sdcard/Android/data/{app_id}/files/jsonui-artifacts",
        "/data/local/tmp/jsonui-artifacts",
    ]

_ADB_NO_DEVICE_MARKERS = ("no devices", "device offline", "device unauthorized",
                          "device not found", "more than one device")


def find_adb(android_cfg: dict | None = None):
    """Resolve the adb executable beyond PATH.

    An MCP daemon does not inherit a login shell's PATH, so PATH-only
    resolution structurally kills the Android leg there. Order:
    config `test.artifacts.android.adb` > PATH > $ANDROID_HOME /
    $ANDROID_SDK_ROOT > OS-default SDK locations. Returns None when
    nothing is found.
    """
    explicit = (android_cfg or {}).get("adb")
    if explicit:
        p = Path(os.path.expanduser(str(explicit)))
        return str(p) if p.is_file() else None

    on_path = shutil.which("adb")
    if on_path:
        return on_path

    candidates = []
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "platform-tools" / "adb")
    candidates.append(Path.home() / "Library/Android/sdk/platform-tools/adb")  # macOS default
    candidates.append(Path.home() / "Android/Sdk/platform-tools/adb")          # Linux default
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def pull_android(test_cfg: dict, project_root, out_root,
                 serial_override=None, clean=False) -> PullResult:
    """Pull on-device artifact dirs into <out_root>/android/<stamp>/ (merged)."""
    result = PullResult(platform="android")
    android_cfg = _artifacts_cfg(test_cfg).get("android", {}) or {}

    app_id = android_cfg.get("appId")
    if not app_id:
        raise ArtifactsConfigError(
            "android artifacts pull requires 'test.artifacts.android.appId' in jui.config.json")

    adb_path = find_adb(android_cfg)
    if not adb_path:
        result.skipped.append(
            "adb not found (PATH, $ANDROID_HOME/$ANDROID_SDK_ROOT, default SDK "
            "locations); set test.artifacts.android.adb to an explicit path")
        return result

    serial = serial_override or android_cfg.get("serial")
    adb = [adb_path] + (["-s", str(serial)] if serial else [])

    stamp = _now_stamp()
    stamp_dir = Path(out_root) / "android" / stamp
    pulled_any = False

    for root in _android_roots(app_id):
        try:
            ls = _run(adb + ["shell", "ls", root])
        except FileNotFoundError:
            result.skipped.append("adb not found on PATH")
            return result
        combined = (getattr(ls, "stdout", "") or "") + (getattr(ls, "stderr", "") or "")
        if any(m in combined for m in _ADB_NO_DEVICE_MARKERS):
            first_line = next((l for l in combined.strip().splitlines() if l.strip()), "no device")
            result.skipped.append(f"adb: {first_line.strip()}")
            return result
        if ls.returncode != 0 or "No such file" in combined:
            continue  # this root simply doesn't exist on the device

        stamp_dir.mkdir(parents=True, exist_ok=True)
        pull = _run(adb + ["pull", f"{root}/.", str(stamp_dir)])
        if pull.returncode != 0:
            stderr = (getattr(pull, "stderr", "") or "").strip()
            result.skipped.append(f"adb pull failed for {root}"
                                  + (f": {stderr}" if stderr else ""))
            continue
        pulled_any = True
        if clean:
            _run(adb + ["shell", "rm", "-rf", root])

    if not pulled_any:
        if not result.skipped:
            result.skipped.append("no jsonui-artifacts directory found on device")
        return result

    result.files = collect_files(stamp_dir)
    result.stamp_dir = str(stamp_dir)
    update_latest_symlink(out_root, "android", stamp_dir)
    return result


# -- Web ------------------------------------------------------------------------

def _resolve_rel(project_root, raw) -> Path:
    p = Path(os.path.expanduser(str(raw)))
    return p if p.is_absolute() else Path(project_root) / p


def pull_web(test_cfg: dict, project_root, out_root, clean=False) -> PullResult:
    """Collect Playwright output + driver screenshots into <out_root>/web/<stamp>/.

    Sources (both local — no device, no result bundle):
      - `web.testResults` (default "test-results"): Playwright's per-test dirs
        (`<spec>-<title-slug>-<project>/`) holding video.webm (with
        `use: { video: 'on' }` in playwright.config), trace, error context.
        Each subdir is one test bucket; files are classified by extension.
      - `web.screenshotDir` (default "screenshots"): the web driver's own
        failure_/screenshot_ PNGs (flat, names carry test/case identity).
    """
    result = PullResult(platform="web")
    web_cfg = _artifacts_cfg(test_cfg).get("web", {}) or {}

    test_results = _resolve_rel(project_root, web_cfg.get("testResults", "test-results"))
    shot_dir = _resolve_rel(project_root, web_cfg.get("screenshotDir", "screenshots"))

    stamp_dir = Path(out_root) / "web" / _now_stamp()
    used: set = set()
    pulled_any = False

    if test_results.is_dir():
        for bucket in sorted(p for p in test_results.iterdir() if p.is_dir()):
            for src in sorted(p for p in bucket.rglob("*") if p.is_file()):
                dest_dir = stamp_dir / bucket.name / _classify(src.suffix)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = _dedupe(dest_dir / _sanitize(src.name), used)
                shutil.copy2(src, dest)
                result.files.append(str(dest))
                pulled_any = True
    else:
        result.skipped.append(f"no Playwright output at {test_results}")

    if shot_dir.is_dir():
        for src in sorted(p for p in shot_dir.rglob("*") if p.is_file()):
            dest_dir = stamp_dir / "screenshots"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = _dedupe(dest_dir / _sanitize(src.name), used)
            shutil.copy2(src, dest)
            result.files.append(str(dest))
            pulled_any = True
    else:
        result.skipped.append(f"no driver screenshots at {shot_dir}")

    if not pulled_any:
        return result

    if clean:
        shutil.rmtree(test_results, ignore_errors=True)
        shutil.rmtree(shot_dir, ignore_errors=True)

    result.stamp_dir = str(stamp_dir)
    update_latest_symlink(out_root, "web", stamp_dir)
    return result


# -- status & exit-code policy -------------------------------------------------

def status(test_cfg: dict, project_root) -> dict:
    """Resolved artifacts config plus every file currently under artifactsDir."""
    art = _artifacts_cfg(test_cfg)
    out_root = resolve_out_root(test_cfg, project_root)
    ios_cfg = art.get("ios", {}) or {}
    android_cfg = art.get("android", {}) or {}
    web_cfg = art.get("web", {}) or {}
    xcresult = find_xcresult(ios_cfg)
    web_results = _resolve_rel(project_root, web_cfg.get("testResults", "test-results"))
    web_shots = _resolve_rel(project_root, web_cfg.get("screenshotDir", "screenshots"))
    return {
        "artifactsDir": str(out_root),
        "ios": {"xcresult": str(xcresult) if xcresult else None},
        "android": {
            "appId": android_cfg.get("appId"),
            "serial": android_cfg.get("serial"),
            "adb": find_adb(android_cfg),
        },
        "web": {
            "testResults": str(web_results) if web_results.is_dir() else None,
            "screenshotDir": str(web_shots) if web_shots.is_dir() else None,
        },
        "existing": collect_files(out_root),
    }


def pull_exit_code(requested_platform: str, results: list) -> int:
    """Exit-code policy for `artifacts pull`.

    - --platform all: best-effort — always 0 (per-platform skips are benign
      environmental conditions like "no device attached on a Mac CI box").
    - explicit single platform: 0 only if it actually produced files.
    Config errors are handled by the caller (always exit 1) before this runs.
    """
    if requested_platform == "all":
        return 0
    return 0 if any(r.files for r in results) else 1
