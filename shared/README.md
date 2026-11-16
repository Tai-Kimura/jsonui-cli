# Shared Resources

This directory contains shared resources used across all JsonUI CLI tools.

## Directory Structure

```
shared/
├── core/
│   └── attribute_definitions.json   # Unified component attribute definitions
└── hotloader/                        # (Future) Shared hotloader code
```

## attribute_definitions.json

Unified attribute definitions for all JsonUI platforms (Swift/Kotlin/React).

### Platform-specific Attributes

Some attributes are platform-specific and marked with a `"platform"` key:
- `"platform": "swift"` - iOS only (SwiftJsonUI)
- `"platform": "kotlin"` - Android only (KotlinJsonUI)
- `"platform": "react"` - Web only (ReactJsonUI)

### Differences Summary

| Category | Attribute | Platforms |
|----------|-----------|-----------|
| **common** | padding | kjui, rjui |
| **Label** | fontWeight | rjui only |
| **Segment** | onValueChange, onValueChanged | rjui only |
| **SelectBox** | onValueChanged, selectedValue | rjui only |
| **TextField** | maxLength, pattern, required | sjui, rjui |
| **TextView** | maxLength, pattern, required | kjui only |

### Platform-specific Attribute Counts

| Tool | Count | Notes |
|------|-------|-------|
| sjui_tools | 38 | iOS-specific + React-specific |
| kjui_tools | 136 | Most comprehensive (iOS + Android + React) |
| rjui_tools | 51 | iOS-specific + React-specific |

### Usage

Each tool links to this shared file via symlink:
```
sjui_tools/lib/core/attribute_definitions.json -> ../../../shared/core/attribute_definitions.json
kjui_tools/lib/core/attribute_definitions.json -> ../../../shared/core/attribute_definitions.json
rjui_tools/lib/core/attribute_definitions.json -> ../../../shared/core/attribute_definitions.json
```
