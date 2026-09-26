"""What a screen reader hears for each image of a layout — the rule of
shared/core/image_accessibility.rb, for the Python side (`jsonui-test
validate`). Five implementations share it: this one, the Ruby module the sjui
and kjui codegen use, and the KotlinJsonUI and SwiftJsonUI Dynamic runtimes.
All of them run shared/core/image_accessibility_vectors.json.

An image is one of three roles:

  label      — alt is a non-empty string: it is read.
  decorative — alt is "", or there is no alt and the image operates nothing.
               iOS hides it from VoiceOver, and the iOS driver then reads it as
               not visible even while it is on screen.
  control    — there is no alt and the image operates a control (a tap
               handler of its own, or it is the only thing naming the nearest
               tappable around it).

Loaded through `jui_cli.core.shared_core.load("image_accessibility")`; it
imports only the standard library, and reads type_synonyms.json and
attribute_definitions.json beside it (drawn_type).
"""

import json
import os

#: The types an image is drawn as. A node is an image when the type it is
#: drawn as (drawn_type below) is one of them: Img, ImageView, AsyncImage,
#: NetworkImageView, CircleImageView and every other spelling the table gives
#: them. Until 1.8.121 this was a list of spellings from component_metadata
#: .json's `aliases`, which named neither AsyncImage nor NetworkImageView.
IMAGE_TYPES = frozenset({"Image", "CircleImage", "NetworkImage"})

_HERE = os.path.dirname(os.path.abspath(__file__))
_TABLES: dict = {}


def _read_beside(name: str) -> dict:
    if name not in _TABLES:
        try:
            with open(os.path.join(_HERE, name), encoding="utf-8") as handle:
                _TABLES[name] = json.load(handle)
        except OSError:
            # A missing file reads as empty, as type_synonyms.rb reads it: the
            # spelling is then its own drawn type.
            _TABLES[name] = {}
    return _TABLES[name]


def drawn_type(type_name):
    """The type a node spelled `type_name` is drawn as — type_synonyms.rb's
    drawn_type: its type-synonym target (`render_as`, else `canonical`, from
    type_synonyms.json beside this file), then the canonical section of a
    declared alias (`_alias_of` in attribute_definitions.json), one hop."""
    if not isinstance(type_name, str):
        return type_name
    entry = _read_beside("type_synonyms.json").get("synonyms", {}).get(type_name)
    drawn = (entry.get("render_as") or entry.get("canonical")) if isinstance(entry, dict) else type_name
    definitions = _read_beside("attribute_definitions.json")
    section = definitions.get(drawn)
    target = section.get("_alias_of") if isinstance(section, dict) else None
    if isinstance(target, str) and isinstance(definitions.get(target), dict) \
            and not isinstance(definitions[target].get("_alias_of"), str):
        return target
    return drawn

#: The canonical spelling first, then the aliases declared on `alt`.
ALT_KEYS = ("alt", "accessibilityLabel", "contentDescription")

#: What a screen-reader user activates, read as shared/core/tap_accessibility.rb
#: reads it (this module imports nothing, so the tap rule's predicate is copied
#: here, and the shared vectors hold the two together): a tap is a handler on
#: onClick / onclick, and a long press one on onLongPress.
TAP_KEYS = ("onClick", "onclick")
LONG_PRESS_KEY = "onLongPress"

#: Text that names a control it sits in (on an image, hint / placeholder name an image).
TEXT_KEYS = ("text", "hint", "placeholder", "label", "prompt")


def is_image(node) -> bool:
    return isinstance(node, dict) and drawn_type(node.get("type")) in IMAGE_TYPES


def alt(node):
    """The image's alt as written, or None when it declares none (JSON null counts as none)."""
    for key in ALT_KEYS:
        if key in node:
            return node[key]
    return None


def names_a_method(value) -> bool:
    """A handler names a method that is not blank: a binding's inside
    (`@{onOpen}`), a bare selector, or each string of an `onclick` array.
    Blank is Unicode white space (`str.isspace`, a full-width space too)."""
    if not isinstance(value, str):
        return False
    inner = value[2:-1] if value.startswith("@{") and value.endswith("}") else value
    return inner.strip() != ""


def is_handler(value) -> bool:
    values = value if isinstance(value, list) else [value]
    return any(names_a_method(v) for v in values)


def stops(node) -> bool:
    """`userInteractionEnabled: false`: the node and everything in it take no
    interaction (the tap rule's `stops?`)."""
    return isinstance(node, dict) and node.get("userInteractionEnabled") is False


def is_tappable(node, stopped=False) -> bool:
    """Whether `node` operates something a screen-reader user can activate —
    a tap (a handler, `enabled` not false, `canTap` not false,
    `userInteractionEnabled` not false on it or on a node around it:
    `stopped`) or a long press (a handler, `enabled` not false) — as the tap
    rule judges it. It read the handler KEY before, so an empty, disabled or
    shut tap made an image a control. A bound gate still operates: it opens
    at run time."""
    if not isinstance(node, dict) or node.get("enabled") is False:
        return False
    if (not stopped and not stops(node) and node.get("canTap") is not False
            and any(is_handler(node.get(key)) for key in TAP_KEYS)):
        return True
    return is_handler(node.get(LONG_PRESS_KEY))


def children(node) -> list:
    out = []
    for key in ("child", "children"):
        value = node.get(key)
        if isinstance(value, list):
            out.extend(c for c in value if isinstance(c, dict))
        elif isinstance(value, dict):
            out.append(value)
    return out


def _non_empty_string(value) -> bool:
    return isinstance(value, str) and value != ""


def names_something(node) -> bool:
    """True when something inside `node` (itself included) names a control:
    text on a non-image, or an image whose alt is a non-empty string."""
    if is_image(node):
        return _non_empty_string(alt(node))
    if any(_non_empty_string(node.get(key)) for key in TEXT_KEYS):
        return True
    items = node.get("items")
    if isinstance(items, list) and any(_non_empty_string(i) for i in items):
        return True
    return any(names_something(c) for c in children(node))


def role(node, nearest_tappable=None, stopped=False) -> str:
    """The role of one image, given the nearest tappable around it (None when
    none), and whether a node around it has `userInteractionEnabled: false`."""
    value = alt(node)
    if value is not None:
        return "decorative" if (value if isinstance(value, str) else str(value)) == "" else "label"
    if is_tappable(node, stopped):
        return "control"
    if nearest_tappable is not None and not names_something(nearest_tappable):
        return "control"
    return "decorative"


def roles(root) -> list:
    """(image node, role) for every image of a layout tree, in document order."""
    out: list = []

    # A node inside one with `userInteractionEnabled: false` is no tappable
    # for the images in it; a tappable around that node still is.
    def walk(node, nearest, stopped):
        if not isinstance(node, dict):
            return
        if is_image(node):
            out.append((node, role(node, nearest, stopped)))
        inner = node if is_tappable(node, stopped) else nearest
        for c in children(node):
            walk(c, inner, stopped or stops(node))

    walk(root, None, False)
    return out
