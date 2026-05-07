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

    # Check if a component has responsive overrides
    def self.responsive?(component)
      component.is_a?(Hash) && component['responsive'].is_a?(Hash)
    end

    # Get all size class keys defined in the responsive block
    def self.size_classes(component)
      return [] unless responsive?(component)

      component['responsive'].keys.select { |k| VALID_SIZE_CLASSES.include?(k) }
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
      PRIORITY_ORDER.each do |sc|
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
    def self.parse_size_class(size_class)
      return { width: nil, landscape: false } if size_class.nil?

      parts = size_class.split('-')
      landscape = parts.include?('landscape')
      width = (parts - ['landscape']).first

      { width: width, landscape: landscape }
    end
  end
end
