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
    # `segments` is undeclared in attribute_definitions.json but IS read by
    # kjui's Segment (segment_component.rb: `json_data['items'] ||
    # json_data['segments']`). Undeclared is not unread -- count the receiving
    # ends in the implementations, and search them by the accessor spelling
    # each face actually uses.
    STRING_ITEM_ARRAYS = %w[items segments].freeze

    # The strings.json section spellings that belong to one layout.
    #
    # sjui prefixes a section with the file's basename, kjui with the
    # layouts-dir-relative path — a divergence W3-2 kept deliberately
    # (unifying renames every existing key). A layout in a subdirectory
    # therefore has TWO legitimate spellings, and BOTH are its own:
    # `item_detail/hero_section_cell.json` owns `hero_section_cell` and
    # `item_detail_hero_section_cell`. Anything else is a foreign
    # section that happens to hold the same text.
    #
    # Returned in preference order, caller's convention first. Variant
    # files (home@regular.json) fold into the base screen — same screen,
    # same strings.
    def self.namespace_candidates(relative_path, preferred: :basename)
      cleaned = relative_path.to_s.tr('\\', '/').sub(/\.json\z/, '').sub(%r{@[^/]*\z}, '')
      segments = cleaned.split('/').reject(&:empty?)
      return [] if segments.empty?

      # Normalized spellings first: the builders derive a section name from
      # a file name via the component-name round-trip (PascalCase →
      # snake_case), which folds camel boundaries AND every non-alphanumeric
      # (kebab hyphens) to underscores, and jsonui-localize writes sections
      # in that spelling. Matching the raw path here left a kebab-case web
      # consumer unable to own its OWN sections — every bare key turned into
      # a false foreign finding (840 findings / 36 files, all hyphenated,
      # 2026-08-11). The raw spellings stay as trailing candidates because
      # the sjui extractor has historically named sections by the raw
      # basename; own-ness is a membership test, and a layout's own raw
      # spelling names no other layout's section.
      normalized = segments.map { |segment| normalize_section_segment(segment) }
      spellings = [normalized.last, normalized.join('_')]
      raw = [segments.last, segments.join('_')]
      if preferred == :relative
        spellings.reverse!
        raw.reverse!
      end
      (spellings + raw).uniq
    end

    # One path segment as it names a strings.json section (the rjui
    # generator's component-name snake_case, hyphen-tolerant).
    def self.normalize_section_segment(segment)
      segment
        .gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
        .gsub(/([a-z\d])([A-Z])/, '\1_\2')
        .downcase
        .gsub(/[^a-z0-9]+/, '_')
        .gsub(/\A_+|_+\z/, '')
    end

    # Resolve a layout literal to the strings.json entry the generated
    # code should reference, or nil if no section declares it.
    #
    # Both builders used to walk the sections in file order and take the
    # first value match, so which key a layout compiled against depended
    # on THE ORDER OF SECTIONS IN strings.json — reordering the file
    # silently repointed generated code, and a screen-scoped cell whose
    # text exists under both of its spellings resolved differently on
    # each platform. Preference is explicit here instead: the sections
    # this layout owns, in the caller's order, then the rest in file
    # order.
    #
    # nil rather than a minted section: a literal no section declares is
    # a finding for the localize gate (`jui lint-strings`), never
    # something to register behind the SSoT's back.
    #
    # Returns { 'namespace', 'key', 'foreign', 'candidates' } — `foreign`
    # marks a resolution outside the layout's own spellings, `candidates`
    # lists every section that declared the same text so the caller can
    # report the collision.
    def self.resolve_string_reference(strings_data, text, own_namespaces = [])
      return nil unless strings_data.is_a?(Hash)

      matches = []
      strings_data.each do |namespace, entries|
        next unless entries.is_a?(Hash)

        key = entries.key(text)
        matches << [namespace, key] unless key.nil?
      end
      return nil if matches.empty?

      # map + compact, NOT filter_map. This file is vendored into kjui_tools
      # and sjui_tools, and kjui runs under the HOST'S SYSTEM RUBY (2.6) in
      # consumer projects, where Enumerable#filter_map (2.7+) does not exist.
      # The failure is worse than a crash: the NoMethodError is swallowed by
      # the per-file rescue as a "Failed to process", which leaves the
      # PREVIOUS generated file on disk — the screen still renders, still
      # compiles, and is silently stale. 252 layouts failed that way before
      # this was found (plan 49, 2026-08-05).
      #
      # kjui_tools/lib/compose/helpers/section_extractor.rb:625 already
      # carried this warning; it was written at the consuming end, where the
      # person editing the shared source never sees it. Anything added to
      # shared/core/ must stay within Ruby 2.6.
      owned = own_namespaces.map { |namespace| matches.assoc(namespace) }.compact
      namespace, key = owned.first || matches.first
      {
        'namespace' => namespace,
        'key' => key,
        'foreign' => !own_namespaces.include?(namespace),
        'candidates' => matches.map(&:first)
      }
    end

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
    #
    # The key becomes a RESOURCE IDENTIFIER (an Android `strings.xml` name,
    # an `R.string` symbol), so punctuation cannot survive even where the
    # letters can: aapt2 accepts kanji and kana as name characters but
    # rejects `。`, and the app then fails to build rather than warning.
    # Measured 2026-09-02 on the sample app, where re-extracting a layout
    # emitted `name='..._今日は天気がいいですね。明日も晴れるといいです。'`
    # and packaging stopped with "'。' is not a valid resource name
    # character". Runs of anything that is not a letter, digit or
    # underscore fold to a single underscore.
    def generate_string_key(text)
      @current_file_strings ||= {}

      base_key =
        if text.match?(/[\p{Hiragana}\p{Katakana}\p{Han}]/)
          text.strip.gsub(/[^\p{L}\p{N}_]+/, '_').gsub(/\A_+|_+\z/, '')
        else
          ascii_key = text
            .downcase
            .gsub(/[^a-z0-9\s_]/, '') # Remove special characters (keep underscores)
            .gsub(/\s+/, '_')         # Replace spaces with underscores
            .gsub(/^_+|_+$/, '')      # Remove leading/trailing underscores
            .gsub(/__+/, '_')         # Replace multiple underscores with single

          # Limit length
          ascii_key.length > 30 ? ascii_key[0..30] : ascii_key
        end

      # Handle duplicates within this file (append _2, _3, ...). BOTH branches
      # go through this: dropping characters a resource name cannot hold is
      # lossy, so two different sentences can reduce to one key — `…ですね。明日…`
      # and `…ですね、明日…` differ only in punctuation. The ASCII branch has
      # always had that property (`Hello, World!` and `Hello World` both reduce
      # to `hello_world`) and has always resolved it here; the Japanese branch
      # used the raw text as its key, so it could not collide and returned
      # early. Now that it also reduces, it needs the same mechanism rather
      # than a second one of its own.
      final_key = base_key
      counter = 2
      while @current_file_strings.key?(final_key) && @current_file_strings[final_key] != text
        final_key = "#{base_key}_#{counter}"
        counter += 1
      end

      final_key
    end

    # Merge freshly-extracted strings into the (possibly nested-by-file)
    # existing strings.json data. Existing keys are NEVER overwritten —
    # hand-edited values and multi-language Hashes survive re-extraction.
    # Returns the number of newly added keys.
    #
    # `aliases` maps an extraction prefix to the layout's OTHER section
    # spellings (namespace_candidates). A string the SSoT already
    # declares under one of those is not registered a second time: sjui
    # names a section after the basename and kjui after the relative
    # path, so extracting a screen-scoped cell on the other toolchain
    # minted a SECOND section holding the same strings — the fork the two
    # platforms then resolved differently, each reading a key the other
    # never wrote. The declared section stays authoritative; the skip is
    # reported rather than silent, because the layout is now relying on a
    # section it does not name.
    def merge_extracted_strings(existing, extracted, aliases = {}, logger = nil)
      added = 0
      extracted.each do |file_prefix, file_strings|
        existing[file_prefix] ||= {}
        siblings = Array(aliases[file_prefix]).reject { |namespace| namespace == file_prefix }

        file_strings.each do |key, value|
          next if existing[file_prefix].key?(key)

          declared_in = siblings.find do |namespace|
            section = existing[namespace]
            section.is_a?(Hash) && section.value?(value)
          end

          if declared_in
            logger&.warn(
              "String #{value.inspect} is already declared in strings.json section " \
              "#{declared_in} — not registering it again under #{file_prefix}. " \
              'One layout, one section: a second section holding the same string ' \
              'forks the SSoT and each platform resolves a different key.'
            )
            next
          end

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
