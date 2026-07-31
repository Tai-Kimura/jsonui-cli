# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class LabelConverter < BaseConverter
        def convert(indent = 2)
          class_attr = build_class_attr
          style_attr = build_style_attr
          id_attr = build_id_attr
          onclick_attr = build_onclick_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          # Check if we need partialAttributes rendering
          jsx = if partial_attributes_list
            render_partial_attributes(indent, id_attr, class_attr, style_attr, onclick_attr, testid_attr, tag_attr)
          elsif attributes['linkable']
            render_linkable_text(indent, id_attr, class_attr, style_attr, onclick_attr, testid_attr, tag_attr)
          else
            render_plain_text(indent, id_attr, class_attr, style_attr, onclick_attr, testid_attr, tag_attr)
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        # The plain single-span label, with the hint swap when configured.
        #
        # Canonical semantics (UIKit SJUILabel, mirrored by kjui): `hint` +
        # `hintAttributes` are BOTH required, and the styled hint replaces the
        # text when the text is empty. `placeholder` is the declared alias of
        # `hint`; `hintAttributes.fontColor` wins over `hintColor`.
        def render_plain_text(indent, id_attr, class_attr, style_attr, onclick_attr, testid_attr, tag_attr)
          raw = attributes['text'] || ''
          hint = hint_config
          common = "#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr}"
          # The hint span merges the hint styling into the (possibly present)
          # dynamic style attribute — two style props on one element is
          # invalid JSX.
          hint_common = hint ? "#{merged_hint_style(style_attr, hint)}#{onclick_attr}#{testid_attr}#{tag_attr}" : common

          if hint && raw.strip.empty?
            # Statically empty: the hint IS the content.
            return "#{indent_str(indent)}<span#{id_attr}#{class_attr}#{hint_common}>#{escape_jsx_text(hint[:text])}</span>"
          end

          if hint && pure_binding_text?(raw)
            # Runtime emptiness: two spans, one rendered. An empty string is
            # falsy in JS, which is exactly the SJUILabel `string.isEmpty`
            # test.
            expr = extract_binding_property(raw)
            text_node = convert_text_binding(raw)
            return <<~JSX.chomp
              #{indent_str(indent)}{(#{expr}) ? (
              #{indent_str(indent + 2)}<span#{id_attr}#{class_attr}#{common}>#{text_node}</span>
              #{indent_str(indent)}) : (
              #{indent_str(indent + 2)}<span#{id_attr}#{class_attr}#{hint_common}>#{escape_jsx_text(hint[:text])}</span>
              #{indent_str(indent)})}
            JSX
          end

          text = convert_text_binding(raw)
          "#{indent_str(indent)}<span#{id_attr}#{class_attr}#{common}>#{text}</span>"
        end

        def merged_hint_style(style_attr, hint)
          return style_attr if hint[:parts].empty?

          if style_attr.include?('style={{')
            style_attr.sub(/ \}\}$/, ", #{hint[:parts].join(', ')} }}")
          else
            " style={{ #{hint[:parts].join(', ')} }}"
          end
        end

        # {text:, style:} when the hint contract is satisfied. Styling is
        # emitted as INLINE STYLE on purpose: appending a second `text-*`
        # class would race the base font classes on stylesheet order (the
        # known Tailwind trap), while an inline style always wins. Theme
        # colour names resolve through the generated `--color-*` variables
        # (theme.css); hex values pass through.
        def hint_config
          attrs = attributes['hintAttributes']
          hint = attributes['hint'] || attributes['placeholder']
          return nil unless attrs.is_a?(Hash) && hint.is_a?(String) && !hint.empty?

          color = attrs['fontColor'] || attributes['hintColor']
          parts = []
          if color && !has_binding?(color)
            css = color.to_s.start_with?('#') ? color : "var(--color-#{color})"
            parts << "color: '#{css}'"
          end
          parts << "fontSize: '#{attrs['fontSize']}px'" if attrs['fontSize']
          parts << "fontFamily: '#{attrs['font']}'" if attrs['font']
          { text: hint, parts: parts }
        end

        def pure_binding_text?(raw)
          raw.is_a?(String) && raw.strip.match?(/\A@\{[^}]+\}\z/)
        end

        def escape_jsx_text(text)
          text.to_s.gsub('{', '&#123;').gsub('}', '&#125;').gsub('<', '&lt;')
        end

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

        # The className attribute, which is an EXPRESSION when the label has a
        # highlight state driven by a binding.
        #
        # A second `text-*` class cannot simply be appended: Tailwind precedence
        # comes from the order rules appear in the stylesheet, not from the order
        # they appear in the attribute, so `text-black text-red-500` picks a
        # winner arbitrarily. The highlight branch therefore REPLACES the base
        # font classes rather than adding to them.
        def build_class_attr
          base = build_class_name
          highlight = highlight_classes
          return " className=\"#{base}\"" if highlight.empty?

          condition = selected_condition
          return " className=\"#{base}\"" if condition.nil?

          swapped = (base.split(/\s+/) - overridden_font_classes + highlight).join(' ')
          # A literal `selected: true` needs no runtime branch.
          return " className=\"#{swapped}\"" if condition == 'true'

          " className={#{condition} ? \"#{swapped}\" : \"#{base}\"}"
        end

        # Classes for the highlight state, from `highlightAttributes` or, when
        # that yields nothing usable, from `highlightColor`.
        #
        # Canonical semantics come from the iOS UIKit runtime, which keeps two
        # attribute dictionaries and swaps on `selected`
        # (SJUILabel#applyAttributedText); its creator prefers a non-empty
        # `highlightAttributes` and otherwise falls back to `highlightColor`.
        def highlight_classes
          attrs = attributes['highlightAttributes']
          classes = []

          if attrs.is_a?(Hash)
            classes << TailwindMapper.map_font_size(attrs['fontSize']) if attrs['fontSize']
            # `font` is polymorphic: a weight name or a family. map_font already
            # discriminates, the same way the base path uses it.
            if attrs['font']
              font_class = TailwindMapper.map_font(attrs['font'])
              classes << font_class if font_class && !font_class.empty?
            end
            classes << TailwindMapper.map_color(attrs['fontColor'], 'text') if attrs['fontColor']
            classes.concat(align_classes(attrs['textAlign']))
          end

          classes = classes.reject { |c| c.nil? || c.empty? }
          if classes.empty? && attributes['highlightColor']
            classes = [TailwindMapper.map_color(attributes['highlightColor'], 'text')]
          end
          classes.reject { |c| c.nil? || c.empty? }
        end

        # The exact base classes the highlight set replaces. Recomputed rather
        # than pattern-matched: Tailwind spells both colour and font size with a
        # `text-` prefix (`text-[#FF0000]`, `text-[24px]`), so a prefix match
        # cannot tell them apart, but the strings the base emitted are knowable.
        def overridden_font_classes
          attrs = attributes['highlightAttributes']
          attrs = {} unless attrs.is_a?(Hash)
          overridden = []

          if attrs['fontColor'] || attributes['highlightColor']
            overridden << TailwindMapper.map_color(attributes['fontColor'], 'text') if attributes['fontColor']
          end
          if attrs['fontSize'] && attributes['fontSize']
            overridden << TailwindMapper.map_font_size(attributes['fontSize'])
          end
          if attrs['font']
            overridden << TailwindMapper.map_font(attributes['font']) if attributes['font']
            if attributes['fontWeight']
              overridden << TailwindMapper.map_font_weight(attributes['fontWeight'])
            end
          end
          overridden.concat(align_classes(attributes['textAlign'])) if attrs['textAlign']
          overridden.reject { |c| c.nil? || c.empty? }
        end

        # textAlign costs two classes, not one: the base converter maps it to
        # `text-*`, and a single-run label is a flex container so this converter
        # also maps it to `justify-*`. A highlight that changes the alignment has
        # to replace both, or the flex justification keeps the old value and wins.
        def align_classes(value)
          return [] unless value.is_a?(String)

          classes = [TailwindMapper.map_text_align(value)]
          unless multi_run_text?
            case value.downcase
            when 'center' then classes << 'justify-center'
            when 'right' then classes << 'justify-end'
            when 'left' then classes << 'justify-start'
            end
          end
          classes.reject { |c| c.nil? || c.empty? }
        end

        # The lineHeight swap. Kept out of the class list because line height is
        # a unitless multiplier in the style object, where React reads a bare
        # number as a multiplier rather than pixels.
        def apply_highlight_line_height
          attrs = attributes['highlightAttributes']
          return unless attrs.is_a?(Hash)

          multiple = attrs['lineHeightMultiple']
          return if multiple.nil?

          condition = selected_condition
          return if condition.nil?

          if condition == 'true'
            @dynamic_styles['lineHeight'] = multiple.to_s
            return
          end

          base = @dynamic_styles['lineHeight'] || "'normal'"
          @dynamic_styles['lineHeight'] = "(#{condition} ? #{multiple} : #{base})"
        end

        # The `selected` state that decides which set is in force. Absent means
        # never highlighted, so no swap is emitted at all.
        def selected_condition
          value = attributes['selected']
          return 'true' if value == true || value == 'true'
          return extract_binding_property(value) if value.is_a?(String) && has_binding?(value)

          nil
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

          # textTransform — declared `platform: react`; CSS text-transform is the
          # web's own capability, and `none` is the initial value, so it is
          # spelled out rather than omitted (a style block may have set another).
          case attributes['textTransform'].to_s
          when 'uppercase' then classes << 'uppercase'
          when 'lowercase' then classes << 'lowercase'
          when 'capitalize' then classes << 'capitalize'
          when 'none' then classes << 'normal-case'
          end

          # Cursor pointer for clickable items
          classes << 'cursor-pointer' if attributes['onClick'] || attributes['onclick']

          # Linkable text
          classes << 'cursor-pointer' if attributes['linkable']

          finalize_classes(classes)
        end

        def build_style_attr
          # Call parent to initialize @dynamic_styles
          super

          # Line spacing / line height. `lineHeight` is declared
          # `platform: react` and is the CSS property directly, in px — the
          # cross-platform spellings are the multiplier and the extra spacing, so
          # they take precedence over the web-only literal.
          if attributes['lineHeightMultiple']
            @dynamic_styles['lineHeight'] = attributes['lineHeightMultiple'].to_s
          elsif attributes['lineSpacing']
            # Convert lineSpacing (px) to lineHeight (em-ish)
            font_size = attributes['fontSize'] || 16
            line_height = ((font_size + attributes['lineSpacing'].to_f) / font_size).round(2)
            @dynamic_styles['lineHeight'] = line_height.to_s

          elsif attributes['lineHeight']
            @dynamic_styles['lineHeight'] = "'#{attributes['lineHeight']}px'"
          end

          # A highlight lineHeightMultiple. Line height is a unitless multiplier
          # here, not a class, so unlike the font attributes it swaps through the
          # style object; `normal` is the CSS initial value, i.e. "the font's own".
          apply_highlight_line_height

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

          # textShadow — canonical object {color, blur, offset: [x, y]}
          # (UIKit SJUILabel requires all three; same contract here). Theme
          # colour names resolve through the generated --color-* variables.
          shadow = attributes['textShadow']
          if shadow.is_a?(Hash) && shadow['color'] && shadow['blur'] && shadow['offset'].is_a?(Array)
            css_color = shadow['color'].to_s.start_with?('#') ? shadow['color'] : "var(--color-#{shadow['color']})"
            @dynamic_styles['textShadow'] = "'#{shadow['offset'][0]}px #{shadow['offset'][1]}px #{shadow['blur']}px #{css_color}'"
          elsif shadow.is_a?(String) && !shadow.empty?
            # A raw CSS string passes through untouched.
            @dynamic_styles['textShadow'] = "'#{shadow}'"
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
        def render_partial_attributes(indent, id_attr, class_attr, style_attr, onclick_attr, testid_attr, tag_attr)
          text_expr = text_runtime_expression(attributes['text'] || '')
          specs = build_partial_specs(attributes['partialAttributes'])

          lines = []
          lines << "#{indent_str(indent)}<span#{id_attr}#{class_attr}#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr}>"
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
        def render_linkable_text(indent, id_attr, class_attr, style_attr, onclick_attr, testid_attr, tag_attr)
          text = attributes['text'] || ''

          # For React, we'll render with a data attribute and let the app handle link detection
          # Or use a simple regex-based approach
          lines = []
          lines << "#{indent_str(indent)}<span#{id_attr}#{class_attr}#{style_attr}#{onclick_attr}#{testid_attr}#{tag_attr} data-linkable=\"true\">"

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
