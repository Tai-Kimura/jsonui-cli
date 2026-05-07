# frozen_string_literal: true

require_relative 'version'
require_relative 'commands/init'
require_relative 'commands/setup'
require_relative 'commands/build'
require_relative 'commands/generate'

module KjuiTools
  module CLI
    class Main
      def self.run(args)
        command = args.shift
        
        case command
        when 'init'
          Commands::Init.new.run(args)
        when 'setup'
          Commands::Setup.new.run(args)
        when 'generate', 'g'
          Commands::Generate.new.run(args)
        when 'build', 'b'
          Commands::Build.new.run(args)
        when 'watch', 'w'
          puts "Watch command not yet implemented"
        when 'version', 'v', '--version', '-v'
          puts "KotlinJsonUI Tools version #{VERSION}"
        when 'help', '--help', '-h', nil
          show_help
        else
          puts "Unknown command: #{command}"
          show_help
          exit 1
        end
      rescue StandardError => e
        puts "Error: #{e.message}"
        puts e.backtrace if ENV['DEBUG']
        exit 1
      end
      
      def self.show_help
        puts <<~HELP
          KotlinJsonUI Tools - JSON-based UI framework for Android
          
          Usage: kjui <command> [options]
          
          Commands:
            init                Initialize a new KotlinJsonUI project
            generate, g         Generate views and components
            setup              Set up project dependencies
            build, b           Build the project
            watch, w           Watch for file changes
            version, v         Show version information
            help               Show this help message
          
          Examples:
            kjui init --mode compose     Initialize a Jetpack Compose project
            kjui init --mode xml         Initialize an XML-based project
            kjui g view HomeView         Generate a new view
          
          For more information on a specific command:
            kjui <command> --help
        HELP
      end
    end
  end
end