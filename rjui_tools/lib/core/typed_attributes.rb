# frozen_string_literal: true

require_relative 'generated/attributes/attr_support'

# Load every generated per-component extraction module
# (lib/core/generated/attributes/*_attributes.rb, emitted by
# `jui generate attr-bindings --lang ruby`).
Dir[File.join(__dir__, 'generated', 'attributes', '*_attributes.rb')].sort.each do |file|
  require file
end

module RjuiTools
  module Core
    # Bridge between the generated typed attribute extraction
    # (JsonUI::Generated::<Component>Attributes.extract) and the React
    # converters.
    #
    # Converters read node attributes through `attributes['key']`
    # (BaseConverter#attributes) instead of raw `json['key']`. Lookup
    # semantics:
    #
    # - Canonical attribute names resolve through the generated extraction
    #   table: alias fallback (L0 layouts), type coercion, enum
    #   validation. Alias spellings passed as `key` are redirected to
    #   their canonical row.
    # - Binding-capable values come back in the raw layout representation
    #   (`"@{expr}"` string or the static value) so the existing
    #   `has_binding?` / `extract_binding_property` converter logic keeps
    #   working unchanged; the AttrValue wrapper is unwrapped here.
    # - L1-normalized layouts (`$jui` marker) take the canonical-only
    #   path: alias spellings are ignored entirely (the normalizer has
    #   already rewritten them, so any leftover is stale input).
    # - Keys not declared in attribute_definitions.json (extension
    #   component props, web-only custom keys, structural internals) pass
    #   through to the raw JSON value untouched.
    # - RAW_LOOKUP_KEYS / `kind: :binding` rows resolve with declared
    #   alias handling but WITHOUT type coercion, because the generated
    #   coercion is narrower than what the web codegen accepts (see
    #   comments on the constant).
    class TypedAttributes
      GENERATED = JsonUI::Generated

      # Layout `type` → generated extraction module. Type spellings that
      # have their own definitions section map to their own module; the
      # remaining converter-supported spellings map to the module of the
      # component the converter treats them as (mirrors
      # BaseConverter#get_converter_class / ReactGenerator::CONVERTERS).
      TYPE_MODULES = {
        'View' => GENERATED::ViewAttributes,
        'SafeAreaView' => GENERATED::SafeAreaViewAttributes,
        'Label' => GENERATED::LabelAttributes,
        'Text' => GENERATED::LabelAttributes,
        'Button' => GENERATED::ButtonAttributes,
        'Image' => GENERATED::ImageAttributes,
        'CircleImage' => GENERATED::ImageAttributes,
        'NetworkImage' => GENERATED::NetworkImageAttributes,
        'TextField' => GENERATED::TextFieldAttributes,
        'EditText' => GENERATED::EditTextAttributes,
        'Input' => GENERATED::InputAttributes,
        'TextView' => GENERATED::TextViewAttributes,
        'Scroll' => GENERATED::ScrollViewAttributes,
        'ScrollView' => GENERATED::ScrollViewAttributes,
        'Collection' => GENERATED::CollectionAttributes,
        'Table' => GENERATED::CollectionAttributes,
        'Switch' => GENERATED::SwitchAttributes,
        'Toggle' => GENERATED::ToggleAttributes,
        'CheckBox' => GENERATED::CheckBoxAttributes,
        'Checkbox' => GENERATED::CheckBoxAttributes,
        'Check' => GENERATED::CheckAttributes,
        'Slider' => GENERATED::SliderAttributes,
        'Segment' => GENERATED::SegmentAttributes,
        'Radio' => GENERATED::RadioAttributes,
        'Progress' => GENERATED::ProgressAttributes,
        'Indicator' => GENERATED::IndicatorAttributes,
        'SelectBox' => GENERATED::SelectBoxAttributes,
        'IconLabel' => GENERATED::IconLabelAttributes,
        'GradientView' => GENERATED::GradientViewAttributes,
        'Blur' => GENERATED::BlurAttributes,
        'CircleView' => GENERATED::CircleViewAttributes,
        'Web' => GENERATED::WebAttributes,
        'TabView' => GENERATED::TabViewAttributes,
        'Embed' => GENERATED::EmbedAttributes
      }.freeze

      # Declared keys that are looked up with alias handling but WITHOUT
      # the generated coercion, because the definitions type is narrower
      # than the value space the web codegen accepts:
      #
      # - width/height: kind :dimension only allows matchParent /
      #   wrapContent keywords, but TailwindMapper.map_width/height accept
      #   arbitrary CSS strings ("50%", "calc(...)").
      # - minWidth/maxWidth/minHeight/maxHeight: kind :number, but the
      #   web mappers also accept 'matchParent' and CSS strings.
      # - padding: kind :number, but rjui accepts edge-inset arrays
      #   ([all] | [v, h] | [t, r, b, l]).
      # - tag: kind :number, but rjui emits it as a data-tag string and
      #   accepts string tags.
      # - textAlign: enum casing differs per component (Label declares
      #   'Left'..'right', Button only 'Left'/'Center'/'Right'), while
      #   TailwindMapper.map_text_align is case-insensitive.
      # - input (TextField): the web converter accepts spellings the enum
      #   doesn't declare ('URL', 'tel', 'webSearch', 'numberPad', ...)
      #   and matches case-insensitively.
      # - contentMode (Image/NetworkImage): converter accepts lowerCamel
      #   spellings ('aspectFit', 'scaleToFill', 'aspect_fit') that the
      #   enum doesn't declare.
      # - resize (TextView): definitions declare a CSS-style enum
      #   ('none'/'both'/...) but the web converter historically accepts
      #   boolean truthiness; keep raw until the converter maps the enum.
      #
      # (Candidates for a definitions/emitter revision — see the 06 plan
      # feedback.)
      RAW_LOOKUP_KEYS = %w[
        width height
        minWidth maxWidth minHeight maxHeight
        padding
        tag
        textAlign
        input
        contentMode
        resize
      ].freeze

      def initialize(json, component_type: nil, normalized: false)
        @json = json.is_a?(Hash) ? json : {}
        @normalized = normalized
        @module = TYPE_MODULES[component_type || @json['type']]
        @rows = build_rows
        @alias_to_canonical = build_alias_map
        @extracted = extraction_module.extract(extract_source)
      end

      # Raw-equivalent read of a declared attribute (canonical name or
      # alias spelling); undeclared keys pass through to the raw JSON.
      def [](key)
        canonical = @rows.key?(key) ? key : @alias_to_canonical[key]
        return @json[key] unless canonical

        row = @rows[canonical]
        return raw_lookup(row) if raw_row?(row)

        unwrap(@extracted[canonical])
      end

      # True when the attribute resolves to a non-nil value.
      def key?(key)
        !self[key].nil?
      end

      # Escape hatch: raw JSON value under the exact key, no alias /
      # coercion handling. Structural reads should keep using the node
      # hash directly; this exists for diagnostic paths.
      def raw(key)
        @json[key]
      end

      private

      def extraction_module
        @module || GENERATED::CommonAttributes
      end

      # Common rows first, component rows override on name collision —
      # same precedence as the generated extract methods.
      def build_rows
        rows = {}
        GENERATED::CommonAttributes::ATTRS.each { |row| rows[row[:name]] = row }
        if @module && @module.const_defined?(:ATTRS)
          @module::ATTRS.each { |row| rows[row[:name]] = row }
        end
        rows
      end

      # alias spelling → canonical row name. Alias names that are ALSO
      # standalone rows (e.g. `alpha` next to `opacity`) keep their own
      # row and are not redirected.
      def build_alias_map
        map = {}
        @rows.each_value do |row|
          Array(row[:aliases]).each do |alias_name|
            next if @rows.key?(alias_name)

            map[alias_name] = row[:name]
          end
        end
        map
      end

      # The generated extract methods always consult alias spellings. On
      # an L1-normalized layout the canonical-only path is required, and
      # alias spellings cannot legitimately exist (the normalizer
      # rewrote them) — so strip every declared alias spelling from the
      # extraction input. No-op when none are present.
      def extract_source
        return @json unless @normalized

        alias_keys = @rows.each_value.flat_map { |row| Array(row[:aliases]) }
        return @json if alias_keys.empty? || alias_keys.none? { |k| @json.key?(k) }

        @json.reject { |k, _| alias_keys.include?(k) }
      end

      def raw_row?(row)
        row[:kind] == :binding || RAW_LOOKUP_KEYS.include?(row[:name])
      end

      # Canonical-first raw lookup honoring the normalized (canonical-
      # only) path — same semantics as BaseConverter#attr_lookup.
      def raw_lookup(row)
        value = @json[row[:name]]
        return value unless value.nil?
        return nil if @normalized

        Array(row[:aliases]).each do |alias_name|
          value = @json[alias_name]
          return value unless value.nil?
        end
        nil
      end

      # AttrValue → raw layout representation ("@{expr}" or static value)
      # so existing converter binding logic works unchanged.
      def unwrap(value)
        return value unless value.is_a?(GENERATED::AttrValue)

        value.binding? ? "@{#{value.binding_expression}}" : value.value
      end
    end
  end
end
