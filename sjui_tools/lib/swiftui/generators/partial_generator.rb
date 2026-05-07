# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'

module SjuiTools
  module SwiftUI
    module Generators
      class PartialGenerator
        def initialize(name, options = {})
          @name = name
          @options = options
          @config = Core::ConfigManager.load_config
          @command = "sjui g partial #{name}"
        end

        def generate
          # Parse name for subdirectories
          parts = @name.split('/')
          partial_name = parts.last
          subdirectory = parts[0...-1].join('/') if parts.length > 1

          # Convert to proper case
          json_file_name = to_snake_case(partial_name)

          # Get directories from config
          source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
          layouts_dir = @config['layouts_directory'] || 'Layouts'

          # Create full path with subdirectory support
          if subdirectory
            json_path = File.join(source_path, layouts_dir, subdirectory)
          else
            json_path = File.join(source_path, layouts_dir)
          end

          # Create directory if it doesn't exist
          FileUtils.mkdir_p(json_path)

          # Create JSON file
          json_file = File.join(json_path, "#{json_file_name}.json")
          create_json_template(json_file, partial_name)

          Core::Logger.info "Generated partial:"
          Core::Logger.info "  JSON: #{json_file}"
          Core::Logger.info ""
          Core::Logger.info "To use this partial, include it in your layout JSON:"
          Core::Logger.info "  { \"include\": \"#{@name}\" }"
        end

        private

        def to_snake_case(str)
          str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
             .gsub(/([a-z\d])([A-Z])/, '\1_\2')
             .downcase
        end

        def create_json_template(file_path, partial_name)
          if File.exist?(file_path)
            Core::Logger.warn "File already exists: #{file_path}"
            return
          end

          template = {
            generatedBy: @command,
            partial: true,
            type: "View",
            width: "matchParent",
            height: "wrapContent",
            paddings: 16,
            background: "#FFFFFF",
            child: [
              {
                type: "Label",
                id: "#{to_snake_case(partial_name)}_label",
                width: "wrapContent",
                height: "wrapContent",
                text: "This is the #{partial_name} partial",
                fontSize: 14,
                fontColor: "#000000"
              }
            ]
          }

          File.write(file_path, JSON.pretty_generate(template))
          Core::Logger.debug "Created JSON template: #{file_path}"
        end
      end
    end
  end
end
