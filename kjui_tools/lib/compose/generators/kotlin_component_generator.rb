# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/logger'
require_relative '../../core/converter_generator_core'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/generated_marker'
require_relative '../../core/attribute_types'

module KjuiTools
  module Compose
    module Generators
      class KotlinComponentGenerator
        def initialize(name, options = {})
          @name = name
          @component_name = name  # PascalCase name
          @package_name = get_package_name
          @options = options
          @logger = Core::Logger
        end

        def generate
          create_kotlin_file
        end

        private

        def create_kotlin_file
          config = Core::ConfigManager.load_config
          
          # Use config directory if available (where kjui.config.json was found)
          base_path = config['_config_dir'] || Dir.pwd
          source_directory = config['source_directory'] || 'src/main'
          package_name = config['package_name'] || Core::ProjectFinder.get_package_name || 'com.example.kotlinjsonui.sample'
          
          # Get extension directory from config
          extension_directory = config['extension_directory'] || "kotlin/#{package_name.gsub('.', '/')}/extensions"
          
          # Build extension directory path
          extension_dir = File.join(
            base_path,
            source_directory,
            extension_directory
          )
          
          FileUtils.mkdir_p(extension_dir)
          
          kotlin_file_path = File.join(extension_dir, "#{@component_name}.kt")
          
          # Through the converter core's one overwrite decision, so
          # --force / --skip-existing / JUI_SKIP_EXISTING reach this
          # file too, and a closed stdin reads as "n" instead of raising.
          return unless JsonUIShared::ConverterGeneratorCore.may_write?(
            kotlin_file_path, @options, @logger, noun: 'kotlin file', exists_label: 'Kotlin file')
          
          File.write(kotlin_file_path, kotlin_template)
          @logger.info "Created Kotlin file: #{kotlin_file_path}"
        end
        
        def get_package_name
          config = Core::ConfigManager.load_config
          base_package = config['package_name'] || 'com.example.kotlinjsonui.sample'
          "#{base_package}.extensions"
        end

        # The three modes, read the same way by the converter, this composable
        # and the Dynamic wrapper (until 1.8.121 each read them differently,
        # and two of the combinations did not compile — ticket
        # kjui-converter-scaffolds-disagree-on-content):
        #   --container      content required; the converter always passes it
        #   default (nil)    content with a default `{}`; the converter passes
        #                    it when the layout gives children
        #   --no-container   no content; the build refuses a layout that gives
        #                    this component children
        def kotlin_template
          if @options[:is_container] != false
            container_template
          else
            non_container_template
          end
        end

        def mode_flag
          case @options[:is_container]
          when true then ' --container'
          when false then ' --no-container'
          else ''
          end
        end

        def container_template
          imports = generate_kotlin_imports
          params = generate_kotlin_parameters
          marker_header = Core::GeneratedMarker.scaffold_header(
            source: @component_name,
            generator: "kjui g converter #{@component_name}#{mode_flag}#{format_attributes_for_command}"
          )

          template = <<~KOTLIN
            #{marker_header}

            package #{@package_name}

            import androidx.compose.foundation.layout.Box
            import androidx.compose.foundation.layout.BoxScope
            import androidx.compose.runtime.Composable
            import androidx.compose.ui.Modifier
          KOTLIN

          template += imports + "\n" if !imports.empty?
          template += "\n"

          template += <<~KOTLIN
            /**
             * Custom #{@component_name} component
             */
            @Composable
            fun #{@component_name}(
          KOTLIN

          if !params.empty?
            template += params
          end

          # The default mode's converter calls this without a lambda when the
          # layout gives no children, so there `content` has a default.
          content_default = @options[:is_container] == true ? '' : ' = {}'
          template += <<~KOTLIN
                modifier: Modifier = Modifier,
                content: @Composable BoxScope.() -> Unit#{content_default}
            ) {
                Box(
                    modifier = modifier
                ) {
                    // Custom container implementation
                    content()
                }
            }
          KOTLIN

          template
        end

        def non_container_template
          imports = generate_kotlin_imports
          params = generate_kotlin_parameters
          marker_header = Core::GeneratedMarker.scaffold_header(
            source: @component_name,
            generator: "kjui g converter #{@component_name}#{mode_flag}#{format_attributes_for_command}"
          )

          template = <<~KOTLIN
            #{marker_header}

            package #{@package_name}

            import androidx.compose.foundation.layout.Box
            import androidx.compose.runtime.Composable
            import androidx.compose.ui.Modifier
          KOTLIN

          template += imports + "\n" if !imports.empty?
          template += "\n"

          template += <<~KOTLIN
            /**
             * Custom #{@component_name} component
             */
            @Composable
            fun #{@component_name}(
          KOTLIN

          if !params.empty?
            template += params
          end

          template += <<~KOTLIN
                modifier: Modifier = Modifier
            ) {
                // TODO: Implement your custom component
                Box(modifier = modifier) {
                    // Component content
                }
            }
          KOTLIN

          template
        end
        
        # Types come from the shared vocabulary (lib/core/attribute_types.rb),
        # which the Dynamic wrapper reads too: until 1.8.121 this file kept its
        # own list, and a Long, a callback, a `String?` or a data source became
        # `v: Any = null`, which is not Kotlin that compiles (ticket
        # kjui-sjui-converter-attr-types-do-not-compile).
        def generate_kotlin_imports
          return "" if !@options[:attributes] || @options[:attributes].empty?

          @options[:attributes].values
                               .flat_map { |type| JsonUIShared::AttributeTypes.kotlin_imports(JsonUIShared::AttributeTypes.parse(type)) }
                               .uniq.map { |i| "import #{i}" }.join("\n")
        end

        def generate_kotlin_parameters
          return "" if !@options[:attributes] || @options[:attributes].empty?

          params = @options[:attributes].map do |key, type|
            actual_key = key.start_with?('@') ? key[1..-1] : key
            "    #{actual_key}: #{map_type_to_kotlin(type)}#{get_default_value(type)},"
          end
          params.join("\n") + "\n"
        end

        def map_type_to_kotlin(type)
          JsonUIShared::AttributeTypes.kotlin_type(JsonUIShared::AttributeTypes.parse(type))
        end

        def get_default_value(type)
          " = #{JsonUIShared::AttributeTypes.kotlin_default(JsonUIShared::AttributeTypes.parse(type))}"
        end

        def format_attributes_for_command
          return "" if !@options[:attributes] || @options[:attributes].empty?
          
          attrs = @options[:attributes].map do |key, type|
            " --attr #{key}:#{type}"
          end.join("")
          
          attrs
        end
      end
    end
  end
end