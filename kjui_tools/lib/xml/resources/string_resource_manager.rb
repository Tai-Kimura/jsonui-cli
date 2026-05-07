require 'nokogiri'
require 'fileutils'

module XmlGenerator
  module Resources
    class StringResourceManager
      def initialize(project_root)
        @project_root = project_root
        @strings_file_path = find_strings_file
        @strings_cache = {}
        @new_strings = {}
        load_existing_strings
      end
      
      # Get or create a string resource reference
      def get_string_resource(text)
        return nil if text.nil? || text.empty?
        
        # Check if it's already a resource reference
        return text if text.start_with?('@string/')
        
        # Check if it's a data binding expression
        return text if text.start_with?('@{')
        
        # Check if text is too short or just numbers
        return text if text.length < 2 || text.match?(/^\d+$/)
        
        # Check existing strings
        existing_name = find_existing_string(text)
        return "@string/#{existing_name}" if existing_name
        
        # Check if we already created this string in this session
        new_name = @new_strings.key(text)
        return "@string/#{new_name}" if new_name
        
        # Create new string resource
        string_name = generate_string_name(text)
        @new_strings[string_name] = text
        "@string/#{string_name}"
      end
      
      # Save all new strings to strings.xml
      def save_new_strings
        return if @new_strings.empty?
        
        ensure_strings_file_exists
        
        # Load the XML file
        doc = Nokogiri::XML(File.read(@strings_file_path)) do |config|
          config.default_xml.noblanks
        end
        
        resources = doc.at_xpath('//resources')
        
        # Add new strings
        @new_strings.each do |name, value|
          # Skip if already exists (double check)
          next if doc.at_xpath("//string[@name='#{name}']")
          
          # Create new string element
          string_element = Nokogiri::XML::Node.new('string', doc)
          string_element['name'] = name
          
          # Process the value to handle line breaks properly
          processed_value = escape_xml_text(value)
          
          # Replace line breaks with \n for XML
          processed_value = processed_value.gsub(/\r?\n/, '\n')
          
          string_element.content = processed_value
          
          # Add to resources
          resources.add_child("\n    ")
          resources.add_child(string_element)
        end
        
        # Add final newline if there are children
        if resources.children.any?
          resources.add_child("\n")
        end
        
        # Save the file
        File.write(@strings_file_path, doc.to_xml(
          indent: 4,
          indent_text: ' ',
          save_with: Nokogiri::XML::Node::SaveOptions::FORMAT | 
                     Nokogiri::XML::Node::SaveOptions::AS_XML
        ))
        
        puts "✅ Added #{@new_strings.size} new strings to strings.xml"
        
        # Add to cache for future lookups
        @strings_cache.merge!(@new_strings)
        @new_strings.clear
      end
      
      private
      
      def find_strings_file
        possible_paths = [
          File.join(@project_root, 'src', 'main', 'res', 'values', 'strings.xml'),
          File.join(@project_root, 'app', 'src', 'main', 'res', 'values', 'strings.xml'),
          File.join(@project_root, 'sample-app', 'src', 'main', 'res', 'values', 'strings.xml')
        ]
        
        possible_paths.find { |path| File.exist?(path) } || possible_paths.first
      end
      
      def ensure_strings_file_exists
        return if File.exist?(@strings_file_path)
        
        # Create directory if needed
        FileUtils.mkdir_p(File.dirname(@strings_file_path))
        
        # Create basic strings.xml
        content = <<~XML
          <?xml version="1.0" encoding="utf-8"?>
          <resources>
              <string name="app_name">App</string>
          </resources>
        XML
        
        File.write(@strings_file_path, content)
      end
      
      def load_existing_strings
        return unless File.exist?(@strings_file_path)
        
        begin
          doc = Nokogiri::XML(File.read(@strings_file_path))
          
          # Load all existing strings into cache
          doc.xpath('//string').each do |string_node|
            name = string_node['name']
            value = unescape_xml_text(string_node.text)
            @strings_cache[name] = value if name && value
          end
        rescue => e
          puts "Warning: Could not parse strings.xml: #{e.message}"
        end
      end
      
      def find_existing_string(text)
        # Exact match
        @strings_cache.find { |name, value| value == text }&.first
      end
      
      def generate_string_name(text)
        # Generate a meaningful name from the text
        base_name = text.downcase
          .gsub(/[^a-z0-9\s_-]/, '') # Remove special characters
          .gsub(/-/, '_')             # Replace hyphens with underscores
          .gsub(/\s+/, '_')           # Replace spaces with underscores
          .gsub(/_+/, '_')             # Remove duplicate underscores
          .gsub(/^_|_$/, '')           # Remove leading/trailing underscores
        
        # Handle reserved words
        reserved_words = ['default', 'public', 'private', 'protected', 'static', 
                         'final', 'abstract', 'class', 'interface', 'enum', 
                         'package', 'import', 'return', 'if', 'else', 'switch',
                         'case', 'break', 'continue', 'for', 'while', 'do',
                         'try', 'catch', 'finally', 'throw', 'throws', 'new',
                         'this', 'super', 'extends', 'implements', 'void',
                         'boolean', 'int', 'long', 'float', 'double', 'char',
                         'byte', 'short', 'true', 'false', 'null']
        
        if reserved_words.include?(base_name)
          base_name = "str_#{base_name}"
        end
        
        # Limit length
        base_name = base_name[0..30] if base_name.length > 30
        
        # Ensure it starts with a letter
        base_name = "str_#{base_name}" unless base_name.match?(/^[a-z]/)
        
        # Handle empty or invalid names
        base_name = "str_text" if base_name.empty?
        
        # Make unique if needed
        final_name = base_name
        counter = 2
        
        while @strings_cache.key?(final_name) || @new_strings.key?(final_name)
          final_name = "#{base_name}_#{counter}"
          counter += 1
        end
        
        final_name
      end
      
      def escape_xml_text(text)
        # Escape special characters for XML
        text.gsub('&', '&amp;')
            .gsub('<', '&lt;')
            .gsub('>', '&gt;')
            .gsub('"', '&quot;')
            .gsub("'", '&apos;')
      end
      
      def unescape_xml_text(text)
        # Unescape XML entities
        text.gsub('&amp;', '&')
            .gsub('&lt;', '<')
            .gsub('&gt;', '>')
            .gsub('&quot;', '"')
            .gsub('&apos;', "'")
      end
    end
  end
end