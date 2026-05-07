# frozen_string_literal: true

require_relative '../../core/config_manager'
require_relative '../../core/logger'
require_relative '../../core/file_watcher'
require_relative 'build_command'

module RjuiTools
  module CLI
    module Commands
      class HotloadCommand
        PID_FILE = '.rjui_hotload.pid'

        def initialize(args)
          @args = args
          @config = Core::ConfigManager.load_config
        end

        def execute
          subcommand = @args.first

          case subcommand
          when 'listen'
            @args.shift
            run_listen
          when 'stop'
            run_stop
          when 'status'
            run_status
          when '--help', '-h', 'help'
            show_help
          else
            # Default to listen for backward compatibility
            run_listen
          end
        rescue Interrupt
          Core::Logger.info("\nShutting down HotLoader...")
          exit 0
        rescue => e
          Core::Logger.error("Error: #{e.message}")
          puts e.backtrace if ENV['DEBUG']
          exit 1
        end

        private

        def run_listen
          Core::Logger.info('Starting HotLoader development environment...')

          layouts_dir = @config['layouts_directory']
          styles_dir = @config['styles_directory']
          strings_dir = @config['strings_directory']

          unless Dir.exist?(layouts_dir)
            Core::Logger.error("Layouts directory not found: #{layouts_dir}")
            Core::Logger.info('Run "rjui init" first')
            exit 1
          end

          # Kill existing processes first
          stop_existing_processes

          # Save current process PID
          File.write(PID_FILE, Process.pid.to_s)

          # Initial build
          run_build

          Core::Logger.success("HotLoader is ready!")
          Core::Logger.info("Watching directories: #{[layouts_dir, styles_dir, strings_dir].compact.join(', ')}")
          Core::Logger.info("Use 'rjui hotload stop' to stop")

          # Setup file watcher
          watch_dirs = [layouts_dir, styles_dir, strings_dir].select { |d| d && Dir.exist?(d) }

          @watcher = Core::FileWatcher.new(watch_dirs, extensions: ['json']) do |file, type|
            Core::Logger.info("\nFile #{type}: #{file}")
            Core::Logger.info("Rebuilding...")
            run_build
          end

          @watcher.start

          # Trap interrupt signal to clean up
          trap('INT') do
            cleanup
            exit 0
          end

          trap('TERM') do
            cleanup
            exit 0
          end

          # Keep the process running
          begin
            sleep
          rescue Interrupt
            cleanup
          end
        end

        def run_stop
          Core::Logger.info('Stopping HotLoader services...')

          # Read PID from file
          if File.exist?(PID_FILE)
            pid = File.read(PID_FILE).strip.to_i
            if pid > 0
              begin
                Process.kill('TERM', pid)
                Core::Logger.info("Stopped process #{pid}")
              rescue Errno::ESRCH
                Core::Logger.info("Process #{pid} already stopped")
              rescue Errno::EPERM
                Core::Logger.error("Permission denied to stop process #{pid}")
              end
            end
            File.delete(PID_FILE)
          end

          # Also try to kill by process name
          system("pkill -f 'rjui.*hotload.*listen' 2>/dev/null")
          system("pkill -f 'rjui.*watch' 2>/dev/null")

          Core::Logger.success('HotLoader stopped')
        end

        def run_status
          Core::Logger.info('HotLoader Status')
          puts '=' * 40

          if File.exist?(PID_FILE)
            pid = File.read(PID_FILE).strip.to_i
            if pid > 0 && process_running?(pid)
              Core::Logger.success("HotLoader is running (PID: #{pid})")
            else
              Core::Logger.info("HotLoader is not running (stale PID file)")
              File.delete(PID_FILE)
            end
          else
            Core::Logger.info("HotLoader is not running")
          end
        end

        def stop_existing_processes
          if File.exist?(PID_FILE)
            pid = File.read(PID_FILE).strip.to_i
            if pid > 0 && process_running?(pid)
              Core::Logger.info("Stopping existing HotLoader (PID: #{pid})...")
              begin
                Process.kill('TERM', pid)
                sleep 1
              rescue Errno::ESRCH, Errno::EPERM
                # Process already dead or no permission
              end
            end
            File.delete(PID_FILE)
          end
        end

        def process_running?(pid)
          Process.kill(0, pid)
          true
        rescue Errno::ESRCH, Errno::EPERM
          false
        end

        def cleanup
          Core::Logger.info("\nStopping HotLoader...")
          @watcher&.stop
          File.delete(PID_FILE) if File.exist?(PID_FILE)
        end

        def run_build
          BuildCommand.new([]).execute
        end

        def show_help
          puts <<~HELP
            Usage: rjui hotload [COMMAND] [options]

            Commands:
              listen             Start HotLoader development environment (default)
              stop               Stop HotLoader services
              status             Show status of HotLoader services

            Options:
              --help, -h         Show this help message

            Examples:
              rjui hotload                   # Start HotLoader (same as 'listen')
              rjui hotload listen            # Start HotLoader development environment
              rjui hotload stop              # Stop all services
              rjui hotload status            # Check service status
          HELP
        end
      end
    end
  end
end
