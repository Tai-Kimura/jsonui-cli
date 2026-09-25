# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/logger'
require_relative '../../core/converter_generator_core'
require_relative '../../core/config_manager'
require_relative '../../core/generated_marker'
require_relative '../../core/attribute_types'

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
          
          # Through the converter core's one overwrite decision, so
          # --force / --skip-existing / JUI_SKIP_EXISTING reach this
          # file too, and a closed stdin reads as "n" instead of raising.
          return unless JsonUIShared::ConverterGeneratorCore.may_write?(
            adapter_file, @options, @logger, noun: 'adapter file', exists_label: 'Adapter file')
          
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
          marker_header = Core::GeneratedMarker.scaffold_header(
            source: @name,
            generator: @command
          )

          <<~SWIFT
          #{marker_header}

          import SwiftUI
          import SwiftJsonUI

          #if DEBUG

          struct #{@adapter_class_name}: CustomComponentAdapter {
              var componentType: String { "#{@name}" }#{accepts_children_line}

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
          SWIFT
        end
        
        # A leaf says so, and DynamicComponentBuilder (SwiftJsonUI 10.29.0)
        # draws an error naming the component and its children instead of the
        # component — the Debug counterpart of the build refusing the layout.
        # Before 10.29.0 the property is simply unused.
        def accepts_children_line
          return '' unless leaf?

          "\n\n    // A leaf (--no-container): a layout that gives it children is refused.\n" \
            "    var acceptsChildren: Bool { false }"
        end

        def leaf?
          @options[:no_container] || @options[:is_container] == false
        end

        def build_view_implementation(attributes)
          # Check both :no_container flag and :is_container flag
          if leaf?
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
        # One reader per attribute, from the shared vocabulary
        # (lib/core/attribute_types.rb) — the table the component's parameter
        # types come from, so the two agree for every type. Until 1.8.121 this
        # file kept its own list: Float was read as Float for a Double
        # parameter, Color as Color? for a Color one, `Integer` / `Boolean`
        # became type names (ticket kjui-sjui-converter-attr-types-do-not-compile).
        def generate_attribute_extraction(attributes)
          impl = ""
          callbacks = []

          attributes.each do |name, attr_info|
            type = attr_info.is_a?(Hash) ? attr_info[:type] : attr_info
            is_binding = attr_info.is_a?(Hash) ? attr_info[:is_binding] : false
            t = JsonUIShared::AttributeTypes.parse(type)
            if t.kind == :callback
              callbacks << [name, t]
            elsif is_binding
              impl += generate_binding_extraction(name, type)
            else
              impl += value_extraction(name, type, t)
            end
          end

          unless callbacks.empty?
            impl += "\n        // Extract callbacks\n"
            callbacks.each do |name, t|
              closure = JsonUIShared::AttributeTypes.swift_type(t).chomp('?')
              impl += "        var #{name}: #{closure}? = nil\n"
              impl += "        if let str = component.rawData[\"#{name}\"] as? String,\n"
              impl += "           let propName = DynamicEventHelper.extractPropertyName(from: str) {\n"
              impl += "            #{name} = data[propName] as? #{closure}\n"
              impl += "        }\n"
            end
          end

          impl
        end

        def value_extraction(name, type, t)
          raw = "component.rawData[\"#{name}\"]"
          resolve = "DynamicBindingHelper.resolveValue(#{raw}, data: data)"
          swift = JsonUIShared::AttributeTypes.swift_type(t)
          default = JsonUIShared::AttributeTypes.swift_default(t)
          fallback = default ? " ?? #{default}" : ''
          if (model = forced_model(type, t))
            return "        let #{name}: #{model} = #{resolve} ?? #{model}.mock\n"
          end
          return "        let #{name}: #{swift} = #{resolve}\n" if t.kind == :outside
          return "        let #{name}: #{swift} = #{resolve}#{fallback}\n" unless t.kind == :scalar

          case t.canonical
          when 'color'
            "        let #{name}: #{swift} = DynamicHelpers.getColor(#{raw} as? String, data: data)#{fallback}\n"
          when 'cgfloat'
            "        let #{name}: #{swift} = #{resolve}\n" \
              "            ?? (#{raw} as? Double).map { CGFloat($0) }#{fallback}\n"
          when 'collection_data_source'
            "        let #{name}: #{swift} = #{resolve}\n"
          else
            base = t.entry[:swift]
            "        let #{name}: #{swift} = #{resolve}\n" \
              "            ?? (#{raw} as? #{base})#{fallback}\n"
          end
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
            split_top_level_commas(@options[:attributes]).each do |attr|
              parts = attr.strip.split(':', 2)
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

        # Split an attributes list on top-level commas only — prop types can
        # contain commas themselves (multi-arg closure types like
        # `((String, String) -> Void)?`).
        def split_top_level_commas(str)
          parts = []
          depth = 0
          current = +''
          str.each_char do |ch|
            case ch
            when '(', '[' then depth += 1
            when ')', ']' then depth -= 1
            when ','
              if depth.zero?
                parts << current
                current = +''
                next
              end
            end
            current << ch
          end
          parts << current unless current.empty?
          parts
        end
        
        # A binding attribute (`@name:Type`): the data's Binding when the
        # layout names one, else a constant. `#{name}Value` was read here and
        # declared nowhere, so no adapter with a binding attribute compiled
        # before 1.8.121.
        def generate_binding_extraction(name, type)
          t = JsonUIShared::AttributeTypes.parse(type)
          model = forced_model(type, t)
          swift = model || JsonUIShared::AttributeTypes.swift_type(t)
          default = model ? "#{model}.mock" : JsonUIShared::AttributeTypes.swift_default(t)
          value_type = swift.chomp('?')
          constant = default ? "(data[propertyName] as? #{value_type}) ?? #{default}" : "data[propertyName] as? #{value_type}"
          literal = default ? "(#{name}Value as? #{value_type}) ?? #{default}" : "#{name}Value as? #{value_type}"
          impl = ""
          impl += "        let #{name}Value = component.rawData[\"#{name}\"]\n"
          impl += "        let #{name}: SwiftUI.Binding<#{swift}>\n"
          impl += "        if let stringValue = #{name}Value as? String,\n"
          impl += "           stringValue.hasPrefix(\"@{\") && stringValue.hasSuffix(\"}\") {\n"
          impl += "            let propertyName = String(stringValue.dropFirst(2).dropLast(1))\n"
          impl += "            if let binding = data[propertyName] as? SwiftUI.Binding<#{swift}> {\n"
          impl += "                #{name} = binding\n"
          impl += "            } else {\n"
          impl += "                #{name} = .constant(#{constant})\n"
          impl += "            }\n"
          impl += "        } else {\n"
          impl += "            #{name} = .constant(#{literal})\n"
          impl += "        }\n"
          impl
        end

        # A model type outside the vocabulary marked `!!` ("not optional"): the
        # component declares it non-optional, so the adapter reads it as one and
        # falls back to `.mock`, as the component's preview does.
        def forced_model(type, t)
          t.name if t.kind == :outside && type.to_s.strip.end_with?('!!')
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