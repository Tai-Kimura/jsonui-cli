# frozen_string_literal: true

require_relative '../../core/config_manager'
require_relative '../../core/logger'
require_relative '../../core/file_watcher'
require_relative 'build_command'

module RjuiTools
  module CLI
    module Commands
      class WatchCommand
        def initialize(args)
          @args = args
          @config = Core::ConfigManager.load_config
        end

        def execute
          Core::Logger.info('Starting watch mode...')

          layouts_dir = @config['layouts_directory']
          styles_dir = @config['styles_directory']
          strings_dir = @config['strings_directory']

          unless Dir.exist?(layouts_dir)
            Core::Logger.error("Layouts directory not found: #{layouts_dir}")
            Core::Logger.info('Run "rjui init" first')
            exit 1
          end

          # Initial build
          run_build

          Core::Logger.info("Press Ctrl+C to stop")

          # Setup file watcher
          watch_dirs = [layouts_dir, styles_dir, strings_dir].select { |d| d && Dir.exist?(d) }

          watcher = Core::FileWatcher.new(watch_dirs, extensions: ['json']) do |file, type|
            Core::Logger.info("\nFile #{type}: #{file}")
            Core::Logger.info("Rebuilding...")
            run_build
          end

          watcher.start

          # Keep the process running
          begin
            sleep
          rescue Interrupt
            Core::Logger.info("\nStopping watch mode...")
            watcher.stop
          end
        end

        private

        def run_build
          # Use BuildCommand to ensure consistent build behavior
          BuildCommand.new([]).execute
        end
      end
    end
  end
end
