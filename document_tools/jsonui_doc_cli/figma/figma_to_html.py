#!/usr/bin/env python3
"""
Figma JSON to HTML Converter
- Reads Figma API JSON and generates individual HTML pages per screen (FRAME)
- Also generates an index page
"""

import json
import os
import shutil
import sys
import re
from pathlib import Path


def rgba_to_css(color, opacity=1.0):
    """Convert a Figma color object to a CSS color string."""
    r = int(color.get("r", 0) * 255)
    g = int(color.get("g", 0) * 255)
    b = int(color.get("b", 0) * 255)
    a = color.get("a", 1.0) * opacity
    if a < 1.0:
        return f"rgba({r},{g},{b},{a:.2f})"
    return f"rgb({r},{g},{b})"


def get_fill_color(node):
    """Get the background fill color of a node."""
    fills = node.get("fills", [])
    for fill in reversed(fills):
        if fill.get("visible", True) and fill.get("type") == "SOLID":
            opacity = fill.get("opacity", 1.0) * node.get("opacity", 1.0)
            return rgba_to_css(fill["color"], opacity)
    return None


def get_stroke_css(node):
    """Get the stroke as a CSS border string."""
    strokes = node.get("strokes", [])
    for stroke in strokes:
        if stroke.get("visible", True) and stroke.get("type") == "SOLID":
            color = rgba_to_css(stroke["color"])
            weight = node.get("strokeWeight", 1)
            return f"{weight}px solid {color}"
    return None


def get_border_radius(node):
    """Get the border radius."""
    r = node.get("cornerRadius")
    if r:
        return f"{r}px"
    radii = node.get("rectangleCornerRadii")
    if radii and any(v > 0 for v in radii):
        return " ".join(f"{v}px" for v in radii)
    return None


def get_shadow_css(node):
    """Get drop shadow as a CSS box-shadow string."""
    effects = node.get("effects", [])
    shadows = []
    for effect in effects:
        if effect.get("visible", True) and effect.get("type") == "DROP_SHADOW":
            color = rgba_to_css(effect["color"])
            offset = effect.get("offset", {})
            x = offset.get("x", 0)
            y = offset.get("y", 0)
            radius = effect.get("radius", 0)
            spread = effect.get("spread", 0)
            shadows.append(f"{x}px {y}px {radius}px {spread}px {color}")
    return ", ".join(shadows) if shadows else None


def get_text_styles(node):
    """Get text node CSS styles."""
    style = node.get("style", {})
    styles = {}
    if "fontSize" in style:
        styles["font-size"] = f"{style['fontSize']}px"
    if "fontWeight" in style:
        styles["font-weight"] = str(int(style["fontWeight"]))
    if "fontFamily" in style:
        styles["font-family"] = f"'{style['fontFamily']}', sans-serif"
    if "letterSpacing" in style:
        ls = style["letterSpacing"]
        if ls != 0:
            styles["letter-spacing"] = f"{ls}px"
    if "lineHeightPx" in style:
        styles["line-height"] = f"{style['lineHeightPx']}px"
    if "textAlignHorizontal" in style:
        align_map = {"LEFT": "left", "CENTER": "center", "RIGHT": "right", "JUSTIFIED": "justify"}
        styles["text-align"] = align_map.get(style["textAlignHorizontal"], "left")
    return styles


def _make_img_tag(css, name, img_src, css_class="image-node"):
    """Helper to generate an <img> tag with CSS styles."""
    css["object-fit"] = "cover"
    style_str = "; ".join(f"{k}: {v}" for k, v in css.items())
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return f'<img class="{css_class}" data-name="{safe_name}" src="{img_src}" style="{style_str}" alt="{safe_name}">\n'


