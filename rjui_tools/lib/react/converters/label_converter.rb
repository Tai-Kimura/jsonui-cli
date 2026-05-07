# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class LabelConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          onclick_attr = build_onclick_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          # Check if we need partialAttributes rendering
          jsx = if json['partialAttributes'] && json['partialAttributes'].is_a?(Array) && !json['partialAttributes'].empty?
            render_partial_attributes(indent, id_attr, class_name, style_attr, onclick_attr, testid_attr, tag_attr)
          elsif json['linkable']
            render_linkable_text(indent, id_attr, class_name, style_attr, onclick_attr, testid_attr, tag_attr)
          else
            text = convert_binding(json['text'] || '')
            "#{indent_str(indent)}<span#{id_attr} className=\"#{class_name}\"#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr}>#{text}</span>"
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Vertical/horizontal alignment with flex
          # Default: vertically centered. gravity overrides vertical, textAlign overrides horizontal.
          classes << 'flex'
          if json['gravity']
            gravity_str = json['gravity'].is_a?(Array) ? json['gravity'].join('|') : json['gravity'].to_s
            if gravity_str.include?('top')
              classes << 'items-start'
            elsif gravity_str.include?('bottom')
              classes << 'items-end'
            else
              classes << 'items-center'
            end
          else
            classes << 'items-center'
          end

          # textAlign → justify-* for horizontal alignment within flex
          case json['textAlign']&.downcase
          when 'center'
            classes << 'justify-center'
          when 'right'
            classes << 'justify-end'
          when 'left'
            classes << 'justify-start'
          end

          # Line clamp for multiple lines
          if json['lines'] && json['lines'] > 0
            if json['lines'] == 1
              classes << 'truncate'
            else
              classes << "line-clamp-#{json['lines']}"
            end
          end

          # Underline
          classes << 'underline' if json['underline']

          # Strikethrough
          classes << 'line-through' if json['strikethrough']

          # Cursor pointer for clickable items
          classes << 'cursor-pointer' if json['onClick'] || json['onclick']

          # Linkable text
          classes << 'cursor-pointer' if json['linkable']

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_style_attr
          # Call parent to initialize @dynamic_styles
          super

          # Line spacing / line height
          if json['lineHeightMultiple']
            @dynamic_styles['lineHeight'] = json['lineHeightMultiple'].to_s
          elsif json['lineSpacing']
            # Convert lineSpacing (px) to lineHeight (em-ish)
            font_size = json['fontSize'] || 16
            line_height = ((font_size + json['lineSpacing'].to_f) / font_size).round(2)
            @dynamic_styles['lineHeight'] = line_height.to_s
          end

          # edgeInset (Label internal padding)
          if json['edgeInset']
            edge_inset = json['edgeInset']
            if edge_inset.is_a?(Array)
              case edge_inset.length
              when 1
                @dynamic_styles['padding'] = "'#{edge_inset[0]}px'"
              when 2
                @dynamic_styles['padding'] = "'#{edge_inset[0]}px #{edge_inset[1]}px'"
              when 3
                @dynamic_styles['padding'] = "'#{edge_inset[0]}px #{edge_inset[1]}px #{edge_inset[2]}px'"
              when 4
                @dynamic_styles['padding'] = "'#{edge_inset[0]}px #{edge_inset[1]}px #{edge_inset[2]}px #{edge_inset[3]}px'"
              end
            elsif edge_inset.is_a?(String) && edge_inset.include?('|')
              parts = edge_inset.split('|').map(&:to_i)
              @dynamic_styles['padding'] = "'#{parts.map { |p| "#{p}px" }.join(' ')}'"
            else
              @dynamic_styles['padding'] = "'#{edge_inset.to_i}px'"
            end
          end

          # Disabled font color
          if json['enabled'] == false && json['disabledFontColor']
            @dynamic_styles['color'] = "'#{json['disabledFontColor']}'"
          end

          # lineBreakMode (truncation)
          if json['lineBreakMode']
            case json['lineBreakMode']
            when 'Head'
              @dynamic_styles['textOverflow'] = "'ellipsis'"
              @dynamic_styles['direction'] = "'rtl'"
              @dynamic_styles['textAlign'] = "'left'"
            when 'Middle'
              # CSS doesn't support middle truncation natively
              # We'll use ellipsis as fallback
              @dynamic_styles['textOverflow'] = "'ellipsis'"
            when 'Tail', 'Clip'
              @dynamic_styles['textOverflow'] = "'ellipsis'"
            end
            @dynamic_styles['overflow'] = "'hidden'"
            @dynamic_styles['whiteSpace'] = "'nowrap'" unless json['lines'] && json['lines'] > 1
          end

          # autoShrink - use CSS font-size clamp or viewport units
          # This is a simplified version - full implementation would need JS
          if json['autoShrink']
            min_scale = json['minimumScaleFactor'] || 0.5
            font_size = json['fontSize'] || 16
            min_size = (font_size * min_scale).round
            # Use min() to allow shrinking but not below minimum
            @dynamic_styles['fontSize'] = "'min(#{font_size}px, max(#{min_size}px, 1vw))'"
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

        private

        # Render text with partial attributes (styled spans within text)
        def render_partial_attributes(indent, id_attr, class_name, style_attr, onclick_attr, testid_attr, tag_attr)
          text = json['text'] || ''
          partials = json['partialAttributes']

          # Build JSX with styled spans
          lines = []
          lines << "#{indent_str(indent)}<span#{id_attr} className=\"#{class_name}\"#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr}>"

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

          lines << "#{indent_str(indent)}</span>"
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

        # Render linkable text (auto-detect URLs and make them clickable)
        def render_linkable_text(indent, id_attr, class_name, style_attr, onclick_attr, testid_attr, tag_attr)
          text = json['text'] || ''

          # For React, we'll render with a data attribute and let the app handle link detection
          # Or use a simple regex-based approach
          lines = []
          lines << "#{indent_str(indent)}<span#{id_attr} className=\"#{class_name}\"#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr} data-linkable=\"true\">"

          # Simple URL detection
          url_regex = /(https?:\/\/[^\s]+)/
          parts = text.split(url_regex)

          parts.each do |part|
            if part.match?(url_regex)
              lines << "#{indent_str(indent + 2)}<a href=\"#{part}\" target=\"_blank\" rel=\"noopener noreferrer\" className=\"text-blue-500 underline\">#{part}</a>"
            else
              lines << "#{indent_str(indent + 2)}#{escape_jsx_text(part)}" unless part.empty?
            end
          end

          lines << "#{indent_str(indent)}</span>"
          lines.join("\n")
        end

        def escape_jsx_text(text)
          return text unless text.is_a?(String)
          return text unless text.include?('{') || text.include?('}') || text.include?('<') || text.include?('>')

          # Wrap in JSX expression with template literal for safe rendering
          escaped = text.gsub('`', '\\`').gsub('${', '\\${')
          "{`#{escaped}`}"
        end
      end
    end
  end
end
