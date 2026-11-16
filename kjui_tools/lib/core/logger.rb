# frozen_string_literal: true

module KjuiTools
  module Core
    class Logger
      class << self
        def info(message)
          puts "  #{message}"
        end
        
        def success(message)
          puts "✅ #{message}"
        end
        
        def error(message)
          puts "❌ #{message}"
        end
        
        def warn(message)
          puts "⚠️  #{message}"
        end
        
        def debug(message)
          puts "🔍 #{message}" if ENV['DEBUG']
        end
        
        def newline
          puts
        end
      end
    end
  end
end