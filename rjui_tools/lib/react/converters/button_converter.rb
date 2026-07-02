# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class ButtonConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          on_click = build_on_click
          disabled_attr = build_disabled_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          # Check if we need partialAttributes rendering (styled text spans)
          jsx = if attributes['partialAttributes'] && attributes['partialAttributes'].is_a?(Array) && !attributes['partialAttributes'].empty?
            render_partial_attributes_button(indent, id_attr, class_name, style_attr, on_click, disabled_attr, testid_attr, tag_attr)
          else
            text = convert_binding(attributes['text'] || '')

            # If href is specified, wrap with Next.js Link
            if attributes['href']
              href = attributes['href']
              "#{indent_str(indent)}<Link href=\"#{href}\"><button#{id_attr} className=\"#{class_name}\"#{style_attr}#{on_click}#{disabled_attr}#{testid_attr}#{tag_attr}>#{text}</button></Link>"
            else
              "#{indent_str(indent)}<button#{id_attr} className=\"#{class_name}\"#{style_attr}#{on_click}#{disabled_attr}#{testid_attr}#{tag_attr}>#{text}</button>"
            end
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Default button styles
          classes << 'cursor-pointer'
          classes << 'transition-colors'

          # Hover state (tapBackground; highlightBackground is the
          # definitions alias of tapBackground for Button — alias +
          # normalized handling is inside TypedAttributes)
          tap_background = attributes['tapBackground']
          if tap_background
            hover_color = TailwindMapper.map_color(tap_background, 'hover:bg')
            classes << hover_color
          else
            classes << 'hover:opacity-80'
          end

          # Active/pressed state
          if tap_background
            active_color = TailwindMapper.map_color(tap_background, 'active:bg')
            classes << active_color
          end

          # Highlight text color on hover (hilightColor is the legacy
          # definitions alias of highlightColor)
          highlight_color = attributes['highlightColor']
          if highlight_color
            hover_text = TailwindMapper.map_color(highlight_color, 'hover:text')
            classes << hover_text
          end

          # Disabled state
          if attributes['disabledBackground']
            disabled_bg = TailwindMapper.map_color(attributes['disabledBackground'], 'disabled:bg')
            classes << disabled_bg
          else
            classes << 'disabled:opacity-50'
          end

          if attributes['disabledFontColor']
            disabled_text = TailwindMapper.map_color(attributes['disabledFontColor'], 'disabled:text')
            classes << disabled_text
          end

          classes << 'disabled:cursor-not-allowed'

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_style_attr
          super

          # Corner radius
          if attributes['cornerRadius']
            @dynamic_styles['borderRadius'] = "'#{attributes['cornerRadius']}px'"
          end

          return '' if @dynamic_styles.nil? || @dynamic_styles.empty?

          # Delegate per-entry rendering to BaseConverter so the SPREAD
          # sentinel (Configuration.Font.resolve(...) emission) is handled
          # consistently across every converter.
          style_pairs = @dynamic_styles.map do |key, value|
            format_dynamic_style_pair(key, value)
          end

          " style={{ #{style_pairs.join(', ')} }}"
        end

        def build_on_click
          build_onclick_attr
        end

        def build_disabled_attr
          enabled = attributes['enabled']
          return '' if enabled.nil?

          if enabled.is_a?(String) && enabled.start_with?('@{') && enabled.end_with?('}')
            # Binding expression: @{isEnabled} -> disabled={data.isEnabled !== "true"}
            property_name = enabled[2...-1]
            " disabled={data.#{property_name} !== \"true\"}"
          elsif enabled == false
            ' disabled'
          else
            ''
          end
        end

        private

        # Render button with partial attributes (styled spans within text)
        def render_partial_attributes_button(indent, id_attr, class_name, style_attr, on_click, disabled_attr, testid_attr, tag_attr)
          text = attributes['text'] || ''
          partials = attributes['partialAttributes']

          lines = []
          lines << "#{indent_str(indent)}<button#{id_attr} className=\"#{class_name}\"#{style_attr}#{on_click}#{disabled_attr}#{testid_attr}#{tag_attr}>"

          # Sort partials by range start position
          sorted_partials = partials.select { |p| p['range'].is_a?(Array) }.sort_by { |p| p['range'][0] }

          current_pos = 0
          sorted_partials.each do |partial|
            range_start = partial['range'][0]
            range_end = partial['range'][1]

            # Add text before this partial
            if current_pos < range_start
              before_text = text[current_pos...range_start]
              lines << "#{indent_str(indent + 2)}#{escape_jsx_text(before_text)}"
            end

            # Add the styled span
            partial_text = text[range_start...range_end]
            partial_style = build_partial_style(partial)
            partial_class = build_partial_class(partial)
            partial_onclick = partial['onclick'] ? " onClick={#{partial['onclick']}}" : ''

            class_attr = partial_class.empty? ? '' : " className=\"#{partial_class}\""
            style_inline = partial_style.empty? ? '' : " style={{ #{partial_style} }}"

            lines << "#{indent_str(indent + 2)}<span#{class_attr}#{style_inline}#{partial_onclick}>#{escape_jsx_text(partial_text)}</span>"

            current_pos = range_end
          end

          # Add remaining text after last partial
          if current_pos < text.length
            remaining_text = text[current_pos..]
            lines << "#{indent_str(indent + 2)}#{escape_jsx_text(remaining_text)}"
          end

          lines << "#{indent_str(indent)}</button>"
          lines.join("\n")
        end

        def build_partial_style(partial)
          styles = []
          styles << "color: '#{partial['fontColor']}'" if partial['fontColor']
          styles << "fontSize: '#{partial['fontSize']}px'" if partial['fontSize']
          styles << "fontWeight: '#{partial['fontWeight']}'" if partial['fontWeight']
          styles << "backgroundColor: '#{partial['background']}'" if partial['background']
          styles.join(', ')
        end

        def build_partial_class(partial)
          classes = []
          classes << 'underline' if partial['underline']
          classes << 'line-through' if partial['strikethrough']
          classes << 'cursor-pointer' if partial['onclick']
          classes.join(' ')
        end

        def escape_jsx_text(text)
          return text unless text.is_a?(String)
          return text unless text.include?('{') || text.include?('}') || text.include?('<') || text.include?('>')

          escaped = text.gsub('`', '\\`').gsub('${', '\\${')
          "{`#{escaped}`}"
        end
      end
    end
  end
end
