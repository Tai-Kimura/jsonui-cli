# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/visibility_helper'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/font_spec_helper'

module KjuiTools
  module Compose
    module Components
      # Text Component Generator
      #
      # NOTE: Label is the primary component name in JsonUI.
      # Text is supported as an alias for backward compatibility.
      # Both "type": "Label" and "type": "Text" work identically.
      #
      class TextComponent
        @counter = 0
        class << self
          attr_accessor :counter
        end

        # Per-file determinism: compose_builder calls this before each layout
        # so resolved_* local names don't drift with process build history.
        def self.reset_counter!
          @counter = 0
        end

        # Returns a fresh `resolved_text<N>` local name for the FontSpec block.
        def self.next_resolved_var
          @counter += 1
          "resolved_text#{@counter}"
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Check if component should be skipped entirely (static gone only;
          # hidden keeps its layout space and renders invisible)
          return "" if Helpers::VisibilityHelper.should_skip_render?(json_data)

          # Check if we need to use PartialAttributesText for partial attributes
          if json_data['partialAttributes'] && json_data['partialAttributes'].any?
            return generate_with_partial_attributes_component(json_data, depth, required_imports, parent_type)
          end

          # Check if we need to use PartialAttributesText for linkable attribute
          if json_data['linkable']
            return generate_with_partial_attributes_for_linkable(json_data, depth, required_imports, parent_type)
          end

          text = Helpers::ResourceResolver.process_text(json_data['text'] || '', required_imports)

          # Build FontSpec args once. We always emit the resolve block for Text-type
          # components so the app's fontProvider is honoured even when the JSON
          # didn't specify any font attribute (matches the SwiftUI parity goal).
          font_args = Helpers::FontSpecHelper.build_font_spec_args(json_data, required_imports)
          var_name = next_resolved_var

          # highlightAttributes / highlightColor take over while `selected` is
          # true. The highlight font goes through the SAME FontSpec resolver as
          # the base one so an app's fontProvider is honoured in both states.
          highlight = highlight_overrides(json_data)
          highlight_condition = selected_condition(json_data)
          highlight_var = nil
          if highlight && highlight_condition && highlight.key?(:font_attrs)
            highlight_var = next_resolved_var
            highlight_args = Helpers::FontSpecHelper.build_font_spec_args(
              json_data.merge(highlight[:font_attrs]), required_imports
            )
          end

          # `hint` + `hintAttributes` — a Label's placeholder. UIKit's SJUILabel
          # swaps in the hint, styled by hintAttributes, when the text is empty
          # (`if let hint, let hintAttributes, string.isEmpty`), and it requires
          # BOTH: a hint with no attributes shows nothing there, so the same is
          # true here rather than inventing a divergence.
          hint = hint_overrides(json_data)
          hint_var = hint ? "labelText#{@counter}" : nil
          hint_condition = hint_var ? "#{hint_var}.isEmpty()" : nil
          hint_font_var = nil
          if hint && hint[:font_attrs].any?
            hint_font_var = next_resolved_var
            hint_font_args = Helpers::FontSpecHelper.build_font_spec_args(
              json_data.merge(hint[:font_attrs]), required_imports
            )
          end

          # Which resolved font is in force. Normally an expression, so the swap
          # happens at recomposition; a literal `selected: true` collapses to the
          # highlight font directly, since `if (true)` earns a Kotlin
          # "condition is always true" warning in the consuming build.
          always_highlighted = highlight_condition == 'true'
          font_ref = if highlight_var.nil?
                       var_name
                     elsif always_highlighted
                       highlight_var
                     else
                       "(if (#{highlight_condition}) #{highlight_var} else #{var_name})"
                     end
          # The hint branch is outermost: an empty label is a hint first and a
          # selected label second.
          font_ref = "(if (#{hint_condition}) #{hint_font_var} else #{font_ref})" if hint_font_var

          # Resolved ahead of emission so only the blocks the Text(...) call
          # actually references are written: an unreferenced `val` is a Kotlin
          # "never used" warning in the consuming build.
          component_code = ""
          if font_ref.include?(var_name)
            component_code += Helpers::FontSpecHelper.emit_resolve_block(var_name, font_args, depth, required_imports)
            component_code += "\n"
          end
          if highlight_var
            component_code += Helpers::FontSpecHelper.emit_resolve_block(highlight_var, highlight_args, depth, required_imports)
            component_code += "\n"
          end
          if hint_font_var
            component_code += Helpers::FontSpecHelper.emit_resolve_block(hint_font_var, hint_font_args, depth, required_imports)
            component_code += "\n"
          end

          # The text is hoisted into a `val` so the emptiness test and the value
          # itself do not evaluate the same string template twice.
          component_code += indent("val #{hint_var} = #{text}", depth) + "\n" if hint_var

          component_code += indent("Text(", depth)
          text_expr = if hint_condition
                        "if (#{hint_condition}) #{Helpers::ResourceResolver.process_text(hint[:text], required_imports)} else #{hint_var}"
                      else
                        text
                      end
          component_code += "\n" + indent("text = #{text_expr},", depth + 1)

          # Font color (official attribute)
          base_color = if json_data['fontColor']
                         Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
                       end
          highlight_color = if highlight && highlight_condition && highlight[:font_color]
                              Helpers::ResourceResolver.process_color(highlight[:font_color], required_imports)
                            end
          hint_color = if hint && hint[:font_color]
                         Helpers::ResourceResolver.process_color(hint[:font_color], required_imports)
                       end
          if hint_color
            # The hint branch wraps whatever the text branch would have used.
            required_imports&.add(:color)
            inner = if highlight_color && always_highlighted
                      highlight_color
                    elsif highlight_color
                      "if (#{highlight_condition}) #{highlight_color} else #{base_color || 'Color.Unspecified'}"
                    else
                      base_color || 'Color.Unspecified'
                    end
            component_code += "\n" + indent(
              "color = if (#{hint_condition}) #{hint_color} else #{inner.start_with?('if (') ? "(#{inner})" : inner},",
              depth + 1
            )
          elsif highlight_color && always_highlighted
            component_code += "\n" + indent("color = #{highlight_color},", depth + 1)
          elsif highlight_color
            # Compose has no "inherit" colour, so the unselected branch needs a
            # concrete value; Color.Unspecified is the documented way to say
            # "whatever Text would have used".
            required_imports&.add(:color)
            component_code += "\n" + indent(
              "color = if (#{highlight_condition}) #{highlight_color} else #{base_color || 'Color.Unspecified'},",
              depth + 1
            )
          elsif base_color
            component_code += "\n" + indent("color = #{base_color},", depth + 1)
          end

          # ResolvedFont fields routed to Text(...) parameters
          required_imports&.add(:font_style)
          required_imports&.add(:text_unit)
          component_code += "\n" + indent("fontFamily = #{font_ref}.family,", depth + 1)
          component_code += "\n" + indent("fontWeight = #{font_ref}.weight,", depth + 1)
          component_code += "\n" + indent("fontSize = #{font_ref}.size ?: TextUnit.Unspecified,", depth + 1)
          component_code += "\n" + indent("fontStyle = #{font_ref}.style ?: FontStyle.Normal,", depth + 1)

          # Text decoration (underline, strikethrough)
          text_decorations = []
          if json_data['underline']
            required_imports&.add(:text_decoration)
            text_decorations << "TextDecoration.Underline"
          end

          if json_data['strikethrough']
            required_imports&.add(:text_decoration)
            text_decorations << "TextDecoration.LineThrough"
          end

          if text_decorations.any?
            if text_decorations.length > 1
              component_code += "\n" + indent("textDecoration = TextDecoration.combine(listOf(#{text_decorations.join(', ')})),", depth + 1)
            else
              component_code += "\n" + indent("textDecoration = #{text_decorations.first},", depth + 1)
            end
          end

          # Text shadow and line height
          style_parts = []

          if json_data['textShadow']
            required_imports&.add(:shadow_style)
            style_parts << text_shadow_expression(json_data['textShadow'], required_imports)
          end

          # A highlight lineHeightMultiple resolves against the highlight's own
          # font size, the same way the base one resolves against the base size.
          highlight_line_height = if highlight && highlight_condition && highlight[:line_height_multiple]
                                    hl_size = (highlight.dig(:font_attrs, 'fontSize') || json_data['fontSize'] || 14).to_f
                                    (hl_size * highlight[:line_height_multiple].to_f)
                                  end

          if highlight_line_height && always_highlighted
            required_imports&.add(:text_style)
            style_parts << "lineHeight = #{highlight_line_height}.sp"
          elsif highlight_line_height
            required_imports&.add(:text_style)
            base_line_height = if json_data['lineHeightMultiple']
                                 (json_data['fontSize'] || 14).to_f * json_data['lineHeightMultiple'].to_f
                               elsif json_data['lineSpacing']
                                 (json_data['fontSize'] || 14).to_f + json_data['lineSpacing'].to_f
                               elsif json_data['fontSize']
                                 (json_data['fontSize'].to_f * 1.3).round(1)
                               end
            style_parts << if base_line_height
                             "lineHeight = (if (#{highlight_condition}) #{highlight_line_height} else #{base_line_height}).sp"
                           else
                             # TextUnit.Unspecified is how Compose says "use the
                             # font's own line height".
                             required_imports&.add(:text_unit)
                             "lineHeight = if (#{highlight_condition}) #{highlight_line_height}.sp else TextUnit.Unspecified"
                           end
          elsif json_data['lineHeightMultiple']
            required_imports&.add(:text_style)
            # Line height multiplier - apply to font size.
            # Both factors are `["number", "binding"]`, and `"@{v}".to_f` is
            # 0.0 — a bound multiple or a bound size used to freeze the line
            # height to 0.sp or to the other factor alone (plan 49 lane C).
            # When either side is bound the multiplication moves into the emit.
            style_parts << "lineHeight = #{scaled_sp(json_data['fontSize'], json_data['lineHeightMultiple'])}"
          elsif json_data['lineSpacing']
            required_imports&.add(:text_style)
            # Line spacing - add to base font size
            style_parts << "lineHeight = #{summed_sp(json_data['fontSize'], json_data['lineSpacing'])}"
          elsif json_data['fontSize']
            # Default lineHeight to match iOS compact line spacing (fontSize * 1.3)
            required_imports&.add(:text_style)
            style_parts << "lineHeight = #{scaled_sp(json_data['fontSize'], 1.3, round: true)}"
          end

          if style_parts.any?
            required_imports&.add(:text_style)
            component_code += "\n" + indent("style = TextStyle(#{style_parts.join(', ')}),", depth + 1)
          end

          # Build modifiers
          modifiers = []

          # Add testTag and contentDescription for UI testing
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          # Get visibility info (but don't add to modifiers, will be handled by wrapper)
          visibility_result = Helpers::ModifierBuilder.build_visibility(json_data, required_imports)
          modifiers.concat(visibility_result[:modifiers]) if visibility_result[:modifiers].any?

          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          # Add weight modifier if in Row or Column
          if parent_type == 'Row' || parent_type == 'Column'
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          end

          # 1. Margins first (outer spacing) - must be before size for outer margin behavior
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

          # 2. Size (parent_type lets a vertical-container weight pair with
          #    wrapContentHeight for `gravity: center` vertical centering)
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))

          # 3. Shadow before background
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))

          # 4. Background (clip + background)
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))

          # 5. Handle edgeInset/padding for internal spacing
          # In Compose, padding AFTER background = internal padding (inside the background)
          if json_data['edgeInset']
            insets = json_data['edgeInset']
            if insets.is_a?(Array) && insets.length == 4
              modifiers << ".padding(top = #{insets[0]}.dp, end = #{insets[1]}.dp, bottom = #{insets[2]}.dp, start = #{insets[3]}.dp)"
            elsif insets.is_a?(Numeric)
              modifiers << ".padding(#{insets}.dp)"
            end
          end
          # padding/paddings for Label = internal padding (after background)
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          # Format modifiers
          if modifiers.any?
            component_code += Helpers::ModifierBuilder.format(modifiers, depth)
          else
            component_code += "\n" + indent("modifier = Modifier", depth + 1)
          end

          # Text alignment
          highlight_align = if highlight && highlight_condition
                              compose_text_align(highlight[:text_align])
                            end
          base_align = compose_text_align(json_data['textAlign'])

          if highlight_align && always_highlighted
            required_imports&.add(:text_align)
            component_code += ",\n" + indent("textAlign = #{highlight_align}", depth + 1)
          elsif highlight_align
            required_imports&.add(:text_align)
            # TextAlign.Unspecified is Compose's "inherit"; the unselected branch
            # needs a concrete value because this is one expression.
            component_code += ",\n" + indent(
              "textAlign = if (#{highlight_condition}) #{highlight_align} else #{base_align || 'TextAlign.Unspecified'}",
              depth + 1
            )
          elsif json_data['textAlign']
            required_imports&.add(:text_align)
            if (align = compose_text_align(json_data['textAlign']))
              component_code += ",\n" + indent("textAlign = #{align}", depth + 1)
            end
          elsif json_data['centerHorizontal']
            required_imports&.add(:text_align)
            component_code += ",\n" + indent("textAlign = TextAlign.Center", depth + 1)
          end

          # Lines / overflow / auto-shrink — compute consolidated maxLines +
          # overflow values upfront so each named arg is emitted at most once.
          # Previously `lines`, `autoShrink`, `minimumScaleFactor`, and
          # `lineBreakMode` each appended their own `overflow = ...` (and
          # `maxLines = ...` for the auto-shrink paths) independently, so
          # combinations like `lines + lineBreakMode` or `lines + autoShrink`
          # produced duplicate named args and kotlinc halted with
          # "named arg specified twice".
          # Regression: kjui-label-lines-and-linebreakmode-double-overflow-emit.
          max_lines_value = nil
          overflow_value = nil

          if json_data['lines']
            if json_data['lines'] == 0
              max_lines_value = 'Int.MAX_VALUE'
            elsif Helpers::BoundValue.bound?(json_data['lines'])
              # `to_s` on a binding put the characters `@{v}` where an Int
              # belongs. `lines: 0` means unlimited, so the runtime form has to
              # carry that branch too (plan 49 lane C: Label.lines).
              lines_expr = Helpers::BoundValue.int(json_data['lines'], fallback: 0)
              max_lines_value = "(#{lines_expr}).let { if (it <= 0) Int.MAX_VALUE else it }"
              overflow_value = 'TextOverflow.Ellipsis'
            else
              max_lines_value = json_data['lines'].to_s
              overflow_value = 'TextOverflow.Ellipsis'
            end
          end

          # Auto shrink text using TextAutoSize (auto-size emit stays here;
          # maxLines / overflow defer to the consolidated emit below).
          # `autoSize` is a named argument, so it may be emitted AT MOST once —
          # `autoShrink` and `minimumScaleFactor` both ask for auto-shrink and
          # each used to append its own, which kotlinc rejects with "an argument
          # is already passed". Same consolidation `maxLines`/`overflow` got
          # above, and for the same reason. An explicit `minimumScaleFactor`
          # wins: it names the floor, where `autoShrink` only implies 0.5.
          auto_size_factor = nil
          if json_data['autoShrink']
            auto_size_factor = 0.5
            max_lines_value ||= '1'
            overflow_value ||= 'TextOverflow.Ellipsis'
          end

          # Minimum scale factor (auto-shrink text) using TextAutoSize
          if json_data['minimumScaleFactor']
            # Same `.to_f` freeze as lineHeightMultiple: a bound factor made
            # minFontSize 0.sp (plan 49 lane C: Label.minimumScaleFactor).
            auto_size_factor = json_data['minimumScaleFactor']
            max_lines_value ||= '1'
            overflow_value ||= 'TextOverflow.Ellipsis'
          end

          if auto_size_factor
            required_imports&.add(:text_auto_size)
            min_font_size = scaled_sp(json_data['fontSize'] || 14, auto_size_factor, round: true)
            component_code += ",\n" + indent("autoSize = TextAutoSize.StepBased(minFontSize = #{min_font_size})", depth + 1)
          end

          # `lineBreakMode`, when explicitly set, takes precedence over the
          # implicit Ellipsis from `lines` / `autoShrink` / `minimumScaleFactor`.
          # Unmapped enum values (`head`/`middle`/`char`) leave the prior
          # value untouched — matches the original silent-skip semantics
          # for those modes.
          if json_data['lineBreakMode']
            case json_data['lineBreakMode'].downcase
            when 'clip'
              overflow_value = 'TextOverflow.Clip'
            when 'tail', 'word'
              overflow_value = 'TextOverflow.Ellipsis'
            end
          end

          if max_lines_value
            component_code += ",\n" + indent("maxLines = #{max_lines_value}", depth + 1)
          end
          if overflow_value
            required_imports&.add(:text_overflow)
            component_code += ",\n" + indent("overflow = #{overflow_value}", depth + 1)
          end

          component_code += "\n" + indent(")", depth)

          # Wrap with VisibilityWrapper if needed
          Helpers::VisibilityHelper.wrap_with_visibility(json_data, component_code, depth, required_imports)
        end

        private

        # The styling that takes over while the label is selected.
        #
        # Canonical semantics come from the iOS UIKit runtime, which keeps two
        # attribute dictionaries and swaps on `selected`
        # (SJUILabel#applyAttributedText). `highlightAttributes` wins over
        # `highlightColor`, and an object with no usable key falls through to
        # `highlightColor` — matching SJUILabel's creator.
        #
        # Returns nil, or a hash with `:font_attrs` (base-shaped keys, so the
        # existing FontSpec builder can consume them) and/or `:font_color`.
        def self.highlight_overrides(json_data)
          attrs = json_data['highlightAttributes']
          result = {}

          if attrs.is_a?(Hash)
            font_attrs = {}
            # `font` carries either a family or the literal weight name "bold",
            # which is exactly what the base `font` key already accepts.
            font_attrs['font'] = attrs['font'] if attrs['font']
            font_attrs['fontSize'] = attrs['fontSize'] if attrs['fontSize']
            result[:font_attrs] = font_attrs if font_attrs.any?
            result[:font_color] = attrs['fontColor'] if attrs['fontColor']
            result[:line_height_multiple] = attrs['lineHeightMultiple'] if attrs['lineHeightMultiple']
            result[:text_align] = attrs['textAlign'] if attrs['textAlign']
          end

          if result.empty? && json_data['highlightColor']
            result[:font_color] = json_data['highlightColor']
          end
          result.empty? ? nil : result
        end

        # The declared textAlign spellings (Left/Right/Center) as Compose values.
        # `textAlign` is `["string", "binding"]`, and the `case` below could
        # never match a `"@{...}"`, so a bound alignment froze to the component
        # default (plan 49 lane C: Label.textAlign, and the shared vocabulary
        # TextView/Button now reuse).
        TEXT_ALIGN_MAPPING = {
          'center' => 'TextAlign.Center',
          'right' => 'TextAlign.End',
          'left' => 'TextAlign.Start'
        }.freeze

        def self.compose_text_align(value)
          return nil unless value.is_a?(String)

          # A static value outside the vocabulary still emits nothing; a bound
          # one needs an exhaustive `else` for the `when` to compile, and
          # `Unspecified` is Compose's own "no opinion" value.
          Helpers::BoundValue.enum(value, TEXT_ALIGN_MAPPING,
                                   bound_default: 'TextAlign.Unspecified', lowercase: true)
        end

        # `textShadow` is `{ color:, blur:, offset: [x, y] }` (a bare string is
        # a colour with UIKit's default 1pt blur) — the same contract sjui and
        # rjui read. kjui emitted a HARD-CODED black/2,2/4 Shadow, so the
        # declared colour, blur and offset were discarded by construction
        # (plan 49 lane C: Label.textShadow presence-only, IconLabel.textShadow
        # unread).
        def self.text_shadow_expression(shadow, required_imports = nil)
          # `:shadow_style` (added by the caller) already pulls in Shadow and
          # Offset alongside TextStyle.
          if shadow.is_a?(Hash)
            color = shadow['color'] ? Helpers::ResourceResolver.process_color(shadow['color'], required_imports) : 'Color.Black'
            blur = shadow['blur'] || 1
            offset = shadow['offset']
            x, y = offset.is_a?(Array) && offset.length >= 2 ? [offset[0], offset[1]] : [0, 1]
            return "shadow = Shadow(color = #{color}, offset = Offset(#{Helpers::BoundValue.float(x)}, " \
                   "#{Helpers::BoundValue.float(y)}), blurRadius = #{Helpers::BoundValue.float(blur)})"
          end

          color = Helpers::ResourceResolver.process_color(shadow, required_imports)
          "shadow = Shadow(color = #{color}, offset = Offset(0f, 1f), blurRadius = 1f)"
        end

        # `<size> * <factor>` as an `.sp` expression. Folded in Ruby when both
        # sides are static (byte-identical to the old emit), lifted into the
        # generated source when either is bound.
        # `round:` mirrors the call site's original arithmetic — the lineHeight
        # multiplier never rounded, the auto-size floors always did. Getting
        # this wrong would move static output, which is the one thing this
        # refactor must not do.
        def self.scaled_sp(size, factor, round: false)
          size = 14 if size.nil?
          if Helpers::BoundValue.bound?(size) || Helpers::BoundValue.bound?(factor)
            "(#{Helpers::BoundValue.float(size, fallback: 14)} * #{Helpers::BoundValue.float(factor, fallback: 1)}).sp"
          else
            product = size.to_f * factor.to_f
            "#{round ? product.round(1) : product}.sp"
          end
        end

        # `<size> + <delta>` as an `.sp` expression. Same two modes.
        def self.summed_sp(size, delta)
          size = 14 if size.nil?
          if Helpers::BoundValue.bound?(size) || Helpers::BoundValue.bound?(delta)
            "(#{Helpers::BoundValue.float(size, fallback: 14)} + #{Helpers::BoundValue.float(delta, fallback: 0)}).sp"
          else
            "#{size.to_f + delta.to_f}.sp"
          end
        end

        # The `selected` state that decides which set is in force. Absent means
        # never highlighted, so there is nothing to emit.
        # `hintAttributes` on a Label, with `hint` as the text it styles. Returns
        # nil unless both are present — that is UIKit's own condition.
        def self.hint_overrides(json_data)
          attrs = json_data['hintAttributes']
          # `placeholder` is the declared alias of `hint` and only sjui/rjui
          # resolved both (plan 49 lane C, handed over from D).
          hint = json_data['hint'] || json_data['placeholder']
          return nil unless attrs.is_a?(Hash) && hint.is_a?(String) && !hint.empty?

          {
            text: hint,
            font_color: attrs['fontColor'] || json_data['hintColor'],
            font_attrs: attrs.slice('font', 'fontSize'),
            line_height_multiple: attrs['lineHeightMultiple']
          }
        end

        def self.selected_condition(json_data)
          value = json_data['selected']
          return 'true' if value == true || value == 'true'
          if Helpers::ModifierBuilder.is_binding?(value)
            return "data.#{Helpers::ModifierBuilder.extract_binding_property(value)}"
          end

          nil
        end

        def self.generate_with_partial_attributes_for_linkable(json_data, depth, required_imports, parent_type)
          required_imports&.add(:partial_attributes_text)

          text = json_data['text'] || ''

          # Build FontSpec resolve block before the component so its fields can be
          # consumed by the TextStyle( ... ) below.
          font_args = Helpers::FontSpecHelper.build_font_spec_args(json_data, required_imports)
          var_name = next_resolved_var
          code = Helpers::FontSpecHelper.emit_resolve_block(var_name, font_args, depth, required_imports)
          code += "\n"

          code += indent("PartialAttributesText(", depth)
          code += "\n" + indent("text = \"#{escape_string(text)}\",", depth + 1)
          # `linkable` is `["boolean", "binding"]`. The literal `true` froze a
          # bound declaration permanently ON (plan 49 lane C: Label.linkable) —
          # the routing test above still has to be a presence test, because the
          # COMPOSABLE differs, but the flag it passes is the real value.
          linkable_state = Helpers::BoundValue.bool(json_data['linkable'])
          linkable_expr = linkable_state == :on ? 'true' : (linkable_state == :off ? 'false' : linkable_state)
          code += "\n" + indent("linkable = #{linkable_expr},", depth + 1)

          # Build style
          style_parts = []

          if json_data['fontColor']
            color_value = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
            style_parts << "color = #{color_value}" if color_value
          end

          # Always pass through resolved font fields (centralised mapping).
          required_imports&.add(:font_style)
          required_imports&.add(:text_unit)
          style_parts.concat(Helpers::FontSpecHelper.style_arg_fragments(var_name, required_imports))

          if json_data['textAlign']
            required_imports&.add(:text_align)
            align = compose_text_align(json_data['textAlign'])
            style_parts << "textAlign = #{align}" if align
          end

          if style_parts.any?
            required_imports&.add(:text_style)
            code += "\n" + indent("style = TextStyle(#{style_parts.join(', ')}),", depth + 1)
          end

          # Build modifiers
          modifiers = []
          # id testTag first, via the shared ModifierBuilder (single source of
          # truth every other component uses) so a partial-attributes node is
          # findable by By.res(id) — parity with iOS accessibilityIdentifier.
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))

          # Handle edgeInset for text-specific padding
          if json_data['edgeInset']
            insets = json_data['edgeInset']
            if insets.is_a?(Array) && insets.length == 4
              modifiers << ".padding(top = #{insets[0]}.dp, end = #{insets[1]}.dp, bottom = #{insets[2]}.dp, start = #{insets[3]}.dp)"
            elsif insets.is_a?(Numeric)
              modifiers << ".padding(#{insets}.dp)"
            end
          else
            modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          end

          if modifiers.any?
            code += Helpers::ModifierBuilder.format(modifiers, depth)
          else
            code += "\n" + indent("modifier = Modifier", depth + 1)
          end

          code += "\n" + indent(")", depth)

          # Wrap with VisibilityWrapper if needed
          Helpers::VisibilityHelper.wrap_with_visibility(json_data, code, depth, required_imports)
        end

        def self.generate_with_partial_attributes_component(json_data, depth, required_imports, parent_type)
          required_imports&.add(:partial_attributes_text)

          text = json_data['text'] || ''
          partial_attrs = json_data['partialAttributes']

          # Process main text through resource resolver for stringResource() support
          processed_text = Helpers::ResourceResolver.process_text(text, required_imports)

          # Build FontSpec resolve block first so the inline style block can consume it.
          font_args = Helpers::FontSpecHelper.build_font_spec_args(json_data, required_imports)
          var_name = next_resolved_var
          code = Helpers::FontSpecHelper.emit_resolve_block(var_name, font_args, depth, required_imports)
          code += "\n"

          code += indent("PartialAttributesText(", depth)
          code += "\n" + indent("text = #{processed_text},", depth + 1)

          # Build partial attributes list
          code += "\n" + indent("partialAttributes = listOf(", depth + 1)

          partial_attrs.each_with_index do |attr, index|
            code += "\n" + indent("PartialAttribute.fromJsonRange(", depth + 2)

            # Handle range - convert numeric array to text pattern for localization support
            range = attr['range']
            if range.is_a?(Array) && range.length == 2 && range.all? { |r| r.is_a?(Integer) }
              # Extract substring from text using numeric range, then use as text pattern
              range_text = text[range[0]...range[1]]
              if range_text && !range_text.empty?
                processed_range = Helpers::ResourceResolver.process_text(range_text, required_imports)
                code += "\n" + indent("range = #{processed_range},", depth + 3)
              else
                code += "\n" + indent("range = listOf(#{range.join(', ')}),", depth + 3)
              end
            elsif range.is_a?(String)
              processed_range = Helpers::ResourceResolver.process_text(range, required_imports)
              code += "\n" + indent("range = #{processed_range},", depth + 3)
            end

            code += "\n" + indent("text = #{processed_text},", depth + 3)

            # Add optional attributes
            if attr['fontColor']
              fc = attr['fontColor']
              if fc.is_a?(String) && fc.match?(/^@\{.+\}$/)
                variable = fc[2..-2]
                code += "\n" + indent("fontColor = data.#{variable},", depth + 3)
              else
                code += "\n" + indent("fontColor = \"#{fc}\",", depth + 3)
              end
            end
            if attr['fontSize']
              code += "\n" + indent("fontSize = #{attr['fontSize']},", depth + 3)
            end
            # Handle font/fontWeight - support both "font" and "fontWeight" keys
            font_weight = attr['fontWeight'] || attr['font']
            if font_weight
              code += "\n" + indent("fontWeight = \"#{font_weight}\",", depth + 3)
            end
            if attr['background']
              code += "\n" + indent("background = \"#{attr['background']}\",", depth + 3)
            end
            if attr['underline']
              code += "\n" + indent("underline = #{attr['underline']},", depth + 3)
            end
            if attr['strikethrough']
              code += "\n" + indent("strikethrough = #{attr['strikethrough']},", depth + 3)
            end
            # Handle click events for partial attributes
            # onclick (lowercase) -> selector format (string only)
            # onClick (camelCase) -> binding format only (@{functionName})
            if attr['onclick']
              handler_call = Helpers::ModifierBuilder.get_event_handler_call(attr['onclick'], is_camel_case: false)
              code += "\n" + indent("onClick = { #{handler_call} }", depth + 3)
            elsif attr['onClick']
              handler_call = Helpers::ModifierBuilder.get_event_handler_call(attr['onClick'], is_camel_case: true)
              code += "\n" + indent("onClick = { #{handler_call} }", depth + 3)
            else
              code += "\n" + indent("onClick = null", depth + 3)
            end

            code += "\n" + indent(")!!", depth + 2) # !! because fromJsonRange returns nullable
            code += "," if index < partial_attrs.length - 1
          end

          code += "\n" + indent("),", depth + 1)

          # Build modifiers
          modifiers = []
          # id testTag first, via the shared ModifierBuilder (single source of
          # truth every other component uses) so a partial-attributes node is
          # findable by By.res(id) — parity with iOS accessibilityIdentifier.
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          if modifiers.any?
            code += Helpers::ModifierBuilder.format(modifiers, depth)
          else
            code += "\n" + indent("modifier = Modifier", depth + 1)
          end

          # Add style — always include resolved font fragments so the Configuration
          # provider is honoured even without explicit JSON font attrs.
          style_parts = []
          if json_data['fontColor']
            color_value = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
            style_parts << "color = #{color_value}" if color_value
          end

          required_imports&.add(:font_style)
          required_imports&.add(:text_unit)
          style_parts.concat(Helpers::FontSpecHelper.style_arg_fragments(var_name, required_imports))

          if json_data['textAlign']
            required_imports&.add(:text_align)
            align = compose_text_align(json_data['textAlign'])
            style_parts << "textAlign = #{align}" if align
          end

          if style_parts.any?
            required_imports&.add(:text_style)
            code += ",\n" + indent("style = TextStyle(#{style_parts.join(', ')})", depth + 1)
          end

          code += "\n" + indent(")", depth)

          # Wrap with VisibilityWrapper if needed
          Helpers::VisibilityHelper.wrap_with_visibility(json_data, code, depth, required_imports)
        end

        # Legacy AnnotatedString path retained for backward compat with any
        # caller that explicitly drives this helper. The two helpers above are
        # the ones routed from `.generate`.
        def self.generate_with_partial_attributes(json_data, depth, required_imports, parent_type)
          required_imports&.add(:annotated_string)
          required_imports&.add(:link_annotation)
          required_imports&.add(:remember_state)

          text = json_data['text'] || ''
          partial_attrs = json_data['partialAttributes']

          # Build AnnotatedString as a variable first
          code = indent("val annotatedText = buildAnnotatedString {", depth)
          code += "\n" + indent("append(\"#{escape_string(text)}\")", depth + 1)

          # Apply partial attributes
          partial_attrs.each do |attr|
            range = attr['range']
            next unless range && range.is_a?(Array) && range.length == 2

            start_idx = range[0]
            end_idx = range[1]

            # Build SpanStyle for this range
            span_styles = []

            if attr['fontColor']
              color_resolved = Helpers::ResourceResolver.process_color(attr['fontColor'], required_imports)
              span_styles << "color = #{color_resolved}"
            end

            if attr['fontSize']
              span_styles << "fontSize = #{attr['fontSize']}.sp"
            end

            if attr['fontWeight']
              required_imports&.add(:font_weight)
              span_styles << "fontWeight = #{Helpers::FontSpecHelper.weight_literal_for(attr['fontWeight'])}"
            end

            if attr['background']
              background_resolved = Helpers::ResourceResolver.process_color(attr['background'], required_imports)
              span_styles << "background = #{background_resolved}"
            end

            if attr['underline']
              required_imports&.add(:text_decoration)
              span_styles << "textDecoration = TextDecoration.Underline"
            end

            if attr['strikethrough']
              required_imports&.add(:text_decoration)
              span_styles << "textDecoration = TextDecoration.LineThrough"
            end

            if span_styles.any?
              code += "\n" + indent("addStyle(", depth + 1)
              code += "\n" + indent("style = SpanStyle(#{span_styles.join(', ')}),", depth + 2)
              code += "\n" + indent("start = #{start_idx},", depth + 2)
              code += "\n" + indent("end = #{end_idx}", depth + 2)
              code += "\n" + indent(")", depth + 1)
            end

            # Add clickable annotation if onclick/onClick is specified.
            # `onclick` is ["string", "array"]; an array names handlers to
            # call in order, and calling `match?` on it raised instead
            # (same family as get_event_handler_call, plan 49 lane C).
            click_handler = attr['onclick'] || attr['onClick']
            if click_handler
              # Extract each method name from binding format if needed
              names = (click_handler.is_a?(Array) ? click_handler : [click_handler]).map do |h|
                h = h.to_s
                (h.match(/^@\{(.+)\}$/) || [nil, h.gsub(':', '')])[1]
              end
              listener_calls = names.map { |n| "viewModel.handlePartialClick(\"#{n}\")" }.join('; ')
              code += "\n" + indent("addLink(", depth + 1)
              code += "\n" + indent("LinkAnnotation.Clickable(", depth + 2)
              code += "\n" + indent("tag = \"CLICKABLE\",", depth + 3)
              code += "\n" + indent("linkInteractionListener = { #{listener_calls} }", depth + 3)
              code += "\n" + indent("),", depth + 2)
              code += "\n" + indent("start = #{start_idx},", depth + 2)
              code += "\n" + indent("end = #{end_idx}", depth + 2)
              code += "\n" + indent(")", depth + 1)
            end
          end

          code += "\n" + indent("}", depth)
          code += "\n"

          # Render with Text — clicks are handled by the LinkAnnotations above
          # (ClickableText is deprecated).
          code += indent("Text(", depth)
          code += "\n" + indent("text = annotatedText", depth + 1)

          # Add style (fontSize, color, etc. for the whole text) — the return
          # value carries its own leading comma.
          style_code = build_text_style(json_data, depth + 1, required_imports)
          if style_code
            code += style_code
          end

          # Build modifiers
          modifiers = []
          # id testTag first, via the shared ModifierBuilder (single source of
          # truth every other component uses) so a partial-attributes node is
          # findable by By.res(id) — parity with iOS accessibilityIdentifier.
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          code += ","
          if modifiers.any?
            code += Helpers::ModifierBuilder.format(modifiers, depth)
          else
            code += "\n" + indent("modifier = Modifier", depth + 1)
          end

          code += "\n" + indent(")", depth)

          # Wrap with VisibilityWrapper if needed
          Helpers::VisibilityHelper.wrap_with_visibility(json_data, code, depth, required_imports)
        end

        # Build a TextStyle(...) literal for callers (e.g. the partial-attributes Text) that
        # need a TextStyle expression rather than separate Text(...) args.
        # Routes font fields through Configuration.Font.resolve(FontSpec(...)).
        def self.build_text_style(json_data, depth, required_imports)
          style_parts = []

          if json_data['fontColor']
            color_value = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
            style_parts << "color = #{color_value}" if color_value
          end

          if json_data['fontSize'] || json_data['font'] || json_data['fontWeight'] || json_data['fontFamily']
            font_args = Helpers::FontSpecHelper.build_font_spec_args(json_data, required_imports)
            var_name = next_resolved_var
            # Inline the resolve into the caller code by emitting a `.also { ... }`-style
            # expression isn't possible in TextStyle args; instead, callers that consume
            # this method should emit the resolve block themselves. To keep
            # backward-compat we emit a flat TextStyle(...) without resolved font here.
            # Concrete callers (PartialAttributesText, partial-attributes Text) construct their
            # own resolve block.
            style_parts << "fontSize = #{json_data['fontSize']}.sp" if json_data['fontSize']
            if json_data['fontFamily']
              required_imports&.add(:font_family)
              style_parts << "fontFamily = FontFamily(Font(R.font.#{json_data['fontFamily'].to_s.gsub('-', '_').gsub(' ', '_').downcase}))"
            end
            font_value = json_data['font'] || json_data['fontWeight']
            if font_value && Helpers::FontSpecHelper.weight_name?(font_value)
              required_imports&.add(:font_weight)
              style_parts << "fontWeight = #{Helpers::FontSpecHelper.weight_literal_for(font_value)}"
            elsif font_value && !json_data['fontFamily']
              # `font` holds a custom family name when not a weight.
              required_imports&.add(:font_family)
              style_parts << "fontFamily = FontFamily(Font(R.font.#{font_value.to_s.gsub('-', '_').downcase}))"
            end
          end

          if json_data['textAlign']
            required_imports&.add(:text_align)
            align = compose_text_align(json_data['textAlign'])
            style_parts << "textAlign = #{align}" if align
          end

          if style_parts.any?
            required_imports&.add(:text_style)
            return ",\n" + indent("style = TextStyle(#{style_parts.join(', ')})", depth)
          end

          nil
        end

        def self.escape_string(text)
          text.gsub('\\', '\\\\\\\\')
              .gsub('"', '\\"')
              .gsub("\n", '\\n')
              .gsub("\r", '\\r')
              .gsub("\t", '\\t')
        end

        def self.quote(text)
          # Escape special characters properly
          escaped = text.gsub('\\', '\\\\\\\\')  # Escape backslashes first
                       .gsub('"', '\\"')           # Escape quotes
                       .gsub("\n", '\\n')           # Escape newlines
                       .gsub("\r", '\\r')           # Escape carriage returns
                       .gsub("\t", '\\t')           # Escape tabs
          "\"#{escaped}\""
        end

        def self.indent(text, level)
          return text if level == 0
          spaces = '    ' * level
          text.split("\n").map { |line|
            line.empty? ? line : spaces + line
          }.join("\n")
        end
      end
    end
  end
end
