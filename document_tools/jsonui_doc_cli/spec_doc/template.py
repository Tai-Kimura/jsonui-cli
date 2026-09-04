"""Screen and component specification template generator."""

import json
import re
from datetime import date
from pathlib import Path
from ..reproducible import build_date


def _pascal_to_kebab(name: str) -> str:
    """Convert PascalCase / camelCase to kebab-case.

    Examples:
        LearnHelloWorld -> learn-hello-world
        Login           -> login
        HTTPServer      -> http-server
    """
    # Handle sequences of uppercase letters followed by a lower-case letter
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name)
    # Then insert a hyphen between a lowercase/digit and an uppercase
    s = re.sub(r"([a-z\d])([A-Z])", r"\1-\2", s)
    return s.lower()


def generate_spec_template(screen_name: str, display_name: str = None) -> dict:
    """Generate a screen specification template.

    Args:
        screen_name: Screen name in PascalCase (e.g., 'Login', 'UserProfile')
        display_name: Localized display name (optional, defaults to screen_name)

    Returns:
        Dictionary containing the specification template
    """
    today = build_date().isoformat()

    return {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {
            "name": screen_name,
            "displayName": display_name or screen_name,
            "description": "",
            "createdAt": today,
            "updatedAt": today
        },
        "structure": {
            "components": [
                {
                    "type": "View",
                    "id": "root_view",
                    "description": "Root container"
                }
            ],
            "layout": {
                "root": "root_view",
                "children": []
            },
            "collection": None,
            "tabView": None
        },
        "dataFlow": {
            "diagram": f"flowchart TD\n    VIEW[{screen_name}View] --> VM[{screen_name}ViewModel]",
            "repositories": [],
            "apiEndpoints": []
        },
        "stateManagement": {
            "states": [],
            "uiVariables": [],
            "eventHandlers": [],
            "displayLogic": []
        },
        "userActions": [],
        "validation": {
            "clientSide": [],
            "serverSide": []
        },
        "transitions": [],
        "relatedFiles": [],
        "notes": []
    }


def create_spec_file(
    screen_name: str,
    output_dir: Path = None,
    display_name: str = None,
    file_path: str | None = None,
) -> Path:
    """Create a screen specification file.

    Args:
        screen_name: Screen name in PascalCase (e.g., 'Login', 'UserProfile')
        output_dir: Output directory (default: docs/screens/json)
        display_name: Localized display name (optional)
        file_path: Explicit relative file path under output_dir
            (e.g., 'learn/hello-world.spec.json'). When supplied, the caller
            owns the naming convention — parent directories are created as
            needed and the filename is used verbatim (with `.spec.json`
            appended when missing). When omitted, the filename is derived
            from `screen_name` via kebab-case (LearnHelloWorld →
            learn-hello-world.spec.json) — this supersedes the old
            `screen_name.lower()` behaviour, which collapsed word boundaries.

    Returns:
        Path to the created file
    """
    if output_dir is None:
        output_dir = Path("docs/screens/json")

    if file_path:
        output_path = output_dir / file_path
        if output_path.suffix == "":
            output_path = output_path.with_suffix(".spec.json")
        elif not output_path.name.endswith(".spec.json"):
            # The caller passed e.g. "hello-world.json"; add .spec. before the extension
            stem = output_path.stem
            output_path = output_path.with_name(f"{stem}.spec.json")
    else:
        filename = f"{_pascal_to_kebab(screen_name)}.spec.json"
        output_path = output_dir / filename

    output_path.parent.mkdir(parents=True, exist_ok=True)

    template = generate_spec_template(screen_name, display_name)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
        f.write('\n')

    return output_path


def generate_component_template(component_name: str, display_name: str = None, category: str = "other") -> dict:
    """Generate a component specification template.

    Args:
        component_name: Component name in PascalCase (e.g., 'UserCard', 'SearchBar')
        display_name: Localized display name (optional, defaults to component_name)
        category: Component category (card, form, list, navigation, input, display, layout, feedback, other)

    Returns:
        Dictionary containing the component specification template
    """
    today = build_date().isoformat()

    return {
        "type": "component_spec",
        "version": "1.0",
        "metadata": {
            "name": component_name,
            "displayName": display_name or component_name,
            "description": "",
            "category": category,
            "createdAt": today,
            "updatedAt": today
        },
        "props": {
            "items": [],
            "notes": None
        },
        "slots": {
            "items": [],
            "notes": None
        },
        "structure": {
            "components": [
                {
                    "type": "View",
                    "id": "root_view",
                    "description": "Root container"
                }
            ],
            "layout": {
                "root": "root_view",
                "children": []
            }
        },
        "stateManagement": {
            "internalStates": [],
            "exposedEvents": []
        },
        "usage": {
            "example": None,
            "usedInScreens": []
        },
        "notes": []
    }


def create_component_file(component_name: str, output_dir: Path = None, display_name: str = None, category: str = "other") -> Path:
    """Create a component specification file.

    Args:
        component_name: Component name in PascalCase (e.g., 'UserCard', 'SearchBar')
        output_dir: Output directory (default: docs/components/json)
        display_name: Localized display name (optional)
        category: Component category (default: other)

    Returns:
        Path to the created file
    """
    if output_dir is None:
        output_dir = Path("docs/components/json")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert to lowercase for filename
    filename = f"{component_name.lower()}.component.json"
    output_path = output_dir / filename

    template = generate_component_template(component_name, display_name, category)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
        f.write('\n')

    return output_path
