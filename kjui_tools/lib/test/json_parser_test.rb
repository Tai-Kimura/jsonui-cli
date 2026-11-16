#!/usr/bin/env ruby

require 'json'
require 'fileutils'
require 'set'
require_relative '../core/config_manager'
require_relative '../xml/helpers/component_mapper'
require_relative '../xml/helpers/attribute_mapper'

module KjuiTools
  module Test
    class JsonParserTest
      def initialize
        @config = Core::ConfigManager.load_config
        @component_mapper = XmlGenerator::ComponentMapper.new
        @attribute_mapper = XmlGenerator::AttributeMapper.new
        @unhandled_keys = {}
        @handled_keys = Set.new([
          'type', 'id', 'width', 'height', 'child', 'children', 
          'style', 'data', 'orientation', 'includes', 'collection'
        ])
        @parse_errors = []
        @statistics = {
          total_files: 0,
          successful_parses: 0,
          failed_parses: 0,
          total_components: 0,
          unique_component_types: Set.new,
          unique_attributes: Set.new
        }
      end

      def run
        puts "🔍 Starting JSON Parser Test..."
        puts "=" * 60
        
        layouts_dir = find_layouts_directory
        unless layouts_dir && Dir.exist?(layouts_dir)
          puts "❌ Layouts directory not found"
          return
        end
        
        puts "📁 Layouts directory: #{layouts_dir}"
        
        # Get all JSON files
        json_files = Dir.glob(File.join(layouts_dir, '*.json'))
        @statistics[:total_files] = json_files.length
        
        puts "📄 Found #{json_files.length} JSON files"
        puts "-" * 60
        
        # Process each file
        json_files.each do |file|
          process_file(file)
        end
        
        # Generate report
        generate_report
        
        puts "=" * 60
        puts "✅ Test completed. Report saved to: verification_report.md"
      end
      
      private
      
      def find_layouts_directory
        # Try different possible locations
        possible_paths = [
          File.join(Dir.pwd, 'src', 'main', 'assets', 'Layouts'),
          File.join(Dir.pwd, 'sample-app', 'src', 'main', 'assets', 'Layouts'),
          File.join(@config['source_directory'] || 'src/main', 'assets', 'Layouts')
        ]
        
        possible_paths.find { |path| Dir.exist?(path) }
      end
      
      def process_file(file_path)
        filename = File.basename(file_path)
        puts "  Processing: #{filename}"
        
        begin
          content = File.read(file_path)
          json_data = JSON.parse(content)
          
          # Analyze the JSON structure
          analyze_component(json_data, filename, [])
          
          @statistics[:successful_parses] += 1
          puts "    ✅ Successfully parsed"
        rescue JSON::ParserError => e
          @parse_errors << {
            file: filename,
            error: e.message
          }
          @statistics[:failed_parses] += 1
          puts "    ❌ Parse error: #{e.message}"
        rescue => e
          @parse_errors << {
            file: filename,
            error: "#{e.class}: #{e.message}"
          }
          @statistics[:failed_parses] += 1
          puts "    ❌ Error: #{e.message}"
        end
      end
      
      def analyze_component(component, filename, path)
        return unless component.is_a?(Hash)
        
        @statistics[:total_components] += 1
        
        # Track component type
        if component['type']
          @statistics[:unique_component_types].add(component['type'])
          
          # Check if component type is handled
          begin
            mapped = @component_mapper.map_component(component['type'])
            if mapped.nil? || mapped.empty?
              track_unhandled("Component type '#{component['type']}' not mapped", filename, path)
            end
          rescue => e
            track_unhandled("Component type '#{component['type']}' mapping error: #{e.message}", filename, path)
          end
        end
        
        # Check all attributes
        component.each do |key, value|
          @statistics[:unique_attributes].add(key)
          
          # Skip known handled keys
          next if @handled_keys.include?(key)
          
          # Check if attribute is handled
          begin
            if component['type']
              mapped_attr = @attribute_mapper.map_attribute(key, value, component['type'])
              if mapped_attr.nil?
                track_unhandled("Attribute '#{key}' with value '#{value.inspect}' not handled for type '#{component['type']}'", filename, path)
              end
            end
          rescue => e
            track_unhandled("Attribute '#{key}' mapping error: #{e.message}", filename, path)
          end
        end
        
        # Process children recursively
        children = component['children'] || component['child']
        if children
          if children.is_a?(Array)
            children.each_with_index do |child, index|
              analyze_component(child, filename, path + ["[#{index}]"])
            end
          elsif children.is_a?(Hash)
            analyze_component(children, filename, path + ["[child]"])
          end
        end
        
        # Process collection items
        if component['collection']
          collection = component['collection']
          if collection.is_a?(Hash)
            # Check collection-specific attributes
            collection.each do |key, value|
              unless ['data', 'cellClass', 'cellClasses', 'orientation', 'template'].include?(key)
                track_unhandled("Collection attribute '#{key}' with value '#{value.inspect}'", filename, path + ["[collection]"])
              end
            end
            
            # Process cell templates if present
            if collection['template']
              analyze_component(collection['template'], filename, path + ["[collection.template]"])
            end
          end
        end
        
        # Process includes
        if component['includes']
          includes = component['includes']
          if includes.is_a?(Array)
            includes.each_with_index do |include_item, index|
              if include_item.is_a?(Hash)
                analyze_component(include_item, filename, path + ["[includes.#{index}]"])
              end
            end
          end
        end
      end
      
      def track_unhandled(message, filename, path)
        @unhandled_keys[filename] ||= []
        location = path.empty? ? "root" : "root#{path.join('')}"
        @unhandled_keys[filename] << {
          message: message,
          location: location
        }
      end
      
      def generate_report
        timestamp = Time.now.strftime("%Y-%m-%d %H:%M:%S")
        
        report = []
        report << "# KotlinJsonUI JSON Parser Verification Report"
        report << ""
        report << "**Generated:** #{timestamp}"
        report << ""
        report << "## Summary"
        report << ""
        report << "| Metric | Value |"
        report << "|--------|-------|"
        report << "| Total JSON files | #{@statistics[:total_files]} |"
        report << "| Successfully parsed | #{@statistics[:successful_parses]} |"
        report << "| Failed to parse | #{@statistics[:failed_parses]} |"
        report << "| Total components | #{@statistics[:total_components]} |"
        report << "| Unique component types | #{@statistics[:unique_component_types].size} |"
        report << "| Unique attributes | #{@statistics[:unique_attributes].size} |"
        report << ""
        
        # Component types
        report << "## Component Types Found"
        report << ""
        @statistics[:unique_component_types].to_a.sort.each do |type|
          status = begin
            mapped = @component_mapper.map_component(type)
            mapped && !mapped.empty? ? "✅" : "❌"
          rescue
            "⚠️"
          end
          report << "- #{status} `#{type}`"
        end
        report << ""
        
        # Unique attributes
        report << "## All Attributes Found"
        report << ""
        report << "```"
        @statistics[:unique_attributes].to_a.sort.each do |attr|
          report << attr
        end
        report << "```"
        report << ""
        
        # Parse errors
        if @parse_errors.any?
          report << "## Parse Errors"
          report << ""
          @parse_errors.each do |error|
            report << "### #{error[:file]}"
            report << "```"
            report << error[:error]
            report << "```"
            report << ""
          end
        end
        
        # Unhandled keys/attributes
        if @unhandled_keys.any?
          report << "## Unhandled Keys and Attributes"
          report << ""
          @unhandled_keys.each do |filename, issues|
            report << "### #{filename}"
            report << ""
            issues.each do |issue|
              report << "- **Location:** `#{issue[:location]}`"
              report << "  - #{issue[:message]}"
            end
            report << ""
          end
        else
          report << "## Unhandled Keys and Attributes"
          report << ""
          report << "✅ No unhandled keys or attributes found!"
          report << ""
        end
        
        # Write report to file
        report_path = File.join(Dir.pwd, 'verification_report.md')
        File.write(report_path, report.join("\n"))
        
        # Also write a JSON version for programmatic access
        json_report = {
          timestamp: timestamp,
          statistics: @statistics.transform_values do |v|
            v.is_a?(Set) ? v.to_a : v
          end,
          parse_errors: @parse_errors,
          unhandled_keys: @unhandled_keys
        }
        
        json_report_path = File.join(Dir.pwd, 'verification_report.json')
        File.write(json_report_path, JSON.pretty_generate(json_report))
      end
    end
  end
end

# Run the test if called directly
if __FILE__ == $0
  KjuiTools::Test::JsonParserTest.new.run
end