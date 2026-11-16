# frozen_string_literal: true

module SjuiTools
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
    end
  end
end
