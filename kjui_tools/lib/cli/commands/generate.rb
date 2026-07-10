# frozen_string_literal: true

require 'optparse'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

module KjuiTools
  module CLI
    module Commands
      class Generate
        SUBCOMMANDS = {
          'view' => 'Generate a new view with JSON and binding',
          'partial' => 'Generate a partial view',
          'collection' => 'Generate a collection cell view',
          'cell' => 'Generate a collection cell view (alias for collection)',
          'binding' => 'Generate binding file',
          'converter' => 'Generate a custom component converter',
          'adapter' => 'Generate adapter for existing View (for Dynamic mode)'
        }.freeze

        def run(args)
          # Parse global options first
          global_options = parse_global_options(args)
          
          subcommand = args.shift
          
          # Load config to get default mode
          config = Core::ConfigManager.load_config
          
          # Use mode from options if provided, otherwise from config, otherwise default to compose
          mode = global_options[:mode] || config['mode'] || 'compose'
          
          # If no subcommand, generate all based on mode
          if subcommand.nil?
            if mode == 'xml'
              generate_all_xml_layouts(config)
            else
              generate_all_compose_views(config)
            end
            return
          end
          
          if subcommand == 'help' || subcommand == '--help' || subcommand == '-h'
            show_help
            return
          end
          
          unless SUBCOMMANDS.key?(subcommand)
            # Check if it's a layout name (no subcommand, just generate that layout)
            if mode == 'xml' && !subcommand.start_with?('-')
              generate_specific_xml_layout(subcommand, args, config)
              return
            elsif !subcommand.start_with?('-')
              # For compose mode, treat it as a layout name and build it
              puts "Building layout: #{subcommand}"
              generate_specific_compose_layout(subcommand, args, config)
              return
            end
            
            puts "Unknown generate command: #{subcommand}"
            show_help
            exit 1
          end
          
          case subcommand
          when 'view'
            generate_view(args, mode)
          when 'partial'
            generate_partial(args, mode)
          when 'collection', 'cell'
            generate_cell(args, mode)
          when 'binding'
            generate_binding(args, mode)
          when 'converter'
            generate_converter(args, mode)
          when 'adapter'
            generate_adapter(args, mode)
          end
        end

        private
        
        def parse_global_options(args)
          options = { mode: nil }
          
          # Look for mode option and remove it from args
          args.each_with_index do |arg, index|
            if arg == '--mode' || arg == '-m'
              if args[index + 1]
                options[:mode] = args[index + 1]
                args.delete_at(index + 1)
                args.delete_at(index)
                break
              end
            elsif arg.start_with?('--mode=')
              options[:mode] = arg.split('=', 2)[1]
              args.delete_at(index)
              break
            end
          end
          
          options
        end

        def generate_view(args, mode)
          options = parse_view_options(args)
          name = args.shift
          
          if name.nil? || name.empty?
            puts "Error: View name is required"
            puts "Usage: kjui generate view <name> [options]"
            exit 1
          end
          
          # Setup project paths
          Core::ProjectFinder.setup_paths
          
          case mode
          when 'xml'
            require_relative '../../xml/generators/view_generator'
            generator = KjuiTools::Xml::Generators::ViewGenerator.new(name, options)
            generator.generate
          when 'compose'
            require_relative '../../compose/generators/view_generator'
            generator = KjuiTools::Compose::Generators::ViewGenerator.new(name, options)
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
            puts "Usage: kjui generate partial <name>"
            exit 1
          end
          
          case mode
          when 'xml'
            require_relative '../../xml/generators/partial_generator'
            generator = KjuiTools::Xml::Generators::PartialGenerator.new(name)
            generator.generate
          when 'compose'
            require_relative '../../compose/generators/partial_generator'
            generator = KjuiTools::Compose::Generators::PartialGenerator.new(name)
            generator.generate
          end
        end

        def generate_cell(args, mode)
          name = args.shift
          
          if name.nil? || name.empty?
            puts "Error: Collection name is required"
            puts "Usage: kjui generate collection <name>"
            exit 1
          end
          
          # Setup project paths
          Core::ProjectFinder.setup_paths
          
          case mode
          when 'xml'
            puts "Collection generation is not available in XML mode"
            exit 1
          when 'compose'
            require_relative '../../compose/generators/cell_generator'
            generator = KjuiTools::Compose::Generators::CellGenerator.new(name)
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
            puts "Usage: kjui generate binding <name>"
            exit 1
          end
          
          if mode != 'xml'
            puts "Binding generation is only available in XML mode"
            exit 1
          end
          
          require_relative '../../xml/generators/binding_generator'
          generator = KjuiTools::Xml::Generators::BindingGenerator.new(name)
          generator.generate
        end
        
        def generate_converter(args, mode)
          unless mode == 'compose'
            puts "Converter generation is only available in Compose mode"
            exit 1
          end
          
          name = args.shift
          unless name
            puts "Error: Please provide a component name"
            puts "Usage: kjui generate converter <ComponentName> [options]"
            puts "Options:"
            puts "  --container         Generate as container component"
            puts "  --no-container      Generate as non-container component"
            puts "  --attr KEY:TYPE     Add attribute (can be used multiple times)"
            puts "  --binding KEY:TYPE  Add binding attribute"
            puts
            puts "Examples:"
            puts "  kjui g converter MyCard --container"
            puts "  kjui g converter StatusBadge --attr text:String --attr color:Color"
            puts "  kjui g converter DataCard --binding title:String --attr icon:String"
            exit 1
          end
          
          options = parse_converter_options(args)
          
          require_relative '../../compose/generators/converter_generator'
          generator = KjuiTools::Compose::Generators::ConverterGenerator.new(name, options)
          generator.generate
        end
        
        def parse_converter_options(args)
          options = {
            is_container: nil,
            attributes: {}
          }
          
          # Parse flags first
          parser = OptionParser.new do |opts|
            opts.on('--container', 'Generate as container component') do
              options[:is_container] = true
            end
            
            opts.on('--no-container', 'Generate as non-container component') do
              options[:is_container] = false
            end
            
            opts.on('--attr KEY:TYPE', 'Add attribute') do |attr|
              # limit 2: the type itself may contain ':' or ',' (closure /
              # dictionary types from component specs)
              key, type = attr.split(':', 2)
              if key && type
                options[:attributes][key] = type
              else
                puts "Invalid attribute format. Use KEY:TYPE (e.g., text:String)"
                exit 1
              end
            end

            opts.on('--binding KEY:TYPE', 'Add binding attribute') do |attr|
              key, type = attr.split(':', 2)
              if key && type
                # Prefix with @ to indicate binding
                options[:attributes]["@#{key}"] = type
              else
                puts "Invalid binding format. Use KEY:TYPE (e.g., title:String)"
                exit 1
              end
            end
          end
          
          parser.parse!(args)
          
          # Parse remaining arguments as attributes (simplified syntax)
          args.each do |arg|
            if arg.include?(':')
              key, type = arg.split(':', 2)
              if key && type
                # Check if it's a binding (starts with @)
                if key.start_with?('@')
                  options[:attributes][key] = type
                else
                  options[:attributes][key] = type
                end
              end
            end
          end
          
          options
        end

        def parse_view_options(args)
          options = {
            root: false,
            mode: nil,
            type: nil,
            force: false
          }
          
          OptionParser.new do |opts|
            opts.on('--root', 'Generate root view/activity') do
              options[:root] = true
            end
            
            opts.on('--mode MODE', 'Override mode (xml, compose)') do |mode|
              options[:mode] = mode
            end
            
            opts.on('--type TYPE', 'View type for XML mode (activity, fragment)') do |type|
              options[:type] = type
            end
            
            opts.on('--activity', 'Generate as Activity (XML mode)') do
              options[:type] = 'activity'
            end
            
            opts.on('--fragment', 'Generate as Fragment (XML mode)') do
              options[:type] = 'fragment'
            end
            
            opts.on('-f', '--force', 'Force overwrite existing files') do
              options[:force] = true
            end
          end.parse!(args)
          
          options
        end

        def generate_all_xml_layouts(config)
          require_relative '../../xml/xml_generator'
          require_relative '../commands/generate_xml'
          
          puts "Generating all XML layouts..."
          CLI::Commands::GenerateXml.run([])
        end
        
        def generate_all_compose_views(config)
          require_relative '../../compose/compose_builder'
          
          puts "Generating all Compose views..."
          # Call the existing Compose builder
          system("ruby #{File.join(File.dirname(__FILE__), '../../..', 'bin', 'kjui')} build")
        end
        
        def generate_specific_xml_layout(layout_name, args, config)
          require_relative '../../xml/xml_generator'
          require_relative '../commands/generate_xml'
          
          puts "Generating XML for layout: #{layout_name}"
          CLI::Commands::GenerateXml.run([layout_name] + args)
        end
        
        def generate_specific_compose_layout(layout_name, args, config)
          require_relative '../../compose/compose_builder'
          
          puts "Building Compose layout: #{layout_name}"
          # TODO: Implement single layout generation for compose
          system("ruby #{File.join(File.dirname(__FILE__), '../../..', 'bin', 'kjui')} build")
        end

        def generate_adapter(args, mode)
          name = args.shift

          if name.nil? || name.empty?
            puts "Error: View name is required"
            puts "Usage: kjui generate adapter <name>"
            puts "Example: kjui g adapter Home  # Creates HomeViewAdapter for HomeView"
            exit 1
          end

          unless mode == 'compose'
            puts "Adapter generation is only available in Compose mode"
            exit 1
          end

          # Setup project paths
          Core::ProjectFinder.setup_paths

          require_relative '../../compose/generators/view_adapter_generator'
          generator = KjuiTools::Compose::Generators::ViewAdapterGenerator.new(name)
          generator.generate
        end

        def show_help
          puts "Usage: kjui generate [SUBCOMMAND] [options]"
          puts
          puts "Global Options:"
          puts "  --mode, -m MODE        Override mode (xml/compose)"
          puts "                         Default: use config.json mode"
          puts
          puts "When in XML mode:"
          puts "  kjui generate              # Generate all XML layouts"
          puts "  kjui generate test_menu    # Generate specific XML layout"
          puts
          puts "When in Compose mode:"
          puts "  kjui generate              # Generate all Compose views"
          puts
          puts "Subcommands:"
          SUBCOMMANDS.each do |cmd, desc|
            puts "  #{cmd.ljust(12)} #{desc}"
          end
          puts
          puts "View Options (XML mode):"
          puts "  --activity             Generate as Activity (default)"
          puts "  --fragment             Generate as Fragment"
          puts "  --type TYPE            Specify type (activity/fragment)"
          puts "  -f, --force            Force overwrite existing files"
          puts
          puts "Examples:"
          puts "  kjui g                     # Generate all (based on config mode)"
          puts "  kjui g --mode xml          # Generate all XML layouts"
          puts "  kjui g --mode compose      # Generate all Compose views"
          puts "  kjui g view HomeView --mode xml --activity  # Generate Activity"
          puts "  kjui g view ProfileView --mode xml --fragment # Generate Fragment"
          puts "  kjui g view MainView --mode compose  # Generate Compose view"
          puts "  kjui g converter MyCard --container # Generate custom component"
          puts
          puts "  # View adapter for Dynamic mode (allows TabView to render existing views)"
          puts "  kjui g adapter Home            # Creates HomeViewAdapter for HomeView"
          puts "  kjui g adapter Search          # Creates SearchViewAdapter for SearchView"
        end
      end
    end
  end
end