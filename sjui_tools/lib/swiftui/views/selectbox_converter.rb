#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/string_manager_helper'

module SjuiTools
  module SwiftUI
    module Views
      class SelectBoxConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::StringManagerHelper

        def convert
          id = @component['id'] || 'selectBox'
          prompt = @component['prompt'] || @component['hint'] || @component['placeholder']
          selectItemType = @component['selectItemType'] || 'Normal'
          items = @component['items'] || []

          # SelectBoxViewを使用
          add_line "SelectBoxView("
          indent do
            add_line "id: \"#{id}\","

            if prompt
              if is_binding?(prompt)
                prop = extract_binding_property(prompt)
                add_line "prompt: data.#{prop},"
              else
                add_line "prompt: #{get_text_with_string_manager("\"#{prompt}\"")},"
              end
            end

            # `labelAttributes` styles the closed-state label; its keys win
            # over the component-level ones (the precedence the web and
            # Compose converters use).
            label_attrs = @component['labelAttributes'].is_a?(Hash) ? @component['labelAttributes'] : {}
            label_size = label_attrs['fontSize'] || @component['fontSize']
            if label_size
              add_line "fontSize: #{label_size},"
            end

            label_color = label_attrs['fontColor'] || @component['fontColor']
            if label_color
              color = get_swiftui_color(label_color)
              add_line "fontColor: #{color},"
            end

            # hintColor — the placeholder colour (SelectBoxView >= 10.10.1;
            # .gray remains the default when unset).
            if @component['hintColor']
              add_line "hintColor: #{get_swiftui_color(@component['hintColor'])},"
            end

            if @component['background']
              bg_color = get_swiftui_color(@component['background'])
              add_line "backgroundColor: #{bg_color},"
            end

            if @component['cornerRadius']
              add_line "cornerRadius: #{@component['cornerRadius']},"
            end

            # selectItemType
            case selectItemType
            when 'Date'
              add_line "selectItemType: .date,"

              # datePickerMode
              if @component['datePickerMode']
                case @component['datePickerMode']
                when 'time'
                  add_line "datePickerMode: .time,"
                when 'datetime', 'dateAndTime'
                  add_line "datePickerMode: .dateTime,"
                else
                  add_line "datePickerMode: .date,"
                end
              end

              # datePickerStyle
              if @component['datePickerStyle']
                case @component['datePickerStyle']
                when 'automatic'
                  add_line "datePickerStyle: .automatic,"
                when 'compact'
                  add_line "datePickerStyle: .compact,"
                when 'graphical', 'inline'  # SwiftJsonUIのinlineはSwiftUIのgraphicalにマッピング
                  add_line "datePickerStyle: .graphical,"
                else # 'wheels' or default
                  add_line "datePickerStyle: .wheel,"
                end
              end

              # dateStringFormat
              if @component['dateStringFormat']
                add_line "dateStringFormat: \"#{@component['dateStringFormat']}\","
              end

              # minimumDate. A binding used to be pasted between the quotes,
              # so the picker parsed the characters `@{...}` as a date, failed,
              # and fell back to today — the bound bound was inert.
              if @component['minimumDate']
                add_line "minimumDate: #{date_operand(@component['minimumDate'])},"
              end

              # maximumDate
              if @component['maximumDate']
                add_line "maximumDate: #{date_operand(@component['maximumDate'])},"
              end

              # minuteInterval for DatePicker
              if @component['minuteInterval']
                add_line "minuteInterval: #{@component['minuteInterval']},"
              end

              # selectedDate for DatePicker initial date.
              # SelectBoxView.selectedDate is `Date?` so we forward the optional
              # produced by `String.toDate(format:)` directly. Falling back to
              # `Date()` would force "today" whenever the binding is empty,
              # which prevents callers from representing "未指定" / "no date set".
              if @component['selectedDate']
                date_format = @component['dateFormat'] || @component['dateStringFormat'] || 'yyyy-MM-dd'
                if is_binding?(@component['selectedDate'])
                  prop = extract_binding_property(@component['selectedDate'])
                  add_line "selectedDate: data.#{prop}.toDate(format: \"#{date_format}\"),"
                else
                  add_line "selectedDate: \"#{@component['selectedDate']}\".toDate(format: \"#{date_format}\"),"
                end
              end

              # onValueChange for Date picker - write back to binding + call handler
              selected_date_prop = if @component['selectedDate'] && is_binding?(@component['selectedDate'])
                                     extract_binding_property(@component['selectedDate'])
                                   else
                                     nil
                                   end
              has_handler = @component['onValueChange'] && is_binding?(@component['onValueChange'])

              if selected_date_prop || has_handler
                add_line "onValueChange: { newValue in"
                indent do
                  if selected_date_prop
                    add_line "data.#{selected_date_prop} = newValue"
                  end
                  if has_handler
                    handler_call = get_event_handler_invocation(@component['onValueChange'], id, 'newValue')
                    add_line handler_call
                  end
                end
                add_line "},"
              end

              # Remove trailing comma from last parameter
              @generated_code[-1] = @generated_code[-1].chomp(',')
            else
              add_line "selectItemType: .normal,"

              # SelectBoxView manages its own selection state internally; the
              # layout's opening selection reaches it through `selectedIndex`
              # (literal or bound) or `selectedIndexBinding` (two-way) below.

              # items配列の処理
              if items.is_a?(String) && items.start_with?('@{') && items.end_with?('}')
                # テンプレート変数の場合
                prop = extract_binding_property(items)
                add_line "items: Array(data.#{prop}), "
              elsif items.is_a?(Array) && items.any?
                # 静的配列の場合
                add_line "items: [#{items.map { |item| "\"#{item}\"" }.join(", ")}],"
              else
                add_line "items: [],"
              end

              # selectedIndex for normal picker
              if @component['selectedIndex']
                if is_binding?(@component['selectedIndex'])
                  prop = extract_binding_property(@component['selectedIndex'])
                  add_line "selectedIndexBinding: $data.#{prop},"
                else
                  add_line "selectedIndex: #{@component['selectedIndex']},"
                end
              elsif @component['selectedValue'] && !is_binding?(@component['selectedValue']) &&
                    items.is_a?(Array) && (idx = items.index(@component['selectedValue']))
                # A literal selectedValue resolves to its item index at
                # generation time — the dynamic path does the same lookup
                # (32 parity: the declared selection rendered empty here).
                add_line "selectedIndex: #{idx},"
              elsif (selected_expr = bound_string(@component['selectedValue']))
                # The same lookup, a step later. The note here used to say
                # "selectedItem binding is not supported in the current
                # implementation" — SelectBoxView takes `selectedIndex: Int?`,
                # and the index of a bound value is an expression over the
                # item list rather than a number the generator can compute.
                add_line "selectedIndex: #{items_expression(items)}.firstIndex(of: #{selected_expr}),"
              end
            end

            # paddings - should come after selectItemType and items（UIKitに合わせてpaddingsに統一）
            if @component['paddings']
              padding = @component['paddings']
              if padding.is_a?(Array)
                case padding.length
                when 1
                  add_line "padding: EdgeInsets(top: #{padding[0]}, leading: #{padding[0]}, bottom: #{padding[0]}, trailing: #{padding[0]})"
                when 2
                  add_line "padding: EdgeInsets(top: #{padding[0]}, leading: #{padding[1]}, bottom: #{padding[0]}, trailing: #{padding[1]})"
                when 4
                  add_line "padding: EdgeInsets(top: #{padding[0]}, leading: #{padding[1]}, bottom: #{padding[2]}, trailing: #{padding[3]})"
                end
              else
                add_line "padding: EdgeInsets(top: #{padding}, leading: #{padding}, bottom: #{padding}, trailing: #{padding})"
              end
            elsif @component['paddingTop'] || @component['paddingBottom'] ||
                  @component['paddingLeft'] || @component['paddingRight']
              # UIKitに合わせてpaddingTop形式に統一
              top = @component['paddingTop'] || 0
              bottom = @component['paddingBottom'] || 0
              left = @component['paddingLeft'] || 0
              right = @component['paddingRight'] || 0
              add_line "padding: EdgeInsets(top: #{top}, leading: #{left}, bottom: #{bottom}, trailing: #{right})"
            end
          end
          add_line ")"

          # SelectBoxView handles padding/background/cornerRadius internally
          # Only apply frame, border, and margins here
          # Corresponding to Dynamic mode: SelectBoxConverter.swift

          # onValueChange handler - called when selection changes
          # onValueChange (camelCase) -> binding format only (@{functionName})
          if @component['onValueChange'] && is_binding?(@component['onValueChange'])
            # Get the binding variable name for onChange
            binding_prop = if @component['selectedDate'] && is_binding?(@component['selectedDate'])
                            extract_binding_property(@component['selectedDate'])
                          elsif @component['selectedIndex'] && is_binding?(@component['selectedIndex'])
                            extract_binding_property(@component['selectedIndex'])
                          elsif @component['selectedItem'] && is_binding?(@component['selectedItem'])
                            extract_binding_property(@component['selectedItem'])
                          elsif @component['selectedValue'] && is_binding?(@component['selectedValue'])
                            # cross-platform spelling of the same two-way
                            # selection binding (selectedItem wins)
                            extract_binding_property(@component['selectedValue'])
                          else
                            nil
                          end
            if binding_prop
              handler_call = get_event_handler_invocation(@component['onValueChange'], id, 'newValue')
              indent_str = "    " * (@indent_level + 1)
              @modifier_bag.append(:on_value_change, ".onChange(of: data.#{binding_prop}) { _, newValue in\n#{indent_str}#{handler_call}\n#{indent_str[0...-4]}}")
            end
          end

          # Apply frame modifiers
          apply_frame_constraints
          apply_frame_size

          # Note: padding, background and cornerRadius are handled internally by SelectBoxView

          # Apply border (after component's internal cornerRadius)
          if @component['borderWidth'] && @component['borderColor']
            color = get_swiftui_color(@component['borderColor'])
            border_code = build_border_overlay(color, (@component['cornerRadius'] || 8).to_i, @component['borderWidth'].to_i, @component['borderStyle'])
            @modifier_bag.register(:border, border_code)
          end

          # Apply margins (external spacing)
          apply_margins

          # Apply other modifiers
          alpha_value = attr_with_alias('opacity', 'alpha')
          if alpha_value
            @modifier_bag.register(:opacity, ".opacity(#{alpha_value})")
          end

          # hidden — visibility:"invisible" shorthand: keep layout space,
          # hide drawing + accessibility (never collapse)
          hidden_value = @component['hidden']
          if hidden_value == true
            @modifier_bag.register(:hidden, ".opacity(0).accessibilityHidden(true)")
          elsif hidden_value.is_a?(String) && hidden_value.start_with?('@{') && hidden_value.end_with?('}')
            hidden_expr = SwiftUI::Binding::BindingExpression.swift_bool_expr(hidden_value[2..-2])
            @modifier_bag.register(:hidden, ".opacity(#{hidden_expr} ? 0 : 1).accessibilityHidden(#{hidden_expr})")
          end

          generated_code
        end

        private

        # The item list as a Swift expression, for the lookups that have to
        # index into it at run time.
        def items_expression(items)
          if items.is_a?(String) && bound_value?(items)
            "Array(data.#{extract_binding_property(items)})"
          elsif items.is_a?(Array)
            "[#{items.map { |item| "\"#{item}\"" }.join(', ')}]"
          else
            '[String]()'
          end
        end

        # One date bound, parsed with the format the picker uses. A binding
        # supplies the string at run time; the parse and the fallback are
        # identical either way.
        def date_operand(value)
          text = bound_string(value) || "\"#{value}\""
          "#{text}.toDate(format: \"yyyy-MM-dd\") ?? Date()"
        end
      end
    end
  end
end
