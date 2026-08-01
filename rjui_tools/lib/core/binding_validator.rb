#!/usr/bin/env ruby
# frozen_string_literal: true

require_relative 'binding_validator_core'

module RjuiTools
  module Core
    # Web profile over the shared binding-validator body
    # (lib/core/binding_validator_core.rb — byte-identical mirror of
    # shared/core/binding_validator_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb). Canonical rules, Embed
    # grammar (now including navigationMode/camelCase, which rjui
    # previously lacked), cell scope, include hygiene and unused-property
    # tracking live in the shared core; this class owns the
    # JavaScript-language advisory patterns, the cross-platform type
    # suggestions, and the react-only used-property sources
    # (auto-generated onXxxChange handlers, partialAttributes handlers).
    class BindingValidator < ::JsonUIShared::BindingValidatorCore
      # Patterns that indicate business logic in bindings (JS spellings)
      # Note: Order matters - more specific patterns should come before general ones
      BUSINESS_LOGIC_PATTERNS = [
        {
          pattern: /\?.*:/,
          message: "ternary operator (? :) - compute value in ViewModel (e.g., showContent: currentTab === 0)"
        },
        {
          pattern: /===|==|!==|!=|<=|>=|<|>/,
          message: "comparison operator - move comparison to ViewModel"
        },
        {
          pattern: /viewModel\./,
          message: "viewModel. prefix - use direct property name (e.g., @{propertyName} instead of @{viewModel.propertyName})"
        },
        {
          pattern: /\+\+|--/,
          message: "increment/decrement - update value in ViewModel"
        },
        {
          pattern: /(?<!\+)\+(?!\+)|(?<!-)\/|(?<![a-zA-Z_])\*|(?<![a-zA-Z_])%/,
          message: "arithmetic operator - compute value in ViewModel"
        },
        {
          pattern: /&&|\|\|/,
          message: "logical operator (&&, ||) - move logic to ViewModel"
        },
        {
          pattern: /\w+\([^)]+\)/,
          message: "function call with arguments - move to ViewModel"
        },
        {
          pattern: /\w+\(\s*\)/,
          message: "function call - move to ViewModel computed property"
        },
        {
          pattern: /`[^`]*\$\{/,
          message: "string interpolation - compose string in ViewModel"
        },
        {
          pattern: /\[[^\]]*[+\-*\/<>=]/,
          message: "complex array subscript - simplify in ViewModel"
        },
        {
          pattern: /\.\.\./,
          message: "spread operator - handle in ViewModel"
        }
      ].freeze

      private

      def platform_id
        'react'
      end

      def log_tag
        'RJUI'
      end

      def business_logic_patterns
        BUSINESS_LOGIC_PATTERNS
      end

      # Pages/components without data definitions get bindings from
      # ViewModel props — the undefined-variable check would be all noise.
      def skip_undefined_without_data_section?
        true
      end

      # Infer type from variable name and attribute context
      # (cross-platform spellings — works with Swift, Kotlin, React)
      def infer_type(var_name, attribute_name, component_type = nil)
        # onTabChange -> ((Int) -> Void)? (callback with Int parameter)
        return '((Int) -> Void)?' if var_name == 'onTabChange' || attribute_name == 'onTabChange'

        # onClick, onXxx -> (() -> Void)? (cross-platform callback type)
        return '(() -> Void)?' if var_name.start_with?('on') && var_name[2]&.match?(/[A-Z]/)

        # xxxItems, xxxOptions, xxxList -> Array
        return 'Array' if var_name.end_with?('Items', 'Options', 'List', 'Args', 'Subcommands')

        # isXxx, hasXxx, canXxx, shouldXxx -> Bool
        return 'Bool' if var_name.start_with?('is', 'has', 'can', 'should')

        # xxxVisibility -> String
        return 'String' if var_name.end_with?('Visibility')

        # xxxIndex, xxxCount, xxxTab -> Int
        return 'Int' if var_name.end_with?('Index', 'Count', 'Tab')

        # Based on attribute name
        case attribute_name
        when 'onTabChange'
          '((Int) -> Void)?'
        when 'onClick', 'onValueChanged', 'onValueChange', 'onTap'
          '(() -> Void)?'
        when 'items', 'sections'
          'Array'
        when 'visibility', 'text', 'fontColor', 'background'
          'String'
        when 'selectedIndex', 'width', 'height'
          'Int'
        when 'hidden', 'enabled', 'disabled'
          'Bool'
        when 'src', 'srcName'
          # NetworkImage uses URL string, Image/CircleImage uses Image type
          if component_type&.include?('Network')
            'String'
          else
            'Image'
          end
        else
          'any'
        end
      end

      # React-only used-property sources: converters synthesize
      # onXxxChange handlers from two-way-style bindings, and
      # partialAttributes handler references never got scanned.
      def collect_platform_used_properties(component, component_type)
        collect_auto_generated_handlers(component, component_type)
        collect_partial_attribute_handlers(component)
      end

      # A handler named by a partialAttributes entry IS a use.
      #
      # These are ordinary handler references, just nested one level deeper
      # than the node's own onclick, and the scan never descended into them.
      # A consumer who declared the handler got "defined but never used";
      # one who omitted it got a generated Data type without the property.
      # There was no spelling that satisfied both, so the zero-warning gate
      # made partial handlers unusable.
      def collect_partial_attribute_handlers(component)
        partials = component['partialAttributes']
        return unless partials.is_a?(Array)

        partials.each do |partial|
          next unless partial.is_a?(Hash)

          %w[onclick onClick].each do |key|
            handler = partial[key]
            next unless handler.is_a?(String) && !handler.empty?

            if handler.start_with?('@{') && handler.end_with?('}')
              extract_variables(handler[2..-2]).each do |var|
                @used_properties << var if @data_properties.include?(var)
              end
            elsif @data_properties.include?(handler)
              @used_properties << handler
            end
          end
        end
      end

      # Collect auto-generated onChange handler names that converters create from bindings
      # e.g. text: "@{email}" → onEmailChange, selectedValue: "@{carrier}" → onCarrierChange
      def collect_auto_generated_handlers(component, component_type)
        # TextField / TextView: text binding → onXxxChange
        if %w[TextField EditText TextView TextArea TextInput].include?(component_type)
          text = component['text']
          if text.is_a?(String) && text.start_with?('@{') && text.end_with?('}')
            prop = text[2..-2]
            handler = "on#{prop[0].upcase}#{prop[1..]}Change"
            @used_properties << handler if @data_properties.include?(handler)
          end
        end

        # SelectBox: selectedValue/value binding → onXxxChange
        if %w[SelectBox Spinner Picker].include?(component_type)
          value_key = component['selectedValue'] || component['value'] || component['selectedIndex']
          if value_key.is_a?(String) && value_key.start_with?('@{') && value_key.end_with?('}')
            prop = value_key[2..-2]
            handler = "on#{prop[0].upcase}#{prop[1..]}Change"
            @used_properties << handler if @data_properties.include?(handler)
          end
        end
      end
    end
  end
end
