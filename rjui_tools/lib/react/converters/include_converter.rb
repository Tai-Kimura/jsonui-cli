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
          merged_data.merge!(attributes['shared_data']) if attributes['shared_data'].is_a?(Hash)
          merged_data.merge!(json['data']) if json['data'].is_a?(Hash)

          # The partial receives a single `data` prop (Partial<XxxData> —
          # the component merges it over its createXxxData() defaults), so
          # the include-site map becomes one object literal, not individual
          # props. Bindings resolve through add_viewmodel_data_prefix like
          # every built-in converter (they reference the PARENT's data).
          data_prop = build_data_prop(merged_data)

          id_attr = build_id_attr

          if data_prop.empty?
            "#{indent_str(indent)}<#{component_name}#{id_attr} />"
          else
            "#{indent_str(indent)}<#{component_name}#{id_attr} #{data_prop} />"
          end
        end

        private

        def build_data_prop(data)
          return '' if data.empty?

          pairs = data.map do |key, value|
            "#{key}: #{format_prop_value(value)}"
          end

          "data={{ #{pairs.join(', ')} }}"
        end

        def format_prop_value(value)
          case value
          when String
            if (m = value.match(/\A@\{([^}]+)\}\z/))
              # Whole-value binding -> parent data reference
              add_viewmodel_data_prefix(m[1].gsub(/^this\./, ''))
            elsif value.match?(/@\{([^}]+)\}/)
              # Interpolated binding(s) -> template literal
              interpolated = value.gsub(/@\{([^}]+)\}/) do
                "${#{add_viewmodel_data_prefix(::Regexp.last_match(1).gsub(/^this\./, ''))}}"
              end
              "`#{interpolated.gsub('`') { '\\`' }}`"
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