def node_to_html(node, parent_x=0, parent_y=0, depth=0, image_manifest=None, images_prefix="../images"):
    """Recursively convert a Figma node to HTML.

    Args:
        image_manifest: Image manifest dict (fills/renders -> local path)
        images_prefix: Relative path from HTML to the images directory
    """
    if not node.get("visible", True):
        return ""

    node_type = node.get("type", "")
    name = node.get("name", "")
    node_id = node.get("id", "")
    bbox = node.get("absoluteBoundingBox")
    if not bbox:
        return ""

    x = bbox.get("x", 0) - parent_x
    y = bbox.get("y", 0) - parent_y
    w = bbox.get("width", 0)
    h = bbox.get("height", 0)

    # Build CSS styles
    css = {
        "position": "absolute",
        "left": f"{x:.1f}px",
        "top": f"{y:.1f}px",
        "width": f"{w:.1f}px",
        "height": f"{h:.1f}px",
    }

    fill = get_fill_color(node)
    if fill:
        css["background-color"] = fill

    stroke = get_stroke_css(node)
    if stroke:
        css["border"] = stroke

    radius = get_border_radius(node)
    if radius:
        css["border-radius"] = radius

    shadow = get_shadow_css(node)
    if shadow:
        css["box-shadow"] = shadow

    opacity = node.get("opacity")
    if opacity is not None and opacity < 1.0:
        css["opacity"] = f"{opacity:.2f}"

    if node.get("clipsContent"):
        css["overflow"] = "hidden"

    # IMAGE fill -> <img> tag
    if image_manifest:
        for fill_item in node.get("fills", []):
            if fill_item.get("type") == "IMAGE" and fill_item.get("imageRef"):
                local_path = image_manifest.get("fills", {}).get(fill_item["imageRef"])
                if local_path:
                    img_src = f"{images_prefix}/{local_path.split('images/', 1)[-1]}" if "images/" in local_path else f"{images_prefix}/{local_path}"
                    return _make_img_tag(css, name, img_src, "image-node")

    # Text node
    if node_type == "TEXT":
        text_styles = get_text_styles(node)
        css.update(text_styles)
        text_fill = get_fill_color(node)
        if text_fill:
            css["color"] = text_fill
            if "background-color" in css and css["background-color"] == text_fill:
                del css["background-color"]
        characters = node.get("characters", "")
        style_str = "; ".join(f"{k}: {v}" for k, v in css.items())
        escaped = characters.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        escaped = escaped.replace("\n", "<br>")
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        return f'<div class="text-node" data-name="{safe_name}" style="{style_str}">{escaped}</div>\n'

    # ELLIPSE -> border-radius: 50%
    if node_type == "ELLIPSE":
        css["border-radius"] = "50%"

    # VECTOR, LINE -> use <img> if rendered, otherwise fallback to div
    if node_type in ("VECTOR", "LINE", "BOOLEAN_OPERATION", "STAR", "REGULAR_POLYGON"):
        if image_manifest and node_id:
            local_path = image_manifest.get("renders", {}).get(node_id)
            if local_path:
                img_src = f"{images_prefix}/{local_path.split('images/', 1)[-1]}" if "images/" in local_path else f"{images_prefix}/{local_path}"
                return _make_img_tag(css, name, img_src, "vector-image")
        style_str = "; ".join(f"{k}: {v}" for k, v in css.items())
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        return f'<div class="vector-node" data-name="{safe_name}" style="{style_str}"></div>\n'

    # Container -> use <img> if rendered as icon container
    if image_manifest and node_id:
        local_path = image_manifest.get("renders", {}).get(node_id)
        if local_path:
            img_src = f"{images_prefix}/{local_path.split('images/', 1)[-1]}" if "images/" in local_path else f"{images_prefix}/{local_path}"
            return _make_img_tag(css, name, img_src, "icon-image")

    # Container nodes (FRAME, GROUP, INSTANCE, COMPONENT, etc.)
    children_html = ""
    children = node.get("children", [])
    current_x = bbox.get("x", 0)
    current_y = bbox.get("y", 0)
    for child in children:
        children_html += node_to_html(child, current_x, current_y, depth + 1,
                                       image_manifest=image_manifest, images_prefix=images_prefix)

    style_str = "; ".join(f"{k}: {v}" for k, v in css.items())
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return f'<div class="frame-node" data-name="{safe_name}" style="{style_str}">{children_html}</div>\n'


