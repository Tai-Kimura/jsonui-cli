# frozen_string_literal: true

require 'json'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

module SjuiTools
  module SwiftUI
    module Helpers
      module StringManagerHelper
        def get_text_with_string_manager(text_content)
          # Remove quotes if present
          text_without_quotes = text_content.gsub(/^\"|\"|^'|'$/, '')

          # Check if it's a binding (starts with @{)
          return text_content if text_without_quotes.match?(/^@\{.*\}$/)

          # First, try to find by value in strings.json (for non-snake_case text like "AppFinder")
          string_manager_call = lookup_string_manager_by_value(text_without_quotes)
          return string_manager_call if string_manager_call

          # Then, check if it's snake_case key format
          if text_without_quotes.match?(/^[a-z]+(_[a-z0-9]+)*$/)
            # Try to find by key in strings.json
            string_manager_call = lookup_string_manager_key(text_without_quotes)
            return string_manager_call if string_manager_call

            # Fallback to .localized() extension for snake_case strings
            return "\"#{text_without_quotes}\".localized()"
          end

          # Return original text content for non-matched strings
          text_content
        end

        private

        # Lookup by value (e.g., "AppFinder" -> StringManager.Login.appfinder())
        def lookup_string_manager_by_value(text)
          strings_data = load_strings_json
          return nil if strings_data.nil? || strings_data.empty?

          strings_data.each do |file_name, file_strings|
            next unless file_strings.is_a?(Hash)

            # Find key by matching value
            file_strings.each do |key, value|
              if value == text
                struct_name = snake_to_pascal(file_name)
                method_name = snake_to_camel(key)
                return "StringManager.#{struct_name}.#{method_name}()"
              end
            end
          end

          nil
        end

        def lookup_string_manager_key(text)
          strings_data = load_strings_json
          return nil if strings_data.nil?

          # Check each file's strings
          strings_data.each do |file_name, file_strings|
            next unless file_strings.is_a?(Hash)

            # Check if text matches file_key pattern (e.g., "login_forgot_password")
            if text.start_with?("#{file_name}_")
              key = text.sub(/^#{file_name}_/, '')
              # Key exists in strings.json (has proper value)
              if file_strings.key?(key)
                struct_name = snake_to_pascal(file_name)
                method_name = snake_to_camel(key)
                return "StringManager.#{struct_name}.#{method_name}()"
              end
            end

            # Check if text matches just the key (without file prefix)
            if file_strings.key?(text)
              struct_name = snake_to_pascal(file_name)
              method_name = snake_to_camel(text)
              return "StringManager.#{struct_name}.#{method_name}()"
            end
          end

          nil
        end

        def load_strings_json
          @strings_json_cache ||= begin
            source_path = Core::ProjectFinder.get_full_source_path
            return {} if source_path.nil?

            config = Core::ConfigManager.load_config
            layouts_dir = config['layouts_directory'] || 'Layouts'
            strings_file = File.join(source_path, layouts_dir, 'Resources', 'strings.json')

            if File.exist?(strings_file)
              JSON.parse(File.read(strings_file))
            else
              {}
            end
          rescue JSON::ParserError, TypeError
            {}
          end
        end

        def snake_to_pascal(snake_str)
          snake_str.split('_').map(&:capitalize).join
        end

        def snake_to_camel(snake_str)
          parts = snake_str.split('_')

          # Handle pure numbers
          if parts.length == 1 && parts[0].match?(/^\d+$/)
            return "value#{parts[0]}"
          end

          # Handle trailing numbers
          if parts.length > 1 && parts.last.match?(/^\d+$/)
            parts[-2] = parts[-2] + parts[-1]
            parts.pop
          end

          parts[0] + parts[1..-1].map(&:capitalize).join
        end
      end
    end
  end
end