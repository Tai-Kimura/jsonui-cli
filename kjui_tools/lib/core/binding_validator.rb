#!/usr/bin/env ruby
# frozen_string_literal: true

require_relative 'binding_validator_core'

module KjuiTools
  module Core
    # Android profile over the shared binding-validator body
    # (lib/core/binding_validator_core.rb — byte-identical mirror of
    # shared/core/binding_validator_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb). Canonical rules, Embed
    # grammar, cell scope, include hygiene and unused-property tracking
    # live in the shared core; this class owns the Kotlin-language
    # advisory patterns and the Kotlin type suggestions.
    class BindingValidator < ::JsonUIShared::BindingValidatorCore
      # Patterns that indicate business logic in bindings (Kotlin spellings)
      BUSINESS_LOGIC_PATTERNS = [
        {
          pattern: /\?.*:/,
          message: "ternary operator (?:) - move condition logic to ViewModel"
        },
        {
          pattern: /\bif\s*\(/,
          message: "if expression - move condition logic to ViewModel"
        },
        {
          pattern: /\bwhen\s*[({]/,
          message: "when expression - move logic to ViewModel"
        },
        {
          pattern: /[<>=!]=|[<>]/,
          message: "comparison operator - move to ViewModel computed property"
        },
        {
          pattern: /(?<![a-zA-Z_])[+\/*%]|(?<![a-zA-Z_0-9])-(?![a-zA-Z_0-9}])/,
          message: "arithmetic operator - compute value in ViewModel"
        },
        {
          pattern: /&&|\|\|/,
          message: "logical operator (&&, ||) - move logic to ViewModel"
        },
        {
          pattern: /\?:/,
          message: "elvis operator (?:) - handle null in ViewModel"
        },
        {
          pattern: /\.\w+\([^)]+\)/,
          message: "method call with arguments - move to ViewModel"
        },
        {
          pattern: /\w+\(\s*\)/,
          message: "method call - move to ViewModel computed property"
        },
        {
          pattern: /\$\{|\$[a-zA-Z]/,
          message: "string interpolation - compose string in ViewModel"
        },
        {
          pattern: /\[[^\]]*[+\-*\/<>=]/,
          message: "complex array subscript - simplify in ViewModel"
        },
        {
          pattern: /\s+as[?\s]+\w+/,
          message: "type casting - handle type conversion in ViewModel"
        },
        {
          pattern: /!!/,
          message: "not-null assertion (!!) - handle nullability safely in ViewModel"
        },
        {
          pattern: /\{[^}]*->[^}]*\}/,
          message: "lambda expression - move to ViewModel"
        },
        {
          pattern: /\.\.|\s+until\s+|\s+downTo\s+/,
          message: "range operator - create range in ViewModel"
        },
        {
          pattern: /\.(let|run|apply|also|with)\s*\{/,
          message: "scope function - move logic to ViewModel"
        }
      ].freeze

      # Kotlin-specific additions to the business-logic allowlist
      EXTRA_ALLOWED_PATTERNS = [
        # Property access with safe call (a?.b)
        /^@\{[a-zA-Z_][a-zA-Z0-9_]*(\??\.[a-zA-Z_][a-zA-Z0-9_]*)*\}$/,
        # Simple boolean negation of a property path — context legality is
        # decided by the canonical rules, not here
        /^@\{!\s*[a-zA-Z_][a-zA-Z0-9_]*(\??\.[a-zA-Z_][a-zA-Z0-9_]*)*\}$/
      ].freeze

      private

      def platform_id
        'kotlin'
      end

      def mode_id
        'compose'
      end

      def log_tag
        'KJUI'
      end

      def data_item_applies?(data_item)
        return false if data_item['platform'] && data_item['platform'] != 'kotlin'
        return false if data_item['mode'] && !['compose', 'xml'].include?(data_item['mode'])
        true
      end

      def business_logic_patterns
        BUSINESS_LOGIC_PATTERNS
      end

      def extra_allowed_patterns
        EXTRA_ALLOWED_PATTERNS
      end

      def map_typed_class?(class_str)
        class_str.match?(/\AMap\s*<|\AHashMap\s*</)
      end

      # Infer type from variable name and attribute context (Kotlin types)
      def infer_type(var_name, attribute_name, component_type = nil)
        # Callbacks with Int parameter
        return '((Int) -> Unit)?' if %w[onTabChange onItemAppear].include?(var_name) || %w[onTabChange onItemAppear].include?(attribute_name)

        # onClick, onXxx -> (() -> Unit)? (Kotlin callback type)
        return '(() -> Unit)?' if var_name.start_with?('on') && var_name[2]&.match?(/[A-Z]/)

        # xxxItems, xxxOptions, xxxList -> List<Any>
        return 'List<Any>' if var_name.end_with?('Items', 'Options', 'List', 'Args', 'Subcommands')

        # isXxx, hasXxx, canXxx, shouldXxx -> Boolean
        return 'Boolean' if var_name.start_with?('is', 'has', 'can', 'should')

        # xxxVisibility -> String
        return 'String' if var_name.end_with?('Visibility')

        # xxxIndex, xxxCount, xxxTab -> Int
        return 'Int' if var_name.end_with?('Index', 'Count', 'Tab')

        # xxxMargin, xxxPadding -> Dp (Kotlin Compose)
        return 'Dp' if var_name.end_with?('Margin', 'Padding')

        # Based on attribute name
        case attribute_name
        when 'onTabChange', 'onItemAppear'
          '((Int) -> Unit)?'
        when 'onClick', 'onValueChanged', 'onValueChange', 'onTap'
          '(() -> Unit)?'
        when 'items'
          'CollectionDataSource'
        when 'sections'
          'List<Any>'
        when 'visibility', 'text', 'fontColor', 'background'
          'String'
        when 'selectedIndex', 'width', 'height'
          'Int'
        when 'hidden', 'enabled', 'disabled'
          'Boolean'
        when 'topMargin', 'bottomMargin', 'leftMargin', 'rightMargin', 'startMargin', 'endMargin'
          'Dp'
        when 'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight', 'paddingStart', 'paddingEnd'
          'Dp'
        when 'src', 'srcName'
          # NetworkImage uses URL string, Image/CircleImage uses Image type
          if component_type&.include?('Network')
            'String'
          else
            'Image'
          end
        else
          'Any'
        end
      end
    end
  end
end
