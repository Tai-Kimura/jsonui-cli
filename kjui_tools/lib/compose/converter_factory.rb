# frozen_string_literal: true

require_relative 'view_registry'

module KjuiTools
  module Compose
    class ConverterFactory
      def initialize
        @view_registry = ViewRegistry.new
      end

      def create_converter(component, indent_level = 0, action_manager = nil, converter_factory = nil, view_registry = nil, binding_registry = nil)
        return nil unless component

        # Use self as converter_factory if not provided
        converter_factory ||= self
        view_registry ||= @view_registry

        # Determine component type
        type = determine_component_type(component)

        # Get converter class from registry
        converter_class = @view_registry.get_converter_class(type)

        # Create and return converter instance
        converter_class.new(
          component,
          indent_level,
          action_manager,
          converter_factory,
          view_registry,
          binding_registry
        )
      end

      private

      def determine_component_type(component)
        return 'View' unless component.is_a?(Hash)

        # Check for include first
        return 'Include' if component['include']

        # Get type from component
        type = component['type'] || 'View'

        # Handle orientation-based type determination
        if type == 'View' && component['orientation']
          case component['orientation']
          when 'horizontal'
            return 'Row'
          when 'vertical'
            return 'Column'
          end
        end

        # Map JSON types to Compose component types
        # Based on SwiftJsonUI's VIEW_TYPE_SET keys
        case type
        when 'Text'
          # Text is an alias for Label
          'Text'
        when 'Label'
          # Label maps to Text component (the actual Compose component name)
          'Text'
        when 'TextView'
          'TextView'
        when 'Button'
          'Button'
        when 'Image', 'NetworkImage', 'CircleImage'
          'Image'
        when 'TextField'
          'TextField'
        when 'Switch'
          'Switch'
        when 'Toggle'
          'Switch'  # Map Toggle to Switch
        when 'Slider'
          'Slider'
        when 'Progress', 'ProgressBar'
          'ProgressBar'
        when 'Scroll', 'ScrollView'
          'ScrollView'
        when 'Table', 'Collection'
          'LazyColumn'
        when 'Web', 'WebView'
          'Web'
        when 'Radio'
          'Radio'
        when 'Check', 'CheckBox'
          'CheckBox'
        when 'Segment'
          'Segment'
        when 'SelectBox', 'Spinner'
          'SelectBox'
        when 'Indicator'
          'Indicator'
        when 'GradientView'
          'GradientView'
        when 'Blur', 'BlurView'
          'BlurView'
        when 'CircleView'
          'CircleView'
        when 'IconLabel'
          'IconLabel'
        when 'Triangle'
          'Triangle'
        when 'SafeAreaView'
          'View'  # SafeAreaView maps to regular View in Compose
        else
          type
        end
      end
    end
  end
end
