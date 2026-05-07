# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/logger'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/generated_marker'

module KjuiTools
  module Compose
    module Generators
      # Generates adapter for existing View to be used in Dynamic mode
      # This allows views like HomeView to be rendered when TabView specifies view: "home"
      class ViewAdapterGenerator
        def initialize(name, options = {})
          @name = name  # PascalCase name like Home
          @view_name = "#{name}View"  # HomeView
          @adapter_class_name = "#{name}ViewAdapter"  # HomeViewAdapter
          @options = options
          @logger = Core::Logger
          @command = "kjui g adapter #{name}"
        end

        def generate
          @logger.info "Generating view adapter for: #{@view_name}"

          config = Core::ConfigManager.load_config
          base_path = config['_config_dir'] || Dir.pwd
          source_directory = config['source_directory'] || 'src/main'
          package_name = config['package_name'] || Core::ProjectFinder.get_package_name || 'com.example.app'

          # Store for use in templates
          @package_name = package_name
          @base_path = base_path
          @source_directory = source_directory

          # Create adapter file in debug source set
          create_adapter_file

          # Update DynamicComponentRegistry
          update_registry_file

          # Create DynamicComponentInitializer (debug/release versions)
          create_dynamic_initializers

          @logger.success "Successfully generated adapter: #{@adapter_class_name}"
          @logger.info "Don't forget to call DynamicComponentInitializer.initialize() in your app initialization."
          true
        end

        private

        def create_adapter_file
          # Create dynamic components directory in debug source set
          adapter_dir = File.join(
            @base_path,
            @source_directory.gsub('main', 'debug'),
            'kotlin',
            @package_name.gsub('.', '/'),
            'dynamic/components/adapters'
          )
          FileUtils.mkdir_p(adapter_dir)

          adapter_file = File.join(adapter_dir, "#{@adapter_class_name}.kt")

          if File.exist?(adapter_file)
            @logger.warn "Adapter file already exists: #{adapter_file}"
            print "Overwrite? (y/n): "
            response = gets.chomp.downcase
            return unless response == 'y'
          end

          File.write(adapter_file, adapter_template)
          @logger.info "Created adapter file: #{adapter_file}"
        end

        def update_registry_file
          registry_file = File.join(
            @base_path,
            @source_directory.gsub('main', 'debug'),
            'kotlin',
            @package_name.gsub('.', '/'),
            'dynamic/DynamicComponentRegistry.kt'
          )

          if !File.exist?(registry_file)
            create_initial_registry
            return
          end

          # Read existing registry
          content = File.read(registry_file, encoding: 'UTF-8')

          # Check if adapter already registered
          if content.include?("\"#{@name.downcase}\"") || content.include?("\"#{to_snake_case(@name)}\"")
            @logger.warn "View '#{@name}' already registered in DynamicComponentRegistry"
            return
          end

          # Add new registration with proper indentation
          # Use snake_case for component type (e.g., "home", "home_screen")
          component_type = to_snake_case(@name)
          new_registration = <<-REGISTRATION.chomp
            "#{component_type}" -> {
                #{@adapter_class_name}.create(json, data)
                true
            }
