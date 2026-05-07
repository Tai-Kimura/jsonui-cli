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
          items = json['items'] || []
          text = json['text'] || ''
          group = json['group'] || extract_id || 'radioGroup'

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

          classes << 'flex flex-col gap-2' if (json['items'] || []).any?
          classes << 'cursor-pointer'

          # Disabled state
          if json['enabled'] == false
            classes << 'opacity-50 cursor-not-allowed'
          elsif has_binding?(json['enabled'])
            binding_expr = extract_binding_property(json['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50 cursor-not-allowed' : ''}"
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        private

        def generate_radio_group(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, items, group, label_text)
          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          tint_color = json['tintColor']

          items_jsx = items.map do |item|
            escaped_item = item.gsub('"', '&quot;')
            input_style = tint_color ? " style={{ accentColor: '#{tint_color}' }}" : ''
            <<~JSX.chomp
              #{indent_str(indent + 2)}<label className="flex items-center gap-2 cursor-pointer">
              #{indent_str(indent + 4)}<input type="radio" name="#{group}" value="#{escaped_item}" checked={#{selected_binding} === "#{escaped_item}"} onChange={() => #{on_change}("#{escaped_item}")}#{disabled_attr}#{input_style} />
              #{indent_str(indent + 4)}<span>#{item}</span>
              #{indent_str(indent + 2)}</label>
            JSX
          end.join("\n")

          label_jsx = if label_text && !label_text.empty?
                        "#{indent_str(indent + 2)}<span className=\"font-medium\">#{convert_binding(label_text)}</span>\n"
                      else
                        ''
                      end

          <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}>
            #{label_jsx}#{items_jsx}
            #{indent_str(indent)}</div>
          JSX
        end

        def generate_single_radio(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, group, text)
          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr
          radio_value = extract_id || 'option'
          tint_color = json['tintColor']
          input_style = tint_color ? " style={{ accentColor: '#{tint_color}' }}" : ''

          <<~JSX.chomp
            #{indent_str(indent)}<label#{id_attr} className="#{class_name} flex items-center gap-2"#{style_attr}#{testid_attr}#{tag_attr}>
            #{indent_str(indent + 2)}<input type="radio" name="#{group}" value="#{radio_value}" checked={#{selected_binding} === "#{radio_value}"} onChange={() => #{on_change}("#{radio_value}")}#{disabled_attr}#{input_style} />
            #{indent_str(indent + 2)}<span>#{convert_binding(text)}</span>
            #{indent_str(indent)}</label>
          JSX
        end

        def build_selected_binding
          selected = json['selectedValue']

          if selected && has_binding?(selected)
            extract_binding_property(selected)
          else
            'selectedValue'
          end
        end

        def build_on_change
          handler = json['onValueChange']

          if handler && has_binding?(handler)
            extract_binding_property(handler)
          else
            # Generate setter from the raw binding name (without viewModel.data. prefix)
            selected = json['selectedValue']
            raw_binding = if selected && has_binding?(selected)
                            extract_raw_binding_property(selected)
                          else
                            'selectedValue'
                          end
            setter_name = "set#{raw_binding[0].upcase}#{raw_binding[1..]}"
            add_viewmodel_data_prefix(setter_name)
          end
        end

        def build_disabled_attr
          enabled = json['enabled']
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
