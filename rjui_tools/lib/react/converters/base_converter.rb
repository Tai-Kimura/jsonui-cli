# frozen_string_literal: true

require_relative '../../core/typed_attributes'
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

        # Typed attribute access backed by the generated extraction tables
        # (lib/core/generated/attributes/, emitted from
        # attribute_definitions.json). Converters read node attributes as
        # `attributes['key']` — canonical/alias resolution and type
        # coercion happen in one place instead of per-call-site raw JSON
        # reads. See Core::TypedAttributes for semantics.
        def attributes
          @attributes ||= Core::TypedAttributes.new(
            json,
            component_type: json['type'] || fallback_component_type,
            normalized: layout_normalized?
          )
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
          left_margin = attributes['leftMargin'] || attributes['startMargin'] || 0
          right_margin = attributes['rightMargin'] || attributes['endMargin'] || 0
          has_horizontal_margin = left_margin.is_a?(Numeric) && left_margin > 0 ||
                                  right_margin.is_a?(Numeric) && right_margin > 0

          if attributes['width'] == 'matchParent' && has_horizontal_margin
            # Use calc to account for margins
            total_margin = (left_margin.is_a?(Numeric) ? left_margin : 0) +
                          (right_margin.is_a?(Numeric) ? right_margin : 0)
            @dynamic_styles['width'] = "'calc(100% - #{total_margin}px)'"
          else
            classes << TailwindMapper.map_width(attributes['width'])
          end
          # matchParent height handling (axis-aware):
          # - ZStack child (absolute): use h-full — flex-1 doesn't apply
          # - flex-row parent (height is CROSS axis): use self-stretch —
          #   flex-1 would grow the main (horizontal) axis and hijack width
          #   from fixed-size siblings like a 3px accent bar
          # - flex-col parent or unknown (height is MAIN axis): use flex-1 —
          #   h-full overflows when siblings exist, flex-1 fills the gap
          if attributes['height'] == 'matchParent' && !attributes['weight']
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
            classes << TailwindMapper.map_height(attributes['height'])
          end

          # Prevent flex shrinking when fixed dimensions are specified
          # This ensures elements maintain their specified size in flex containers
          if attributes['width'].is_a?(Numeric) || attributes['height'].is_a?(Numeric)
            classes << 'shrink-0'
          end

          # Min/Max Width/Height constraints
          # Skip when the component has claimed the same key as a semantic
          # prop via attribute_definitions/<Component>.json — otherwise the
          # wrapper <div> steals keys like CodeBlock#maxHeight that the
          # custom component uses for its own purpose.
          classes << TailwindMapper.map_min_width(attributes['minWidth'])   if attributes['minWidth']   && decoration_allowed?('minWidth')
          classes << TailwindMapper.map_max_width(attributes['maxWidth'])   if attributes['maxWidth']   && decoration_allowed?('maxWidth')
          classes << TailwindMapper.map_min_height(attributes['minHeight']) if attributes['minHeight'] && decoration_allowed?('minHeight')
          classes << TailwindMapper.map_max_height(attributes['maxHeight']) if attributes['maxHeight'] && decoration_allowed?('maxHeight')

          # Padding (array format)
          classes << TailwindMapper.map_padding(attributes['padding'] || attributes['paddings'])

          # Individual paddings (topPadding, bottomPadding, leftPadding, rightPadding)
          # Also support paddingTop, paddingRight, paddingBottom, paddingLeft format
          classes << TailwindMapper.map_individual_paddings(
            attributes['topPadding'] || attributes['paddingTop'],
            attributes['rightPadding'] || attributes['paddingRight'],
            attributes['bottomPadding'] || attributes['paddingBottom'],
            attributes['leftPadding'] || attributes['paddingLeft']
          )

          # RTL-aware paddings (paddingStart, paddingEnd)
          classes << TailwindMapper.map_rtl_paddings(
            attributes['paddingStart'],
            attributes['paddingEnd']
          )

          # Insets (alternative padding format)
          classes << TailwindMapper.map_insets(attributes['insets']) if attributes['insets']
          classes << TailwindMapper.map_inset_horizontal(attributes['insetHorizontal']) if attributes['insetHorizontal']

          # Margin (array format)
          classes << TailwindMapper.map_margin(attributes['margins'])

          # Individual margins (topMargin, bottomMargin, leftMargin, rightMargin)
          classes << TailwindMapper.map_individual_margins(
            attributes['topMargin'],
            attributes['rightMargin'],
            attributes['bottomMargin'],
            attributes['leftMargin']
          )

          # RTL-aware margins (startMargin, endMargin)
          classes << TailwindMapper.map_rtl_margins(
            attributes['startMargin'],
            attributes['endMargin']
          )

          # Background - check for dynamic binding or gradient
          if attributes['background']
            if has_binding?(attributes['background'])
              @dynamic_styles['backgroundColor'] = convert_binding(attributes['background'])
            elsif attributes['background'].to_s.include?('gradient')
              # CSS gradients must be inline styles
              @dynamic_styles['background'] = "'#{attributes['background']}'"
            else
              classes << TailwindMapper.map_color(attributes['background'], 'bg')
            end
          end

          # Corner radius
          classes << TailwindMapper.map_corner_radius(attributes['cornerRadius']) if attributes['cornerRadius']

          # Text color - check for dynamic binding
          if attributes['fontColor']
            if has_binding?(attributes['fontColor'])
              @dynamic_styles['color'] = convert_binding(attributes['fontColor'])
            else
              classes << TailwindMapper.map_color(attributes['fontColor'], 'text')
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
          font_family_attr   = attributes['fontFamily']
          font_attr          = attributes['font']
          font_size_attr     = attributes['fontSize']
          font_weight_attr   = attributes['fontWeight']

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
          classes << TailwindMapper.map_text_align(attributes['textAlign'])

          # Orientation (flex)
          classes << TailwindMapper.map_orientation(attributes['orientation'])

          # Shadow
          classes << TailwindMapper.map_shadow(attributes['shadow']) if attributes['shadow']

          # Border
          if attributes['borderWidth'] || attributes['borderColor'] || attributes['borderStyle']
            border_width_binding = attributes['borderWidth'] && has_binding?(attributes['borderWidth'])
            border_color_binding = attributes['borderColor'] && has_binding?(attributes['borderColor'])
            border_style_binding = attributes['borderStyle'] && has_binding?(attributes['borderStyle'])

            if border_width_binding || border_color_binding || border_style_binding
              # Dynamic border - use inline styles
              if border_width_binding
                prop = convert_binding(attributes['borderWidth']).gsub(/[{}]/, '')
                @dynamic_styles['borderWidth'] = "`${#{prop}}px`"
              elsif attributes['borderWidth']
                @dynamic_styles['borderWidth'] = "'#{attributes['borderWidth']}px'"
              end
              if border_color_binding
                @dynamic_styles['borderColor'] = convert_binding(attributes['borderColor'])
              elsif attributes['borderColor']
                @dynamic_styles['borderColor'] = "'#{attributes['borderColor']}'"
              end
              if border_style_binding
                @dynamic_styles['borderStyle'] = convert_binding(attributes['borderStyle'])
              end
              classes << 'border-solid' unless attributes['borderStyle']
            else
              classes << TailwindMapper.map_border(attributes['borderWidth'], attributes['borderColor'], attributes['borderStyle'])
            end
          end

          # Opacity/Alpha (alpha is the definitions alias of opacity;
          # alias + normalized handling is inside TypedAttributes)
          opacity = attributes['opacity']
          if opacity
            if has_binding?(opacity.to_s)
              @dynamic_styles['opacity'] = convert_binding(opacity.to_s)
            elsif opacity.is_a?(Numeric) && opacity < 1
              classes << TailwindMapper.map_opacity(opacity)
            end
          end

          # Visibility (hidden attribute - static). hidden keeps the layout
          # space (Tailwind `invisible`, i.e. visibility:"invisible"
          # shorthand). A binding value is handled as a conditional class in
          # wrap_with_visibility — mapping it here would bake an
          # unconditional `invisible` into the className.
          if attributes['hidden'] && !has_binding?(attributes['hidden'])
            classes << TailwindMapper.map_visibility(attributes['hidden'])
          end

          # Visibility attribute (supports data binding)
          # If it's a binding, we'll handle it with conditional render/class
          # (see wrap_with_visibility). Static values map to Tailwind:
          #   "gone"      -> hidden    (display:none, removed from layout)
          #   "invisible" -> invisible (visibility:hidden, keeps its space)
          #   "visible"   -> no class
          if attributes['visibility'] && !has_binding?(attributes['visibility'])
            case attributes['visibility']
            when 'gone'
              classes << 'hidden'
            when 'invisible'
              classes << 'invisible'
            end
          end

          # Disabled state
          if attributes['enabled'] == false
            classes << 'opacity-50'
            classes << 'pointer-events-none'
          end

          # User interaction enabled
          if attributes['userInteractionEnabled'] == false
            classes << 'pointer-events-none'
          end

          # Clip to bounds
          classes << TailwindMapper.map_overflow(attributes['clipToBounds']) if attributes['clipToBounds']

          # Z-index
          classes << TailwindMapper.map_z_index(attributes['zIndex']) if attributes['zIndex']

          # Flex grow (weight)
          classes << TailwindMapper.map_flex_grow(attributes['weight']) if attributes['weight']

          # Self-centering (for non-View elements like Image, Label)
          # centerHorizontal: center this element horizontally within parent
          # centerVertical: center this element vertically within parent
          classes << 'mx-auto' if attributes['centerHorizontal']
          classes << 'my-auto' if attributes['centerVertical']
          if attributes['centerInParent']
            classes << 'mx-auto'
            classes << 'my-auto'
          end

          # Gravity alignment - pass orientation for correct flexbox mapping
          classes.concat(TailwindMapper.map_gravity(attributes['gravity'], attributes['orientation'])) if attributes['gravity']

          # Direction (RTL/LTR)
          classes << TailwindMapper.map_direction(attributes['direction']) if attributes['direction']

          # Additional className from JSON
          classes << attributes['className'] if attributes['className']

          # Offset (position adjustment) - handled as dynamic style
          if attributes['offsetX'] || attributes['offsetY']
            offset_x = attributes['offsetX'] || 0
            offset_y = attributes['offsetY'] || 0
            @dynamic_styles['transform'] = "'translate(#{offset_x}px, #{offset_y}px)'"
          end

          # Tint color (accent color for interactive elements)
          if attributes['tintColor']
            @dynamic_styles['accentColor'] = "'#{attributes['tintColor']}'"
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

        # Component type for typed attribute extraction when the node
        # itself has no `type` key (e.g. converter driven directly in
        # specs, or a defaulted root). Derived from the converter class
        # name: SliderConverter → 'Slider'. An explicit `type` always
        # wins (SwitchConverter also serves 'Toggle' nodes, etc.).
        def fallback_component_type
          name = self.class.name.to_s.split('::').last
          return nil unless name&.end_with?('Converter')

          name.sub(/Converter\z/, '')
        end

        # True when the layout being generated carried the `$jui` L1
        # normalization marker (see Core::Normalization). Set per file by
        # ReactGenerator#generate through the shared config hash.
        def layout_normalized?
          @config['_layout_normalized'] == true
        end

        # Canonical-first attribute lookup with alias fallback.
        #
        # - The canonical spelling always wins when present (matches the
        #   jui build normalizer semantics).
        # - Alias spellings are consulted only for raw (L0) layouts; an
        #   L1-normalized layout already had aliases rewritten, so the
        #   canonical-only path is taken (aliases are NOT read).
        def attr_lookup(canonical, *aliases)
          value = json[canonical]
          return value unless value.nil?
          return nil if layout_normalized?

          aliases.each do |alias_name|
            value = json[alias_name]
            return value unless value.nil?
          end
          nil
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
          parent_orientation = attributes['orientation']

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

        # TEXT-context binding conversion (Label text and equivalents
        # rendered as JSX children). Canonical textStringification
        # (shared/core/binding_semantics.json) needs bool => "true"/"false"
        # and unresolved => "" — but raw JSX `{data.flag}` renders booleans
        # as NOTHING, so text sinks emit a template literal instead: JS
        # interpolation is exactly canonical (`${true}` => "true",
        # `${5.0}` => "5", `${undefined ?? ""}` => "").
        #
        #   "@{x}"            => {`${data.x ?? ""}`}
        #   "@{x ?? 'Guest'}" => {`${data.x ?? 'Guest'}`}
        #   "Hello @{name}!"  => {`Hello ${data.name ?? ""}!`}
        #
        # strings.json keys still route to StringManager BEFORE binding
        # logic, exactly like convert_binding. Non-text value contexts
        # (visibility conditions, controlled inputs, handler refs, style
        # bindings) must keep using convert_binding / raw references.
        def convert_text_binding(value)
          return value unless value.is_a?(String)

          if (resolved = convert_string_key(value))
            return resolved
          end

          return convert_text_with_newlines(value) unless value.match?(/@\{[^}]+\}/)

          body = value.split(/(@\{[^}]+\})/).map do |part|
            if (inner = part[/\A@\{([^}]+)\}\z/, 1])
              expr = text_binding_expression(inner)
              expr.nil? ? '' : "${#{expr}}"
            else
              escape_template_literal_segment(part)
            end
          end.join

          "{`#{body}`}"
        end

        # JS expression for one '@{...}' occurrence in a text run.
        # Canonical paths get the text-context unresolved default appended
        # (`?? ""`) unless an authored '?? literal' already survived emit
        # (a null default is dropped by add_viewmodel_data_prefix, so the
        # canonical unresolved->emptyString still applies). '!' negation is
        # a validator error in text (binding-negation-context): the token
        # resolves as an ordinary unresolvable key => empty string (nil
        # here). Non-canonical legacy expressions pass through unchanged —
        # appending '?? ""' to arbitrary JS (e.g. `a || b`) can be a
        # SyntaxError.
        def text_binding_expression(inner)
          expr = inner.to_s.strip
          return nil if expr.start_with?('!')

          path, default = expr.split(/\s*\?\?\s*/, 2)
          bare = path.to_s.strip
                     .sub(/\AviewModel\.data\./, '')
                     .sub(/\AviewModel\./, '')
                     .sub(/\Adata\./, '')
          canonical = bare.match?(BINDING_PATH_RE) &&
                      (default.nil? || default.strip.match?(BINDING_DEFAULT_LITERAL_RE))

          js = add_viewmodel_data_prefix(expr)
          return js unless canonical

          js.include?(' ?? ') ? js : "#{js} ?? \"\""
        end

        # Literal text inside the generated template literal: backticks and
        # '${' must be escaped so authored braces/backticks render verbatim;
        # raw newlines become '\n' so the emitted JSX stays single-line.
        # Block-form gsub is deliberate: in a plain replacement STRING the
        # sequence backslash-backtick is the PREMATCH special sequence and
        # would corrupt the output.
        def escape_template_literal_segment(text)
          text.gsub('`') { '\\`' }.gsub('${') { '\\${' }.gsub("\n") { '\\n' }
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
          # Check if text starts with { and is likely JSON (not a binding —
          # bindings start with an identifier or a '!' negation prefix)
          if value.start_with?('{') && !value.match?(/^\{!?[a-zA-Z]/)
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
          attributes['id'] || attributes['propertyName']
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

        # Focus-state binding attrs for editable fields (TextField / TextView)
        # — cross-platform parity with sjui/kjui `data.<id>IsFocused`: the
        # generator hoists `const <camel>Ref = useRef(...)` + a `useEffect`
        # driving focus from `data.<camel>IsFocused`; here the element gets the
        # ref and reports focus changes back through the optional
        # `on<Camel>IsFocusedChange` handler. Only fields with a literal id
        # participate (the ref/effect are derived from the same walk).
        def build_focus_binding_attrs
          id_value = attributes['id']
          return '' unless id_value.is_a?(String) && !id_value.empty? && !has_binding?(id_value)

          camel = snake_to_camel_id(id_value)
          handler = "on#{camel[0].upcase}#{camel[1..]}IsFocusedChange"
          " ref={#{camel}Ref}" \
            " onFocus={() => data.#{handler}?.(true)}" \
            " onBlur={() => data.#{handler}?.(false)}"
        end

        # snake_case id -> lowerCamel stem. MUST stay in sync with
        # DataModelGenerator / ReactGenerator focus-field derivation.
        def snake_to_camel_id(str)
          parts = str.split('_')
          parts[0] + parts[1..].map(&:capitalize).join
        end

        # Build aria-disabled for wrapper elements (div/label) whose inner
        # <input> carries the real `disabled` attribute. The layout `id` is
        # emitted on the wrapper, so the wrapper must reflect the disabled
        # state for accessibility and element-level testability.
        def build_aria_disabled_attr
          enabled = attributes['enabled']
          return '' if enabled.nil?

          if has_binding?(enabled)
            " aria-disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' aria-disabled="true"'
          else
            ''
          end
        end

        # Build the alt attribute for image-family converters. alt is
        # user-visible text (screen readers), so it resolves strings.json
        # keys exactly like text/hint. Decorative images keep alt=""
        # untouched; unregistered literals pass through raw.
        def build_alt_attr
          raw = attributes['alt'] || attributes['accessibilityLabel'] || ''
          return " alt=\"#{raw}\"" if raw.empty?

          if (resolved = convert_string_key(raw))
            " alt=#{resolved}"
          else
            " alt=\"#{raw}\""
          end
        end

        # Build data-testid attribute for testing
        def build_testid_attr
          test_id = attributes['testId']
          return '' unless test_id
          " data-testid=\"#{test_id}\""
        end

        # Build tag attribute (as data-tag for reference)
        def build_tag_attr
          tag = attributes['tag']
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
          if attributes['onClick']
            handler = attributes['onClick']
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
          if attributes['onclick']
            handler = attributes['onclick']
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

        # Resolve a handler attribute (binding `@{name}` or bare selector `name`)
        # to a `data.`-prefixed property reference
        def resolve_handler_property(handler)
          if is_binding_format?(handler)
            extract_binding_property(handler)
          else
            add_viewmodel_data_prefix(handler)
          end
        end

        # Determine absolute position classes based on align attributes for overlay children
        def overlay_position_classes
          has_align = attributes['centerInParent'] || attributes['centerVertical'] || attributes['centerHorizontal'] ||
                      attributes['alignTop'] || attributes['alignBottom'] || attributes['alignLeft'] || attributes['alignRight']

          unless has_align
            return 'inset-0'
          end

          classes = []

          if attributes['centerInParent']
            classes << 'top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2'
          else
            # Vertical
            if attributes['centerVertical']
              classes << 'top-1/2 -translate-y-1/2'
            elsif attributes['alignBottom']
              classes << 'bottom-0'
            elsif attributes['alignTop']
              classes << 'top-0'
            end

            # Horizontal
            if attributes['centerHorizontal']
              classes << 'left-1/2 -translate-x-1/2'
            elsif attributes['alignRight']
              classes << 'right-0'
            elsif attributes['alignLeft']
              classes << 'left-0'
            end
          end

          classes.join(' ')
        end

        # Canonical binding grammar (shared/core/binding_semantics.json):
        # inner = [!]path [?? default], path = identifier segments joined by
        # '.' with optional bracket index (items[0].title).
        BINDING_PATH_RE = /\A[a-zA-Z_$][\w$]*(?:\.[a-zA-Z_$][\w$]*|\[\d+\])*\z/
        # Binding shape accepted by the visibility/hidden conditional paths:
        # optional '!' negation + canonical path (incl. bracket index).
        SIMPLE_BINDING_EXPR_RE = /\A!?[a-zA-Z_$][\w$]*(?:\.[a-zA-Z_$][\w$]*|\[\d+\])*\z/
        # Canonical '??' default literals: "x" / 'x' / true / false / number /
        # null (null = unresolved, so the default is dropped at emit time).
        BINDING_DEFAULT_LITERAL_RE = /\A(?:"[^"]*"|'[^']*'|true|false|null|-?\d+(?:\.\d+)?)\z/

        # Add data. prefix to a property name for binding expressions.
        # All properties are converted to data.xxx format.
        #
        # Canonical expressions ([!]path [?? literal]) additionally get:
        # - optional chaining on every segment after the root
        #   (user.name -> data.user?.name, items[0].title ->
        #   data.items?.[0]?.title) so a missing intermediate node resolves
        #   to undefined instead of throwing at runtime; a single flat
        #   segment stays data.x — two-way/controlled-value emit sites are
        #   flat-only (binding-two-way-complex) and keep their exact shape
        # - '!' negation emitted as a JS prefix (!data.flag)
        # - '?? default' emitted after the chained path; `?.` yields
        #   undefined for unresolved paths, so JS nullish semantics give the
        #   canonical unresolved->default behavior naturally. A null default
        #   means "unresolved" and is dropped.
        # Non-canonical expressions keep the legacy passthrough (prefix
        # only) so the validator's business-logic warnings stay the signal.
        def add_viewmodel_data_prefix(prop)
          expr = prop.to_s.strip
          # Legacy viewModel spellings normalize to data.
          expr = expr.sub(/\AviewModel\.data\./, 'data.')
          expr = expr.sub(/\AviewModel\./, 'data.')

          negated = expr.start_with?('!')
          body = negated ? expr[1..].to_s.strip : expr

          path, default = body.split(/\s*\?\?\s*/, 2)
          path = path.to_s.strip
          bare = path.sub(/\Adata\./, '')

          canonical = bare.match?(BINDING_PATH_RE) &&
                      (default.nil? || default.strip.match?(BINDING_DEFAULT_LITERAL_RE))
          unless canonical
            return expr.start_with?('data.') ? expr : "data.#{expr}"
          end

          js = "data.#{optional_chain_path(bare)}"
          js = "!#{js}" if negated
          if default && default.strip != 'null'
            js = "#{js} ?? #{default.strip}"
          end
          js
        end

        # user.name -> user?.name / items[0].title -> items?.[0]?.title.
        # A single flat segment is returned untouched (data.x stays data.x;
        # the data root itself always exists and never needs chaining).
        def optional_chain_path(path)
          segments = path.scan(/[a-zA-Z_$][\w$]*|\[\d+\]/)
          return path if segments.length <= 1

          segments[0] + segments[1..].map { |seg| "?.#{seg}" }.join
        end

        # Build visibility binding for conditional rendering
        # Supports simple property bindings: flat, dotted, bracket-indexed,
        # optionally negated ("@{isVisible}", "@{a.b}", "@{items[0].v}",
        # "@{!x}") - no ternary operators / business logic. Negation on
        # visibility is a validator error (binding-negation-context —
        # visibility is a string enum, not a bool attribute), but the emit
        # path still handles it instead of silently dropping the binding.
        def build_visibility_info
          visibility = attributes['visibility']
          return nil unless visibility && has_binding?(visibility)

          binding_expr = visibility.gsub(/@\{|\}/, '').strip

          if binding_expr.match?(SIMPLE_BINDING_EXPR_RE)
            { condition: add_viewmodel_data_prefix(binding_expr) }
          else
            nil
          end
        end

        # Wrap JSX with visibility condition (conditional render)
        # "gone" → removes from DOM, "invisible" → hidden but keeps space
        def wrap_with_visibility(jsx, indent)
          jsx = apply_hidden_binding(jsx)

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

        # `hidden` is ["boolean", "binding"] — a bound value toggles the
        # Tailwind `invisible` class at runtime instead of baking it in
        # statically (static true/false is handled in build_class_name).
        # hidden = visibility:"invisible" shorthand: the component keeps
        # its layout space (visibility:hidden), it is NOT display:none.
        # `hidden` is a bool attribute, so canonical negation ("@{!flag}")
        # is legal here and emits `!data.flag` as the toggle condition.
        def apply_hidden_binding(jsx)
          hidden = attributes['hidden']
          return jsx unless has_binding?(hidden)

          binding_expr = hidden[/@\{([^}]+)\}/, 1].strip
          # Only simple property bindings (no ternary / business logic)
          return jsx unless binding_expr.match?(SIMPLE_BINDING_EXPR_RE)

          cond = add_viewmodel_data_prefix(binding_expr)
          inject_class_expression(jsx, "${#{cond} ? \"invisible\" : \"\"}")
        end

        # Inject invisible class into JSX when visibility === "invisible"
        def inject_invisible_class(jsx, condition)
          inject_class_expression(jsx, "${#{condition} === \"invisible\" ? \"invisible\" : \"\"}")
        end

        # Append a `${...}` expression to the first className attribute,
        # upgrading a static className="..." to a template literal.
        def inject_class_expression(jsx, class_expr)
          # Case 1: className={`...`} (template literal)
          result = jsx.sub(/className=\{`([^`]*)`\}/) do
            "className={`#{$1} #{class_expr}`}"
          end
          return result if result != jsx

          # Case 2: className="..." (static string)
          jsx.sub(/className="([^"]*)"/) do
            "className={`#{$1} #{class_expr}`}"
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
        # partialAttributes on web is rendered at BUILD time by slicing the
        # literal `text`, so two shapes the canon allows cannot work here and
        # used to be dropped in silence — no error, no warning, just a label
        # with the styling and the click handler missing.
        #
        # iOS and Android hand the partials to their runtime, which sees the
        # resolved string, so both shapes work there. Until web does the
        # same, say so at build time instead of emitting something wrong.
        def warn_unsupported_partial_ranges(partials, text)
          return unless defined?(Core::Logger)

          dropped = partials.reject { |p| p['range'].is_a?(Array) }
          unless dropped.empty?
            shapes = dropped.map { |p| p['range'].inspect }.join(', ')
            Core::Logger.warn(
              "Label partialAttributes: #{dropped.length} partial(s) with a non-array range " \
              "(#{shapes}) are NOT rendered on web and were dropped. Web slices the literal " \
              'text at build time, so pattern and binding ranges cannot be resolved; only ' \
              '[start, end] works. iOS and Android render these at runtime.'
            )
          end

          # A string-resource key or a binding is not the text the user sees,
          # so slicing it produces sliced key fragments in the output.
          if text.is_a?(String) && (has_binding?(text) || convert_string_key(text))
            Core::Logger.warn(
              "Label partialAttributes combined with a localized/bound text ('#{text}') — " \
              'web slices the raw key at build time, so the string table is bypassed and ' \
              'the key itself is emitted. Use a literal text here, or move the emphasis out ' \
              'of the Label, until web renders partials at runtime.'
            )
          end
        end

      end
    end
  end
end
