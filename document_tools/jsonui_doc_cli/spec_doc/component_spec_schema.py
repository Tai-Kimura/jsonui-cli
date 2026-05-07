"""JSON Schema definition for component specification files."""

COMPONENT_SPEC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Component Specification",
    "description": "Schema for JsonUI reusable component specification documents",
    "type": "object",
    "required": ["type", "version", "metadata", "structure"],
    "properties": {
        "$schema": {
            "type": "string",
            "description": "JSON Schema reference"
        },
        "type": {
            "type": "string",
            "const": "component_spec",
            "description": "Document type identifier"
        },
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+$",
            "description": "Schema version (e.g., '1.0')"
        },
        "metadata": {"$ref": "#/$defs/metadata"},
        "props": {"$ref": "#/$defs/props"},
        "slots": {"$ref": "#/$defs/slots"},
        "structure": {"$ref": "#/$defs/structure"},
        "stateManagement": {"$ref": "#/$defs/stateManagement"},
        "usage": {"$ref": "#/$defs/usage"},
        "notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "General notes for the component"
        }
    },
    "$defs": {
        "metadata": {
            "type": "object",
            "required": ["name", "displayName", "description"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^[A-Z][a-zA-Z0-9]*$",
                    "description": "Component name in PascalCase (e.g., 'UserCard', 'SearchBar')"
                },
                "displayName": {
                    "type": "string",
                    "description": "Localized display name"
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the component's purpose"
                },
                "category": {
                    "type": "string",
                    "enum": ["card", "form", "list", "navigation", "input", "display", "layout", "feedback", "other"],
                    "description": "Component category for organization"
                },
                "author": {
                    "type": "string",
                    "description": "Author name"
                },
                "createdAt": {
                    "type": "string",
                    "format": "date",
                    "description": "Creation date (YYYY-MM-DD)"
                },
                "updatedAt": {
                    "type": "string",
                    "format": "date",
                    "description": "Last update date (YYYY-MM-DD)"
                }
            }
        },
        "props": {
            "type": "object",
            "description": "Properties that can be passed to the component from outside",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/propItem"}
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about props"
                }
            }
        },
        "propItem": {
            "type": "object",
            "required": ["name", "type", "description"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^[a-z][a-zA-Z0-9]*$",
                    "description": "Property name in camelCase"
                },
                "type": {
                    "type": "string",
                    "description": "Property type (String, Int, Bool, String?, [String], etc.)"
                },
                "required": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether the property is required"
                },
                "default": {
                    "description": "Default value if not required"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the property"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "slots": {
            "type": "object",
            "description": "Slots where external content can be inserted",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/slotItem"}
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about slots"
                }
            }
        },
        "slotItem": {
            "type": "object",
            "required": ["name", "description"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^[a-z][a-zA-Z0-9]*$",
                    "description": "Slot name in camelCase"
                },
                "description": {
                    "type": "string",
                    "description": "Description of what should be inserted"
                },
                "required": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether the slot is required"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "structure": {
            "type": "object",
            "required": ["components", "layout"],
            "properties": {
                "components": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/component"},
                    "minItems": 1
                },
                "layout": {"$ref": "#/$defs/layoutNode"},
                "notes": {
                    "type": "string",
                    "description": "Notes about the overall structure"
                }
            }
        },
        "component": {
            "type": "object",
            "required": ["type", "id", "description"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": [
                        "View", "ScrollView",
                        "Label", "TextField", "TextView",
                        "Button", "Image", "Collection",
                        "SelectBox", "CheckBox", "Switch", "Web",
                        "Spacer", "Divider", "Indicator"
                    ],
                    "description": "Component type"
                },
                "id": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9_]*$",
                    "description": "Component ID in snake_case"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the component"
                },
                "boundToProp": {
                    "type": "string",
                    "description": "If this component displays a prop value, specify the prop name"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "layoutNode": {
            "type": "object",
            "required": ["root", "children"],
            "properties": {
                "root": {
                    "type": "string",
                    "description": "Root component ID"
                },
                "children": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"$ref": "#/$defs/layoutChild"},
                            {"type": "string"}
                        ]
                    }
                }
            }
        },
        "layoutChild": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Component ID"
                },
                "children": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"$ref": "#/$defs/layoutChild"},
                            {"type": "string"}
                        ]
                    }
                }
            }
        },
        "stateManagement": {
            "type": "object",
            "properties": {
                "internalStates": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/internalState"},
                    "description": "States managed internally by the component"
                },
                "exposedEvents": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/exposedEvent"},
                    "description": "Events that the component exposes to parent"
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about state management"
                }
            }
        },
        "internalState": {
            "type": "object",
            "required": ["name", "type", "description"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^[a-z][a-zA-Z0-9]*$",
                    "description": "State variable name in camelCase"
                },
                "type": {
                    "type": "string",
                    "description": "State type (String, Int, Bool, etc.)"
                },
                "initialValue": {
                    "description": "Initial value"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the state"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "exposedEvent": {
            "type": "object",
            "required": ["name", "description"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^on[A-Z][a-zA-Z0-9]*$",
                    "description": "Event name (e.g., onTap, onSelect)"
                },
                "parameters": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/eventParameter"},
                    "description": "Parameters passed with the event"
                },
                "description": {
                    "type": "string",
                    "description": "Description of when the event is triggered"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "eventParameter": {
            "type": "object",
            "required": ["name", "type"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Parameter name"
                },
                "type": {
                    "type": "string",
                    "description": "Parameter type"
                },
                "description": {
                    "type": "string",
                    "description": "Parameter description"
                }
            }
        },
        "usage": {
            "type": "object",
            "properties": {
                "example": {
                    "type": "string",
                    "description": "Example JSON usage"
                },
                "usedInScreens": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of screens that use this component"
                },
                "notes": {
                    "type": "string",
                    "description": "Usage notes"
                }
            }
        }
    }
}