REGISTRATION

          # Insert before the else statement in when block
          content.sub!(/(when \(type\) \{.*?)(\n            else)/m) do
            existing = $1
            else_clause = $2
            "#{existing}\n#{new_registration}#{else_clause}"
          end

          # Add import if not present
          import_line = "import #{@package_name}.dynamic.components.adapters.#{@adapter_class_name}"
          unless content.include?(import_line)
            # Add import after the last import line
            content.sub!(/(import .+\n)(\n)/) do
              "#{$1}#{import_line}\n#{$2}"
            end
          end

          File.write(registry_file, content)
          @logger.info "Updated DynamicComponentRegistry with #{@adapter_class_name}"
        end

        def create_initial_registry
          registry_dir = File.join(
            @base_path,
            @source_directory.gsub('main', 'debug'),
            'kotlin',
            @package_name.gsub('.', '/'),
            'dynamic'
          )
          FileUtils.mkdir_p(registry_dir)

          registry_file = File.join(registry_dir, 'DynamicComponentRegistry.kt')

          component_type = to_snake_case(@name)

          content = <<~KOTLIN
            package #{@package_name}.dynamic

            import androidx.compose.runtime.Composable
            import com.google.gson.JsonObject
            import #{@package_name}.dynamic.components.adapters.#{@adapter_class_name}

            /**
             * Registry for dynamic custom components
             * Auto-generated by #{@command}
             */
            object DynamicComponentRegistry {
                @Composable
                fun createCustomComponent(
                    type: String,
                    json: JsonObject,
                    data: Map<String, Any>
                ): Boolean {
                    return when (type) {
                        "#{component_type}" -> {
                            #{@adapter_class_name}.create(json, data)
                            true
                        }
                        else -> false
                    }
                }
            }
          KOTLIN

          File.write(registry_file, content)
          @logger.info "Created DynamicComponentRegistry with #{@adapter_class_name}"
        end

        def adapter_template
          # Convert name to snake_case for component type matching and subdirectory
          # e.g., "Home" -> "home", "HomeScreen" -> "home_screen"
          component_type = to_snake_case(@name)
          marker_header = Core::GeneratedMarker.comment_header(
            source: @view_name,
            generator: @command
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          <<~KOTLIN
            #{marker_header}

            package #{@package_name}.dynamic.components.adapters

            import androidx.compose.runtime.Composable
            import com.google.gson.JsonObject
            import #{@package_name}.views.#{component_type}.#{@view_name}

            /**
             * Adapter to render #{@view_name} in Dynamic mode
             * Use in TabView with: "view": "#{component_type}"
             */
            object #{@adapter_class_name} {

                /**
                 * Create the view
                 */
                @Composable
                fun create(
                    json: JsonObject,
                    data: Map<String, Any>
                ) {
                    // Render the actual view
                    #{@view_name}()
                }
            }

            #{marker_footer}
          KOTLIN
        end

        def to_snake_case(str)
          str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
             .gsub(/([a-z\d])([A-Z])/, '\1_\2')
             .downcase
        end

        def create_dynamic_initializers
          # Create debug version
          debug_dir = File.join(
            @base_path,
            @source_directory.gsub('main', 'debug'),
            'kotlin',
            @package_name.gsub('.', '/')
          )
          FileUtils.mkdir_p(debug_dir)

          debug_file = File.join(debug_dir, 'DynamicComponentInitializer.kt')

          # Only create if it doesn't exist yet
          unless File.exist?(debug_file)
            File.write(debug_file, generate_debug_initializer_content)
            @logger.info "Created DynamicComponentInitializer (debug)"
          end

          # Create release version
          release_dir = File.join(
            @base_path,
            @source_directory.gsub('main', 'release'),
            'kotlin',
            @package_name.gsub('.', '/')
          )
          FileUtils.mkdir_p(release_dir)

          release_file = File.join(release_dir, 'DynamicComponentInitializer.kt')

          # Only create if it doesn't exist yet
          unless File.exist?(release_file)
            File.write(release_file, generate_release_initializer_content)
            @logger.info "Created DynamicComponentInitializer (release)"
          end
        end

        def generate_debug_initializer_content
          <<~KOTLIN
            package #{@package_name}

            import androidx.compose.runtime.Composable
            import com.google.gson.JsonObject
            import com.kotlinjsonui.core.Configuration
            import #{@package_name}.dynamic.DynamicComponentRegistry

            /**
             * Debug-only initializer for custom components in dynamic mode
             * Auto-generated by #{@command}
             */
            object DynamicComponentInitializer {

                /**
                 * Register custom component handler for dynamic mode
                 * This is only available in debug builds where DynamicComponentRegistry exists
                 */
                fun initialize() {
                    Configuration.customComponentHandler = { type, json, data ->
                        DynamicComponentRegistry.createCustomComponent(type, json, data)
                    }
                }
            }
          KOTLIN
        end

        def generate_release_initializer_content
          <<~KOTLIN
            package #{@package_name}

            /**
             * Release version of DynamicComponentInitializer (no-op)
             * Auto-generated by #{@command}
             */
            object DynamicComponentInitializer {

                /**
                 * No-op in release builds
                 */
                fun initialize() {
                    // Dynamic component registry is not available in release builds
                }
            }
          KOTLIN
        end
      end
    end
  end
end
