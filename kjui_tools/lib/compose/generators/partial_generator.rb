# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

module KjuiTools
  module Compose
    module Generators
      class PartialGenerator
        def initialize(name, options = {})
          @name = name
          @options = options
          @config = Core::ConfigManager.load_config
          @command = "kjui g partial #{name}"
        end

        def generate
          # Parse name for subdirectories
          parts = @name.split('/')
          partial_name = parts.last
          subdirectory = parts[0...-1].join('/') if parts.length > 1

          # Convert to proper case
          json_file_name = to_snake_case(partial_name)

          # Get directories from config
          source_dir = @config['source_directory'] || 'src/main'
          layouts_dir = @config['layouts_directory'] || 'assets/Layouts'

          # Create full path with subdirectory support
          if subdirectory
            json_path = File.join(source_dir, layouts_dir, subdirectory)
          else
            json_path = File.join(source_dir, layouts_dir)
          end

          # Create directory if it doesn't exist
          FileUtils.mkdir_p(json_path)

          # Create JSON file
          json_file = File.join(json_path, "#{json_file_name}.json")
          create_json_template(json_file, partial_name)

          puts "Generated partial:"
          puts "  JSON: #{json_file}"
          puts ""
          puts "To use this partial, include it in your layout JSON:"
          puts "  { \"include\": \"#{@name}\" }"
          puts ""
          puts "With data binding:"
          puts "  { \"include\": \"#{@name}\", \"data\": { \"title\": \"@{someValue}\" } }"
        end

        private

        def to_snake_case(str)
          str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
             .gsub(/([a-z\d])([A-Z])/, '\1_\2')
             .downcase
        end

        def create_json_template(file_path, partial_name)
          if File.exist?(file_path)
            puts "Warning: File already exists: #{file_path}"
            return
          end

          template = {
            generatedBy: @command,
            partial: true,
            type: "View",
            width: "matchParent",
            height: "wrapContent",
            padding: 16,
            background: "#FFFFFF",
            child: [
              {
                type: "Label",
                id: "#{to_snake_case(partial_name)}_label",
                text: "This is the #{partial_name} partial",
                fontSize: 14,
                fontColor: "#000000"
              }
            ]
          }

          File.write(file_path, JSON.pretty_generate(template))
          puts "Created JSON template: #{file_path}"
        end
      end
    end
  end
end
