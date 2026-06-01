# frozen_string_literal: true

require 'fileutils'
require 'json'
require_relative '../../core/logger'
require_relative '../../core/generated_marker'
require_relative 'swift_component_generator'
require_relative 'adapter_generator'

module SjuiTools
  module SwiftUI
    module Generators
      class ConverterGenerator
        def initialize(name, options = {})
          @name = name
          # Keep original PascalCase name for component, add Converter suffix for class
          @component_pascal_case = name  # e.g., MyTestCard
          @class_name = name + "Converter"  # e.g., MyTestCardConverter
          @options = options
          @logger = Core::Logger
          @command = build_command_string(name, options)
        end

        def build_command_string(name, options)
          cmd = "sjui g converter #{name}"
          if options[:attributes] && !options[:attributes].empty?
            attrs = options[:attributes].map { |k, v| "#{k}:#{v}" }.join(",")
            cmd += " --attributes=\"#{attrs}\""
          end
          cmd += " --container" if options[:is_container] == true
          cmd += " --no-container" if options[:is_container] == false
          cmd
        end

        def generate
          @logger.info "Generating custom converter: #{@class_name}"

          # Create converter file
          create_converter_file

          # Update mappings file
          update_mappings_file

          # Generate attribute definition file
          generate_attribute_definition_file

          # Create Swift file using separate generator (pass command for comment)
          swift_options = @options.merge(command: @command)
          swift_generator = SwiftComponentGenerator.new(@name, swift_options)
          swift_generator.generate

          # Generate adapter file if adapter_directory is configured (pass command for comment)
          adapter_generator = AdapterGenerator.new(@name, swift_options)
          adapter_generator.generate

          @logger.success "Successfully generated converter: #{@class_name}"
          @logger.info "Converter file created at: views/extensions/#{@name}_converter.rb"
          @logger.info "Mappings file updated with '#{@component_pascal_case}' => '#{@class_name}'"

          # Update membership exceptions to exclude the extensions directory
          update_membership_exceptions_if_needed
        end

        private

        def create_converter_file
          # Ensure views/extensions directory exists
          # Check if we're in a test app or main SwiftJsonUI
          if File.exist?(File.join(Dir.pwd, 'sjui_tools'))
            # Test app structure
            extensions_dir = File.join(Dir.pwd, 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions')
          else
            # Main SwiftJsonUI structure
            extensions_dir = File.join(Dir.pwd, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions')
          end
          FileUtils.mkdir_p(extensions_dir)

          # Convert name to snake_case for file name
          snake_case_name = @name.gsub(/([A-Z]+)([A-Z][a-z])/,'\1_\2').
                                  gsub(/([a-z\d])([A-Z])/,'\1_\2').
                                  downcase
          file_path = File.join(extensions_dir, "#{snake_case_name}_converter.rb")

          if File.exist?(file_path)
            # `jui build` (and other non-interactive flows) set JUI_SKIP_EXISTING=1
            # so the prompt is bypassed and existing converter files are left alone.
            if ENV['JUI_SKIP_EXISTING'] == '1'
              @logger.info "Skipped existing converter: #{file_path}"
              return
            end
            @logger.warn "Converter file already exists: #{file_path}"
            print "Overwrite? (y/n): "
            response = gets.chomp.downcase
            return unless response == 'y'
          end

          File.write(file_path, converter_template)
          @logger.info "Created converter file: #{file_path}"
        end

        def update_mappings_file
          # Check if we're in a test app or main SwiftJsonUI
          if File.exist?(File.join(Dir.pwd, 'sjui_tools'))
            # Test app structure
            mappings_file = File.join(Dir.pwd, 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'converter_mappings.rb')
          else
            # Main SwiftJsonUI structure
            mappings_file = File.join(Dir.pwd, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'converter_mappings.rb')
          end

          # Create new mappings file if it doesn't exist
          if !File.exist?(mappings_file)
            create_initial_mappings_file
            return
          end

          # Read existing mappings
          content = File.read(mappings_file)

          # Check if mapping already exists
          component_type = @component_pascal_case
          if content.include?("'#{component_type}' =>")
            @logger.warn "Mapping for '#{component_type}' already exists in converter_mappings.rb"
            return
          end

          # Add new mapping
          new_mapping = "          '#{component_type}' => '#{@class_name}',"

          # Insert the new mapping before the closing brace of CONVERTER_MAPPINGS
          content.sub!(/(CONVERTER_MAPPINGS = \{.*?)(,?)(\s*)(        \}\.freeze)/m) do
            existing_mappings = $1
            last_comma = $2
            whitespace = $3
            closing = $4

            # If there are existing mappings, add the new one with proper formatting
            if existing_mappings =~ /=>/
              # Ensure the last existing mapping has a comma, then add the new mapping
              "#{existing_mappings},\n#{new_mapping}\n#{closing}"
            else
              # First mapping
              "#{existing_mappings}\n#{new_mapping}\n#{closing}"
            end
          end

          File.write(mappings_file, content)
          @logger.info "Updated converter_mappings.rb with new mapping"
        end

        def create_initial_mappings_file
          # Ensure views/extensions directory exists
          # Check if we're in a test app or main SwiftJsonUI
          if File.exist?(File.join(Dir.pwd, 'sjui_tools'))
            # Test app structure
            extensions_dir = File.join(Dir.pwd, 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions')
          else
            # Main SwiftJsonUI structure
            extensions_dir = File.join(Dir.pwd, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions')
          end
          FileUtils.mkdir_p(extensions_dir)

          mappings_file = File.join(extensions_dir, 'converter_mappings.rb')

          content = <<~RUBY
            # frozen_string_literal: true

            # This file maps custom component types to their converter classes
            # Auto-generated by sjui g converter command

            module SjuiTools
              module SwiftUI
                module Views
                  module Extensions
                    CONVERTER_MAPPINGS = {
                      '#{@component_pascal_case}' => '#{@class_name}',
                    }.freeze
                  end
                end
              end
            end
          RUBY

          File.write(mappings_file, content)
          @logger.info "Created converter_mappings.rb with initial mapping"
        end

        def generate_attribute_definition_file
          # Skip if no attributes and not a container
          has_attributes = @options[:attributes] && !@options[:attributes].empty?
          is_container = @options[:is_container] == true
          return if !has_attributes && !is_container

          # Determine directory path
          if File.exist?(File.join(Dir.pwd, 'sjui_tools'))
            # Test app structure
            attr_defs_dir = File.join(Dir.pwd, 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions')
          else
            # Main SwiftJsonUI structure
            attr_defs_dir = File.join(Dir.pwd, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions')
          end

          # Create directory if it doesn't exist
          FileUtils.mkdir_p(attr_defs_dir)

          # Build attribute definitions
          attributes = {}
          if has_attributes
            @options[:attributes].each do |key, type|
              # Remove @ prefix if this is a binding attribute
              actual_key = key.start_with?('@') ? key[1..-1] : key

              attributes[actual_key] = build_attribute_definition(actual_key, type)
            end
          end

          # Add child/children for container components
          if is_container
            attributes["child"] = { "type" => "array", "description" => "Child component(s)" }
            attributes["children"] = { "type" => "array", "description" => "Child components (alias for child)" }
          end

          # Build JSON structure (prefix with _generated marker so LLM/Agent tools
          # know the file is regenerated on every `sjui g converter` run).
          json_content = {
            "_generated" => Core::GeneratedMarker.json_marker(
              source: @component_pascal_case,
              generator: @command
            ),
            @component_pascal_case => attributes
          }

          # Write to file
          file_path = File.join(attr_defs_dir, "#{@component_pascal_case}.json")
          File.write(file_path, JSON.pretty_generate(json_content))

          @logger.info "Created attribute definition file: attribute_definitions/#{@component_pascal_case}.json"
        end

        # Map type string to JSON schema type (supports binding for all types)
        # @param type [String] The type string from options
        # @return [Array, String] JSON schema type(s) - array for binding support
        def map_type_to_json_type(type)
          case type.downcase
          when 'string'
            ['string', 'binding']
          when 'int', 'integer'
            ['number', 'binding']
          when 'double', 'float'
            ['number', 'binding']
          when 'bool', 'boolean'
            ['boolean', 'binding']
          when 'color'
            # Color accepts either a semantic key ("dark_brown_text") or a
            # binding. format_color_value handles both at runtime.
            ['string', 'binding']
          else
            # Custom class types must use binding syntax (@{propertyName})
            'binding'
          end
        end

        def build_attribute_definition(actual_key, type)
          {
            "type" => map_type_to_json_type(type),
            "description" => "#{actual_key} attribute"
          }
        end

        def converter_template
          marker_header = Core::GeneratedMarker.comment_header(
            source: @component_pascal_case,
            generator: @command,
            prefix: "#"
          )
          marker_footer = Core::GeneratedMarker.comment_footer(prefix: "#")
          <<~RUBY
            # frozen_string_literal: true

            #{marker_header}

            require_relative '../base_view_converter'
            require_relative '../responsive_helper'

            module SjuiTools
              module SwiftUI
                module Views
                  module Extensions
                    class #{@class_name} < BaseViewConverter
                      def initialize(component, indent_level = 0, action_manager = nil, converter_factory = nil, view_registry = nil, binding_registry = nil)
                        super(component, indent_level, action_manager, binding_registry)
                        @factory = converter_factory
                        @registry = view_registry
                      end

                      def convert
                        # Responsive override (regression: sjui-markdown-text-converter-ignores-responsive)
                        # When this component has a `responsive` block, route through
                        # ResponsiveHelper.generate_leaf_function so the size-class
                        # branches (maxWidth / centerHorizontal / padding / margin /
                        # background / cornerRadius / ...) take effect. Without this
                        # the override silently drops, since BaseViewConverter#convert
                        # does not check responsive — that's ViewConverter's role for
                        # built-in `View` containers, and each extension converter has
                        # to opt in on its own surface.
                        if JsonUIShared::ResponsiveResolver.responsive?(@component) && @factory
                          func_name = @factory.next_responsive_name
                          func_code = SjuiTools::SwiftUI::Views::ResponsiveHelper.generate_leaf_function(
                            func_name, @component, @factory, @indent_level,
                            @action_manager, @registry, @binding_registry
                          )
                          @factory.register_responsive_function(func_code)
                          add_line "\#{func_name}()"
                          return generated_code
                        end

            #{generate_container_check}

                        # Collect parameters
                        params = []
            #{generate_parameter_collection}

                        if is_container
                          # Container component with children
                          if params.empty?
                            add_line "#{@component_pascal_case} {"
                          else
                            add_line "#{@component_pascal_case}("
                            indent do
                              params.each_with_index do |param, index|
                                if index == params.length - 1
                                  add_line param
                                else
                                  add_line "\#{param},"
                                end
                              end
                            end
                            add_line ") {"
                          end

                          # Process children
                          indent do
                            process_children
                          end

                          add_line "}"
                        else
                          # Non-container component
                          if params.empty?
                            add_line "#{@component_pascal_case}()"
                          else
                            add_line "#{@component_pascal_case}("
                            indent do
                              params.each_with_index do |param, index|
                                if index == params.length - 1
                                  add_line param
                                else
                                  add_line "\#{param},"
                                end
                              end
                            end
                            add_line ")"
                          end
                        end

            #{generate_modifiers_code}

                        generated_code
                      end

                      private

                      def component_name
                        "#{@component_pascal_case}"
                      end

                      # Process children components (handles both 'children' and 'child' keys)
                      def process_children
                        # Handle both 'children' and 'child' keys (both are arrays)
                        child_array = @component['children'] || @component['child']

                        if child_array && child_array.is_a?(Array)
                          child_array.each do |child|
                            child_converter = @factory.create_converter(child, @indent_level, @action_manager, @factory, @registry)
                            @generated_code.concat(child_converter.convert.split("\\n"))
                          end
                        end
                      end

                      # Helper method to format value based on type
                      # @param is_binding_attr [Boolean] if true, use $data. (Binding), otherwise data. (read-only)
                      def format_value(value, type, is_binding_attr: false)
                        return nil if value.nil?

                        # Check if it's a binding expression @{propertyName}
                        if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
                          # Extract property name and return as binding or read-only
                          property_name = value[2..-2]  # Remove @{ and }
                          prefix = is_binding_attr ? "$data" : "data"
                          return "\#{prefix}.\#{property_name}"
                        end

                        case type.downcase
                        when 'string'
                          '"\' + value.to_s + '"'
                        when 'int', 'integer'
                          value.to_s
                        when 'double', 'float'
                          value.to_s
                        when 'bool', 'boolean'
                          return nil if value.nil?
                          value.to_s.downcase
                        when 'color'
                          format_color_value(value)
                        when 'edgeinsets'
                          format_edge_insets_value(value)
                        else
                          value.to_s
                        end
                      end

                      def format_color_value(value)
                        return nil unless value
                        if value.is_a?(String) && value.start_with?('#')
                          # Parse hex color
                          hex = value.delete('#')
                          r = hex[0..1].to_i(16) / 255.0
                          g = hex[2..3].to_i(16) / 255.0
                          b = hex[4..5].to_i(16) / 255.0
                          "Color(red: \#{r}, green: \#{g}, blue: \#{b})"
                        elsif value.is_a?(Hash)
                          r = value['red'] || value['r'] || 0
                          g = value['green'] || value['g'] || 0
                          b = value['blue'] || value['b'] || 0
                          "Color(red: \#{r}, green: \#{g}, blue: \#{b})"
                        else
                          "SwiftJsonUIConfiguration.shared.getColor(for: \\"\#{value}\\") ?? Color.clear"
                        end
                      end

                      def format_edge_insets_value(value)
                        return nil unless value
                        if value.is_a?(Hash)
                          top = value['top'] || 0
                          leading = value['leading'] || value['left'] || 0
                          bottom = value['bottom'] || 0
                          trailing = value['trailing'] || value['right'] || 0
                          "EdgeInsets(top: \#{top}, leading: \#{leading}, bottom: \#{bottom}, trailing: \#{trailing})"
                        elsif value.is_a?(Numeric)
                          "EdgeInsets(top: \#{value}, leading: \#{value}, bottom: \#{value}, trailing: \#{value})"
                        else
                          nil
                        end
                      end
                    end
                  end
                end
              end
            end

            #{marker_footer}
          RUBY
        end

        def generate_container_check
          case @options[:is_container]
          when true
            "            # Force container mode\n            is_container = true\n"
          when false
            "            # Force non-container mode\n            is_container = false\n"
          else
            "            # Auto-detect container based on children or child\n            is_container = (@component['children'] && !@component['children'].empty?) || (@component['child'] && !@component['child'].empty?)\n"
          end
        end

        def generate_parameter_collection
          return "" if !@options[:attributes] || @options[:attributes].empty?

          lines = []
          @options[:attributes].each do |key, type|
            # Check if this is a binding property (starts with @)
            # @-prefixed attributes generate @Binding var in Swift → use $data. (Binding)
            # Non-@ attributes generate let in Swift → use data. (read-only)
            is_binding = key.start_with?('@')
            actual_key = is_binding ? key[1..-1] : key
            data_prefix = is_binding ? "$data" : "data"
            # Check if we need to handle the key existing vs nil differently
            if is_binding
              # Binding property - always expect @{} format, use $data. (Binding)
              lines << "            if @component['#{actual_key}']"
              lines << "              value = @component['#{actual_key}']"
              lines << "              if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')"
              lines << "                property_name = value[2..-2]"
              lines << '                params << "' + "#{actual_key}: #{data_prefix}." + '#{property_name}"'
              lines << "              else"
              lines << "                # For binding properties, assume direct property binding if not @{} format"
              lines << '                params << "' + "#{actual_key}: #{data_prefix}." + '#{value}"'
              lines << "              end"
              lines << "            end"
            elsif type.downcase == 'bool' || type.downcase == 'boolean'
              lines << "            if @component.key?('#{actual_key}')"
              lines << "              value = @component['#{actual_key}']"
              lines << "              if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')"
              lines << "                # Handle binding - use #{data_prefix}. (#{is_binding ? 'Binding' : 'read-only'})"
              lines << "                property_name = value[2..-2]"
              lines << '                params << "' + "#{actual_key}: #{data_prefix}." + '#{property_name}"'
              lines << "              else"
              lines << "                # Handle static value"
              lines << "                formatted_value = format_value(value, '#{type}')"
              lines << '                params << "' + "#{actual_key}: " + '#{formatted_value}" unless formatted_value.nil?'
              lines << "              end"
              lines << "            end"
            else
              lines << "            if @component['#{actual_key}']"
              lines << "              value = @component['#{actual_key}']"
              lines << "              if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')"
              lines << "                # Handle binding - use #{data_prefix}. (#{is_binding ? 'Binding' : 'read-only'})"
              lines << "                property_name = value[2..-2]"
              lines << '                params << "' + "#{actual_key}: #{data_prefix}." + '#{property_name}"'
              lines << "              else"
              lines << "                # Handle static value"
              lines << "                formatted_value = format_value(value, '#{type}')"
              lines << '                params << "' + "#{actual_key}: " + '#{formatted_value}" if formatted_value'
              lines << "              end"
              lines << "            end"
            end
          end
          lines.join("\n")
        end

        def generate_modifiers_code
          "            # Apply default modifiers\n            apply_modifiers"
        end

        def to_camel_case(str)
          str.split('_').map(&:capitalize).join
        end

        def update_membership_exceptions_if_needed
          # Try to find and update the Xcode project file
          require_relative '../../core/project_finder'
          require_relative '../../core/pbxproj_manager'

          if Core::ProjectFinder.setup_paths && Core::ProjectFinder.project_file_path
            begin
              manager = Core::PbxprojManager.new(Core::ProjectFinder.project_file_path)
              manager.setup_membership_exceptions
              @logger.info "Updated Xcode project to exclude extensions directory"
            rescue => e
              @logger.warn "Could not update Xcode project exclusions: #{e.message}"
            end
          end
        end
      end
    end
  end
end
