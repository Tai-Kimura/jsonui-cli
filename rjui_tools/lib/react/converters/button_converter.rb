# frozen_string_literal: true

require_relative 'base_converter'
require_relative '../../core/frameworks'

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
            text = convert_text_binding(attributes['text'] || '')
            body = "#{build_image_markup}#{text}"

            # If href is specified, wrap with the framework's Link component
            if attributes['href']
              href = attributes['href']
              link_attr = Core::Frameworks.for(@config).link_href_attribute
              "#{indent_str(indent)}<Link #{link_attr}=\"#{href}\"><button#{id_attr}#{build_button_type_attr} className=\"#{class_name}\"#{style_attr}#{on_click}#{disabled_attr}#{testid_attr}#{tag_attr}>#{body}</button></Link>"
            else
              "#{indent_str(indent)}<button#{id_attr}#{build_button_type_attr} className=\"#{class_name}\"#{style_attr}#{on_click}#{disabled_attr}#{testid_attr}#{tag_attr}>#{body}</button>"
            end
          end

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # An icon needs a layout box to sit in, and an icon+label pair needs
          # a gap. A text-only button keeps its previous class list exactly.
          if attributes['image']
            classes << 'inline-flex items-center justify-center'
            # Fixed gap on purpose: `spacing` is not declared for Button in
            # attribute_definitions.json, and reading it here would add one
            # more undeclared consumption instead of shrinking the list.
            # Declaring it is an SSoT change that affects all three platforms.
            classes << 'gap-2' if attributes['text']
          end

          # Default button styles
          classes << 'cursor-pointer'
          classes << 'transition-colors'

          # Hover state. tapBackground (tap state) and
          # highlightBackground (highlighted state) are DISTINCT
          # attributes in the definitions/runtimes, but the web has a
          # single hover/active affordance — both map onto it here
          # (tapBackground wins when both are present).
          #
          # A bound state color cannot be a palette class — `map_color` sees a
          # string that does not start with `#`, calls it a palette name and
          # emits `hover:bg-@{v}`. The binding goes to a CSS custom property
          # that the variant utility reads back; see
          # BaseConverter#bound_state_color_class.
          tap_background = attributes['tapBackground'] || attributes['highlightBackground']
          if tap_background
            hover_color = bound_state_color_class(tap_background, custom_property: '--jui-tap-bg', prefix: 'hover:bg') ||
                          TailwindMapper.map_color(tap_background, 'hover:bg')
            classes << hover_color
          else
            classes << 'hover:opacity-80'
          end

          # Active/pressed state
          if tap_background
            active_color = bound_state_color_class(tap_background, custom_property: '--jui-tap-bg', prefix: 'active:bg') ||
                           TailwindMapper.map_color(tap_background, 'active:bg')
            classes << active_color
          end

          # Highlight text color on hover (hilightColor is the legacy
          # definitions alias of highlightColor)
          highlight_color = attributes['highlightColor']
          if highlight_color
            hover_text = bound_state_color_class(highlight_color, custom_property: '--jui-highlight-color', prefix: 'hover:text') ||
                         TailwindMapper.map_color(highlight_color, 'hover:text')
            classes << hover_text
          end

          # Disabled state
          if attributes['disabledBackground']
            disabled_bg = bound_state_color_class(attributes['disabledBackground'], custom_property: '--jui-disabled-bg', prefix: 'disabled:bg') ||
                          TailwindMapper.map_color(attributes['disabledBackground'], 'disabled:bg')
            classes << disabled_bg
          else
            classes << 'disabled:opacity-50'
          end

          if attributes['disabledFontColor']
            disabled_text = bound_state_color_class(attributes['disabledFontColor'], custom_property: '--jui-disabled-color', prefix: 'disabled:text') ||
                            TailwindMapper.map_color(attributes['disabledFontColor'], 'disabled:text')
            classes << disabled_text
          end

          classes << 'disabled:cursor-not-allowed'

          finalize_classes(classes)
        end

        def build_style_attr
          super

          # Corner radius. The static form keeps its own quoted-px spelling;
          # a bound one is already in `borderRadius` from the base pass, and
          # overwriting it here would put the characters `@{v}` back.
          corner_radius = attributes['cornerRadius']
          if corner_radius && !has_binding?(corner_radius)
            @dynamic_styles['borderRadius'] = "'#{corner_radius}px'"
          end

          # One renderer for every converter (BaseConverter#style_attr_for):
          # the SPREAD sentinel and the `React.CSSProperties` assertion a
          # custom-property key needs are handled in ONE place.
          style_attr_for(@dynamic_styles)
        end

        def build_on_click
          build_onclick_attr
        end

        def build_disabled_attr
          enabled = attributes['enabled']
          return '' if enabled.nil?

          if enabled.is_a?(String) && enabled.start_with?('@{') && enabled.end_with?('}')
            # Binding expression: @{isEnabled} -> disabled={!data.isEnabled}
            # (Bool data props generate as TS boolean — a string comparison
            # would be always-true and leave the control permanently disabled.)
            " disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' disabled'
          else
            ''
          end
        end

        # `image` was in the attribute tables but no converter read it, so an
        # icon-only Button rendered as an empty <button>: clickable, sized,
        # invisible (rjui-button-image-attribute-dropped). Resolution follows
        # Image#srcName — a bare name becomes /images/<name>.<ext>.
        #
        # A tinted icon is emitted as a masked box rather than an <img>: an
        # <img> cannot take the button's colour, so a `currentColor` SVG on a
        # dark toolbar stays black. The mask + bg-current pair inherits
        # `fontColor`, which is the class BaseConverter already emitted.
        def build_image_markup
          image = attributes['image']
          return '' if image.nil? || image.to_s.empty?

          src = build_image_src(image)
          size = 'w-[1.25em] h-[1.25em] shrink-0'

          if tinted_icon?
            styles = [
              "maskImage: `url(#{src})`",
              "WebkitMaskImage: `url(#{src})`",
              "maskSize: 'contain'",
              "WebkitMaskSize: 'contain'",
              "maskRepeat: 'no-repeat'",
              "WebkitMaskRepeat: 'no-repeat'",
              "maskPosition: 'center'",
              "WebkitMaskPosition: 'center'",
            ].join(', ')
            %(<span aria-hidden="true" className="#{size} bg-current" ) +
              %(style={{ #{styles} }} />)
          else
            %(<img src={`#{src}`} alt="#{image_alt(image)}" ) +
              %(className="#{size} object-contain" />)
          end
        end

        # `/images/<name>.<ext>` for a bare name, the binding for a bound one.
        def build_image_src(image)
          if has_binding?(image)
            "/images/${#{extract_binding_property(image)}}"
          else
            "/images/#{resolve_image_extension(image.to_s)}"
          end
        end

        # A button with no text has no accessible name, so the icon carries
        # it. Alongside text the icon is decorative and stays out of the
        # accessibility tree.
        def image_alt(image)
          return '' if attributes['text']
          return '' if has_binding?(image)

          image.to_s.sub(/\.[a-z0-9]+\z/i, '').tr('_-', '  ')
        end

        def tinted_icon?
          !!(attributes['tintColor'] || attributes['fontColor'])
        end

        private

        # Render button with partial attributes.
        #
        # Same runtime path as Label: the partials go to the generated
        # buttonType — declared `platform: react`, because it is the HTML
        # `type` attribute and nothing else. It matters more than it looks: a
        # <button> inside a <form> defaults to `submit`, so a plain action button
        # submits the form unless it says `button`.
        def build_button_type_attr
          type = attributes['buttonType'].to_s
          return '' unless %w[button submit reset].include?(type)

          " type=\"#{type}\""
        end

        # `partialText` helper so a pattern range and a localized text work,
        # matching iOS and Android.
        def render_partial_attributes_button(indent, id_attr, class_name, style_attr, on_click, disabled_attr, testid_attr, tag_attr)
          text_expr = text_runtime_expression(attributes['text'] || '')
          specs = build_partial_specs(attributes['partialAttributes'])

          lines = []
          lines << "#{indent_str(indent)}<button#{id_attr}#{build_button_type_attr} className=\"#{class_name}\"#{style_attr}#{on_click}#{disabled_attr}#{testid_attr}#{tag_attr}>"
          lines << "#{indent_str(indent + 2)}{partialText(#{text_expr}, #{specs})}"
          lines << "#{indent_str(indent)}</button>"
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
