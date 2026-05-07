# frozen_string_literal: true

require 'optparse'
require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

module KjuiTools
  module CLI
    module Commands
      class Setup
        def run(args)
          options = parse_options(args)
          
          # Check and install dependencies first
          ensure_dependencies_installed
          
          # Setup project paths
          Core::ProjectFinder.setup_paths
          
          # Load config to determine mode
          config = Core::ConfigManager.load_config
          mode = config['mode'] || 'compose'
          
          puts "Setting up KotlinJsonUI project in #{mode} mode..."
          
          # Setup based on mode
          case mode
          when 'compose'
            setup_compose_project
          when 'xml'
            setup_xml_project
          when 'all'
            setup_xml_project
            setup_compose_project
          end
          
          puts "\nSetup complete!"
          if mode == 'compose'
            puts "Next steps:"
            puts "  1. Create your layouts in the assets/Layouts directory"
            puts "  2. Run 'kjui convert' to generate Compose code"
            puts "  3. Build your project with Gradle"
          else
            puts "Next steps:"
            puts "  1. Run 'kjui g view HomeView' to generate your first view"
            puts "  2. Build your project with Gradle"
          end
        end

        private

        def ensure_dependencies_installed
          # Check if Gemfile.lock exists
          kjui_tools_dir = File.expand_path('../../../..', __FILE__)
          gemfile_lock = File.join(kjui_tools_dir, 'Gemfile.lock')
          
          unless File.exist?(gemfile_lock)
            puts "Installing kjui_tools dependencies..."
            Dir.chdir(kjui_tools_dir) do
              success = system('bundle install')
              unless success
                puts "Warning: Failed to install some dependencies"
                puts "You may need to install them manually with: cd kjui_tools && bundle install"
              end
            end
          end
        end

        def parse_options(args)
          options = {}
          
          OptionParser.new do |opts|
            opts.banner = "Usage: kjui setup [options]"
            
            opts.on('-h', '--help', 'Show this help message') do
              puts opts
              exit
            end
          end.parse!(args)
          
          options
        end

        def setup_compose_project
          require_relative '../../compose/setup/compose_setup'
          
          # Use the Compose-specific setup
          setup = ::KjuiTools::Compose::Setup::ComposeSetup.new(Core::ProjectFinder.project_file_path)
          setup.run_full_setup
        end

        def setup_xml_project
          require_relative '../../xml/setup/xml_setup'
          
          # Use the XML-specific setup
          setup = ::KjuiTools::Xml::Setup::XmlSetup.new(Core::ProjectFinder.project_file_path)
          setup.run_full_setup
        end
      end
    end
  end
end