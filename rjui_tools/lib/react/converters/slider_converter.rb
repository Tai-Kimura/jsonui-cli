# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class SliderConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          base_style_attr = build_base_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          # Canonical names are minimum/maximum; minimumValue/minValue and
          # maximumValue/maxValue are the definitions aliases.
          #
          # The declared defaults are 0 .. 1 (attribute_definitions Slider), and
          # this defaulted to 100 — so `value: 0.5` meant HALF on ios and 0.5%
          # here, from the same layout. The three platforms had each invented a
          # ceiling because the SSoT declared none; it declares 1 now.
          min_value = attributes['minimum'] || 0
          max_value = attributes['maximum'] || 1
          step_value = attributes['step']

          # Handle range array format: [min, max]
          if attributes['range'].is_a?(Array) && attributes['range'].length == 2
            min_value = attributes['range'][0]
            max_value = attributes['range'][1]
          end

          value_attr = build_value_attr
          on_change = build_on_change
          disabled_attr = build_disabled_attr

          # `min` / `max` / `step` are JSX attributes in CODE position, so a
          # bound value was interpolated raw and the emit was `min={@{v}}` —
          # not a program. Every Slider written the way the SSoT describes
          # (all four bounds spellings are declared `["number","binding"]`)
          # broke the consumer's build outright, and no validator said a word.
          min_expr = jsx_value_expr(min_value)
          max_expr = jsx_value_expr(max_value)
          step_attr = step_value ? " step={#{jsx_value_expr(step_value)}}" : ''

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<input#{id_attr} type="range" className="#{class_name}" min={#{min_expr}} max={#{max_expr}}#{step_attr}#{value_attr}#{on_change}#{disabled_attr}#{base_style_attr}#{testid_attr}#{tag_attr} />
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          classes << 'w-full'
          classes << 'cursor-pointer'

          # Disabled state
          if attributes['enabled'] == false
            classes << 'opacity-50 cursor-not-allowed'
          elsif has_binding?(attributes['enabled'])
            binding_expr = extract_binding_property(attributes['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50 cursor-not-allowed' : ''}"
          end

          # Track colours go into @dynamic_styles, which `build_class_name`
          # owns, so the ONE style attribute BaseConverter renders carries
          # them. A second `style={...}` of our own is how Fx0375 ended up
          # with a duplicate JSX attribute (TS17001) — and the losing copy
          # held the raw palette name, which is not a colour at all.
          #
          # `progressTintColor` / `trackTintColor` are the spellings
          # attribute_definitions declares: the filled track and the unfilled
          # one. `tintColor` is the generic accent behind the first, and
          # minimum/maximumTrackTintColor are the undeclared UIKit legacy
          # behind both (slider.trackColors in attribute_semantics.json).
          progress_tint = attributes['progressTintColor'] || attributes['tintColor'] ||
                          attributes['minimumTrackTintColor']
          @dynamic_styles['accentColor'] = color_style_expr(progress_tint) if progress_tint

          # The UNFILLED track is drawn by ::-webkit-slider-runnable-track, and
          # the native control paints straight over the element's own
          # background — measured: a `backgroundColor` style on the input is
          # pixel-identical to no colour at all, while the pseudo-element
          # accepts one (and does NOT need `appearance: none`, which would
          # take the thumb with it).
          track_tint = attributes['trackTintColor'] || attributes['maximumTrackTintColor']
          if track_tint
            classes << TailwindMapper.map_color(
              track_tint, '[&::-webkit-slider-runnable-track]:bg'
            )
          end

          finalize_classes(classes)
        end

        def build_value_attr
          value = with_bind_fallback(attributes['value'])

          if value && has_binding?(value)
            prop = extract_binding_property(value)
            " value={#{prop}}"
          elsif value
            " defaultValue={#{value}}"
          else
            ''
          end
        end

        def build_on_change
          # If custom handler is defined, use it (passing the event object).
          # onValueChanged is the definitions alias of onValueChange.
          handler = attributes['onValueChange']
          if handler && has_binding?(handler)
            prop = extract_binding_property(handler)
            return " onChange={(e) => #{prop}?.(Number(e.target.value))}"
          end

          # Auto-generate onChange from value binding property
          # e.g., value: "@{sliderValue}" -> onChange={(e) => data.onSliderValueChange?.(Number(e.target.value))}
          value = with_bind_fallback(attributes['value'])
          if value && has_binding?(value)
            property_name = extract_raw_binding_property(value)
            handler_name = "on#{capitalize_first(property_name)}Change"
            return " onChange={(e) => data.#{handler_name}?.(Number(e.target.value))}"
          end

          ''
        end

        def capitalize_first(str)
          return str if str.nil? || str.empty?

          str[0].upcase + str[1..]
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


        def build_base_style_attr
          build_style_attr
        end
      end
    end
  end
end
