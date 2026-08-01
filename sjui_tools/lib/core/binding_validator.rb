#!/usr/bin/env ruby
# frozen_string_literal: true

require_relative 'binding_validator_core'

module SjuiTools
  module Core
    # iOS profile over the shared binding-validator body
    # (lib/core/binding_validator_core.rb — byte-identical mirror of
    # shared/core/binding_validator_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb). Canonical rules, Embed
    # grammar, cell scope, include hygiene and unused-property tracking
    # live in the shared core; this class owns the Swift-language
    # advisory patterns, the Swift type suggestions, and the UIKit-era
    # binding-needs-an-id advisory.
    class BindingValidator < ::JsonUIShared::BindingValidatorCore
      # Patterns that indicate business logic in bindings (Swift spellings)
      BUSINESS_LOGIC_PATTERNS = [
        {
          pattern: /\?.*:/,
          message: "ternary operator (?:) - move condition logic to ViewModel"
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
        # NOTE: nil coalescing (??) is NOT flagged — '@{path ?? default}'
        # is official grammar; the canonical rules enforce its arity.
        {
          pattern: /\.\w+\([^)]+\)/,
          message: "method call with arguments - move to ViewModel"
        },
        {
          pattern: /\w+\(\s*\)/,
          message: "method call - move to ViewModel computed property"
        },
        {
          pattern: /\\?\$\{|\\\(/,
          message: "string interpolation - compose string in ViewModel"
        },
        {
          pattern: /\[[^\]]*[+\-*\/<>=]/,
          message: "complex array subscript - simplify in ViewModel"
        },
        {
          pattern: /\s+as[?\s!]+\w+/,
          message: "type casting - handle type conversion in ViewModel"
        },
        {
          pattern: /[^?]!/,
          message: "force unwrap (!) - handle optionals safely in ViewModel"
        },
        {
          pattern: /\{[^}]*(?:in|->)[^}]*\}/,
          message: "closure/lambda - move to ViewModel"
        },
        {
          pattern: /\.\.\.|\.\.</,
          message: "range operator - create range in ViewModel"
        },
        {
          pattern: /\+\+|--/,
          message: "increment/decrement - update value in ViewModel"
        }
      ].freeze

      # Swift-specific additions to the business-logic allowlist
      EXTRA_ALLOWED_PATTERNS = [
        # Property access with optional chaining (a?.b)
        /^@\{[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*(\?)?\.?[a-zA-Z_][a-zA-Z0-9_]*\}$/
      ].freeze

      private

      def platform_id
        'swift'
      end

      def mode_id
        'swiftui'
      end

      def log_tag
        'SJUI'
      end

      def data_item_applies?(data_item)
        return false if data_item['platform'] && data_item['platform'] != 'swift'
        return false if data_item['mode'] && data_item['mode'] != 'swiftui'
        true
      end

      def business_logic_patterns
        BUSINESS_LOGIC_PATTERNS
      end

      def extra_allowed_patterns
        EXTRA_ALLOWED_PATTERNS
      end

      def map_typed_class?(class_str)
        class_str.match?(/\[\s*String\s*:|Dictionary\s*</)
      end

      # In UIKit mode, bindings require an id to reference the view.
      def warn_binding_without_id?
        true
      end

      # Infer type from variable name and attribute context (Swift types)
      def infer_type(var_name, attribute_name, component_type = nil)
        # confirmationDialog.actions -> (() -> AnyView)? (SwiftUI callback returning Button views)
        return '(() -> AnyView)?' if attribute_name == 'confirmationDialog.actions'

        # Callbacks with Int parameter
        return '((Int) -> Void)?' if %w[onTabChange onItemAppear].include?(var_name) || %w[onTabChange onItemAppear].include?(attribute_name)

        # TextField/TextView event handlers with UITextField/UITextView parameter
        text_field_events = %w[onBeginEditing onEndEditing onTextChange onDeleteBackward onChangeSelection]
        text_field_bool_events = %w[onShouldReturn onShouldClear onShouldBeginEditing onShouldEndEditing]
        text_field_change_events = %w[onShouldChangeCharacters]
        text_view_change_events = %w[onShouldChangeText]

        return '((UITextField) -> Void)?' if text_field_events.include?(var_name) || text_field_events.include?(attribute_name)
        return '((UITextField) -> Bool)?' if text_field_bool_events.include?(var_name) || text_field_bool_events.include?(attribute_name)
        return '((UITextField, NSRange, String) -> Bool)?' if text_field_change_events.include?(var_name) || text_field_change_events.include?(attribute_name)
        return '((UITextView, NSRange, String) -> Bool)?' if text_view_change_events.include?(var_name) || text_view_change_events.include?(attribute_name)

        # onClick, onXxx -> (() -> Void)? (Swift callback type)
        return '(() -> Void)?' if var_name.start_with?('on') && var_name[2]&.match?(/[A-Z]/)

        # xxxItems, xxxOptions, xxxList -> [Any]
        return '[Any]' if var_name.end_with?('Items', 'Options', 'List', 'Args', 'Subcommands')

        # isXxx, hasXxx, canXxx, shouldXxx -> Bool
        return 'Bool' if var_name.start_with?('is', 'has', 'can', 'should')

        # xxxVisibility -> String
        return 'String' if var_name.end_with?('Visibility')

        # xxxIndex, xxxCount, xxxTab -> Int
        return 'Int' if var_name.end_with?('Index', 'Count', 'Tab')

        # xxxMargin, xxxPadding -> CGFloat
        return 'CGFloat' if var_name.end_with?('Margin', 'Padding')

        # Based on attribute name
        case attribute_name
        when 'onTabChange', 'onItemAppear'
          '((Int) -> Void)?'
        when 'onClick', 'onValueChanged', 'onValueChange', 'onTap'
          '(() -> Void)?'
        when 'items'
          'CollectionDataSource'
        when 'sections'
          '[Any]'
        when 'visibility', 'text', 'fontColor', 'background'
          'String'
        when 'selectedIndex', 'width', 'height'
          'Int'
        when 'hidden', 'enabled', 'disabled'
          'Bool'
        when 'topMargin', 'bottomMargin', 'leftMargin', 'rightMargin', 'startMargin', 'endMargin'
          'CGFloat'
        when 'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight', 'paddingStart', 'paddingEnd'
          'CGFloat'
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
