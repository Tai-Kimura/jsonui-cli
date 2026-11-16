#!/usr/bin/env ruby

require 'json'
require 'fileutils'
require 'set'
require 'nokogiri'
require_relative '../core/json_loader'
require_relative '../core/style_loader'
require_relative '../core/generated_marker'
require_relative 'helpers/component_mapper'
require_relative 'helpers/attribute_mapper'
require_relative 'helpers/binding_parser'
require_relative 'helpers/layout_attribute_processor'
require_relative 'helpers/data_binding_helper'
require_relative 'drawable/drawable_generator'
require_relative 'resources/string_resource_manager'

module XmlGenerator
  class Generator
    def initialize(layout_name, config, options = {})
      @layout_name = layout_name
      @config = config
      @options = options
      @json_loader = JsonLoader.new(config)
      @style_loader = StyleLoader.new(config)
      @component_mapper = ComponentMapper.new
      
      # Initialize resource managers
      project_root = @config['project_path']
      @drawable_generator = DrawableGenerator::Generator.new(project_root)
      @string_resource_manager = Resources::StringResourceManager.new(project_root)
      
      @attribute_mapper = AttributeMapper.new(@drawable_generator, @string_resource_manager)
      @binding_parser = BindingParser.new
      @layout_processor = LayoutAttributeProcessor.new(@attribute_mapper)
      
      # Get package name from config or auto-detect
      @package_name = @config['package_name'] || detect_package_name
      
      # Allow custom output filename
      @output_filename = options[:output_filename]
    end
    
    def generate
      puts "Generating XML for #{@layout_name}..."
      
      # Load JSON
      json_content = @json_loader.load_layout(@layout_name)
      if json_content.nil?
        puts "Error: Could not load layout #{@layout_name}"
        return false
      end

      # Parse JSON
      layout_data = JSON.parse(json_content)
      
      # Apply styles
      layout_data = @style_loader.apply_styles(layout_data)
      
      # Generate XML
      xml_content = generate_xml(layout_data)
      
      # Save XML file
      save_xml(xml_content)
      
      # Save any new strings to strings.xml
      @string_resource_manager.save_new_strings
      
      true
    rescue => e
      puts "Error generating XML: #{e.message}"
      puts "  Backtrace:"
      e.backtrace[0..4].each { |line| puts "    #{line}" }
      false
    end

    private
    
    def detect_package_name
      # Try to detect from AndroidManifest.xml
      manifest_paths = [
        File.join(@config['project_path'], 'src', 'main', 'AndroidManifest.xml'),
        File.join(@config['project_path'], 'app', 'src', 'main', 'AndroidManifest.xml')
      ]
      
      manifest_paths.each do |path|
        if File.exist?(path)
          content = File.read(path)
          if content =~ /package="([^"]+)"/
            return $1
          end
        end
      end
      
      # Try to detect from build.gradle
      gradle_paths = [
        File.join(@config['project_path'], 'build.gradle'),
        File.join(@config['project_path'], 'app', 'build.gradle'),
        File.join(@config['project_path'], 'build.gradle.kts'),
        File.join(@config['project_path'], 'app', 'build.gradle.kts')
      ]
      
      gradle_paths.each do |path|
        if File.exist?(path)
          content = File.read(path)
          # Look for namespace
          if content =~ /namespace\s*[=:]\s*["']([^"']+)["']/
            return $1
          end
          # Look for applicationId
          if content =~ /applicationId\s*[=:]\s*["']([^"']+)["']/
            return $1
          end
        end
      end
      
      # Default
      'com.example.app'
    end

    def generate_xml(json_data)
      # Check if layout uses data binding
      has_binding = check_for_bindings(json_data)
      
      if has_binding
        generate_data_binding_xml(json_data)
      else
        generate_regular_xml(json_data)
      end
    end

    def check_for_bindings(json_data)
      # Recursively check for @{} syntax in the JSON
      json_string = json_data.to_json
      json_string.include?('@{')
    end

    def generate_data_binding_xml(json_data)
      # Extract all binding variables
      variables = extract_binding_variables(json_data)
      
      builder = Nokogiri::XML::Builder.new(encoding: 'UTF-8') do |xml|
        emit_generated_marker_comments(xml, "#{@layout_name}.json (data binding)")
        
        # Create layout root for data binding
        xml.layout('xmlns:android' => 'http://schemas.android.com/apk/res/android',
                  'xmlns:app' => 'http://schemas.android.com/apk/res-auto',
                  'xmlns:tools' => 'http://schemas.android.com/tools') do
          
          # Add data section
          xml.data do
            # Add common imports
            xml.import(type: 'android.view.View')
            
            # Add data variable
            if has_data_definitions?(json_data)
              data_class = "#{camelize(@layout_name)}Data"
              xml.variable(name: 'data', type: "#{@package_name}.data.#{data_class}")
            end
            
            # Add viewModel variable if there are onClick handlers
            if has_click_handlers?(json_data)
              view_model_class = "#{camelize(@layout_name)}ViewModel"
              xml.variable(name: 'viewModel', type: "#{@package_name}.viewmodels.#{view_model_class}")
            end
          end
          
          # Add the actual layout content
          # Pass false for is_root since namespaces are already on <layout> tag
          create_xml_element(xml, json_data, false)
        end
      end
      
      # Format the XML nicely
      doc = Nokogiri::XML(builder.to_xml) do |config|
        config.default_xml.noblanks
      end
      
      # Pretty print with proper indentation
      formatted_xml = doc.to_xml(
        indent: 4,
        indent_text: ' ',
        save_with: Nokogiri::XML::Node::SaveOptions::FORMAT |
                   Nokogiri::XML::Node::SaveOptions::AS_XML
      )

      # Additional formatting: put each attribute on a new line for better readability
      append_generated_marker_footer(format_attributes(formatted_xml))
    end

    def generate_regular_xml(json_data)
      builder = Nokogiri::XML::Builder.new(encoding: 'UTF-8') do |xml|
        emit_generated_marker_comments(xml, "#{@layout_name}.json")
        
        # Create root layout
        create_xml_element(xml, json_data, true)
      end
      
      # Format the XML nicely
      doc = Nokogiri::XML(builder.to_xml) do |config|
        config.default_xml.noblanks
      end
      
      # Pretty print with proper indentation
      formatted_xml = doc.to_xml(
        indent: 4,
        indent_text: ' ',
        save_with: Nokogiri::XML::Node::SaveOptions::FORMAT | 
                   Nokogiri::XML::Node::SaveOptions::AS_XML
      )
      
      # Additional formatting: put each attribute on a new line for better readability
      append_generated_marker_footer(format_attributes(formatted_xml))
    end

    def extract_binding_variables(json_data)
      variables = Set.new
      extract_variables_recursive(json_data, variables)
      variables
    end

    def extract_variables_recursive(data, variables)
      if data.is_a?(Hash)
        data.each do |key, value|
          if value.is_a?(String) && value.start_with?('@{')
            # Extract variable name from binding expression
            if value.match(/@\{([^}]+)\}/)
              expr = $1
              # Simple variable extraction (can be enhanced)
              if expr.match(/^(\w+)/)
                variables.add($1)
              end
            end
          elsif value.is_a?(Hash) || value.is_a?(Array)
            extract_variables_recursive(value, variables)
          end
        end
      elsif data.is_a?(Array)
        data.each { |item| extract_variables_recursive(item, variables) }
      end
    end

    def has_click_handlers?(json_data)
      json_string = json_data.to_json
      json_string.include?('"onClick"') || json_string.include?('"onclick"')
    end

    def camelize(snake_case)
      snake_case.split('_').map(&:capitalize).join
    end

    def emit_generated_marker_comments(xml, source)
      marker = ::KjuiTools::Core::GeneratedMarker
      xml.comment " #{marker::SENTINEL} AUTO-GENERATED FILE — DO NOT EDIT "
      xml.comment " Source:    #{source} "
      xml.comment " Generator: kjui build "
      xml.comment " #{marker::HUMAN_WARNING} "
      xml.comment " #{marker::AGENT_WARNING} "
    end

    def append_generated_marker_footer(xml_string)
      footer = "<!-- ══ #{::KjuiTools::Core::GeneratedMarker::END_LINE} ══ -->"
      trailing_newline = xml_string.end_with?("\n") ? "" : "\n"
      "#{xml_string}#{trailing_newline}#{footer}\n"
    end
    
    def needs_tools_namespace?(json_element)
      # Check if this element or any of its children use tools attributes
      json_string = json_element.to_json
      json_string.include?('"tools:') || json_string.include?('"title"') || json_string.include?('"count"')
    end
    
    def has_data_definitions?(json_data)
      # Check if there are any data definitions anywhere in the JSON structure
      return true if json_data['data']
      
      # Check children recursively
      if json_data['child']
        children = json_data['child'].is_a?(Array) ? json_data['child'] : [json_data['child']]
        children.each do |child|
          return true if child.is_a?(Hash) && child['data']
          return true if child.is_a?(Hash) && has_data_definitions?(child)
        end
      end
      
      if json_data['children']
        children = json_data['children'].is_a?(Array) ? json_data['children'] : [json_data['children']]
        children.each do |child|
          return true if child.is_a?(Hash) && child['data']
          return true if child.is_a?(Hash) && has_data_definitions?(child)
        end
      end
      
      false
    end

    def create_xml_element(xml, json_element, is_root = false, parent_orientation = nil, parent_type = nil)
      # Map JSON type to Android view class (pass json_element for View type checking)
      view_class = @component_mapper.map_component(json_element['type'], json_element)
      
      # Prepare all attributes first
      attrs = {}
      
      # Add namespace declarations if this is the root element
      if is_root
        attrs['xmlns:android'] = 'http://schemas.android.com/apk/res/android'
        # Always add app namespace as it's commonly needed for ConstraintLayout and custom attributes
        attrs['xmlns:app'] = 'http://schemas.android.com/apk/res-auto'
        # Add tools namespace if we're using tools attributes
        if needs_tools_namespace?(json_element)
          attrs['xmlns:tools'] = 'http://schemas.android.com/tools'
        end
      end
      
      # Add ID if present
      if json_element['id']
        attrs['android:id'] = "@+id/#{json_element['id']}"
      end
      
      # Process layout dimensions
      dimension_attrs = @layout_processor.process_dimensions(json_element, is_root, parent_orientation)
      attrs.merge!(dimension_attrs)
      
      # Process orientation for LinearLayout
      orientation_attrs = @layout_processor.process_orientation(view_class, json_element)
      attrs.merge!(orientation_attrs)
      
      # Process all other attributes
      other_attrs = @layout_processor.process_attributes(json_element, parent_type)
      attrs.merge!(other_attrs)
      
      # Determine orientation for children
      current_orientation = nil
      if view_class == 'LinearLayout'
        current_orientation = json_element['orientation'] || 'vertical'
      end
      
      # Create element with attributes
      # For custom views with package name, use the full class name
      if view_class.include?('.')
        # Custom view with package name - create element directly
        xml.send(:method_missing, view_class, attrs) do
          create_children(xml, json_element, current_orientation, view_class)
        end
      else
        # Standard Android view
        xml.send(view_class, attrs) do
          create_children(xml, json_element, current_orientation, view_class)
        end
      end
    end


    def create_children(parent_element, json_element, parent_orientation = nil, parent_type = nil)
      # Handle children
      children = json_element['children'] || json_element['child']
      return unless children
      
      children = [children] unless children.is_a?(Array)
      
      children.each do |child|
        # Skip data definitions - they don't create UI elements
        next if child.is_a?(Hash) && child.key?('data') && !child.key?('type')
        
        create_xml_element(parent_element, child, false, parent_orientation, parent_type)
      end
    end


    def format_attributes(xml_string)
      # Format XML to put each attribute on its own line for better readability
      lines = xml_string.split("\n")
      formatted_lines = []
      
      lines.each do |line|
        # Skip comments and empty lines
        if line.strip.start_with?('<!--') || line.strip.start_with?('<?xml') || line.strip.empty?
          formatted_lines << line
          next
        end
        
        # Check if line contains an XML tag with attributes
        if line =~ /^(\s*)<([^\/\s>]+)(.*?)(\s*\/?>.*?)$/
          indent = $1
          tag_name = $2
          attributes_str = $3
          tag_end = $4
          
          # Parse all attributes including namespace prefixes
          attributes = []
          attributes_str.scan(/(\S+?)="([^"]*)"/) do |attr_name, attr_value|
            attributes << [attr_name, attr_value]
          end
          
          # Format based on number of attributes
          if attributes.size > 1
            # Multiple attributes - put each on its own line
            formatted_lines << "#{indent}<#{tag_name}"
            attributes.each do |attr_name, attr_value|
              formatted_lines << "#{indent}    #{attr_name}=\"#{attr_value}\""
            end
            # Handle closing tag
            if tag_end.strip == '/>'
              formatted_lines[-1] += '/>'
            elsif tag_end.include?('>')
              # Check if there's content after the >
              if tag_end =~ />\s*(.+)$/
                content = $1
                formatted_lines[-1] += '>'
                # Add the content on the same line if it's simple text
                if content && !content.empty?
                  formatted_lines[-1] += content
                end
              else
                formatted_lines[-1] += '>'
              end
            else
              formatted_lines[-1] += tag_end.strip
            end
          elsif attributes.size == 1
            # Single attribute - can stay on one line
            formatted_lines << line
          else
            # No attributes
            formatted_lines << line
          end
        else
          # Not a tag line or closing tag
          formatted_lines << line
        end
      end
      
      formatted_lines.join("\n")
    end
    
    def save_xml(xml_content)
      # Determine output path  
      output_dir = File.join(@config['project_path'], 'src', 'main', 'res', 'layout')
      output_dir = File.join(@config['project_path'], 'app', 'src', 'main', 'res', 'layout') if File.exist?(File.join(@config['project_path'], 'app'))
      FileUtils.mkdir_p(output_dir)
      
      # Use custom filename if provided, otherwise use default
      filename = @output_filename || "#{@layout_name.downcase}.xml"
      output_file = File.join(output_dir, filename)
      
      # Save XML file
      File.write(output_file, xml_content)
      puts "✅ Generated: #{output_file}"
    end
  end
end