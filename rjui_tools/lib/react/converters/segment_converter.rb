# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class SegmentConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          items = json['items'] || []

          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr

          items_jsx = items.each_with_index.map do |item, index|
            button_class = build_button_class(index)
            button_disabled = json['enabled'] == false ? ' disabled' : ''
            "#{indent_str(indent + 2)}<button key={#{index}} className={`#{button_class}`} onClick={() => #{on_change}(#{index})}#{button_disabled}>#{item}</button>"
          end.join("\n")

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}#{disabled_attr}>
            #{items_jsx}
            #{indent_str(indent)}</div>
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          classes << 'w-full'
          classes << 'flex'
          classes << 'rounded-lg'

          # Background color
          bg_color = json['backgroundColor']
          if bg_color
            classes << TailwindMapper.map_color(bg_color, 'bg')
          else
            classes << 'bg-gray-100'
          end

          classes << 'p-1'

          # Disabled state
          if json['enabled'] == false
            classes << 'opacity-50'
          elsif has_binding?(json['enabled'])
            binding_expr = extract_binding_property(json['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50' : ''}"
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_button_class(index)
          selected_index = json['selectedIndex'] || json['selectedTabIndex'] || 0

          # Build font size class
          font_size_class = if json['fontSize']
            TailwindMapper.map_font_size(json['fontSize'])
          else
            'text-sm'
          end

          # Build padding class
          padding_class = if json['height']
            "py-#{TailwindMapper::PADDING_MAP[json['height'] / 4] || (json['height'] / 4)}"
          else
            'py-2'
          end

          # Font color
          font_color = json['fontColor']
          font_color_class = font_color ? TailwindMapper.map_color(font_color, 'text') : 'text-gray-900'

          # Selected colors
          selected_bg = json['selectedBackground'] || 'bg-white'
          selected_text = json['selectedFontColor'] ? TailwindMapper.map_color(json['selectedFontColor'], 'text') : font_color_class

          base_classes = "flex-1 px-4 #{padding_class} #{font_size_class} font-medium rounded-md transition-colors cursor-pointer"
          disabled_class = json['enabled'] == false ? ' cursor-not-allowed' : ''

          if has_binding?(selected_index)
            prop = extract_binding_property(selected_index)
            "#{base_classes}#{disabled_class} ${#{prop} === #{index} ? '#{selected_bg} #{selected_text} shadow' : 'text-gray-500 hover:text-gray-700'}"
          else
            "#{base_classes}#{disabled_class} ${selectedIndex === #{index} ? '#{selected_bg} #{selected_text} shadow' : 'text-gray-500 hover:text-gray-700'}"
          end
        end

        def build_selected_binding
          selected = json['selectedIndex'] || json['selectedTabIndex']

          if selected && has_binding?(selected)
            extract_binding_property(selected)
          else
            'selectedIndex'
          end
        end

        def build_on_change
          handler = json['onValueChange']

          if handler && has_binding?(handler)
            extract_binding_property(handler)
          else
            # Generate setter from the raw binding name (without viewModel.data. prefix)
            selected = json['selectedIndex'] || json['selectedTabIndex']
            raw_binding = if selected && has_binding?(selected)
                            extract_raw_binding_property(selected)
                          else
                            'selectedIndex'
                          end
            setter_name = "set#{raw_binding[0].upcase}#{raw_binding[1..]}"
            add_viewmodel_data_prefix(setter_name)
          end
        end

        def build_disabled_attr
          enabled = json['enabled']
          return '' if enabled.nil?

          if has_binding?(enabled)
            " data-disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' data-disabled="true"'
          else
            ''
          end
        end
      end
    end
  end
end
