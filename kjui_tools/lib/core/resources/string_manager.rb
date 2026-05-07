# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'rexml/document'
require_relative '../logger'
require_relative '../generated_marker'

module KjuiTools
  module Core
    module Resources
      class StringManager
        def initialize(config, source_path, resources_dir)
          @config = config
          @source_path = source_path
          @resources_dir = resources_dir
          @strings_file = File.join(@resources_dir, 'strings.json')
          @extracted_strings = {}  # Structure: { "filename": { "key": "value" } }
          @strings_data = load_strings_json
        end
        
        # Main process method called from ResourcesManager
        def process_strings(processed_files, processed_count, skipped_count)
          return if processed_files.empty?
          
          Core::Logger.info "Extracting strings from #{processed_count} files (#{skipped_count} skipped)..."
          
          # Extract strings from JSON files
          extract_strings(processed_files)
          
          # Save updated strings.json if there are new strings
          save_strings_json if @extracted_strings.any?
          
          # Generate StringManager.kt if needed
          # Disabled: StringManager.kt generation is not needed
          # generate_string_manager_kotlin if @config['resource_manager_directory']
        end
        
        # Apply extracted strings to strings.xml files
        def apply_to_strings_files
          return if @strings_data.empty?
          
          # Get string files from config
          string_files = @config['string_files'] || []
          
          if string_files.empty?
            # Default: update strings.xml for default language
            update_strings_xml('values')
          else
            # Update configured string files
            string_files.each do |string_file_path|
              # Extract values directory from path (e.g., "res/values-ja/strings.xml" -> "values-ja")
              if string_file_path =~ /res\/(values[^\/]*)\//
                lang_dir = $1
                update_strings_xml(lang_dir)
              elsif string_file_path =~ /(values[^\/]*)\//
                lang_dir = $1
                update_strings_xml(lang_dir)
              else
                # If no standard pattern, try to use the parent directory name
                parts = string_file_path.split('/')
                if parts.length >= 2
                  lang_dir = parts[-2]
                  update_strings_xml(lang_dir) if lang_dir.start_with?('values')
                end
              end
            end
          end
        end
        
        private
        
        # Load existing strings.json file
        def load_strings_json
          return {} unless File.exist?(@strings_file)
          
          begin
            JSON.parse(File.read(@strings_file))
          rescue JSON::ParserError => e
            Core::Logger.warn "Failed to parse strings.json: #{e.message}"
            {}
          end
        end
        
        # Save strings data to strings.json
        def save_strings_json
          # Count total new strings
          total_new_strings = 0
          @extracted_strings.each do |file_prefix, file_strings|
            total_new_strings += file_strings.size
          end
          
          # Merge extracted strings with existing strings
          # Don't overwrite Hash values (multi-language) with extracted String values
          @extracted_strings.each do |file_prefix, file_strings|
            @strings_data[file_prefix] ||= {}
            file_strings.each do |key, value|
              existing = @strings_data[file_prefix][key]
              # Only add if key doesn't exist, or existing is not a Hash (multi-language)
              if existing.nil? || !existing.is_a?(Hash)
                @strings_data[file_prefix][key] = value
              end
            end
          end
          
          # Ensure Resources directory exists
          FileUtils.mkdir_p(@resources_dir)
          
          # Write strings.json
          File.write(@strings_file, JSON.pretty_generate(@strings_data))
          Core::Logger.info "Updated strings.json with #{total_new_strings} new strings"
          
          # Clear extracted strings after saving
          @extracted_strings.clear
        end
        
        # Extract string values from processed JSON files
        def extract_strings(processed_files)
          @modified_files = []
          
          Core::Logger.debug "Processing #{processed_files.size} files for strings"
          
          # Get the layouts directory to calculate relative paths
          layouts_dir = File.join(@source_path, @config['source_directory'] || 'src/main', 'assets/Layouts')
          
          processed_files.each do |json_file|
            begin
              Core::Logger.debug "Processing file: #{json_file}"
              content = File.read(json_file)
              data = JSON.parse(content)
              
              # Get file prefix from relative path
              relative_path = Pathname.new(json_file).relative_path_from(Pathname.new(layouts_dir)).to_s
              file_prefix = generate_file_prefix(relative_path)
              
              # Create current file strings container if not exists
              @current_file_strings = {}
              
              # Extract strings recursively from JSON structure (without modifying)
              extract_strings_recursive(data, nil, file_prefix)
              
              # Store extracted strings for this file if any
              if @current_file_strings.any?
                @extracted_strings[file_prefix] ||= {}
                @extracted_strings[file_prefix].merge!(@current_file_strings)
                Core::Logger.debug "Extracted #{@current_file_strings.size} strings from #{file_prefix}"
              end
              
              # NOTE: We don't modify the original JSON files anymore
              # The resource resolution happens during code generation
            rescue JSON::ParserError => e
              Core::Logger.warn "Failed to parse #{json_file}: #{e.message}"
            rescue => e
              Core::Logger.error "Error processing #{json_file}: #{e.message}"
            end
          end
          
          if @modified_files.any?
            Core::Logger.info "Replaced strings in #{@modified_files.size} files"
          end
        end
        
        # Generate file prefix from relative path
        def generate_file_prefix(relative_path)
          # Remove .json extension and replace / with _
          # Examples:
          #   "test.json" -> "test"
          #   "subdir/test.json" -> "subdir_test"
          #   "a/b/c/test.json" -> "a_b_c_test"
          relative_path
            .gsub(/\.json$/, '')
            .gsub('/', '_')
        end
        
        # Extract strings recursively from JSON data (without modifying)
        def extract_strings_recursive(data, parent_key = nil, file_prefix = nil)
          case data
          when Hash
            data.each do |key, value|
              # Special handling for partialAttributes
              if key == 'partialAttributes' && value.is_a?(Array)
                value.each do |partial_attr|
                  if partial_attr.is_a?(Hash) && partial_attr['range'].is_a?(String)
                    # Process range text when it's a string (not an array)
                    range_text = partial_attr['range']
                    if !range_text.empty? && should_extract_string?(range_text)
                      extract_and_store_string(range_text, file_prefix)
                    end
                  end
                end
              # Regular string property handling
              elsif is_string_property?(key) && value.is_a?(String) && !value.empty?
                # Extract the string value
                if should_extract_string?(value)
                  extract_and_store_string(value, file_prefix)
                end
              elsif value.is_a?(Hash) || value.is_a?(Array)
                # Recurse into nested structures
                extract_strings_recursive(value, key, file_prefix)
              end
            end
          when Array
            data.each_with_index do |item, index|
              if item.is_a?(Hash) || item.is_a?(Array)
                extract_strings_recursive(item, parent_key, file_prefix)
              elsif item.is_a?(String) && %w[items segments].include?(parent_key)
                # Extract string items from items/segments arrays (e.g., Segment items)
                extract_and_store_string(item, file_prefix) if should_extract_string?(item)
              end
            end
          end
        end
        
        # Check if a property name is likely to contain a localizable string
        def is_string_property?(key)
          # Based on actual XML mapper and Compose components code
          string_properties = [
            'text',        # Text, Button, TextField, TextView, Checkbox
            'hint',        # TextField, SelectBox (both XML and Compose)
            'placeholder', # TextField, SelectBox alternative to hint
            'label',       # Checkbox label
            'prompt'       # SelectBox (maps to placeholder in XML)
          ]
          
          string_properties.include?(key.to_s)
        end
        
        # Check if a string should be extracted for localization
        def should_extract_string?(value)
          # Skip data binding expressions
          return false if value.start_with?('@{') || value.start_with?('${')

          # Skip if it's already a snake_case key (already converted)
          return false if value.match?(/^[a-z]+(_[a-z0-9]+)*$/)

          # Extract if it contains alphabetic characters or Japanese characters
          value.length > 2 && value.match?(/[a-zA-Z\p{Hiragana}\p{Katakana}\p{Han}]/)
        end
        
        # Extract and store string (without returning a key)
        def extract_and_store_string(value, file_prefix = nil)
          # Generate a snake_case key from the text
          key = generate_string_key(value)
          
          # Check if this exact string already has a key in this file
          existing_key = find_string_key_in_file(value, file_prefix)
          if existing_key
            Core::Logger.debug "String already extracted: #{existing_key}"
            return
          end
          
          # Add to current file strings
          @current_file_strings[key] = value
          Core::Logger.debug "New string extracted: #{key} = '#{value}'"
        end
        
        # Find existing key for a string value in a specific file
        def find_string_key_in_file(value, file_prefix)
          return nil unless file_prefix
          
          # Check if this file has been processed before
          if @strings_data[file_prefix]
            # Look for existing key in this file's strings
            @strings_data[file_prefix].find { |key, val| val == value }&.first
          end
          
          # Also check current file's strings being extracted
          if @current_file_strings
            found_key = @current_file_strings.find { |key, val| val == value }&.first
            return "#{file_prefix}_#{found_key}" if found_key
          end
          
          nil
        end
        
        # Find existing key for a string value (legacy method)
        def find_string_key(value)
          # Check both existing strings and newly extracted strings
          all_strings = @strings_data.merge(@extracted_strings)
          all_strings.find { |key, val| val == value }&.first
        end
        
        # Generate a snake_case key from text
        def generate_string_key(text)
          # Convert to snake_case
          base_key = text
            .downcase
            .gsub(/[^a-z0-9\s_]/, '') # Remove special characters (keep underscores)
            .gsub(/\s+/, '_')          # Replace spaces with underscores
            .gsub(/^_+|_+$/, '')       # Remove leading/trailing underscores
            .gsub(/__+/, '_')          # Replace multiple underscores with single
          
          # Limit length
          base_key = base_key[0..30] if base_key.length > 30
          
          # Handle duplicates
          final_key = base_key
          counter = 2
          all_strings = @strings_data.merge(@extracted_strings)
          
          while all_strings.key?(final_key)
            final_key = "#{base_key}_#{counter}"
            counter += 1
          end
          
          final_key
        end
        
        # Update strings.xml file for a specific language
        def update_strings_xml(lang_dir)
          Core::Logger.debug "Updating strings.xml for #{lang_dir}..."
          res_dir = File.join(@source_path, @config['source_directory'] || 'src/main', 'res', lang_dir)
          FileUtils.mkdir_p(res_dir)
          
          strings_xml_file = File.join(res_dir, 'strings.xml')
          Core::Logger.debug "Strings.xml path: #{strings_xml_file}"
          
          # Load existing strings.xml or create new
          doc = if File.exist?(strings_xml_file)
                  Core::Logger.debug "Loading existing strings.xml..."
                  REXML::Document.new(File.read(strings_xml_file))
                else
                  Core::Logger.debug "Creating new strings.xml..."
                  create_new_strings_xml
                end
          
          resources = doc.root
          Core::Logger.debug "Processing #{@strings_data.keys.length} files..."
          
          # Build a hash of existing strings for faster lookup
          existing_strings = {}
          resources.elements.each('string') do |elem|
            name = elem.attributes['name']
            existing_strings[name] = elem if name
          end
          Core::Logger.debug "Found #{existing_strings.keys.length} existing strings"
          
          # Add new strings from strings.json (now structured by file)
          @strings_data.each do |file_prefix, file_strings|
            next unless file_strings.is_a?(Hash)
            Core::Logger.debug "Processing #{file_prefix} with #{file_strings.keys.length} strings..."
            file_strings.each do |key, value|
              # Create full key with file prefix
              full_key = "#{file_prefix}_#{key}"
              
              # Use translated value if available for this language
              translated_value = get_translated_value(full_key, value, lang_dir)
              # Trim whitespace and normalize the string for XML
              # Preserve \n as literal \\n for Android (renders as newline at runtime)
              normalized_value = translated_value.strip.gsub("\n", "\\n").gsub(/[ \t\r]+/, ' ')
              # Escape for Android XML strings:
              # - Apostrophes must be backslash-escaped for Android resource compiler
              # - &, <, > are handled by REXML's .text= (auto-escapes to &amp; etc.)
              normalized_value = normalized_value.gsub("'") { "\\'" }
              # Convert iOS format specifiers to Android format
              # %@ -> %s, %N$@ -> %N$s (positional)
              normalized_value = convert_ios_to_android_format(normalized_value)

              if existing_strings[full_key]
                # Update existing string element
                existing_strings[full_key].text = normalized_value
              else
                # Add new string element
                string_elem = REXML::Element.new('string')
                string_elem.add_attribute('name', full_key)
                string_elem.text = normalized_value
                resources.add_element(string_elem)
                Core::Logger.debug "Added string '#{full_key}' to #{lang_dir}/strings.xml"
              end
            end
          end
          
          # Write updated XML with custom formatting to prevent multiline strings
          File.open(strings_xml_file, 'w') do |file|
            # Use a custom formatter that doesn't wrap text content
            formatter = REXML::Formatters::Pretty.new(4)
            formatter.compact = true  # Don't add extra whitespace inside text
            formatter.write(doc, file)
          end
          
          Core::Logger.info "Updated #{lang_dir}/strings.xml"
        end
        
        # Create a new strings.xml document
        def create_new_strings_xml
          doc = REXML::Document.new
          doc.add(REXML::XMLDecl.new('1.0', 'utf-8'))
          
          resources = REXML::Element.new('resources')
          doc.add_element(resources)
          
          doc
        end
        
        # Get translated value for a specific language
        def get_translated_value(key, default_value, lang_dir)
          # If value is a Hash with language keys (e.g., {"en": "Hello", "ja": "こんにちは"})
          if default_value.is_a?(Hash)
            # Extract language code from lang_dir (e.g., "values-ja" -> "ja", "values" -> "en")
            lang_code = if lang_dir =~ /values-(\w+)/
                          $1
                        else
                          'en'  # default language for "values"
                        end
            # Return the value for this language, fall back to "en", then first available
            default_value[lang_code] || default_value['en'] || default_value.values.first || ''
          else
            default_value.to_s
          end
        end
        
        # Convert iOS format specifiers to Android format
        # %@ -> %s, %1$@ -> %1$s (positional string)
        def convert_ios_to_android_format(str)
          str.gsub(/%(\d+\$)?@/) { |match|
            pos = $1 # e.g., "1$" or nil
            pos ? "%#{pos}s" : "%s"
          }
        end

        # Generate Kotlin code for StringManager
        def generate_string_manager_kotlin
          return unless @config['resource_manager_directory']
          
          resource_manager_dir = File.join(@source_path, @config['source_directory'] || 'src/main', 
                                          'java/com/kotlinjsonui/generated')
          FileUtils.mkdir_p(resource_manager_dir)
          
          output_file = File.join(resource_manager_dir, 'StringManager.kt')
          
          kotlin_code = generate_kotlin_code(@strings_data)
          
          File.write(output_file, kotlin_code)
          Core::Logger.info "✓ Generated StringManager.kt"
        end
        
        def generate_kotlin_code(strings)
          marker_header = Core::GeneratedMarker.comment_header(
            source: "StringManager (strings from resources/*.json)",
            generator: "kjui build"
          )

          code = []
          code.concat(marker_header.split("\n"))
          code << ""
          code << "package com.kotlinjsonui.generated"
          code << ""
          code << "import android.content.Context"
          code << ""
          code << "object StringManager {"
          code << "    // String resource IDs mapped from strings.json keys"
          code << "    private val stringResources: Map<String, Int> = mapOf("
          
          # Add string resource mappings
          strings.keys.sort.each do |key|
            code << "        \"#{key}\" to R.string.#{key},"
          end
          
          # Remove trailing comma from last item
          if strings.any?
            code[-1] = code[-1].chomp(',')
          end
          
          code << "    )"
          code << ""
          code << "    // Get localized string by key"
          code << "    fun getString(context: Context, key: String): String {"
          code << "        val resId = stringResources[key]"
          code << "        return if (resId != null) {"
          code << "            context.getString(resId)"
          code << "        } else {"
          code << "            // Fallback to key itself if not found"
          code << "            println(\"Warning: String key '$key' not found in strings.json\")"
          code << "            key"
          code << "        }"
          code << "    }"
          code << ""
          code << "    // Extension function for easy access"
          code << "    fun String.localized(context: Context): String {"
          code << "        // Check if this is a string key (snake_case)"
          code << "        return if (this.matches(Regex(\"^[a-z]+(_[a-z]+)*$\"))) {"
          code << "            getString(context, this)"
          code << "        } else {"
          code << "            // Return as-is if not a key"
          code << "            this"
          code << "        }"
          code << "    }"
          code << ""
          
          # Generate static accessors for each string
          strings.keys.sort.each do |key|
            property_name = snake_to_camel(key)
            
            code << "    // Access string: #{key}"
            code << "    fun get#{property_name.capitalize}(context: Context): String ="
            code << "        getString(context, \"#{key}\")"
            code << ""
          end
          
          code << "}"
          code << ""
          code << Core::GeneratedMarker.comment_footer
          code.join("\n")
        end

        def snake_to_camel(snake_case)
          parts = snake_case.split('_')
          first_part = parts.shift
          camel = first_part + parts.map(&:capitalize).join
          camel
        end
      end
    end
  end
end