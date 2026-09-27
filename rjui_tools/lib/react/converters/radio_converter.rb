# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class RadioConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          # In the single-radio shape the gap-bearing <label> IS the subtree
          # root, so a bound `spacing` has to reach @dynamic_styles BEFORE the
          # root's style attribute is rendered. Emitting a second style={{…}}
          # on the same tag would be a duplicate JSX attribute (TS17001) —
          # the Fx0375 shape SliderConverter documents. The group shape puts
          # the gap on inner labels the root's style cannot reach, and those
          # carry their own (see item_gap_parts).
          @root_gap_class = root_item_gap_class unless radio_group?
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          text = attributes['text'] || attributes['label'] || ''
          group = attributes['group'] || extract_id || 'radioGroup'

          jsx = if radio_group?
            generate_radio_group(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, literal_items, group, text)
          else
            generate_single_radio(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, group, text)
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          classes << 'flex flex-col gap-2' if radio_group?
          classes << 'cursor-pointer'

          # Disabled state
          if attributes['enabled'] == false
            classes << 'opacity-50 cursor-not-allowed'
          elsif has_binding?(attributes['enabled'])
            binding_expr = extract_binding_property(attributes['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50 cursor-not-allowed' : ''}"
          end

          finalize_classes(classes)
        end

        private

        # `items` is declared ["array", "binding"]: an array is the options,
        # written out one by one; a binding is a list the data holds, mapped
        # at render time — what KotlinJsonUI's dynamic renderer does with it.
        # Until 1.9.0 a bound `items` raised NoMethodError (`any?` on a
        # String) and took the build down (ticket
        # kjui-codegen-table-crashes-on-an-items-array).
        def bound_items
          items = attributes['items']
          items.is_a?(String) && has_binding?(items) ? extract_binding_property(items) : nil
        end

        def literal_items
          attributes['items'].is_a?(Array) ? attributes['items'] : []
        end

        def radio_group?
          !bound_items.nil? || literal_items.any?
        end

        def generate_radio_group(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, items, group, label_text)
          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          tint_color = attributes['tintColor']

          gap, gap_style = item_gap_parts
          input_style = tint_color ? " style={{ accentColor: #{color_style_expr(tint_color)} }}" : ''
          items_jsx = items.map do |item|
            state_attrs = build_state_attrs(selected_binding, on_change, item)
            <<~JSX.chomp
              #{indent_str(indent + 2)}<label className="flex items-center #{gap} cursor-pointer"#{gap_style}>
              #{indent_str(indent + 4)}<input type="radio" name="#{group}"#{jsx_attr_text('value', item)}#{state_attrs}#{disabled_attr}#{input_style} />
              #{indent_str(indent + 4)}<span>#{JsonUIShared::StringLiterals.jsx_text(item)}</span>
              #{indent_str(indent + 2)}</label>
            JSX
          end.join("\n")
          if bound_items
            # The one option, for each item the data holds.
            state_attrs = build_state_attrs(selected_binding, on_change, nil, expr: 'item')
            items_jsx = <<~JSX.chomp
              #{indent_str(indent + 2)}{#{bound_items}.map((item) => (
              #{indent_str(indent + 4)}<label key={item} className="flex items-center #{gap} cursor-pointer"#{gap_style}>
              #{indent_str(indent + 6)}<input type="radio" name="#{group}" value={item}#{state_attrs}#{disabled_attr}#{input_style} />
              #{indent_str(indent + 6)}<span>{item}</span>
              #{indent_str(indent + 4)}</label>
              #{indent_str(indent + 2)}))}
            JSX
          end

          label_jsx = if label_text && !label_text.empty?
                        "#{indent_str(indent + 2)}<span className=\"font-medium\">#{convert_text_binding(label_text)}</span>\n"
                      else
                        ''
                      end

          <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
            #{label_jsx}#{items_jsx}
            #{indent_str(indent)}</div>
          JSX
        end

        def generate_single_radio(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, group, text)
          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          # `value` is the option's identity within the group and the node id is
          # only the fallback (sjui radio_converter reads the same order). Taking
          # the id unconditionally compared selectedValue against the node name,
          # so a single Radio could never be checked no matter what was declared
          # — the host's tsc caught it as a comparison of non-overlapping
          # literals.
          radio_value = attributes['value'] || extract_id || 'option'
          tint_color = attributes['tintColor']
          input_style = tint_color ? " style={{ accentColor: #{color_style_expr(tint_color)} }}" : ''

          state_attrs = build_state_attrs(selected_binding, on_change, radio_value)
          # With no group selection the radio's own `checked` is its state,
          # whatever handler it also has. It used to stand in only for an
          # EMPTY state, so the handler an onValueChange writes, and from
          # bae96913 the one a declared onClick writes, took its place: a radio
          # declared checked started unchecked the moment it had either.
          state_attrs = "#{checked_attr(operated: !state_attrs.empty?)}#{state_attrs}" unless selected_binding

          # Custom icon radio: hidden input + state-swapped images (the kjui/
          # sjui icon path — 33 cross-effect: web rendered the native circle
          # for declared icons). 'selected_icon' is the declared snake alias.
          icon_off = attributes['icon']
          icon_on = attributes['selectedIcon'] || attributes['selected_icon']
          if icon_on || icon_off
            off_src = icon_off || icon_on
            on_src = icon_on || icon_off
            control_jsx =
              "<input type=\"radio\" name=\"#{group}\"#{jsx_attr_text('value', radio_value)}#{state_attrs}#{disabled_attr} className=\"peer sr-only\" />"               "<img#{jsx_attr_text('src', off_src)} alt=\"\" className=\"w-6 h-6 peer-checked:hidden\" />"               "<img#{jsx_attr_text('src', on_src)} alt=\"\" className=\"w-6 h-6 hidden peer-checked:block\" />"
            return <<~JSX.chomp
              #{indent_str(indent)}<label#{id_attr} className="#{class_name} flex items-center #{@root_gap_class}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
              #{indent_str(indent + 2)}#{control_jsx}
              #{indent_str(indent + 2)}<span>#{convert_text_binding(text)}</span>
              #{indent_str(indent)}</label>
            JSX
          end

          <<~JSX.chomp
            #{indent_str(indent)}<label#{id_attr} className="#{class_name} flex items-center #{@root_gap_class}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
            #{indent_str(indent + 2)}<input type="radio" name="#{group}"#{jsx_attr_text('value', radio_value)}#{state_attrs}#{disabled_attr}#{input_style} />
            #{indent_str(indent + 2)}<span>#{convert_text_binding(text)}</span>
            #{indent_str(indent)}</label>
          JSX
        end

        # `spacing` — the gap between the radio control and its label text
        # (kjui reads the same attribute for the row arrangement). Default
        # keeps the historical gap-2 (8px).
        # Root-label shape. A bound value has no place in an arbitrary-value
        # class — it produced `gap-[@{v}px]`, which matches nothing — so it
        # folds into the root's own inline `gap` and the class falls back to
        # the historical default.
        def root_item_gap_class
          spacing = bound_length_style('gap', attributes['spacing'])
          spacing ? "gap-[#{spacing}px]" : 'gap-2'
        end

        # Inner-label shape: [class, style attribute]. The root's style
        # cannot reach these labels, so a bound gap becomes theirs.
        def item_gap_parts
          spacing = attributes['spacing']
          return [spacing ? "gap-[#{spacing}px]" : 'gap-2', ''] unless (expr = bound_value_expr(spacing))

          ['gap-2', style_attr_for({ 'gap' => "`${#{expr}}px`" })]
        end

        # A single radio with no group selection still honours `checked` —
        # the effect check measured the generated input carrying no checked
        # state at all (the fixture rendered identically to its control).
        # Same shape as ToggleConverter: literal -> defaultChecked,
        # binding -> controlled checked, `readOnly` only where no handler
        # (`operated`) answers the change.
        def checked_attr(operated: false)
          checked = attributes['checked']
          return '' if checked.nil? || checked == false

          if has_binding?(checked)
            " checked={#{extract_binding_property(checked)}}#{operated ? '' : ' readOnly'}"
          else
            ' defaultChecked'
          end
        end

        # Selected-state expression for the radio input.
        # - `selectedValue: "@{prop}"`  -> JS expression (data-prefixed property)
        # - `selectedValue: "Static"`  -> quoted string literal
        # - absent                      -> nil (uncontrolled input; the old code
        #   emitted a bare `selectedValue` identifier which is undefined at
        #   runtime and crashed the component on render)
        def build_selected_binding
          selected = attributes['selectedValue']
          return nil unless selected

          if has_binding?(selected)
            extract_binding_property(selected)
          else
            JsonUIShared::StringLiterals.ts(selected)
          end
        end

        # onChange handler expression, or nil when neither onValueChange nor a
        # selectedValue binding provides one (static/uncontrolled radio).
        def build_on_change
          handler = attributes['onValueChange']

          if handler && has_binding?(handler)
            extract_binding_property(handler)
          else
            # Generate setter from the raw binding name (without viewModel.data. prefix)
            selected = attributes['selectedValue']
            return nil unless selected && has_binding?(selected)

            raw_binding = extract_raw_binding_property(selected)
            setter_name = "set#{raw_binding[0].upcase}#{raw_binding[1..]}"
            add_viewmodel_data_prefix(setter_name)
          end
        end

        # checked / onChange attribute pair. Controlled inputs need onChange
        # (or readOnly) to satisfy React; static selections emit readOnly.
        # Data closure props are always optional (type_converter makes all
        # function types `| undefined`), so calls must be optional-chained.
        # The literal `selectedValue` behind a `build_selected_binding` result,
        # or nil when that result was a binding expression (`data.x`, unquoted).
        def static_selected_value(selected_binding)
          selected_binding[/\A"(.*)"\z/m, 1]
        end

        # `expr`: the option is a runtime value (a bound `items`), so there is
        # no literal to answer the comparison with at codegen time.
        def build_state_attrs(selected_binding, on_change, value, expr: nil)
          value_literal = expr || JsonUIShared::StringLiterals.ts(value)
          if selected_binding
            # A STATIC `selectedValue` never reaches a comparison: with a
            # literal on both sides TypeScript narrows each to its own literal
            # type, so `"Beta" === "Alpha"` is TS2367 inside an @generated file
            # no consumer can patch. It seeds instead (below). Only the BOUND
            # form compares, and there the left side is a runtime value with no
            # literal type to narrow.
            static_selected = static_selected_value(selected_binding)
            if static_selected
              # A static selection is where the group starts, and the user
              # changes it (ticket static-valued-controls-do-not-change-on-a-
              # users-tap): an uncontrolled `defaultChecked` on the item it
              # names — `checked` + readOnly held the group still.
              # A bound list's option is a runtime value, so its seed compares
              # at run time — there is no literal to answer with here, and
              # leaving it out started the group with nothing chosen.
              seed =
                if expr
                  " defaultChecked={#{selected_binding} === #{expr}}"
                else
                  chosen = static_selected == (value.is_a?(String) ? JsonUIShared::StringLiterals.ts_body(value) : value)
                  chosen ? ' defaultChecked' : ''
                end
              return "#{seed}#{operation_attr('onChange', '()', on_change && "#{on_change}?.(#{value_literal})")}"
            end
            # A bound selection: the static one returned above. (The branch
            # that answered a static selection here, `checked={true}` /
            # `{false}`, was unreachable after that return — 6750135d — and
            # is gone.)
            checked = " checked={#{selected_binding} === #{value_literal}}"
            if on_change || operation_click_call
              "#{checked}#{operation_attr('onChange', '()', on_change && "#{on_change}?.(#{value_literal})")}"
            else
              "#{checked} readOnly"
            end
          else
            # The selection is the operation a declared onClick follows.
            operation_attr('onChange', '()', on_change && "#{on_change}?.(#{value_literal})")
          end
        end

        def build_disabled_attr
          enabled = attributes['enabled']
          return '' if enabled.nil?

          if has_binding?(enabled)
            " disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' disabled'
          else
            ''
          end
        end
      end
    end
  end
end
