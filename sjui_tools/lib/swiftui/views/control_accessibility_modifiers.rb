# frozen_string_literal: true

require_relative '../../core/control_accessibility'

module SjuiTools
  module SwiftUI
    module Views
      # What VoiceOver is told about a control beyond what it shows
      # (shared/core/control_accessibility.rb), last on the view's chain so
      # it names the element the chain formed — a Button, a Toggle, the one
      # button a tappable View combines into:
      #   accessibilityLabel      — `.accessibilityLabel(Text(…))`, the key
      #                             localized like `text`, or the binding
      #   accessibilityLiveRegion — on a Label whose text is bound, an
      #                             announcement of the new text whenever it
      #                             changes (`assertive` at high priority).
      #                             iOS has no live region, so a View's does
      #                             nothing here (attribute_definitions.json
      #                             declares it for web and Android).
      # A Radio forms its own element and names it (RadioConverter), so it
      # reads the label there.
      module ControlAccessibilityModifiers
        def apply_control_accessibility
          return if @control_accessibility_applied

          @control_accessibility_applied = true
          rule = JsonUIShared::ControlAccessibility
          section = rule.section(@component)
          if section != 'Radio' && (expr = control_accessibility_label_expr)
            add_modifier_line ".accessibilityLabel(Text(#{expr}))"
          end
          apply_live_announcement if section == 'Label'
        end

        # The accessibilityLabel as a Swift String expression, or nil.
        def control_accessibility_label_expr
          raw = JsonUIShared::ControlAccessibility.label(@component)
          return nil unless raw

          bound_string(raw) || get_text_with_string_manager("\"#{raw}\"")
        end

        def apply_live_announcement
          live = JsonUIShared::ControlAccessibility.live(@component)
          return unless live

          text = bound_string(@component['text'])
          return unless text

          priority = live == 'assertive' ? '.high' : '.default'
          add_modifier_line ".onChange(of: #{text}) { _, newValue in"
          add_modifier_line '    var announcement = AttributedString(newValue)'
          add_modifier_line "    announcement.accessibilitySpeechAnnouncementPriority = #{priority}"
          add_modifier_line '    AccessibilityNotification.Announcement(announcement).post()'
          add_modifier_line '}'
        end
      end
    end
  end
end
