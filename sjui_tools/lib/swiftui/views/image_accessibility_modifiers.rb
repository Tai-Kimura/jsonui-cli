# frozen_string_literal: true

require_relative '../../core/image_accessibility'

module SjuiTools
  module SwiftUI
    module Views
      # What VoiceOver hears for an image, from its role
      # (shared/core/image_accessibility.rb):
      #   label      — `.accessibilityLabel(Text(alt))`, the alt localized
      #                like `text`; a bound alt that is "" at run time hides
      #                the image
      #   decorative — `.accessibilityHidden(true)`; without it SwiftUI reads
      #                the asset name
      #   control    — nothing: it keeps reading the asset name, because
      #                hiding the only image of a `.onTapGesture` tappable
      #                leaves the control no accessibility element. The build
      #                has already named it (INFO).
      # The builder writes the role after expanding includes. A node that
      # reaches the converter without one gets the role its own attributes
      # decide, with no tappable around it.
      module ImageAccessibilityModifiers
        def apply_image_accessibility
          rule = JsonUIShared::ImageAccessibility
          case @component[rule::ROLE_KEY] || rule.role(@component)
          when 'label'
            alt = rule.alt(@component)
            if (bound = bound_string(alt))
              @modifier_bag.append(:component_specific, ".accessibilityLabel(Text(#{bound}))")
              @modifier_bag.append(:component_specific, ".accessibilityHidden(#{bound}.isEmpty)")
            else
              text = get_text_with_string_manager("\"#{alt}\"")
              @modifier_bag.append(:component_specific, ".accessibilityLabel(Text(#{text}))")
            end
          when 'decorative'
            @modifier_bag.append(:component_specific, '.accessibilityHidden(true)')
          end
        end
      end
    end
  end
end
