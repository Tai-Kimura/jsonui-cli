# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'rexml/document'
require_relative '../logger'
require_relative '../generated_marker'
require_relative '../plural_validator'
require_relative '../string_manager_core'

module KjuiTools
  module Core
    module Resources
      # Android profile over the shared string-extraction body
      # (lib/core/string_manager_core.rb — byte-identical mirror of
      # shared/core/string_manager_core.rb, pinned by
      # spec/core/shared_core_mirror_spec.rb). Extraction semantics, key
      # generation and the strings.json merge policy live in the shared
      # core; this class owns the Android side: the relative-path file
      # namespace, strings.xml / <plurals> upsert with managed-prefix
      # stale pruning, and the iOS→Android format-specifier conversion.
      class StringManager < ::JsonUIShared::StringManagerCore
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
          validate_plural_strings!

          return if processed_files.empty?

          Core::Logger.info "Extracting strings from #{processed_count} files (#{skipped_count} skipped)..."

          # Extract strings from JSON files
          extract_strings(processed_files)

          # Save updated strings.json if there are new strings
          save_strings_json if @extracted_strings.any?
        end

        # Validate plural entries in strings.json (schema + CLDR categories)
        # and reject layout string attributes that reference a plural key
        # (VM-only in v1; Compose/VM code uses pluralStringResource /
        # getQuantityString against R.plurals). Raises
        # JsonUIShared::PluralValidator::ValidationError. Memoized — both
        # process_strings and apply_to_strings_files call through here.
        def validate_plural_strings!
          return if @plural_validated
          @plural_validated = true

          layouts_dir = File.join(@source_path, @config['source_directory'] || 'src/main', 'assets/Layouts')
          layout_files = Dir.glob(File.join(layouts_dir, '**/*.json')).reject do |file|
            file.include?('/Resources/')
          end
          validate_plural_strings_data!(@strings_data, layout_files, Core::Logger)
        end

        # Apply extracted strings to strings.xml files
        def apply_to_strings_files
          return if @strings_data.empty?

          validate_plural_strings!

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

        # Save strings data to strings.json. The merge policy lives in the
        # shared core: existing keys are never overwritten, so hand-edited
        # values and multi-language Hashes survive re-extraction.
        def save_strings_json
          added = merge_extracted_strings(@strings_data, @extracted_strings)

          # Ensure Resources directory exists
          FileUtils.mkdir_p(@resources_dir)

          # Write strings.json
          File.write(@strings_file, JSON.pretty_generate(@strings_data))
          Core::Logger.info "Updated strings.json with #{added} new strings"

          # Clear extracted strings after saving
          @extracted_strings.clear
        end

        # Extract string values from processed JSON files
        def extract_strings(processed_files)
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

              # Extract strings recursively from JSON structure (without modifying)
              file_strings = extract_strings_from_json(data)

              # Store extracted strings for this file if any
              if file_strings.any?
                @extracted_strings[file_prefix] ||= {}
                @extracted_strings[file_prefix].merge!(file_strings)
                Core::Logger.debug "Extracted #{file_strings.size} strings from #{file_prefix}"
              end

              # NOTE: We don't modify the original JSON files anymore
              # The resource resolution happens during code generation
            rescue JSON::ParserError => e
              Core::Logger.warn "Failed to parse #{json_file}: #{e.message}"
            rescue => e
              Core::Logger.error "Error processing #{json_file}: #{e.message}"
            end
          end
        end

        # Generate file prefix from relative path
        def generate_file_prefix(relative_path)
          # Remove .json extension and replace / with _
          # Examples:
          #   "test.json" -> "test"
          #   "subdir/test.json" -> "subdir_test"
          #   "a/b/c/test.json" -> "a_b_c_test"
          # Variant files (home@regular.json) fold into the BASE screen's
          # namespace — same screen, shared strings dedupe.
          relative_path
            .gsub(/\.json$/, '')
            .sub(/@[^\/]*\z/, '')
            .gsub('/', '_')
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
          existing_plurals = {}
          resources.elements.each('plurals') do |elem|
            name = elem.attributes['name']
            existing_plurals[name] = elem if name
          end
          Core::Logger.debug "Found #{existing_strings.keys.length} existing strings"

          # Add new strings from strings.json (now structured by file)
          @strings_data.each do |file_prefix, file_strings|
            next unless file_strings.is_a?(Hash)
            Core::Logger.debug "Processing #{file_prefix} with #{file_strings.keys.length} strings..."
            file_strings.each do |key, value|
              # Create full key with file prefix
              full_key = "#{file_prefix}_#{key}"

              # Plural entries compile to <plurals> (R.plurals); VM/Compose
              # code reads them via pluralStringResource / getQuantityString.
              if JsonUIShared::PluralValidator.plural_value?(value)
                upsert_plurals_element(resources, existing_plurals, full_key, value, lang_dir)
                next
              end

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

          # Prune stale keys: a key inside a JsonUI-managed namespace
          # (`<file_prefix>_...` for a prefix present in strings.json) that
          # strings.json no longer declares was removed from the SSoT and
          # must not survive here (same semantics as iOS Localizable.strings).
          # Hand-written keys outside the managed prefixes are never touched.
          expected_keys = {}
          expected_plural_keys = {}
          managed_prefixes = []
          @strings_data.each do |file_prefix, file_strings|
            next unless file_strings.is_a?(Hash)
            managed_prefixes << "#{file_prefix}_"
            file_strings.each do |key, value|
              if JsonUIShared::PluralValidator.plural_value?(value)
                expected_plural_keys["#{file_prefix}_#{key}"] = true
              else
                expected_keys["#{file_prefix}_#{key}"] = true
              end
            end
          end
          pruned_count = 0
          existing_strings.each do |name, elem|
            next if expected_keys[name]
            next unless managed_prefixes.any? { |prefix| name.start_with?(prefix) }
            resources.delete_element(elem)
            pruned_count += 1
            Core::Logger.debug "Pruned stale string '#{name}' from #{lang_dir}/strings.xml"
          end
          # Same rule for <plurals>: prunes keys removed from strings.json
          # AND the stale twin left behind when a key switches between the
          # flat and plural forms.
          existing_plurals.each do |name, elem|
            next if expected_plural_keys[name]
            next unless managed_prefixes.any? { |prefix| name.start_with?(prefix) }
            resources.delete_element(elem)
            pruned_count += 1
            Core::Logger.debug "Pruned stale plurals '#{name}' from #{lang_dir}/strings.xml"
          end
          Core::Logger.info "Pruned #{pruned_count} stale strings from #{lang_dir}/strings.xml" if pruned_count > 0


          # Write updated XML with custom formatting to prevent multiline strings
          File.open(strings_xml_file, 'w') do |file|
            # Use a custom formatter that doesn't wrap text content
            formatter = REXML::Formatters::Pretty.new(4)
            formatter.compact = true  # Don't add extra whitespace inside text
            formatter.write(doc, file)
          end

          Core::Logger.info "Updated #{lang_dir}/strings.xml"
        end

        # Insert or update a <plurals name="..."> element for a plural
        # strings.json entry, resolved for the language of lang_dir. Items
        # are rebuilt in place (stable element position) in CLDR category
        # order; `{count}` becomes %d (%1$d when it appears more than once).
        def upsert_plurals_element(resources, existing_plurals, full_key, value, lang_dir)
          lang_code = lang_dir =~ /values-(\w+)/ ? $1 : 'en'
          forms = JsonUIShared::PluralValidator.plural_forms(value, lang_code)
          return unless forms

          elem = existing_plurals[full_key]
          if elem
            elem.elements.delete_all('item')
          else
            elem = REXML::Element.new('plurals')
            elem.add_attribute('name', full_key)
            resources.add_element(elem)
            existing_plurals[full_key] = elem
            Core::Logger.debug "Added plurals '#{full_key}' to #{lang_dir}/strings.xml"
          end

          JsonUIShared::PluralValidator::CATEGORIES.each do |cat|
            body = forms[cat]
            next unless body.is_a?(String)
            normalized = body.strip.gsub("\n", "\\n").gsub(/[ \t\r]+/, ' ')
            normalized = normalized.gsub("'") { "\\'" }
            normalized = JsonUIShared::PluralValidator.substitute_count(
              normalized, token: '%d', positional_token: '%1$d'
            )
            item = REXML::Element.new('item')
            item.add_attribute('quantity', cat)
            item.text = normalized
            elem.add_element(item)
          end
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
      end
    end
  end
end
