# frozen_string_literal: true

require 'json'
require_relative '../../core/config_manager'
require_relative '../../core/logger'

module RjuiTools
  module React
    module Helpers
      module StringManagerHelper
        # Check if the text is a snake_case string key (e.g., "welcome_message", "button_submit")
        def string_key?(text)
          return false unless text.is_a?(String)
          return false if text.empty?

          text_without_quotes = text.gsub(/^["']|["']$/, '')

          # Skip binding expressions (@{...})
          return false if text_without_quotes.match?(/^@\{.*\}$/)

          # Skip if it contains spaces (regular text)
          return false if text_without_quotes.include?(' ')

          # Check if it's snake_case (lowercase letters, numbers, underscores
          # only). Same spelling the extractor's should_extract_string? skips
          # (string_manager_core.rb), trailing underscore included — the
          # extractor truncates long ASCII text to 31 chars, which can leave
          # a trailing underscore ("dont_have_an_account_apply_for_"), and
          # every resolver must accept what the extractor produces.
          text_without_quotes.match?(/^[a-z][a-z0-9]*(_[a-z0-9]+)*_?$/)
        end

        # Convert snake_case string key to StringManager.currentLanguage.{filePrefix}{Key}
        # Looks up strings.json to resolve the file prefix (screen name).
        #
        # Returns nil when the key either isn't a snake_case identifier or
        # doesn't resolve to any strings.json namespace. Callers must
        # handle nil — the old behavior (silently falling back to
        # `{StringManager.currentLanguage.<camelCase>}` whether or not the
        # key was registered) produced runtime `undefined` for identifiers
        # like "bash" / "yaml" / "shell" that look like snake_case but are
        # not translations.
        def convert_string_key(text)
          return nil unless string_key?(text)

          text_without_quotes = text.gsub(/^["']|["']$/, '')
          lookup_string_manager_key(text_without_quotes)
        end

        # Rewrite JSON-encoded string values that look like strings.json
        # keys and resolve to a known namespace entry. Used by the custom
        # component scaffold's array-literal path so layouts like
        # `items: [{label: "toc_row_targets"}]` emit
        # `items={[{"label":StringManager.currentLanguage.xxx}]}`.
        #
        # Only VALUES preceded by `:` are considered — JSON object keys are
        # untouched, and array-of-plain-strings literals are preserved as-is.
        # An identifier that isn't present in strings.json (e.g. `id: "a"`,
        # `anchor: "section_contract"`) falls through unchanged: lookup is
        # the safety gate that keeps non-translatable fields from being
        # turned into dangling StringManager references.
        def rewrite_json_string_values(json_str)
          return json_str unless json_str.is_a?(String)

          json_str.gsub(/:\s*"([a-z][a-z0-9]*(?:_[a-z0-9]+)*_?)"/) do |match|
            key = Regexp.last_match(1)
            resolved = lookup_string_manager_key(key)
            next match unless resolved

            # `resolved` is `{StringManager.currentLanguage.xxx}` with outer
            # braces. Inside a JS object literal we want the raw expression,
            # so strip the braces.
            ": #{resolved[1..-2]}"
          end
        end

        # Get text with StringManager resolution
        def get_text_with_string_manager(text_content)
          return text_content unless text_content.is_a?(String)

          text_without_quotes = text_content.gsub(/^["']|["']$/, '')

          # Check if it's a binding (starts with @{)
          return text_content if text_without_quotes.match?(/^@\{.*\}$/)

          # A text that IS a declared strings.json key resolves as that key,
          # before the value reverse-lookup: membership in the SSoT is what
          # makes something a key, not how it is spelled. A legacy poison
          # entry whose VALUE is another key's raw spelling hijacked the
          # value lookup on the sjui face (downstream login screen, 2026-08-09);
          # `convert_string_key` returns nil for unregistered keys, so this
          # is membership-gated and cannot mint dangling references.
          if (resolved = convert_string_key(text_without_quotes))
            return resolved
          end

          # Then, try to find by value in strings.json
          result = lookup_string_manager_by_value(text_without_quotes)
          return result if result

          text_content
        end

        private

        # Lookup by value (e.g., "AppFinder" -> StringManager.currentLanguage.loginSampleApp)
        def lookup_string_manager_by_value(text)
          strings_data = load_strings_json
          return nil if strings_data.nil? || strings_data.empty?

          strings_data.each do |file_name, file_strings|
            next unless file_strings.is_a?(Hash)

            file_strings.each do |key, value|
              # Match against string value or first language value
              match_value = value.is_a?(Hash) ? (value.values.first || '') : value.to_s
              if match_value == text
                full_key = "#{file_name}_#{key}"
                camel_key = to_camel_case(full_key)
                return "{StringManager.currentLanguage.#{camel_key}}"
              end
            end
          end

          nil
        end

        # Lookup by key in strings.json, matching sjui behavior:
        # 1. Check if text matches "file_key" pattern (e.g., "login_forgot_password")
        # 2. Check current JSON file's keys first (e.g., "title" in file "sales")
        # 3. Check all other files as fallback
        def lookup_string_manager_key(text)
          strings_data = load_strings_json
          return nil if strings_data.nil? || strings_data.empty?

          # Phase 1: Check "file_key" pattern across all files
          strings_data.each do |file_name, file_strings|
            next unless file_strings.is_a?(Hash)

            if text.start_with?("#{file_name}_")
              key = text.sub(/^#{Regexp.escape(file_name)}_/, '')
              if file_strings.key?(key)
                full_key = "#{file_name}_#{key}"
                camel_key = to_camel_case(full_key)
                return "{StringManager.currentLanguage.#{camel_key}}"
              end
            end
          end

          # Phase 2: bare key — ONLY within sections this layout owns (the
          # basename and relative-path spellings from the generator). The
          # prefixed form above names its section explicitly, so a foreign
          # hit there is a deliberate reference; a BARE key hitting a foreign
          # section is a collision, not a reference — the same ruling the
          # sjui/kjui resolvers carry. The old "all other files as fallback"
          # phase resolved a cell's bare key through whatever section
          # happened to declare it (asymmetric-resolution filing, 2026-08-11).
          own_namespaces.each do |namespace|
            file_strings = strings_data[namespace]
            next unless file_strings.is_a?(Hash)

            if file_strings.key?(text)
              full_key = "#{namespace}_#{text}"
              camel_key = to_camel_case(full_key)
              return "{StringManager.currentLanguage.#{camel_key}}"
            end
          end

          report_foreign_bare_key(text, strings_data)
          nil
        end

        # The sections the layout being generated owns. Falls back to the
        # single legacy spelling when the generator predates
        # `_current_namespaces`.
        def own_namespaces
          return [] unless @config

          @config['_current_namespaces'] ||
            [@config['_current_json_name']].compact
        end

        # A bare key declared ONLY under sections this layout does not own is
        # a broken reference under the own-section canon — warn so `jui
        # build`'s zero-warning invariant gates it (sjui/kjui emit the same
        # warning from their resolvers).
        def report_foreign_bare_key(text, strings_data)
          return unless strings_data.is_a?(Hash)
          return unless text.is_a?(String) && text.match?(/^[a-z][a-z0-9]*(_[a-z0-9]+)*_?$/)

          own = own_namespaces
          foreign = strings_data.map do |namespace, entries|
            namespace if entries.is_a?(Hash) && entries.key?(text) && !own.include?(namespace)
          end.compact
          return if foreign.empty?

          Core::Logger.warn(
            "Bare key #{text.inspect} is declared only in foreign strings.json " \
            "section(s) #{foreign.join(', ')} — a bare key resolves within the " \
            "layout's own sections (#{own.join(' / ')}). Use the fully-qualified " \
            "'<section>_<key>' spelling for a deliberate cross-section reference, " \
            "or register the key under the layout's own section (jsonui-localize)."
          )
        end

        def load_strings_json
          @strings_json_cache ||= begin
            config = Core::ConfigManager.load_config
            layouts_dir = config['layouts_directory'] || 'Layouts'
            strings_file = File.join(layouts_dir, 'Resources', 'strings.json')

            if File.exist?(strings_file)
              JSON.parse(File.read(strings_file, encoding: 'UTF-8'))
            else
              {}
            end
          rescue JSON::ParserError, TypeError
            {}
          end
        end

        # Convert snake_case to camelCase
        def to_camel_case(snake_str)
          parts = snake_str.split('_')
          return snake_str if parts.empty?

          parts.first + parts[1..].map(&:capitalize).join
        end
      end
    end
  end
end
