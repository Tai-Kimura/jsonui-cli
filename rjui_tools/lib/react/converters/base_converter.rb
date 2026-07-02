# frozen_string_literal: true

require_relative '../tailwind_mapper'
require_relative '../responsive_helper'
require_relative '../helpers/string_manager_helper'
require_relative '../helpers/font_spec_helper'

module RjuiTools
  module React
    module Converters
      class BaseConverter
        include Helpers::StringManagerHelper

        attr_reader :json, :config

        def initialize(json, config)
          @json = json
          @config = config
          @use_tailwind = config['use_tailwind'] != false
          @responsive_result = nil
        end

        def convert(indent = 2)
          raise NotImplementedError, 'Subclasses must implement convert method'
        end

        protected

        def build_class_name
          classes = []
          @dynamic_styles = {}

          # Compute responsive info up front so we know which keys are overridden
          @responsive_result = ResponsiveHelper.build_responsive(json)

          # Overlay child (absolute positioning within parent)
          if json['_overlay']
            classes << 'absolute'
            classes << overlay_position_classes
          end

          # Width/Height - handle matchParent with horizontal margin
          left_margin = json['leftMargin'] || json['startMargin'] || 0
          right_margin = json['rightMargin'] || json['endMargin'] || 0
          has_horizontal_margin = left_margin.is_a?(Numeric) && left_margin > 0 ||
                                  right_margin.is_a?(Numeric) && right_margin > 0

          if json['width'] == 'matchParent' && has_horizontal_margin
            # Use calc to account for margins
            total_margin = (left_margin.is_a?(Numeric) ? left_margin : 0) +
                          (right_margin.is_a?(Numeric) ? right_margin : 0)
            @dynamic_styles['width'] = "'calc(100% - #{total_margin}px)'"
          else
            classes << TailwindMapper.map_width(json['width'])
          end
          # matchParent height handling (axis-aware):
          # - ZStack child (absolute): use h-full — flex-1 doesn't apply
          # - flex-row parent (height is CROSS axis): use self-stretch —
          #   flex-1 would grow the main (horizontal) axis and hijack width
          #   from fixed-size siblings like a 3px accent bar
          # - flex-col parent or unknown (height is MAIN axis): use flex-1 —
          #   h-full overflows when siblings exist, flex-1 fills the gap
          if json['height'] == 'matchParent' && !json['weight']
            if json['_overlay']
              classes << 'h-full'
            elsif json['_parent_orientation'] == 'horizontal'
              classes << 'self-stretch'
            else
              # Pair flex-1 with min-w-0 / min-h-0 for the same reason
              # TailwindMapper.map_flex_grow does it for weight-bearing
              # siblings: the CSS default `min-*-size: auto` lets long
              # descendants (long <pre>, prose) push the flex container
              # past its intended main-axis slice.
              classes << 'flex-1 min-w-0 min-h-0'
            end
          else
            classes << TailwindMapper.map_height(json['height'])
          end

          # Prevent flex shrinking when fixed dimensions are specified
          # This ensures elements maintain their specified size in flex containers
          if json['width'].is_a?(Numeric) || json['height'].is_a?(Numeric)
            classes << 'shrink-0'
          end

          # Min/Max Width/Height constraints
          # Skip when the component has claimed the same key as a semantic
          # prop via attribute_definitions/<Component>.json — otherwise the
          # wrapper <div> steals keys like CodeBlock#maxHeight that the
          # custom component uses for its own purpose.
          classes << TailwindMapper.map_min_width(json['minWidth'])   if json['minWidth']   && decoration_allowed?('minWidth')
          classes << TailwindMapper.map_max_width(json['maxWidth'])   if json['maxWidth']   && decoration_allowed?('maxWidth')
          classes << TailwindMapper.map_min_height(json['minHeight']) if json['minHeight'] && decoration_allowed?('minHeight')
          classes << TailwindMapper.map_max_height(json['maxHeight']) if json['maxHeight'] && decoration_allowed?('maxHeight')

          # Padding (array format)
          classes << TailwindMapper.map_padding(json['padding'] || json['paddings'])

          # Individual paddings (topPadding, bottomPadding, leftPadding, rightPadding)
          # Also support paddingTop, paddingRight, paddingBottom, paddingLeft format
          classes << TailwindMapper.map_individual_paddings(
            json['topPadding'] || json['paddingTop'],
            json['rightPadding'] || json['paddingRight'],
            json['bottomPadding'] || json['paddingBottom'],
            json['leftPadding'] || json['paddingLeft']
          )

          # RTL-aware paddings (paddingStart, paddingEnd)
          classes << TailwindMapper.map_rtl_paddings(
            json['paddingStart'],
            json['paddingEnd']
          )

          # Insets (alternative padding format)
          classes << TailwindMapper.map_insets(json['insets']) if json['insets']
          classes << TailwindMapper.map_inset_horizontal(json['insetHorizontal']) if json['insetHorizontal']

          # Margin (array format)
          classes << TailwindMapper.map_margin(json['margins'])

          # Individual margins (topMargin, bottomMargin, leftMargin, rightMargin)
          classes << TailwindMapper.map_individual_margins(
            json['topMargin'],
            json['rightMargin'],
            json['bottomMargin'],
            json['leftMargin']
          )

          # RTL-aware margins (startMargin, endMargin)
          classes << TailwindMapper.map_rtl_margins(
            json['startMargin'],
            json['endMargin']
          )

          # Background - check for dynamic binding or gradient
          if json['background']
            if has_binding?(json['background'])
              @dynamic_styles['backgroundColor'] = convert_binding(json['background'])
            elsif json['background'].to_s.include?('gradient')
              # CSS gradients must be inline styles
              @dynamic_styles['background'] = "'#{json['background']}'"
            else
              classes << TailwindMapper.map_color(json['background'], 'bg')
            end
          end

          # Corner radius
          classes << TailwindMapper.map_corner_radius(json['cornerRadius']) if json['cornerRadius']

          # Text color - check for dynamic binding
          if json['fontColor']
            if has_binding?(json['fontColor'])
              @dynamic_styles['color'] = convert_binding(json['fontColor'])
            else
              classes << TailwindMapper.map_color(json['fontColor'], 'text')
            end
          end

          # Font handling.
          #
          # When `fontFamily` is set, the entire font spec (family / weight /
          # size / italic) routes through `Configuration.Font.resolve(...)`
          # so the host-supplied fontProvider can return its own
          # React.CSSProperties chunk; the matching Tailwind weight/size
          # classes are intentionally dropped in that branch — emitting both
          # is redundant since CSS specificity makes inline style win, and
          # keeping a single source of truth (the resolved style) avoids
          # surprising overlay behavior.
          #
          # When `fontFamily` is absent, the legacy class-based behavior is
          # preserved: weight-name `font` strings map to font-* classes,
          # numeric/static `fontSize` maps to text-* classes, and bindings
          # spill into `@dynamic_styles` as before.
          font_family_attr   = json['fontFamily']
          font_attr          = json['font']
          font_size_attr     = json['fontSize']
          font_weight_attr   = json['fontWeight']

          if font_family_attr
            # Pick the weight-bearing string for the FontSpec. fontWeight
            # wins over `font` so explicit weight overrides a polymorphic
            # `font` (which can carry weight names too).
            spec_weight = font_weight_attr || font_attr
            spec_weight = nil if spec_weight.is_a?(String) && has_binding?(spec_weight)

            spec_size = font_size_attr.is_a?(Numeric) ? font_size_attr : nil

            spread = Helpers::FontSpecHelper.build_resolve_spread(
              family: font_family_attr,
              weight: spec_weight,
              size:   spec_size,
              italic: false
            )
            if spread
              # Sentinel key — `format_dynamic_style_pair` renders this as
              # `...<value>` (a JS spread) rather than `key: value`.
              @dynamic_styles['__SPREAD__font'] = spread
            end

            # Bindings still need a regular CSS prop entry so the runtime
            # value can update; the provider only sees the static spec.
            if font_size_attr && !font_size_attr.is_a?(Numeric) && has_binding?(font_size_attr.to_s)
              @dynamic_styles['fontSize'] = convert_binding(font_size_attr.to_s)
            end
            if font_weight_attr.is_a?(String) && has_binding?(font_weight_attr)
              @dynamic_styles['fontWeight'] = convert_binding(font_weight_attr)
            end
          else
            # Font size
            classes << TailwindMapper.map_font_size(font_size_attr) if font_size_attr

            # Font - can be weight name (bold, semibold) or font family alias (monospace).
            # TailwindMapper.map_font already discriminates between the two.
            if font_attr
              font_class = TailwindMapper.map_font(font_attr)
              classes << font_class if font_class && !font_class.empty?
            end

            # Font weight (fontWeight attribute takes precedence if both specified)
            if font_weight_attr
              if has_binding?(font_weight_attr)
                @dynamic_styles['fontWeight'] = convert_binding(font_weight_attr)
              else
                classes << TailwindMapper.map_font_weight(font_weight_attr)
              end
            end
          end

          # Text align
          classes << TailwindMapper.map_text_align(json['textAlign'])

          # Orientation (flex)
          classes << TailwindMapper.map_orientation(json['orientation'])

          # Shadow
          classes << TailwindMapper.map_shadow(json['shadow']) if json['shadow']

          # Border
          if json['borderWidth'] || json['borderColor'] || json['borderStyle']
            border_width_binding = json['borderWidth'] && has_binding?(json['borderWidth'])
            border_color_binding = json['borderColor'] && has_binding?(json['borderColor'])
            border_style_binding = json['borderStyle'] && has_binding?(json['borderStyle'])

            if border_width_binding || border_color_binding || border_style_binding
              # Dynamic border - use inline styles
              if border_width_binding
                prop = convert_binding(json['borderWidth']).gsub(/[{}]/, '')
                @dynamic_styles['borderWidth'] = "`${#{prop}}px`"
              elsif json['borderWidth']
                @dynamic_styles['borderWidth'] = "'#{json['borderWidth']}px'"
              end
              if border_color_binding
                @dynamic_styles['borderColor'] = convert_binding(json['borderColor'])
              elsif json['borderColor']
                @dynamic_styles['borderColor'] = "'#{json['borderColor']}'"
              end
              if border_style_binding
                @dynamic_styles['borderStyle'] = convert_binding(json['borderStyle'])
              end
              classes << 'border-solid' unless json['borderStyle']
            else
              classes << TailwindMapper.map_border(json['borderWidth'], json['borderColor'], json['borderStyle'])
            end
          end

          # Opacity/Alpha
          opacity = json['opacity'] || json['alpha']
          if opacity
            if has_binding?(opacity.to_s)
              @dynamic_styles['opacity'] = convert_binding(opacity.to_s)
            elsif opacity.is_a?(Numeric) && opacity < 1
              classes << TailwindMapper.map_opacity(opacity)
            end
          end

          # Visibility (hidden attribute - static)
          classes << TailwindMapper.map_visibility(json['hidden']) if json['hidden']

          # Visibility attribute (supports data binding)
          # If it's a binding, we'll handle it with conditional render/class
          # (see wrap_with_visibility). Static values map to Tailwind:
          #   "gone"      -> hidden    (display:none, removed from layout)
          #   "invisible" -> invisible (visibility:hidden, keeps its space)
          #   "visible"   -> no class
          if json['visibility'] && !has_binding?(json['visibility'])
            case json['visibility']
            when 'gone'
              classes << 'hidden'
            when 'invisible'
              classes << 'invisible'
            end
          end

          # Disabled state
          if json['enabled'] == false
            classes << 'opacity-50'
            classes << 'pointer-events-none'
          end

          # User interaction enabled
          if json['userInteractionEnabled'] == false
            classes << 'pointer-events-none'
          end

          # Clip to bounds
          classes << TailwindMapper.map_overflow(json['clipToBounds']) if json['clipToBounds']

          # Z-index
          classes << TailwindMapper.map_z_index(json['zIndex']) if json['zIndex']

          # Flex grow (weight)
          classes << TailwindMapper.map_flex_grow(json['weight']) if json['weight']

          # Self-centering (for non-View elements like Image, Label)
          # centerHorizontal: center this element horizontally within parent
          # centerVertical: center this element vertically within parent
          classes << 'mx-auto' if json['centerHorizontal']
          classes << 'my-auto' if json['centerVertical']
          if json['centerInParent']
            classes << 'mx-auto'
            classes << 'my-auto'
          end

          # Gravity alignment - pass orientation for correct flexbox mapping
          classes.concat(TailwindMapper.map_gravity(json['gravity'], json['orientation'])) if json['gravity']

          # Direction (RTL/LTR)
          classes << TailwindMapper.map_direction(json['direction']) if json['direction']

          # Additional className from JSON
          classes << json['className'] if json['className']

          # Offset (position adjustment) - handled as dynamic style
          if json['offsetX'] || json['offsetY']
            offset_x = json['offsetX'] || 0
            offset_y = json['offsetY'] || 0
            @dynamic_styles['transform'] = "'translate(#{offset_x}px, #{offset_y}px)'"
          end

          # Tint color (accent color for interactive elements)
          if json['tintColor']
            @dynamic_styles['accentColor'] = "'#{json['tintColor']}'"
          end

          # Append responsive Tailwind classes (breakpoint-prefixed overrides)
          if @responsive_result && !@responsive_result[:classes].empty?
            classes.concat(@responsive_result[:classes])
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        def has_binding?(value)
          value.is_a?(String) && value.include?('@{')
        end

        # Keys that BaseConverter#build_class_name may emit as Tailwind
        # decoration but a custom component might plausibly want to reclaim
        # as a semantic prop. Currently scoped to size constraints — the
        # other decoration keys (width/height/padding/etc.) have no real
        # reason to be reclaimed, and making them overridable would break
        # existing layouts.
        DECORATION_KEYS_OVERRIDABLE = %w[minWidth maxWidth minHeight maxHeight].freeze

        # Is `key` allowed to be consumed as a Tailwind decoration on this
        # component? Returns false only when the component type has an entry
        # for `key` in its attribute_definitions JSON — i.e. the component
        # author claimed this key as a semantic prop.
        def decoration_allowed?(key)
          return true unless DECORATION_KEYS_OVERRIDABLE.include?(key)
          !component_claims_prop?(key)
        end

        def component_claims_prop?(key)
          type = json['type']
          return false unless type
          defs = @config && @config.dig('_attribute_definitions', type)
          defs.is_a?(Hash) && defs.key?(key)
        end

        def build_style_attr
          return '' if @dynamic_styles.nil? || @dynamic_styles.empty?

          style_pairs = @dynamic_styles.map do |key, value|
            format_dynamic_style_pair(key, value)
          end

          " style={{ #{style_pairs.join(', ')} }}"
        end

        # Render a single (key, value) entry from `@dynamic_styles` as a JSX
        # object-literal fragment. Sentinel keys with the SPREAD prefix
        # (currently emitted by the FontSpec routing in `build_class_name`)
        # render as `...<value>` so `Configuration.Font.resolve(spec)` is
        # spread into the inline `style={{ ... }}` attribute.
        def format_dynamic_style_pair(key, value)
          if key.to_s.start_with?(Helpers::FontSpecHelper::SPREAD_KEY_PREFIX)
            return value.to_s
          end

          # Remove braces from the value since we're inside a JSX expression
          clean_value = value.gsub(/^\{|\}$/, '')
          # CSS custom properties (starting with --) need to be quoted in JSX
          key_str = key.start_with?('--') ? "'#{key}'" : key
          "#{key_str}: #{clean_value}"
        end

        # Build className attribute, handling landscape responsive with template literal.
        # Returns the full className="..." or className={`...`} string.
        def build_responsive_class_attr(static_classes)
          if @responsive_result && @responsive_result[:needs_landscape_hook] &&
             !@responsive_result[:landscape_styles].empty?
            landscape_expr = ResponsiveHelper.build_landscape_class_expression(
              @responsive_result[:landscape_styles]
            )
            unless landscape_expr.empty?
              return " className={`#{static_classes} #{landscape_expr}`}"
            end
          end

          " className=\"#{static_classes}\""
        end

        # Check if this component needs the useMediaQuery hook for landscape
        def needs_landscape_hook?
          @responsive_result&.dig(:needs_landscape_hook) == true
        end

        def convert_children(indent)
          # Support both 'children' and 'child' keys
          child_data = json['children'] || json['child']
          return '' unless child_data

          # Normalize to array (support both single object and array)
          child_array = child_data.is_a?(Array) ? child_data : [child_data]

          # Propagate parent orientation so children know whether their own
          # `height: matchParent` / `width: matchParent` is a main-axis or
          # cross-axis instruction. Same pattern as `_overlay` injection in
          # ViewConverter.
          parent_orientation = json['orientation']

          child_array.filter_map do |child|
            # Skip data-only elements (they define props, not rendered content)
            next nil if data_only_element?(child)

            annotated = parent_orientation ? child.merge('_parent_orientation' => parent_orientation) : child
            converter = create_converter_for_child(annotated)
            converter.convert(indent + 2)
          end.join("\n")
        end

        # Check if a child element is a data-only element (should not be rendered)
        # Data-only element: { "data": [...] } with only the data key
        def data_only_element?(child)
          return false unless child.is_a?(Hash)
          child.keys == ['data'] && child['data'].is_a?(Array)
        end

        def create_converter_for_child(child)
          # Check if this is an include component
          if child['include']
            require_relative 'include_converter'
            return IncludeConverter.new(child, config)
          end

          # Apply style if specified
          resolved_child = apply_style(child)

          converter_class = get_converter_class(resolved_child['type'])
          converter_class.new(resolved_child, config)
        end

        def apply_style(child)
          return child unless child['style']

          style_name = child['style']
          style_data = load_style(style_name)
          return child unless style_data

          # Merge style with child (child attributes override style)
          merged = style_data.merge(child)
          merged.delete('style')
          merged
        end

        def load_style(style_name)
          styles_dir = config['styles_directory'] || 'src/Styles'
          style_path = File.join(styles_dir, "#{style_name}.json")

          return nil unless File.exist?(style_path)

          JSON.parse(File.read(style_path))
        rescue JSON::ParserError
          nil
        end

        def get_converter_class(type)
          # First check extension converters
          extension_converters = config['_extension_converters'] || {}
          return extension_converters[type] if extension_converters[type]

          require_relative 'view_converter'
          require_relative 'label_converter'
          require_relative 'button_converter'
          require_relative 'image_converter'
          require_relative 'text_field_converter'
          require_relative 'text_view_converter'
          require_relative 'scroll_view_converter'
          require_relative 'collection_converter'
          require_relative 'toggle_converter'
          require_relative 'slider_converter'
          require_relative 'segment_converter'
          require_relative 'radio_converter'
          require_relative 'progress_converter'
          require_relative 'indicator_converter'
          require_relative 'select_box_converter'
          require_relative 'include_converter'
          require_relative 'icon_label_converter'
          require_relative 'gradient_view_converter'
          require_relative 'blur_converter'
          require_relative 'circle_view_converter'
          require_relative 'web_converter'
          require_relative 'switch_converter'
          require_relative 'network_image_converter'
          require_relative 'tab_view_converter'

          {
            'View' => ViewConverter,
            'SafeAreaView' => ViewConverter,
            'Label' => LabelConverter,
            'Text' => LabelConverter,
            'Button' => ButtonConverter,
            'Image' => ImageConverter,
            'CircleImage' => ImageConverter,
            'NetworkImage' => NetworkImageConverter,
            'TextField' => TextFieldConverter,
            # EditText / Input are aliases for TextField (attribute_definitions
            # `_alias_of: TextField`)
            'EditText' => TextFieldConverter,
            'Input' => TextFieldConverter,
            'TextView' => TextViewConverter,
            'Scroll' => ScrollViewConverter,
            'ScrollView' => ScrollViewConverter,
            'Collection' => CollectionConverter,
            'Table' => CollectionConverter,
            'Switch' => SwitchConverter,
            'Toggle' => ToggleConverter,
            'CheckBox' => ToggleConverter,
            'Check' => ToggleConverter,
            'Checkbox' => ToggleConverter,
            'Slider' => SliderConverter,
            'Segment' => SegmentConverter,
            'Radio' => RadioConverter,
            'Progress' => ProgressConverter,
            'Indicator' => IndicatorConverter,
            'SelectBox' => SelectBoxConverter,
            'Include' => IncludeConverter,
            'IconLabel' => IconLabelConverter,
            'GradientView' => GradientViewConverter,
            'Blur' => BlurConverter,
            'CircleView' => CircleViewConverter,
            'Web' => WebConverter,
            'TabView' => TabViewConverter,
            'Embed' => EmbedConverter
          }[type] || ViewConverter
        end

        def indent_str(indent)
          ' ' * indent
        end

        def convert_binding(value)
          return value unless value.is_a?(String)

          # Check if it's a snake_case string key for StringManager.
          # `convert_string_key` returns nil when the key isn't registered
          # in strings.json — we fall through to binding / literal handling
          # so identifiers like "bash" / "yaml" stay as-is instead of
          # turning into dangling StringManager references.
          if (resolved = convert_string_key(value))
            return resolved
          end

          # Check if it's a binding expression @{propName} or @{prop.name}
          if value.match?(/@\{[^}]+\}/)
            # Convert @{propName} to {viewModel.data.propName}
            # All properties are converted to viewModel.data.xxx format
            converted = value.gsub(/@\{([^}]+)\}/) do |_match|
              prop = $1
              "{#{add_viewmodel_data_prefix(prop)}}"
            end
            # Also escape any remaining literal braces (not part of binding expressions)
            return escape_jsx_braces_with_bindings(converted)
          end

          # Convert newlines to <br /> and escape JSX braces
          convert_text_with_newlines(value)
        end

        # Convert text with newline characters to JSX with <br /> tags
        def convert_text_with_newlines(value)
          return value unless value.is_a?(String)

          # If text contains newlines, convert to JSX fragment with <br /> tags
          if value.include?("\n")
            parts = value.split("\n")
            # Build JSX expression: <>line1<br />line2<br />line3</>
            jsx_parts = parts.map.with_index do |part, i|
              escaped_part = escape_text_for_jsx(part)
              i < parts.length - 1 ? "#{escaped_part}<br />" : escaped_part
            end
            return "<>#{jsx_parts.join('')}</>"
          end

          # Escape { and } in plain text for JSX (must be wrapped as JSX expressions)
          escape_jsx_braces(value)
        end

        # Escape special characters in text for JSX (without wrapping)
        def escape_text_for_jsx(text)
          return text unless text.is_a?(String)
          # Escape if text contains braces or single quotes
          return text unless text.include?('{') || text.include?('}') || text.include?("'")

          # Wrap text containing special characters in JSX expression
          escaped = text.gsub('`', '\\`').gsub('${', '\\${')
          "{`#{escaped}`}"
        end

        def escape_jsx_braces_with_bindings(value)
          # For text that has both JSX expressions {binding} and literal braces,
          # we need to handle them differently
          return value unless value.is_a?(String)

          # If the text contains literal { or } that aren't part of JSX expressions,
          # wrap in template literal
          # Check if text starts with { and is likely JSON (not a binding)
          if value.start_with?('{') && !value.match?(/^\{[a-zA-Z]/)
            # Likely JSON code block, wrap in template literal
            escaped = value.gsub('`', '\\`').gsub('${', '\\${')
            return "{`#{escaped}`}"
          end

          value
        end

        def escape_jsx_braces(value)
          return value unless value.is_a?(String)
          # Escape if text contains braces or single quotes (which can break JSX attributes)
          return value unless value.include?('{') || value.include?('}') || value.include?("'")

          # For text containing special characters, wrap entire string in JSX expression with template literal
          escaped = value.gsub('`', '\\`').gsub('${', '\\${')
          "{`#{escaped}`}"
        end

        def extract_id
          json['id'] || json['propertyName']
        end

        # Build the DOM id="..." attribute. Converters should use this instead
        # of inlining `" id=\"#{extract_id}\""` so that `id: "@{field}"`
        # bindings in cell layouts resolve to a JSX expression rather than
        # being emitted as the literal string `"@{field}"`.
        #
        # Returns:
        #   ""                         when no id
        #   " id=\"my_root\""         for a literal id
        #   " id={String(data.foo)}"  for an @{foo} binding
        def build_id_attr
          id_value = extract_id
          return '' unless id_value

          if has_binding?(id_value.to_s)
            prop = id_value.to_s.gsub(/@\{|\}/, '')
            " id={String(#{add_viewmodel_data_prefix(prop)})}"
          else
            " id=\"#{id_value}\""
          end
        end

        # Build aria-disabled for wrapper elements (div/label) whose inner
        # <input> carries the real `disabled` attribute. The layout `id` is
        # emitted on the wrapper, so the wrapper must reflect the disabled
        # state for accessibility and element-level testability.
        def build_aria_disabled_attr
          enabled = json['enabled']
          return '' if enabled.nil?

          if has_binding?(enabled)
            " aria-disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' aria-disabled="true"'
          else
            ''
          end
        end

        # Build data-testid attribute for testing
        def build_testid_attr
          test_id = json['testId']
          return '' unless test_id
          " data-testid=\"#{test_id}\""
        end

        # Build tag attribute (as data-tag for reference)
        def build_tag_attr
          tag = json['tag']
          return '' unless tag
          " data-tag=\"#{tag}\""
        end

        # Build onClick attribute
        # Rules:
        # - onClick (camelCase) -> binding format only (@{functionName})
        # - onclick (lowercase) -> selector format only (string)
        # - { "action": "link", "url": "..." } -> opens URL in new tab
        def build_onclick_attr
          # Check onClick (camelCase) first - binding format only
          if json['onClick']
            handler = json['onClick']
            if handler.is_a?(Hash)
              # Action object: { "action": "link", "url": "..." }
              if handler['action'] == 'link' && handler['url']
                url = handler['url']
                return " onClick={() => window.open('#{url}', '_blank')}"
              else
                return ''
              end
            elsif is_binding_format?(handler)
              # Valid binding: @{handleClick} -> viewModel.data.handleClick
              prop = handler.gsub(/@\{|\}/, '')
              return " onClick={#{add_viewmodel_data_prefix(prop)}}"
            else
              # ERROR: onClick (camelCase) must use binding format
              return " {/* ERROR: onClick requires binding format @{functionName} */}"
            end
          end

          # Check onclick (lowercase) - selector format only
          if json['onclick']
            handler = json['onclick']
            if is_binding_format?(handler)
              # ERROR: onclick (lowercase) must use selector format
              return " {/* ERROR: onclick requires selector format (string) */}"
            else
              # Valid selector: functionName -> data.functionName
              return " onClick={data.#{handler}}"
            end
          end

          ''
        end

        # Check if value is binding format (@{...})
        def is_binding_format?(value)
          value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
        end

        # Extract property from binding format
        def extract_binding_value(value)
          return nil unless is_binding_format?(value)
          value[2...-1]
        end

        # Extract binding property and add viewModel.data. prefix
        # This is the main method converters should use for binding values
        def extract_binding_property(value)
          prop = extract_binding_value(value)
          add_viewmodel_data_prefix(prop)
        end

        # Extract raw binding value without prefix (for internal use or special cases)
        def extract_raw_binding_property(value)
          extract_binding_value(value)
        end

        # Determine absolute position classes based on align attributes for overlay children
        def overlay_position_classes
          has_align = json['centerInParent'] || json['centerVertical'] || json['centerHorizontal'] ||
                      json['alignTop'] || json['alignBottom'] || json['alignLeft'] || json['alignRight']

          unless has_align
            return 'inset-0'
          end

          classes = []

          if json['centerInParent']
            classes << 'top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2'
          else
            # Vertical
            if json['centerVertical']
              classes << 'top-1/2 -translate-y-1/2'
            elsif json['alignBottom']
              classes << 'bottom-0'
            elsif json['alignTop']
              classes << 'top-0'
            end

            # Horizontal
            if json['centerHorizontal']
              classes << 'left-1/2 -translate-x-1/2'
            elsif json['alignRight']
              classes << 'right-0'
            elsif json['alignLeft']
              classes << 'left-0'
            end
          end

          classes.join(' ')
        end

        # Add data. prefix to a property name for binding expressions
        # All properties are converted to data.xxx format
        def add_viewmodel_data_prefix(prop)
          if prop.start_with?('data.')
            # Already has data. prefix, use as-is
            prop
          elsif prop.start_with?('viewModel.data.')
            # viewModel.data.xxx -> data.xxx
            prop.sub('viewModel.data.', 'data.')
          elsif prop.start_with?('viewModel.')
            # viewModel.xxx -> data.xxx
            "data.#{prop.sub('viewModel.', '')}"
          else
            # Add data. prefix for data properties
            "data.#{prop}"
          end
        end

        # Build visibility binding for conditional rendering
        # Only supports simple property binding like "@{isVisible}" - no ternary operators
        # Returns: { type: :gone/:invisible, condition: "..." } or nil
        def build_visibility_info
          visibility = json['visibility']
          return nil unless visibility && has_binding?(visibility)

          binding_expr = visibility.gsub(/@\{|\}/, '')

          # Only support simple property binding (no ternary operators / business logic)
          if binding_expr =~ /^[\w.]+$/
            { condition: add_viewmodel_data_prefix(binding_expr) }
          else
            nil
          end
        end

        # Wrap JSX with visibility condition (conditional render)
        # "gone" → removes from DOM, "invisible" → hidden but keeps space
        def wrap_with_visibility(jsx, indent)
          vis_info = build_visibility_info
          return jsx unless vis_info

          cond = vis_info[:condition]

          # Replace className="..." with dynamic className that adds invisible style
          invisible_jsx = inject_invisible_class(jsx, cond)

          <<~JSX.chomp
            #{indent_str(indent)}{#{cond} !== "gone" && (
            #{invisible_jsx}
            #{indent_str(indent)})}
          JSX
        end

        # Inject invisible class into JSX when visibility === "invisible"
        def inject_invisible_class(jsx, condition)
          invisible_expr = "${#{condition} === \"invisible\" ? \"invisible\" : \"\"}"

          # Case 1: className={`...`} (template literal)
          result = jsx.sub(/className=\{`([^`]*)`\}/) do
            "className={`#{$1} #{invisible_expr}`}"
          end
          return result if result != jsx

          # Case 2: className="..." (static string)
          jsx.sub(/className="([^"]*)"/) do
            "className={`#{$1} #{invisible_expr}`}"
          end
        end

        # Get default value from config
        def defaults(component_type = nil)
          return {} unless config['defaults']

          if component_type
            config['defaults'][component_type] || {}
          else
            config['defaults']
          end
        end

        # Get value with fallback to default
        def get_value(key, component_type = nil)
          json[key] || defaults(component_type)[key]
        end
      end
    end
  end
end
