#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/string_manager_helper'
require_relative '../../core/attribute_validator_core'

module SjuiTools
  module SwiftUI
    module Views
      class SegmentConverter < BaseViewConverter
        # A Segment reads no cornerRadius (the requester's ruling 2026-11-16, ticket
        # rjui-selectbox-default-corner-overrides-declared): its track and selected fill are the
        # segmented control's capsules on every platform. The `.cornerRadius` the common stages
        # wrote clipped nothing of the capsule itself, but did clip a declared background, so the
        # declaration — a size class's included — is taken out before anything reads it.
        def initialize(component, *rest)
          super(Segment.without_corner(component), *rest)
        end

        # The segmented control's capsule: its declared border and fill follow it, and with the
        # fill clipped to it the shadow does too (the orchestrator's decision 2026-11-16, under
        # the ruling above).
        def outline_shape
          'Capsule()'
        end

        module Segment
          def self.without_corner(node)
            return node unless node.is_a?(Hash) && (node.key?('cornerRadius') || node['responsive'].is_a?(Hash))

            stripped = node.reject { |key, _| key == 'cornerRadius' }
            if stripped['responsive'].is_a?(Hash)
              stripped['responsive'] = stripped['responsive'].transform_values do |overrides|
                overrides.is_a?(Hash) ? overrides.reject { |key, _| key == 'cornerRadius' } : overrides
              end
            end
            stripped
          end
        end

        include SjuiTools::SwiftUI::Helpers::StringManagerHelper
        def convert
          id = @component['id'] || 'segment'
          # Objects are not items: the declaration says static labels, and
          # both runtimes drop a non-primitive element. Dropped BEFORE the
          # index is taken so `.tag(n)` stays contiguous — the runtimes
          # compact too (asStrings / mapNotNull), and a hole here would put
          # the tags out of step with them.
          # Declared `type: "array"`, so only an array is items. A binding
          # string reached `each_with_index` and raised NoMethodError —
          # the build died on input the validator accepted silently
          # (measured 2026-09-04). A binding no longer arrives: it is
          # refused at `:error` before conversion (ruled 2026-09-05). The
          # guard stays for the values that are NOT bindings — an object,
          # a number — which nothing upstream refuses.
          raw_items = @component['items']
          items = raw_items.is_a?(Array) ? raw_items.select { |item| JsonUIShared::AttributeValidatorCore.scalar_item?(item) } : []
          
          # selectedTabIndex プロパティの処理
          initial_selection = @component['selectedTabIndex'] || @component['selectedIndex'] || 0
          
          # Get selection binding
          selection_binding = if (@component['selectedIndex'] && is_binding?(@component['selectedIndex']))
                               "$data.#{extract_binding_property(@component['selectedIndex'])}"
                             elsif (@component['selectedTabIndex'] && is_binding?(@component['selectedTabIndex']))
                               "$data.#{extract_binding_property(@component['selectedTabIndex'])}"
                             else
                               # View-local @State fallback (injected by
                               # update_generated_body) — bare reference; the
                               # old `$data.` spelling pointed at a property
                               # the Data model never grows and did not
                               # compile (codegen parity host, __control/
                               # Segment, 2026-08-02). Picker tags are Int.
                               # Seeded with the literal selectedIndex — a
                               # hard-coded 0 opened segment One regardless
                               # of the declaration.
                               # No id: its position (position_name),
                               # not camelCased (the path keeps its `_`).
                               state_var = @component['id'] ? "selected#{id.split('_').map(&:capitalize).join}" : "selected#{position_name('Segment')}"
                               add_state_variable(state_var, "Int", initial_selection.to_i.to_s)
                               "$#{state_var}"
                             end
          
          # onValueChange handler - called when the user chooses a segment
          # onValueChange (camelCase) -> binding format only (@{functionName});
          # without one, `valueChange` (value_change_call).
          on_value_change = @component['onValueChange']
          value_call = if on_value_change && is_binding?(on_value_change)
                         get_event_handler_invocation(on_value_change, view_id, 'newValue')
                       else
                         value_change_call(view_id)
                       end

          # Picker（SwiftUIのSegmented Control）. The user's choice writes the
          # selection, then calls onValueChange, then the declared onClick
          # (operation_binding); no tap around it.
          add_line "Picker(\"\", selection: #{operation_binding(selection_binding, operation_click_call, value_call)}) {"
          indent do
            items.each_with_index do |item, index|
              # Unescaped: the helper escapes what it writes back
              localized_text = get_text_with_string_manager("\"#{item}\"")
              add_line "Text(#{localized_text}).tag(#{index})#{tab_identifier(index)}"
            end
          end
          add_line "}"
          add_modifier_line ".pickerStyle(.segmented)"
          apply_segment_appearance
          # A wrapContent Segment (or one with no width and no weight) is as
          # wide as its labels: equal segments, capped at the offered width
          # (SwiftJsonUI's segmentFitsItsLabels; jsonui-cli 2.5.47, the same
          # on every platform).
          add_modifier_line ".segmentFitsItsLabels()" if fits_its_labels?

          # (appearance emitted above; see apply_segment_appearance)

          # 共通のモディファイアを適用
          apply_modifiers
          
          generated_code
        end

        # A segmented Picker's segments are UIKit's elements, not SwiftUI
        # views: inside a stop each read as a button that responds until the
        # control is read as disabled (JsonUIStoppedControl `items`).
        def stopped_items?
          true
        end

        private

        # wrapContent (any spelling codegen accepts), or no width and no
        # weight. matchParent, a number, a binding and a weight keep the width
        # the frame gives.
        def fits_its_labels?
          return false if @component.key?('weight') || @component.key?('widthWeight')
          width = @component['width']
          return true if width.nil?
          width.is_a?(String) && width.downcase.delete('_') == 'wrapcontent'
        end

        # `<id>_tab_<n>` on each segment: the id every driver's selectTab
        # looks for (iOS ActionExecutor executeSelectTab, Android and web the
        # same pattern), and the one rjui gives each segment button. The
        # segments were id-less, so a Segment could not be selected from a UI
        # test on iOS — the fallback looks in the tab bar, which a segmented
        # Picker is not (ticket
        # jui-segment-tabs-carry-no-tab-ids-so-selecttab-cannot-reach-them).
        # Measured 2026-10-03 (iOS 26.5 simulator, Xcode 26.6): an identifier
        # on a segment's Text reaches XCUITest as that segment's button, and a
        # tap on it selects the segment. None without an id, like the
        # Segment's own identifier.
        def tab_identifier(index)
          return '' unless @component['id']

          ".accessibilityIdentifier(#{swift_string_literal("#{@component['id']}_tab_#{index}")})"
        end

        # valueChange — the selector-based handler, string only: its own
        # attribute in the definitions (Segment.valueChange, "Value change
        # event"), no platform named. UIKit wires it with
        # `addTarget(_:action:for:.valueChanged)` (SJUISegmentedControl:62) —
        # the user's change only — and kjui and rjui call it where
        # onValueChange is not declared, from the tab's own operation. So it is
        # onValueChange's rule here too: called from the user's choice, after
        # the selection is written and before onClick (operation_binding),
        # as the data declares it (get_event_handler_invocation). It was an
        # `.onChange(of:)` on a bound selectedIndex — the view model's writes
        # called it as well — which called the optional closure without `?`,
        # and an unbound segment's was not read at all (the orchestrator's ruling).
        def value_change_call(id)
          handler = @component['valueChange']
          return nil unless handler.is_a?(String) && !handler.strip.empty?
          # Declared "string": '@{h}' names the same closure a bare name does.
          # It was refused here as "onValueChange's job" — but this is only
          # read when onValueChange is absent, so `valueChange: "@{h}"` built
          # a Picker that called nothing, with no warning (ticket
          # sjui-segment-valuechange-binding-is-never-called).
          return get_event_handler_invocation(handler, id, 'newValue') if is_binding?(handler)

          get_event_handler_invocation(to_camel_case(handler), id, 'newValue')
        end

        # fontColor / selectedFontColor — unselected and selected title colours.
        #
        # SwiftUI's segmented Picker exposes no per-state colour modifier, so
        # both the UIKit runtime and the SwiftUI Dynamic runtime reach through to
        # `UISegmentedControl.appearance()`. This emits the same thing from the
        # codegen (SegmentConverter.configureSegmentAppearance is the reference).
        #
        # `.appearance()` is process-wide, which is why it is applied in
        # `.onAppear` rather than at build time: a screen that sets it should not
        # restyle segments on screens that do not.
        def apply_segment_appearance
          # fontColor is the unselected label colour and selectedFontColor the
          # selected one, falling back to fontColor (contract:
          # semantics.segmentLabelColors). normalColor / selectedColor are
          # declared aliases the normalizer canonicalizes, so only the canonical
          # spellings are read here.
          normal_color = @component['fontColor']
          selected_font_color = @component['selectedFontColor'] || @component['fontColor']
          # tintColor joins the selected-tint chain: UISegmentedControl's
          # legacy tintColor is its segment tint, and the dynamic converter
          # already maps it there.
          selected_color = @component['selectedSegmentTintColor'] || @component['tintColor']
          return if normal_color.nil? && selected_color.nil? && selected_font_color.nil?

          add_modifier_line ".onAppear {"
          indent do
            add_line "let appearance = UISegmentedControl.appearance()"
            if selected_color
              add_line "appearance.selectedSegmentTintColor = UIColor(#{get_swiftui_color(selected_color)})"
            end
            if normal_color
              add_line "appearance.setTitleTextAttributes([.foregroundColor: UIColor(#{get_swiftui_color(normal_color)})], for: .normal)"
            end
            if selected_font_color
              add_line "appearance.setTitleTextAttributes([.foregroundColor: UIColor(#{get_swiftui_color(selected_font_color)})], for: .selected)"
            end
          end
          add_line "}"
        end

        def add_state_variable(name, type, default_value)
          @state_variables ||= []
          @state_variables << "@State private var #{name}: #{type} = #{default_value}"
        end

      end
    end
  end
end
