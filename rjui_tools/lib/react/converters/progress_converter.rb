# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class ProgressConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          base_style_attr = build_base_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          value_attr = build_value_attr
          # Canonical Progress value range is 0..1 (ios/android render it so);
          # max=100 shrank a 0.5 value to a 0.5% sliver — invisible, which is
          # how every web tint measured inert (33 cross-effect).
          literal_value = attributes['value'] || attributes['progress']
          default_max = literal_value.is_a?(Numeric) && literal_value <= 1 ? 1 : 100
          max_attr = " max={#{attributes['maximumValue'] || default_max}}"

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<progress#{id_attr} className="#{class_name}"#{value_attr}#{max_attr}#{base_style_attr}#{testid_attr}#{tag_attr} />
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          base = super
          # appearance-none strips the native progress chrome, so the element
          # has no intrinsic content — wrapContent's h-fit collapses it to
          # ZERO height and nothing rendered at all (33: every web progress
          # comparison measured blank-vs-blank). The component's h-2 default
          # must win when no height is declared.
          explicit_height = attributes['height'] && attributes['height'] != 'wrapContent'
          base = base.split.reject { |c| c == 'h-fit' }.join(' ') unless explicit_height
          classes = [base]

          classes << 'w-full'

          # Height
          height = attributes['progressHeight'] || attributes['barHeight']
          if height
            classes << "h-[#{height}px]"
          else
            classes << 'h-2'
          end

          classes << 'rounded-full'
          classes << 'appearance-none'

          # Custom progress bar styling
          classes << '[&::-webkit-progress-bar]:rounded-full'

          # Track color (CSS variable — see the tint comment below).
          track_color = attributes['trackTintColor'] || attributes['trackColor']
          if track_color
            @dynamic_styles['--pb-color'] = color_style_expr(track_color)
            classes << '[&::-webkit-progress-bar]:bg-[color:var(--pb-color)]'
          else
            classes << '[&::-webkit-progress-bar]:bg-gray-200'
          end

          classes << '[&::-webkit-progress-value]:rounded-full'

          # Progress color. The raw value may resolve to a PALETTE NAME
          # (bg-[dark_red] is not a color) — route through CSS variables the
          # inline style sets from ColorManager, so the pseudo-elements get
          # a real color on every build (33 cross-effect).
          tint_color = attributes['tintColor'] || attributes['progressTintColor']
          if tint_color
            @dynamic_styles['--pv-color'] = color_style_expr(tint_color)
            classes << '[&::-webkit-progress-value]:bg-[color:var(--pv-color)]'
            classes << '[&::-moz-progress-bar]:bg-[color:var(--pv-color)]'
          else
            classes << '[&::-webkit-progress-value]:bg-blue-500'
            classes << '[&::-moz-progress-bar]:bg-blue-500'
          end

          finalize_classes(classes)
        end

        def build_value_attr
          value = with_bind_fallback(attributes['value'] || attributes['progress']) || 0

          if has_binding?(value)
            prop = extract_binding_property(value)
            " value={#{prop}}"
          else
            " value={#{value}}"
          end
        end

        def build_base_style_attr
          build_style_attr
        end
      end
    end
  end
end
