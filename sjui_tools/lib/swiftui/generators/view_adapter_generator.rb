# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/logger'
require_relative '../../core/converter_generator_core'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/generated_marker'

module SjuiTools
  module SwiftUI
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
          @command = "sjui g adapter #{name}"
        end

        def generate
          @logger.info "Generating view adapter for: #{@view_name}"

          # Determine adapter directory
          adapter_dir = get_adapter_directory

          if adapter_dir.nil?
            @logger.warn "No adapter_directory configured. Skipping adapter generation."
            @logger.info "Add 'adapter_directory: Extensions/Adapters' to sjui_config.yml to enable adapter generation."
            return false
          end

          # Create adapter file
          written = create_adapter_file(adapter_dir)

          # Update registration file
          update_registration_file(adapter_dir)

          # Only when it wrote the adapter: a kept one has said "Skipped
          # existing" / "Kept existing". Until 1.8.121 this line followed
          # either way (ticket kjui-g-view-reports-what-it-did-not-do).
          @logger.success "Successfully generated adapter: #{@adapter_class_name}" if written
          @logger.info "Don't forget to call CustomComponentRegistration.registerAll() in your app initialization."
          true
        end

        private

        def get_adapter_directory
          config = Core::ConfigManager.load_config

          # Use ProjectFinder to get the correct source path (like view_generator.rb)
          source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd

          adapter_dir = config['adapter_directory']
          if adapter_dir && !adapter_dir.strip.empty?
            return File.join(source_path, adapter_dir)
          end

          # Check for extension_directory as fallback
          extension_dir = config['extension_directory']
          if extension_dir && !extension_dir.strip.empty?
            return File.join(source_path, extension_dir, 'Adapters')
          end

          nil
        end

        def create_adapter_file(adapter_dir)
          full_adapter_dir = adapter_dir

          unless File.directory?(full_adapter_dir)
            @logger.info "Creating adapter directory: #{full_adapter_dir}"
            FileUtils.mkdir_p(full_adapter_dir)
          end

          adapter_file = File.join(full_adapter_dir, "#{@adapter_class_name}.swift")

          # Through the converter core's one overwrite decision, so
          # --force / --skip-existing / JUI_SKIP_EXISTING reach this
          # file too, and a closed stdin reads as "n" instead of raising.
          # It says Created or Overwrote; returns whether it wrote.
          JsonUIShared::ConverterGeneratorCore.write_scaffold(
            adapter_file, @options, @logger, noun: 'adapter file', label: 'adapter file', exists_label: 'Adapter file'
          ) { adapter_template }
        end

        def update_registration_file(adapter_dir)
          registration_file = File.join(adapter_dir, 'CustomComponentRegistration.swift')

          if File.exist?(registration_file)
            content = File.read(registration_file, encoding: 'UTF-8')

            # Check if adapter is already registered
            if content.include?("#{@adapter_class_name}()")
              @logger.info "Unchanged #{registration_file}: it already registers #{@adapter_class_name}"
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
              @logger.info "Updated #{registration_file}: registered #{@adapter_class_name}"
            else
              # Said: until 1.8.121 a file without this list was left as it
              # was without a word.
              @logger.warn "Could not register #{@adapter_class_name} in #{registration_file}: it has no " \
                           "`let adapters: [CustomComponentAdapter] = [ … ]` — add `#{@adapter_class_name}()` by hand"
            end
          else
            # Create registration file if it doesn't exist
            File.write(registration_file, registration_template)
            @logger.info "Created #{registration_file} registering #{@adapter_class_name}"
          end
        end

        def adapter_template
          # Convert name to lowercase for component type matching
          # e.g., "Home" -> "home"
          component_type_lower = @name.gsub(/([A-Z])/) { "_#{$1.downcase}" }.sub(/^_/, '')
          marker_header = Core::GeneratedMarker.scaffold_header(
            source: @view_name,
            generator: @command
          )

          <<~SWIFT
            #{marker_header}

            import SwiftUI
            import SwiftJsonUI

            #if DEBUG

            /// Adapter to render #{@view_name} in Dynamic mode
            /// Use in TabView with: "view": "#{component_type_lower}"
            struct #{@adapter_class_name}: CustomComponentAdapter {
                var componentType: String { "#{component_type_lower}" }

                func buildView(
                    component: DynamicComponent,
                    data: [String: Any],
                    viewId: String?,
                    parentOrientation: String?
                ) -> AnyView {
                    // Pass data to the view for binding resolution
                    AnyView(
                        #{@view_name}(data: data)
                    )
                }
            }

            #endif
          SWIFT
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
