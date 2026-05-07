# frozen_string_literal: true

require 'json'
require_relative '../../core/logger'

module KjuiTools
  module Xml
    module Helpers
      class ResourceResolver
        class << self
          # Load resources lazily
          def strings_data
            @strings_data ||= load_strings_data
          end
          
          def colors_data
            @colors_data ||= load_colors_data
          end
          
          def defined_colors_data
            @defined_colors_data ||= load_defined_colors_data
          end
          
          # Clear cache (useful when resources change)
          def clear_cache
            @strings_data = nil
            @colors_data = nil
            @defined_colors_data = nil
          end
          
          # Process text value - returns @string/key or original text
          def process_text(text)
            return text if text.nil? || text.empty?
            
            # Skip data binding expressions
            return text if text.start_with?('@{') || text.start_with?('${')
            
            # Find string key
            string_key = find_string_key(text)
            if string_key
              "@string/#{string_key}"
            else
              # Return original text wrapped in quotes for XML
              "\"#{text}\""
            end
          end
          
          # Process color value - returns @color/key or hex color
          def process_color(color)
            return color if color.nil? || color.empty?
            
            # Skip data binding expressions
            return color if color.start_with?('@{') || color.start_with?('${')
            
            # Skip if already a resource reference
            return color if color.start_with?('@')
            
            # Find color key
            color_key = find_color_key(color)
            if color_key
              "@color/#{color_key}"
            else
              # Return hex color with # prefix
              if color.match?(/^#?[A-Fa-f0-9]{6,8}$/)
                color.start_with?('#') ? color : "##{color}"
              else
                color
              end
            end
          end
          
          private
          
          def load_strings_data
            strings_file = find_strings_json
            return {} unless strings_file && File.exist?(strings_file)
            
            begin
              data = JSON.parse(File.read(strings_file))
              # Flatten the nested structure (file -> key -> value)
              flattened = {}
              data.each do |file_prefix, file_strings|
                next unless file_strings.is_a?(Hash)
                file_strings.each do |key, value|
                  full_key = "#{file_prefix}_#{key}"
                  flattened[full_key] = value
                end
              end
              flattened
            rescue JSON::ParserError => e
              Core::Logger.warn "Failed to parse strings.json: #{e.message}"
              {}
            end
          end
          
          def load_colors_data
            colors_file = find_colors_json
            return {} unless colors_file && File.exist?(colors_file)
            
            begin
              JSON.parse(File.read(colors_file))
            rescue JSON::ParserError => e
              Core::Logger.warn "Failed to parse colors.json: #{e.message}"
              {}
            end
          end
          
          def load_defined_colors_data
            defined_colors_file = find_defined_colors_json
            return {} unless defined_colors_file && File.exist?(defined_colors_file)
            
            begin
              JSON.parse(File.read(defined_colors_file))
            rescue JSON::ParserError => e
              Core::Logger.warn "Failed to parse defined_colors.json: #{e.message}"
              {}
            end
          end
          
          def find_strings_json
            # Try common locations
            paths = [
              'src/main/assets/Layouts/Resources/strings.json',
              'app/src/main/assets/Layouts/Resources/strings.json',
              'sample-app/src/main/assets/Layouts/Resources/strings.json'
            ]
            
            paths.each do |path|
              full_path = File.expand_path(path)
              return full_path if File.exist?(full_path)
            end
            
            nil
          end
          
          def find_colors_json
            # Try common locations
            paths = [
              'src/main/assets/Layouts/Resources/colors.json',
              'app/src/main/assets/Layouts/Resources/colors.json',
              'sample-app/src/main/assets/Layouts/Resources/colors.json'
            ]
            
            paths.each do |path|
              full_path = File.expand_path(path)
              return full_path if File.exist?(full_path)
            end
            
            nil
          end
          
          def find_defined_colors_json
            # Try common locations
            paths = [
              'src/main/assets/Layouts/Resources/defined_colors.json',
              'app/src/main/assets/Layouts/Resources/defined_colors.json',
              'sample-app/src/main/assets/Layouts/Resources/defined_colors.json'
            ]
            
            paths.each do |path|
              full_path = File.expand_path(path)
              return full_path if File.exist?(full_path)
            end
            
            nil
          end
          
          def find_string_key(text)
            strings_data.find { |key, value| value == text }&.first
          end
          
          def find_color_key(color)
            # If the color itself is a key in colors.json, return it
            if colors_data.key?(color)
              return color
            end
            
            # If the color itself is in defined_colors.json, return it
            if defined_colors_data.key?(color)
              return color
            end
            
            # Otherwise, normalize and search for hex values
            normalized_color = normalize_color(color)
            
            # Check colors.json for hex values
            if colors_data.any? && normalized_color
              found = colors_data.find { |key, value| normalize_color(value) == normalized_color }
              return found.first if found
            end
            
            nil
          end
          
          def normalize_color(color)
            return nil if color.nil?
            
            # If it's a hex color, normalize it
            if color.match?(/^#?[A-Fa-f0-9]{6,8}$/)
              hex = color.gsub('#', '').upcase
              # Convert 3-digit to 6-digit
              if hex.length == 3
                hex = hex.chars.map { |c| c * 2 }.join
              end
              "##{hex}"
            else
              color
            end
          end
        end
      end
    end
  end
end