def generate_screen_html(screen_node, screen_name, image_manifest=None, images_prefix="images"):
    """Generate standalone HTML for a single screen."""
    bbox = screen_node.get("absoluteBoundingBox", {})
    w = bbox.get("width", 375)
    h = bbox.get("height", 812)
    bg = get_fill_color(screen_node) or "#ffffff"

    children_html = ""
    px = bbox.get("x", 0)
    py = bbox.get("y", 0)
    for child in screen_node.get("children", []):
        children_html += node_to_html(child, px, py, image_manifest=image_manifest, images_prefix=images_prefix)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{screen_name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    display: flex;
    justify-content: center;
    background: #f0f0f0;
    padding: 20px;
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
  }}
  .screen-container {{
    position: relative;
    width: {w:.0f}px;
    height: {h:.0f}px;
    background: {bg};
    overflow: hidden;
    box-shadow: 0 2px 20px rgba(0,0,0,0.15);
    border-radius: 8px;
  }}
  .frame-node, .text-node, .vector-node, .image-node, .vector-image, .icon-image {{
    box-sizing: border-box;
  }}
  .image-node, .vector-image, .icon-image {{
    object-fit: cover;
  }}
</style>
</head>
<body>
<div class="screen-container">
{children_html}
</div>
</body>
</html>
"""


def sanitize_filename(name):
    """Replace characters not allowed in filenames."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    name = name.strip('_.')
    return name[:100]


