# frozen_string_literal: true

require 'json'
require 'set'
require 'fileutils'
require 'rexml/document'
require 'pathname'
require_relative '../logger'
require_relative '../kotlin_identifier'
require_relative '../generated_marker'
require_relative '../plural_validator'
require_relative '../string_manager_core'
require_relative '../screen_index'

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
          # { extraction prefix => the layout's other section spellings }
          @namespace_aliases = {}
          @strings_data = load_strings_json
          # Whether THIS build re-derived strings.json from the layouts.
          # The prune below deletes on the strength of what strings.json
          # says, so it may only run when strings.json is this build's own
          # output — see the three states in update_strings_xml.
          @extraction_ran = false
          # The section spellings extraction actually re-derived, in every
          # convention that names them. This is the prune's namespace, and
          # it is recorded rather than re-globbed on purpose: a namespace
          # is only safe to delete inside if THIS build re-read the layout
          # that owns it. Globbing the layouts directory would claim the
          # namespace of a layout extraction never opened.
          @extracted_namespaces = []
        end

        # Main process method called from ResourcesManager
        def process_strings(processed_files, processed_count, skipped_count)
          validate_plural_strings!

          return if processed_files.empty?

          @extraction_ran = true

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

        # The layouts this app declares. Declared once: both the plural
        # validation and the prune namespace read it, and a second spelling
        # of the directory is how the two would come to disagree.
        def layouts_dir
          File.join(@source_path, @config['source_directory'] || 'src/main', 'assets/Layouts')
        end

        def layout_files
          Dir.glob(File.join(layouts_dir, '**/*.json')).select do |file|
            JsonUIShared::ScreenIndex.layout_path?(layouts_dir, file)
          end
        end

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
          added = merge_extracted_strings(
            @strings_data, @extracted_strings, @namespace_aliases, Core::Logger
          )

          # Ensure Resources directory exists
          FileUtils.mkdir_p(@resources_dir)

          # Write strings.json
          File.write(@strings_file, JSON.pretty_generate(@strings_data))
          Core::Logger.info "Updated strings.json with #{added} new strings"

          # Clear extracted strings after saving
          @extracted_strings.clear
          @namespace_aliases.clear
        end

        # Extract string values from processed JSON files
        def extract_strings(processed_files)
          Core::Logger.debug "Processing #{processed_files.size} files for strings"

          # Get the layouts directory to calculate relative paths
          base_dir = layouts_dir

          processed_files.each do |json_file|
            begin
              Core::Logger.debug "Processing file: #{json_file}"
              content = File.read(json_file)
              data = JSON.parse(content)

              # Get file prefix from relative path
              relative_path = Pathname.new(json_file).relative_path_from(Pathname.new(base_dir)).to_s
              file_prefix = generate_file_prefix(relative_path)
              # The other spelling of this layout's section (sjui names it
              # after the basename). Recorded so the merge does not mint a
              # second section for strings the SSoT already declares.
              @namespace_aliases[file_prefix] = JsonUIShared::StringManagerCore.namespace_candidates(
                relative_path, preferred: :relative
              )
              # Claimed whether or not this layout yields any string: a
              # layout with nothing to extract declares an EMPTY section,
              # and a key left over under its name is stale by exactly the
              # same argument.
              @extracted_namespaces.concat(@namespace_aliases[file_prefix])

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
              # Named at the end of the build (ticket
              # uikit-build-reports-success-after-a-binding-error).
              require_relative '../stage_failures'
              JsonUI::StageFailures.record('strings', "#{json_file}: its strings were not extracted (#{e.message})")
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
        # Android's resource compiler trims leading and trailing whitespace
        # from a <string> and folds internal runs, UNLESS the value is
        # wrapped in double quotes. Reported 2026-09-07: this file trimmed
        # and folded the value itself, so a SSoT string written with a
        # leading space reached iOS intact and Android without it, and the
        # same key held two different strings on two faces. There was no way
        # to fix it from the SSoT, because the SSoT is what was being
        # discarded.
        #
        # Quoting is applied only where it changes something. Wrapping every
        # value would rewrite the whole file on the next build and bury the
        # real change in thousands of lines of noise.
        #
        # The condition is the EDGE only, deliberately. An internal run is
        # not saved by quoting — REXML folds it when the Text node is built,
        # before any formatter runs — so quoting a value for its run would
        # produce a file where the quotes say "preserved" and the value is
        # folded anyway. Quotes here mean exactly one thing: this value's
        # leading or trailing whitespace survived.
        #
        # A `"` inside the value is already `\"` (android_string_escape runs
        # first), so the wrap adds the quotes and nothing else.
        def quote_whitespace_edges(text)
          return text if text.nil? || text.empty?
          return text if text == text.strip
          %("#{text}")
        end

        ANDROID_STRING_ESCAPES = { '\\' => '\\\\', '"' => '\\"', "'" => "\\'", "\n" => '\\n', "\t" => '\\t' }.freeze

        # A text as an Android string resource value. aapt reads `\` as an
        # escape, drops an unescaped `"` (a quote delimiter), rejects a bare
        # `'`, and reads a leading `@` / `?` as a resource / attribute
        # reference; a newline or tab is kept as `\n` / `\t` (REXML would
        # fold it). One pass, block form, so no escape it writes is escaped
        # again. `&`, `<` and `>` are REXML's: the Text node escapes them.
        def android_string_escape(text)
          text.gsub(/[\\"'\n\t]/) { |c| ANDROID_STRING_ESCAPES[c] }.sub(/\A[@?]/) { |c| "\\#{c}" }
        end

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

          # kjui's entries live in a marked region, rewritten from strings.json
          # on every build; everything outside it is the app's and is not
          # touched (ticket face-strings-json-keeps-a-section-the-shared-copy-
          # removed). Until 1.9.10 kjui upserted into the whole file and
          # pruned only inside a namespace a layout or a section claims, so a
          # key whose layout and section were both gone stayed forever —
          # nothing told it from a hand-written one. The region is what tells
          # them apart now, as Localizable.strings's auto-generated section
          # does on iOS.
          generated = generated_string_elements(lang_dir)
          generated_names = generated.map { |elem| elem.attributes['name'] }.to_set

          children = resources.children.to_a
          begin_at = children.index { |n| region_mark?(n, REGION_BEGIN) }
          end_at = children.index { |n| region_mark?(n, REGION_END) }
          has_region = begin_at && end_at && end_at > begin_at
          inside = has_region ? children[(begin_at + 1)...end_at] : []
          outside = has_region ? children[0...begin_at] + children[(end_at + 1)..] : children

          # Which entries outside the region are kjui's:
          #   - one under a name this build generates — always (two elements
          #     of one name do not compile; the generator's name is its own);
          #   - on the first build with a region (the file has none yet), also
          #     one inside a namespace a layout or a section claims (the rule
          #     the old prune used): it moves into the region, and if
          #     strings.json no longer declares it, it is gone with the rest
          #     of the region's stale keys. Everything else stays outside.
          managed = managed_prefixes
          moved = outside.select do |node|
            next false unless node.is_a?(REXML::Element) && %w[string plurals].include?(node.name)

            name = node.attributes['name'].to_s
            generated_names.include?(name) ||
              (!has_region && managed.any? { |prefix| name.start_with?(prefix) })
          end
          kept_outside = outside - moved

          # A build that extracted nothing does not judge: strings.json may be
          # another writer's (jui copies the shared one over this tree), so the
          # region's entries it no longer declares are kept, as the old prune
          # declined to prune.
          carried = []
          unless @extraction_ran
            carried = (inside + moved).select do |node|
              node.is_a?(REXML::Element) && !generated_names.include?(node.attributes['name'].to_s)
            end
            Core::Logger.info(
              "Did not prune #{lang_dir}/strings.xml: no strings were extracted this build, " \
              "so strings.json is not this build's own output (#{carried.size} key(s) left unjudged)"
            )
          end

          resources.children.to_a.each { |node| resources.delete(node) }
          kept_outside.each { |node| resources.add(node) unless node.is_a?(REXML::Text) && node.to_s.strip.empty? }
          resources.add(REXML::Comment.new(" #{REGION_BEGIN} "))
          (generated + carried).each { |elem| resources.add_element(elem) }
          resources.add(REXML::Comment.new(" #{REGION_END} "))

          if !has_region
            Core::Logger.info "#{lang_dir}/strings.xml: moved #{moved.size} entr#{moved.size == 1 ? 'y' : 'ies'} into the " \
                              "generated region (#{kept_outside.count { |n| n.is_a?(REXML::Element) }} hand-written left outside)"
          elsif moved.any?
            Core::Logger.info "#{lang_dir}/strings.xml: moved #{moved.size} entr#{moved.size == 1 ? 'y' : 'ies'} named as " \
                              "kjui generates into the generated region: #{moved.map { |n| n.attributes['name'] }.join(', ')}"
          end
          stale = (inside.select { |n| n.is_a?(REXML::Element) } + (has_region ? [] : moved))
                  .map { |n| n.attributes['name'].to_s } - generated_names.to_a - carried.map { |n| n.attributes['name'].to_s }
          Core::Logger.info(stale.empty? ? "Nothing to prune in #{lang_dir}/strings.xml" :
                                           "Pruned #{stale.size} stale strings from #{lang_dir}/strings.xml")

          write_strings_xml(doc, strings_xml_file, lang_dir)
        end

        REGION_BEGIN = 'JsonUI generated strings (kjui): begin. Rewritten from strings.json on every build; write your own strings outside this region.'
        REGION_END = 'JsonUI generated strings (kjui): end'

        def region_mark?(node, text)
          node.is_a?(REXML::Comment) && node.to_s.strip == text
        end

        # The namespaces a layout or a section claims (both spellings, and the
        # resource-name spelling of each) — the old prune's managed set, now
        # used once, to tell kjui's entries on the first build with a region.
        def managed_prefixes
          prefixes = []
          @extracted_namespaces.each do |spelling|
            prefixes << "#{spelling}_" << Core::KotlinIdentifier.resource_name("#{spelling}_")
          end
          @strings_data.each do |file_prefix, file_strings|
            next unless file_strings.is_a?(Hash)

            prefixes << "#{file_prefix}_" << Core::KotlinIdentifier.resource_name("#{file_prefix}_")
          end
          prefixes.uniq
        end

        # The region's elements for lang_dir, in strings.json order — the
        # sections, then each section's keys.
        def generated_string_elements(lang_dir)
          holder = REXML::Element.new('resources')
          @strings_data.each do |file_prefix, file_strings|
            next unless file_strings.is_a?(Hash)

            file_strings.each do |key, value|
              full_key = "#{file_prefix}_#{key}"
              # An Android resource cannot start with a digit (a layout whose
              # path does) — Core::KotlinIdentifier. Translations are looked up
              # by full_key, the strings.json spelling.
              xml_name = Core::KotlinIdentifier.resource_name(full_key)

              # Plural entries compile to <plurals> (R.plurals); VM/Compose
              # code reads them via pluralStringResource / getQuantityString.
              if JsonUIShared::PluralValidator.plural_value?(value)
                upsert_plurals_element(holder, {}, xml_name, value, lang_dir)
                next
              end

              # Not trimmed, whitespace runs not folded (quote_whitespace_edges);
              # \, ", ' and a leading @ / ? escaped for the resource compiler
              # (android_string_escape); &, <, > by REXML's text=; iOS format
              # specifiers converted (%@ -> %s, %N$@ -> %N$s).
              normalized_value = android_string_escape(get_translated_value(full_key, value, lang_dir))
              normalized_value = convert_ios_to_android_format(normalized_value)
              normalized_value = quote_whitespace_edges(normalized_value)

              string_elem = REXML::Element.new('string')
              string_elem.add_attribute('name', xml_name)
              string_elem.text = normalized_value
              holder.add_element(string_elem)
            end
          end
          holder.elements.to_a.each { |elem| holder.delete_element(elem) }
        end

        # Write updated XML with custom formatting to prevent multiline strings
        def write_strings_xml(doc, strings_xml_file, lang_dir)
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
            normalized = android_string_escape(body)
            normalized = JsonUIShared::PluralValidator.substitute_count(
              normalized, token: '%d', positional_token: '%1$d'
            )
            normalized = quote_whitespace_edges(normalized)
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
