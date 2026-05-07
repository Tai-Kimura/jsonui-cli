# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/logger'
require_relative '../../core/config_manager'
require_relative '../../core/generated_marker'

module SjuiTools
  module SwiftUI
    module Generators
      class AdapterGenerator
        def initialize(name, options = {})
          @name = name  # PascalCase name like TestComponent
          @adapter_class_name = "#{name}Adapter"
          @options = options
          @logger = Core::Logger
          @command = options[:command] || "sjui g converter #{name}"
        end

        def generate
          @logger.info "Generating adapter for: #{@name}"
          
          # Determine adapter directory
          adapter_dir = get_adapter_directory
          
          if adapter_dir.nil?
            @logger.warn "No adapter_directory configured. Skipping adapter generation."
            @logger.info "Add 'adapter_directory: Extensions/Adapters' to sjui_config.yml to enable adapter generation."
            return false
          end
          
          # Create adapter file
          create_adapter_file(adapter_dir)
          
          # Update registration file if it exists
          update_registration_file(adapter_dir)
          
          @logger.success "Successfully generated adapter: #{@adapter_class_name}"
          true
        end
        
        private
        
        def get_adapter_directory
          # Load config using ConfigManager
          config = Core::ConfigManager.load_config
          
          # Check for adapter_directory in config
          adapter_dir = config['adapter_directory']
          source_dir = config['source_directory']
          
          if adapter_dir && !adapter_dir.strip.empty?
            # Check if we need to prepend source_directory
            # Only prepend if:
            # 1. source_dir is configured
            # 2. adapter_dir is not an absolute path
            # 3. Current working directory doesn't already end with source_dir
            current_dir_name = File.basename(Dir.pwd)
            if source_dir && !source_dir.strip.empty? && 
               !adapter_dir.start_with?('/') && 
               current_dir_name != source_dir
              return File.join(source_dir, adapter_dir)
            else
              return adapter_dir
            end
          end
          
          # Check for extension_directory as fallback
          extension_dir = config['extension_directory']
          if extension_dir && !extension_dir.strip.empty?
            current_dir_name = File.basename(Dir.pwd)
            if source_dir && !source_dir.strip.empty? && 
               !extension_dir.start_with?('/') && 
               current_dir_name != source_dir
              return File.join(source_dir, extension_dir, 'Adapters')
            else
              return File.join(extension_dir, 'Adapters')
            end
          end
          
          nil
        end
        
        def create_adapter_file(adapter_dir)
          # Ensure directory exists
          full_adapter_dir = File.join(Dir.pwd, adapter_dir)
          
          # Create directory if it doesn't exist
          unless File.directory?(full_adapter_dir)
            @logger.info "Creating adapter directory: #{full_adapter_dir}"
            FileUtils.mkdir_p(full_adapter_dir)
          end
          
          # Create adapter file
          adapter_file = File.join(full_adapter_dir, "#{@adapter_class_name}.swift")
          
          if File.exist?(adapter_file)
            @logger.warn "Adapter file already exists: #{adapter_file}"
            print "Overwrite? (y/n): "
            response = gets.chomp.downcase
            return unless response == 'y'
          end
          
          File.write(adapter_file, adapter_template)
          @logger.info "Created adapter file: #{adapter_file}"
        end
        
        def update_registration_file(adapter_dir)
          registration_file = File.join(Dir.pwd, adapter_dir, 'CustomComponentRegistration.swift')
          
          if File.exist?(registration_file)
            content = File.read(registration_file)
            
            # Check if adapter is already registered
            if content.include?("#{@adapter_class_name}()")
              @logger.info "Adapter already registered in CustomComponentRegistration.swift"
              return
            end
            
            # Add adapter to the list
            if content =~ /let adapters:\s*\[CustomComponentAdapter\]\s*=\s*\[(.*?)\]/m
              existing_adapters = $1
              
              # Split existing adapters and properly format
              adapter_lines = existing_adapters.strip.split(/,\s*\n/)
              adapter_lines = adapter_lines.reject(&:empty?)
              
              # Add new adapter
              adapter_lines << "#{@adapter_class_name}()"
              
              # Format all adapters with proper indentation
              formatted_adapters = adapter_lines.map { |a| "            #{a.strip}" }.join(",\n")
              
              new_content = content.sub(
                /let adapters:\s*\[CustomComponentAdapter\]\s*=\s*\[.*?\]/m,
                "let adapters: [CustomComponentAdapter] = [\n#{formatted_adapters}\n        ]"
              )
              
              File.write(registration_file, new_content)
              @logger.info "Updated CustomComponentRegistration.swift with #{@adapter_class_name}"
            end
          else
            # Create registration file if it doesn't exist
            File.write(registration_file, registration_template)
            @logger.info "Created CustomComponentRegistration.swift"
          end
        end
        
        def adapter_template
          attributes = parse_attributes
          marker_header = Core::GeneratedMarker.comment_header(
            source: @name,
            generator: @command
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          <<~SWIFT
          #{marker_header}

          import SwiftUI
          import SwiftJsonUI

          #if DEBUG

          struct #{@adapter_class_name}: CustomComponentAdapter {
              var componentType: String { "#{@name}" }

              func buildView(
                  component: DynamicComponent,
                  data: [String: Any],
                  viewId: String?,
                  parentOrientation: String?
              ) -> AnyView {
                  #{build_view_implementation(attributes)}
              }
          }

          #endif

          #{marker_footer}
          SWIFT
        end
        
        def build_view_implementation(attributes)
          # Check both :no_container flag and :is_container flag
          if @options[:no_container] || @options[:is_container] == false
            # Non-container component
            build_non_container_implementation(attributes)
          else
            # Container component (default)
            build_container_implementation(attributes)
          end
        end
        
        def build_non_container_implementation(attributes)
          impl = "// Use DynamicBindingHelper.resolveValue for Binding-safe value extraction\n"
          impl += generate_attribute_extraction(attributes)

          impl += "\n        return DynamicModifierHelper.applyStandardModifiers(\n"
          impl += "            AnyView(\n"
          impl += "                #{@name}(\n"

          # Add parameters
          param_lines = attributes.map { |name, _| "                    #{name}: #{name}" }
          impl += param_lines.join(",\n")

          impl += "\n                )\n"
          impl += "            ),\n"
          impl += "            component: component,\n"
          impl += "            data: data\n"
          impl += "        )"

          impl
        end

        def build_container_implementation(attributes)
          impl = "// Use DynamicBindingHelper.resolveValue for Binding-safe value extraction\n"
          impl += generate_attribute_extraction(attributes)

          impl += "\n        // Build the content from child components\n"
          impl += "        let content = VStack(alignment: .leading, spacing: 0) {\n"
          impl += "            if let children = component.childComponents {\n"
          impl += "                ForEach(Array(children.enumerated()), id: \\.offset) { _, child in\n"
          impl += "                    DynamicComponentBuilder(\n"
          impl += "                        component: child,\n"
          impl += "                        data: data,\n"
          impl += "                        viewId: viewId,\n"
          impl += "                        isWeightedChild: false,\n"
          impl += "                        parentOrientation: \"vertical\"\n"
          impl += "                    )\n"
          impl += "                }\n"
          impl += "            }\n"
          impl += "        }\n"

          impl += "\n        let result = AnyView(\n"
          impl += "            #{@name}(\n"

          # Add parameters
          param_lines = attributes.map { |name, _| "                #{name}: #{name}" }
          impl += param_lines.join(",\n")

          if !attributes.empty?
            impl += "\n"
          end
          impl += "            ) {\n"
          impl += "                content\n"
          impl += "            }\n"
          impl += "        )\n"
          impl += "        return DynamicModifierHelper.applyStandardModifiers(result, component: component, data: data)"

          impl
        end

        # Generate attribute extraction code using DynamicBindingHelper.resolveValue
        # This produces clean one-liners instead of verbose manual @{} parsing
        def generate_attribute_extraction(attributes)
          impl = ""
          callback_attrs = []
          value_attrs = []

          # Separate callbacks from value attributes
          attributes.each do |name, attr_info|
            type = attr_info.is_a?(Hash) ? attr_info[:type] : attr_info
            if type =~ /^\(.*\)\s*->\s*/
              callback_attrs << [name, attr_info]
            else
              value_attrs << [name, attr_info]
            end
          end

          # Generate value attribute extractions
          value_attrs.each do |name, attr_info|
            type = attr_info.is_a?(Hash) ? attr_info[:type] : attr_info
            is_binding = attr_info.is_a?(Hash) ? attr_info[:is_binding] : false

            if is_binding
              # Binding properties still need explicit Binding extraction
              impl += generate_binding_extraction(name, type)
            else
              case type
              when 'String'
                impl += "        let #{name}: String = DynamicBindingHelper.resolveValue(component.rawData[\"#{name}\"], data: data) ?? \"\"\n"
              when 'Bool'
                impl += "        let #{name}: Bool = DynamicBindingHelper.resolveValue(component.rawData[\"#{name}\"], data: data)\n"
                impl += "            ?? (component.rawData[\"#{name}\"] as? Bool) ?? false\n"
              when 'Int'
                impl += "        let #{name}: Int = DynamicBindingHelper.resolveValue(component.rawData[\"#{name}\"], data: data)\n"
                impl += "            ?? (component.rawData[\"#{name}\"] as? Int) ?? 0\n"
              when 'Double'
                impl += "        let #{name}: Double = DynamicBindingHelper.resolveValue(component.rawData[\"#{name}\"], data: data)\n"
                impl += "            ?? (component.rawData[\"#{name}\"] as? Double) ?? 0.0\n"
              when 'Float'
                impl += "        let #{name}: Float = DynamicBindingHelper.resolveValue(component.rawData[\"#{name}\"], data: data)\n"
                impl += "            ?? (component.rawData[\"#{name}\"] as? Float) ?? 0.0\n"
              when 'Color'
                impl += "        let #{name} = DynamicHelpers.getColor(component.rawData[\"#{name}\"] as? String, data: data)\n"
              else
                # Model/custom types
                actual_type = type.is_a?(Hash) ? type[:type] : type
                force_non_optional = actual_type.is_a?(String) ? actual_type.end_with?('!!') : false
                clean_type = force_non_optional ? actual_type[0..-3] : actual_type
                swift_type = force_non_optional ? clean_type : "#{clean_type}?"

                impl += "        let #{name}: #{swift_type} = DynamicBindingHelper.resolveValue(component.rawData[\"#{name}\"], data: data)\n"
              end
            end
          end

          # Generate callback extractions
          if !callback_attrs.empty?
            impl += "\n        // Extract callbacks\n"
            callback_attrs.each do |name, attr_info|
              type = attr_info.is_a?(Hash) ? attr_info[:type] : attr_info
              impl += "        var #{name}: #{type}? = nil\n"
              impl += "        if let str = component.rawData[\"#{name}\"] as? String,\n"
              impl += "           let propName = DynamicEventHelper.extractPropertyName(from: str) {\n"
              impl += "            #{name} = data[propName] as? (#{type})\n"
              impl += "        }\n"
            end
          end

          impl
        end
        
        def parse_attributes
          return {} unless @options[:attributes]
          
          # Handle both string and hash formats
          if @options[:attributes].is_a?(Hash)
            # Already parsed as hash - check for binding properties
            result = {}
            @options[:attributes].each do |key, type|
              actual_key = key.start_with?('@') ? key[1..-1] : key
              result[actual_key] = { 
                type: type,
                is_binding: key.start_with?('@')
              }
            end
            return result
          elsif @options[:attributes].is_a?(String)
            # Parse attributes string like "text:String,@isEnabled:Bool"
            attributes = {}
            @options[:attributes].split(',').each do |attr|
              parts = attr.strip.split(':')
              if parts.size == 2
                name = parts[0].strip
                is_binding = name.start_with?('@')
                actual_name = is_binding ? name[1..-1] : name
                type = parts[1].strip
                attributes[actual_name] = {
                  type: type,
                  is_binding: is_binding
                }
              end
            end
            return attributes
          else
            return {}
          end
        end
        
        def generate_binding_extraction(name, type)
          impl = ""

          # For binding properties, extract Binding from data dictionary
          case type
          when 'String', 'Bool', 'Int', 'Double', 'Float'
            default_value = get_default_value_for_type(type)
            impl += "        let #{name}: SwiftUI.Binding<#{type}>\n"
            impl += "        if let stringValue = #{name}Value as? String,\n"
            impl += "           stringValue.hasPrefix(\"@{\") && stringValue.hasSuffix(\"}\") {\n"
            impl += "            let propertyName = String(stringValue.dropFirst(2).dropLast(1))\n"
            impl += "            if let binding = data[propertyName] as? SwiftUI.Binding<#{type}> {\n"
            impl += "                #{name} = binding\n"
            impl += "            } else {\n"
            impl += "                #{name} = .constant(data[propertyName] as? #{type} ?? #{default_value})\n"
            impl += "            }\n"
            impl += "        } else {\n"
            impl += "            #{name} = .constant(#{name}Value as? #{type} ?? #{default_value})\n"
            impl += "        }\n"
          else
            # Model types
            force_non_optional = type.end_with?('!!')
            clean_type = force_non_optional ? type[0..-3] : type
            swift_type = force_non_optional ? clean_type : "#{clean_type}?"

            impl += "        let #{name}: SwiftUI.Binding<#{swift_type}>\n"
            impl += "        if let stringValue = #{name}Value as? String,\n"
            impl += "           stringValue.hasPrefix(\"@{\") && stringValue.hasSuffix(\"}\") {\n"
            impl += "            let propertyName = String(stringValue.dropFirst(2).dropLast(1))\n"
            impl += "            if let binding = data[propertyName] as? SwiftUI.Binding<#{swift_type}> {\n"
            impl += "                #{name} = binding\n"
            impl += "            } else {\n"
            impl += "                #{name} = .constant(data[propertyName] as? #{clean_type})\n"
            impl += "            }\n"
            impl += "        } else {\n"
            impl += "            #{name} = .constant(nil)\n"
            impl += "        }\n"
          end

          impl
        end
        
        def get_default_value_for_type(type)
          case type
          when 'String'
            '""'
          when 'Bool'
            'false'
          when 'Int'
            '0'
          when 'Double'
            '0.0'
          when 'Float'
            '0.0'
          else
            'nil'
          end
        end
        
        def registration_template
          marker_header = Core::GeneratedMarker.comment_header(
            source: "CustomComponentRegistration",
            generator: @command
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          <<~SWIFT
          #{marker_header}

          import SwiftUI
          import SwiftJsonUI

          #if DEBUG

          /// Helper to register all custom component adapters
          public struct CustomComponentRegistration {

              /// Register all custom component adapters with the registry
              public static func registerAll() {
                  let adapters: [CustomComponentAdapter] = [
                      #{@adapter_class_name}()
                  ]

                  CustomComponentRegistry.shared.registerAll(adapters)

                  print("✅ Registered \\(adapters.count) custom component adapters")
              }
          }

          #endif

          #{marker_footer}
          SWIFT
        end
      end
    end
  end
end