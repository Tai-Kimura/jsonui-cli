# frozen_string_literal: true

require 'json'
require_relative 'plural_validator'

module JsonUIShared
  # Shared body of the sjui/kjui StringManagers: the layout string
  # EXTRACTION pipeline (which attributes are localizable, which values
  # qualify, key generation), the strings.json merge policy, and the
  # plural validation entry point. Canonical copy lives in
  # shared/core/string_manager_core.rb; the per-tool copies under
  # <tool>/lib/core/ must stay byte-identical (pinned by each tool's
  # shared_core_mirror_spec — same contract as layout_validator).
  #
  # Everything that touches platform resources stays in the profile
  # (<tool>/lib/core/resources/string_manager.rb): Android strings.xml /
  # <plurals> upsert + managed-prefix prune and the %@→%s conversion on
  # kjui; Localizable.strings manual/auto sections, .stringsdict, the
  # generated StringManager.swift and the %s→%@ conversion on sjui. The
  # per-file namespace convention also stays platform (kjui prefixes with
  # the relative path, sjui with the basename) — unifying it would rename
  # every existing strings.json key.
  #
  # Unified 2026-08-02 (W3-2, file 4). Divergences resolved toward the
  # correct side:
  #   - key generation follows sjui: Japanese/non-ASCII text keeps the
  #     original text as its key (the localize skill converts later).
  #     kjui stripped non-ASCII after downcasing, so Japanese extractions
  #     collapsed to an empty key; its duplicate check also compared
  #     string keys against strings.json FILE PREFIXES (never matched)
  #   - the strings.json merge never overwrites an existing key (sjui
  #     semantics): hand-edited values survive re-extraction. kjui used
  #     to refresh existing String values from the layout text
  #   - `partialAttributes` extraction handles the canonical camelCase
  #     spelling with BOTH range shapes (pattern String and legacy
  #     {text:} Hash): kjui missed Hash ranges, sjui only matched the
  #     legacy snake_case spelling (kept for compatibility)
  #   - the already-a-key skip regex follows sjui (leading letter, digits
  #     allowed in the first segment, tolerant of a trailing underscore)
  class StringManagerCore
    # Layout attributes whose String values are user-visible text
    # (mirrors the XML mapper / Compose components / SwiftUI converters).
    STRING_PROPERTIES = %w[text hint placeholder label prompt].freeze

    # Array attributes whose String items are user-visible text
    # (e.g. Segment items).
    STRING_ITEM_ARRAYS = %w[items segments].freeze

    private

    # Extract localizable strings from one parsed layout JSON.
    # Returns { generated_key => original_text }.
    def extract_strings_from_json(json_data)
      @current_file_strings = {}
      extract_strings_recursive(json_data)
      @current_file_strings
    end

    def extract_strings_recursive(data, parent_key = nil)
      case data
      when Hash
        data.each do |key, value|
          if (key == 'partialAttributes' || key == 'partial_attributes') && value.is_a?(Array)
            # Partial text styling: 'range' selects the substring — as a
            # [start, end] pair or binding (nothing to localize) or as a
            # pattern String / legacy {text:} Hash (localizable text).
            value.each do |partial_attr|
              next unless partial_attr.is_a?(Hash)
              range = partial_attr['range']
              if range.is_a?(Hash) && range['text'].is_a?(String)
                extract_and_store_string(range['text'])
              elsif range.is_a?(String) && !range.empty?
                extract_and_store_string(range)
              end
            end
          elsif STRING_PROPERTIES.include?(key.to_s) && value.is_a?(String) && !value.empty?
            extract_and_store_string(value)
          elsif value.is_a?(Hash) || value.is_a?(Array)
            extract_strings_recursive(value, key)
          end
        end
      when Array
        data.each do |item|
          if item.is_a?(Hash) || item.is_a?(Array)
            extract_strings_recursive(item, parent_key)
          elsif item.is_a?(String) && STRING_ITEM_ARRAYS.include?(parent_key.to_s)
            extract_and_store_string(item)
          end
        end
      end
    end

    # Check if a string should be extracted for localization
    def should_extract_string?(value)
      # Skip data binding expressions
      return false if value.start_with?('@{') || value.start_with?('${')

      # Skip if it's already a snake_case key (already converted).
      # Tolerates digits in any segment and a trailing underscore
      # (e.g. "key_name_"), so converted layouts never re-extract.
      return false if value.match?(/^[a-z][a-z0-9]*(_[a-z0-9]+)*_?$/)

      # Extract if it's longer than 2 characters and contains alphabetic
      # or Japanese (hiragana/katakana/kanji) characters
      value.length > 2 && value.match?(/[a-zA-Z\p{Hiragana}\p{Katakana}\p{Han}]/)
    end

    def extract_and_store_string(value)
      return unless should_extract_string?(value)

      key = generate_string_key(value)
      @current_file_strings[key] = value
    end

    # Generate a key from text.
    # ASCII text converts to snake_case; Japanese/non-ASCII text keeps the
    # original text as the key (the localize skill assigns a proper key
    # later — stripping non-ASCII would collapse the key to nothing).
    def generate_string_key(text)
      @current_file_strings ||= {}
      if text.match?(/[\p{Hiragana}\p{Katakana}\p{Han}]/)
        text.strip
      else
        base_key = text
          .downcase
          .gsub(/[^a-z0-9\s_]/, '') # Remove special characters (keep underscores)
          .gsub(/\s+/, '_')         # Replace spaces with underscores
          .gsub(/^_+|_+$/, '')      # Remove leading/trailing underscores
          .gsub(/__+/, '_')         # Replace multiple underscores with single

        # Limit length
        base_key = base_key[0..30] if base_key.length > 30

        # Handle duplicates within this file (append _2, _3, ...)
        final_key = base_key
        counter = 2
        while @current_file_strings.key?(final_key) && @current_file_strings[final_key] != text
          final_key = "#{base_key}_#{counter}"
          counter += 1
        end

        final_key
      end
    end

    # Merge freshly-extracted strings into the (possibly nested-by-file)
    # existing strings.json data. Existing keys are NEVER overwritten —
    # hand-edited values and multi-language Hashes survive re-extraction.
    # Returns the number of newly added keys.
    def merge_extracted_strings(existing, extracted)
      added = 0
      extracted.each do |file_prefix, file_strings|
        existing[file_prefix] ||= {}
        file_strings.each do |key, value|
          next if existing[file_prefix].key?(key)

          existing[file_prefix][key] = value
          added += 1
        end
      end
      added
    end

    # Validate plural entries in strings.json (schema + CLDR categories)
    # and reject layout string attributes that reference a plural key
    # (VM-only in v1). Raises JsonUIShared::PluralValidator::ValidationError
    # with all errors logged through the given logger.
    def validate_plural_strings_data!(strings_data, layout_files, logger)
      errors = JsonUIShared::PluralValidator.validate_strings(strings_data)
      errors.concat(JsonUIShared::PluralValidator.validate_layout_references(strings_data, layout_files))
      return if errors.empty?

      errors.each { |e| logger.error(e) }
      raise JsonUIShared::PluralValidator::ValidationError,
            "strings.json plural validation failed (#{errors.length} error(s))"
    end
  end
end
