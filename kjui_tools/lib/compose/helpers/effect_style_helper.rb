# frozen_string_literal: true

require_relative 'bound_value'

module KjuiTools
  module Compose
    module Helpers
      # `effectStyle` — the UIKit visual-effect material.
      #
      # It is declared on `common`, not just on Blur, and only BlurViewComponent
      # read it: a plain View declaring a material got nothing. The
      # codegen-effect gate reported `common.effectStyle` as unread on all three
      # platforms the moment E's mode audit put these fixtures back in scope
      # (plan 49 lane C).
      #
      # The vocabulary lives here rather than inside the Blur component, so the
      # component that OWNS the concept and the common spelling cannot answer
      # differently — the shape rjui settled on (base_converter.rb:1033).
      #
      # `common.effectStyle` enumerates fourteen spellings: the UIKit trio, the
      # five SwiftUI material names, and five aliases that normalise onto them.
      # `Blur.effectStyle` still enumerates only the UIKit trio, which is why
      # the table has to cover the union and the Blur path may consult a subset.
      # `Regular` is the declared default and the fallback all three converters
      # already used.
      #
      # Compose has no material blur. Both paths spell it the way the dynamic
      # renderer does: a translucent scrim under a real `Modifier.blur(...)`.
      module EffectStyleHelper
        module_function

        DEFAULT = 'regular'

        # Scrim colour per material. The UIKit trio keeps the alphas the Blur
        # component and DynamicBlurViewComponent already use, so folding the
        # tables together changes no Blur output.
        SCRIM = {
          'light' => 'Color.White.copy(alpha = 0.4f)',
          'extralight' => 'Color.White.copy(alpha = 0.6f)',
          'dark' => 'Color.Black.copy(alpha = 0.4f)',
          'ultrathin' => 'Color.White.copy(alpha = 0.3f)',
          'systemultrathinmaterial' => 'Color.White.copy(alpha = 0.3f)',
          'thin' => 'Color.White.copy(alpha = 0.5f)',
          'systemthinmaterial' => 'Color.White.copy(alpha = 0.5f)',
          'regular' => 'Color.White.copy(alpha = 0.7f)',
          'systemmaterial' => 'Color.White.copy(alpha = 0.7f)',
          'thick' => 'Color.White.copy(alpha = 0.85f)',
          'systemthickmaterial' => 'Color.White.copy(alpha = 0.85f)',
          'chrome' => 'Color.White.copy(alpha = 0.95f)',
          'systemchromematerial' => 'Color.White.copy(alpha = 0.95f)',
          'prominent' => 'Color.White.copy(alpha = 0.9f)'
        }.freeze

        # Blur radius per material, in the same five steps rjui uses in px.
        BLUR_DP = {
          'ultrathin' => 4, 'systemultrathinmaterial' => 4,
          'thin' => 8, 'systemthinmaterial' => 8,
          'light' => 8, 'extralight' => 4,
          'regular' => 12, 'systemmaterial' => 12,
          'prominent' => 12,
          'thick' => 16, 'systemthickmaterial' => 16,
          'chrome' => 20, 'systemchromematerial' => 20,
          'dark' => 12
        }.freeze

        def key_for(value)
          k = value.to_s.strip.downcase
          SCRIM.key?(k) ? k : DEFAULT
        end

        # Scrim expression for a declared material, or nil when absent.
        def scrim(value)
          return nil if value.nil? || value.to_s.strip.empty?

          SCRIM[key_for(value)]
        end

        # Blur radius in dp for a declared material, or nil when absent.
        def blur_dp(value)
          return nil if value.nil? || value.to_s.strip.empty?

          BLUR_DP[key_for(value)]
        end
      end
    end
  end
end
