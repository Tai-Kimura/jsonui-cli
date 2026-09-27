# frozen_string_literal: true

require_relative 'text_component'
require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/font_spec_helper'
require_relative '../../core/normalization'
require_relative '../../core/string_literals'

module KjuiTools
  module Compose
    module Components
      class ButtonComponent
        @counter ||= 0

        # Per-file determinism: compose_builder calls this before each layout
        # so resolved_* local names don't drift with process build history.
        def self.reset_counter!
          @counter = 0
          @interaction_names = {}
        end

        # The pressed-state locals are named after the button's id, so two
        # buttons WITHOUT one produced the same `buttonInteraction` in the
        # same scope and the generated file stopped compiling ("Conflicting
        # declarations" — measured 2026-09-02 on the sample app, where one
        # button declares `tapBackground` and another `hilightColor`, and
        # neither carries an id). A name that is still free is used as-is, so
        # every layout that compiles today keeps byte-identical output; only
        # the colliding second one gains a suffix.
        def self.unique_interaction_name(base)
          @interaction_names ||= {}
          n = @interaction_names[base].to_i + 1
          @interaction_names[base] = n
          n == 1 ? base : "#{base}_#{n}"
        end

        def self.next_resolved_var
          @counter += 1
          "resolved_button#{@counter}"
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Button uses 'text' attribute per SwiftJsonUI spec
          image_name = json_data['image']
          has_image = !image_name.nil? && !image_name.to_s.empty?
          # "Button" is the placeholder for a button with nothing in it. An
          # icon-only button has content, so it must not render the word
          # "Button" beside its icon. Without an icon the fallback is
          # unchanged (including the explicit empty-string case).
          show_text = !has_image || !json_data['text'].to_s.empty?
          text = if show_text
                   Helpers::ResourceResolver.process_text(json_data['text'] || 'Button', required_imports)
                 end

          # Pressed-state colours need an owned InteractionSource: Material3
          # ButtonDefaults has no pressed slot, so the container/content
          # colours become conditional on collectIsPressedAsState.
          # `tapBackground` is the declared cross-platform spelling of "the
          # background while pressed"; the whole pressed-state machinery below
          # already exists and simply was not reading it, so a declaration went
          # nowhere on Compose (plan 49 lane C: Button.tapBackground,
          # common.tapBackground — sjui and rjui both read both spellings).
          highlight_bg = json_data['tapBackground'] || json_data['highlightBackground']
          highlight_font = Core::Normalization.attr_lookup(json_data, 'highlightColor', 'hilightColor')
          pressed_var = nil
          code = ''
          if highlight_bg || highlight_font
            required_imports&.add(:pressed_state)
            suffix = json_data['id'].to_s.gsub(/[^A-Za-z0-9]/, '')
            interaction_var = unique_interaction_name("buttonInteraction#{suffix}")
            pressed_var = interaction_var.sub('buttonInteraction', 'buttonPressed')
            code += indent("val #{interaction_var} = remember { MutableInteractionSource() }", depth) + "\n"
            code += indent("val #{pressed_var} by #{interaction_var}.collectIsPressedAsState()", depth) + "\n"
          end

          code += indent("Button(", depth)
          if highlight_bg || highlight_font
            code += "\n" + indent("interactionSource = #{interaction_var},", depth + 1)
          end

          # Handle click events
          # onclick (lowercase) -> selector format (string only)
          # onClick (camelCase) -> binding format only (@{functionName})
          view_id = Helpers::ModifierBuilder.view_id(json_data)
          # A handler names a method (TapAccessibility.handler?): an empty or
          # blank one is no handler, and the Button gets `onClick = { }`.
          tap = JsonUIShared::TapAccessibility
          # `canTap` gates the handler's call (attribute_definitions
          # common.canTap: false turns onClick / onclick off), as `clickable`
          # gates every other type's — not `enabled`: a button that cannot be
          # tapped is not disabled to a screen reader. userInteractionEnabled
          # with it, on the button or on a node around it (tap_gate): its
          # pointer blocker stops a touch, not TalkBack's double tap, which
          # calls onClick.
          # In a layout a stop can reach, the stop handed down too, captured
          # in the composable's scope (ModifierBuilder.lambda_gate).
          can_tap = Helpers::ModifierBuilder.lambda_gate(Helpers::ModifierBuilder.tap_gate(json_data))
          on_click = lambda do |call|
            next 'onClick = { }' if can_tap == 'false'

            "onClick = { #{can_tap ? "if (#{can_tap}) { #{call} }" : call} }"
          end
          if tap.handler?(json_data['onclick'])
            # Lowercase onclick - legacy selector format
            handler_call = Helpers::ModifierBuilder.get_event_handler_call(json_data['onclick'], is_camel_case: false, view_id: view_id)
            code += "\n" + indent(on_click.call(handler_call), depth + 1)
          elsif tap.handler?(json_data['onClick'])
            # camelCase onClick - binding format only (@{functionName})
            if Helpers::ModifierBuilder.is_binding?(json_data['onClick'])
              handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onClick'], view_id, nil)
              code += "\n" + indent(on_click.call(handler_call), depth + 1)
            else
              code += "\n" + indent("onClick = #{Helpers::ModifierBuilder.error_lambda("ERROR: #{json_data['onClick']} - camelCase events require binding format @{functionName}")}", depth + 1)
            end
          else
            code += "\n" + indent("onClick = { }", depth + 1)
          end
          
          # Build modifiers (only margins, size, and weight, not padding)
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          # userInteractionEnabled stops this node and
          # what is in it (ModifierBuilder.build_interaction_blocker); this
          # component builds no clickable, which is where it came from.
          modifiers.concat(Helpers::ModifierBuilder.build_interaction_blocker(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          # Shadow: alpha → shadow, the slot every other component uses. The
          # outline is the button's own — the declared cornerRadius, or the
          # default radius the `shape =` argument below draws.
          shadow_shape = json_data['cornerRadius'] ? nil : 'RoundedCornerShape(Configuration.Button.defaultCornerRadius.dp)'
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports, shape: shadow_shape))
          # onLongPress: Button's own inner .clickable consumes the down event
          # in the Main pass, so the detector must watch the Initial pass
          # (see ModifierBuilder.build_long_pressable). combinedClickable on
          # this modifier would race the inner clickable the same way. Pan and
          # pinch, declared on `common` with it, were dropped
          # (kjui-dynamic-components-that-skip-the-common-modifiers, B6).
          modifiers.concat(Helpers::ModifierBuilder.build_gestures(json_data, required_imports))

          # Format modifiers only if there are modifiers
          if modifiers.any?
            code += ","
            code += Helpers::ModifierBuilder.format(modifiers, depth)
          end
          
          # Add shape with cornerRadius (always set to match dynamic defaults)
          required_imports&.add(:shape)
          required_imports&.add(:configuration)
          # A bound cornerRadius is an expression (BoundValue.dp); `@{r}` was
          # written into the Kotlin as `RoundedCornerShape(@{r}.dp)` (B8).
          corner_radius = Helpers::BoundValue.dp(json_data['cornerRadius']) || 'Configuration.Button.defaultCornerRadius.dp'
          code += ",\n" + indent("shape = RoundedCornerShape(#{corner_radius})", depth + 1)
          
          # Add contentPadding for internal padding
          # Support both 'padding' (number), 'paddings' (array), and individual padding attributes
          padding_data = json_data['paddings'] || json_data['padding']
          
          if padding_data || json_data['paddingTop'] || json_data['paddingBottom'] ||
             json_data['paddingLeft'] || json_data['paddingRight'] || json_data['paddingStart'] ||
             json_data['paddingEnd'] || json_data['paddingHorizontal'] || json_data['paddingVertical'] ||
             json_data['leftPadding'] || json_data['rightPadding']
            required_imports&.add(:button_padding)
            
            padding_values = []
            
            if padding_data
              # Handle paddings array or padding number
              if padding_data.is_a?(Array)
                case padding_data.length
                when 1
                  # One value: all sides
                  padding_values << "#{Helpers::BoundValue.dp(padding_data[0])}"
                when 2
                  # Two values: [vertical, horizontal]
                  padding_values << "vertical = #{Helpers::BoundValue.dp(padding_data[0])}"
                  padding_values << "horizontal = #{Helpers::BoundValue.dp(padding_data[1])}"
                when 3
                  # Three values: [top, horizontal, bottom]
                  padding_values << "top = #{Helpers::BoundValue.dp(padding_data[0])}"
                  padding_values << "horizontal = #{Helpers::BoundValue.dp(padding_data[1])}"
                  padding_values << "bottom = #{Helpers::BoundValue.dp(padding_data[2])}"
                when 4
                  # Four values: [top, right, bottom, left] (iOS UIEdgeInsets convention)
                  padding_values << "top = #{Helpers::BoundValue.dp(padding_data[0])}"
                  padding_values << "end = #{Helpers::BoundValue.dp(padding_data[1])}"
                  padding_values << "bottom = #{Helpers::BoundValue.dp(padding_data[2])}"
                  padding_values << "start = #{Helpers::BoundValue.dp(padding_data[3])}"
                end
              else
                # Single number: all sides
                padding_values << "#{Helpers::BoundValue.dp(padding_data)}"
              end
            else
              # Handle individual padding attributes
              top_padding = json_data['paddingTop'] || json_data['paddingVertical'] || 0
              bottom_padding = json_data['paddingBottom'] || json_data['paddingVertical'] || 0
              start_padding = json_data['paddingStart'] || json_data['paddingLeft'] || json_data['leftPadding'] || json_data['paddingHorizontal'] || 0
              end_padding = json_data['paddingEnd'] || json_data['paddingRight'] || json_data['rightPadding'] || json_data['paddingHorizontal'] || 0
              
              if top_padding == bottom_padding && start_padding == end_padding && top_padding == start_padding
                # All same, use single value
                padding_values << "#{Helpers::BoundValue.dp(top_padding)}" if Helpers::BoundValue.positive_or_bound?(top_padding)
              elsif top_padding == bottom_padding && start_padding == end_padding
                # Different horizontal and vertical
                padding_values << "horizontal = #{Helpers::BoundValue.dp(start_padding)}" if Helpers::BoundValue.positive_or_bound?(start_padding)
                padding_values << "vertical = #{Helpers::BoundValue.dp(top_padding)}" if Helpers::BoundValue.positive_or_bound?(top_padding)
              else
                # All different, need to specify each
                padding_values << "start = #{Helpers::BoundValue.dp(start_padding)}" if Helpers::BoundValue.positive_or_bound?(start_padding)
                padding_values << "top = #{Helpers::BoundValue.dp(top_padding)}" if Helpers::BoundValue.positive_or_bound?(top_padding)
                padding_values << "end = #{Helpers::BoundValue.dp(end_padding)}" if Helpers::BoundValue.positive_or_bound?(end_padding)
                padding_values << "bottom = #{Helpers::BoundValue.dp(bottom_padding)}" if Helpers::BoundValue.positive_or_bound?(bottom_padding)
              end
            end
            
            if padding_values.any?
              code += ",\n" + indent("contentPadding = PaddingValues(#{padding_values.join(', ')})", depth + 1)
            end
          else
            # No padding specified: use zero padding to avoid Material default (24dp horizontal)
            code += ",\n" + indent("contentPadding = PaddingValues(0.dp)", depth + 1)
          end
          
          # Button colors including normal, disabled, and pressed states
          # Always set to match dynamic defaults
          required_imports&.add(:button_colors)
          colors_code = "colors = ButtonDefaults.buttonColors("
          color_params = []

          base_bg = if json_data['background']
                      Helpers::ResourceResolver.process_color(json_data['background'], required_imports)
                    else
                      'Configuration.Button.defaultBackgroundColor'
                    end
          if highlight_bg
            hl_bg = Helpers::ResourceResolver.process_color(highlight_bg, required_imports)
            color_params << "containerColor = if (#{pressed_var}) #{hl_bg} else #{base_bg}"
          else
            color_params << "containerColor = #{base_bg}"
          end

          # The disabled slots are UNCONDITIONAL, matching the comment three
          # lines up ("Always set to match dynamic defaults") — which this
          # method honoured for every slot except these two.
          #
          # Leaving them out does not mean "no opinion": Compose fills in
          # ButtonDefaults' own M3 values (container `onSurface@12%`, content
          # `onSurface@38%`), which are a different colour from the declared
          # one at half alpha. The dynamic renderer falls back to
          # `backgroundColor.copy(alpha = 0.5f)` / `textColor.copy(alpha =
          # 0.5f)` (DynamicButtonComponent.kt:125-131) and web says the same
          # thing with `disabled:opacity-50` (rjui button_converter.rb:94-99),
          # so the codegen was the lone outlier.
          #
          # G reduced two CI parity deviations to this single root:
          # `control_Button__enabled-False` (d=27, BOTH slots wrong) and
          # `common_disabledBackground__static` (d=9, only the content slot —
          # its container is declared and therefore already matched). The
          # distance difference is itself the corroboration.
          disabled_bg = if json_data['disabledBackground']
                          Helpers::ResourceResolver.process_color(json_data['disabledBackground'], required_imports)
                        else
                          "#{base_bg}.copy(alpha = 0.5f)"
                        end
          color_params << "disabledContainerColor = #{disabled_bg}"

          base_font = if json_data['fontColor']
                        Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
                      else
                        'Configuration.Button.defaultTextColor'
                      end
          if highlight_font
            hl_font = Helpers::ResourceResolver.process_color(highlight_font, required_imports)
            color_params << "contentColor = if (#{pressed_var}) #{hl_font} else #{base_font}"
          else
            color_params << "contentColor = #{base_font}"
          end

          disabled_font = if json_data['disabledFontColor']
                            Helpers::ResourceResolver.process_color(json_data['disabledFontColor'], required_imports)
                          else
                            "#{base_font}.copy(alpha = 0.5f)"
                          end
          color_params << "disabledContentColor = #{disabled_font}"

          colors_code += "\n" + color_params.map { |param| indent(param, depth + 2) }.join(",\n")
          colors_code += "\n" + indent(")", depth + 1)
          code += ",\n" + indent(colors_code, depth + 1)

          # Handle border
          if json_data['borderColor']
            required_imports&.add(:border_stroke)
            border_color = Helpers::ResourceResolver.process_color(json_data['borderColor'], required_imports)
            border_width = json_data['borderWidth'] || 1
            code += ",\n" + indent("border = BorderStroke(#{Helpers::BoundValue.dp(border_width)}, #{border_color})", depth + 1)
          end

          # Handle enabled attribute
          if json_data.key?('enabled')
            # `enabled` as every other stage reads it (enabled_expression): a
            # nullable binding is `(data.on ?: false)` — the bare `data.on` it
            # was did not type-check against the Boolean parameter.
            enabled = Helpers::ModifierBuilder.enabled_expression(json_data) || 'true'
            code += ",\n" + indent("enabled = #{enabled}", depth + 1)
          end
          
          code += "\n" + indent(") {", depth)

          # Content lambda. Icon + label sit in a Row; either one alone is
          # emitted on its own so a text-only button keeps its previous
          # output byte for byte.
          if has_image && show_text
            # The icon and the text move together, placed across the button by
            # textAlign (4f ruling 2026-09-27, round 18; measured on iOS: the
            # icon + text group at the start / end / middle of a 200pt
            # button): the Row takes the button's width and arranges the pair.
            # It sat in the middle whatever textAlign said.
            row_args = 'verticalAlignment = Alignment.CenterVertically'
            if (arrangement = icon_row_arrangement(json_data))
              required_imports&.add(:arrangement)
              row_args = "modifier = Modifier.fillMaxWidth(), horizontalArrangement = #{arrangement}, #{row_args}"
            end
            code += "\n" + indent("Row(#{row_args}) {", depth + 1)
            code += "\n" + build_icon_code(json_data, image_name, depth + 2, required_imports,
                                           decorative: true, spacer_after: true)
            code += "\n" + build_text_code(json_data, text, depth + 2, required_imports)
            code += "\n" + indent("}", depth + 1)
          elsif has_image
            code += "\n" + build_icon_code(json_data, image_name, depth + 1, required_imports,
                                           decorative: false, spacer_after: false)
          else
            code += "\n" + build_text_code(json_data, text, depth + 1, required_imports, fills: true)
          end

          code += "\n" + indent("}", depth)
          code
        end

        # Gap between the icon and the label. Fixed on purpose: `spacing` is
        # not declared for Button in attribute_definitions.json, so reading it
        # here would consume an undeclared attribute (same call as the web
        # converter's `gap-2`).
        ICON_LABEL_SPACING = 8

        # Icon box, matching the dynamic component's default.
        ICON_SIZE = 18

        # `image` was declared for Button but no Compose codegen read it, so
        # the icon simply never rendered — while the dynamic component (which
        # the hot-reload preview uses) did render it. Static/dynamic parity is
        # the contract, so this mirrors DynamicButtonComponent.
        #
        # Tinting follows the icon's own attributes rather than always
        # flattening: `Icon` forces a single colour, which would destroy a
        # multi-colour asset. Only an explicit `tintColor` / `fontColor` asks
        # for a tint — the same rule the web converter applies.
        def self.build_icon_code(json_data, image_name, depth, required_imports, decorative:, spacer_after:)
          required_imports&.add(:painter_resource)
          content_desc = decorative ? 'null' : quote(humanize_image_name(image_name))
          spacer = indent("Spacer(modifier = Modifier.width(#{ICON_LABEL_SPACING}.dp))", depth)

          if Helpers::ModifierBuilder.is_binding?(image_name)
            required_imports&.add(:local_context)
            property = to_camel_case(Helpers::ModifierBuilder.extract_binding_property(image_name))
            # An unresolvable name yields id 0; drop the icon rather than
            # crash on a missing resource (DynamicButtonComponent's takeIf).
            # The gap goes inside the branch so an unresolved icon does not
            # leave a stray 8dp indent in front of the label.
            lines = [
              indent("val iconResId = LocalContext.current.let { ctx ->", depth),
              indent("ctx.resources.getIdentifier(data.#{property}, \"drawable\", ctx.packageName)", depth + 1),
              indent("}", depth),
              indent("if (iconResId != 0) {", depth),
              build_icon_call('painterResource(id = iconResId)', content_desc, depth + 1, json_data, required_imports)
            ]
            lines << indent("Spacer(modifier = Modifier.width(#{ICON_LABEL_SPACING}.dp))", depth + 1) if spacer_after
            lines << indent("}", depth)
            lines.join("\n")
          else
            required_imports&.add(:r_class)
            painter = "painterResource(id = R.drawable.#{Helpers::ResourceResolver.drawable_name(image_name)})"
            icon = build_icon_call(painter, content_desc, depth, json_data, required_imports)
            spacer_after ? "#{icon}\n#{spacer}" : icon
          end
        end

        def self.build_icon_call(painter, content_desc, depth, json_data, required_imports)
          tint = json_data['tintColor'] || json_data['fontColor']
          composable = tint ? 'Icon' : 'Image'
          required_imports&.add(:image) unless tint

          lines = [indent("#{composable}(", depth),
                   indent("painter = #{painter},", depth + 1),
                   indent("contentDescription = #{content_desc},", depth + 1)]
          if tint
            tint_color = Helpers::ResourceResolver.process_color(tint, required_imports)
            lines << indent("modifier = Modifier.size(#{ICON_SIZE}.dp),", depth + 1)
            lines << indent("tint = #{tint_color}", depth + 1)
          else
            lines << indent("modifier = Modifier.size(#{ICON_SIZE}.dp)", depth + 1)
          end
          lines << indent(")", depth)
          lines.join("\n")
        end

        # Apply text attributes if specified (fontColor handled in ButtonDefaults.buttonColors).
        # All font attrs (fontFamily/font/fontWeight/fontSize) flow through the unified
        # Configuration.Font.resolve(FontSpec(...)) hook so the app's fontProvider sees
        # the full context.
        def self.build_text_code(json_data, text, depth, required_imports, fills: false)
          font_args = Helpers::FontSpecHelper.build_font_spec_args(json_data, required_imports)
          # `textAlign` is declared on Button and no converter read the
          # spelling on either mobile platform (plan 49 lane C:
          # Button.textAlign). The vocabulary is the shared one Label uses.
          align = json_data['textAlign'] &&
                  TextComponent.compose_text_align(json_data['textAlign'], json_data['type'] || 'Button')
          required_imports&.add(:text_align) if align
          align_arg = align ? "\n" + indent("textAlign = #{align},", depth + 1) : ''
          # The text is placed across the button by textAlign (4f ruling
          # 2026-09-27, round 17; centre by default): the Text takes the
          # button's width, which the button's content Row centred a wrap-width
          # Text in, so TextAlign.Start / End drew it in the middle. Only a
          # button of a width of its own (declared, not wrapContent, or
          # weighted): a wrap-width one is its text's width, and filling there
          # would stretch it to its parent. Not beside an icon.
          if fills && align && bounded_width?(json_data)
            align_arg += "\n" + indent("modifier = Modifier.fillMaxWidth(),", depth + 1)
          end

          unless font_args[:has_any]
            return indent("Text(#{text})", depth) if align_arg.empty?

            return indent("Text(", depth) +
                   "\n" + indent("text = #{text},", depth + 1) +
                   align_arg.chomp(',') +
                   "\n" + indent(")", depth)
          end

          var_name = next_resolved_var
          resolve_block = Helpers::FontSpecHelper.emit_resolve_block(var_name, font_args, depth, required_imports)
          text_arg_lines = Helpers::FontSpecHelper.text_arg_lines(var_name, depth, required_imports)

          resolve_block + "\n" + indent("Text(", depth) +
            "\n" + indent("text = #{text},", depth + 1) +
            align_arg +
            "\n" + text_arg_lines +
            "\n" + indent(")", depth)
        end

        # textAlign as the icon row's arrangement (the pair's place), or nil:
        # no textAlign, or a button with no width of its own.
        ICON_ROW_ARRANGEMENT = {
          'left' => 'Arrangement.Start',
          'center' => 'Arrangement.Center',
          'right' => 'Arrangement.End'
        }.freeze

        def self.icon_row_arrangement(json_data)
          return nil unless json_data['textAlign'] && bounded_width?(json_data)

          Helpers::BoundValue.enum(json_data['textAlign'], ICON_ROW_ARRANGEMENT,
                                   bound_default: 'Arrangement.Center', declared: [json_data['type'] || 'Button', 'textAlign'])
        end

        # Whether the button has a width of its own: a declared width that is
        # not wrapContent, or a weight along a row.
        def self.bounded_width?(json_data)
          width = json_data['width']
          return true if json_data['weight'] || json_data['widthWeight']

          !width.nil? && !%w[wrapContent wrap_content].include?(width.to_s)
        end

        # An icon-only button has no accessible name unless the icon carries
        # one, so the asset name becomes the contentDescription. Alongside a
        # label the icon is decorative and stays out of the a11y tree.
        def self.humanize_image_name(image_name)
          image_name.to_s.sub(/\.[a-z0-9]+\z/i, '').tr('_-', '  ')
        end

        private

        def self.to_camel_case(snake_case_string)
          return snake_case_string unless snake_case_string.include?('_')
          parts = snake_case_string.split('_')
          parts[0] + parts[1..-1].map(&:capitalize).join
        end

        # A Kotlin string literal — the one escaper (`$` included).
        def self.quote(text)
          JsonUIShared::StringLiterals.kotlin(text)
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