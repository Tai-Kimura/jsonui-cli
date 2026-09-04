# frozen_string_literal: true

require 'json'
# The item-array vocabulary lives in StringManagerCore, which requires THIS
# file. The cycle is safe because the constant is read inside a method body
# (resolved at call time, not load time), and this require guarantees it is
# defined for callers that load the validator alone (build_command does).
require_relative 'string_manager_core'

module JsonUIShared
  # Build-time validation + shared helpers for CLDR-cardinal plural entries
  # in strings.json. Canonical copy lives in shared/core/plural_validator.rb;
  # the per-tool copies under <tool>/lib/core/ must stay byte-identical
  # (same distribution contract as layout_validator.rb).
  #
  # Schema (strings.json):
  #   "items_count": {
  #     "en": { "plural": { "one": "{count} item", "other": "{count} items" } },
  #     "ja": { "plural": { "other": "{count}件" } }
  #   }
  #
  # v1 rules:
  #   - Categories are CLDR cardinal (zero/one/two/few/many/other); "other"
  #     is required, and a category the language's CLDR cardinal rules never
  #     select (e.g. "zero" for en) is an error — platforms would disagree.
  #   - "{count}" is the only placeholder (one number). printf-style
  #     specifiers (%@/%s/%d…) are not allowed inside plural forms.
  #   - Plural keys are VM-only: layout string attributes referencing one is
  #     an error, because the converters inline layout strings statically and
  #     have no syntax to pass a count.
  module PluralValidator
    class ValidationError < StandardError; end

    module_function

    CATEGORIES = %w[zero one two few many other].freeze

    # CLDR cardinal categories per language (primary subtag), excluding the
    # always-allowed 'other'. Languages absent from the table skip the
    # language×category check (structural checks still apply).
    CLDR_CARDINAL = {
      'af' => %w[one], 'am' => %w[one], 'ar' => %w[zero one two few many],
      'az' => %w[one], 'be' => %w[one few many], 'bg' => %w[one],
      'bn' => %w[one], 'bs' => %w[one few], 'ca' => %w[one many],
      'cs' => %w[one few many], 'cy' => %w[zero one two few many],
      'da' => %w[one], 'de' => %w[one], 'el' => %w[one], 'en' => %w[one],
      'es' => %w[one many], 'et' => %w[one], 'eu' => %w[one],
      'fa' => %w[one], 'fi' => %w[one], 'fil' => %w[one], 'fr' => %w[one many],
      'ga' => %w[one two few many], 'gl' => %w[one], 'gu' => %w[one],
      'he' => %w[one two many], 'hi' => %w[one], 'hr' => %w[one few],
      'hu' => %w[one], 'hy' => %w[one], 'id' => [], 'is' => %w[one],
      'it' => %w[one many], 'ja' => [], 'ka' => %w[one], 'kk' => %w[one],
      'km' => [], 'kn' => %w[one], 'ko' => [], 'lo' => [],
      'lt' => %w[one few many], 'lv' => %w[zero one], 'mk' => %w[one],
      'ml' => %w[one], 'mn' => %w[one], 'mr' => %w[one], 'ms' => [],
      'mt' => %w[one few many], 'my' => [], 'nb' => %w[one], 'ne' => %w[one],
      'nl' => %w[one], 'nn' => %w[one], 'no' => %w[one], 'pa' => %w[one],
      'pl' => %w[one few many], 'pt' => %w[one many], 'ro' => %w[one few],
      'ru' => %w[one few many], 'si' => %w[one], 'sk' => %w[one few many],
      'sl' => %w[one two few], 'sq' => %w[one], 'sr' => %w[one few],
      'sv' => %w[one], 'sw' => %w[one], 'ta' => %w[one], 'te' => %w[one],
      'th' => [], 'tl' => %w[one], 'tr' => %w[one], 'uk' => %w[one few many],
      'ur' => %w[one], 'uz' => %w[one], 'vi' => [], 'yue' => [], 'zh' => [],
      'zu' => %w[one]
    }.freeze

    # The layout string-attribute vocabulary is StringManagerCore's
    # STRING_PROPERTIES. It used to be repeated here as STRING_PROPS, so
    # "must match the extraction walk" was a comment where a reference
    # belonged. Read at call time -- a constant assignment here would run at
    # LOAD time and fail when string_manager_core.rb is required first (it
    # requires this file before defining its class).

    # True when a strings.json value is a plural entry
    # ({ lang => { "plural" => { ... } } }).
    def plural_value?(value)
      value.is_a?(Hash) && value.values.any? { |v| v.is_a?(Hash) && v.key?('plural') }
    end

    # Resolve the category=>body forms Hash for a language, with the same
    # fallback chain the flat string resolution uses
    # (lang -> default_language -> first available). Returns nil when the
    # entry carries no usable forms.
    def plural_forms(value, lang, default_language = 'en')
      return nil unless value.is_a?(Hash)

      entry = value[lang] || value[default_language] || value.values.first
      return nil unless entry.is_a?(Hash)

      forms = entry['plural']
      forms.is_a?(Hash) ? forms : nil
    end

    # Replace "{count}" with a platform token. When the body contains the
    # placeholder more than once, every occurrence uses positional_token
    # (e.g. "%1$ld") so iOS/Android format engines bind them to the single
    # count argument.
    def substitute_count(body, token:, positional_token:)
      occurrences = body.scan('{count}').length
      body.gsub('{count}', occurrences > 1 ? positional_token : token)
    end

    # Structural + CLDR validation of every plural entry in strings.json.
    # Returns an Array of error message Strings (empty when valid).
    def validate_strings(strings_data)
      errors = []
      return errors unless strings_data.is_a?(Hash)

      strings_data.each do |file_name, file_strings|
        next unless file_strings.is_a?(Hash)

        file_strings.each do |key, value|
          next unless value.is_a?(Hash)
          where = "#{file_name}.#{key}"

          if value.key?('plural')
            errors << "#{where}: 'plural' must be nested under language codes " \
                      '(e.g. "en": { "plural": { ... } })'
            next
          end
          next unless plural_value?(value)

          value.each do |lang, entry|
            unless entry.is_a?(Hash) && entry.key?('plural')
              errors << "#{where} (#{lang}): every language of a plural key must use " \
                        "{ \"plural\": { ... } } — mixing plural and plain values is not allowed"
              next
            end

            extra = entry.keys - ['plural']
            if extra.any?
              errors << "#{where} (#{lang}): unexpected keys #{extra.inspect} alongside 'plural'"
            end

            forms = entry['plural']
            unless forms.is_a?(Hash)
              errors << "#{where} (#{lang}): 'plural' must be an object of CLDR cardinal categories"
              next
            end

            unknown = forms.keys - CATEGORIES
            if unknown.any?
              errors << "#{where} (#{lang}): unknown plural categories #{unknown.inspect} " \
                        "(allowed: #{CATEGORIES.join('/')})"
            end
            errors << "#{where} (#{lang}): the 'other' category is required" unless forms.key?('other')

            allowed = CLDR_CARDINAL[lang.to_s.split(/[-_]/).first]
            if allowed
              ((forms.keys & CATEGORIES) - allowed - ['other']).each do |cat|
                errors << "#{where} (#{lang}): category '#{cat}' is never selected by CLDR " \
                          "cardinal rules for '#{lang}' — remove it (a special count=0 wording " \
                          'belongs in the ViewModel, not in plural forms)'
              end
            end

            forms.each do |cat, body|
              next unless CATEGORIES.include?(cat)

              unless body.is_a?(String)
                errors << "#{where} (#{lang}/#{cat}): plural form must be a String"
                next
              end
              body.scan(/\{([^{}]*)\}/) do |(token)|
                next if token == 'count'
                errors << "#{where} (#{lang}/#{cat}): unsupported placeholder '{#{token}}' — " \
                          "'{count}' is the only placeholder available in plural forms"
              end
              if body.match?(/%(\d+\$)?[@a-zA-Z]/)
                errors << "#{where} (#{lang}/#{cat}): printf-style specifiers (%@/%s/%d…) are " \
                          "not allowed in plural forms — use '{count}'"
              end
            end
          end
        end
      end

      errors
    end

    # Detect layout string attributes that reference a plural key (either the
    # full "<file>_<key>" form or the bare key, matching the builders' lookup
    # semantics). v1 plural keys are VM-only; returns error Strings.
    def validate_layout_references(strings_data, layout_files)
      full_keys = {}
      bare_keys = {}
      return [] unless strings_data.is_a?(Hash)

      strings_data.each do |file_name, file_strings|
        next unless file_strings.is_a?(Hash)
        file_strings.each do |key, value|
          next unless plural_value?(value)
          full_keys["#{file_name}_#{key}"] = true
          bare_keys[key] ||= "#{file_name}_#{key}"
        end
      end
      return [] if full_keys.empty?

      errors = []
      layout_files.each do |path|
        begin
          data = JSON.parse(File.read(path, encoding: 'UTF-8'))
        rescue StandardError
          next
        end

        scan_layout_node(data) do |prop, ref|
          next if ref.start_with?('@{') || ref.start_with?('${')
          resolved = full_keys[ref] ? ref : bare_keys[ref]
          next unless resolved
          errors << "#{File.basename(path)}: '#{prop}' references plural key '#{resolved}' — " \
                    'plural keys are VM-only in v1; bind a computed value ' \
                    '(e.g. "@{itemsCountText}") instead'
        end
      end
      errors
    end

    # Yields [property_name, string_value] for every layout string slot the
    # builders resolve against strings.json.
    def scan_layout_node(node, &block)
      case node
      when Hash
        StringManagerCore::STRING_PROPERTIES.each do |prop|
          yield(prop, node[prop]) if node[prop].is_a?(String) && !node[prop].empty?
        end
        %w[partialAttributes partial_attributes].each do |pa_key|
          next unless node[pa_key].is_a?(Array)
          node[pa_key].each do |attr|
            next unless attr.is_a?(Hash)
            range = attr['range']
            if range.is_a?(String) && !range.empty?
              yield('range', range)
            elsif range.is_a?(Hash) && range['text'].is_a?(String) && !range['text'].empty?
              yield('range', range['text'])
            end
          end
        end
        node.each do |key, value|
          case value
          when Hash
            scan_layout_node(value, &block)
          when Array
            value.each do |item|
              if item.is_a?(Hash) || item.is_a?(Array)
                scan_layout_node(item, &block)
              elsif item.is_a?(String) && StringManagerCore::STRING_ITEM_ARRAYS.include?(key) && !item.empty?
                yield(key, item)
              end
            end
          end
        end
      when Array
        node.each { |item| scan_layout_node(item, &block) }
      end
    end
  end
end
