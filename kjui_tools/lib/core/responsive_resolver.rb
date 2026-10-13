# frozen_string_literal: true

require 'set'

module JsonUIShared
  # Resolves responsive overrides for a component based on size class.
  #
  # Usage:
  #   resolver = ResponsiveResolver.new(component)
  #   resolver.responsive?                     # => true if component has responsive block
  #   resolver.size_classes                     # => ["regular", "landscape", "regular-landscape"]
  #   resolver.resolve("regular")              # => merged attributes for regular
  #   resolver.overridden_keys                  # => Set of all attribute keys that change across any size class
  #
  module ResponsiveResolver
    # Valid size class keys (single and compound)
    VALID_SIZE_CLASSES = %w[
      compact medium regular landscape
      compact-landscape medium-landscape regular-landscape
    ].freeze

    # Resolution priority (highest first). Compound > single > default.
    PRIORITY_ORDER = %w[
      regular-landscape medium-landscape compact-landscape
      landscape regular medium compact
    ].freeze

    # Window-width conditions (jui-responsive-width-threshold-conditions,
    # jsonui-cli 1.9.25): `minWidth:N` holds when the window is at least N
    # wide, `maxWidth:N` when it is narrower than N — N itself is not
    # included, so `maxWidth:700` and `minWidth:700` split the widths with no
    # gap and no overlap, fractional widths included. N is a non-negative
    # integer in the platform's logical unit (iOS pt, Android dp, web CSS px)
    # and the width is the window's (iOS the scene's, Android
    # LocalWindowInfo.containerSize, web the viewport), not the parent's.
    # ⚠️ jsonui-test-runner's responsive *test conditions* read maxWidth as
    # "at most N"; a layout key's maxWidth is "less than N".
    #
    # One responsive block holds width conditions or size classes, never
    # both; every maxWidth's N is at most every minWidth's N; no landscape
    # combination. jui build refuses anything else (ERROR [responsive],
    # jui_tools responsive_width_gate.py). Among the conditions that hold,
    # the most narrowing one wins alone, as a size class does: the smallest
    # maxWidth, else the largest minWidth.
    WIDTH_CONDITION = /\A(minWidth|maxWidth):(0|[1-9][0-9]*)\z/

    # { kind: :min | :max, value: Integer } for a width-condition key, else nil
    def self.width_condition(key)
      match = WIDTH_CONDITION.match(key.to_s)
      return nil unless match

      { kind: match[1] == 'minWidth' ? :min : :max, value: Integer(match[2], 10) }
    end

    # The width-condition keys of a block, most narrowing first: maxWidth by
    # N ascending, then minWidth by N descending. Tried in this order, the
    # first that holds is the one that wins.
    def self.width_condition_keys(component)
      return [] unless responsive?(component)

      parsed = component['responsive'].keys.filter_map { |k| (c = width_condition(k)) && [k, c] }
      maxes = parsed.select { |_, c| c[:kind] == :max }.sort_by { |_, c| c[:value] }
      mins = parsed.select { |_, c| c[:kind] == :min }.sort_by { |_, c| -c[:value] }
      (maxes + mins).map(&:first)
    end

    # True when the block uses width conditions and no size class — the only
    # shape whose width conditions are drawn.
    def self.width_conditions?(component)
      return false unless responsive?(component)

      keys = component['responsive'].keys
      keys.none? { |k| VALID_SIZE_CLASSES.include?(k) } && keys.any? { |k| width_condition(k) }
    end

    # Check if a component has responsive overrides
    def self.responsive?(component)
      component.is_a?(Hash) && component['responsive'].is_a?(Hash)
    end

    # Get all size class keys defined in the responsive block
    def self.size_classes(component)
      return [] unless responsive?(component)

      component['responsive'].keys.select { |k| VALID_SIZE_CLASSES.include?(k) || width_condition(k) }
    end

    # Get the set of attribute keys that are overridden in any size class
    def self.overridden_keys(component)
      return Set.new unless responsive?(component)

      keys = Set.new
      component['responsive'].each_value do |overrides|
        next unless overrides.is_a?(Hash)

        overrides.each_key { |k| keys.add(k) }
      end
      keys
    end

    # Resolve attributes for a specific size class.
    # Returns the component attributes with overrides merged in.
    # Does NOT include 'responsive', 'type', 'child', 'data' keys in overrides.
    def self.resolve(component, size_class)
      return component unless responsive?(component)

      overrides = component.dig('responsive', size_class)
      return component unless overrides.is_a?(Hash)

      merged = component.dup
      merged.delete('responsive')
      overrides.each do |key, value|
        next if %w[type child data responsive].include?(key)

        merged[key] = value
      end
      merged
    end

    # Build a list of condition/attributes pairs ordered by priority.
    # Returns: [{ size_class: "regular-landscape", overrides: { ... } }, ...]
    # The last entry (size_class: nil) is the default (no overrides).
    def self.build_branches(component)
      return [{ size_class: nil, attrs: component }] unless responsive?(component)

      branches = []
      order = width_conditions?(component) ? width_condition_keys(component) : PRIORITY_ORDER
      order.each do |sc|
        overrides = component.dig('responsive', sc)
        next unless overrides.is_a?(Hash)

        branches << { size_class: sc, attrs: resolve(component, sc) }
      end

      # Default branch (no overrides)
      default_attrs = component.dup
      default_attrs.delete('responsive')
      branches << { size_class: nil, attrs: default_attrs }

      branches
    end

    # Parse a size class key into its width and orientation components.
    # Returns: { width: "regular"|"medium"|"compact"|nil, landscape: true|false }
    # A width-condition key parses as no size class: { width: nil,
    # landscape: false, condition: { kind:, value: } }.
    def self.parse_size_class(size_class)
      return { width: nil, landscape: false } if size_class.nil?

      condition = width_condition(size_class)
      return { width: nil, landscape: false, condition: condition } if condition

      parts = size_class.split('-')
      landscape = parts.include?('landscape')
      width = (parts - ['landscape']).first

      { width: width, landscape: landscape }
    end
  end
end
