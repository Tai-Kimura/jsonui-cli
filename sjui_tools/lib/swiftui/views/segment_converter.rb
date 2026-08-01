#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/string_manager_helper'

module SjuiTools
  module SwiftUI
    module Views
      class SegmentConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::StringManagerHelper
        def convert
          id = @component['id'] || 'segment'
          items = @component['items'] || []
          
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
                               state_var = "selected#{id.split('_').map(&:capitalize).join}"
                               add_state_variable(state_var, "Int", "0")
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

        # normalColor / selectedColor — unselected and selected title colours.
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
          normal_color = @component['normalColor']
          selected_color = @component['selectedColor'] || @component['selectedSegmentTintColor']
          return if normal_color.nil? && selected_color.nil?

          add_modifier_line ".onAppear {"
          indent do
            add_line "let appearance = UISegmentedControl.appearance()"
            if selected_color
              add_line "appearance.selectedSegmentTintColor = UIColor(#{get_swiftui_color(selected_color)})"
            end
            if normal_color
              add_line "appearance.setTitleTextAttributes([.foregroundColor: UIColor(#{get_swiftui_color(normal_color)})], for: .normal)"
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
