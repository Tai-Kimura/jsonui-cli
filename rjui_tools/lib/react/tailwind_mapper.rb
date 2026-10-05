# frozen_string_literal: true

require 'bigdecimal'
require_relative '../core/logger'
require_relative '../core/enum_spelling'

module RjuiTools
  module React
    class TailwindMapper
      # Font size mapping
      FONT_SIZE_MAP = {
        12 => 'text-xs', 14 => 'text-sm', 16 => 'text-base',
        18 => 'text-lg', 20 => 'text-xl', 24 => 'text-2xl',
        30 => 'text-3xl', 36 => 'text-4xl', 48 => 'text-5xl',
        60 => 'text-6xl'
      }.freeze

      # Corner radius mapping
      RADIUS_MAP = {
        0 => 'rounded-none', 2 => 'rounded-sm', 4 => 'rounded',
        6 => 'rounded-md', 8 => 'rounded-lg', 12 => 'rounded-xl',
        16 => 'rounded-2xl', 24 => 'rounded-3xl'
      }.freeze

      # Shadow mapping
      SHADOW_MAP = {
        'sm' => 'shadow-sm',
        'md' => 'shadow-md',
        'lg' => 'shadow-lg',
        'xl' => 'shadow-xl',
        '2xl' => 'shadow-2xl'
      }.freeze

      # Opacity mapping
      OPACITY_MAP = {
        0 => 'opacity-0',
        0.1 => 'opacity-10',
        0.2 => 'opacity-20',
        0.25 => 'opacity-25',
        0.3 => 'opacity-30',
        0.4 => 'opacity-40',
        0.5 => 'opacity-50',
        0.6 => 'opacity-60',
        0.7 => 'opacity-70',
        0.75 => 'opacity-75',
        0.8 => 'opacity-80',
        0.9 => 'opacity-90',
        1 => 'opacity-100'
      }.freeze

      # Font weight mapping
      FONT_WEIGHT_MAP = {
        'thin' => 'font-thin',
        'extralight' => 'font-extralight',
        'light' => 'font-light',
        'normal' => 'font-normal',
        'medium' => 'font-medium',
        'semibold' => 'font-semibold',
        'bold' => 'font-bold',
        'extrabold' => 'font-extrabold',
        'black' => 'font-black'
      }.freeze

      class << self
        def map_padding(padding)
          case padding
          when Numeric
            "p-#{spacing_value(padding)}"
          when Array
            map_padding_array(padding)
          else
            ''
          end
        end

        def map_padding_array(arr)
          case arr.length
          when 1
            "p-#{spacing_value(arr[0])}"
          when 2
            "py-#{spacing_value(arr[0])} px-#{spacing_value(arr[1])}"
          when 4
            classes = []
            classes << "pt-#{spacing_value(arr[0])}"
            classes << "pr-#{spacing_value(arr[1])}"
            classes << "pb-#{spacing_value(arr[2])}"
            classes << "pl-#{spacing_value(arr[3])}"
            classes.join(' ')
          else
            ''
          end
        end

        def map_individual_paddings(top, right, bottom, left)
          classes = []
          classes << "pt-#{spacing_value(top)}" if top
          classes << "pr-#{spacing_value(right)}" if right
          classes << "pb-#{spacing_value(bottom)}" if bottom
          classes << "pl-#{spacing_value(left)}" if left
          classes.join(' ')
        end

        def map_margin(margin)
          case margin
          when Numeric
            "m-#{spacing_value(margin)}"
          when Array
            map_margin_array(margin)
          else
            ''
          end
        end

        def map_margin_array(arr)
          case arr.length
          when 1
            "m-#{spacing_value(arr[0])}"
          when 2
            "my-#{spacing_value(arr[0])} mx-#{spacing_value(arr[1])}"
          when 4
            classes = []
            classes << "mt-#{spacing_value(arr[0])}"
            classes << "mr-#{spacing_value(arr[1])}"
            classes << "mb-#{spacing_value(arr[2])}"
            classes << "ml-#{spacing_value(arr[3])}"
            classes.join(' ')
          else
            ''
          end
        end

        def map_individual_margins(top, right, bottom, left)
          classes = []
          classes << "mt-#{spacing_value(top)}" if top
          classes << "mr-#{spacing_value(right)}" if right
          classes << "mb-#{spacing_value(bottom)}" if bottom
          classes << "ml-#{spacing_value(left)}" if left
          classes.join(' ')
        end

        def map_font_size(size)
          FONT_SIZE_MAP[size] || "text-[#{rem(size)}]"
        end

        def map_corner_radius(radius)
          RADIUS_MAP[radius] || "rounded-[#{radius}px]"
        end

        # Color-name policy (rjui-offpalette-hex-dead-tailwind-class):
        # `bg-<name>` only resolves when the web @theme registers `--color-<name>`.
        # The tool can't read the project's globals.css, but colors.json
        # mode-completeness is the contract the theme mirrors: a name defined in
        # EVERY mode is a curated token (theme-safe); a name missing from some
        # mode is machine-extracted (light-only) and would emit a dead class —
        # invisible, and worse, `white`/`black` silently hit Tailwind builtins
        # that never follow dark mode. Those resolve back to their hex as an
        # arbitrary value (visible, static) with a build warning.
        # theme_safe: Set of names defined in all modes; fallbacks: name=>hex.
        def configure_palette(theme_safe:, fallbacks:)
          @theme_safe_colors = theme_safe
          @color_fallbacks = fallbacks
          @warned_colors = {}
        end

        def reset_palette!
          @theme_safe_colors = nil
          @color_fallbacks = nil
          @warned_colors = nil
        end

        def map_color(color, prefix = 'bg')
          return '' unless color

          return "#{prefix}-[#{color}]" if color.start_with?('#')

          # Unconfigured (direct helper use / older callers): legacy behavior.
          return "#{prefix}-#{color}" if @theme_safe_colors.nil? || @theme_safe_colors.include?(color)

          hex = @color_fallbacks&.[](color)
          if hex
            warn_off_palette(color, "resolving to #{hex}")
            "#{prefix}-[#{hex}]"
          else
            # Name outside colors.json entirely (custom Tailwind class?):
            # keep it, but flag it — a dead class here is on the author.
            warn_off_palette(color, 'not in colors.json; emitting as-is')
            "#{prefix}-#{color}"
          end
        end

        def warn_off_palette(name, detail)
          @warned_colors ||= {}
          return if @warned_colors[name]

          @warned_colors[name] = true
          Core::Logger.warn(
            "Color '#{name}' is not defined for every mode in colors.json — " \
            "Tailwind @theme cannot resolve it (#{detail}). Add it to all modes " \
            'in colors.json (and the @theme block) to make it theme-aware.'
          )
        end

        def map_width(width)
          case width
          when 'matchParent'
            'w-full'
          when 'wrapContent'
            'w-fit'
          when Numeric
            "w-[#{width}px]"
          when String
            css_arbitrary(width, 'w')
          else
            ''
          end
        end

        def map_height(height)
          case height
          when 'matchParent'
            'h-full'
          when 'wrapContent'
            'h-fit'
          when Numeric
            "h-[#{height}px]"
          when String
            css_arbitrary(height, 'h')
          else
            ''
          end
        end

        # *type*: the node's — a Button declares Left / Center / Right only.
        # *attribute*: a path for a textAlign declared inside an object
        # (%w[highlightAttributes textAlign] — Left / Right / Center only).
        def map_text_align(align, type = nil, attribute = 'textAlign')
          case JsonUIShared::EnumSpelling.lowered(align, type || 'Label', attribute)
          when 'center'
            'text-center'
          when 'right'
            'text-right'
          when 'left'
            'text-left'
          else
            ''
          end
        end

        def map_orientation(orientation)
          case JsonUIShared::EnumSpelling.lowered(orientation, 'View', 'orientation')
          when 'horizontal'
            'flex flex-row'
          when 'vertical'
            'flex flex-col'
          else
            ''
          end
        end

        def map_shadow(shadow)
          return '' unless shadow

          if shadow.is_a?(Hash)
            # Custom shadow: { radius: 5, offsetX: 0, offsetY: 2, color: "#000" }
            radius = shadow['radius'] || 5
            offset_x = shadow['offsetX'] || 0
            offset_y = shadow['offsetY'] || 2
            color = shadow['color'] || 'rgba(0,0,0,0.1)'
            color = shadow_color_with_alpha(color, shadow['opacity']) if shadow['opacity']
            "[box-shadow:#{offset_x}px_#{offset_y}px_#{radius}px_#{color}]"
          elsif shadow.is_a?(String) && shadow.include?('|')
            # The pipe form is the UIKit contract
            # 'color|offsetX|offsetY|opacity|radius' — exactly five fields;
            # anything else draws nothing (the canonical guard all render
            # paths share).
            parts = shadow.split('|', -1)
            return '' unless parts.length == 5
            color = shadow_color_with_alpha(parts[0], parts[3].to_f)
            "[box-shadow:#{parts[1].to_f}px_#{parts[2].to_f}px_#{parts[4].to_f}px_#{color}]"
          elsif shadow.is_a?(String)
            SHADOW_MAP[shadow] || 'shadow'
          elsif shadow == true
            'shadow'
          else
            ''
          end
        end

        def map_opacity(opacity)
          return '' unless opacity

          closest = OPACITY_MAP.keys.min_by { |k| (k - opacity.to_f).abs }
          OPACITY_MAP[closest]
        end

        def map_border(border_width, border_color, border_style = nil)
          classes = []

          if border_width
            classes << case border_width
                       when 0 then 'border-0'
                       when 1 then 'border'
                       when 2 then 'border-2'
                       when 4 then 'border-4'
                       when 8 then 'border-8'
                       else "border-[#{border_width}px]"
                       end
          end

          classes << map_color(border_color, 'border') if border_color
          classes << map_border_style(border_style) if border_style
          classes.compact.reject(&:empty?).join(' ')
        end

        # Fold a 0..1 opacity into the colour as a #RRGGBBAA alpha byte —
        # box-shadow has no separate opacity channel. Non-hex colours pass
        # through untouched.
        def shadow_color_with_alpha(color, opacity)
          alpha = (opacity.to_f.clamp(0.0, 1.0) * 255).round
          h = color.to_s.strip
          if h =~ /\A#([0-9a-fA-F]{6})\z/
            format('#%s%02X', Regexp.last_match(1), alpha)
          elsif h =~ /\A#([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])\z/
            m = Regexp.last_match
            format('#%s%s%s%s%s%s%02X', m[1], m[1], m[2], m[2], m[3], m[3], alpha)
          else
            h
          end
        end

        # A border drawn OVER the content, inside the box: an outline pulled
        # in by its own width, so it takes no layout space (user ruling B,
        # 2026-10-05 — see BaseConverter's border block). Width 0 draws
        # nothing, as `border-0` did.
        # A border width as a CSS px length (2 -> "2px", 1.5 -> "1.5px").
        def css_px(value)
          number = value.is_a?(Float) && value == value.to_i ? value.to_i : value
          "#{number}px"
        end

        def map_border_over_content(border_width, border_color, border_style = nil)
          return '' if border_width.nil? || border_width.to_f <= 0

          width = border_width.is_a?(Float) && border_width == border_width.to_i ? border_width.to_i : border_width
          classes = ["outline-[length:#{width}px]", "outline-offset-[-#{width}px]"]
          classes << map_color(border_color, 'outline') if border_color
          style_class = map_border_style(border_style).sub('border-', 'outline-')
          classes << (style_class.empty? ? 'outline-solid' : style_class)
          classes.compact.reject(&:empty?).join(' ')
        end

        def map_border_style(style)
          case JsonUIShared::EnumSpelling.lowered(style, 'common', 'borderStyle')
          when 'dashed'
            'border-dashed'
          when 'dotted'
            'border-dotted'
          when 'solid'
            'border-solid'
          else
            ''
          end
        end

        def map_font_weight(weight)
          return '' unless weight

          # The SSoT declares fontWeight ["string","number"], and CSS takes a
          # numeric font-weight verbatim — but the name table answered '' for
          # `600`, so the numeric face silently vanished from the emit
          # (run 6: ios active, android/web inert on the same declaration).
          # A number becomes the arbitrary-value class; Tailwind reads a bare
          # number in `font-[...]` as font-weight, not family.
          key = weight.to_s.downcase
          return "font-[#{key}]" if key.match?(/\A\d{1,4}\z/)

          FONT_WEIGHT_MAP[key] || ''
        end

        # Map font attribute - can be weight name or font family
        def map_font(font)
          return '' unless font

          font_lower = font.to_s.downcase

          # Weight names that should map to font-weight
          weight_names = %w[bold semibold medium light thin extralight heavy black normal]
          if weight_names.include?(font_lower)
            return FONT_WEIGHT_MAP[font_lower] || ''
          end

          # Font family names
          case font_lower
          when 'monospace', 'mono'
            'font-mono'
          when 'sans', 'sans-serif'
            'font-sans'
          when 'serif'
            'font-serif'
          else
            # Custom font - return empty, would need CSS custom font-family
            ''
          end
        end

        def map_gap(spacing)
          return '' unless spacing

          "gap-#{spacing_value(spacing)}"
        end

        # A single-run Label's alignment classes: it is a flex ROW, so
        # `items-*` is its vertical and `justify-*` its horizontal. The
        # vertical is the one gravity names (top / bottom / centerVertical,
        # center), else the middle; across, textAlign's position, else the
        # horizontal gravity names (left / right / centerHorizontal, center),
        # else the start (no class). LabelConverter and a responsive gravity
        # override (ResponsiveHelper#responsive_gravity_classes) both read it,
        # so a size class's gravity lands on the same axes as the base one.
        def map_label_gravity(gravity, text_align = nil)
          parts = if gravity.is_a?(Array) then gravity.map(&:to_s)
                  elsif gravity.nil? then []
                  else gravity.to_s.split('|')
                  end
          tokens = parts.map { |g| JsonUIShared::EnumSpelling.lowered(g.strip, 'common', 'gravity') || g.strip.downcase }
          classes = [if tokens.include?('top') then 'items-start'
                     elsif tokens.include?('bottom') then 'items-end'
                     else 'items-center'
                     end]
          across = case JsonUIShared::EnumSpelling.lowered(text_align, 'Label', 'textAlign')
                   when 'center' then 'justify-center'
                   when 'right' then 'justify-end'
                   when 'left' then 'justify-start'
                   else
                     if (tokens & %w[centerhorizontal center_horizontal center]).any? then 'justify-center'
                     elsif tokens.include?('right') || tokens.include?('end') then 'justify-end'
                     elsif tokens.include?('left') || tokens.include?('start') then 'justify-start'
                     end
                   end
          classes << across if across
          line_align = label_gravity_text_align(gravity, text_align)
          classes << line_align if line_align
          classes
        end

        # The lines of a Label follow its gravity across when it declares no
        # textAlign (textAlign's own text-* comes from the base converter):
        # `text-center` for center / centerHorizontal, `text-right` for right,
        # `text-left` for left; nil otherwise. The flex `justify-*` above
        # places the text's box; a wrapped or multi-line text fills its row,
        # and only text-align places its lines (the SSoT's Label.textAlign,
        # 4f round 6: until jsonui-cli 1.9.0 they stayed at the start).
        def label_gravity_text_align(gravity, text_align = nil)
          return nil if text_align.is_a?(String) && !text_align.empty?

          parts = if gravity.is_a?(Array) then gravity.map(&:to_s)
                  elsif gravity.nil? then []
                  else gravity.to_s.split('|')
                  end
          tokens = parts.map { |g| JsonUIShared::EnumSpelling.lowered(g.strip, 'common', 'gravity') || g.strip.downcase }
          if (tokens & %w[centerhorizontal center_horizontal center]).any? then 'text-center'
          elsif tokens.include?('right') || tokens.include?('end') then 'text-right'
          elsif tokens.include?('left') || tokens.include?('start') then 'text-left'
          end
        end

        # Map gravity attribute based on orientation
        # Flexbox behavior:
        # - flex-row (horizontal): items-* controls vertical alignment, justify-* controls horizontal alignment
        # - flex-col (vertical): items-* controls horizontal alignment, justify-* controls vertical alignment
        def map_gravity(gravity, orientation = nil)
          return [] unless gravity

          classes = []
          gravity_str = gravity.is_a?(Array) ? gravity.join('|') : gravity.to_s
          is_horizontal = JsonUIShared::EnumSpelling.lowered(orientation, 'View', 'orientation') == 'horizontal'

          if is_horizontal
            # orientation: "horizontal" (flex-row)
            # items-* = vertical alignment, justify-* = horizontal alignment

            # Vertical alignment (cross-axis for flex-row)
            if gravity_str.include?('centerVertical')
              classes << 'items-center'
            elsif gravity_str.include?('top')
              classes << 'items-start'
            elsif gravity_str.include?('bottom')
              classes << 'items-end'
            end

            # Horizontal alignment (main-axis for flex-row)
            if gravity_str.include?('centerHorizontal')
              classes << 'justify-center'
            elsif gravity_str.include?('left')
              classes << 'justify-start'
            elsif gravity_str.include?('right')
              classes << 'justify-end'
            end

            # Handle "center" (both directions)
            if gravity_str == 'center' || (gravity_str.include?('center') && !gravity_str.include?('centerVertical') && !gravity_str.include?('centerHorizontal'))
              classes << 'items-center' unless classes.any? { |c| c.start_with?('items-') }
              classes << 'justify-center' unless classes.any? { |c| c.start_with?('justify-') }
            end
          else
            # orientation: "vertical" (flex-col) or not specified (default to vertical behavior)
            # items-* = horizontal alignment, justify-* = vertical alignment

            # Horizontal alignment (cross-axis for flex-col). Read by TOKEN:
            # `include?('center')` also matched `centerVertical`, so a gravity
            # that names only the vertical axis centred the horizontal one as
            # well — on web only, where ios and android leave it at the
            # container default (attribute_semantics.json -> gravityDefaults).
            tokens = gravity_str.split('|').map(&:strip)
            if tokens.include?('centerHorizontal') || tokens.include?('center')
              classes << 'items-center'
            elsif gravity_str.include?('right')
              classes << 'items-end'
            elsif gravity_str.include?('left')
              classes << 'items-start'
            end

            # Vertical alignment (main-axis for flex-col)
            if gravity_str.include?('centerVertical')
              classes << 'justify-center'
            elsif gravity_str.include?('bottom')
              classes << 'justify-end'
            elsif gravity_str.include?('top')
              classes << 'justify-start'
            end

            # Handle "center" (both directions)
            if gravity_str == 'center' && !classes.any? { |c| c.start_with?('justify-') }
              classes << 'justify-center'
            end
          end

          classes
        end

        # `hidden: true` is the boolean shorthand for visibility:"invisible":
        # the component keeps its layout space but is not drawn and is
        # hidden from accessibility. Tailwind `invisible` (visibility:hidden)
        # gives exactly that; `hidden` (display:none) would collapse the
        # space, which is `visibility:"gone"` semantics — not this attribute.
        # `flexWrap` was defined in the attribute tables but nothing in the
        # web codegen read it, so "wrap" silently stayed nowrap
        # (rjui-view-flexwrap-attribute-dropped). The three enum values come
        # from view_attributes.rb.
        FLEX_WRAP_MAP = {
          'nowrap' => 'flex-nowrap',
          'wrap' => 'flex-wrap',
          'wrap-reverse' => 'flex-wrap-reverse',
        }.freeze

        def map_flex_wrap(value)
          FLEX_WRAP_MAP[value.to_s] || ''
        end

        def map_visibility(hidden)
          hidden ? 'invisible' : ''
        end

        # Layout direction: reverse the children of an oriented container.
        #
        # `direction` alone means nothing — the canonical semantics (SJUIView,
        # kjui container_component) are "vertical + bottomToTop reverses" and
        # "horizontal + rightToLeft reverses"; every other combination is normal
        # order. So the reverse value has to agree with the orientation, which is
        # why this takes both.
        def map_direction(direction, orientation = nil)
          d = JsonUIShared::EnumSpelling.lowered(direction, 'View', 'direction')
          o = JsonUIShared::EnumSpelling.lowered(orientation, 'View', 'orientation')
          return 'flex-col-reverse' if o == 'vertical' && d == 'bottomtotop'
          return 'flex-row-reverse' if o == 'horizontal' && d == 'righttoleft'
          # No other combination moves anything: the reverse value must agree
          # with the orientation ("a vertical stack honours bottomToTop, a
          # horizontal one rightToLeft"). The old items-end arm anchored a
          # vertical column's children to the trailing edge for rightToLeft —
          # measured against the axis-gated faces it was the ONE platform
          # moving pixels (SafeAreaView/direction__righttoleft, run
          # 31243724782 cross-effect: android and ios correctly inert).

          ''
        end

        def map_overflow(clip_to_bounds)
          clip_to_bounds ? 'overflow-hidden' : ''
        end

        def map_z_index(z_index)
          return '' unless z_index

          case z_index
          when 0 then 'z-0'
          when 10 then 'z-10'
          when 20 then 'z-20'
          when 30 then 'z-30'
          when 40 then 'z-40'
          when 50 then 'z-50'
          else "z-[#{z_index}]"
          end
        end

        def map_flex_grow(weight)
          return '' unless weight

          # Fractional weights (0.8, 1.2) are legal — Tailwind arbitrary
          # values accept decimals — so keep the number as-is instead of
          # truncating (0.8.to_i == 0 collapsed ratio layouts to flex-none).
          w = weight.to_f
          w_str = w == w.to_i ? w.to_i.to_s : w.to_s
          base = if w == 0
                   'flex-none'
                 elsif w == 1
                   'flex-1'
                 else
                   "flex-[#{w_str}]"
                 end
          # `flex-1` / `flex-[N]` children need `min-w-0 min-h-0` so the
          # CSS default `min-*-size: auto` doesn't let long descendants
          # (long <pre>, prose, etc.) push the flex container past the
          # intended weight slice. `flex-none` opts out of growth entirely
          # and doesn't need the tweak.
          w == 0 ? base : "#{base} min-w-0 min-h-0"
        end

        # Min/Max Width/Height constraints
        def map_min_width(value)
          return '' unless value
          case value
          when 'matchParent' then 'min-w-full'
          when Numeric then "min-w-[#{value}px]"
          when String then css_arbitrary(value, 'min-w')
          else ''
          end
        end

        def map_max_width(value)
          return '' unless value
          case value
          when 'matchParent' then 'max-w-full'
          when Numeric then "max-w-[#{value}px]"
          when String then css_arbitrary(value, 'max-w')
          else ''
          end
        end

        def map_min_height(value)
          return '' unless value
          case value
          when 'matchParent' then 'min-h-full'
          when Numeric then "min-h-[#{value}px]"
          when String then css_arbitrary(value, 'min-h')
          else ''
          end
        end

        def map_max_height(value)
          return '' unless value
          case value
          when 'matchParent' then 'max-h-full'
          when Numeric then "max-h-[#{value}px]"
          when String then css_arbitrary(value, 'max-h')
          else ''
          end
        end

        # RTL-aware paddings (paddingStart -> ps-, paddingEnd -> pe-)
        def map_rtl_paddings(start_pad, end_pad)
          classes = []
          classes << "ps-#{spacing_value(start_pad)}" if start_pad
          classes << "pe-#{spacing_value(end_pad)}" if end_pad
          classes.join(' ')
        end

        # RTL-aware margins (startMargin -> ms-, endMargin -> me-)
        def map_rtl_margins(start_margin, end_margin)
          classes = []
          classes << "ms-#{spacing_value(start_margin)}" if start_margin
          classes << "me-#{spacing_value(end_margin)}" if end_margin
          classes.join(' ')
        end

        # The value part of a spacing class (padding, margin, gap): the
        # declared length as rem, N / 16 — `[1.625rem]` for 26, `[0.75rem]`
        # for 12, `[0rem]` for 0 — never a step of Tailwind's spacing scale.
        # At the default 16px root it is the declared px exactly; a viewer
        # who raises the browser's default font size gets spacing that grows
        # with the text, as the scale steps did (the text's own classes are
        # rem). Division by 16 is exact in decimal (1/16 = 0.0625), and it is
        # done in BigDecimal, so no length picks up a float tail.
        #
        # History: until 1.9.14 every length was rounded to the NEAREST scale
        # step (22 drew 20px; ticket rjui-spacing-rounds-to-the-tailwind-
        # scale); 1.9.14 wrote the exact length in px, which stopped spacing
        # following the browser's font size (ticket
        # rjui-spacing-px-does-not-follow-the-browser-font-size); 1.9.15
        # writes the exact length in rem. A non-number passes through as
        # written.
        def spacing_value(value)
          return '[0rem]' if value.nil?
          return value.to_s unless value.is_a?(Numeric)

          "[#{rem(value)}]"
        end

        # A spacing length for CSS (an inline style, a calc): N / 16 rem, the
        # same value spacing_value writes into a class. A numeric string
        # reads as its number; anything else is written as it always was, in
        # px.
        def rem(value)
          number = value.is_a?(Numeric) ? value : (Float(value.to_s) rescue nil)
          return "#{value}px" if number.nil?

          "#{(BigDecimal(number.to_s) / 16).to_s('F').sub(/\.0\z/, '')}rem"
        end

        # Insets (alternative padding format - same as padding array)
        def map_insets(insets)
          map_padding(insets)
        end

        # Inset horizontal
        def map_inset_horizontal(value)
          return '' unless value
          "px-#{spacing_value(value)}"
        end

        private

        # Convert a CSS string value (e.g. "100vh", "50vw", "calc(100% - 16px)")
        # to a Tailwind arbitrary value class like "h-[100vh]".
        CSS_UNIT_RE = /\A[\d.]+(vh|vw|rem|em|%|px|pt|cm|mm|in|ch|ex|svh|svw|dvh|dvw|lvh|lvw)\z/

        def css_arbitrary(value, prefix)
          return '' if value.nil? || value.empty?

          if value.match?(CSS_UNIT_RE) || value.start_with?('calc(')
            "#{prefix}-[#{value}]"
          else
            ''
          end
        end

      end
    end
  end
end
