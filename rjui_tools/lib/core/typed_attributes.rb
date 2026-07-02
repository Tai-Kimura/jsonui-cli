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
    #   table: alias fallback (L0 layouts), type coercion, lenient enum
    #   matching (case-insensitive; unknown values warn and pass through
    #   raw). Alias spellings passed as `key` are redirected to their
    #   canonical row.
    # - Binding-capable and binding-only values come back in the raw
    #   layout representation (`"@{expr}"` string, static value, or the
    #   original action-object Hash) so the existing `has_binding?` /
    #   `extract_binding_property` converter logic keeps working
    #   unchanged; the AttrValue wrapper is unwrapped here via
    #   `AttrValue#raw`.
    # - L1-normalized layouts (`$jui` marker) take the canonical-only
    #   path: `extract(..., canonical_only: true)` ignores alias
    #   spellings entirely (the normalizer has already rewritten them,
    #   so any leftover is stale input).
    # - Keys not declared in attribute_definitions.json (extension
    #   component props, web-only custom keys, structural internals) pass
    #   through to the raw JSON value untouched.
    # - RAW_LOOKUP_KEYS rows resolve with declared alias handling but
    #   WITHOUT type coercion, because the generated coercion is narrower
    #   than what the web codegen accepts (see comments on the constant).
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
      #
      # These are all number/dimension-typed keys that accept web-only
      # CSS value shapes — a :css_dimension definitions kind was
      # deliberately deferred (06 plan §5 item 5), so the bridge keeps
      # absorbing them. The former enum entries (textAlign, input,
      # contentMode, resize, navigationMode, gradientDirection) were
      # resolved by the lenient (case-insensitive, warn-but-pass)
      # generated enum matching and now go through the extraction table.
      RAW_LOOKUP_KEYS = %w[
        width height
        minWidth maxWidth minHeight maxHeight
        padding
        tag
      ].freeze

      def initialize(json, component_type: nil, normalized: false)
        @json = json.is_a?(Hash) ? json : {}
        @normalized = normalized
        @module = TYPE_MODULES[component_type || @json['type']]
        # Declared-attribute metadata comes straight from the generated
        # modules' public API (rows / alias_map).
        @rows = extraction_module.rows
        @alias_to_canonical = extraction_module.alias_map
        @extracted = extraction_module.extract(@json, canonical_only: @normalized)
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

      # True when `key` is declared (canonical name or alias spelling)
      # for this component in attribute_definitions.json.
      def declared?(key)
        @rows.key?(key) || @alias_to_canonical.key?(key)
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

      def raw_row?(row)
        RAW_LOOKUP_KEYS.include?(row[:name])
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

      # AttrValue → raw layout representation ("@{expr}", static value,
      # or the original action-object Hash) so existing converter
      # binding logic works unchanged.
      def unwrap(value)
        value.is_a?(GENERATED::AttrValue) ? value.raw : value
      end
    end
  end
end
