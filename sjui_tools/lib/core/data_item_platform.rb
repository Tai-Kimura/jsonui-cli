# frozen_string_literal: true

module JsonUIShared
  # Whether a layout `data` item is this platform's — the one reader of a
  # data item's `platform` key, for every tool and every place that asks
  # (the binding validator's data_item_applies?, the data model / converter
  # readers of sjui and kjui, rjui's Data type and ViewModel handlers).
  #
  # The shape is the one `jui build` reads (jui_tools/jui_cli/core/
  # platform_resolver.py, restated in shared/core/platform_semantics.json
  # nodeDirective.stringForm): a string of comma-separated tokens, compared
  # without case, each naming a platform by any of its tokens. `jui build`
  # drops a data item whose tokens name none of the target's and removes the
  # key from the one it keeps, so a distributed layout never carries it; a
  # tool meets the key only in a layout that did not go through `jui build`.
  #
  # Until jsonui-cli 1.9.0 the tools read it three ways: sjui and kjui kept an
  # item only when the value was exactly 'swift' / 'kotlin' (so "ios",
  # "swift,kotlin", "Swift" or an override map dropped it on the platform it
  # names), and rjui did not read it at all (a "swift" item was the web's
  # data too). None was the declared reading; this is.
  #
  # Any other shape (an override map, which `jui build` merges; a list, which
  # nothing declares) is not a filter here either, as in the resolver: the
  # item applies. The binding validator names a shape that is neither a
  # string nor an override map.
  module DataItemPlatform
    # nodeDirective.stringForm.tokens — held equal to
    # shared/core/platform_semantics.json by each tool's
    # spec/core/data_item_platform_spec.rb, as the resolver's own table is by
    # jui_tools/tests/test_platform_semantics_is_read_by_the_resolver.py.
    TOKENS = {
      'ios' => %w[ios swift swiftui uikit],
      'android' => %w[android kotlin java compose xml],
      'web' => %w[web typescript javascript react]
    }.freeze

    module_function

    # `target`: the asking tool, by platform ('ios') or by any of its tokens
    # ('swift', 'kotlin', 'react').
    def applies?(item, target)
      return true unless item.is_a?(Hash)

      value = item['platform']
      return true unless value.is_a?(String)

      named = value.split(',').map { |t| t.strip.downcase }.reject(&:empty?)
      return true if named.empty?

      !(named & tokens_of(target)).empty?
    end

    # The tokens of the platform `target` names; raises on a target no
    # platform owns (a caller's spelling error, not a layout's).
    def tokens_of(target)
      key = target.to_s.downcase
      return TOKENS[key] if TOKENS.key?(key)

      TOKENS.each_value { |tokens| return tokens if tokens.include?(key) }
      raise ArgumentError, "no platform has the token '#{target}' (#{TOKENS.keys.join(' / ')})"
    end

    # A `platform` value that is neither a string nor an override map
    # (a non-empty Hash whose keys are all platforms): nothing reads it.
    def unread_shape?(value)
      return false if value.nil? || value.is_a?(String)
      return false if value.is_a?(Hash) && !value.empty? && value.keys.all? { |k| TOKENS.key?(k) }

      true
    end
  end
end
