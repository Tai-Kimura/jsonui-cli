# frozen_string_literal: true

module KjuiTools
  module Core
    # A name kjui writes as a Kotlin declaration or an Android resource name,
    # made valid whatever the key it comes from — sjui's Core::SwiftIdentifier
    # for Kotlin (ticket sjui-resource-managers-emit-swift-that-does-not-compile,
    # the Android section). Only a name that does not compile today changes,
    # so every file that builds today is emitted byte for byte as before.
    #
    #   a leading digit   `4ecdc4` -> `_4ecdc4` (kotlinc rejects `val 4ecdc4`;
    #                     aapt2 rejects a resource named `1_screen_…`)
    #   a hard keyword    `object` -> `` `object` `` where declared (soft and
    #                     modifier keywords — `open`, `data`, `value` — are
    #                     legal names and stay)
    module KotlinIdentifier
      module_function

      # Kotlin's hard keywords (kotlinlang.org/docs/keyword-reference.html).
      HARD_KEYWORDS = %w[
        as break class continue do else false for fun if in interface is null
        object package return super this throw true try typealias typeof val
        var when while
      ].freeze

      # The name as a declaration: `val <declaration(name)>`.
      def declaration(name)
        name = leading_digit(name)
        HARD_KEYWORDS.include?(name) ? "`#{name}`" : name
      end

      # An Android resource name (R.string.<name>): a resource cannot start
      # with a digit; a kjui resource name always holds `_`, so it is never
      # a keyword alone.
      def resource_name(name)
        leading_digit(name)
      end

      def leading_digit(name)
        name = name.to_s
        name.match?(/\A[0-9]/) ? "_#{name}" : name
      end
    end
  end
end
