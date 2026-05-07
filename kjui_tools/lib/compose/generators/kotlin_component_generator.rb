# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/logger'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/generated_marker'

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
          
          if File.exist?(kotlin_file_path)
            @logger.warn "Kotlin file already exists: #{kotlin_file_path}"
            print "Overwrite? (y/n): "
            response = gets.chomp.downcase
            return unless response == 'y'
          end
          
          File.write(kotlin_file_path, kotlin_template)
          @logger.info "Created Kotlin file: #{kotlin_file_path}"
        end
        
        def get_package_name
          config = Core::ConfigManager.load_config
          base_package = config['package_name'] || 'com.example.kotlinjsonui.sample'
          "#{base_package}.extensions"
        end

        def kotlin_template
          if @options[:is_container] != false
            container_template
          else
            non_container_template
          end
        end

        def container_template
          imports = generate_kotlin_imports
          params = generate_kotlin_parameters
          marker_header = Core::GeneratedMarker.comment_header(
            source: @component_name,
            generator: "kjui g converter #{@component_name} --container#{format_attributes_for_command}"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

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

          template += <<~KOTLIN
                modifier: Modifier = Modifier,
                content: @Composable BoxScope.() -> Unit
            ) {
                Box(
                    modifier = modifier
                ) {
                    // Custom container implementation
                    content()
                }
            }

            #{marker_footer}
          KOTLIN

          template
        end

        def non_container_template
          imports = generate_kotlin_imports
          params = generate_kotlin_parameters
          marker_header = Core::GeneratedMarker.comment_header(
            source: @component_name,
            generator: "kjui g converter #{@component_name} --no-container#{format_attributes_for_command}"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

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

            #{marker_footer}
          KOTLIN

          template
        end
        
        def generate_kotlin_imports
          return "" if !@options[:attributes] || @options[:attributes].empty?
          
          imports = []
          @options[:attributes].each do |key, type|
            case type.downcase
            when 'color'
              imports << "import androidx.compose.ui.graphics.Color"
            when 'dp', 'size'
              imports << "import androidx.compose.ui.unit.dp"
              imports << "import androidx.compose.ui.unit.Dp"
            when 'alignment'
              imports << "import androidx.compose.ui.Alignment"
            when 'text', 'string'
              # No special import needed
            when 'int', 'float', 'double'
              # No special import needed
            when 'boolean', 'bool'
              # No special import needed
            end
          end
          
          imports.uniq.join("\n")
        end
        
        def generate_kotlin_parameters
          return "" if !@options[:attributes] || @options[:attributes].empty?
          
          params = []
          @options[:attributes].each do |key, type|
            is_binding = key.start_with?('@')
            actual_key = is_binding ? key[1..-1] : key
            kotlin_type = map_type_to_kotlin(type)
            
            default_value = get_default_value(type)
            params << "    #{actual_key}: #{kotlin_type}#{default_value},"
          end
          
          params.join("\n") + "\n"
        end
        
        
        def map_type_to_kotlin(type)
          case type.downcase
          when 'string', 'text'
            'String'
          when 'int', 'integer'
            'Int'
          when 'float'
            'Float'
          when 'double'
            'Double'
          when 'bool', 'boolean'
            'Boolean'
          when 'color'
            'Color'
          when 'dp', 'size'
            'Dp'
          when 'alignment'
            'Alignment'
          else
            'Any'
          end
        end
        
        def get_default_value(type)
          case type.downcase
          when 'string', 'text'
            ' = ""'
          when 'int', 'integer'
            ' = 0'
          when 'float'
            ' = 0f'
          when 'double'
            ' = 0.0'
          when 'bool', 'boolean'
            ' = false'
          when 'color'
            ' = Color.Unspecified'
          when 'dp', 'size'
            ' = 0.dp'
          when 'alignment'
            ' = Alignment.TopStart'
          else
            ' = null'
          end
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