# frozen_string_literal: true

module SjuiTools
  module SwiftUI
    module Views
      # ModifierBag collects modifiers with ordered keys and deduplication.
      # Later `register` calls win (binding overrides static).
      # Multi-value keys (padding, margin, component_specific) use arrays.
      class ModifierBag
        MODIFIER_ORDER = [
          :component_specific,  # font, resizable, aspectRatio, etc.
          :padding,             # inner padding entries
          :frame_constraints,   # min/max width/height
          :fixed_size,          # fixedSize
          :frame_size,          # width/height
          :background,          # background color
          :gradient,            # gradient background
          :corner_radius,       # cornerRadius
          :border,              # overlay stroke
          :shadow,              # shadow
          :clip_to_bounds,      # clipped
          :foreground_color,    # foregroundColor
          :opacity,             # opacity/alpha
          :hidden,              # hidden
          :offset,              # offset
          :margin,              # outer margin entries
          :disabled,            # disabled
          :allows_hit_testing,  # allowsHitTesting
          :tint_color,          # tint
          :on_click,            # contentShape + onTapGesture
          :on_value_change,     # onChange handlers
          :on_text_change,      # text change handlers
          :on_appear,           # onAppear
          :on_disappear,        # onDisappear
          :confirmation_dialog, # confirmationDialog
          :safe_area_insets,    # ignoresSafeArea
          :tag,                 # tag
          :z_index,             # zIndex
          :accessibility_id,    # accessibilityIdentifier (always last)
        ].freeze

        # Keys that store arrays of code strings (multi-value)
        MULTI_VALUE_KEYS = [
          :component_specific,
          :padding,
          :margin,
          :frame_constraints,
          :frame_size,
          :on_click,
          :on_value_change,
          :on_text_change,
          :on_appear,
          :on_disappear,
          :confirmation_dialog,
          :safe_area_insets,
          :z_index,
          :border,
        ].freeze

        def initialize
          @bag = {}
        end

        # Register a modifier. Later registration wins (overwrites previous).
        # For multi-value keys, replaces the entire array.
        # @param key [Symbol] modifier key from MODIFIER_ORDER
        # @param code [String, Array<String>] SwiftUI modifier code line(s)
        def register(key, code)
          if MULTI_VALUE_KEYS.include?(key)
            @bag[key] = code.is_a?(Array) ? code : [code]
          else
            @bag[key] = code
          end
        end

        # Register only if key is not yet set (static default, won't override binding).
        # @param key [Symbol] modifier key
        # @param code [String, Array<String>] SwiftUI modifier code line(s)
        def register_unless_exists(key, code)
          return if @bag.key?(key)
          register(key, code)
        end

        # Append a code string to a multi-value key.
        # Creates the array if it doesn't exist yet.
        # @param key [Symbol] modifier key (should be in MULTI_VALUE_KEYS)
        # @param code [String] single SwiftUI modifier code line
        def append(key, code)
          @bag[key] ||= []
          if @bag[key].is_a?(Array)
            @bag[key] << code
          else
            # Convert single value to array and append
            @bag[key] = [@bag[key], code]
          end
        end

        # Check if a key is registered
        # @param key [Symbol] modifier key
        # @return [Boolean]
        def key?(key)
          @bag.key?(key)
        end

        # Get the value for a key (for inspection/testing)
        # @param key [Symbol] modifier key
        # @return [String, Array<String>, nil]
        def [](key)
          @bag[key]
        end

        # Emit all registered modifiers in correct order via converter.add_modifier_line
        # @param converter [BaseViewConverter] the converter to emit lines through
        def emit_all(converter)
          MODIFIER_ORDER.each do |key|
            next unless @bag.key?(key)
            value = @bag[key]

            if value.is_a?(Array)
              value.each do |line|
                next unless line && !line.empty?
                # Multi-line modifiers (like .overlay with indented content)
                # are passed as-is; the converter handles indentation
                if line.include?("\n")
                  line.split("\n").each_with_index do |sub_line, idx|
                    if idx == 0
                      converter.add_modifier_line(sub_line)
                    else
                      converter.add_line(sub_line)
                    end
                  end
                else
                  converter.add_modifier_line(line)
                end
              end
            else
              next unless value && !value.to_s.empty?
              if value.include?("\n")
                value.split("\n").each_with_index do |sub_line, idx|
                  if idx == 0
                    converter.add_modifier_line(sub_line)
                  else
                    converter.add_line(sub_line)
                  end
                end
              else
                converter.add_modifier_line(value)
              end
            end
          end
        end

        # Return all registered keys (for testing)
        def keys
          @bag.keys
        end

        # Clear all modifiers
        def clear
          @bag.clear
        end
      end
    end
  end
end
