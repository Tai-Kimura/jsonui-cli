# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'
require_relative '../../core/converter_generator_core'

module SjuiTools
  module SwiftUI
    module Generators
      class ViewGenerator
        def initialize(name, options = {})
          @name = name
          @options = options
          @config = Core::ConfigManager.load_config
          @command = build_command_string(name, options)
        end

        def build_command_string(name, options)
          cmd = "sjui g view #{name}"
          cmd += " --root" if options[:root]
          cmd
        end

        def generate
          # Parse name for subdirectories
          parts = @name.split('/')
          view_name = parts.last
          subdirectory = parts[0...-1].join('/') if parts.length > 1
          
          # Convert to proper case
          view_class_name = to_pascal_case(view_name)
          json_file_name = to_snake_case(view_name)
          
          # Get directories from config
          source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
          layouts_dir = @config['layouts_directory'] || 'Layouts'
          view_dir = @config['view_directory'] || 'View'
          viewmodel_dir = @config['viewmodel_directory'] || 'ViewModel'
          data_dir = @config['data_directory'] || 'Data'
          
          # Create full paths with subdirectory support
          if subdirectory
            # Layouts keep snake_case directory names
            json_path = File.join(source_path, layouts_dir, subdirectory)
            # Swift directories use PascalCase to match view folder naming convention
            pascal_subdir = subdirectory.split('/').map { |s| to_pascal_case(s) }.join('/')
            swift_path = File.join(source_path, view_dir, pascal_subdir, view_class_name)
            viewmodel_path = File.join(source_path, viewmodel_dir, pascal_subdir)
            # Data files are always in root Data directory
            data_path = File.join(source_path, data_dir)
          else
            json_path = File.join(source_path, layouts_dir)
            # Create folder for the view in View directory
            swift_path = File.join(source_path, view_dir, view_class_name)
            viewmodel_path = File.join(source_path, viewmodel_dir)
            data_path = File.join(source_path, data_dir)
          end
          
          # Create directories if they don't exist
          FileUtils.mkdir_p(json_path)
          FileUtils.mkdir_p(swift_path)
          FileUtils.mkdir_p(viewmodel_path)
          FileUtils.mkdir_p(data_path)
          
          # Each file through the one overwrite decision the generate commands
          # share: one that is there is the app's — kept unless --force (or
          # "y" at the prompt); a closed stdin and --skip-existing keep it.
          # Each is said as it goes (Created / Overwrote / Kept / Skipped).
          json_file = File.join(json_path, "#{json_file_name}.json")
          main_swift_file = File.join(swift_path, "#{view_class_name}View.swift")
          generated_swift_file = File.join(swift_path, "#{view_class_name}GeneratedView.swift")
          data_file = File.join(data_path, "#{view_class_name}Data.swift")
          viewmodel_file = File.join(viewmodel_path, "#{view_class_name}ViewModel.swift")
          core = JsonUIShared::ConverterGeneratorCore
          record = core.scaffold_record
          options = @options.merge(scaffold_files: record)
          scaffold = lambda do |path, noun, &content|
            core.write_scaffold(path, options, Core::Logger,
                                noun: noun, label: noun, exists_label: noun.sub(/\A\w/, &:upcase), &content)
          end

          scaffold.call(json_file, 'JSON layout') { json_template(view_class_name) }
          scaffold.call(main_swift_file, 'view') { main_view_template(view_class_name) }
          scaffold.call(generated_swift_file, 'generated view') do
            generated_view_template(view_class_name, json_file_name, subdirectory)
          end
          scaffold.call(data_file, 'data file') { data_template(view_class_name) }
          scaffold.call(viewmodel_file, 'ViewModel') { viewmodel_template(view_class_name, json_file_name, subdirectory) }

          # Update App.swift if --root option is specified
          app_updated = update_app_file(view_class_name) if @options[:root]

          # The counts, from the record (until 1.8.121 a list whatever the run
          # had done — ticket kjui-g-view-reports-what-it-did-not-do).
          core.report_scaffold_record("SwiftUI view #{view_class_name}", record, Core::Logger)

          if app_updated
            Core::Logger.info "  Updated App.swift to use #{view_class_name}View as root"
          end
          
          Core::Logger.info ""
          Core::Logger.info "Next steps:"
          Core::Logger.info "  1. Edit the JSON layout in #{json_file}"
          Core::Logger.info "  2. Run 'sjui build' to generate the SwiftUI code"
        end

        private

        def to_pascal_case(str)
          # Handle camelCase and PascalCase input
          # First convert to snake_case, then to PascalCase
          snake = str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                     .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                     .downcase
          snake.split(/[_\-]/).map(&:capitalize).join
        end

        def to_snake_case(str)
          str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
             .gsub(/([a-z\d])([A-Z])/, '\1_\2')
             .downcase
        end

        def json_template(view_name)
          template = {
            generatedBy: @command,
            type: "View",
            width: "matchParent",
            height: "matchParent",
            background: "#FFFFFF",
            orientation: "vertical",
            child: [
              {
                data: [
                  {
                    name: "title",
                    class: "String",
                    defaultValue: view_name
                  }
                ]
              },
              {
                type: "Label",
                id: "title_label",
                width: "wrapContent",
                height: "wrapContent",
                topMargin: 20,
                text: "@{title}",
                fontSize: 24,
                fontColor: "#000000"
              }
            ]
          }

          JSON.pretty_generate(template)
        end

        def update_app_file(view_name)
          source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
          
          # Find App.swift file
          app_files = Dir.glob(File.join(source_path, '**/*App.swift'))
          if app_files.empty?
            Core::Logger.warn "Could not find App.swift file to update"
            return false
          end
          
          app_file = app_files.first
          content = File.read(app_file)
          
          # Update WindowGroup content
          # Match patterns like: WindowGroup { SomeView() }
          updated = false
          
          # Pattern 1: Empty WindowGroup
          if content =~ /WindowGroup\s*\{\s*\}/m
            content.gsub!(/WindowGroup\s*\{\s*\}/m, "WindowGroup {\n            #{view_name}View()\n        }")
            updated = true
          # Pattern 2: Direct view in WindowGroup
          elsif content =~ /WindowGroup\s*\{[^}]*\w+View\(\)[^}]*\}/m
            content.gsub!(/WindowGroup\s*\{[^}]*\}/m, "WindowGroup {\n            #{view_name}View()\n        }")
            updated = true
          # Pattern 3: View with modifiers
          elsif content =~ /WindowGroup\s*\{[^}]*\w+View\(\)[\s\S]*?\n\s*\}/m
            content.gsub!(/(WindowGroup\s*\{)[^}]*(\})/m, "\\1\n            #{view_name}View()\n        \\2")
            updated = true
          end
          
          if updated
            File.write(app_file, content)
            Core::Logger.debug "Updated #{app_file}"
          else
            Core::Logger.warn "Could not update App.swift automatically"
            Core::Logger.info "Please manually update your App.swift to use #{view_name}View()"
          end
          updated
        end
        
        def main_view_template(view_name)
          <<~SWIFT
            //
            //  #{view_name}View.swift
            //  Generated by: #{@command}
            //

            import SwiftUI
            import SwiftJsonUI
            import Combine

            struct #{view_name}View: View {
                @StateObject private var viewModel: #{view_name}ViewModel

                // Default initializer
                init() {
                    _viewModel = StateObject(wrappedValue: #{view_name}ViewModel())
                }

                // Initializer with data parameter for Include support
                init(data: [String: Any]) {
                    let vm = #{view_name}ViewModel()
                    vm.data.update(dictionary: data)
                    _viewModel = StateObject(wrappedValue: vm)
                }

                var body: some View {
                    #{view_name}GeneratedView(data: $viewModel.data, viewModel: viewModel)
                        // Add navigation destinations, sheets, or other view-level modifiers here
                }
            }

            // MARK: - Preview
            struct #{view_name}View_Previews: PreviewProvider {
                static var previews: some View {
                    #{view_name}View()
                }
            }
          SWIFT
        end

        def generated_view_template(view_name, json_name, subdirectory)
          # Determine the JSON path reference for loading
          json_reference = subdirectory ? "#{subdirectory}/#{json_name}" : json_name

          <<~SWIFT
            //
            //  #{view_name}GeneratedView.swift
            //  Generated by: #{@command}
            //

            import SwiftUI
            import SwiftJsonUI
            import Combine

            struct #{view_name}GeneratedView: View {
                @SwiftUI.Binding var data: #{view_name}Data
                var viewModel: Any = ()

                var body: some View {
                    Group {
        #if DEBUG
                        if ViewSwitcher.isDynamicMode {
                            DynamicView(jsonName: "#{json_reference}", viewId: "#{json_name}_view", data: data.toDictionary(binding: $data))
                        } else {
                            generatedBody
                        }
        #else
                        generatedBody
        #endif
                    }
                    // Requires SwiftJsonUI >= 10.6.0 (embed init-params child-side wiring)
                    .receiveEmbedInitParams(to: viewModel)
                }

                @ViewBuilder
                private var generatedBody: some View {
                        // Generated SwiftUI code from #{json_reference}.json
                        // This will be updated when you run 'sjui build'
                        // >>> GENERATED_CODE_START
                        VStack {
                            Text(data.title)
                                .font(.title)
                                .padding()

                            Text("Run 'sjui build' to generate SwiftUI code")
                                .font(.caption)
                                .foregroundColor(.gray)
                        }
                        // >>> GENERATED_CODE_END
                }
            }
          SWIFT
        end

        def data_template(view_name)
          <<~SWIFT
            //
            //  #{view_name}Data.swift
            //  Generated by: #{@command}
            //

            import Foundation
            import SwiftUI
            import SwiftJsonUI

            struct #{view_name}Data {
                // Data properties from JSON
                var title: String = "#{view_name}"

                // Add more data properties as needed based on your JSON structure

                // Action closures (called from generated views)
                var onTap: (() -> Void)?

                // Update properties from dictionary
                mutating func update(dictionary: [String: Any]) {
                    if let value = dictionary["title"] {
                        if let stringValue = value as? String {
                            self.title = stringValue
                        }
                    }
                }

                // Convert properties to dictionary for Dynamic mode
                func toDictionary() -> [String: Any] {
                    var dict: [String: Any] = [:]

                    // Data properties
                    dict["title"] = title

                    // Action closures
                    if let onTap = onTap {
                        dict["onTap"] = onTap
                    }

                    return dict
                }
            }
          SWIFT
        end

        def viewmodel_template(view_name, json_name, subdirectory)
          # Determine the JSON path reference for loading
          json_reference = subdirectory ? "#{subdirectory}/#{json_name}" : json_name

          <<~SWIFT
            //
            //  #{view_name}ViewModel.swift
            //  Generated by: #{@command}
            //

            import Foundation
            import Combine
            import SwiftJsonUI

            class #{view_name}ViewModel: ObservableObject {
                // JSON file reference for hot reload
                let jsonFileName = "#{json_reference}"

                // Data model (passed to GeneratedView via EnvironmentObject)
                @Published var data = #{view_name}Data()

                init() {
                    setupActionHandlers()
                }

                // Setup action closures on data object
                private func setupActionHandlers() {
                    data.onTap = { [weak self] in
                        self?.onTap()
                    }
                }

                // Action handlers
                func onAppear() {
                    // Called when view appears
                }

                // Add more action handlers as needed
                func onTap() {
                    // Handle tap events
                }
            }
          SWIFT
        end
      end
    end
  end
end