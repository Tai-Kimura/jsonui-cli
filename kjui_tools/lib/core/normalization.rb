# frozen_string_literal: true

module KjuiTools
  module Core
    # Helpers around the `$jui` normalization marker that `jui build`
    # (jui_tools normalizer, `"build": {"normalizeLayouts": true}`) writes
    # into distributed layout JSON:
    #
    #   { "$jui": { "normalized": "L1", "schemaVersion": 1 }, ... }
    #
    # A layout that carries the L1 (or higher, e.g. L2) marker has already
    # had alias attribute spellings rewritten to their canonical names, so
    # consumers may take the canonical-only code path and skip alias
    # fallbacks. Raw (L0) layouts keep the legacy alias-fallback behavior.
    module Normalization
      MARKER_KEY = '$jui'
      SUPPORTED_SCHEMA_VERSION = 1

      # True when the layout root carries a normalization marker of at
      # least L1 (L2 includes L1 canonicalization).
      def self.canonicalized?(layout)
        return false unless layout.is_a?(Hash)

        marker = layout[MARKER_KEY]
        return false unless marker.is_a?(Hash)

        %w[L1 L2].include?(marker['normalized'])
      end

      # Per-file build state: ComposeBuilder#build_file sets this from the
      # layout root marker before generating (builds are single-threaded),
      # so stateless component emitters can take the canonical-only lookup
      # path without threading a flag through every helper signature.
      class << self
        attr_accessor :layout_canonicalized
      end
      self.layout_canonicalized = false

      # Canonical-first attribute lookup with alias fallback.
      #
      # - The canonical spelling always wins when present (matches the
      #   `jui build` normalizer semantics: canonical wins over aliases).
      # - Alias spellings are consulted only for raw (L0) layouts; an
      #   L1-normalized layout already had aliases rewritten, so the
      #   canonical-only path is taken (aliases are NOT read).
      def self.attr_lookup(json, canonical, *aliases)
        value = json[canonical]
        return value unless value.nil?
        return nil if layout_canonicalized

        aliases.each do |alias_name|
          value = json[alias_name]
          return value unless value.nil?
        end
        nil
      end
    end
  end
end
