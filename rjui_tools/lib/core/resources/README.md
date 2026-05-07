# ReactJsonUI Resources

This directory contains resource managers for ReactJsonUI.

## ColorManager

The ColorManager automatically extracts color values from JSON layout files and manages them in a centralized `colors.json` file.

### Features

1. **Automatic Color Extraction**: Extracts hex color values (#FF0000, #F00, etc.) from JSON layouts
2. **Color Key Generation**: Generates descriptive keys based on color values (e.g., "light_red", "dark_blue")
3. **Binding Expression Support**: Skips @{...} binding expressions without logging
4. **TypeScript/JavaScript Code Generation**: Generates ColorManager.js with typed accessors

### Usage

#### 1. Build Command Integration

ColorManager is automatically invoked when you run `rjui build`:

```bash
rjui build
```

This will:
- Scan all JSON layout files
- Extract hex colors and replace them with keys
- Generate/update `Resources/colors.json`
- Generate `src/generated/ColorManager.js`

#### 2. Generated Files

**Resources/colors.json**
```json
{
  "light_red": "#FF0000",
  "dark_blue": "#0000AA",
  "white": "#FFFFFF"
}
```

**Resources/defined_colors.json** (for undefined color keys)
```json
{
  "custom_primary": null,
  "brand_color": null
}
```

**src/generated/ColorManager.js**
```javascript
"use client";

const colorsData = {
  "light_red": "#FF0000",
  "dark_blue": "#0000AA"
};

class ColorManagerClass {
  // Returns undefined for @{...} bindings without logging
  color(key) { ... }

  // Static accessors (camelCase)
  get lightRed() { return "#FF0000"; }
  get darkBlue() { return "#0000AA"; }
}

export const ColorManager = new ColorManagerClass();
```

#### 3. JSON Layout Example

**Before:**
```json
{
  "type": "View",
  "background": "#FF0000",
  "child": [
    {
      "type": "Label",
      "fontColor": "#0000AA",
      "text": "Hello"
    }
  ]
}
```

**After (automatically updated):**
```json
{
  "type": "View",
  "background": "light_red",
  "child": [
    {
      "type": "Label",
      "fontColor": "dark_blue",
      "text": "Hello"
    }
  ]
}
```

#### 4. React Component Usage

```javascript
import { ColorManager } from './generated/ColorManager';

// Method 1: Using color() method
const bgColor = ColorManager.color('light_red'); // "#FF0000"

// Method 2: Using static accessors
const textColor = ColorManager.lightRed; // "#FF0000"

// Binding expressions return undefined without logging
const bindingColor = ColorManager.color('@{vm.color}'); // undefined (no console warning)

// Unknown keys log a warning
const unknown = ColorManager.color('unknown_key'); // undefined (console warning)

// Get all available colors
const allColors = ColorManager.availableColors; // ['light_red', 'dark_blue']
```

#### 5. Binding Expressions

ColorManager automatically skips binding expressions:

```json
{
  "type": "View",
  "background": "@{viewModel.backgroundColor}"
}
```

When this is processed:
- The binding `@{viewModel.backgroundColor}` remains unchanged
- `ColorManager.color('@{viewModel.backgroundColor}')` returns `undefined` without logging
- No warnings or errors are generated

### Color Properties

ColorManager recognizes the following color properties:

- `background`
- `tapBackground`
- `borderColor`
- `fontColor`
- `textColor`
- `hintColor`
- `shadowColor`
- `tintColor`
- `selectedColor`
- `unselectedColor`
- `backgroundColor`
- `strokeColor`
- `overlayColor`
- `caretColor`
- `disabledBackground`

### Color Key Naming

ColorManager generates descriptive keys based on RGB values:

| Color | Generated Key |
|-------|---------------|
| #FFFFFF | white |
| #000000 | black |
| #FF0000 | light_red |
| #AA0000 | dark_red |
| #00FF00 | light_green |
| #0000FF | light_blue |
| #808080 | medium_gray |

If duplicate keys exist, a numeric suffix is added (e.g., `light_red_2`).

### Configuration

Add to `rjui.config.json`:

```json
{
  "layouts_directory": "src/Layouts",
  "generated_directory": "src/generated",
  "resources_directory": "Resources"
}
```

### API Reference

#### ColorManager.color(key: string): string | undefined

Get color value by key.

- Returns hex color string if key exists
- Returns `undefined` for binding expressions (no logging)
- Returns hex string if key is already a hex color
- Logs warning and returns `undefined` for unknown keys

#### ColorManager.isHexColor(value: string): boolean

Check if a string is a valid hex color.

#### ColorManager.availableColors: string[]

Get array of all available color keys.

#### ColorManager.{colorKey} (getter)

Static accessor for each color (camelCase).

Example: `ColorManager.primaryBlue` for color key `primary_blue`.

### Cross-Platform Compatibility

ColorManager follows the same conventions as SwiftJsonUI and KotlinJsonUI:

- Same JSON schema for colors.json
- Same color property names
- Same binding expression handling
- Consistent color key generation algorithm

This ensures that the same JSON layout files work across all platforms.
