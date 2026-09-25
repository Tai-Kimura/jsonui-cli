# frozen_string_literal: true

require 'fileutils'
require 'json'
require_relative '../../../core/logger'
require_relative '../../../core/converter_generator_core'
require_relative '../../../core/config_manager'
require_relative '../../../core/generated_marker'

module SjuiTools
  module UIKit
    module XcodeProject
      module Generators
        class ConverterGenerator
          def initialize(name, options = {})
            @name = name
            # Keep original PascalCase name for component
            @component_pascal_case = name  # e.g., MyCustomView
            @class_name = "#{name}BindingHandler"  # e.g., MyCustomViewBindingHandler
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
            cmd += " --import-module=#{options[:import_module]}" if options[:import_module]
            cmd
          end

          def generate
            @logger.info "Generating UIKit custom converter: #{@class_name}"

            # Create binding handler file
            handler_written = create_binding_handler_file

            # Update config file
            update_config_file

            # Create attribute definition file
            definition_written = create_attribute_definition_file

            # What the run did — each file has said its own line with its
            # path. Until 1.8.121 this said "Successfully generated", "Binding
            # handler created at: …", "Attribute definition created at: …" and
            # "Config file updated …" whatever the run had done (ticket
            # g-converter-reports-files-it-did-not-write).
            if handler_written || definition_written
              @logger.success "Scaffolded UIKit converter #{@class_name}"
            else
              @logger.info "#{@class_name}: the binding handler and the attribute definition already existed and " \
                           'were kept; --force overwrites them'
            end
            @logger.info ""
            @logger.info "Next steps:"
            @logger.info "1. Implement binding logic in the handler file"
            @logger.info "2. Run 'sjui build' to regenerate binding files"
          end

          private

          def create_binding_handler_file
            # Ensure handlers/extensions directory exists
            if File.exist?(File.join(Dir.pwd, 'sjui_tools'))
              # Test app structure
              handlers_dir = File.join(Dir.pwd, 'sjui_tools', 'lib', 'uikit', 'handlers', 'extensions')
            else
              # Main SwiftJsonUI structure
              handlers_dir = File.join(Dir.pwd, 'tools', 'sjui_tools', 'lib', 'uikit', 'handlers', 'extensions')
            end
            FileUtils.mkdir_p(handlers_dir)

            file_path = File.join(handlers_dir, "#{snake_case(@name)}_binding_handler.rb")

            # The converter core's one overwrite decision: JUI_SKIP_EXISTING,
            # --skip-existing and --force, and a closed stdin reads as "n";
            # it says Created or Overwrote. Returns whether it wrote.
            JsonUIShared::ConverterGeneratorCore.write_scaffold(
              file_path, @options, @logger,
              noun: 'binding handler', label: 'binding handler file', exists_label: 'Binding handler file'
            ) { binding_handler_template }
          end

          def update_config_file
            config_path = Core::ConfigManager.find_config_file

            unless config_path && File.exist?(config_path)
              @logger.warn "Config file not found. Creating new sjui.config.json"
              config_path = File.join(Dir.pwd, 'sjui.config.json')
              config = Core::ConfigManager.load_config
            else
              config = Core::ConfigManager.load_config(config_path)
            end

            # Initialize custom_view_types if not exists
            config['custom_view_types'] ||= {}

            # Add or update the custom view type
            view_type_config = {
              'class_name' => @options[:class_name] || @component_pascal_case
            }

            # Add import_module if specified
            if @options[:import_module]
              view_type_config['import_module'] = @options[:import_module]
            end

            # Add attributes if specified
            if @options[:attributes] && !@options[:attributes].empty?
              view_type_config['attributes'] = @options[:attributes]
            end

            config['custom_view_types'][@component_pascal_case] = view_type_config

            content = JSON.pretty_generate(config)
            before = File.exist?(config_path) ? File.read(config_path) : nil
            File.write(config_path, content)
            # What changed in it, said: until 1.8.121 "Updated" when it was
            # written back as it was.
            @logger.info(if before.nil?
                           "Created #{config_path} with custom_view_types['#{@component_pascal_case}']"
                         elsif before == content
                           "Rewrote #{config_path} as it was (custom_view_types['#{@component_pascal_case}'] unchanged)"
                         else
                           "Updated #{config_path}: custom_view_types['#{@component_pascal_case}']"
                         end)
          end

          def binding_handler_template
            marker_header = Core::GeneratedMarker.comment_header(
              source: @component_pascal_case,
              generator: @command,
              prefix: "#"
            )
            marker_footer = Core::GeneratedMarker.comment_footer(prefix: "#")
            <<~RUBY
              # frozen_string_literal: true

              #{marker_header}

              require_relative '../../view_binding_handler'

              module SjuiTools
                module UIKit
                  class #{@class_name} < ViewBindingHandler
                    def handle_specific_binding(view_name, key, value)
                      case key
              #{generate_attribute_cases}
                      else
                        return false
                      end
                      true
                    end
                  end
                end
              end

              #{marker_footer}
            RUBY
          end

          def generate_attribute_cases
            return "        # TODO: Implement custom attribute bindings here\n        # Example:\n        # when \"customAttribute\"\n        #   @binding_content << \"        \#{view_name}?.customProperty = \#{value}\\n\"\n" if !@options[:attributes] || @options[:attributes].empty?

            lines = []
            @options[:attributes].each do |key, type|
              property_name = to_camel_case(key)
              lines << "        when \"#{key}\""

              case type.downcase
              when 'string'
                lines << "          @binding_content << \"        \#{view_name}?.#{property_name} = \#{value}\\n\""
              when 'int', 'integer', 'double', 'float'
                lines << "          @binding_content << \"        \#{view_name}?.#{property_name} = \#{value}\\n\""
              when 'bool', 'boolean'
                lines << "          @binding_content << \"        \#{view_name}?.#{property_name} = \#{value}\\n\""
              when 'color'
                lines << "          @binding_content << \"        \#{view_name}?.#{property_name} = \#{value}\\n\""
              else
                # Custom type
                lines << "          # TODO: Handle custom type '#{type}'"
                lines << "          @binding_content << \"        \#{view_name}?.#{property_name} = \#{value}\\n\""
              end
            end
            lines.join("\n")
          end

          def create_attribute_definition_file
            # Ensure extensions/attribute_definitions directory exists
            if File.exist?(File.join(Dir.pwd, 'sjui_tools'))
              # Test app structure
              attr_defs_dir = File.join(Dir.pwd, 'sjui_tools', 'lib', 'uikit', 'extensions', 'attribute_definitions')
            else
              # Main SwiftJsonUI structure
              attr_defs_dir = File.join(Dir.pwd, 'tools', 'sjui_tools', 'lib', 'uikit', 'extensions', 'attribute_definitions')
            end
            FileUtils.mkdir_p(attr_defs_dir)

            file_path = File.join(attr_defs_dir, "#{snake_case(@name)}.json")

            # The converter core's one overwrite decision: JUI_SKIP_EXISTING,
            # --skip-existing and --force, and a closed stdin reads as "n";
            # it says Created or Overwrote. Returns whether it wrote.
            JsonUIShared::ConverterGeneratorCore.write_scaffold(
              file_path, @options, @logger,
              noun: 'attribute definition', label: 'attribute definition file',
              exists_label: 'Attribute definition file'
            ) { attribute_definition_template }
          end

          def attribute_definition_template
            definition = {
              "_generated" => Core::GeneratedMarker.json_marker(
                source: @component_pascal_case,
                generator: @command
              ),
              @component_pascal_case => {}
            }

            if @options[:attributes] && !@options[:attributes].empty?
              @options[:attributes].each do |key, type|
                attr_def = {
                  'type' => map_type_to_json_type(type),
                  'description' => JsonUIShared::ConverterGeneratorCore.attribute_description(
                    @options, key.to_s.delete_prefix('@'),
                    "#{key} attribute for #{@component_pascal_case}")
                }
                definition[@component_pascal_case][key] = attr_def
              end
            else
              # Add placeholder comment
              definition['_comment'] = "Add custom attributes for #{@component_pascal_case} here"
            end

            JSON.pretty_generate(definition)
          end

          def map_type_to_json_type(type)
            case type.downcase
            when 'string'
              ['string', 'binding']
            when 'int', 'integer'
              ['number', 'binding']
            when 'double', 'float', 'number'
              ['number', 'binding']
            when 'bool', 'boolean'
              ['boolean', 'binding']
            when 'color'
              ['string', 'number', 'binding']
            else
              ['any', 'binding']
            end
          end

          def snake_case(str)
            str.gsub(/([A-Z]+)([A-Z][a-z])/,'\1_\2')
               .gsub(/([a-z\d])([A-Z])/,'\1_\2')
               .downcase
          end

          def to_camel_case(str)
            # Convert snake_case or kebab-case to camelCase
            parts = str.split(/[_-]/)
            return str if parts.length == 1

            parts[0] + parts[1..-1].map(&:capitalize).join
          end
        end
      end
    end
  end
end
