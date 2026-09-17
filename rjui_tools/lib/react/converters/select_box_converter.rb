# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class SelectBoxConverter < BaseConverter
        def convert(indent = 2)
          # Date picker mode: selectItemType == "Date"
          select_item_type = attributes['selectItemType']
          if select_item_type&.downcase == 'date'
            return generate_date_picker(indent)
          end

          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          items = attributes['items'] || []

          value_attr = build_value_attr
          on_change = build_on_change
          disabled_attr = build_disabled_attr

          jsx = if items.is_a?(String) && has_binding?(items)
            generate_dynamic_select(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, value_attr, on_change, disabled_attr, items)
          else
            generate_static_select(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, value_attr, on_change, disabled_attr, items)
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Default select styling
          classes << 'border'
          classes << 'rounded-md'
          classes << 'pl-3 pr-8 py-2'
          classes << 'bg-white' unless attributes['background']
          classes << 'cursor-pointer'
          classes << 'outline-none'
          classes << 'focus:ring-2 focus:ring-blue-500 focus:border-blue-500'

          # Border color
          border_color = attributes['borderColor']
          classes << TailwindMapper.map_color(border_color, 'border') if border_color

          # fontColor and fontSize are emitted by base_converter already; this
          # converter used to emit them a second time, which put two `text-*`
          # classes on the element and, when `fontFamily` routed the spec through
          # Configuration.Font.resolve, re-added the size class the base had
          # deliberately dropped.
          #
          # `labelAttributes` is the same style object Label takes, and on a
          # <select> the closed-state text IS the label — so it styles this
          # element, and it wins over the component-level keys (the precedence
          # Toggle already uses).
          #
          # It has to REPLACE, not append: Tailwind spells colour and font size
          # both with `text-`, and two `text-*` classes have no defined winner —
          # precedence comes from stylesheet order, not from the order they
          # appear in the class list.
          classes = apply_label_attributes(classes)

          # A multi-select is a list box: it has no closed state, so the arrow
          # gutter and the pointer cursor are both wrong.
          if multiple_select?
            classes.reject! { |c| c == 'pl-3 pr-8 py-2' || c == 'cursor-pointer' }
            classes << 'px-3 py-2'
          end

          # caretAttributes: present → the native arrow goes and the caret is
          # redrawn from the object; absent → nothing here changes.
          classes = apply_caret_attributes(classes)

          # Hint/placeholder color for when no value is selected.
          #
          # This was read and then thrown away unless `selectedValue` was a
          # binding: the class swap below is the only consumer, and it only
          # exists when there is a runtime condition to swap on. A declared
          # hintColor on a plain select reached nothing at all, which is the
          # C0 finding. The placeholder <option> now carries it too, so the
          # attribute is read in both shapes.
          #
          # A BOUND colour cannot be a palette class either — `text-@{v}`
          # matches nothing — so it rides a custom property. It has to be
          # recorded here, in build_class_name, which owns @dynamic_styles and
          # runs before the style attribute is rendered.
          hint_color = attributes['hintColor'] || attributes['placeholderColor']
          @select_hint_color = hint_color || 'gray-400'
          @declared_hint_color = hint_color
          @select_hint_class =
            if selected_value_bound?
              bound_state_color_class(hint_color, custom_property: '--jui-hint-color', prefix: 'text') ||
                "text-#{@select_hint_color}"
            else
              # No runtime condition to swap on, so the class is never emitted
              # — registering the custom property would leave dead style.
              "text-#{@select_hint_color}"
            end

          # …with one exception: CSS can express "the placeholder row is the
          # selected one" without any runtime state. Without this the CLOSED
          # control — the only state a non-interacting user ever sees — paints
          # the prompt in the inherited colour whatever hintColor said, because
          # an <option>'s own colour reaches the dropdown popup and nothing
          # else. Measured: the conformance select renders byte-identical to
          # its control with hintColor declared (51-A).
          closed_hint = closed_state_hint_class
          classes << closed_hint if closed_hint

          # Disabled state. The binding form used to push a `${...}` into the
          # class list, which finalize_classes split on whitespace and, when no
          # value binding made the className a template literal, left inside a
          # plain className="…" — React rendered the expression as literal text.
          # It is a runtime expression now (build_select_class_attr). The
          # functional half, the real `disabled` attribute, was never affected.
          if attributes['enabled'] == false
            classes << 'cursor-not-allowed'
          end

          finalize_classes(classes)
        end

        private

        def label_attributes
          attrs = attributes['labelAttributes']
          attrs.is_a?(Hash) ? attrs : {}
        end

        def apply_label_attributes(classes)
          label = label_attributes
          return classes if label.empty?

          if (color = label['fontColor'])
            classes = drop_class(classes, TailwindMapper.map_color(attributes['fontColor'], 'text')) if
              attributes['fontColor'] && !has_binding?(attributes['fontColor'])
            classes << TailwindMapper.map_color(color, 'text')
          end

          if (size = label['fontSize'])
            classes = drop_class(classes, TailwindMapper.map_font_size(attributes['fontSize'])) if
              attributes['fontSize']
            classes << TailwindMapper.map_font_size(size)
          end

          if (align = label['textAlign'])
            classes = drop_class(classes, TailwindMapper.map_text_align(attributes['textAlign'])) if
              attributes['textAlign']
            align_class = TailwindMapper.map_text_align(align)
            classes << align_class unless align_class.empty?
          end

          # map_font discriminates a weight name from a family alias, the same
          # way the component-level `font` is resolved.
          if (font = label['font'])
            classes = drop_class(classes, TailwindMapper.map_font(attributes['font'])) if attributes['font']
            font_class = TailwindMapper.map_font(font)
            classes << font_class if font_class && !font_class.empty?
          end

          classes
        end

        # The class list starts life as a single joined string from super, so a
        # replacement has to rewrite that string token by token.
        def drop_class(classes, token)
          return classes if token.nil? || token.to_s.empty?

          classes.map do |entry|
            entry.is_a?(String) && entry.include?(' ') ?
              entry.split(' ').reject { |c| c == token }.join(' ') :
              entry
          end.reject { |entry| entry == token }
        end

        # `multiple` is declared `platform: react` — a list box is a web-only
        # control shape, and the value it reports is an array, not a string.
        def multiple_select?
          attributes['multiple'] == true || attributes['multiple'] == 'true'
        end

        # --- caretAttributes ---------------------------------------------------
        #
        # The browser paints a native <select>'s arrow at an inset nothing in
        # CSS can move: `pr-8` is the TEXT's escape width, not the arrow's
        # position. That is the observation this object was promoted for — an
        # arrow stuck to the trailing edge with no key that pushes it in.
        #
        # Absent → not one byte of the class list or the style changes; the
        # SelectBox baselines that predate this are the evidence. Present →
        # `appearance-none` removes the native arrow and the caret is redrawn
        # as background layers on the <select> itself:
        #
        #   layer 1  the glyph — an inline-SVG chevron by default, `src` if given
        #   layer 2  the `background` box, a solid two-stop gradient, only when
        #            `background` is declared
        #
        # Both layers share one position (`right <rightMargin>px center`) and
        # one size (`<width>px <height>px`), so the box IS the caret's own
        # width × height and never the select's. A pseudo-element would need a
        # stylesheet the codegen does not own; a wrapper <span> would move the
        # element the id / testId / value binding land on.
        #
        # tintColor reaches the default glyph as its stroke. A raster `src` is
        # drawn as-is: the web has no "template image", and recolouring a
        # bitmap needs mask-image, which would paint over the background box.
        # A colors.json key resolves through ColorManager at runtime (the path
        # color_style_expr already takes), which turns the value into a
        # template literal; a CSS literal is baked in.
        #
        # The list box (`multiple`) and the Date mode have no closed-state
        # caret (SSoT), so both are out — the same predicate that drops the
        # arrow gutter above. A bound width/height/rightMargin is not resolved
        # here and falls to the default.
        #
        # Known limit: a gradient `background` on the select itself lands in
        # `@dynamic_styles['background']` (the shorthand), and a shorthand plus
        # `backgroundImage` on one element has one winner in key order. That
        # combination has no fixture and is left as it falls.
        CARET_DEFAULT_SIZE = 16
        CARET_DEFAULT_TINT = '#000000'
        CARET_TEXT_GAP = 8
        CARET_CHEVRON_PATH = 'M6 9l6 6 6-6'

        def caret_attributes
          caret = attributes['caretAttributes']
          caret.is_a?(Hash) ? caret : nil
        end

        def date_picker?
          attributes['selectItemType'].to_s.downcase == 'date'
        end

        def apply_caret_attributes(classes)
          caret = caret_attributes
          return classes if caret.nil? || multiple_select? || date_picker?

          width = caret_px(caret['width'], CARET_DEFAULT_SIZE)
          height = caret_px(caret['height'], CARET_DEFAULT_SIZE)
          right = caret_px(caret['rightMargin'], 0)

          classes = drop_class(classes, 'pr-8')
          classes << 'appearance-none'

          layers = caret_glyph_layer(caret)
          layers += [[:lit, ', ']] + caret_box_layer(caret['background']) if caret['background']

          @dynamic_styles['backgroundImage'] = js_string_expr(layers)
          @dynamic_styles['backgroundRepeat'] = "'no-repeat'"
          @dynamic_styles['backgroundPosition'] = "'right #{right}px center'"
          @dynamic_styles['backgroundSize'] = "'#{width}px #{height}px'"
          # The text's escape width follows the caret. The fixed `pr-8` (32px)
          # would put a 32px caret at rightMargin 24 straight over the text.
          @dynamic_styles['paddingRight'] = "'#{right + width + CARET_TEXT_GAP}px'"
          classes
        end

        # Parts are [:lit, text] / [:expr, js] so one renderer can decide
        # between a plain string and a template literal.
        def caret_glyph_layer(caret)
          if caret['src']
            return [[:lit, "url(\"/images/#{resolve_image_extension(caret['src'].to_s)}\")"]]
          end

          head = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="'
          tail = "\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\">" \
                 "<path d=\"#{CARET_CHEVRON_PATH}\"/></svg>"
          [[:lit, "url(\"data:image/svg+xml,#{svg_uri_encode(head)}"]] +
            caret_color_parts(caret['tintColor'] || CARET_DEFAULT_TINT, uri: true, fallback: CARET_DEFAULT_TINT) +
            [[:lit, "#{svg_uri_encode(tail)}\")"]]
        end

        def caret_box_layer(color)
          parts = caret_color_parts(color, uri: false, fallback: 'transparent')
          [[:lit, 'linear-gradient(']] + parts + [[:lit, ', ']] + parts + [[:lit, ')']]
        end

        # A colors.json name resolves at runtime through
        # `ColorManager.resolveColor`, whose return type is `string | undefined`
        # — and the conformance host reverse-maps every `#FF0000` in a fixture
        # to its `dark_red` entry, so the generated caret fixture takes this
        # branch. Two things go wrong without the `??`:
        #   * `encodeURIComponent(undefined)` is a TS2345 on the typed
        #     parameter — CI's "generated code must have zero type errors"
        #     step caught it on run 35172403874 before any pixel was drawn;
        #   * inside the template literal an unresolved name renders the text
        #     `undefined` into the CSS, which invalidates the whole
        #     `background-image` and takes the glyph down with the box.
        # The fallbacks are the defaults the layer would have had anyway: the
        # glyph's default tint, and no paint for the box.
        def caret_color_parts(value, uri:, fallback:)
          expr = color_style_expr(value)
          if expr.start_with?("'")
            literal = expr[1..-2]
            [[:lit, uri ? svg_uri_encode(literal) : literal]]
          else
            guarded = "#{expr} ?? '#{fallback}'"
            [[:expr, uri ? "encodeURIComponent(#{guarded})" : "(#{guarded})"]]
          end
        end

        # Only the characters a data: URI cannot carry raw inside url("…").
        def svg_uri_encode(text)
          text.gsub(/[<>#"% ]/) { |ch| format('%%%02X', ch.ord) }
        end

        def js_string_expr(parts)
          return "'#{parts.map(&:last).join}'" if parts.none? { |kind, _| kind == :expr }

          "`#{parts.map { |kind, text| kind == :expr ? "${#{text}}" : text }.join}`"
        end

        def caret_px(value, default)
          number =
            case value
            when Numeric then value.to_f
            when /\A\d+(\.\d+)?\z/ then value.to_f
            else return default
            end
          (number % 1).zero? ? number.to_i : number
        end

        # `size` — how many option rows are visible. Only meaningful on a list
        # box, which is why HTML ignores it on a closed single select unless it
        # is > 1 (and then turns the select INTO a list box).
        def build_size_attr
          size = attributes['size']
          return '' unless size.is_a?(Numeric) || (size.is_a?(String) && size.match?(/\A\d+\z/))

          " size={#{size.to_i}}"
        end

        def build_multiple_attr
          multiple_select? ? ' multiple' : ''
        end

        # Build className attribute for select, with dynamic hint color when no value is selected
        # Is the selected value a binding? The hint/normal class swap only
        # exists when there is a runtime condition to swap on, and
        # build_class_name has to know the same answer to decide whether the
        # hint colour needs a custom property.
        def selected_value_bound?
          value_binding = with_bind_fallback(attributes['selectedValue'] || attributes['value'])
          !!(value_binding && has_binding?(value_binding))
        end

        def build_select_class_attr(class_name)
          value_binding = with_bind_fallback(attributes['selectedValue'] || attributes['value'])

          expressions = []
          if value_binding && has_binding?(value_binding)
            prop = extract_binding_property(value_binding)
            hint_class = @select_hint_class
            font_color = attributes['fontColor']
            normal_class = font_color ? "text-#{font_color}" : ''
            expressions << "${#{prop} ? '#{normal_class}' : '#{hint_class}'}"
          end
          if has_binding?(attributes['enabled'])
            expressions << "${!#{extract_binding_property(attributes['enabled'])} ? 'opacity-50 cursor-not-allowed' : ''}"
          end

          return "className=\"#{class_name}\"" if expressions.empty?

          "className={`#{class_name} #{expressions.join(' ')}`}"
        end

        # The closed control's own colour while the placeholder row is the
        # selected one. `:has(option:first-child:checked)` is the runtime
        # condition expressed in CSS — the placeholder row is always emitted
        # first, and `:checked` follows the user's selection — so the literal
        # face gets the same closed-state colour the bound face gets from its
        # class swap. The colour rides the same custom property either way:
        # a palette name resolves through ColorManager at runtime, which no
        # `text-<name>` class could do for a bound value.
        def closed_state_hint_class
          return @closed_state_hint_class if defined?(@closed_state_hint_class)

          @closed_state_hint_class =
            if @declared_hint_color && placeholder_row?
              dynamic_styles['--jui-hint-color'] = color_style_expr(@declared_hint_color)
              "[&:has(option:first-child:checked)]:text-[var(--jui-hint-color)]"
            end
        end

        # Is a placeholder row emitted at all? A list box has no closed state,
        # so it never gets one (and the class would style the wrong thing).
        def placeholder_row?
          hint = attributes['prompt'] || attributes['hint'] || attributes['placeholder']
          !!hint && !multiple_select?
        end

        # The placeholder <option>'s own colour. Emitted only when hintColor
        # (or its placeholderColor alias) was actually DECLARED — the
        # `gray-400` fallback must stay a class so every existing select keeps
        # the markup it had.
        def hint_option_style
          return '' unless @declared_hint_color

          style_attr_for({ 'color' => color_style_expr(@declared_hint_color) })
        end

        def resolve_hint_text(hint)
          return hint unless hint
          resolved = convert_text_binding(hint)
          if resolved != hint && resolved.include?('{')
            resolved
          else
            hint
          end
        end

        def generate_dynamic_select(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, value_attr, on_change, disabled_attr, items)
          items_prop = extract_binding_property(items)
          hint = attributes['prompt'] || attributes['hint'] || attributes['placeholder']
          hint_text = resolve_hint_text(hint)
          # Placeholder row is selectable (no `disabled hidden`) so picking
          # it clears the value back to "" — the unselected state mirrors
          # iOS / Android SelectBox behavior.
          # A list box has no closed state to label, so a blank row there is just
          # a selectable item meaning "nothing".
          hint_option = hint && !multiple_select? ?
            "\n#{indent_str(indent + 2)}<option value=\"\"#{hint_option_style}>#{hint_text}</option>" : ''
          class_attr = build_select_class_attr(class_name)

          # Canonical items are a plain string array ([String] — matches
          # SwiftJsonUI SelectBoxView's `items: [String]`); {value,text}
          # object elements stay supported as the web-side extended form.
          # The widening cast keeps the runtime dual-shape branch compatible
          # with ANY declared element type — on string[] items a bare
          # typeof-narrowing would reduce the object branch to `never` and
          # every property access to TS2339.
          opt_cast =
            if config['typescript'] != false
              ' as string | number | { value?: string | number; id?: string | number; text?: string; label?: string }'
            else
              ''
            end
          <<~JSX.chomp
            #{indent_str(indent)}<select#{id_attr} #{class_attr}#{build_multiple_attr}#{build_size_attr}#{value_attr}#{on_change}#{disabled_attr}#{style_attr}#{testid_attr}#{tag_attr}>#{hint_option}
            #{indent_str(indent + 2)}{#{items_prop}?.map((item) => {
            #{indent_str(indent + 4)}const opt = item#{opt_cast};
            #{indent_str(indent + 4)}return typeof opt === 'object' && opt !== null
            #{indent_str(indent + 6)}? <option key={String(opt.value ?? opt.id ?? '')} value={String(opt.value ?? opt.id ?? '')}>{opt.text || opt.label}</option>
            #{indent_str(indent + 6)}: <option key={String(opt)} value={String(opt)}>{String(opt)}</option>;
            #{indent_str(indent + 2)}})}
            #{indent_str(indent)}</select>
          JSX
        end

        def generate_static_select(indent, id_attr, class_name, style_attr, testid_attr, tag_attr, value_attr, on_change, disabled_attr, items)
          options_jsx = items.map do |item|
            if item.is_a?(Hash)
              value = item['value'] || item['id'] || item['text']
              label = item['text'] || item['label'] || value
              "#{indent_str(indent + 2)}<option value=\"#{value}\">#{label}</option>"
            else
              "#{indent_str(indent + 2)}<option value=\"#{item}\">#{item}</option>"
            end
          end.join("\n")

          hint = attributes['prompt'] || attributes['hint'] || attributes['placeholder']
          if hint && !multiple_select?
            hint_text = resolve_hint_text(hint)
            # Placeholder row is selectable (no `disabled hidden`) so picking
            # it clears the value back to "" — the unselected state mirrors
            # iOS / Android SelectBox behavior.
            options_jsx = "#{indent_str(indent + 2)}<option value=\"\"#{hint_option_style}>#{hint_text}</option>\n#{options_jsx}"
          end

          class_attr = build_select_class_attr(class_name)

          <<~JSX.chomp
            #{indent_str(indent)}<select#{id_attr} #{class_attr}#{build_multiple_attr}#{build_size_attr}#{value_attr}#{on_change}#{disabled_attr}#{style_attr}#{testid_attr}#{tag_attr}>
            #{options_jsx}
            #{indent_str(indent)}</select>
          JSX
        end

        def build_value_attr
          value = with_bind_fallback(attributes['selectedValue'] || attributes['value'])

          if value && has_binding?(value)
            prop = extract_binding_property(value)
            # React requires an array for a multi-select; the ViewModel may
            # still be holding the single-value shape, so normalise rather than
            # trust it and have React warn at runtime.
            return " value={Array.isArray(#{prop}) ? #{prop} : (#{prop} == null || #{prop} === '' ? [] : [#{prop}])}" if
              multiple_select?

            " value={#{prop}}"
          elsif value
            multiple_select? ? " defaultValue={[\"#{value}\"]}" : " defaultValue=\"#{value}\""
          elsif (index_binding = attributes['selectedIndex']) && has_binding?(index_binding)
            build_index_value_attr(index_binding)
          elsif attributes['selectedIndex'].is_a?(Numeric)
            # A literal selectedIndex seeds the initial selection (33
            # cross-effect: web ignored it while ios honored it).
            items = attributes['items']
            if items.is_a?(Array)
              item = items[attributes['selectedIndex'].to_i]
              literal = item.is_a?(Hash) ? (item['value'] || item['label']) : item
              literal ? " defaultValue=\"#{literal}\"" : ''
            else
              ''
            end
          else
            ''
          end
        end

        # selectedIndex is a two-way binding, so the <select> must be a
        # controlled component: resolve the item at the bound index to the
        # same value string the <option> rows emit (dual-shape aware).
        def build_index_value_attr(index_binding)
          index_prop = extract_binding_property(index_binding)
          items = attributes['items']

          if items.is_a?(String) && has_binding?(items)
            items_prop = extract_binding_property(items)
            sel_cast =
              if config['typescript'] != false
                ' as string | number | { value?: string | number; id?: string | number } | undefined'
              else
                ''
              end
            " value={(() => { const sel = #{items_prop}?.[#{index_prop} ?? -1]#{sel_cast}; return sel != null && typeof sel === 'object' ? String(sel.value ?? sel.id ?? '') : String(sel ?? ''); })()}"
          elsif items.is_a?(Array)
            values = items.map do |item|
              raw = item.is_a?(Hash) ? (item['value'] || item['id'] || item['text']) : item
              "'#{raw.to_s.gsub("'") { "\\'" }}'"
            end
            " value={[#{values.join(', ')}][#{index_prop} ?? -1] ?? ''}"
          else
            ''
          end
        end

        def build_on_change
          handler = attributes['onValueChange'] || attributes['onValueChanged'] || attributes['onChange']
          if handler
            if has_binding?(handler)
              prop = extract_binding_property(handler)
              return " onChange={(e) => #{prop}?.(#{changed_value_expr})}"
            else
              return " onChange={(e) => #{handler}?.(#{changed_value_expr})}"
            end
          end

          # Auto-generate onChange from value binding (two-way binding)
          value_key = attributes['selectedValue'] || attributes['value']
          index_key = attributes['selectedIndex'] unless value_key
          value_key ||= index_key
          if value_key && has_binding?(value_key)
            property_name = value_key.match(/@\{(.+)\}/)[1]
            handler_name = "on#{property_name[0].upcase}#{property_name[1..]}Change"
            # A selectedIndex binding is a NUMBER both ways: the value side
            # resolves the item at the index (build_index_value_attr), so the
            # write-back reports the index, not the option's string. The
            # placeholder row occupies DOM index 0 when present, and picking it
            # reports -1 — the same "nothing selected" the value side renders
            # for. (Reporting `e.target.value` typed the handler's argument as
            # a string, which the declared `(value: number) => void` rejects.)
            if index_key
              index_expr = placeholder_row? ? 'e.target.selectedIndex - 1' : 'e.target.selectedIndex'
              return " onChange={(e) => data.#{handler_name}?.(#{index_expr})}"
            end
            return " onChange={(e) => data.#{handler_name}?.(#{changed_value_expr})}"
          end

          ''
        end

        # `e.target.value` on a multi-select is only the FIRST selected option,
        # which silently loses every other selection — the whole point of the
        # attribute. selectedOptions is the full set.
        def changed_value_expr
          multiple_select? ? 'Array.from(e.target.selectedOptions).map((o) => o.value)' : 'e.target.value'
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

        def generate_date_picker(indent)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          disabled_attr = build_disabled_attr

          # Determine input type from datePickerMode
          date_picker_mode = attributes['datePickerMode']&.downcase
          input_type = case date_picker_mode
                       when 'time' then 'time'
                       when 'datetime', 'dateandtime' then 'datetime-local'
                       else 'date'
                       end

          # Value binding (selectedDate or selectedValue)
          date_value = attributes['selectedDate'] || attributes['selectedValue'] || attributes['value']
          # dateStringFormat is the shape the ViewModel holds; the input only
          # ever speaks ISO (yyyy-MM-dd / HH:mm / yyyy-MM-ddTHH:mm), so the value
          # is converted in both directions rather than silently handing the VM a
          # string in a format it did not ask for.
          format = date_string_format
          value_attr = if date_value && has_binding?(date_value)
                         prop = extract_binding_property(date_value)
                         if format
                           @uses_date_format = true
                           " value={toIsoDateValue(#{prop}, '#{format}', '#{input_type}')}"
                         else
                           " value={#{prop} || ''}"
                         end
                       elsif date_value
                         " value=\"#{date_value}\""
                       else
                         ''
                       end

          # Min/max date. Both are declared binding-capable, and the quoted
          # interpolation handed the <input> the literal characters `@{v}` —
          # not a date, so the browser drops the bound and the field accepts
          # anything. A binding becomes a JSX expression.
          min_attr = date_bound_attr('min', attributes['minimumDate'])
          max_attr = date_bound_attr('max', attributes['maximumDate'])

          # minuteInterval / datePickerStyle / click-to-open
          step_attr = build_minute_interval_attr(input_type)
          picker_attr = build_date_picker_style_attr
          click_attr = build_date_picker_click_attr

          # onChange handler
          on_change = build_date_on_change(date_value, input_type)

          # Apply color-scheme for dark backgrounds so the calendar icon is visible
          date_style = build_date_style_attr
          combined_style = date_style.empty? ? style_attr : date_style

          jsx = "#{indent_str(indent)}<input#{id_attr} className=\"#{class_name}\" type=\"#{input_type}\"#{value_attr}#{on_change}#{min_attr}#{max_attr}#{step_attr}#{picker_attr}#{click_attr}#{disabled_attr}#{combined_style}#{testid_attr}#{tag_attr} />"

          wrap_with_visibility(jsx, indent)
        end

        def build_date_style_attr
          color_scheme = attributes['colorScheme']
          existing_style = build_style_attr

          if color_scheme
            if existing_style.include?('style=')
              existing_style.sub('style={{', "style={{ colorScheme: '#{color_scheme}',")
            else
              " style={{ colorScheme: '#{color_scheme}' }}"
            end
          else
            existing_style
          end
        end

        def build_date_on_change(date_value, input_type = 'date')
          value_expr = if (format = date_string_format)
                         @uses_date_format = true
                         "formatDateValue(e.target.value, '#{format}', '#{input_type}')"
                       else
                         'e.target.value'
                       end

          # Custom handler takes priority
          handler = attributes['onValueChange'] || attributes['onChange']
          if handler && has_binding?(handler)
            prop = extract_binding_property(handler)
            return " onChange={(e) => #{prop}?.(#{value_expr})}"
          end

          # Auto-generate from selectedDate binding
          if date_value && has_binding?(date_value)
            property_name = date_value.match(/@\{(.+)\}/)[1]
            handler_name = "on#{property_name[0].upcase}#{property_name[1..]}Change"
            return " onChange={(e) => data.#{handler_name}?.(#{value_expr})}"
          end

          ''
        end

        def date_string_format
          format = attributes['dateStringFormat']
          format.is_a?(String) && !format.empty? ? format : nil
        end

        # `min` / `max` on the date input: a static value stays a quoted
        # literal, a bound one becomes the expression it stands for.
        def date_bound_attr(name, value)
          return '' unless value

          expr = bound_value_expr(value)
          expr ? " #{name}={#{expr}}" : " #{name}=\"#{value}\""
        end

        # minuteInterval — `step` is in seconds, so the interval is minutes * 60.
        # Only a time-bearing input has minutes to step through.
        def build_minute_interval_attr(input_type)
          interval = attributes['minuteInterval']
          return '' unless interval.is_a?(Numeric) && interval.positive?
          return '' unless %w[time datetime-local].include?(input_type)

          " step={#{interval.to_i * 60}}"
        end

        # datePickerStyle — the wheel/compact/graphical chrome is UIKit's, and a
        # native web date input has none of it. What the web CAN honour is
        # whether the picker is presented or merely available: `graphical` and
        # `inline` mean "show the picker", so the calendar is opened as soon as
        # the field takes focus (HTMLInputElement.showPicker). The wheel styles
        # have no web analogue and fall through to the native control.
        def build_date_picker_style_attr
          style = attributes['datePickerStyle'].to_s.downcase
          return '' unless %w[graphical inline].include?(style)

          ' onFocus={(e) => e.currentTarget.showPicker?.()}'
        end

        # A native date input opens its calendar only from the indicator icon
        # at its right edge; a click anywhere else in the box merely focuses
        # the field, and a person tapping the visible control expects the
        # calendar (reported on a web admin face, 2026-09-14). Every click
        # therefore asks for the picker, whatever the datePickerStyle. Guarded
        # because showPicker throws where it cannot open (no user activation,
        # a cross-origin frame) — the native control is the fallback either
        # way, and an engine without showPicker simply keeps its own behaviour.
        # Independent of the focus hook above: focus is the "present it"
        # semantics of graphical/inline; click is what a pointer does.
        def build_date_picker_click_attr
          ' onClick={(e) => { try { e.currentTarget.showPicker?.(); } catch {} }}'
        end
      end
    end
  end
end
