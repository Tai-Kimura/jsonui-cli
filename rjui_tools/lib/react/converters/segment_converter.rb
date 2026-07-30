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
          items = attributes['items'] || []

          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr

          items_jsx = items.each_with_index.map do |item, index|
            button_class = build_button_class(index)
            button_disabled = attributes['enabled'] == false ? ' disabled' : ''
            # Data closure props are always optional (type_converter makes all
            # function types `| undefined`), so the call must be optional-chained.
            on_click_attr = on_change ? " onClick={() => #{on_change}?.(#{index})}" : ''
            # Item labels go through the same string resolution as Label.text
            # (string key -> binding -> literal), matching sjui's per-item
            # get_text_with_string_manager.
            "#{indent_str(indent + 2)}<button key={#{index}}#{segment_item_id_attr(index)} className={`#{button_class}`}#{on_click_attr}#{button_disabled}>#{convert_text_binding(item)}</button>"
          end.join("\n")

          # `disabled` is not a valid attribute on <div>; reflect the state via
          # aria-disabled (each inner <button> carries the real disabled attr).
          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
            #{items_jsx}
            #{indent_str(indent)}</div>
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        # Per-button DOM id following the TabView `{id}_tab_{index}` naming
        # contract that the web test driver's selectTab action resolves.
        # Literal ids only — a bound id has no static value to interpolate.
        def segment_item_id_attr(index)
          seg_id = extract_id
          return '' if seg_id.nil? || has_binding?(seg_id)

          " id=\"#{seg_id}_tab_#{index}\""
        end

        def build_class_name
          classes = [super]

          classes << 'w-full'
          classes << 'flex'
          classes << 'rounded-lg'

          # Background color
          bg_color = attributes['backgroundColor']
          if bg_color
            classes << TailwindMapper.map_color(bg_color, 'bg')
          else
            classes << 'bg-gray-100'
          end

          classes << 'p-1'

          # Disabled state
          if attributes['enabled'] == false
            classes << 'opacity-50'
          elsif has_binding?(attributes['enabled'])
            binding_expr = extract_binding_property(attributes['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50' : ''}"
          end

          finalize_classes(classes)
        end

        def build_button_class(index)
          selected_index = with_bind_fallback(attributes['selectedIndex'] || attributes['selectedTabIndex']) || 0

          # Build font size class
          font_size_class = if attributes['fontSize']
            TailwindMapper.map_font_size(attributes['fontSize'])
          else
            'text-sm'
          end

          # Build padding class
          # height may be a keyword ("wrapContent" / "matchParent") — only a
          # numeric height can be translated into vertical padding.
          padding_class = if attributes['height'].is_a?(Numeric)
            "py-#{TailwindMapper::PADDING_MAP[attributes['height'] / 4] || (attributes['height'] / 4)}"
          else
            'py-2'
          end

          # Font color
          font_color = attributes['fontColor']
          font_color_class = font_color ? TailwindMapper.map_color(font_color, 'text') : 'text-gray-900'

          # Selected colors
          selected_bg = attributes['selectedBackground'] || 'bg-white'
          selected_text = attributes['selectedFontColor'] ? TailwindMapper.map_color(attributes['selectedFontColor'], 'text') : font_color_class

          base_classes = "flex-1 px-4 #{padding_class} #{font_size_class} font-medium rounded-md transition-colors cursor-pointer"
          disabled_class = attributes['enabled'] == false ? ' cursor-not-allowed' : ''

          if has_binding?(selected_index)
            prop = extract_binding_property(selected_index)
            "#{base_classes}#{disabled_class} ${#{prop} === #{index} ? '#{selected_bg} #{selected_text} shadow' : 'text-gray-500 hover:text-gray-700'}"
          else
            # Static selectedIndex — resolve the selected state at generation
            # time (the old code emitted a bare `selectedIndex` identifier,
            # which is undefined at runtime and crashed the component).
            selected_classes = if selected_index.to_i == index
                                 "#{selected_bg} #{selected_text} shadow"
                               else
                                 'text-gray-500 hover:text-gray-700'
                               end
            "#{base_classes}#{disabled_class} #{selected_classes}"
          end
        end

        def build_selected_binding
          selected = with_bind_fallback(attributes['selectedIndex'] || attributes['selectedTabIndex'])

          if selected && has_binding?(selected)
            extract_binding_property(selected)
          else
            selected || 0
          end
        end

        # onChange handler expression, or nil when neither onValueChange nor a
        # selectedIndex binding provides one (static segment).
        def build_on_change
          handler = attributes['onValueChange']

          if handler && has_binding?(handler)
            extract_binding_property(handler)
          else
            # Generate setter from the raw binding name (without viewModel.data. prefix)
            selected = with_bind_fallback(attributes['selectedIndex'] || attributes['selectedTabIndex'])
            return nil unless selected && has_binding?(selected)

            raw_binding = extract_raw_binding_property(selected)
            setter_name = "set#{raw_binding[0].upcase}#{raw_binding[1..]}"
            add_viewmodel_data_prefix(setter_name)
          end
        end

        def build_disabled_attr
          enabled = attributes['enabled']
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
