#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../helpers/string_manager_helper'
require_relative '../../core/binding_validator_core'

module SjuiTools
  module SwiftUI
    module Views
      class SelectBoxConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::StringManagerHelper

        def convert
          # The box's name — its handlers' viewId and SelectBoxView's id:
          # the id, else its drawn type and position (view_id).
          id = view_id
          prompt = @component['prompt'] || @component['hint'] || @component['placeholder']
          selectItemType = @component['selectItemType'] || 'Normal'
          items = @component['items'] || []

          # The declared onClick, called from the user's pick — after the
          # selection is written and onValueChange — through the closure
          # SelectBoxView calls for a pick and nothing else
          # (operation_click_call); no tap around the box, whose own tap opens
          # the picker. It was called from nothing.
          click = operation_click_call

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

            # font — the label's family, or "bold" for the weight. Nothing
            # read the spelling here at all, and an outer `.font()` could not
            # have fixed it: SelectBoxView sets its own font internally, so it
            # would win. SwiftJsonUI grew `fontName:` for this (10.14.x); the
            # resolution rule inside it is the one TextViewWithPlaceholder and
            # IconLabelView already use.
            label_font = label_attrs['font'] || @component['font']
            if label_font
              add_line "fontName: #{bound_string(label_font) || "\"#{label_font}\""},"
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

            # caretAttributes — the closed-state caret. The object was
            # UIKit-only (SJUISelectBox) until 1.8.101, so nothing here read
            # it; the SSoT now declares it for every face. Absent: nothing is
            # emitted and SelectBoxView keeps its fixed chevron, so existing
            # layouts do not move. Present: the keys become the view's
            # `CaretAttributes` — every key optional, so `{"rightMargin": 12}`
            # alone moves the default glyph off the trailing edge. The
            # dynamic path (SelectBoxConverter.swift) builds the same struct.
            caret_attrs = @component['caretAttributes']
            if caret_attrs.is_a?(Hash)
              add_line "caret: #{caret_literal(caret_attrs)},"
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
                  add_line "selectedDate: #{swift_string_literal(@component['selectedDate'])}.toDate(format: \"#{date_format}\"),"
                end
              end

              # onValueChange for Date picker - write back to binding + call handler
              selected_date_prop = if @component['selectedDate'] && is_binding?(@component['selectedDate'])
                                     extract_binding_property(@component['selectedDate'])
                                   else
                                     nil
                                   end
              has_handler = @component['onValueChange'] && is_binding?(@component['onValueChange'])

              if selected_date_prop || has_handler || click
                add_line "onValueChange: { newValue in"
                indent do
                  if selected_date_prop
                    add_line "data.#{selected_date_prop} = newValue"
                  end
                  if has_handler
                    # The date's string; by the handler's declared parameters
                    # (pick_invocation) — no index for a date, and a handler
                    # declared to take one is not called.
                    add_line pick_invocation(@component['onValueChange'], id, nil)
                  end
                  add_line click if click
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
                add_line "items: [#{items.map { |item| swift_string_literal(item) }.join(", ")}],"
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
              elsif selected_declaration && !is_binding?(selected_declaration) &&
                    items.is_a?(Array) && (idx = items.index(selected_declaration))
                # A literal selection resolves to its item index at
                # generation time — the dynamic path does the same lookup
                # (32 parity: the declared selection rendered empty here).
                add_line "selectedIndex: #{idx},"
              elsif (selected_expr = bound_string(selected_declaration))
                # The same lookup, a step later. The note here used to say
                # "selectedItem binding is not supported in the current
                # implementation" — SelectBoxView takes `selectedIndex: Int?`,
                # and the index of a bound value is an expression over the
                # item list rather than a number the generator can compute.
                items_expr = items_expression(items)
                expression = SjuiTools::SwiftUI::Binding::BindingExpression
                parsed = expression.parse(selected_declaration[2..-2])
                prop = parsed.path
                if parsed.default_kind == :none && !parsed.negated && expression.emittable_path?(prop)
                  # A bound selectedItem / selectedValue is declared two-way: the
                  # item's index, read through the items so the box follows the
                  # data, and the picked item written back. As a one-time
                  # `selectedIndex` it was neither (ticket
                  # selectbox-selected-item-binding-is-read-once).
                  # The read is the same expression the seed used (it knows the
                  # property's optionality: `(data.x ?? "")` for a String?).
                  add_line "selectedIndexBinding: SwiftUI.Binding(get: { #{items_expr}.firstIndex(of: #{selected_expr}) ?? -1 }, " \
                           "set: { index in data.#{prop} = #{items_expr}.indices.contains(index) ? #{items_expr}[index] : \"\" }),"
                else
                  # A default (`?? …`) or a negation: a value to read, nothing
                  # to write back to.
                  add_line "selectedIndex: #{items_expr}.firstIndex(of: #{selected_expr}),"
                end
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

            # A normal picker reports the pick through the same closure, after
            # SelectBoxView has written the selection: onValueChange, with what
            # its declared parameters ask for (pick_invocation) — then the
            # declared onClick. Last, as the
            # parameter is. The bound selection was observed with
            # `.onChange(of:)` instead, which ran after the click and for the
            # view model's writes too, and an unbound one was reported by
            # nothing.
            if selectItemType != 'Date'
              calls = []
              handler = @component['onValueChange']
              if handler && is_binding?(handler)
                index_prop = extract_binding_property(@component['selectedIndex']) if is_binding?(@component['selectedIndex'])
                index_expr = index_prop ? "data.#{index_prop}" : "(#{items_expression(items)}.firstIndex(of: newValue) ?? -1)"
                calls << pick_invocation(handler, id, index_expr, index_bound: !index_prop.nil?)
              end
              calls << click if click
              if calls.any?
                @generated_code[-1] = "#{@generated_code[-1]}," unless @generated_code[-1].rstrip.end_with?(',', '(')
                add_line "onValueChange: { newValue in #{calls.join('; ')} }"
              end
            end
          end
          add_line ")"

          # SelectBoxView handles padding/background/cornerRadius internally
          # Only apply frame, border, and margins here
          # Corresponding to Dynamic mode: SelectBoxConverter.swift

          # onValueChange is the pick's (the closure above), not an
          # `.onChange(of:)` on the bound value: that one ran after the click,
          # for the view model's writes too, and — for a date, whose closure
          # already reported the pick — a second time.

          # Apply frame modifiers
          apply_frame_constraints
          apply_frame_size

          # Note: padding, background and cornerRadius are handled internally by SelectBoxView

          # Apply border (after component's internal cornerRadius)
          if (border_code = border_overlay(8))
            @modifier_bag.register(:border, border_code)
          end

          # Apply margins (external spacing)
          apply_margins
          # opacity / shadow / clipToBounds / offset / hidden, as apply_modifiers
          # draws them for every other type.
          apply_common_decorations

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

          # enabled (`.disabled`, outermost) and userInteractionEnabled. Only
          # the flag was registered (with touchDisabledState, which SwiftUI no
          # longer reads — UIKit's hit-test mode): SelectBoxView
          # takes no `enabled`, so `enabled: false` still opened the picker and
          # took a pick (SwiftJsonUI ConformanceHost OnClickProbeUITests).
          register_interaction_gates

          generated_code
        end

        private

        # onValueChange's call for a pick, by the parameters the data declares
        # for it (4f's ruling on control-onclick-is-called-differently-on-every-
        # path, 1.9.0): one String — the picked item (`newValue`, the item
        # SelectBoxView reports), even with selectedIndex bound; one Int — the
        # item's index; a String then an Int — the viewId and the index; two
        # Strings — the viewId and the item; none — no argument. The index is
        # the bound selectedIndex, else the item's place in `items`; a date has
        # none, and a handler declared to take one — `(Int)`, `(String, Int)` —
        # is not called: an `// ERROR:` comment keeps its place, and the build
        # says it (BindingValidatorCore.date_pick_handler_problem; 4f's ruling,
        # 1.9.0). It was handed the date string for its Int, which does not
        # compile. Any other declaration (an Event type, none at all) keeps the
        # generic reading: the viewId where it takes one, and the index where
        # selectedIndex is bound, else the item. It was the generic reading
        # for every type, whose `(String` pattern also caught a lone String: a
        # `((String) -> Void)?` handler was handed the viewId and the index —
        # two arguments to a one-argument closure, which does not compile.
        def pick_invocation(handler, id, index_expr, index_bound: false)
          name = extract_binding_property(handler) || handler
          klass = ColorHelper.data_definitions.dig(name, 'class').to_s
          if index_expr.nil? && (problem = JsonUIShared::BindingValidatorCore.date_pick_handler_problem(klass))
            return "// ERROR: SelectBox.onValueChange #{name} is not called: #{problem}"
          end

          viewid = swift_string_literal(id.to_s)
          case JsonUIShared::BindingValidatorCore.closure_parameters(klass)
          when ['String'] then "data.#{name}?(newValue)"
          when ['Int'] then "data.#{name}?(#{index_expr})"
          when %w[String Int] then "data.#{name}?(#{viewid}, #{index_expr})"
          when %w[String String] then "data.#{name}?(#{viewid}, newValue)"
          when [] then "data.#{name}?()"
          else generic_pick(handler, id, index_expr, index_bound)
          end
        end

        def generic_pick(handler, id, index_expr, index_bound)
          get_event_handler_invocation(handler, id, index_bound ? index_expr : 'newValue')
        end

        # The declared selection. `selectedItem` and `selectedValue` are the
        # same two-way selection under two spellings, and `selectedItem`
        # wins — the precedence kjui's SelectBox has taken since it was
        # written (`selectbox_component.rb:27`, `selectedItem` tested before
        # `selectedValue`). Only `selectedValue` was read here, so a layout
        # that used the other spelling opened the picker with nothing
        # selected, in both its literal and its bound form
        # (`jui conformance codegen-effect`: SelectBox.selectedItem C0 and C1
        # on ios).
        def selected_declaration
          @component['selectedItem'] || @component['selectedValue']
        end

        # `SelectBoxView.CaretAttributes(...)` from the declared object. Only
        # the declared keys are named, so the view's defaults (nil → glyph
        # size / gray / clear / 0) fill the rest, exactly as they do for the
        # dynamic path. Colours go through the same resolver as every other
        # colour here, so the `@color/…` spelling and bound colours work.
        def caret_literal(attrs)
          args = []
          args << "src: \"#{attrs['src']}\"" if attrs['src']
          args << "width: #{attrs['width']}" if attrs['width']
          args << "height: #{attrs['height']}" if attrs['height']
          args << "tintColor: #{get_swiftui_color(attrs['tintColor'])}" if attrs['tintColor']
          args << "background: #{get_swiftui_color(attrs['background'])}" if attrs['background']
          args << "rightMargin: #{attrs['rightMargin']}" if attrs['rightMargin']
          "SelectBoxView.CaretAttributes(#{args.join(', ')})"
        end

        # The item list as a Swift expression, for the lookups that have to
        # index into it at run time.
        def items_expression(items)
          if items.is_a?(String) && bound_value?(items)
            "Array(data.#{extract_binding_property(items)})"
          elsif items.is_a?(Array)
            "[#{items.map { |item| swift_string_literal(item) }.join(', ')}]"
          else
            '[String]()'
          end
        end

        # One date bound, parsed with the format the picker uses. A binding
        # supplies the string at run time; the parse and the fallback are
        # identical either way.
        def date_operand(value)
          text = bound_string(value) || swift_string_literal(value)
          "#{text}.toDate(format: \"yyyy-MM-dd\") ?? Date()"
        end
      end
    end
  end
end
