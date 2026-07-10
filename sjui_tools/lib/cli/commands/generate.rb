# frozen_string_literal: true

require 'optparse'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

module SjuiTools
  module CLI
    module Commands
      class Generate
        SUBCOMMANDS = {
          'view' => 'Generate a new view with JSON and binding',
          'partial' => 'Generate a partial view',
          'collection' => 'Generate a collection view',
          'binding' => 'Generate binding file',
          'converter' => 'Generate a custom converter',
          'adapter' => 'Generate adapter for existing View (for Dynamic mode)'
        }.freeze

        def run(args)
          subcommand = args.shift

          if subcommand.nil? || subcommand == 'help'
            show_help
            return
          end

          unless SUBCOMMANDS.key?(subcommand)
            puts "Unknown generate command: #{subcommand}"
            show_help
            exit 1
          end

          # Detect mode
          mode = Core::ConfigManager.detect_mode

          case subcommand
          when 'view'
            generate_view(args, mode)
          when 'partial'
            generate_partial(args, mode)
          when 'collection'
            generate_collection(args, mode)
          when 'uikit'
            generate_binding(args, mode)
          when 'converter'
            generate_converter(args, mode)
          when 'adapter'
            generate_adapter(args, mode)
          end
        end

        private

        def generate_view(args, mode)
          options = parse_view_options(args)
          name = args.shift

          if name.nil? || name.empty?
            puts "Error: View name is required"
            puts "Usage: sjui generate view <name> [options]"
            exit 1
          end

          # Setup project paths
          unless Core::ProjectFinder.setup_paths
            puts "Error: Could not find project file (.xcodeproj or Package.swift)"
            exit 1
          end

          case mode
          when 'uikit'
            require_relative '../../uikit/xcode_project/generators/view_generator'
            generator = SjuiTools::UIKit::XcodeProject::Generators::ViewGenerator.new(name, options)
            generator.generate
          when 'swiftui'
            require_relative '../../swiftui/generators/view_generator'
            generator = SjuiTools::SwiftUI::Generators::ViewGenerator.new(name, options)
            generator.generate
          else
            puts "Error: Unknown mode: #{mode}"
            exit 1
          end
        end

        def generate_partial(args, mode)
          name = args.shift

          if name.nil? || name.empty?
            puts "Error: Partial name is required"
            puts "Usage: sjui generate partial <name>"
            exit 1
          end

          # Setup project paths
          unless Core::ProjectFinder.setup_paths
            puts "Error: Could not find project file (.xcodeproj or Package.swift)"
            exit 1
          end

          case mode
          when 'uikit'
            require_relative '../../uikit/xcode_project/generators/partial_generator'
            project_file = Core::ProjectFinder.find_project_file
            generator = SjuiTools::UIKit::XcodeProject::Generators::PartialGenerator.new(project_file)
            generator.generate(name)
          when 'swiftui'
            require_relative '../../swiftui/generators/partial_generator'
            generator = SjuiTools::SwiftUI::Generators::PartialGenerator.new(name)
            generator.generate
          else
            puts "Error: Unknown mode: #{mode}"
            exit 1
          end
        end

        def generate_collection(args, mode)
          name = args.shift

          if name.nil? || name.empty?
            puts "Error: Collection name is required"
            puts "Usage: sjui generate collection <name>"
            exit 1
          end

          # Setup project paths
          unless Core::ProjectFinder.setup_paths
            puts "Error: Could not find project file (.xcodeproj or Package.swift)"
            exit 1
          end

          case mode
          when 'uikit'
            require_relative '../../uikit/xcode_project/generators/collection_generator'
            project_file = Core::ProjectFinder.find_project_file
            generator = SjuiTools::UIKit::XcodeProject::Generators::CollectionGenerator.new(project_file)
            generator.generate(name)
          when 'swiftui'
            require_relative '../../swiftui/generators/collection_generator'
            generator = SjuiTools::SwiftUI::Generators::CollectionGenerator.new(name)
            generator.generate
          else
            puts "Error: Unknown mode: #{mode}"
            exit 1
          end
        end

        def generate_binding(args, mode)
          name = args.shift

          if name.nil? || name.empty?
            puts "Error: Binding name is required"
            puts "Usage: sjui generate binding <name>"
            exit 1
          end

          if mode != 'uikit'
            puts "Binding generation is only available in UIKit mode"
            exit 1
          end

          require_relative '../../uikit/xcode_project/generators/binding_generator'
          generator = SjuiTools::UIKit::XcodeProject::Generators::BindingGenerator.new(name)
          generator.generate
        end

        def generate_converter(args, mode)
          options = parse_converter_options(args)
          name = args.shift

          if name.nil? || name.empty?
            puts "Error: Converter name is required"
            puts "Usage: sjui generate converter <name> [options]"
            exit 1
          end

          case mode
          when 'uikit'
            require_relative '../../uikit/xcode_project/generators/converter_generator'
            generator = SjuiTools::UIKit::XcodeProject::Generators::ConverterGenerator.new(name, options)
            generator.generate
          when 'swiftui'
            require_relative '../../swiftui/generators/converter_generator'
            generator = SjuiTools::SwiftUI::Generators::ConverterGenerator.new(name, options)
            generator.generate
          else
            puts "Error: Unknown mode: #{mode}"
            exit 1
          end
        end

        def parse_view_options(args)
          options = {
            root: false,
            mode: nil
          }

          OptionParser.new do |opts|
            opts.on('--root', 'Generate root view controller') do
              options[:root] = true
            end

            opts.on('--mode MODE', 'Override mode (uikit, swiftui, dynamic)') do |mode|
              options[:mode] = mode
            end
          end.parse!(args)

          options
        end

        def parse_converter_options(args)
          options = {
            use_default_attributes: true,
            attributes: {},
            is_container: nil,  # nil means auto-detect based on children (SwiftUI only)
            class_name: nil,
            import_module: nil
          }

          OptionParser.new do |opts|
            opts.on('--no-default-attributes', 'Do not use default attributes') do
              options[:use_default_attributes] = false
            end

            opts.on('--container', 'Force component to be a container (handles children) [SwiftUI only]') do
              options[:is_container] = true
            end

            opts.on('--no-container', 'Force component to not be a container (ignores children) [SwiftUI only]') do
              options[:is_container] = false
            end

            opts.on('--class-name NAME', 'Custom class name for the view [UIKit only]') do |name|
              options[:class_name] = name
            end

            opts.on('--import-module MODULE', 'Import module for the custom view [UIKit only]') do |module_name|
              options[:import_module] = module_name
            end

            opts.on('--attributes KEY:TYPE', 'Add custom attribute (can be used multiple times or comma-separated)') do |attr|
              # Handle comma-separated attributes
              split_top_level_commas(attr).each do |single_attr|
                key, type = single_attr.strip.split(':', 2)
                if key && type
                  options[:attributes][key] = type
                else
                  puts "Error: Invalid attribute format. Use KEY:TYPE"
                  exit 1
                end
              end
            end
          end.parse!(args)

          options
        end

        # Split an --attributes list on top-level commas only. Spec prop
        # types can contain commas themselves (multi-arg closure types like
        # `((String, String) -> Void)?`) — commas nested in parens/brackets
        # belong to the type, not the list.
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

        def generate_adapter(args, mode)
          name = args.shift

          if name.nil? || name.empty?
            puts "Error: View name is required"
            puts "Usage: sjui generate adapter <name>"
            puts "Example: sjui g adapter Home  # Creates HomeViewAdapter for HomeView"
            exit 1
          end

          if mode != 'swiftui'
            puts "Adapter generation is only available in SwiftUI mode"
            exit 1
          end

          # Setup project paths (like other generators)
          unless Core::ProjectFinder.setup_paths
            puts "Error: Could not find project file (.xcodeproj or Package.swift)"
            exit 1
          end

          require_relative '../../swiftui/generators/view_adapter_generator'
          generator = SjuiTools::SwiftUI::Generators::ViewAdapterGenerator.new(name)
          generator.generate
        end

        def show_help
          puts "Usage: sjui generate SUBCOMMAND [options]"
          puts
          puts "Subcommands:"
          SUBCOMMANDS.each do |cmd, desc|
            puts "  #{cmd.ljust(12)} #{desc}"
          end
          puts
          puts "Examples:"
          puts "  sjui g view HomeView           # Generate a view"
          puts "  sjui g view RootView --root    # Generate root view"
          puts "  sjui g partial Header          # Generate a partial"
          puts "  sjui g collection Post/Cell    # Generate collection cell"
          puts "  sjui g binding CustomBinding   # Generate binding file"
          puts
          puts "  # SwiftUI converter"
          puts "  sjui g converter MyConverter   # Generate custom converter"
          puts "  sjui g converter MyConverter --attributes text:String,color:Color"
          puts
          puts "  # UIKit converter"
          puts "  sjui g converter MyCustomView  # Generate custom UIKit converter"
          puts "  sjui g converter MyCustomView --attributes title:String,count:Int"
          puts "  sjui g converter MyCustomView --class-name CustomUIView --import-module CustomModule"
          puts
          puts "  # View adapter for Dynamic mode (allows TabView to render existing views)"
          puts "  sjui g adapter Home            # Creates HomeViewAdapter for HomeView"
          puts "  sjui g adapter Search          # Creates SearchViewAdapter for SearchView"
        end
      end
    end
  end
end
