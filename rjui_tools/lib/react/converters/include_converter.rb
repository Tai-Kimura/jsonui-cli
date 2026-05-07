# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class IncludeConverter < BaseConverter
        def convert(indent = 2)
          include_path = json['include']

          unless include_path
            return "#{indent_str(indent)}{/* Error: Include component must have 'include' property */}"
          end

          # Generate component name from include path
          # included_1 -> Included1, main_menu -> MainMenu
          base_name = include_path.split('/').last
          component_name = base_name.split('_').map(&:capitalize).join

          # Merge shared_data and data
          merged_data = {}
          merged_data.merge!(json['shared_data']) if json['shared_data'].is_a?(Hash)
          merged_data.merge!(json['data']) if json['data'].is_a?(Hash)

          # Build props
          props = build_props(merged_data)

          id_attr = build_id_attr

          if props.empty?
            "#{indent_str(indent)}<#{component_name}#{id_attr} />"
          else
            "#{indent_str(indent)}<#{component_name}#{id_attr} #{props} />"
          end
        end

        private

        def build_props(data)
          return '' if data.empty?

          props = data.map do |key, value|
            formatted_value = format_prop_value(value)
            "#{key}={#{formatted_value}}"
          end

          props.join(' ')
        end

        def format_prop_value(value)
          case value
          when String
            if value.match?(/@\{([^}]+)\}/)
              # @{xxx} binding -> direct reference
              value.gsub(/@\{([^}]+)\}/) do
                var_name = ::Regexp.last_match(1)
                # Remove 'this.' prefix if present
                var_name.gsub(/^this\./, '')
              end
            else
              # Regular string
              "\"#{value}\""
            end
          when Hash
            # Nested object
            pairs = value.map { |k, v| "#{k}: #{format_prop_value(v)}" }
            "{ #{pairs.join(', ')} }"
          when Array
            # Array
            items = value.map { |v| format_prop_value(v) }
            "[#{items.join(', ')}]"
          when Numeric
            value.to_s
          when TrueClass, FalseClass
            value.to_s
          when NilClass
            'null'
          else
            "\"#{value}\""
          end
        end
      end
    end
  end
end
