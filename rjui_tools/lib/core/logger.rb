# frozen_string_literal: true

# Disable buffering for real-time output
$stdout.sync = true

module RjuiTools
  module Core
    class Logger
      class << self
        def info(message)
          puts "\e[34m[INFO]\e[0m #{message}"
        end

        def success(message)
          puts "\e[32m[SUCCESS]\e[0m #{message}"
        end

        def warn(message)
          puts "\e[33m[WARN]\e[0m #{message}"
        end

        def error(message)
          puts "\e[31m[ERROR]\e[0m #{message}"
        end

        def debug(message)
          puts "\e[90m[DEBUG]\e[0m #{message}" if ENV['DEBUG']
        end
      end
    end
  end
end
