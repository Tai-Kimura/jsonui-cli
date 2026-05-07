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
                               # Use state variable name on data object
                               state_var = "selected#{id.split('_').map(&:capitalize).join}"
                               # Note: This needs to be defined in JSON data section
                               "$data.#{state_var}"
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
      end
    end
  end
end