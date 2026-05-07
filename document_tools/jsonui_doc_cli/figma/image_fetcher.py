"""Figma image collection, download, and manifest management.

Walks a Figma JSON tree to find image nodes, fetches them via the
Figma API, downloads to a local directory, and writes a manifest file
(images.json) that maps image references to local paths.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .api_client import (
    FigmaAPIError,
    download_url,
    fetch_file_images,
    fetch_image_renders,
    get_request_interval,
)

# Node types that should be rendered as images
_VECTOR_TYPES = frozenset({
    "VECTOR", "BOOLEAN_OPERATION", "LINE", "STAR", "REGULAR_POLYGON",
})

# Max bounding box size to consider a container as an "icon component"
_ICON_MAX_SIZE = 120

# Min bounding box size for a vector to be rendered (skip tiny decorative elements)
_VECTOR_MIN_SIZE = 16


def _is_icon_container(node: dict) -> bool:
    """Check if a container node is a small icon/UI component.

    An icon container is a FRAME/INSTANCE/COMPONENT/GROUP that is small
    (<=120px) and contains only vector-type leaf nodes (no TEXT).
    """
    bbox = node.get("absoluteBoundingBox", {})
    w = bbox.get("width", 0)
    h = bbox.get("height", 0)
    if w > _ICON_MAX_SIZE or h > _ICON_MAX_SIZE or w <= 0 or h <= 0:
        return False

    def _has_only_vectors(n: dict) -> bool:
        children = n.get("children", [])
        if not children:
            return n.get("type", "") in _VECTOR_TYPES or n.get("type", "") == "ELLIPSE"
        for child in children:
            if child.get("type") == "TEXT":
                return False
            if not _has_only_vectors(child):
                return False
        return True

    return _has_only_vectors(node)


def collect_image_nodes(figma_json: dict) -> Tuple[Set[str], List[str]]:
    """Walk the Figma JSON tree and collect image-bearing nodes.

    Returns:
        Tuple of:
          - image_refs: Set of imageRef strings (for IMAGE fills)
          - render_ids: List of node IDs to render as images (vectors/icons)
    """
    image_refs: Set[str] = set()
    render_ids: List[str] = []
    rendered_ids: Set[str] = set()  # prevent child duplication

    def _walk(node: dict) -> None:
        if not node.get("visible", True):
            return

        node_id = node.get("id", "")
        node_type = node.get("type", "")
        bbox = node.get("absoluteBoundingBox", {})

        # Skip zero-size nodes (but not CANVAS/DOCUMENT which lack bounding boxes)
        if node_type not in ("CANVAS", "DOCUMENT"):
            if not bbox or bbox.get("width", 0) <= 0 or bbox.get("height", 0) <= 0:
                return

        # Skip if an ancestor is already marked for rendering
        if node_id in rendered_ids:
            return

        # Collect IMAGE fill references
        for fill in node.get("fills", []):
            if fill.get("type") == "IMAGE" and fill.get("imageRef"):
                image_refs.add(fill["imageRef"])

        # Vector-type nodes → render as image (skip tiny ones and LINEs)
        if node_type in _VECTOR_TYPES:
            if node_type == "LINE":
                return  # CSS handles lines fine
            w = bbox.get("width", 0)
            h = bbox.get("height", 0)
            if w >= _VECTOR_MIN_SIZE and h >= _VECTOR_MIN_SIZE:
                if node_id and node_id not in rendered_ids:
                    render_ids.append(node_id)
                    rendered_ids.add(node_id)
            return  # no children to walk

        # Small icon/UI containers → render whole container
        if node_type in ("FRAME", "INSTANCE", "COMPONENT", "GROUP") and _is_icon_container(node):
            if node_id and node_id not in rendered_ids:
                render_ids.append(node_id)
                rendered_ids.add(node_id)
                # Mark all descendants to skip
                _mark_descendants(node, rendered_ids)
            return

        # Recurse into children
        for child in node.get("children", []):
            _walk(child)

    def _mark_descendants(node: dict, ids: Set[str]) -> None:
        for child in node.get("children", []):
            child_id = child.get("id", "")
            if child_id:
                ids.add(child_id)
            _mark_descendants(child, ids)

    # Walk based on JSON format
    document = figma_json.get("document")
    if document:
        # Full file format
        for canvas in document.get("children", []):
            _walk(canvas)
    else:
        # Nodes format
        nodes = figma_json.get("nodes", {})
        for node_data in nodes.values():
            doc = node_data.get("document", {})
            if doc:
                _walk(doc)

    return image_refs, render_ids


def _progress(label: str, failed: int = 0, skipped: int = 0) -> None:
    """Print inline progress on stderr."""
    extra = ""
    if skipped:
        extra += f", {skipped} skipped"
    if failed:
        extra += f", {failed} failed"
    sys.stderr.write(f"\r  {label}{extra}    ")
    sys.stderr.flush()


def _progress_done() -> None:
    """Clear the progress line."""
    sys.stderr.write("\r" + " " * 70 + "\r")
    sys.stderr.flush()


def _sanitize_id(node_id: str) -> str:
    """Sanitize a node ID for use as a filename."""
    return node_id.replace(":", "_").replace("/", "_")


def fetch_and_download_images(
    file_key: str,
    token: str,
    figma_json: dict,
    output_dir: Path,
    plan: str | None = None,
    after_api_call: bool = False,
) -> dict:
    """Orchestrate image collection, API fetching, and downloading.

    Args:
        file_key: Figma file key.
        token: Figma API token.
        figma_json: Parsed Figma JSON data.
        output_dir: Directory to save images (e.g. figma/).
        plan: Figma plan name for rate limit throttling.
        after_api_call: True if called right after another Figma API call
            (e.g. fetch_file/fetch_nodes), so an initial delay is needed.

    Returns:
        Manifest dict with 'fills' and 'renders' mappings.
    """
    interval = get_request_interval(plan)
    if plan:
        print(f"  Plan: {plan} (request interval: {interval:.1f}s)")
    print("Collecting image nodes...")
    image_refs, render_ids = collect_image_nodes(figma_json)
    print(f"  Found {len(image_refs)} image fills, {len(render_ids)} render candidates")

    if not image_refs and not render_ids:
        print("  No images to download.")
        return {"fills": {}, "renders": {}}

    fills_map: Dict[str, str] = {}
    renders_map: Dict[str, str] = {}

    # 1. Fetch IMAGE fill URLs
    if image_refs:
        # Wait before first API call (previous fetch_file/fetch_nodes also counts)
        if interval > 0 and after_api_call:
            print(f"\n  Waiting {interval:.0f}s before image API requests...")
            time.sleep(interval)
        print(f"Fetching {len(image_refs)} image fill URLs...")
        try:
            fill_urls = fetch_file_images(file_key, token)
        except FigmaAPIError as e:
            print(f"  Warning: Could not fetch image fills: {e}", file=sys.stderr)
            fill_urls = {}

        # Download fills
        fills_dir = output_dir / "images" / "fills"
        fills_dir.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        failed = 0
        total = len(image_refs)
        for ref in image_refs:
            url = fill_urls.get(ref)
            if not url:
                continue
            ext = "png"
            if ".jpg" in url or ".jpeg" in url:
                ext = "jpg"
            elif ".svg" in url:
                ext = "svg"
            local_name = f"{ref}.{ext}"
            local_path = fills_dir / local_name
            rel_path = f"images/fills/{local_name}"

            if local_path.exists():
                fills_map[ref] = rel_path
                downloaded += 1
            elif download_url(url, local_path):
                fills_map[ref] = rel_path
                downloaded += 1
            else:
                failed += 1

            _progress(f"Fills: {downloaded}/{total}", failed)

        _progress_done()
        print(f"  Fills: {downloaded}/{total} downloaded" +
              (f", {failed} failed" if failed else ""))

    # 2. Fetch rendered node URLs
    if render_ids:
        # Wait before starting renders (fills API call also counts toward rate limit)
        if interval > 0 and image_refs:
            print(f"\n  Waiting {interval:.0f}s before render requests...")
            time.sleep(interval)
        print(f"\nFetching render URLs for {len(render_ids)} nodes...")
        try:
            render_urls = fetch_image_renders(file_key, token, render_ids, request_interval=interval)
        except FigmaAPIError as e:
            print(f"  Warning: Could not fetch renders: {e}", file=sys.stderr)
            render_urls = {}

        # Download renders
        renders_dir = output_dir / "images" / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        skipped = 0
        failed = 0
        total = len(render_ids)
        for node_id in render_ids:
            url = render_urls.get(node_id)
            if not url:
                skipped += 1
                _progress(f"Renders: {downloaded}/{total}", failed, skipped)
                continue
            safe_id = _sanitize_id(node_id)
            local_name = f"{safe_id}.png"
            local_path = renders_dir / local_name
            rel_path = f"images/renders/{local_name}"

            if local_path.exists():
                renders_map[node_id] = rel_path
                downloaded += 1
            elif download_url(url, local_path):
                renders_map[node_id] = rel_path
                downloaded += 1
            else:
                failed += 1

            _progress(f"Renders: {downloaded}/{total}", failed, skipped)

        _progress_done()
        print(f"  Renders: {downloaded}/{total} downloaded" +
              (f", {skipped} skipped" if skipped else "") +
              (f", {failed} failed" if failed else ""))

    # 3. Write manifest
    manifest = {
        "version": 1,
        "file_key": file_key,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fills": fills_map,
        "renders": renders_map,
    }
    manifest_path = output_dir / "images.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\nManifest written to: {manifest_path}")

    return manifest


def load_image_manifest(figma_dir: Path) -> dict:
    """Load image manifest from a figma directory.

    Args:
        figma_dir: Path to the figma/ directory containing images.json.

    Returns:
        Manifest dict with 'fills' and 'renders' keys,
        or empty dicts if manifest not found.
    """
    manifest_path = figma_dir / "images.json"
    if not manifest_path.exists():
        return {"fills": {}, "renders": {}}
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "fills": data.get("fills", {}),
            "renders": data.get("renders", {}),
        }
    except (json.JSONDecodeError, OSError):
        return {"fills": {}, "renders": {}}
