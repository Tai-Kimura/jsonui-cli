# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/bound_value'
require_relative '../helpers/static_seed'

module KjuiTools
  module Compose
    module Components
      # SwitchComponent handles both Switch (primary) and Toggle (alias) component types
      # Switch is the primary component name. Toggle is supported as an alias for backward compatibility.
      class SwitchComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Switch/Toggle uses 'isOn', 'value', 'checked', or 'bind' for binding
          # Priority: isOn > value > checked > bind
          state_attr = json_data['isOn'] || json_data['value'] || json_data['checked']
          checked = if state_attr
            if state_attr.is_a?(String) && state_attr.match(/@\{([^}]+)\}/)
              variable = $1
              "data.#{variable}"
            else
              # Direct boolean value
              state_attr.to_s
            end
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          else
            'false'
          end

          # A Switch draws a label when it declares one, and `labelAttributes`
          # is not the only way to declare it: `label` is the canonical row
          # (with `text` as its declared alias), the same shape CheckBox and
          # Radio already carry. Only the bag opened this branch, so a Switch
          # with a plain `label` drew the control and dropped the text.
          has_label = json_data['labelAttributes'] || label_text_of(json_data)

          # A static value (or none) is the seed of the switch's own state
          # (Helpers::StaticSeed); a bound one is the view model's.
          unless checked.start_with?('data.')
            return Helpers::StaticSeed.wrap(checked, depth, required_imports) do |d, state|
              if has_label
                generate_with_label(json_data, d, required_imports, parent_type, state, seeded: state)
              else
                generate_switch_only(json_data, d, required_imports, parent_type, state, seeded: state)
              end
            end
          end

          if has_label
            generate_with_label(json_data, depth, required_imports, parent_type, checked)
          else
            generate_switch_only(json_data, depth, required_imports, parent_type, checked)
          end
        end

        def self.generate_switch_only(json_data, depth, required_imports, parent_type, checked, seeded: nil)
          code = indent("Switch(", depth)
          code += "\n" + indent("checked = #{checked},", depth + 1)

          # onCheckedChange handler
          binding_variable = nil
          state_attr_val = json_data['isOn'] || json_data['value'] || json_data['checked']
          if state_attr_val.is_a?(String) && state_attr_val.match(/@\{([^}]+)\}/)
            binding_variable = $1
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          end

          code += "\n" + indent("onCheckedChange = #{checked_change_lambda(json_data, binding_variable, seeded: seeded)},", depth + 1)

          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          # userInteractionEnabled / touchDisabledState stop this node and
          # what is in it (ModifierBuilder.build_interaction_blocker); this
          # component builds no clickable, which is where it came from.
          modifiers.concat(Helpers::ModifierBuilder.build_interaction_blocker(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(common_stages(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          # Add weight modifier if in Row or Column
          if parent_type == 'Row' || parent_type == 'Column'
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          end

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?

          # Switch colors
          # tint and tintColor are aliases for onTintColor
          track_color = json_data['onTintColor'] || json_data['tint'] || json_data['tintColor']
          # `trackTintColor` is the declared spelling for the track itself —
          # it skins the OFF state, which `onTintColor` overrides when on
          # (switch.trackColors in shared/core/attribute_semantics.json).
          off_track_color = json_data['trackTintColor'] || json_data['offTintColor']
          if track_color || off_track_color || json_data['thumbTintColor']
            required_imports&.add(:switch_colors)
            colors_params = []

            if track_color
              checkedtrackcolor_resolved = Helpers::ResourceResolver.process_color(track_color, required_imports)
              colors_params << "checkedTrackColor = #{checkedtrackcolor_resolved}"
            end

            if off_track_color
              uncheckedtrackcolor_resolved = Helpers::ResourceResolver.process_color(off_track_color, required_imports)
              colors_params << "uncheckedTrackColor = #{uncheckedtrackcolor_resolved}"
            end

            if json_data['thumbTintColor']
              checkedthumbcolor_resolved = Helpers::ResourceResolver.process_color(json_data['thumbTintColor'], required_imports)
              colors_params << "checkedThumbColor = #{checkedthumbcolor_resolved}"
              # thumbTintColor skins the thumb in BOTH states (UIKit
              # heritage — mirrors the dynamic component).
              colors_params << "uncheckedThumbColor = #{checkedthumbcolor_resolved}"
            end

            if colors_params.any?
              code = Helpers::ModifierBuilder.join_argument(code, ",\n" + indent("colors = SwitchDefaults.colors(", depth + 1))
              code += "\n" + colors_params.map { |param| indent(param, depth + 2) }.join(",\n")
              code += "\n" + indent(")", depth + 1)
            end
          end

          # Handle enabled attribute
          if json_data.key?('enabled')
            if json_data['enabled'].is_a?(String) && json_data['enabled'].start_with?('@{')
              inner_expr = json_data['enabled'].match(/@\{([^}]+)\}/)[1]
              code = Helpers::ModifierBuilder.join_argument(code, ",\n" + indent("enabled = #{Helpers::BindingExpression.value_access(inner_expr, negatable: true)}", depth + 1))
            else
              code = Helpers::ModifierBuilder.join_argument(code, ",\n" + indent("enabled = #{json_data['enabled']}", depth + 1))
            end
          end

          code += "\n" + indent(")", depth)
          code
        end

        def self.generate_with_label(json_data, depth, required_imports, parent_type, checked, seeded: nil)
          # Row container for label + switch
          code = indent("Row(", depth)
          code += "\n" + indent("verticalAlignment = Alignment.CenterVertically,", depth + 1)

          # Build modifiers for Row
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          # userInteractionEnabled / touchDisabledState stop this node and
          # what is in it (ModifierBuilder.build_interaction_blocker); this
          # component builds no clickable, which is where it came from.
          modifiers.concat(Helpers::ModifierBuilder.build_interaction_blocker(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(common_stages(json_data, parent_type, required_imports, labelled: true))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          if parent_type == 'Row' || parent_type == 'Column'
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          end

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
          code += "\n" + indent(") {", depth)

          # labelPosition — which side of the Switch the label sits on.
          #
          # The label was always emitted first, i.e. always leading, and the
          # attribute was read by nobody: the Compose codegen ignored it while
          # the Dynamic runtime honoured it (DynamicToggleComponent). Built as a
          # separate string so it can be placed either side.
          label_code = build_label_code(json_data, depth, required_imports)
          label_position = (json_data['labelPosition'] || 'leading').to_s.downcase
          code += label_code unless label_position == 'trailing'

          # Switch
          code += "\n" + indent("Switch(", depth + 1)
          code += "\n" + indent("checked = #{checked},", depth + 2)

          # onCheckedChange handler
          binding_variable = nil
          state_attr_val = json_data['isOn'] || json_data['value'] || json_data['checked']
          if state_attr_val.is_a?(String) && state_attr_val.match(/@\{([^}]+)\}/)
            binding_variable = $1
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          end

          code += "\n" + indent("onCheckedChange = #{checked_change_lambda(json_data, binding_variable, seeded: seeded)}", depth + 2)

          # Switch colors — same canonical/legacy pair as the block above.
          track_color = json_data['onTintColor'] || json_data['tint'] || json_data['tintColor']
          off_track_color = json_data['trackTintColor'] || json_data['offTintColor']
          if track_color || off_track_color || json_data['thumbTintColor']
            required_imports&.add(:switch_colors)
            colors_params = []

            if track_color
              checkedtrackcolor_resolved = Helpers::ResourceResolver.process_color(track_color, required_imports)
              colors_params << "checkedTrackColor = #{checkedtrackcolor_resolved}"
            end

            if off_track_color
              uncheckedtrackcolor_resolved = Helpers::ResourceResolver.process_color(off_track_color, required_imports)
              colors_params << "uncheckedTrackColor = #{uncheckedtrackcolor_resolved}"
            end

            if json_data['thumbTintColor']
              checkedthumbcolor_resolved = Helpers::ResourceResolver.process_color(json_data['thumbTintColor'], required_imports)
              colors_params << "checkedThumbColor = #{checkedthumbcolor_resolved}"
              # thumbTintColor skins the thumb in BOTH states (UIKit
              # heritage — mirrors the dynamic component).
              colors_params << "uncheckedThumbColor = #{checkedthumbcolor_resolved}"
            end

            if colors_params.any?
              code = Helpers::ModifierBuilder.join_argument(code, ",\n" + indent("colors = SwitchDefaults.colors(", depth + 2))
              code += "\n" + colors_params.map { |param| indent(param, depth + 3) }.join(",\n")
              code += "\n" + indent(")", depth + 2)
            end
          end

          # Handle enabled attribute
          if json_data.key?('enabled')
            if json_data['enabled'].is_a?(String) && json_data['enabled'].start_with?('@{')
              inner_expr = json_data['enabled'].match(/@\{([^}]+)\}/)[1]
              code = Helpers::ModifierBuilder.join_argument(code, ",\n" + indent("enabled = #{Helpers::BindingExpression.value_access(inner_expr, negatable: true)}", depth + 2))
            else
              code = Helpers::ModifierBuilder.join_argument(code, ",\n" + indent("enabled = #{json_data['enabled']}", depth + 2))
            end
          end

          code += "\n" + indent(")", depth + 1)
          code += label_code if label_position == 'trailing'
          code += "\n" + indent("}", depth)
          code
        end

        # size → offset → alpha → shadow → background: the View slots between
        # margins and padding. Size, shadow and background (with its
        # cornerRadius and border) are declared on `common` and were dropped by
        # both branches (kjui-dynamic-components-that-skip-the-common-
        # modifiers). There is no click here: the declared onClick is called
        # from onCheckedChange (checked_change_lambda). The labelled Row
        # carries the tag and the Switch inside it the `enabled`, so the Row
        # takes `disabled()` for a UI test to read; on the bare Switch the
        # control's own `enabled` is on the tagged node.
        def self.common_stages(json_data, parent_type, required_imports, labelled: false)
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          if labelled
            modifiers.concat(Helpers::ModifierBuilder.build_disabled_semantics(
              json_data, Helpers::ModifierBuilder.enabled_expression(json_data), required_imports
            ))
          end
          modifiers
        end

        # The Switch's own operation: write the bound value, run onValueChange
        # / onToggle, then the declared onClick
        # (ModifierBuilder.with_operation_click). The first three forms are the
        # ones this component always emitted.
        # The switch's own operation, in order: its own update — the bound
        # write, or the seeded state's (Helpers::StaticSeed, `seeded`) — then
        # onValueChange, then the declared onClick (with_operation_click).
        def self.checked_change_lambda(json_data, binding_variable, seeded: nil)
          handler = json_data['onValueChange'] || json_data['onToggle']
          view_id = json_data['id'] || 'switch'
          update = if binding_variable
                     "viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue))"
                   elsif seeded
                     "#{seeded} = newValue"
                   end
          lambda = if handler && !Helpers::ModifierBuilder.is_binding?(handler)
                     "{ // ERROR: #{handler} - camelCase events require binding format @{functionName} }"
                   else
                     handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(handler, view_id, 'newValue') if handler
                     body = [update, handler_call].compact
                     if body.empty? then '{ }'
                     elsif seeded && !binding_variable && !handler_call then "{ #{seeded} = it }"
                     else "{ newValue -> #{body.join('; ')} }"
                     end
                   end
          Helpers::ModifierBuilder.with_operation_click(lambda, json_data)
        end

        # The label's TEXT: the bag's own `text` outranks the flat spelling,
        # and `label` is the canonical flat row with `text` as its declared
        # alias. Same precedence the dynamic path settled on (a nested bag
        # outranks the flat spelling, KotlinJsonUI 8ed8a16).
        def self.label_text_of(json_data)
          bag = json_data['labelAttributes']
          (bag.is_a?(Hash) ? bag['text'] : nil) || json_data['label'] || json_data['text']
        end

        # One styling row: the bag wins where it declares, the flat spelling
        # answers where it does not. The flat `fontColor` / `fontSize` are
        # declared on Switch itself (51-E) and only the bag was ever read.
        def self.label_style_of(json_data, key)
          bag = json_data['labelAttributes']
          (bag.is_a?(Hash) ? bag[key] : nil) || json_data[key]
        end

        # The label Text block, as a string, so generate_with_label can put it
        # before or after the Switch depending on labelPosition.
        def self.build_label_code(json_data, depth, required_imports)
          out = "\n" + indent("Text(", depth + 1)
          # `label` is `["string", "binding"]`; the old string literal put the
          # characters `@{...}` on screen, which is the bug CheckBox already
          # fixed for the same spelling.
          out += "\n" + indent("text = #{Helpers::BoundValue.text(label_text_of(json_data) || '')},", depth + 2)

          font_size = label_style_of(json_data, 'fontSize')
          if font_size
            required_imports&.add(:text_unit) if Helpers::BoundValue.bound?(font_size)
            out += "\n" + indent("fontSize = #{Helpers::BoundValue.sp(font_size, null_expr: 'TextUnit.Unspecified')},", depth + 2)
          end

          font_color = label_style_of(json_data, 'fontColor')
          if font_color
            resolved = Helpers::ResourceResolver.process_color(font_color, required_imports)
            out += "\n" + indent("color = #{resolved},", depth + 2)
          end

          font = label_style_of(json_data, 'font')
          if font
            font_weight = font.to_s.downcase == 'bold' ? 'FontWeight.Bold' : 'FontWeight.Normal'
            out += "\n" + indent("fontWeight = #{font_weight},", depth + 2)
          end

          # weight(1f) on the label pushes the Switch to the far edge, which is
          # what you want on either side.
          out += "\n" + indent("modifier = Modifier.weight(1f)", depth + 2)
          out + "\n" + indent(")", depth + 1)
        end

        private

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
