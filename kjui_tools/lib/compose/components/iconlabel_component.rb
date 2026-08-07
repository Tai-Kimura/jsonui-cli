# frozen_string_literal: true

require_relative 'text_component'
require_relative '../helpers/bound_value'
require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/font_spec_helper'

module KjuiTools
  module Compose
    module Components
      # IconLabel — an icon and a label that share a selected state.
      #
      # The Compose codegen had no IconLabel at all: the type fell through to
      # `check_custom_component` and emitted `// TODO: Implement component type:
      # IconLabel`. Only four of its attributes showed up as coverage gaps
      # because the rest (`text`, `font`, `fontSize`, `fontColor`) are read by
      # text_component and the scan matches attribute names, not
      # (component, attribute) pairs.
      #
      # The layout follows IconLabelView.swift, which is the reference: the icon
      # and the text sit in a Row or a Column depending on `iconPosition`, spaced
      # by `iconMargin`, and the selected state swaps `icon_off` for `icon_on`
      # and `fontColor` for `selectedFontColor`.
      #
      # The undeclared legacy spellings (`icon`, `src`, `iconSize`, `iconColor`,
      # `tintColor`, `spacing`, `fontWeight`) are accepted too, because
      # DynamicIconLabelComponent reads those and a layout must not change
      # meaning between dynamic and generated mode.
      class IconLabelComponent
        # Matches IconLabelView.swift's own default.
        # 5 is the cross-platform canonical (IconLabelView.swift and the ios
        # dynamic converter both default to 5) — the KJUI dynamic 8f fallback
        # was the deviant side (32 parity re-measure).
        DEFAULT_ICON_MARGIN = 5
        DEFAULT_ICON_SIZE = 24

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          position = (json_data['iconPosition'] || 'Left').to_s.downcase
          vertical = %w[top bottom].include?(position)
          icon_first = !%w[right bottom].include?(position)

          container = vertical ? 'Column' : 'Row'
          spacing = icon_spacing(json_data)

          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          required_imports&.add(:arrangement)

          code = indent("#{container}(", depth)
          code += Helpers::ModifierBuilder.format(modifiers, depth)
          code += ",\n" unless modifiers.empty?
          code += "\n" if modifiers.empty?
          arrangement = vertical ? 'verticalArrangement' : 'horizontalArrangement'
          code += indent("#{arrangement} = Arrangement.spacedBy(#{spacing}.dp),", depth + 1) + "\n"
          cross = vertical ? 'horizontalAlignment = Alignment.CenterHorizontally' :
                             'verticalAlignment = Alignment.CenterVertically'
          code += indent(cross, depth + 1) + "\n"
          code += indent(") {", depth) + "\n"

          parts = [icon_code(json_data, depth + 1, required_imports),
                   text_code(json_data, depth + 1, required_imports)]
          parts.reverse! unless icon_first
          code += parts.compact.join("\n")
          code += "\n" + indent("}", depth)
          code
        end

        # `iconSize` is declared `["number", "array"]` — a number sizes both
        # edges, a two-element `[width, height]` sizes them separately (rjui
        # reads both). Only the number face was handled, so the declared array
        # face reached the source as a Ruby literal — `Modifier.size([40, 20].dp)`
        # is not Kotlin, which made the only two-axis spelling uncompilable.
        # NOT the same shape as CheckBox.iconSize, which is number-only for a
        # square glyph and must stay that way.
        def self.icon_size_call(value)
          if value.is_a?(Array) && value.length >= 2
            return "size(width = #{value[0]}.dp, height = #{value[1]}.dp)"
          end

          # A one-element array still means "both edges", the same as a number.
          scalar = value.is_a?(Array) ? value.first : value
          "size(#{scalar || DEFAULT_ICON_SIZE}.dp)"
        end

        # `iconMargin` is the declared row; `spacing` is the legacy spelling the
        # dynamic runtime reads.
        def self.icon_spacing(json_data)
          json_data['iconMargin'] || json_data['spacing'] || DEFAULT_ICON_MARGIN
        end

        # `selected` chooses between icon_on/icon_off and between
        # fontColor/selectedFontColor — without it neither pair means anything.
        def self.selected_condition(json_data)
          value = json_data['selected']
          return 'true' if value == true || value == 'true'
          return 'false' if value == false || value == 'false'
          return "data.#{Helpers::ModifierBuilder.extract_binding_property(value)}" if
            Helpers::ModifierBuilder.is_binding?(value)

          nil
        end

        def self.icon_code(json_data, depth, required_imports)
          on_icon = json_data['icon_on']
          off_icon = json_data['icon_off'] || json_data['icon'] || json_data['src']
          return nil if on_icon.nil? && off_icon.nil?

          condition = selected_condition(json_data)
          required_imports&.add(:image)
          required_imports&.add(:painter_resource)
          required_imports&.add(:r_class)

          # icon_off is the resting state, and iOS falls back to icon_on when
          # only that was supplied (IconLabelView.iconView).
          resting = off_icon || on_icon
          selected = on_icon || off_icon
          swaps = condition && condition != 'false' && selected != resting
          painter =
            if condition == 'true'
              drawable(selected)
            elsif swaps
              "if (#{condition}) #{drawable(selected)} else #{drawable(resting)}"
            else
              drawable(resting)
            end

          code = indent("Image(", depth) + "\n"
          code += indent("painter = #{painter},", depth + 1) + "\n"
          code += indent("contentDescription = #{quote(json_data['contentDescription'] || '')},", depth + 1) + "\n"
          code += indent("modifier = Modifier.#{icon_size_call(json_data['iconSize'])}", depth + 1)
          if (filter = icon_color_filter(json_data, condition, required_imports))
            required_imports&.add(:color_filter)
            code += ",\n" + indent("colorFilter = #{filter}", depth + 1)
          end
          code += "\n" + indent(")", depth)
          code
        end

        # Tint only when a colour was asked for. iOS tints the icon with the font
        # colour unconditionally, which would silently flatten a multi-colour
        # asset; the dynamic runtime tints only on iconColor/tintColor, and that
        # is the behaviour to match. selectedFontColor still reaches the icon,
        # because recolouring on selection is the point of the attribute.
        def self.icon_color_filter(json_data, condition, required_imports)
          explicit = json_data['iconColor'] || json_data['tintColor']
          selected_color = json_data['selectedFontColor']
          resting = explicit ? tint(explicit, required_imports) : 'null'

          return (explicit ? resting : nil) unless selected_color && condition

          on_tint = tint(selected_color, required_imports)
          return on_tint if condition == 'true'
          return explicit ? resting : nil if condition == 'false'

          "if (#{condition}) #{on_tint} else #{resting}"
        end

        def self.tint(color, required_imports)
          "ColorFilter.tint(#{Helpers::ResourceResolver.process_color(color, required_imports)})"
        end

        def self.text_code(json_data, depth, required_imports)
          text = json_data['text']
          return nil if text.nil?

          code = indent("Text(", depth) + "\n"
          # required_imports must ride along: when the extractor externalized
          # this text, the resolver emits stringResource(R.string.…) and the
          # imports have to register with it (missing them left every
          # IconLabel fixture uncompilable in the codegen parity host).
          code += indent("text = #{Helpers::ResourceResolver.process_text(text, required_imports)},", depth + 1)

          if (color = text_color(json_data, required_imports))
            code += "\n" + indent("color = #{color},", depth + 1)
          end
          if (size = json_data['fontSize'])
            required_imports&.add(:text_unit) if Helpers::BoundValue.bound?(size)
            code += "\n" + indent("fontSize = #{Helpers::BoundValue.sp(size, null_expr: 'TextUnit.Unspecified')},", depth + 1)
          end
          if (weight = font_weight(json_data))
            required_imports&.add(:font_weight)
            code += "\n" + indent("fontWeight = #{weight},", depth + 1)
          end
          # `textShadow` — same `{color, blur, offset: [x, y]}` contract as
          # Label (the UIKit runtime passes the identical JSON to both), and
          # this component never reached ANY shadow path (plan 49 lane C:
          # IconLabel.textShadow). The emitter is Label's, so the two cannot
          # drift.
          if json_data['textShadow']
            required_imports&.add(:shadow_style)
            shadow = TextComponent.text_shadow_expression(json_data['textShadow'], required_imports)
            code += "\n" + indent("style = TextStyle(#{shadow}),", depth + 1)
          end
          code = code.chomp(',')
          code += "\n" + indent(")", depth)
          code
        end

        def self.text_color(json_data, required_imports)
          base = json_data['fontColor']
          selected_color = json_data['selectedFontColor']
          condition = selected_condition(json_data)

          base_expr = base ? Helpers::ResourceResolver.process_color(base, required_imports) : nil
          return base_expr unless selected_color && condition

          on_expr = Helpers::ResourceResolver.process_color(selected_color, required_imports)
          return on_expr if condition == 'true'
          return base_expr if condition == 'false'

          "if (#{condition}) #{on_expr} else #{base_expr || 'Color.Unspecified'}"
        end

        # `font` is the declared row and carries a weight name on this component
        # (IconLabelConverter treats `font: "bold"` as a weight, not a family);
        # `fontWeight` is the legacy spelling the dynamic runtime reads.
        WEIGHT_NAMES = {
          'thin' => 'FontWeight.Thin',
          'extralight' => 'FontWeight.ExtraLight',
          'light' => 'FontWeight.Light',
          'normal' => 'FontWeight.Normal',
          'regular' => 'FontWeight.Normal',
          'medium' => 'FontWeight.Medium',
          'semibold' => 'FontWeight.SemiBold',
          'bold' => 'FontWeight.Bold',
          'extrabold' => 'FontWeight.ExtraBold',
          'heavy' => 'FontWeight.ExtraBold',
          'black' => 'FontWeight.Black'
        }.freeze

        def self.font_weight(json_data)
          raw = json_data['fontWeight'] || json_data['font']
          return nil unless raw.is_a?(String)

          WEIGHT_NAMES[raw.downcase]
        end

        def self.drawable(name)
          "painterResource(id = R.drawable.#{Helpers::ResourceResolver.drawable_name(name)})"
        end

        def self.quote(text)
          "\"#{text.to_s.gsub('"', '\\"')}\""
        end

        def self.indent(text, level)
          return text if level.zero?

          spaces = '    ' * level
          text.split("\n").map { |line| line.empty? ? line : spaces + line }.join("\n")
        end
      end
    end
  end
end
