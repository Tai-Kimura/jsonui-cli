#!/usr/bin/env ruby

require 'json'
require 'fileutils'
require_relative '../core/config_manager'
require_relative '../core/project_finder'
require_relative '../core/attribute_validator'
require_relative '../core/binding_validator'
require_relative 'xml_generator'

module KjuiTools
  module Xml
    class XmlBuilder
      attr_accessor :validation_enabled, :validation_callback

      def initialize(config = nil)
        @config = config || Core::ConfigManager.load_config
        Core::ProjectFinder.setup_paths
        # Use current directory as project path (where kjui.config.json is located)
        @project_path = Dir.pwd
        @layouts_dir = File.join(@project_path, @config['source_directory'] || 'src/main', @config['layouts_directory'] || 'assets/Layouts')
        @output_dir = File.join(@project_path, @config['source_directory'] || 'src/main', 'res/layout')
        @generated_count = 0
        @failed_count = 0
        @skipped_count = 0
        @validation_enabled = false
        @validation_callback = nil
        @validator = nil
        @binding_validator = nil
      end

      def build(options = {})
        puts "🔨 Building XML View files..."
        puts "📁 Project: #{@project_path}"
        puts "📂 Layouts: #{@layouts_dir}"
        puts "📂 Output: #{@output_dir}"
        puts "-" * 60

        unless Dir.exist?(@layouts_dir)
          puts "❌ Layouts directory not found: #{@layouts_dir}"
          return false
        end

        # Clean output directory if requested
        if options[:clean]
          clean_output_directory
        end

        # Ensure output directory exists
        FileUtils.mkdir_p(@output_dir)

        # Initialize validators if validation is enabled
        @validator = Core::AttributeValidator.new(:xml) if @validation_enabled
        @binding_validator = Core::BindingValidator.new if @validation_enabled

        # Get all JSON files (excluding Resources folder)
        json_files = Dir.glob(File.join(@layouts_dir, '*.json'))
        # Also get JSON files from subdirectories, but exclude Resources
        json_files += Dir.glob(File.join(@layouts_dir, '**/*.json')).reject do |file|
          file.include?('/Resources/')
        end
        json_files.uniq!

        if json_files.empty?
          puts "⚠️  No JSON files found in #{@layouts_dir}"
          return true
        end

        puts "📄 Found #{json_files.length} JSON files"
        puts "-" * 60

        # Extract resources before processing layouts
        require_relative '../core/resources_manager'
        resources_manager = Core::ResourcesManager.new(@config, @project_path)
        resources_manager.extract_resources(json_files)
        puts "-" * 60

        # Process each file
        json_files.each do |json_file|
          process_layout(json_file, options)
        end

        # Print summary
        puts "-" * 60
        puts "✅ Build Complete!"
        puts "   Generated: #{@generated_count} files"
        puts "   Failed: #{@failed_count} files" if @failed_count > 0
        puts "   Skipped: #{@skipped_count} files" if @skipped_count > 0

        @failed_count == 0
      end

      private

      def clean_output_directory
        puts "🧹 Cleaning output directory..."

        if Dir.exist?(@output_dir)
          # Only remove generated XML files (those with our comment marker)
          Dir.glob(File.join(@output_dir, '*.xml')).each do |file|
            content = File.read(file)
            if content.include?('<!-- Generated from') && content.include?('.json')
              puts "   Removing: #{File.basename(file)}"
              File.delete(file)
            end
          end
        end
      end

      # Validate a JSON component and all its children recursively
      # @param json_data [Hash] The JSON component to validate
      # @param parent_orientation [String, nil] The orientation of the parent component
      def validate_json(json_data, parent_orientation = nil)
        return [] unless json_data.is_a?(Hash)

        warnings = @validator.validate(json_data, nil, parent_orientation)

        # Get this component's orientation for passing to children
        current_orientation = json_data['orientation']

        # Validate children recursively
        children = json_data['child'] || json_data['children'] || []
        children = [children] unless children.is_a?(Array)

        children.each do |child|
          warnings.concat(validate_json(child, current_orientation)) if child.is_a?(Hash)
        end

        # Validate sections (for Collection/Table)
        # Section headers, footers, and cells are top-level components, so parent_orientation is nil
        if json_data['sections'].is_a?(Array)
          json_data['sections'].each do |section|
            if section.is_a?(Hash)
              ['header', 'footer', 'cell'].each do |key|
                warnings.concat(validate_json(section[key], nil)) if section[key].is_a?(Hash)
              end
            end
          end
        end

        warnings
      end

      def process_layout(json_file, options = {})
        layout_name = File.basename(json_file, '.json')

        # Skip partial/included files (convention: starts with underscore)
        if layout_name.start_with?('_')
          puts "   ⏭️  Skipping partial: #{layout_name}"
          @skipped_count += 1
          return
        end

        # Skip cell templates (they're used in collections)
        if layout_name.end_with?('_cell') || layout_name.include?('cell')
          puts "   ⏭️  Skipping cell template: #{layout_name}"
          @skipped_count += 1
          return
        end

        # Skip included files (used by include mechanism)
        if layout_name.start_with?('included')
          puts "   ⏭️  Skipping include file: #{layout_name}"
          @skipped_count += 1
          return
        end

        print "   📝 Processing: #{layout_name}..."

        begin
          # Validate JSON if enabled
          if @validation_enabled && @validator
            json_content = File.read(json_file)
            json_data = JSON.parse(json_content)
            warnings = validate_json(json_data)

            if warnings.any?
              puts " ⚠️  #{warnings.length} attribute warning(s)"
              @validation_callback&.call(layout_name, warnings)
            end

            # Validate bindings for business logic
            if @binding_validator
              binding_warnings = @binding_validator.validate(json_data, layout_name)
              if binding_warnings.any?
                puts " ⚠️  #{binding_warnings.length} binding warning(s)"
                @validation_callback&.call(layout_name, binding_warnings)
              end
            end
          end

          # Ensure project_path is set in config
          config_with_path = @config.merge('project_path' => @project_path)

          # Generate XML using the existing generator
          generator = XmlGenerator::Generator.new(layout_name, config_with_path)
          if generator.generate
            @generated_count += 1
            puts " ✅" unless @validation_enabled && warnings&.any?
          else
            @failed_count += 1
            puts " ❌"
          end
        rescue JSON::ParserError => e
          @failed_count += 1
          puts " ❌"
          puts "      JSON Parse Error: #{e.message}"
        rescue => e
          @failed_count += 1
          puts " ❌"
          puts "      Error: #{e.message}"
          puts e.backtrace.first(5).map { |line| "        #{line}" }.join("\n")
        end
      end
    end
  end
end

# Allow running directly
if __FILE__ == $0
  require_relative '../core/config_manager'

  config = KjuiTools::Core::ConfigManager.load_config
  builder = KjuiTools::Xml::XmlBuilder.new(config)

  options = {}
  ARGV.each do |arg|
    case arg
    when '--clean', '-c'
      options[:clean] = true
    when '--debug', '-d'
      config['debug'] = true
    when '--validate', '-v'
      builder.validation_enabled = true
    end
  end

  builder.build(options)
end
