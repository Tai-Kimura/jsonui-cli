"""JSON Schema definition for screen specification files."""

SCREEN_SPEC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Screen Specification",
    "description": "Schema for JsonUI screen specification documents",
    "type": "object",
    "required": ["type", "version", "metadata", "structure"],
    "properties": {
        "$schema": {
            "type": "string",
            "description": "JSON Schema reference"
        },
        "type": {
            "type": "string",
            "const": "screen_spec",
            "description": "Document type identifier"
        },
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+$",
            "description": "Schema version (e.g., '1.0')"
        },
        "metadata": {"$ref": "#/$defs/metadata"},
        "structure": {"$ref": "#/$defs/structure"},
        "dataFlow": {"$ref": "#/$defs/dataFlow"},
        "stateManagement": {"$ref": "#/$defs/stateManagement"},
        "userActions": {
            "type": "array",
            "items": {"$ref": "#/$defs/userAction"}
        },
        "validation": {"$ref": "#/$defs/validation"},
        "transitions": {
            "type": "array",
            "items": {"$ref": "#/$defs/transition"}
        },
        "branchContracts": {"$ref": "#/$defs/branchContracts"},
        "relatedFiles": {
            "type": "array",
            "items": {"$ref": "#/$defs/relatedFile"}
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "General notes for the entire screen"
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
                    "description": "Screen name in PascalCase (e.g., 'Login', 'UserProfile')"
                },
                "displayName": {
                    "type": "string",
                    "description": "Localized display name"
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the screen's purpose"
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
                },
                "layoutFile": {
                    "type": "string",
                    "description": "Path to existing Layout JSON file (relative to layouts_directory, without .json extension). When set, components and bindings are imported from this file for documentation."
                }
            }
        },
        "structure": {
            "type": "object",
            "required": ["components", "layout"],
            "properties": {
                "components": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/component"}
                },
                "customComponents": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/customComponentRef"},
                    "description": "References to custom component specifications"
                },
                "decorativeElements": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/decorativeElement"},
                    "description": (
                        "Groups of decorative components (hero images, "
                        "security-indicator icons, gradient overlays, etc.)"
                    )
                },
                "wrapperViews": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/wrapperView"},
                    "description": (
                        "Style-only wrapper Views inserted around target "
                        "components at generation time."
                    )
                },
                "layout": {"$ref": "#/$defs/layoutNode"},
                "collection": {
                    "oneOf": [
                        {"$ref": "#/$defs/collectionStructure"},
                        {"type": "null"}
                    ]
                },
                "tabView": {
                    "oneOf": [
                        {"$ref": "#/$defs/tabViewStructure"},
                        {"type": "null"}
                    ]
                },
                "embeds": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/embedEntry"},
                    "description": (
                        "Cross-screen embeds. Each entry hosts another "
                        "screen as a region of this layout while keeping "
                        "its own ViewModel. See specification-rules.md (5)."
                    )
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about the overall structure"
                }
            }
        },
        "embedEntry": {
            "type": "object",
            "required": ["regionId", "screen"],
            "properties": {
                "regionId": {
                    "type": "string",
                    "pattern": "^[a-z][a-zA-Z0-9]*$",
                    "description": (
                        "camelCase id matching the corresponding Layout "
                        "JSON Embed.id. Unique within the parent layout."
                    )
                },
                "screen": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9_]*$",
                    "description": (
                        "snake_case layout JSON filename of the embedded "
                        "screen (no extension)."
                    )
                },
                "params": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": (
                        "Init params for the embedded VM. Keys camelCase. "
                        "Values may be literals or @{varName} bindings."
                    )
                },
                "events": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": (
                        "Map of on[A-Z]... event names to parent VM "
                        "method or eventHandler names."
                    )
                },
                "navigationMode": {
                    "type": "string",
                    "enum": ["delegate"],
                    "default": "delegate",
                    "description": (
                        "v1 supports 'delegate' only — embedded screen "
                        "shares the parent's NavController/Router. "
                        "'isolated' is deferred to v1.5."
                    )
                }
            }
        },
        "customComponentRef": {
            "type": "object",
            "required": ["name", "specFile"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^[A-Z][a-zA-Z0-9]*$",
                    "description": "Custom component name in PascalCase"
                },
                "specFile": {
                    "type": "string",
                    "description": "Path to .component.json file (e.g., 'googlemapview.component.json')"
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of how this component is used"
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
                        "View", "ScrollView", "SafeAreaView",
                        "Label", "TextField", "TextView",
                        "Button", "Image", "Collection", "TabView",
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
                "initialState": {
                    "type": "string",
                    "description": "Initial state/style of the component"
                },
                "style": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": (
                        "Optional visual/layout style attributes applied "
                        "directly onto the generated Layout JSON node "
                        "(e.g., background, cornerRadius, padding, weight, "
                        "width, height)."
                    )
                },
                "binding": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": (
                        "Optional map of JSON attribute name to variable "
                        "name (e.g., {\"text\": \"title\"} becomes "
                        "\"text\": \"@{title}\" in the Layout JSON)."
                    )
                },
                "children": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/component"},
                    "description": (
                        "Optional nested component tree. When present the "
                        "generator renders them as child nodes of this "
                        "component in the Layout JSON."
                    )
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "decorativeElement": {
            "type": "object",
            "required": ["id", "components"],
            "properties": {
                "id": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9_]*$"
                },
                "purpose": {
                    "type": "string",
                    "description": (
                        "Short label categorising the decoration "
                        "(e.g., 'hero', 'security-indicator')."
                    )
                },
                "parentId": {
                    "type": "string",
                    "description": (
                        "Target component ID to insert the decorative "
                        "elements into. Defaults to the layout root."
                    )
                },
                "components": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/component"}
                }
            }
        },
        "wrapperView": {
            "type": "object",
            "required": ["id", "wraps"],
            "properties": {
                "id": {
                    "type": "string",
                    "pattern": "^[a-z][a-z0-9_]*$"
                },
                "wraps": {
                    "type": "string",
                    "description": "Component ID that this wrapper wraps"
                },
                "purpose": {"type": "string"},
                "style": {
                    "type": "object",
                    "additionalProperties": True
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
                "overlay": {
                    "type": "boolean",
                    "description": (
                        "When true, children are stacked on top of each "
                        "other (ZStack-style) instead of laid out along the "
                        "container's orientation. The generator emits the "
                        "container without an 'orientation' field and "
                        "respects each child's zIndex ordering."
                    )
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
                "overlay": {
                    "type": "boolean",
                    "description": (
                        "When true, this node's children are stacked on top "
                        "of each other (ZStack-style)."
                    )
                },
                "zIndex": {
                    "type": "integer",
                    "description": (
                        "Z-order index for overlay layouts — higher values "
                        "render above lower ones."
                    )
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
        "collectionStructure": {
            "type": "object",
            "required": ["id", "cell"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Collection component ID"
                },
                "cellIdProperty": {"type": "string"},
                "autoChangeTrackingId": {"type": "boolean"},
                "lazy": {
                    "type": "boolean",
                    "description": (
                        "Whether the Collection uses a lazy (virtualized) "
                        "container. Default true. When false, generators emit "
                        "a plain VStack/Column/div with ForEach and NO scroll "
                        "container (use when nested inside an already-"
                        "scrollable parent). Sticky headers and paging require "
                        "lazy: true."
                    )
                },
                "header": {
                    "oneOf": [
                        {"$ref": "#/$defs/layoutNode"},
                        {"$ref": "#/$defs/cellNode"},
                        {"type": "null"}
                    ]
                },
                "cell": {
                    "oneOf": [
                        {"$ref": "#/$defs/layoutNode"},
                        {"$ref": "#/$defs/cellNode"}
                    ]
                },
                "footer": {
                    "oneOf": [
                        {"$ref": "#/$defs/layoutNode"},
                        {"$ref": "#/$defs/cellNode"},
                        {"type": "null"}
                    ]
                }
            }
        },
        "cellNode": {
            "type": "object",
            "required": ["root"],
            "properties": {
                "viewName": {
                    "type": "string",
                    "description": "Cell SwiftUI/Compose view class name"
                },
                "layoutFile": {
                    "type": "string",
                    "description": (
                        "Cell Layout JSON path (relative to layouts_directory), "
                        "without the .json suffix. Same convention as "
                        "metadata.layoutFile and include/view references."
                    )
                },
                "layout": {
                    "type": "string",
                    "description": (
                        "Deprecated alias for layoutFile. Use layoutFile instead."
                    ),
                    "deprecated": True
                },
                "generateCellLayout": {
                    "type": "boolean",
                    "description": (
                        "When true, jui_tools writes a standalone cell "
                        "Layout JSON to layouts_directory/{layoutFile}.json "
                        "during generation."
                    )
                },
                "root": {
                    "oneOf": [
                        {"type": "string"},
                        {"$ref": "#/$defs/component"}
                    ],
                    "description": (
                        "Cell root. When a string, the cell is described "
                        "separately (legacy). When an object, it's a full "
                        "component tree the generator can render directly."
                    )
                },
                "dataKeys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Legacy: plain list of binding names. Prefer "
                        "cellNode.uiVariables for typed declarations so the "
                        "cell's generated Layout JSON gets a proper `data` "
                        "section."
                    )
                },
                "uiVariables": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/uiVariable"},
                    "description": (
                        "Cell-local UI variables (same shape as "
                        "stateManagement.uiVariables). When set, the cell's "
                        "generated Layout JSON gets a top-level `data` "
                        "section built from these variables — giving the cell "
                        "its own typed data model instead of inheriting "
                        "untyped values through the parent Collection's "
                        "items binding."
                    )
                },
                "eventHandlers": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/eventHandler"},
                    "description": (
                        "Cell-local event handlers. Added to the cell's `data` "
                        "section as callback properties so Layout JSON "
                        "bindings like `\"onClick\": \"@{onMapTap}\"` resolve "
                        "against the cell's own data."
                    )
                }
            }
        },
        "tabViewStructure": {
            "type": "object",
            "required": ["id", "tabs"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "TabView component ID"
                },
                "tabs": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/tab"},
                    "minItems": 1
                }
            }
        },
        "tab": {
            "type": "object",
            "required": ["title", "layoutFile"],
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Tab title"
                },
                "layoutFile": {
                    "type": "string",
                    "description": "Layout file name"
                }
            }
        },
        "dataFlow": {
            "type": "object",
            "properties": {
                "diagram": {
                    "type": "string",
                    "description": "Mermaid diagram code"
                },
                "viewModel": {"$ref": "#/$defs/viewModel"},
                "repositories": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/repository"}
                },
                "useCases": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/useCase"}
                },
                "apiEndpoints": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/apiEndpoint"}
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about data flow"
                }
            }
        },
        "viewModel": {
            "type": "object",
            "description": (
                "ViewModel public contract — ``methods`` are public API "
                "(button taps, async fetches, etc.) and ``vars`` are public "
                "properties (state, callbacks). Both are auto-imported into "
                "the platform Protocol/Interface during `jui build`."
            ),
            "properties": {
                "description": {"type": "string"},
                "methods": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {"$ref": "#/$defs/repositoryMethod"},
                        ]
                    }
                },
                "vars": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/viewModelVar"}
                }
            }
        },
        "viewModelVar": {
            "type": "object",
            "required": ["name", "type"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Property name (camelCase)"
                },
                "type": {
                    "type": "string",
                    "description": (
                        "Swift-style type. Closure types (`() -> Void`) are "
                        "translated per platform. Plain names route through "
                        "TypeMapper."
                    )
                },
                "optional": {
                    "type": "boolean",
                    "default": False,
                    "description": "Append ?/| undefined on each platform"
                },
                "observable": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "iOS: @Published; Android: StateFlow-backed; Web: "
                        "stored in <Name>Data (not directly on Base)."
                    )
                },
                "readOnly": {
                    "type": "boolean",
                    "default": False,
                    "description": "Protocol emits getter-only / `val` / `readonly`"
                },
                "platforms": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["ios", "android", "web"]},
                    "description": (
                        "Target platforms. Omit for all. [] means 'nowhere' "
                        "(warning). Values outside {ios, android, web} fail "
                        "validation."
                    )
                },
                "description": {"type": "string"}
            }
        },
        "useCase": {
            "type": "object",
            "required": ["name", "methods"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "UseCase class name (e.g., 'LoginUseCase')"
                },
                "description": {
                    "type": "string",
                    "description": "UseCase description"
                },
                "repositories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of dependent Repository names"
                },
                "methods": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {"$ref": "#/$defs/repositoryMethod"}
                        ]
                    },
                    "description": "Method signatures (string or structured object)"
                }
            }
        },
        "repository": {
            "type": "object",
            "required": ["name", "methods"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Repository class name"
                },
                "methods": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {"$ref": "#/$defs/repositoryMethod"}
                        ]
                    },
                    "description": "Method signatures (string or object with name, params, returnType)"
                }
            }
        },
        "methodParam": {
            "type": "object",
            "required": ["name", "type"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Parameter name"
                },
                "type": {
                    "type": "string",
                    "description": "Parameter type (e.g., 'String', 'Int', '[String]')"
                },
                "description": {
                    "type": "string",
                    "description": "Parameter description"
                }
            }
        },
        "repositoryMethod": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Method name"
                },
                "params": {
                    "oneOf": [
                        {
                            "type": "string",
                            "description": "Method parameters (legacy free-text format)"
                        },
                        {
                            "type": "array",
                            "items": {"$ref": "#/$defs/methodParam"},
                            "description": "Structured method parameters"
                        }
                    ]
                },
                "returnType": {
                    "type": "string",
                    "description": "Return type"
                },
                "isAsync": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether the method is async (default: true)"
                },
                "description": {
                    "type": "string",
                    "description": "Method description"
                }
            }
        },
        "apiEndpoint": {
            "type": "object",
            "required": ["path", "method"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "API endpoint path"
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "description": "HTTP method"
                },
                "request": {
                    "type": "object",
                    "description": "Request body structure"
                },
                "response": {
                    "type": "object",
                    "description": "Response body structure"
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about this endpoint"
                }
            }
        },
        "stateManagement": {
            "type": "object",
            "properties": {
                "states": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/stateDefinition"}
                },
                "uiVariables": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/uiVariable"}
                },
                "eventHandlers": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/eventHandler"}
                },
                "displayLogic": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/displayLogicRule"}
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about state management"
                }
            }
        },
        "stateDefinition": {
            "type": "object",
            "required": ["name", "values"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "State enum name"
                },
                "values": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/stateValue"},
                    "minItems": 1
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about this state"
                }
            }
        },
        "stateValue": {
            "type": "object",
            "required": ["value", "description"],
            "properties": {
                "value": {
                    "type": "string",
                    "description": "State value name"
                },
                "description": {
                    "type": "string",
                    "description": "Description of this state"
                },
                "visibleElements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Elements visible in this state"
                }
            }
        },
        "uiVariable": {
            "type": "object",
            "required": ["name", "type", "description"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^[a-z][a-zA-Z0-9]*$",
                    "description": "Variable name in camelCase"
                },
                "type": {
                    "type": "string",
                    "description": "Variable type (String, Int, Bool, etc.)"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the variable"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "eventHandler": {
            "type": "object",
            "required": ["name", "description"],
            "description": (
                "View-local event handler. Under the new architecture ViewModel "
                "public API lives in dataFlow.viewModel; eventHandlers is "
                "reserved for handlers that stay inside the View layer."
            ),
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^on[A-Z][a-zA-Z0-9]*$",
                    "description": "Handler name (e.g., onLoginTap)"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the handler"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "displayLogicRule": {
            "type": "object",
            "required": ["condition", "effects"],
            "properties": {
                "condition": {
                    "type": "string",
                    "description": "Condition expression"
                },
                "effects": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/displayEffect"}
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "displayEffect": {
            "type": "object",
            "required": ["element", "state"],
            "properties": {
                "element": {
                    "type": "string",
                    "description": "Target element ID"
                },
                "state": {
                    "type": "string",
                    "description": "State to apply (visible, hidden, disabled, etc.)"
                },
                "variableName": {
                    "type": "string",
                    "description": (
                        "Explicit variable name for the generated visibility "
                        "binding. When omitted, the name is derived from the "
                        "element ID (e.g. 'loading_indicator' → "
                        "'loadingIndicatorVisibility'). Useful when multiple "
                        "effects should share one variable."
                    )
                }
            }
        },
        "userAction": {
            "type": "object",
            "required": ["action", "processing"],
            "properties": {
                "action": {
                    "type": "string",
                    "description": "User action description"
                },
                "processing": {
                    "type": "string",
                    "description": "Processing logic"
                },
                "destination": {
                    "type": "string",
                    "description": "Next screen or '-'"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "validation": {
            "type": "object",
            "properties": {
                "clientSide": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/clientValidation"}
                },
                "serverSide": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/serverValidation"}
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about validation"
                }
            }
        },
        "clientValidation": {
            "type": "object",
            "required": ["field", "rule"],
            "properties": {
                "field": {
                    "type": "string",
                    "description": "Field name"
                },
                "rule": {
                    "type": "string",
                    "description": "Validation rule"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "serverValidation": {
            "type": "object",
            "required": ["condition", "handling"],
            "properties": {
                "condition": {
                    "type": "string",
                    "description": "Error condition"
                },
                "handling": {
                    "type": "string",
                    "description": "How to handle the error"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "branchContracts": {
            "type": "object",
            "description": (
                "Opt-in, machine-checkable branch declarations for VM/UseCase "
                "methods. Conditions and outcomes reference ONLY already-"
                "declared vocabulary: data fields (stateManagement.uiVariables "
                "/ dataFlow.viewModel.vars / stateManagement.states), method "
                "args, API operations (dataFlow) with named mock scenarios, "
                "transitions, and strings.json keys ('@key'). Branches that "
                "cannot be expressed in the closed vocabulary are declared as "
                "'note' entries — counted explicitly, never silently dropped."
            ),
            "properties": {
                "conditions": {
                    "type": "object",
                    "description": (
                        "Named derived predicates. The expression body is NOT "
                        "declared (it would mirror the code); instead each "
                        "condition ships witness states that make it "
                        "true/false, which test generation can replay."
                    ),
                    "additionalProperties": {"$ref": "#/$defs/branchCondition"}
                },
                "methods": {
                    "type": "object",
                    "description": (
                        "Per-method branch tables. Keys must be method names "
                        "declared in dataFlow.viewModel.methods or "
                        "stateManagement.eventHandlers."
                    ),
                    "additionalProperties": {"$ref": "#/$defs/branchMethodContract"}
                },
                "notes": {"type": "string"}
            },
            "additionalProperties": False
        },
        "branchCondition": {
            "type": "object",
            "required": ["meaning"],
            "properties": {
                "meaning": {
                    "type": "string",
                    "description": "Human meaning of the predicate"
                },
                "witness_true": {
                    "type": "object",
                    "description": "Example data state that makes the predicate true"
                },
                "witness_false": {
                    "type": "object",
                    "description": "Example data state that makes the predicate false"
                }
            },
            "additionalProperties": False
        },
        "branchMethodContract": {
            "type": "object",
            "required": ["branches"],
            "properties": {
                "baseline": {
                    "type": "object",
                    "description": (
                        "Method-level default witness: the data state every "
                        "branch's arrange starts from (e.g. 'all entry guards "
                        "pass'). Individual branches override on top of it."
                    )
                },
                "branches": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/$defs/branchEntry"}
                }
            },
            "additionalProperties": False
        },
        "branchEntry": {
            "type": "object",
            "description": (
                "Either a declared branch {when, then, notes?} or an escape-"
                "hatch {note} for branches outside the closed vocabulary. "
                "when keys: 'data.<field>' / 'arg.<name>' / 'api.<op>' (value "
                "= named mock scenario) / 'cond' (named condition reference, "
                "'!' prefix allowed). then keys: 'data.<field>' (literal, "
                "'@strings_key', or '@data.<field>') / 'transition' / 'api' "
                "(value 'none') / 'api.<op>' ('called' | 'not-called') / "
                "'api.<op>.request' (partial request-body match)."
            ),
            "oneOf": [
                {
                    "type": "object",
                    "required": ["note"],
                    "properties": {"note": {"type": "string"}},
                    "additionalProperties": False
                },
                {
                    "type": "object",
                    "required": ["when", "then"],
                    "properties": {
                        "when": {"type": "object", "minProperties": 1},
                        "then": {"type": "object", "minProperties": 1},
                        "notes": {"type": "string"},
                        "platforms": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string",
                                      "enum": ["ios", "android", "web"]},
                            "description": (
                                "Platform-scoped branch: renderers generate "
                                "it only for the listed platforms (e.g. an "
                                "outcome field that exists on one platform "
                                "only). Omit for all platforms."
                            )
                        }
                    },
                    "additionalProperties": False
                }
            ]
        },
        "transition": {
            "type": "object",
            "required": ["condition", "destination"],
            "properties": {
                "condition": {
                    "type": "string",
                    "description": "Transition condition"
                },
                "destination": {
                    "type": "string",
                    "description": "Destination screen"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        },
        "relatedFile": {
            "type": "object",
            "required": ["type", "path"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["View", "ViewModel", "Layout", "Repository", "UseCase", "Model", "Test"],
                    "description": "File type"
                },
                "path": {
                    "type": "string",
                    "description": "File path"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            }
        }
    }
}
