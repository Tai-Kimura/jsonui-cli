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
imports nothing of its own.
"""

#: Image, its type aliases (component_metadata.json) and NetworkImage.
IMAGE_TYPES = frozenset({"Image", "CircleImage", "CircleImageView", "ImageView", "Img", "NetworkImage"})

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
    return isinstance(node, dict) and node.get("type") in IMAGE_TYPES


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


def is_tappable(node) -> bool:
    """Whether `node` operates something a screen-reader user can activate —
    a tap (a handler, `enabled` not false, `canTap` not false) or a long press
    (a handler, `enabled` not false) — as the tap rule judges it. It read the
    handler KEY before, so an empty, disabled or shut tap made an image a
    control. A bound gate still operates: it opens at run time."""
    if not isinstance(node, dict) or node.get("enabled") is False:
        return False
    if node.get("canTap") is not False and any(is_handler(node.get(key)) for key in TAP_KEYS):
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


def role(node, nearest_tappable=None) -> str:
    """The role of one image, given the nearest tappable around it (None when none)."""
    value = alt(node)
    if value is not None:
        return "decorative" if (value if isinstance(value, str) else str(value)) == "" else "label"
    if is_tappable(node):
        return "control"
    if nearest_tappable is not None and not names_something(nearest_tappable):
        return "control"
    return "decorative"


def roles(root) -> list:
    """(image node, role) for every image of a layout tree, in document order."""
    out: list = []

    def walk(node, nearest):
        if not isinstance(node, dict):
            return
        if is_image(node):
            out.append((node, role(node, nearest)))
        inner = node if is_tappable(node) else nearest
        for c in children(node):
            walk(c, inner)

    walk(root, None)
    return out
