# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class RadioConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          items = attributes['items'] || []
          text = attributes['text'] || ''
          group = attributes['group'] || extract_id || 'radioGroup'

          jsx = if items.any?
            generate_radio_group(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, items, group, text)
          else
            generate_single_radio(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, group, text)
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          classes << 'flex flex-col gap-2' if (attributes['items'] || []).any?
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

        def generate_radio_group(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, items, group, label_text)
          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          tint_color = attributes['tintColor']

          items_jsx = items.map do |item|
            escaped_item = item.gsub('"', '&quot;')
            input_style = tint_color ? " style={{ accentColor: '#{tint_color}' }}" : ''
            state_attrs = build_state_attrs(selected_binding, on_change, escaped_item)
            <<~JSX.chomp
              #{indent_str(indent + 2)}<label className="flex items-center gap-2 cursor-pointer">
              #{indent_str(indent + 4)}<input type="radio" name="#{group}" value="#{escaped_item}"#{state_attrs}#{disabled_attr}#{input_style} />
              #{indent_str(indent + 4)}<span>#{item}</span>
              #{indent_str(indent + 2)}</label>
            JSX
          end.join("\n")

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
          radio_value = extract_id || 'option'
          tint_color = attributes['tintColor']
          input_style = tint_color ? " style={{ accentColor: '#{tint_color}' }}" : ''

          state_attrs = build_state_attrs(selected_binding, on_change, radio_value)

          <<~JSX.chomp
            #{indent_str(indent)}<label#{id_attr} className="#{class_name} flex items-center gap-2"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
            #{indent_str(indent + 2)}<input type="radio" name="#{group}" value="#{radio_value}"#{state_attrs}#{disabled_attr}#{input_style} />
            #{indent_str(indent + 2)}<span>#{convert_text_binding(text)}</span>
            #{indent_str(indent)}</label>
          JSX
        end

        # Selected-state expression for the radio input.
        # - `selectedValue: "@{prop}"`  -> JS expression (data-prefixed property)
        # - `selectedValue: "Static"`  -> quoted string literal
        # - absent                      -> nil (uncontrolled input; the old code
        #   emitted a bare `selectedValue` identifier which is undefined at
        #   runtime and crashed the component on render)
        def build_selected_binding
          selected = with_bind_fallback(attributes['selectedValue'])
          return nil unless selected

          if has_binding?(selected)
            extract_binding_property(selected)
          else
            "\"#{selected.to_s.gsub('"', '&quot;')}\""
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
            selected = with_bind_fallback(attributes['selectedValue'])
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
        def build_state_attrs(selected_binding, on_change, value_literal)
          if selected_binding
            checked = " checked={#{selected_binding} === \"#{value_literal}\"}"
            if on_change
              "#{checked} onChange={() => #{on_change}?.(\"#{value_literal}\")}"
            else
              "#{checked} readOnly"
            end
          elsif on_change
            " onChange={() => #{on_change}?.(\"#{value_literal}\")}"
          else
            ''
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