def generate_index_html(screens_by_canvas, output_dir):
    """Generate the index HTML page."""
    links = ""
    for canvas_name, screens in screens_by_canvas.items():
        links += f'<h2>{canvas_name}</h2>\n<div class="grid">\n'
        for screen_name, filename in screens:
            links += f'  <a class="card" href="{filename}">{screen_name}</a>\n'
        links += '</div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Figma Screens</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
    background: #f5f5f7;
    padding: 40px;
    color: #333;
  }}
  h1 {{ margin-bottom: 30px; font-size: 28px; }}
  h2 {{ margin: 30px 0 15px; font-size: 20px; color: #666; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 12px;
  }}
  .card {{
    display: block;
    padding: 16px;
    background: #fff;
    border-radius: 8px;
    text-decoration: none;
    color: #333;
    font-size: 14px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    transition: box-shadow 0.2s;
    word-break: break-all;
  }}
  .card:hover {{
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  }}
</style>
</head>
<body>
<h1>Figma Screens</h1>
{links}
</body>
</html>
"""


def generate_figma_screen_page(screen_node, screen_name, canvas_name,
                               all_tests_nav=None, current_path=None, figma_screens=None,
                               image_manifest=None):
    """Generate a Figma screen page with sidebar navigation."""
    from ..test_doc.html.styles import get_common_styles, get_sidebar_base_styles, get_responsive_styles, get_toggle_script
    from ..test_doc.html.sidebar import escape_html

    bbox = screen_node.get("absoluteBoundingBox", {})
    w = bbox.get("width", 375)
    h = bbox.get("height", 812)
    bg = get_fill_color(screen_node) or "#ffffff"

    # Images are at html/figma/images/, pages are at html/figma/{canvas}/
    images_prefix = "../images"

    children_html = ""
    px = bbox.get("x", 0)
    py = bbox.get("y", 0)
    for child in screen_node.get("children", []):
        children_html += node_to_html(child, px, py, image_manifest=image_manifest, images_prefix=images_prefix)

    # Build HTML
    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        f"  <title>{escape_html(screen_name)} - Figma</title>",
        "  <meta charset='utf-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1'>",
        "  <style>",
    ]
    parts.extend(get_common_styles())
    parts.extend(get_sidebar_base_styles())
    parts.extend([
        "    .main-content { margin-left: 280px; padding: 30px; flex: 1; background: #f0f0f0; min-height: 100vh; }",
        "    .main-content h1 { margin-bottom: 8px; }",
        "    .canvas-label { color: #666; font-size: 0.9em; margin-bottom: 20px; }",
        "    .screen-container { position: relative; background: " + bg + "; overflow: hidden; box-shadow: 0 2px 20px rgba(0,0,0,0.15); border-radius: 8px; display: inline-block; }",
        "    .frame-node, .text-node, .vector-node, .image-node, .vector-image, .icon-image { box-sizing: border-box; }",
        "    .image-node, .vector-image, .icon-image { object-fit: cover; }",
        f"    .screen-container {{ width: {w:.0f}px; height: {h:.0f}px; }}",
    ])
    parts.extend(get_responsive_styles())
    parts.append("  </style>")
    parts.extend(get_toggle_script())
    parts.extend([
        "</head>",
        "<body>",
    ])

    # Sidebar (pages are at figma/{canvas}/{screen}.html, so ../../ to reach root)
    parts.append("  <nav class='sidebar'>")
    parts.append("    <a href='../../index.html' class='back-link'>&larr; Back to Index</a>")
    parts.append(f"    <h2>{escape_html(screen_name)}</h2>")

    # Figma screens in sidebar (grouped by canvas)
    if figma_screens:
        from ..test_doc.html.sidebar import _render_figma_sidebar_section
        parts.extend(_render_figma_sidebar_section(
            figma_screens, href_prefix='../../', current_path=current_path, collapsed=False))

    # Other navigation from all_tests_nav
    if all_tests_nav:
        for key, label, css_class in [
            ('specs', 'Screen Specs', 'spec'),
            ('components', 'Components', 'component'),
            ('flows', 'Flow Tests', 'flow'),
            ('screens', 'Screen Tests', ''),
        ]:
            items = all_tests_nav.get(key, [])
            if items:
                parts.append("    <div class='sidebar-section'>")
                collapsed = "collapsed"
                parts.append(f"      <div class='sidebar-title {css_class} {collapsed}' id='{key}-title' onclick=\"toggleSection('{key}')\"><span class='arrow'>▼</span> {label} <span class='count'>{len(items)}</span></div>")
                parts.append(f"      <div class='sidebar-list {collapsed}' id='{key}-list'>")
                parts.append("        <ul>")
                for item in items:
                    parts.append(f"          <li><a href='../../{item['path']}' class='nav-link' title='{escape_html(item['name'])}'>{escape_html(item['name'])}</a></li>")
                parts.append("        </ul>")
                parts.append("      </div>")
                parts.append("    </div>")

    parts.append("  </nav>")

    # Main content
    parts.append("  <main class='main-content'>")
    parts.append(f"    <h1>{escape_html(screen_name)}</h1>")
    parts.append(f"    <p class='canvas-label'>Canvas: {escape_html(canvas_name)}</p>")
    parts.append(f"    <div class='screen-container'>")
    parts.append(children_html)
    parts.append("    </div>")
    parts.append("  </main>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


def _infer_sections_from_names(screens):
    """When no SECTION nodes exist, infer section grouping from screen names.

    Phase 1: Match numbered patterns (e.g. "1.2.3::Category-..." or "1.2.3-Category-...")
    Phase 2: Group remaining screens by common name prefix (min 2 chars, min 2 screens)

    Args:
        screens: List of screen dicts (modified in place)
    """
    from collections import Counter

    # Phase 1: Number-prefixed patterns
    for screen in screens:
        name = screen.get('name', '')
        # Pattern 1: "5.3.2::Settings-EditProfile-Saving"
        m = re.match(r'[\d.]+::(\w+)', name)
        if m:
            screen['sections'] = [m.group(1)]
            continue
        # Pattern 2: "1.1.1-Home-ItemList-Collapse"
        m = re.match(r'\d+\.\d+[\d.]*-(\w+)', name)
        if m:
            screen['sections'] = [m.group(1)]
            continue

    # Phase 2: Group ungrouped screens by common name prefix
    ungrouped = [s for s in screens if not s.get('sections')]
    if len(ungrouped) < 2:
        return

    # Sort by name so similar names are adjacent
    ungrouped.sort(key=lambda s: s.get('name', ''))

    # Find longest common prefix with adjacent names for each screen
    prefixes = []
    for i, screen in enumerate(ungrouped):
        name = screen.get('name', '')
        best = None
        for j in (i - 1, i + 1):
            if 0 <= j < len(ungrouped):
                other = ungrouped[j].get('name', '')
                common = 0
                for c1, c2 in zip(name, other):
                    if c1 == c2:
                        common += 1
                    else:
                        break
                if common >= 2:
                    p = name[:common].rstrip(' _-.()?')
                    if len(p) >= 2 and (best is None or len(p) > len(best)):
                        best = p
        prefixes.append(best)

    # Only assign sections where 2+ screens share the same prefix
    counts = Counter(p for p in prefixes if p)
    for screen, prefix in zip(ungrouped, prefixes):
        if prefix and counts[prefix] >= 2:
            screen['sections'] = [prefix]


def _collect_screens_recursive(node, section_path=None):
    """Recursively collect FRAME/COMPONENT screens from a Figma node tree.

    Traverses SECTION and GROUP nodes to find screens, tracking the section
    hierarchy path for each screen.

    Args:
        node: Figma node dict (canvas or section/group)
        section_path: Current section path (list of section names)

    Returns:
        list[dict]: Each dict has 'node' and 'sections' keys
    """
    if section_path is None:
        section_path = []

    results = []
    for child in node.get("children", []):
        child_type = child.get("type", "")
        if not child.get("visible", True):
            continue

        if child_type == "SECTION":
            section_name = child.get("name", "Unknown")
            sub_screens = _collect_screens_recursive(child, section_path + [section_name])
            results.extend(sub_screens)
        elif child_type in ("FRAME", "COMPONENT"):
            bbox = child.get("absoluteBoundingBox", {})
            if bbox.get("width", 0) < 100 or bbox.get("height", 0) < 100:
                continue
            results.append({'node': child, 'sections': list(section_path)})
        elif child_type == "GROUP":
            # GROUP doesn't add to section path, just recurse
            sub_screens = _collect_screens_recursive(child, section_path)
            results.extend(sub_screens)

    return results


def convert_figma_json(figma_json_path, output_dir, all_tests_nav=None):
    """Generate sidebar-enabled HTML pages from a Figma JSON file.

    Args:
        figma_json_path: Path to the Figma JSON file.
        output_dir: HTML output directory.
        all_tests_nav: Navigation data for other document sections.

    Returns:
        list[dict]: Generated screen info [{'name', 'path', 'canvas', 'sections'}]
    """
    from .image_fetcher import load_image_manifest

    with open(figma_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    figma_out = Path(output_dir) / "figma"
    figma_out.mkdir(parents=True, exist_ok=True)

    # Load image manifest and copy images to output
    figma_dir = Path(figma_json_path).parent
    image_manifest = load_image_manifest(figma_dir)
    has_images = bool(image_manifest.get("fills") or image_manifest.get("renders"))

    if has_images:
        images_src = figma_dir / "images"
        images_dest = figma_out / "images"
        if images_src.exists() and not images_dest.exists():
            shutil.copytree(images_src, images_dest)
        elif images_src.exists():
            # Update: copy new files only
            for subdir in ("fills", "renders"):
                src_sub = images_src / subdir
                dest_sub = images_dest / subdir
                if src_sub.exists():
                    dest_sub.mkdir(parents=True, exist_ok=True)
                    for f in src_sub.iterdir():
                        dest_f = dest_sub / f.name
                        if not dest_f.exists():
                            shutil.copy2(f, dest_f)

    # Normalize: support both full file format and nodes format
    # Full file: { "document": { "children": [canvas1, canvas2, ...] } }
    # Nodes:     { "nodes": { "0:1": { "document": { "type": "CANVAS", "children": [...] } } } }
    canvases = []
    if "document" in data and "children" in data.get("document", {}):
        canvases = data["document"]["children"]
    elif "nodes" in data and isinstance(data["nodes"], dict):
        for node_id, node_data in data["nodes"].items():
            doc = node_data.get("document", {})
            if doc.get("type") == "CANVAS":
                canvases.append(doc)
            elif doc.get("children"):
                # Top-level node with children (e.g. page selected directly)
                canvases.append(doc)

    # First pass: collect screen info recursively (respecting SECTION hierarchy)
    figma_screens = []
    used_filenames_per_canvas = {}  # canvas_dir -> set of filenames

    for canvas in canvases:
        canvas_name = canvas.get("name", "Unknown")
        canvas_dir = sanitize_filename(canvas_name)

        if canvas_dir not in used_filenames_per_canvas:
            used_filenames_per_canvas[canvas_dir] = set()
        used_filenames = used_filenames_per_canvas[canvas_dir]

        collected = _collect_screens_recursive(canvas)
        print(f"    Canvas '{canvas_name}': {len(collected)} screens found")
        for item in collected:
            child = item['node']
            sections = item['sections']

            screen_name = child.get("name", f"screen_{len(figma_screens)}")
            base_filename = sanitize_filename(screen_name)
            filename = base_filename + ".html"
            counter = 1
            while filename in used_filenames:
                filename = f"{base_filename}_{counter}.html"
                counter += 1
            used_filenames.add(filename)

            figma_screens.append({
                'name': screen_name,
                'path': f"figma/{canvas_dir}/{filename}",
                'canvas': canvas_name,
                'canvas_dir': canvas_dir,
                'node': child,
                'filename': filename,
                'sections': sections,
            })

    # Fallback: if no screens have sections (no SECTION nodes in Figma),
    # infer grouping from screen name patterns
    has_any_sections = any(s.get('sections') for s in figma_screens)
    if not has_any_sections and figma_screens:
        print("    No SECTION nodes found, inferring groups from screen names...")
        _infer_sections_from_names(figma_screens)

    # Build grouped navigation data for sidebar (include sections)
    figma_nav = [{'name': s['name'], 'path': s['path'], 'canvas': s['canvas'], 'sections': s['sections']} for s in figma_screens]

    # Second pass: generate HTML with navigation
    total = len(figma_screens)
    print(f"    Generating {total} Figma screen pages...")
    result = []
    for i, screen in enumerate(figma_screens, 1):
        canvas_out = figma_out / screen['canvas_dir']
        canvas_out.mkdir(parents=True, exist_ok=True)

        html = generate_figma_screen_page(
            screen['node'], screen['name'], screen['canvas'],
            all_tests_nav=all_tests_nav,
            current_path=screen['path'],
            figma_screens=figma_nav,
            image_manifest=image_manifest if has_images else None
        )
        filepath = canvas_out / screen['filename']
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        sections_str = " > ".join(screen['sections']) if screen.get('sections') else ""
        location = f" [{sections_str}]" if sections_str else ""
        print(f"      [{i}/{total}] {screen['name']}{location}")

        result.append({
            'name': screen['name'],
            'path': screen['path'],
            'canvas': screen['canvas'],
            'sections': screen.get('sections', []),
        })

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 figma_to_html.py <figma.json> [output_dir]")
        print("  figma.json  : JSON file fetched from Figma API")
        print("  output_dir  : Output directory (default: ./figma_html)")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./figma_html"

    print(f"Loading {input_file}...")
    with open(input_file, "r") as f:
        data = json.load(f)

    os.makedirs(output_dir, exist_ok=True)
    screens_by_canvas = {}
    total = 0

    for canvas in data["document"]["children"]:
        canvas_name = canvas.get("name", "Unknown")
        canvas_screens = []
        used_filenames = set()

        for child in canvas.get("children", []):
            # Only treat FRAME and COMPONENT as screens
            if child.get("type") not in ("FRAME", "COMPONENT"):
                continue
            if not child.get("visible", True):
                continue
            # Skip elements too small to be screens (likely components)
            bbox = child.get("absoluteBoundingBox", {})
            if bbox.get("width", 0) < 100 or bbox.get("height", 0) < 100:
                continue

            screen_name = child.get("name", f"screen_{total}")
            base_filename = sanitize_filename(f"{canvas_name}_{screen_name}")

            # Avoid duplicate filenames
            filename = base_filename + ".html"
            counter = 1
            while filename in used_filenames:
                filename = f"{base_filename}_{counter}.html"
                counter += 1
            used_filenames.add(filename)

            filepath = os.path.join(output_dir, filename)
            html = generate_screen_html(child, screen_name)
            with open(filepath, "w") as f:
                f.write(html)

            canvas_screens.append((screen_name, filename))
            total += 1

            if total % 50 == 0:
                print(f"  {total} screens processed...")

        if canvas_screens:
            screens_by_canvas[canvas_name] = canvas_screens

    # Generate index page
    index_html = generate_index_html(screens_by_canvas, output_dir)
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write(index_html)

    print(f"\nDone! {total} screens generated in {output_dir}/")
    print(f"Open {output_dir}/index.html to browse all screens.")


if __name__ == "__main__":
    main()
