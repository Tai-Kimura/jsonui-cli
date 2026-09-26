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
                    "description": "Author name. Documentation only: no generator or check reads it."
                },
                "createdAt": {
                    "type": "string",
                    "format": "date",
                    "description": (
                        "Creation date (YYYY-MM-DD). Documentation only: no "
                        "generator reads it; the validator checks its format."
                    )
                },
                "updatedAt": {
                    "type": "string",
                    "format": "date",
                    "description": (
                        "Last update date (YYYY-MM-DD). Documentation only: no "
                        "generator reads it; the validator checks its format."
                    )
                },
                "group": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}}
                    ],
                    "description": (
                        "The group(s) this screen is drawn in on the flow "
                        "diagram (`jsonui-doc generate mermaid`)."
                    )
                },
                "layoutFile": {
                    "type": "string",
                    "description": "Path to existing Layout JSON file (relative to layouts_directory, without .json extension). When set, components and bindings are imported from this file for documentation."
                },
                "platforms": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"enum": ["ios", "android", "web"]},
                    "description": (
                        "The platforms this screen exists on. Absent = every "
                        "platform the project declares. Read by `jsonui-test "
                        "generate branch-tests` (a platform outside this list, "
                        "or outside jui.config.json's platforms, generates "
                        "nothing for the screen) and by `jsonui-test contracts "
                        "coverage` (its statuses count as n/a(platform-excluded))."
                    )
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
                "collections": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/collectionStructure"},
                    "description": (
                        "More Collections on one screen, each read as "
                        "`collection` is (after it, when both are given)."
                    )
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
                    "description": "Notes about the overall structure. Documentation only: no generator or check reads it."
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
                    "enum": ["delegate", "isolated"],
                    "default": "delegate",
                    "description": (
                        "The Layout JSON Embed's navigationMode "
                        "(shared/core/attribute_definitions.json). "
                        "'delegate' (default): the embedded screen shares the "
                        "parent's NavController/Router. 'isolated': the embed "
                        "owns a private navigation stack, and the embedded "
                        "screen's spec may not declare present-type "
                        "transitions (jui build refuses it). Until jsonui-cli "
                        "1.9.0 the spec allowed 'delegate' only."
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
                    "description": "Brief description of how this component is used. Documentation only: no generator or check reads it."
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
                        "Button", "Image", "NetworkImage", "CircleView",
                        "IconLabel", "Collection", "TabView",
                        "SelectBox", "CheckBox", "Switch", "Radio",
                        "Segment", "Slider", "Progress", "Indicator",
                        "Web", "Blur", "GradientView"
                    ],
                    "description": (
                        "Component type: a Layout JSON component "
                        "(shared/core/attribute_definitions.json), by its "
                        "canonical name. Not Embed — another screen is hosted "
                        "through structure.embeds. Until jsonui-cli 1.9.0 the "
                        "list also held Spacer and Divider, which no Layout "
                        "tool knows, and lacked ten components it has."
                    )
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
                "platform": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "object"}
                    ],
                    "description": (
                        "The Layout JSON `platform` directive for this "
                        "component's node — 'ios' / 'android' / 'web', comma-"
                        "separated, or a per-platform attribute map. Written "
                        "onto the generated node."
                    )
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes. Documentation only: no generator or check reads it."
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
            "required": ["id"],
            "description": (
                "One Collection. Its cells are named by `cell`, by "
                "`cellClasses`, or by `sections[].cell` — one of them is "
                "required (the spec validator checks it)."
            ),
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
                    "anyOf": [
                        {"$ref": "#/$defs/layoutNode"},
                        {"$ref": "#/$defs/cellNode"},
                        {"type": "null"}
                    ]
                },
                "cell": {
                    "anyOf": [
                        {"$ref": "#/$defs/layoutNode"},
                        {"$ref": "#/$defs/cellNode"}
                    ]
                },
                "footer": {
                    "anyOf": [
                        {"$ref": "#/$defs/layoutNode"},
                        {"$ref": "#/$defs/cellNode"},
                        {"type": "null"}
                    ]
                },
                "insets": {
                    "type": ["array", "string"],
                    "items": {"type": "number"},
                    "description": (
                        "The Layout Collection's insets (content insets), "
                        "written onto the Collection `jui g project` "
                        "generates (from jsonui-cli 1.9.0)."
                    )
                },
                "description": {
                    "type": "string",
                    "description": "What the Collection shows. Documentation only: no generator or check reads it."
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes. Documentation only: no generator or check reads it."
                },
                "cellClasses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Layout JSON refs (layouts_directory-relative, no "
                        ".json) of the cells this Collection may use — the "
                        "multi-cell form. Written onto the Collection "
                        "`jui g project` generates (from jsonui-cli 1.9.0; "
                        "read by the validator and jsonui-doc before)."
                    )
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cell": {"type": "string", "description": "Cell layout ref"},
                            "header": {"type": ["string", "null"], "description": "Header layout ref"},
                            "footer": {"type": ["string", "null"], "description": "Footer layout ref"},
                            "columns": {"type": "number", "description": "Section columns"},
                            "index": {
                                "type": "integer",
                                "description": "The section's position, for the reader (the order is the array's). Documentation only: no generator or check reads it."
                            },
                            "description": {"type": "string", "description": "What the section shows. Documentation only: no generator or check reads it."},
                            "notes": {"type": "string", "description": "Additional notes. Documentation only: no generator or check reads it."}
                        }
                    },
                    "description": (
                        "Section-based Collection: each section names its "
                        "cell / header / footer layout. Written onto the "
                        "Collection `jui g project` generates, in place of "
                        "the section it derives from cell / header / footer "
                        "(from jsonui-cli 1.9.0)."
                    )
                }
            }
        },
        "cellNode": {
            "type": "object",
            "required": ["root"],
            "description": (
                "A Collection's cell, header or footer. With "
                "generateCellLayout: true, `jui g project` writes its Layout "
                "JSON (layoutFile, else <collection id>_<cell|header|footer>) "
                "and the Collection's section names that file; without it the "
                "layout is authored elsewhere and the fields describe it."
            ),
            "properties": {
                "children": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"$ref": "#/$defs/layoutChild"},
                            {"type": "string"}
                        ]
                    },
                    "description": (
                        "The layoutNode form's tree under a string root: "
                        "component ids from structure.components (a View of "
                        "that id when there is none), or layoutChild objects."
                    )
                },
                "overlay": {
                    "type": "boolean",
                    "description": (
                        "With children: stacked (ZStack-style) instead of "
                        "vertical."
                    )
                },
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
                },
                "view": {
                    "type": "string",
                    "description": "Older name of layoutFile, read when layoutFile is absent.",
                    "deprecated": True
                },
                "icon": {
                    "type": "string",
                    "description": "Tab icon name (SF Symbol for iOS, drawable for Android) — the Layout's TabView tabs[].icon"
                },
                "selectedIcon": {
                    "type": "string",
                    "description": "Icon when the tab is selected (defaults to icon)"
                },
                "iconType": {
                    "type": "string",
                    "enum": ["system", "resource", "lucide"],
                    "description": "Icon source type — the Layout's tabs[].iconType"
                }
            }
        },
        "dataFlow": {
            "type": "object",
            "properties": {
                "diagram": {
                    "type": "string",
                    "description": "Mermaid diagram code. Documentation only: no generator or check reads it."
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
                    "description": "Notes about data flow. Documentation only: no generator or check reads it."
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
                "description": {
                    "type": "string",
                    "description": "Repository description (jui g project records it in .jui_cache.json; no generated source file carries it)"
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
                "platforms": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["ios", "android", "web"]},
                    "description": (
                        "Platforms this method exists on — same spelling and "
                        "values as a viewModel var's `platforms`. Omit for all; "
                        "an empty list is read as all as well (unlike a "
                        "viewModel var, where [] means nowhere). `jui generate "
                        "project` leaves the method out of the other "
                        "platforms' Repository / UseCase protocols, the spec "
                        "validator suggests `[\"ios\"]` for a method typed "
                        "with iOS-only types, and `jsonui-test contracts "
                        "coverage` counts this method's endpoint on the other "
                        "platforms as n/a(platform-excluded) — unless another "
                        "method declaring the same endpoint exists there."
                    )
                },
                "params": {
                    "oneOf": [
                        {
                            "type": "string",
                            "description": (
                                "'@canonical' to take the parameters from the "
                                "operation this method's 'endpoint' names, or "
                                "legacy free-text"
                            )
                        },
                        {
                            "type": "array",
                            "items": {
                                "oneOf": [
                                    {"const": "@canonical"},
                                    {"$ref": "#/$defs/methodParam"}
                                ]
                            },
                            "description": (
                                "Structured method parameters. '@canonical' may "
                                "appear as an entry, expanding in place to the "
                                "operation's parameters; hand-written entries "
                                "beside it win on name collision, which is how "
                                "a client-side argument the API never declares "
                                "is added"
                            )
                        }
                    ]
                },
                "canonicalDivergence": {
                    "type": "object",
                    "description": (
                        "Declares, with a reason, how this method's written-out "
                        "params deliberately differ from the operation its "
                        "endpoint names. Checked against the real difference: a "
                        "note that no longer describes one is an error, which is "
                        "how a rename in the API document stops a stale "
                        "'we already handled that' from outliving the thing it "
                        "was about. Only meaningful on hand-written params — a "
                        "'@canonical' method follows the canon by construction. "
                        "Read on dataFlow.repositories / useCases methods; on "
                        "dataFlow.viewModel.methods no tool reads it."
                    ),
                    "properties": {
                        "renamed": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "description": "canonical parameter name -> the name this spec uses"
                        },
                        "omitted": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Canonical arguments this method deliberately "
                                "does not take (constants the caller never chooses)"
                            )
                        },
                        "wrapped": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "array", "items": {"type": "string"}
                            },
                            "description": (
                                "spec argument -> the canonical arguments it "
                                "stands in for (a request object)"
                            )
                        },
                        "added": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Written arguments the operation does not "
                                "declare (multipart bodies)"
                            )
                        },
                        "reason": {"type": "string", "minLength": 1}
                    },
                    "required": ["reason"],
                    "additionalProperties": False
                },
                "returnType": {
                    "type": "string",
                    "description": (
                        "Return type, or '@canonical.wire' for the schema the "
                        "operation's success response names. Not '@canonical': "
                        "a spec's return type is the domain type and the "
                        "canon's is the wire type, and they legitimately differ"
                    )
                },
                "isAsync": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether the method is async (default: true)"
                },
                "endpoint": {
                    "type": "string",
                    "description": (
                        "Transport this method talks to, as '<VERB> <path>' "
                        "(e.g. 'POST /api/items/{item_id}/notes'). An HTTP "
                        "verb makes the declaration checkable: validate "
                        "compares path and parameter spelling against the "
                        "OpenAPI documents under api_directory, and "
                        "`jsonui-test generate branch-tests` binds "
                        "`api.<method>` scenarios through it. Non-HTTP verbs "
                        "(WebSocket / RTDB / GraphQL …) are legal and left "
                        "unchecked."
                    )
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
                    "description": "Request body structure. Documentation only: no generator or check reads it."
                },
                "response": {
                    "type": "object",
                    "description": "Response body structure. Documentation only: no generator or check reads it."
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about this endpoint. Documentation only: no generator or check reads it."
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
                    "description": "Notes about state management. Documentation only: no generator or check reads it."
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
                    "description": "Notes about this state. Documentation only: no generator or check reads it."
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
                    "description": "Description of this state. Documentation only: no generator or check reads it."
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
                "defaultValue": {
                    "description": (
                        "Initial value — the Layout JSON data entry's "
                        "defaultValue. `jui g project` writes it; `jui verify` "
                        "compares it with the layout's."
                    )
                },
                "default": {
                    "description": (
                        "Older spelling of defaultValue. When both are given, "
                        "default is used (and a differing defaultValue is named)."
                    )
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes. Documentation only: no generator or check reads it."
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
                    "description": "Additional notes. Documentation only: no generator or check reads it."
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
                    "description": "Additional notes. Documentation only: no generator or check reads it."
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
                "notes": {"type": "string"},
                "seedableState": {
                    "type": "object",
                    "description": (
                        "ViewModel-internal state a branch may arrange: "
                        "{name: type}. The harness seeds it and reads it back."
                    ),
                    "additionalProperties": {"type": "string"}
                },
                "unreachedOps": {
                    "type": "object",
                    "description": (
                        "Declared operations no contracted method on this "
                        "screen calls: {\"api.<op>\": {reason, platforms?}}. "
                        "Removes the operation from the coverage requirement "
                        "(counted as unreached-op)."
                    ),
                    "propertyNames": {"pattern": "^api\\.\\S+$"},
                    "additionalProperties": {"$ref": "#/$defs/unreachedOp"}
                }
            },
            "additionalProperties": False
        },
        "unreachedOp": {
            "type": "object",
            "required": ["reason"],
            "properties": {
                "reason": {"type": "string", "minLength": 1},
                "platforms": {"$ref": "#/$defs/contractPlatforms"}
            },
            "additionalProperties": False
        },
        "contractPlatforms": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"enum": ["ios", "android", "web"]},
            "description": "Limit to these platforms. Absent = every platform."
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
                },
                "excludedOutcomes": {
                    "type": "object",
                    "description": (
                        "API outcomes this method reaches but does not need a "
                        "row for: {\"api.<op>\": {\"<status>\": {by, reason, "
                        "platforms?}}}. <status> is an OpenAPI response key "
                        "(\"404\", \"4XX\"; not \"default\"). by: unit | "
                        "unreachable | unexpressible. Folding a status into "
                        "another outcome is a row, not an exclusion."
                    ),
                    "propertyNames": {"pattern": "^api\\.\\S+$"},
                    "additionalProperties": {
                        "type": "object",
                        "propertyNames": {"pattern": "^[1-5]([0-9]{2}|XX)$"},
                        "additionalProperties": {"$ref": "#/$defs/excludedOutcome"}
                    }
                }
            },
            "additionalProperties": False
        },
        "excludedOutcome": {
            "type": "object",
            "required": ["by", "reason"],
            "properties": {
                "by": {"enum": ["unit", "unreachable", "unexpressible"]},
                "reason": {"type": "string", "minLength": 1},
                "platforms": {"$ref": "#/$defs/contractPlatforms"}
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
                "'!' prefix allowed) / 'harness.<name>' (a precondition the "
                "harness sets up — one of the values the app contracts "
                "spec's harnessConditions declares). then keys: 'data.<field>' (literal, "
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
                        },
                        "alsoStatuses": {
                            "type": "object",
                            "minProperties": 1,
                            "description": (
                                "This row's then holds for these statuses of "
                                "the operation too: {\"api.<op>\": [\"429\", "
                                "\"503\"]}. The key must be an api.<op> this "
                                "row's when names with a scenario; values are "
                                "plain statuses (no ranges, no 'default'). Not "
                                "on a note row."
                            ),
                            "propertyNames": {"pattern": "^api\\.\\S+$"},
                            "additionalProperties": {
                                "type": "array",
                                "minItems": 1,
                                "uniqueItems": True,
                                "items": {"type": "string", "pattern": "^[1-5][0-9]{2}$"}
                            }
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
                    "description": "Transition condition. Documentation only: no generator or check reads it."
                },
                "destination": {
                    "type": "string",
                    "description": "Destination screen"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes. Documentation only: no generator or check reads it."
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
