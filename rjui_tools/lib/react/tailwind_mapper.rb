# frozen_string_literal: true

module RjuiTools
  module React
    class TailwindMapper
      # Padding mapping (px to Tailwind)
      PADDING_MAP = {
        0 => '0', 1 => 'px', 2 => '0.5', 4 => '1', 6 => '1.5',
        8 => '2', 10 => '2.5', 12 => '3', 14 => '3.5', 16 => '4',
        20 => '5', 24 => '6', 28 => '7', 32 => '8', 36 => '9',
        40 => '10', 44 => '11', 48 => '12', 56 => '14', 64 => '16'
      }.freeze

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
            "p-#{closest_padding(padding)}"
          when Array
            map_padding_array(padding)
          else
            ''
          end
        end

        def map_padding_array(arr)
          case arr.length
          when 1
            "p-#{closest_padding(arr[0])}"
          when 2
            "py-#{closest_padding(arr[0])} px-#{closest_padding(arr[1])}"
          when 4
            classes = []
            classes << "pt-#{closest_padding(arr[0])}"
            classes << "pr-#{closest_padding(arr[1])}"
            classes << "pb-#{closest_padding(arr[2])}"
            classes << "pl-#{closest_padding(arr[3])}"
            classes.join(' ')
          else
            ''
          end
        end

        def map_individual_paddings(top, right, bottom, left)
          classes = []
          classes << "pt-#{closest_padding(top)}" if top
          classes << "pr-#{closest_padding(right)}" if right
          classes << "pb-#{closest_padding(bottom)}" if bottom
          classes << "pl-#{closest_padding(left)}" if left
          classes.join(' ')
        end

        def map_margin(margin)
          case margin
          when Numeric
            "m-#{closest_padding(margin)}"
          when Array
            map_margin_array(margin)
          else
            ''
          end
        end

        def map_margin_array(arr)
          case arr.length
          when 1
            "m-#{closest_padding(arr[0])}"
          when 2
            "my-#{closest_padding(arr[0])} mx-#{closest_padding(arr[1])}"
          when 4
            classes = []
            classes << "mt-#{closest_padding(arr[0])}"
            classes << "mr-#{closest_padding(arr[1])}"
            classes << "mb-#{closest_padding(arr[2])}"
            classes << "ml-#{closest_padding(arr[3])}"
            classes.join(' ')
          else
            ''
          end
        end

        def map_individual_margins(top, right, bottom, left)
          classes = []
          classes << "mt-#{closest_padding(top)}" if top
          classes << "mr-#{closest_padding(right)}" if right
          classes << "mb-#{closest_padding(bottom)}" if bottom
          classes << "ml-#{closest_padding(left)}" if left
          classes.join(' ')
        end

        def map_font_size(size)
          FONT_SIZE_MAP[size] || "text-[#{size}px]"
        end

        def map_corner_radius(radius)
          RADIUS_MAP[radius] || "rounded-[#{radius}px]"
        end

        def map_color(color, prefix = 'bg')
          return '' unless color

          if color.start_with?('#')
            "#{prefix}-[#{color}]"
          else
            "#{prefix}-#{color}"
          end
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

        def map_text_align(align)
          case align&.downcase
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
          case orientation&.downcase
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
            "[box-shadow:#{offset_x}px_#{offset_y}px_#{radius}px_#{color}]"
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

        def map_border_style(style)
          case style&.downcase
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

          FONT_WEIGHT_MAP[weight.to_s.downcase] || ''
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

          "gap-#{closest_padding(spacing)}"
        end

        # Map gravity attribute based on orientation
        # Flexbox behavior:
        # - flex-row (horizontal): items-* controls vertical alignment, justify-* controls horizontal alignment
        # - flex-col (vertical): items-* controls horizontal alignment, justify-* controls vertical alignment
        def map_gravity(gravity, orientation = nil)
          return [] unless gravity

          classes = []
          gravity_str = gravity.is_a?(Array) ? gravity.join('|') : gravity.to_s
          is_horizontal = orientation&.downcase == 'horizontal'

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

            # Horizontal alignment (cross-axis for flex-col)
            if gravity_str.include?('centerHorizontal') || gravity_str.include?('center')
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

        def map_visibility(hidden)
          hidden ? 'hidden' : ''
        end

        def map_direction(direction)
          case direction&.downcase
          when 'rtl'
            'rtl'
          when 'ltr'
            'ltr'
          else
            ''
          end
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

          w = weight.to_i
          base = case w
                 when 0 then 'flex-none'
                 when 1 then 'flex-1'
                 else "flex-[#{w}]"
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
          classes << "ps-#{closest_padding(start_pad)}" if start_pad
          classes << "pe-#{closest_padding(end_pad)}" if end_pad
          classes.join(' ')
        end

        # RTL-aware margins (startMargin -> ms-, endMargin -> me-)
        def map_rtl_margins(start_margin, end_margin)
          classes = []
          classes << "ms-#{closest_padding(start_margin)}" if start_margin
          classes << "me-#{closest_padding(end_margin)}" if end_margin
          classes.join(' ')
        end

        # Insets (alternative padding format - same as padding array)
        def map_insets(insets)
          map_padding(insets)
        end

        # Inset horizontal
        def map_inset_horizontal(value)
          return '' unless value
          "px-#{closest_padding(value)}"
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

        def closest_padding(value)
          return '0' unless value

          closest = PADDING_MAP.keys.min_by { |k| (k - value).abs }
          PADDING_MAP[closest]
        end
      end
    end
  end
end
