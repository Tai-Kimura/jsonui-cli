# frozen_string_literal: true

require_relative '../core/config_manager'
require_relative '../core/logger'

module RjuiTools
  module CLI
    class Main
      COMMANDS = {
        'init' => 'Initialize ReactJsonUI in current project',
        'build' => 'Build React components from JSON layouts',
        'watch' => 'Watch JSON files and auto-rebuild on changes',
        'hotload' => 'HotLoader (listen, stop, status)',
        'g' => 'Generate (view, component)',
        'generate' => 'Generate (view, component)',
        'help' => 'Show this help message'
      }.freeze

      def self.start(args)
        command = args[0]
        sub_args = args[1..]

        case command
        when 'init'
          require_relative 'commands/init_command'
          Commands::InitCommand.new(sub_args).execute
        when 'build'
          require_relative 'commands/build_command'
          Commands::BuildCommand.new(sub_args).execute
        when 'watch'
          require_relative 'commands/watch_command'
          Commands::WatchCommand.new(sub_args).execute
        when 'hotload'
          require_relative 'commands/hotload_command'
          Commands::HotloadCommand.new(sub_args).execute
        when 'g', 'generate'
          require_relative 'commands/generate_command'
          Commands::GenerateCommand.new(sub_args, sub_args.dup).execute
        when 'help', nil, '-h', '--help'
          show_help
        else
          Core::Logger.error("Unknown command: #{command}")
          show_help
          exit 1
        end
      end

      def self.show_help
        puts <<~HELP
          ReactJsonUI CLI - Generate React components from JSON layouts

          Usage: rjui <command> [options]

          Commands:
        HELP

        COMMANDS.each do |cmd, desc|
          puts "  #{cmd.ljust(12)} #{desc}"
        end

        puts <<~EXAMPLES

          Examples:
            rjui init                    # Initialize in current directory
            rjui g view HomeView         # Generate HomeView component
            rjui build                   # Build all components from JSON
            rjui watch                   # Watch and auto-rebuild on changes
            rjui hotload listen          # Start HotLoader watch mode
            rjui hotload stop            # Stop HotLoader
        EXAMPLES
      end
    end
  end
end
