# frozen_string_literal: true

module SjuiTools
  module Core
    # A generated Swift name made valid whatever the key it comes from.
    # StringManager and ColorManager name their members after strings.json /
    # colors.json keys; a key that starts with a digit ("15 Minute
    # Intervals" → `15MinuteIntervals`) or that is a reserved word
    # (`default`) was written as is, and the generated file did not compile
    # (ticket sjui-resource-managers-emit-swift-that-does-not-compile).
    #
    # Only names that did not compile change: a leading digit gets `_`
    # (declaration and every reference); a reserved word is back-quoted where
    # it is declared and written plainly after a dot, where Swift accepts it.
    # Contextual keywords (`open`, `get`, `set`, …) are valid names and are
    # left alone.
    module SwiftIdentifier
      RESERVED = %w[
        associatedtype class deinit enum extension fileprivate func import init inout internal let
        operator precedencegroup private protocol public rethrows static struct subscript typealias var
        break case catch continue default defer do else fallthrough for guard if in repeat return
        throw switch where while Any as false is nil self Self super throws true try
      ].freeze

      module_function

      # The name a reference writes after a dot.
      def reference(name)
        name = name.to_s
        name.match?(/\A\d/) ? "_#{name}" : name
      end

      # The name a declaration writes.
      def declaration(name)
        ref = reference(name)
        RESERVED.include?(ref) ? "`#{ref}`" : ref
      end
    end
  end
end
