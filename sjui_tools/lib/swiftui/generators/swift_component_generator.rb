# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/logger'
require_relative '../../core/converter_generator_core'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/generated_marker'
require_relative '../../core/attribute_types'

module SjuiTools
  module SwiftUI
    module Generators
      class SwiftComponentGenerator
        def initialize(name, options = {})
          @name = name
          # Keep the original PascalCase name for Swift file
          @component_name = name
          @options = options
          @logger = Core::Logger
          @command = options[:command] || "sjui g converter #{name}"
        end

        def generate
          create_swift_file
        end

        private

        def create_swift_file
          config = Core::ConfigManager.load_config
          extension_dir = config['extension_directory'] || 'Extensions'

          # Create full path for Swift file (use source_path like other generators)
          Core::ProjectFinder.setup_paths unless Core::ProjectFinder.project_dir
          source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
          swift_dir = File.join(source_path, extension_dir)
          FileUtils.mkdir_p(swift_dir)
          
          swift_file_path = File.join(swift_dir, "#{@component_name}.swift")
          
          # Through the converter core's one overwrite decision, so
          # --force / --skip-existing / JUI_SKIP_EXISTING reach this
          # file too, and a closed stdin reads as "n" instead of raising;
          # it says Created or Overwrote.
          JsonUIShared::ConverterGeneratorCore.write_scaffold(
            swift_file_path, @options, @logger, noun: 'swift file', label: 'Swift file', exists_label: 'Swift file'
          ) { swift_template }
        end

        def swift_template
          if @options[:is_container] != false
            container_template
          else
            non_container_template
          end
        end

        def container_template
          marker_header = Core::GeneratedMarker.scaffold_header(
            source: @component_name,
            generator: @command
          )

          <<~SWIFT
            #{marker_header}

            import SwiftUI#{library_import}

            struct #{@component_name}<Content: View>: View {
            #{generate_swift_properties}
            #{generate_container_init}

                var body: some View {
            #{generate_container_body}
                }
            }

            #if DEBUG
            struct #{@component_name}_Previews: PreviewProvider {
                static var previews: some View {
                    #{@component_name}(#{generate_swift_preview_params}) {
                        Text("Preview Content")
                    }
                }
            }
            #endif
          SWIFT
        end

        def non_container_template
          marker_header = Core::GeneratedMarker.scaffold_header(
            source: @component_name,
            generator: @command
          )

          <<~SWIFT
            #{marker_header}

            import SwiftUI#{library_import}

            struct #{@component_name}: View {
            #{generate_swift_properties}
            #{generate_non_container_init}

                var body: some View {
            #{generate_non_container_body}
                }
            }

            #if DEBUG
            struct #{@component_name}_Previews: PreviewProvider {
                static var previews: some View {
                    #{@component_name}(#{generate_swift_preview_params})
                }
            }
            #endif
          SWIFT
        end

        def generate_swift_properties
          lines = []
          
          if @options[:attributes] && !@options[:attributes].empty?
            @options[:attributes].each do |key, type|
              # Check if it's a binding property (starts with @)
              if key.start_with?('@')
                clean_key = key[1..-1]
                swift_type = map_to_swift_type(type)
                lines << "    @SwiftUI.Binding var #{clean_key}: #{swift_type}"
              else
                swift_type = map_to_swift_type(type)
                lines << "    let #{key}: #{swift_type}"
              end
            end
          end
          
          # Add content property for containers
          if @options[:is_container] != false
            if @options[:is_container] == true
              lines << "    let content: Content"
            else
              lines << "    let content: Content?"
            end
          end
          
          return "" if lines.empty?
          lines.join("\n")
        end

        def generate_container_init
          if @options[:is_container] == true
            "\n    init(#{generate_swift_init_params}@ViewBuilder content: () -> Content) {\n#{generate_swift_init_assignments}        self.content = content()\n    }"
          else
            "\n    init(#{generate_swift_init_params}@ViewBuilder content: () -> Content = { EmptyView() }) {\n#{generate_swift_init_assignments}        self.content = content()\n    }"
          end
        end

        def generate_non_container_init
          return "" if !@options[:attributes] || @options[:attributes].empty?
          "\n    init(#{generate_swift_init_params.chomp(", ")}) {\n#{generate_swift_init_assignments.chomp("\n")}\n    }"
        end

        def generate_container_body
          if @options[:is_container] == true
            "        content"
          else
            "        Group {\n            if let content = content {\n                content\n            } else {\n                EmptyView()\n            }\n        }"
          end
        end

        def generate_non_container_body
          "        // TODO: Implement view body\n        EmptyView()"
        end

        def generate_swift_init_params
          return "" if !@options[:attributes] || @options[:attributes].empty?
          
          @options[:attributes].map do |key, type|
            if key.start_with?('@')
              # Binding property
              clean_key = key[1..-1]
              swift_type = map_to_swift_type(type)
              default = init_default(type)
              "#{clean_key}: SwiftUI.Binding<#{swift_type}>#{default ? " = .constant(#{default})" : ''}, "
            else
              swift_type = map_to_swift_type(type)
              default = init_default(type)
              "#{key}: #{swift_type}#{default ? " = #{default}" : ''}, "
            end
          end.join("")
        end

        # The default each parameter declares, so a call the converter writes
        # without it — the layout left the prop out, gave it null, or gave a
        # value that is not of its type — compiles and the prop keeps it, as
        # it does on kjui (the composable's defaults) and rjui (optional
        # props): nil for an optional type, the vocabulary's value for any
        # other (the one the Dynamic adapter falls back to). A `T!!` model has
        # none — the converter says so. Until 1.8.121 only optional
        # parameters had one, and every other call without the prop failed
        # with "missing argument for parameter" (ticket
        # sjui-unwritten-non-optional-prop-does-not-compile).
        def init_default(type)
          t = JsonUIShared::AttributeTypes.parse(type)
          return 'nil' if map_to_swift_type(type).end_with?('?')

          JsonUIShared::AttributeTypes.swift_default(t)
        end

        def generate_swift_init_assignments
          return "" if !@options[:attributes] || @options[:attributes].empty?
          
          @options[:attributes].map do |key, _|
            if key.start_with?('@')
              clean_key = key[1..-1]
              "        self._#{clean_key} = #{clean_key}\n"
            else
              "        self.#{key} = #{key}\n"
            end
          end.join("")
        end

        def generate_swift_preview_params
          return "" if !@options[:attributes] || @options[:attributes].empty?
          
          @options[:attributes].map do |key, type|
            if key.start_with?('@')
              clean_key = key[1..-1]
              default_value = get_swift_default_value(type)
              "#{clean_key}: .constant(#{default_value})"
            else
              default_value = get_swift_default_value(type)
              "#{key}: #{default_value}"
            end
          end.join(", ")
        end

        # Types come from the shared vocabulary (lib/core/attribute_types.rb),
        # which the Dynamic adapter reads too. Until 1.8.121 this file kept its
        # own list: Float became Double here and Float in the adapter, a Long
        # became `Long?` (no such Swift type), and `String?` became `String??`
        # (ticket kjui-sjui-converter-attr-types-do-not-compile).
        # A type outside the vocabulary stays a model type the app declares:
        # optional, or not with the `!!` mark — which the shared table reads
        # (Type#forced) and answers for, so the warning that names the type
        # names this one (until 1.8.121 this file read `!!` itself and the
        # warning said `Row?` for the `Row` declared here — ticket
        # converter-attr-types-warning-wording).
        def map_to_swift_type(type)
          JsonUIShared::AttributeTypes.swift_type(JsonUIShared::AttributeTypes.parse(type))
        end

        def get_swift_default_value(type)
          t = JsonUIShared::AttributeTypes.parse(type)
          if t.kind == :scalar && !t.nullable
            { 'string' => '"Sample Text"', 'bool' => 'true', 'color' => '.blue' }.fetch(t.canonical, t.entry[:swift_default])
          elsif t.kind == :list && !t.nullable
            '[]'
          elsif t.kind == :outside && t.forced
            "#{t.name}.mock"
          else
            'nil'
          end
        end

        # CollectionDataSource is SwiftJsonUI's.
        def library_import
          types = (@options[:attributes] || {}).values.map { |type| JsonUIShared::AttributeTypes.parse(type) }
          uses = types.any? { |t| (t.kind == :list ? t.element : t).canonical == 'collection_data_source' }
          uses ? "\nimport SwiftJsonUI" : ''
        end

        def to_camel_case(str)
          str.split('_').map(&:capitalize).join
        end
      end
    end
  end
end