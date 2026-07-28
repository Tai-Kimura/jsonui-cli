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
          jsx = if partial_attributes_list
            render_partial_attributes(indent, id_attr, class_name, style_attr, onclick_attr, testid_attr, tag_attr)
          elsif attributes['linkable']
            render_linkable_text(indent, id_attr, class_name, style_attr, onclick_attr, testid_attr, tag_attr)
          else
            text = convert_text_binding(attributes['text'] || '')
            "#{indent_str(indent)}<span#{id_attr} className=\"#{class_name}\"#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr}>#{text}</span>"
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        # The partialAttributes entries, or nil when the label has none. One
        # definition so the render branch and the class builder can't disagree
        # about whether this label is multi-run.
        def partial_attributes_list
          partials = attributes['partialAttributes']
          return nil unless partials.is_a?(Array) && !partials.empty?

          partials
        end

        # True when the label renders as several sibling nodes rather than one
        # text node: partialText returns a node per run, and linkable splits
        # the text around each detected URL.
        def multi_run_text?
          !partial_attributes_list.nil? || !!attributes['linkable']
        end

        def build_class_name
          classes = [super]

          if multi_run_text?
            # partialText / linkable emit one node per run (text, span, text…).
            # As flex items every run becomes its own line box, so the whole
            # paragraph lays out as a single row and stops wrapping — the text
            # after a link shoots off past the column
            # (web-partial-labels-render-inside-a-flex-row). A multi-run label
            # is a paragraph and wants normal block flow; horizontal alignment
            # already arrives from textAlign as text-* via the base converter,
            # and vertical centering means nothing once the text wraps.
            classes << 'block'
          else
            # Vertical/horizontal alignment with flex
            # Default: vertically centered. gravity overrides vertical, textAlign overrides horizontal.
            classes << 'flex'
            if attributes['gravity']
              gravity_str = attributes['gravity'].is_a?(Array) ? attributes['gravity'].join('|') : attributes['gravity'].to_s
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
            case attributes['textAlign']&.downcase
            when 'center'
              classes << 'justify-center'
            when 'right'
              classes << 'justify-end'
            when 'left'
              classes << 'justify-start'
            end
          end

          # Line clamp for multiple lines
          if attributes['lines'] && attributes['lines'] > 0
            if attributes['lines'] == 1
              classes << 'truncate'
            else
              classes << "line-clamp-#{attributes['lines']}"
            end
          end

          # Underline
          classes << 'underline' if attributes['underline']

          # Strikethrough
          classes << 'line-through' if attributes['strikethrough']

          # Cursor pointer for clickable items
          classes << 'cursor-pointer' if attributes['onClick'] || attributes['onclick']

          # Linkable text
          classes << 'cursor-pointer' if attributes['linkable']

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_style_attr
          # Call parent to initialize @dynamic_styles
          super

          # Line spacing / line height
          if attributes['lineHeightMultiple']
            @dynamic_styles['lineHeight'] = attributes['lineHeightMultiple'].to_s
          elsif attributes['lineSpacing']
            # Convert lineSpacing (px) to lineHeight (em-ish)
            font_size = attributes['fontSize'] || 16
            line_height = ((font_size + attributes['lineSpacing'].to_f) / font_size).round(2)
            @dynamic_styles['lineHeight'] = line_height.to_s
          end

          # edgeInset (Label internal padding)
          if attributes['edgeInset']
            edge_inset = attributes['edgeInset']
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
          if attributes['enabled'] == false && attributes['disabledFontColor']
            @dynamic_styles['color'] = color_style_expr(attributes['disabledFontColor'])
          end

          # lineBreakMode (truncation)
          if attributes['lineBreakMode']
            case attributes['lineBreakMode']
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
            @dynamic_styles['whiteSpace'] = "'nowrap'" unless attributes['lines'] && attributes['lines'] > 1
          end

          # autoShrink - use CSS font-size clamp or viewport units
          # This is a simplified version - full implementation would need JS
          if attributes['autoShrink']
            min_scale = attributes['minimumScaleFactor'] || 0.5
            font_size = attributes['fontSize'] || 16
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

        # Render text with partial attributes.
        #
        # The partials are handed to the generated `partialText` helper and
        # applied at RUNTIME, against the resolved string. Slicing here at
        # build time could not support a pattern range or a localized text,
        # and iOS/Android have always done this at runtime.
        def render_partial_attributes(indent, id_attr, class_name, style_attr, onclick_attr, testid_attr, tag_attr)
          text_expr = text_runtime_expression(attributes['text'] || '')
          specs = build_partial_specs(attributes['partialAttributes'])

          lines = []
          lines << "#{indent_str(indent)}<span#{id_attr} className=\"#{class_name}\"#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr}>"
          lines << "#{indent_str(indent + 2)}{partialText(#{text_expr}, #{specs})}"
          lines << "#{indent_str(indent)}</span>"
          lines.join("\n")
        end

        # Colors are deliberately NOT emitted inline here: they go through
        # build_partial_class -> TailwindMapper.map_color, the same route the
        # main fontColor path takes. L1 normalization rewrites a palette hex
        # to its TOKEN name (#2563EB -> accent), and a token is not a CSS
        # color — `style: { color: 'accent' }` is silently ignored by the
        # browser, so the text simply came out unstyled.
        def build_partial_style(partial)
          styles = []
          styles << "fontSize: '#{partial['fontSize']}px'" if partial['fontSize']
          styles << "fontWeight: '#{partial['fontWeight']}'" if partial['fontWeight']
          styles.join(', ')
        end

        def build_partial_class(partial)
          classes = []
          # Same color resolution as the main fontColor / background path:
          # a palette TOKEN becomes a Tailwind class, an off-palette name is
          # reported once. Emitting the raw value inline would produce
          # `color: 'accent'`, which no browser understands.
          classes << TailwindMapper.map_color(partial['fontColor'], 'text') if partial['fontColor']
          classes << TailwindMapper.map_color(partial['background'], 'bg') if partial['background']
          classes << 'underline' if partial['underline']
          classes << 'line-through' if partial['strikethrough']
          classes << 'cursor-pointer' if partial['onclick']
          classes.reject { |c| c.nil? || c.empty? }.join(' ')
        end

        # Render linkable text (auto-detect URLs and make them clickable)
        def render_linkable_text(indent, id_attr, class_name, style_attr, onclick_attr, testid_attr, tag_attr)
          text = attributes['text'] || ''

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
