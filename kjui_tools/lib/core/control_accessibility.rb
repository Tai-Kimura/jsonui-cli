# frozen_string_literal: true

require_relative 'tap_accessibility'
require_relative 'type_synonyms'

module JsonUIShared
  # What a screen reader is told about a control beyond what it shows — one
  # rule for the rjui, sjui and kjui codegen (the Dynamic runtimes of both
  # libraries implement the same rule).
  #
  # `accessibilityLabel` (alias `contentDescription`) is the name a control is
  # read by in place of its own text: a strings.json key or literal, localized
  # like `text`, or a binding (web aria-label, iOS `.accessibilityLabel`,
  # Android `contentDescription`). It is declared on the types a user
  # operates, LABEL_TYPES. On a View it names the View only when the View is
  # one button to a screen reader — the tap rule's `button` or `combine`
  # shape (tap_accessibility.rb): a View that taps nothing, or holds a
  # control of its own, is no element of its own on iOS, and a name there
  # would land on its children instead. An image's name is its `alt`
  # (image_accessibility.rb), which takes both spellings as aliases.
  #
  # `accessibilityLiveRegion` (`polite` / `assertive` / `off`) reads a node
  # out whenever what it shows changes (web aria-live with role status /
  # alert, Android liveRegion). It is declared on Label and View; iOS has no
  # live region, so sjui gives it to a Label alone — an announcement of the
  # Label's text when a bound text changes — and a View's is declared for
  # web and Android only (attribute_definitions.json `platform`).
  module ControlAccessibility
    module_function

    LABEL_KEYS = %w[accessibilityLabel contentDescription].freeze

    # attribute_definitions.json sections that declare accessibilityLabel.
    LABEL_TYPES = %w[Button CheckBox Switch Radio Segment Slider SelectBox TextField View].freeze

    LIVE_KEY = 'accessibilityLiveRegion'
    LIVE_TYPES = %w[Label View].freeze
    LIVE_VALUES = %w[polite assertive].freeze

    # The declared section a node is drawn as: a synonym (HStack) as its
    # type, an alias section (Check, Toggle) as its canonical one.
    def section(node)
      ComponentAliases.canonical(TypeSynonyms.drawn_type(node['type'] || 'View'))
    end

    # The node's accessibilityLabel as written (a String: a key, text or a
    # binding), or nil when it declares none or is no type that takes one.
    # Spelled out key by key, in LABEL_KEYS order, so `jui conformance
    # coverage` sees the codegens read both spellings here.
    def label(node)
      return nil unless node.is_a?(Hash)

      value = if node.key?('accessibilityLabel') then node['accessibilityLabel']
              elsif node.key?('contentDescription') then node['contentDescription']
              end
      return nil unless value.is_a?(String) && !value.empty?

      type = section(node)
      return nil unless LABEL_TYPES.include?(type)
      return nil if type == 'View' && !one_button?(node)

      value
    end

    # A View that is one button to a screen reader: the tap rule's shape as
    # annotate! wrote it, else as the node alone decides.
    def one_button?(node)
      shape = node[TapAccessibility::SHAPE_KEY] || TapAccessibility.shape(node)
      %w[button combine].include?(shape)
    end

    # `polite`, `assertive`, or nil (`off`, none, or no type that takes one).
    def live(node)
      return nil unless node.is_a?(Hash) && node.key?('accessibilityLiveRegion')

      value = node['accessibilityLiveRegion']
      return nil unless LIVE_VALUES.include?(value)
      return nil unless LIVE_TYPES.include?(section(node))

      value
    end
  end
end
