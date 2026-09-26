# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      # Indentation for code a builder wraps around code it already emitted
      # (compose_builder's capture_interaction_stop / provide_interaction_stop).
      # These lived in TintHelper, beside the LocalContentColor wrapper that
      # tintColor no longer uses (tintColor is the accent of the operable
      # parts, jsonui-cli 1.9.0).
      module CodeIndent
        module_function

        def pad(text, level)
          return text if level.to_i <= 0

          ('    ' * level) + text
        end

        def shift(text, levels)
          prefix = '    ' * levels
          text.split("\n").map { |l| l.empty? ? l : prefix + l }.join("\n")
        end
      end
    end
  end
end
