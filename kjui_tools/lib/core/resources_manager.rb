# frozen_string_literal: true

require 'json'
require 'fileutils'
require_relative 'config_manager'
require_relative 'project_finder'
require_relative 'logger'
require_relative 'resources/string_manager'
require_relative 'resources/color_manager'

module KjuiTools
  module Core
    class ResourcesManager
      def initialize(config, source_path)
        @config = config
        @source_path = source_path
        @layouts_dir = File.join(@source_path, @config['source_directory'] || 'src/main', 'assets/Layouts')
        @resources_dir = File.join(@layouts_dir, 'Resources')
        @string_manager = Resources::StringManager.new(@config, @source_path, @resources_dir)
        @color_manager = Resources::ColorManager.new(@config, @source_path, @resources_dir)
      end

      # Main method called from build command
      def extract_resources(json_files)
        # Extract resources from JSON files
        extract_from_json_files(json_files)

        # Apply extracted strings to strings.xml files
        apply_extracted_strings

        # Apply extracted colors
        apply_extracted_colors
      end

      # Extract resources from JSON files
      def extract_from_json_files(json_files)
        processed_files = []
        processed_count = 0
        skipped_count = 0

        json_files.each do |json_file|
          # Skip files in Resources directory only
          if json_file.include?('/Resources/')
            skipped_count += 1
            next
          end

          processed_files << json_file
          processed_count += 1
        end

        if processed_count == 0
          Logger.info "No files to process for resource extraction"
          return
        end

        Logger.info "Extracting resources from #{processed_count} files (#{skipped_count} skipped)..."

        # Ensure Resources directory exists
        FileUtils.mkdir_p(@resources_dir)

        # Process strings through StringManager
        @string_manager.process_strings(processed_files, processed_count, skipped_count)

        # Process colors through ColorManager
        @color_manager.process_colors(processed_files, processed_count, skipped_count, @config)
      end

      private

      def apply_extracted_strings
        Logger.info "Applying extracted strings to strings.xml files..."
        @string_manager.apply_to_strings_files
      end

      def apply_extracted_colors
        Logger.info "Applying extracted colors..."
        @color_manager.apply_to_color_assets
      end
    end
  end
end
