# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative '../core/config_manager'
require_relative '../core/project_finder'
require_relative '../core/type_converter'
require_relative '../core/generated_marker'
require_relative '../core/data_model_updater_core'
require_relative 'style_loader'
require_relative 'include_expander'
require_relative 'helpers/string_manager_helper'

module SjuiTools
  module SwiftUI
    # iOS profile over the shared Data-model updater body
    # (lib/core/data_model_updater_core.rb — byte-identical mirror of
    # shared/core/data_model_updater_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb). Traversal/extraction live in
    # the shared core; this class owns the iOS constructor facts and
    # everything that emits Swift.
    class DataModelUpdater < ::JsonUIShared::DataModelUpdaterCore
      include Helpers::StringManagerHelper

      def initialize(mode: nil)
        @config = Core::ConfigManager.load_config
        @source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
        @layouts_dir = File.join(@source_path, @config['layouts_directory'] || 'Layouts')
        @data_dir = File.join(@source_path, @config['data_directory'] || 'Data')
        @styles_dir = File.join(@source_path, @config['styles_directory'] || 'Styles')
        @mode = mode || @config['mode'] || 'swiftui'
      end

      private

      # Skip files with "mode": "uikit" (SwiftUI data models don't need UIKit-only files)
      def skip_layout_file_extra?(file)
        json_content = JSON.parse(File.read(file))
        file_mode = json_content['mode']
        !!(file_mode && file_mode.downcase == 'uikit')
      rescue JSON::ParserError
        false
      end

      def expand_styles(json_data, _json_file)
        StyleLoader.load_and_merge(json_data, @styles_dir)
      end

      def expand_includes(json_data, dir)
        IncludeExpander.process_includes(json_data, dir)
      end

      def event_binding_attrs
        %w[onClick onValueChange onToggle onTextChange onChange onLongPress]
      end

      # onClick carries the callback in binding format: @{functionName}
      def onclick_action_name(node)
        return nil unless node['onClick'].is_a?(String)
        node['onClick'].gsub(/^@\{|\}$/, '')
      end

      def data_platform_filter
        'swift'
      end

      # Historical: the data[] mode filter accepts 'swiftui' regardless of
      # the constructor mode (this updater is only run for SwiftUI builds).
      def data_mode_filter
        'swiftui'
      end

      def boolean_class
        'Bool'
      end

      # Event conversion runs on the RAW item BEFORE TypeConverter
      # normalization to avoid double-wrapping the converted signature.
      def finalize_data_property(data_item, event_bindings)
        prop_name = data_item['name']
        raw_class = data_item['class'].to_s

        modified_item = data_item.dup
        if event_bindings[prop_name] && raw_class.include?('Event')
          # Get event type from type_mapping.json
          binding_info = event_bindings[prop_name]
          event_type = Core::TypeConverter.get_event_type(
            binding_info[:component],
            binding_info[:attribute],
            'swiftui'
          )

          if event_type
            # Convert Event to platform-specific type in the function signature
            # event_type is an array like ["String", "Bool"] for swiftui
            if event_type.is_a?(Array)
              # Convert to tuple type: String, Bool (without extra parens)
              # Replace (Event) with (String, Bool) - the parens are already there
              converted_type = event_type.join(', ')
              modified_item['class'] = raw_class.gsub('(Event)', "(#{converted_type})")
            else
              modified_item['class'] = raw_class.gsub('Event', event_type)
            end
          end
        end

        # Normalize type using TypeConverter (mode: swiftui) after Event replacement
        Core::TypeConverter.normalize_data_property(modified_item, 'swiftui')
      end

      def data_file_extension
        'swift'
      end

      def extract_type_name(content)
        if match = content.match(/struct\s+(\w+Data)\s*{/)
          match[1]
        else
          nil
        end
      end

      def generate_data_content(view_name, data_properties, onclick_actions = [], json_base_name: nil)
        needs_combine = data_properties.any? { |p| p['class'].to_s.include?('PassthroughSubject') || p['class'].to_s.include?('CurrentValueSubject') }
        combine_import = needs_combine ? "\nimport Combine" : ""
        marker_source = json_base_name ? "Layouts/#{json_base_name}.json" : "#{view_name}Data"
        marker_header = Core::GeneratedMarker.comment_header(
          source: marker_source,
          generator: "sjui build"
        )
        content = <<~SWIFT
        #{marker_header}

        import Foundation
        import SwiftUI
        import SwiftJsonUI#{combine_import}

        struct #{view_name}Data {
            // Data properties from JSON
        SWIFT

        if data_properties.empty?
          content += "    // No data properties defined in JSON\n"
        else
          # Add each property with correct type and default value
          data_properties.each do |prop|
            name = prop['name']
            class_type = prop['class']  # Use class name directly
            default_value = prop['defaultValue']

            # If no default value or nil, make it optional
            if default_value.nil? || default_value == 'nil'
              # Check if type already ends with '?' (already optional)
              if class_type.end_with?('?')
                content += "    var #{name}: #{class_type} = nil\n"
              else
                content += "    var #{name}: #{class_type}? = nil\n"
              end
            else
              formatted_value = format_default_value(default_value, class_type)
              content += "    var #{name}: #{class_type} = #{formatted_value}\n"
            end
          end
        end

        # Add onclick action properties as closures (skip if already in data_properties)
        data_prop_names = data_properties.map { |p| p['name'] }
        extra_onclick_actions = onclick_actions.reject { |action| data_prop_names.include?(action) }
        if !extra_onclick_actions.empty?
          content += "\n"
          content += "    // onClick action callbacks\n"
          extra_onclick_actions.each do |action|
            content += "    var #{action}: (() -> Void)? = nil\n"
          end
        end

        # Add update function to allow dynamic property updates
        content += "\n"
        content += "    // Update properties from dictionary\n"
        content += "    mutating func update(dictionary: [String: Any]) {\n"

        if !data_properties.empty?
          data_properties.each do |prop|
            name = prop['name']
            class_type = prop['class']

            # Generate update code based on type
            content += "        if let value = dictionary[\"#{name}\"] {\n"

            case class_type
            when 'String'
              content += "            if let stringValue = value as? String {\n"
              content += "                self.#{name} = stringValue\n"
              content += "            }\n"
            when 'Int'
              content += "            if let intValue = value as? Int {\n"
              content += "                self.#{name} = intValue\n"
              content += "            }\n"
            when 'Double'
              content += "            if let doubleValue = value as? Double {\n"
              content += "                self.#{name} = doubleValue\n"
              content += "            }\n"
            when 'Bool'
              content += "            if let boolValue = value as? Bool {\n"
              content += "                self.#{name} = boolValue\n"
              content += "            }\n"
            when 'CGFloat'
              content += "            if let floatValue = value as? CGFloat {\n"
              content += "                self.#{name} = floatValue\n"
              content += "            } else if let doubleValue = value as? Double {\n"
              content += "                self.#{name} = CGFloat(doubleValue)\n"
              content += "            }\n"
            else
              # For custom types, try to cast directly
              content += "            if let typedValue = value as? #{class_type} {\n"
              content += "                self.#{name} = typedValue\n"
              content += "            }\n"
            end

            content += "        }\n"
          end
        else
          # No properties, but still include empty function body
          content += "        // No properties to update\n"
        end

        content += "    }\n"

        # Add toDictionary function
        content += "\n"
        content += "    // Convert properties to dictionary for Dynamic mode\n"
        content += "    func toDictionary() -> [String: Any] {\n"
        content += "        var dict: [String: Any] = [:]\n"

        # Add data properties
        if !data_properties.empty?
          content += "        \n"
          content += "        // Data properties\n"
          data_properties.each do |prop|
            name = prop['name']
            class_type = prop['class']
            default_value = prop['defaultValue']

            # If it's optional, check for nil
            if default_value.nil? || default_value == 'nil'
              content += "        if let value = #{name} {\n"
              content += "            dict[\"#{name}\"] = value\n"
              content += "        }\n"
            else
              content += "        dict[\"#{name}\"] = #{name}\n"
            end
          end
        end

        # Add onclick actions not already in data_properties
        if !extra_onclick_actions.empty?
          content += "        \n"
          content += "        // Add onclick action callbacks\n"
          extra_onclick_actions.each do |action|
            content += "        if let #{action} = #{action} {\n"
            content += "            dict[\"#{action}\"] = #{action}\n"
            content += "        }\n"
          end
        end

        if data_properties.empty? && onclick_actions.empty?
          content += "        // No properties to add\n"
        end

        content += "        \n"
        content += "        return dict\n"
        content += "    }\n"

        # Add toDictionary(binding:) for Dynamic mode reactivity
        content += "\n"
        content += "    #if DEBUG\n"
        content += "    // Convert properties to binding dictionary for Dynamic mode reactivity\n"
        content += "    // SwiftUI.Binding<T> values enable automatic re-rendering on changes\n"
        content += "    func toDictionary(binding dataBinding: SwiftUI.Binding<#{view_name}Data>) -> [String: Any] {\n"
        content += "        var dict: [String: Any] = [:]\n"

        if !data_properties.empty?
          content += "        \n"
          content += "        // Data properties as SwiftUI.Binding for reactivity\n"
          data_properties.each do |prop|
            name = prop['name']
            class_type = prop['class']
            default_value = prop['defaultValue']
            is_optional = default_value.nil? || default_value == 'nil'

            # Determine if type is bindable (primitive types)
            binding_type = case class_type.gsub('?', '')
              when 'String' then 'String'
              when 'Bool' then 'Bool'
              when 'Int' then 'Int'
              when 'Double' then 'Double'
              when 'CGFloat' then 'CGFloat'
              else nil
            end

            # Skip closure types
            if class_type.include?('->') || class_type.include?('Void')
              # Closure: keep as plain value
              content += "        if let #{name} = #{name} {\n"
              content += "            dict[\"#{name}\"] = #{name}\n"
              content += "        }\n"
            elsif binding_type
              # Bindable primitive type
              default_for_type = case binding_type
                when 'String' then '""'
                when 'Bool' then 'false'
                when 'Int' then '0'
                when 'Double' then '0.0'
                when 'CGFloat' then '0.0'
                else '""'
              end

              if is_optional
                content += "        if #{name} != nil {\n"
                content += "            dict[\"#{name}\"] = SwiftUI.Binding<#{binding_type}>(\n"
                content += "                get: { dataBinding.wrappedValue.#{name} ?? #{default_for_type} },\n"
                content += "                set: { dataBinding.wrappedValue.#{name} = $0 }\n"
                content += "            )\n"
                content += "        }\n"
              else
                content += "        dict[\"#{name}\"] = SwiftUI.Binding<#{binding_type}>(\n"
                content += "            get: { dataBinding.wrappedValue.#{name} },\n"
                content += "            set: { dataBinding.wrappedValue.#{name} = $0 }\n"
                content += "        )\n"
              end
            else
              # Non-bindable type (custom struct, array, etc.): keep as plain value
              if is_optional
                content += "        if let value = #{name} {\n"
                content += "            dict[\"#{name}\"] = value\n"
                content += "        }\n"
              else
                content += "        dict[\"#{name}\"] = #{name}\n"
              end
            end
          end
        end

        # Add onclick callbacks (same as toDictionary)
        if !extra_onclick_actions.empty?
          content += "        \n"
          content += "        // Add onclick action callbacks\n"
          extra_onclick_actions.each do |action|
            content += "        if let #{action} = #{action} {\n"
            content += "            dict[\"#{action}\"] = #{action}\n"
            content += "        }\n"
          end
        end

        if data_properties.empty? && onclick_actions.empty?
          content += "        // No properties to add\n"
        end

        content += "        \n"
        content += "        return dict\n"
        content += "    }\n"
        content += "    #endif\n"

        content += "}\n"
        content += "\n"
        content += Core::GeneratedMarker.comment_footer + "\n"
        content
      end

      def format_default_value(value, json_class)
        if json_class == 'String'
          # Handle '' as empty string (common shorthand)
          if value == "''" || value.to_s.empty?
            '""'
          else
            # Use StringManager for localized strings
            get_text_with_string_manager("\"#{value}\"")
          end
        elsif json_class == 'CollectionDataSource' && (value.is_a?(Array) || value.is_a?(Hash))
          # Materialize the declared defaultValue (INTERACTIVE_HOST_CONTRACT
          # §4 shapes: shorthand cell array / explicit sections object) into
          # a real initializer — passing the raw Ruby value through emitted
          # invalid Swift and dropped declared cells (31 F4 Phase 2).
          collection_data_source_literal(value)
        else
          # Check if default value contains a type constructor that needs mode conversion
          # e.g., "CollectionDataSource()" -> "UIKitCollectionDataSource()" in UIKit mode
          val_str = value.to_s
          Core::TypeConverter::MODE_TYPE_MAPPING.each do |generic_type, mode_map|
            mode = @mode || 'swiftui'
            mapped_type = mode_map[mode]
            if mapped_type && mapped_type != generic_type && val_str.include?(generic_type)
              return val_str.gsub(generic_type, mapped_type)
            end
          end
          value
        end
      end

      # CollectionDataSource defaultValue → Swift initializer literal.
      # Shapes (INTERACTIVE_HOST_CONTRACT.md §4): shorthand `[ {...} ]`
      # (one section holding these cell dicts) or explicit
      # `{"sections" => [{"cell" => name?, "cells" => [ {...} ]}]}`.
      # Cell dicts emit as [String: Any] literals with string/number/bool
      # values only.
      def collection_data_source_literal(value)
        sections =
          if value.is_a?(Array)
            [{ 'cell' => nil, 'cells' => value }]
          elsif value.is_a?(Hash) && value['sections'].is_a?(Array)
            value['sections']
          else
            []
          end
        return 'CollectionDataSource()' if sections.empty?

        section_literals = sections.map do |section|
          next nil unless section.is_a?(Hash)
          cells = section['cells'].is_a?(Array) ? section['cells'] : []
          cell_dicts = cells.select { |c| c.is_a?(Hash) }.map do |cell|
            pairs = cell.map do |k, v|
              literal =
                case v
                when String then v.inspect
                when true, false, Numeric then v.to_s
                end
              literal && "#{k.to_s.inspect}: #{literal}"
            end.compact
            pairs.empty? ? '[:]' : "[#{pairs.join(', ')}]"
          end
          view_name = section['cell'].is_a?(String) ? section['cell'].inspect : '""'
          "CollectionDataSection(cells: (viewName: #{view_name}, " \
            "data: [#{cell_dicts.join(', ')}]))"
        end.compact

        "CollectionDataSource(sections: [#{section_literals.join(', ')}])"
      end
    end
  end
end
