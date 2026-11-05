# frozen_string_literal: true

module JsonUIShared
  # The language of an output path, and which of a strings.json entry's
  # languages it shows. Canonical copy lives in shared/core/language_code.rb;
  # the per-tool copies under <tool>/lib/core/ must stay byte-identical.
  #
  # Two rules the paths need, because a tag has more than one word:
  # zh-Hant.lproj is zh-Hant (not Hant), and values-b+zh+Hant, values-zh-rTW
  # and values-zh-rTW-night are zh-Hant, zh-TW and zh-TW (not b, zh and zh).
  #
  # Chinese follows what the systems do (measured on iOS 26.2 and Android API
  # 35, ticket jui-strings-language-code-with-script-subtag-lost): every
  # Traditional device takes zh-Hant or zh-TW alike and never takes a plain zh,
  # which both treat as Simplified. So Traditional never falls back to `zh`:
  # that would show Simplified with nothing saying so.
  module LanguageCode
    TRADITIONAL = %w[zh-Hant zh-TW zh-HK zh-MO].freeze
    SIMPLIFIED = %w[zh-Hans zh-CN zh-SG zh].freeze
    DEFAULT = 'en'
    # A resource directory's qualifiers that look like a language and are not.
    NOT_LANGUAGES = %w[tv car any].freeze
    NAMED_KEYS = 5

    module_function

    # "app/zh-Hant.lproj/Localizable.strings" -> "zh-Hant". Base and a path
    # with no .lproj are the default language.
    def of_lproj(path)
      name = path.to_s.split('/').reverse.find { |part| part.end_with?('.lproj') }
      return DEFAULT if name.nil?

      code = name.delete_suffix('.lproj').tr('_', '-')
      code == 'Base' ? DEFAULT : code
    end

    # "values-b+zh+Hant" -> "zh-Hant", "values-zh-rTW-night" -> "zh-TW",
    # "values-land" and "values" -> the default language.
    def of_values_dir(dir)
      qualifiers = File.basename(dir.to_s).split('-').drop(1)
      qualifiers.shift while qualifiers.first&.match?(/\A(mcc|mnc)\d+\z/)
      first = qualifiers.first.to_s
      return first.split('+').drop(1).join('-') if first.start_with?('b+')
      return DEFAULT unless first.match?(/\A[a-z]{2,3}\z/) && !NOT_LANGUAGES.include?(first)

      region = qualifiers[1].to_s[/\Ar([A-Z]{2})\z/, 1]
      region ? "#{first}-#{region}" : first
    end

    # The spellings that hold this language's text, best first. Not the
    # default language: that one is a fallback, and a fallback is said.
    def candidates(code)
      code = code.to_s.tr('_', '-')
      family = chinese_family(code)
      return ([code] + region_of(code) + family).uniq if family

      parts = code.split('-')
      parts.length.downto(1).map { |n| parts.first(n).join('-') }
    end

    # The language in `entry` that holds `code`'s text, or nil when only a
    # fallback is left.
    def spelling_in(entry, code)
      candidates(code).find { |spelling| entry.key?(spelling) && !entry[spelling].nil? }
    end

    # The text `code` shows: its own spelling, else the default language's,
    # else the first there is.
    def resolve(entry, code, default = DEFAULT)
      spelling = spelling_in(entry, code)
      spelling ? entry[spelling] : (entry[default] || entry.values.first)
    end

    # A line for the output whose keys show another language's text, or nil.
    def fallback_warning(output, code, keys)
      return nil if keys.empty?

      named = keys.first(NAMED_KEYS).join(', ')
      more = keys.length > NAMED_KEYS ? " and #{keys.length - NAMED_KEYS} more" : ''
      "#{output}: #{keys.length} key(s) have no #{code} text and show another language's: #{named}#{more}"
    end

    def chinese_family(code)
      parts = code.split('-')
      return nil unless parts.first == 'zh'
      return TRADITIONAL if parts.include?('Hant') || (parts & %w[TW HK MO]).any?

      SIMPLIFIED
    end
    private_class_method :chinese_family

    # zh-Hant-HK's own region (zh-HK) comes before the script's other spellings.
    def region_of(code)
      parts = code.split('-')
      parts.length == 3 ? ["#{parts.first}-#{parts.last}"] : []
    end
    private_class_method :region_of
  end
end
