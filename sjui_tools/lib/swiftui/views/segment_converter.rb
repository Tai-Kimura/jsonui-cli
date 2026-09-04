#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/string_manager_helper'
require_relative '../../core/attribute_validator_core'

module SjuiTools
  module SwiftUI
    module Views
      class SegmentConverter < BaseViewConverter
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
          # (measured 2026-09-04). Now it generates nothing and the
          # validator names it.
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
                               state_var = "selected#{id.split('_').map(&:capitalize).join}"
                               add_state_variable(state_var, "Int", initial_selection.to_i.to_s)
                               "$#{state_var}"
                             end
          
          # Picker（SwiftUIのSegmented Control）
          add_line "Picker(\"\", selection: #{selection_binding}) {"
          indent do
            items.each_with_index do |item, index|
              # Escape double quotes in item text for Swift string literal
              escaped_item = item.to_s.gsub('\\', '\\\\').gsub('"', '\\"')
              localized_text = get_text_with_string_manager("\"#{escaped_item}\"")
              add_line "Text(#{localized_text}).tag(#{index})"
            end
          end
          add_line "}"
          add_modifier_line ".pickerStyle(.segmented)"
          apply_segment_appearance
          apply_value_change

          # (appearance emitted above; see apply_segment_appearance)

          # onValueChange handler - called when selection changes
          # onValueChange (camelCase) -> binding format only (@{functionName})
          if @component['onValueChange'] && is_binding?(@component['onValueChange'])
            binding_prop = if @component['selectedIndex'] && is_binding?(@component['selectedIndex'])
                            extract_binding_property(@component['selectedIndex'])
                          elsif @component['selectedTabIndex'] && is_binding?(@component['selectedTabIndex'])
                            extract_binding_property(@component['selectedTabIndex'])
                          else
                            "selected#{id.split('_').map(&:capitalize).join}"
                          end
            handler_call = get_event_handler_invocation(@component['onValueChange'], id, 'newValue')
            add_modifier_line ".onChange(of: data.#{binding_prop}) { _, newValue in"
            indent do
              add_line handler_call
            end
            add_line "}"
          end

          # 共通のモディファイアを適用
          apply_modifiers
          
          generated_code
        end
        private

        # valueChange — the selector-based handler, string only.
        #
        # UIKit wires it with `addTarget(_:action:for:.valueChanged)`
        # (SJUISegmentedControl:62). It is the lowercase sibling of
        # `onValueChange`, which takes a binding; this one names a method
        # directly, so it emits an `.onChange` that calls that method on the data
        # object. Nothing read it on the SwiftUI path.
        def apply_value_change
          handler = @component['valueChange']
          return if handler.nil? || handler.to_s.empty?
          # A binding here is `onValueChange`'s job, not this attribute's.
          return if is_binding?(handler)

          binding_prop = if @component['selectedIndex'] && is_binding?(@component['selectedIndex'])
                           extract_binding_property(@component['selectedIndex'])
                         elsif @component['selectedTabIndex'] && is_binding?(@component['selectedTabIndex'])
                           extract_binding_property(@component['selectedTabIndex'])
                         end
          return if binding_prop.nil?

          add_modifier_line ".onChange(of: data.#{binding_prop}) { _, newValue in"
          indent do
            add_line "data.#{to_camel_case(handler.to_s)}(newValue)"
          end
          add_line "}"
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
