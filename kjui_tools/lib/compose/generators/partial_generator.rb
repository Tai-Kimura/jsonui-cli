# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'
require_relative '../../core/converter_generator_core'

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

          # Through the one overwrite decision the generate commands share: an
          # existing partial is kept unless --force (or "y" at the prompt).
          # Until 1.8.121 --force / --skip-existing were not read here.
          json_file = File.join(json_path, "#{json_file_name}.json")
          core = JsonUIShared::ConverterGeneratorCore
          record = core.scaffold_record
          core.write_scaffold(json_file, @options.merge(scaffold_files: record), Core::Logger,
                              noun: 'partial layout', label: 'partial layout', exists_label: 'Partial layout') do
            json_content(partial_name)
          end
          core.report_scaffold_record("partial #{@name}", record, Core::Logger)
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

        def json_content(partial_name)
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

          JSON.pretty_generate(template)
        end
      end
    end
  end
end
