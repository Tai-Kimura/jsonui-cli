#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/string_manager_helper'

module SjuiTools
  module SwiftUI
    module Views
      class TextViewConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::StringManagerHelper
        def convert
          id = @component['id'] || 'textEditor'

          # Get the binding property from text field
          text_binding = @component['text']

          # Extract property name from binding (e.g., "@{simpleText}" -> "simpleText")
          if text_binding && text_binding.start_with?('@{') && text_binding.end_with?('}')
            # Two-way position: canonically a single flat identifier — the
            # parsed path alone is emitted ('??'/'!' are validator errors)
            property_name = SwiftUI::Binding::BindingExpression.parse(text_binding[2..-2]).path
            binding_path = "data.#{property_name}"
          else
            # Fallback to ID-based naming if no binding
            state_var = "#{id}Text"
            add_state_variable(state_var, "String", '""')
            binding_path = "data.#{state_var}"
          end

          # TextViewWithPlaceholderを使用
          add_line "TextViewWithPlaceholder("
          indent do
            add_line "text: $#{binding_path},"

            # hint (placeholder) - hint takes priority, fallback to placeholder
            hint_value = @component['hint'] || @component['placeholder']
            if hint_value
              if hint_value.is_a?(String) && hint_value.start_with?('@{') && hint_value.end_with?('}')
                # Binding expression -> resolve to data property (canonical
                # expression parsing: path + optional '?? default')
                hint_expr = SwiftUI::Binding::BindingExpression.swift_value_expr(hint_value[2..-2])
                add_line "hint: #{hint_expr},"
              else
                # Escape newlines in hint text
                escaped_hint = hint_value.gsub("\n", "\\n")
                # Use localized strings for snake_case hint text
                hint_text = get_text_with_string_manager("\"#{escaped_hint}\"")
                add_line "hint: #{hint_text},"
              end
            end

            # hintAttributes の処理
            if @component['hintAttributes']
              # hintAttributesからhintColorとhintFontを取得
              hint_attrs = @component['hintAttributes']

              if hint_attrs['fontColor'] || hint_attrs['color']
                color = get_swiftui_color(hint_attrs['fontColor'] || hint_attrs['color'])
                add_line "hintColor: #{color},"
              elsif @component['hintColor']
                # 個別のhintColor属性も引き続きサポート
                color = get_swiftui_color(@component['hintColor'])
                add_line "hintColor: #{color},"
              end

              if hint_attrs['font']
                add_line "hintFont: \"#{hint_attrs['font']}\","
              elsif @component['hintFont']
                # 個別のhintFont属性も引き続きサポート
                add_line "hintFont: \"#{@component['hintFont']}\","
              end

              if hint_attrs['fontSize']
                add_line "hintFontSize: #{hint_attrs['fontSize']},"
              elsif @component['hintFontSize']
                add_line "hintFontSize: #{@component['hintFontSize']},"
              end

              if hint_attrs['lineHeightMultiple']
                add_line "hintLineHeightMultiple: #{hint_attrs['lineHeightMultiple']},"
              elsif @component['hintLineHeightMultiple']
                add_line "hintLineHeightMultiple: #{@component['hintLineHeightMultiple']},"
              end

              # その他のhintAttributesはコメントとして記録
              add_line "// hintAttributes: #{hint_attrs.to_json}"
            else
              # hintColor (個別属性)
              if @component['hintColor']
                color = get_swiftui_color(@component['hintColor'])
                add_line "hintColor: #{color},"
              end

              # hintFont (個別属性)
              if @component['hintFont']
                add_line "hintFont: \"#{@component['hintFont']}\","
              end

              # hintFontSize (個別属性)
              if @component['hintFontSize']
                add_line "hintFontSize: #{@component['hintFontSize']},"
              end

              # hintLineHeightMultiple (個別属性)
              if @component['hintLineHeightMultiple']
                add_line "hintLineHeightMultiple: #{@component['hintLineHeightMultiple']},"
              end
            end

            # hideOnFocused
            if @component['hideOnFocused'] == false
              add_line "hideOnFocused: false,"
            end

            # fontSize
            if @component['fontSize']
              add_line "fontSize: #{@component['fontSize']},"
            end

            # fontColor
            if @component['fontColor']
              color = get_swiftui_color(@component['fontColor'])
              add_line "fontColor: #{color},"
            end

            # font
            if @component['font']
              add_line "fontName: \"#{@component['font']}\","
            end

            # background
            if @component['background']
              bg_color = get_swiftui_color(@component['background'])
              add_line "backgroundColor: #{bg_color},"
            end

            # cornerRadius
            if @component['cornerRadius']
              add_line "cornerRadius: #{@component['cornerRadius']},"
            end

            # containerInset (also accept paddings as containerInset for TextView)
            inset = @component['containerInset'] || @component['paddings']
            if inset
              if inset.is_a?(Array)
                case inset.length
                when 1
                  add_line "containerInset: EdgeInsets(top: #{inset[0]}, leading: #{inset[0]}, bottom: #{inset[0]}, trailing: #{inset[0]}),"
                when 2
                  add_line "containerInset: EdgeInsets(top: #{inset[0]}, leading: #{inset[1]}, bottom: #{inset[0]}, trailing: #{inset[1]}),"
                when 4
                  add_line "containerInset: EdgeInsets(top: #{inset[0]}, leading: #{inset[1]}, bottom: #{inset[2]}, trailing: #{inset[3]}),"
                end
              else
                add_line "containerInset: EdgeInsets(top: #{inset}, leading: #{inset}, bottom: #{inset}, trailing: #{inset}),"
              end
            end

            # flexible
            if @component['flexible'] == true
              add_line "flexible: true,"
            end

            # minHeight
            if @component['minHeight']
              add_line "minHeight: #{@component['minHeight']},"
            end

            # maxHeight
            if @component['maxHeight']
              add_line "maxHeight: #{@component['maxHeight']},"
            end

            # Focus-state binding — TextField parity: every TextView with an id
            # binds data.<id>IsFocused (auto-added to Data by the updater) into
            # the component, so a ViewModel can drive focus. The component keeps
            # it in two-way sync with its internal FocusState (SwiftJsonUI
            # TextViewWithPlaceholder `isFocused:` param, v10.3.0+).
            # Declared LAST in the library init — Swift requires call-site
            # argument order to match the declaration, so emit it last.
            if @component['id']
              focus_var = "#{to_camel_case(@component['id'])}IsFocused"
              add_line "isFocused: $data.#{focus_var},"
            end

            # 最後のカンマを削除
            if @generated_code.last.end_with?(',')
              @generated_code[-1] = @generated_code.last.chomp(',')
            end
          end
          add_line ")"

          # onTextChange handler - called when text changes
          # onTextChange (camelCase) -> binding format only (@{functionName})
          if @component['onTextChange'] && is_binding?(@component['onTextChange'])
            handler_call = get_event_handler_invocation(@component['onTextChange'], id, 'newValue')
            indent_str = "    " * (@indent_level + 1)
            # Guard: only call callback when value actually changed (prevent feedback loop)
            @modifier_bag.append(:on_text_change, ".onChange(of: #{binding_path}) { oldValue, newValue in\n#{indent_str}guard oldValue != newValue else { return }\n#{indent_str}#{handler_call}\n#{indent_str[0...-4]}}")
          end

          # TextViewWithPlaceholder handles background/cornerRadius internally
          # Only apply frame, border, and margins here
          # Corresponding to Dynamic mode: TextViewConverter.swift

          # Apply frame modifiers
          if @component['flexible'] == true
            # For flexible TextViews, apply minHeight/maxHeight as frame
            if @component['minHeight'] && @component['maxHeight']
              @modifier_bag.append(:frame_size, ".frame(minHeight: #{@component['minHeight']}, maxHeight: #{@component['maxHeight']})")
            elsif @component['minHeight']
              @modifier_bag.append(:frame_size, ".frame(minHeight: #{@component['minHeight']})")
            elsif @component['maxHeight']
              @modifier_bag.append(:frame_size, ".frame(maxHeight: #{@component['maxHeight']})")
            end
          else
            # paddings is used as containerInset for TextView, so don't apply external padding
            # Normal frame application
            apply_frame_constraints
            apply_frame_size
          end

          # Note: background and cornerRadius are handled internally by TextViewWithPlaceholder
          # so we skip them here

          # Apply border (after component's internal cornerRadius)
          if @component['borderWidth'] && @component['borderColor']
            color = get_swiftui_color(@component['borderColor'])
            border_code = build_border_overlay(color, (@component['cornerRadius'] || 0).to_i, @component['borderWidth'].to_i)
            @modifier_bag.register(:border, border_code)
          end

          # Apply margins (external spacing)
          apply_margins

          # Apply other modifiers
          alpha_value = attr_with_alias('opacity', 'alpha')
          if alpha_value
            @modifier_bag.register(:opacity, ".opacity(#{alpha_value})")
          end

          hidden_value = @component['hidden']
          if hidden_value == true
            @modifier_bag.register(:hidden, ".hidden()")
          elsif hidden_value.is_a?(String) && hidden_value.start_with?('@{') && hidden_value.end_with?('}')
            hidden_expr = SwiftUI::Binding::BindingExpression.swift_bool_expr(hidden_value[2..-2])
            @modifier_bag.register(:hidden, ".opacity(#{hidden_expr} ? 0 : 1)")
          end

          generated_code
        end

        private

        def add_state_variable(name, type, default_value)
          @state_variables ||= []
          @state_variables << "@State private var #{name}: #{type} = #{default_value}"
        end
      end
    end
  end
end
