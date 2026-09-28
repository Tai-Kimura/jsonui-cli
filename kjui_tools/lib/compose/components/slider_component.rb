# frozen_string_literal: true

require_relative '../helpers/bound_value'
require_relative '../helpers/static_seed'
require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/inherited_tint'
require_relative '../../core/normalization'

module KjuiTools
  module Compose
    module Components
      class SliderComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Slider binds through 'value' (a lone 'bind' arrives as it: JsonUIShared::BindFold)
          # A bound value reads through BoundValue.float: `data.v.toFloat()` did
          # not compile on a nullable property (`(data.v?.toFloat() ?: 0f)`
          # does), and spliced a `?? default` in as it stood. A static value
          # is `<value>f` as before.
          # The slider's `value` (a lone `bind` arrives as it:
          # JsonUIShared::BindFold at the dispatch).
          value = if !json_data['value'].nil?
            Helpers::BoundValue.float(json_data['value'], fallback: 0)
          else
            '0f'
          end
          
          # Canonical minimum/maximum with alias fallbacks (skipped on
          # L1-normalized layouts); 'min'/'max' are undeclared legacy
          # spellings, always honored last.
          # The undeclared range was 0..100 here, which the SSoT now contradicts:
          # `minimum` declares `default: 0` and `maximum` declares `default: 1`,
          # so an undeclared slider runs 0 .. 1 — the same unitless-track
          # convention Progress.progress and opacity already carry. Only the
          # DEFAULT moves; a layout that declares its own bounds is untouched.
          min_value = Core::Normalization.attr_lookup(json_data, 'minimum', 'minimumValue', 'minValue') || json_data['min'] || 0
          max_value = Core::Normalization.attr_lookup(json_data, 'maximum', 'maximumValue', 'maxValue') || json_data['max'] || 1

          # A static value is the seed of the slider's own state
          # (Helpers::StaticSeed); with no value the thumb starts at the
          # minimum, as on the other faces. A bound value is the view model's.
          # Bound is decided on the layout, not on the emitted text: a nullable
          # binding's expression starts `(data.…`, not `data.`.
          bound = Helpers::BoundValue.bound?(json_data['value'])
          unless bound
            seed = json_data['value'].nil? ? Helpers::BoundValue.float(min_value, fallback: 0) : value
            return Helpers::StaticSeed.wrap(seed, depth, required_imports) do |d, state|
              generate_body(json_data, d, required_imports, parent_type, state, min_value, max_value, state)
            end
          end
          generate_body(json_data, depth, required_imports, parent_type, value, min_value, max_value, nil)
        end

        def self.generate_body(json_data, depth, required_imports, parent_type, value, min_value, max_value, seeded)
          code = indent("Slider(", depth)
          code += "\n" + indent("value = #{value},", depth + 1)
          
          # onValueChange handler
          # The attribute written is the one shown: a bound `value` (a static
          # one writes the seeded state).
          binding_variable = nil
          if json_data['value'] && json_data['value'].is_a?(String) && json_data['value'].match(/@\{([^}]+)\}/)
            binding_variable = $1
          end
          
          view_id = Helpers::ModifierBuilder.view_id(json_data)
          on_value_change = Core::Normalization.attr_lookup(json_data, 'onValueChange', 'onValueChanged')
          if on_value_change
            # onValueChange (camelCase) -> binding format only (@{functionName})
            if Helpers::ModifierBuilder.is_binding?(on_value_change)
              if binding_variable
                # Both data binding and event handler: the lambda names its
                # parameter `newValue`, so the handler invocation must reference
                # `newValue` (an `it`-based call would not resolve).
                handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(on_value_change, view_id, 'newValue')
                code += "\n" + indent("onValueChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue.toDouble())); #{handler_call} },", depth + 1)
              else
                # Event handler only (implicit `it` parameter)
                handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(on_value_change, view_id, 'it')
                code += "\n" + indent("onValueChange = { #{seeded ? "#{seeded} = it; " : ''}#{handler_call} },", depth + 1)
              end
            else
              code += "\n" + indent("onValueChange = #{Helpers::ModifierBuilder.error_lambda("ERROR: #{on_value_change} - camelCase events require binding format @{functionName}")},", depth + 1)
            end
          elsif binding_variable
            # Update the bound variable only
            code += "\n" + indent("onValueChange = { newValue -> viewModel.updateData(mapOf(\"#{binding_variable}\" to newValue.toDouble())) },", depth + 1)
          else
            code += "\n" + indent(seeded ? "onValueChange = { #{seeded} = it }," : "onValueChange = { },", depth + 1)
          end
          # The declared onClick is called when the value change finishes —
          # the Slider's own operation, not an outer `.clickable`, whose
          # action would replace the Slider's own for TalkBack
          # (ModifierBuilder.operation_click_call).
          if (click = Helpers::ModifierBuilder.operation_click_call(json_data))
            code += "\n" + indent("onValueChangeFinished = { #{click} },", depth + 1)
          end
          
          # Value range
          # `min|maxValue` (and their `minimum`/`maximum` aliases) are
          # `["number", "binding"]`; the raw `#{...}f` interpolation put
          # `@{v}f` in code position (plan 49 lane C, 4 entries).
          # The fallbacks mirror the STATIC defaults just above (0 / 1). A
          # bound maximum falling back to 0 would collapse the range onto the
          # minimum and leave the slider unusable — the same fallback-collides-
          # with-the-attribute's-unset-value hazard B found on Label.lines.
          code += "\n" + indent("valueRange = #{Helpers::BoundValue.float(min_value, fallback: 0)}..#{Helpers::BoundValue.float(max_value, fallback: 1)},", depth + 1)
          
          # Steps
          step = json_data['step']
          if step && [step, min_value, max_value].any? { |v| Helpers::BoundValue.bound?(v) }
            # A bound step or range is decided at run time — `step > 0` on the
            # layout's `@{v}` raised ArgumentError, and `max - min` on a bound
            # end did too.
            range = "(#{Helpers::BoundValue.float(max_value, fallback: 1)} - #{Helpers::BoundValue.float(min_value, fallback: 0)})"
            per = Helpers::BoundValue.float(step, fallback: 0)
            code += "\n" + indent("steps = (if (#{per} > 0f) (#{range} / #{per}).toInt() - 1 else 0).coerceAtLeast(0),", depth + 1)
          elsif step && step > 0
            steps = ((max_value - min_value) / step.to_f).to_i - 1
            code += "\n" + indent("steps = #{steps},", depth + 1) if steps > 0
          end
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          # The node's gestures and blocker; the click is onValueChangeFinished
          # above, and `enabled` is the Slider's own parameter on this node.
          modifiers.concat(Helpers::ModifierBuilder.build_control_clickable(json_data, required_imports, enabled_on_node: true))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
          
          # Slider colors. The canonical spellings are the ones
          # attribute_definitions declares — `progressTintColor` for the
          # filled track, `trackTintColor` for the unfilled one; the
          # minimum/maximumTrackTintColor pair is the undeclared UIKit
          # legacy and reads canonical-first behind them (see the
          # slider.trackColors entry in shared/core/attribute_semantics.json).
          # `tintColor` is the UIKit accent: it colours the thumb and the
          # active track when nothing more specific is declared.
          thumb_tint = json_data['thumbTintColor'] || json_data['tintColor']
          active_tint = json_data['progressTintColor'] ||
                        json_data['minimumTrackTintColor'] || json_data['tintColor']
          inactive_tint = json_data['trackTintColor'] || json_data['maximumTrackTintColor']
          # The thumb and the filled track are the accent: the Slider's own,
          # else the tint a container handed down (InheritedTint) — so the
          # colors are always emitted.
          begin
            required_imports&.add(:slider_colors)
            colors_params = []

            thumbcolor_resolved = if thumb_tint
                                    Helpers::ResourceResolver.process_color(thumb_tint, required_imports)
                                  else
                                    Helpers::InheritedTint.accent(required_imports)
                                  end
            colors_params << "thumbColor = #{thumbcolor_resolved}"

            activetrackcolor_resolved = if active_tint
                                          Helpers::ResourceResolver.process_color(active_tint, required_imports)
                                        else
                                          Helpers::InheritedTint.accent(required_imports)
                                        end
            colors_params << "activeTrackColor = #{activetrackcolor_resolved}"
            
            if inactive_tint
              inactivetrackcolor_resolved = Helpers::ResourceResolver.process_color(inactive_tint, required_imports)
              colors_params << "inactiveTrackColor = #{inactivetrackcolor_resolved}"
            end
            
            if colors_params.any?
              code = Helpers::ModifierBuilder.join_argument(code, ",\n" + indent("colors = SliderDefaults.colors(", depth + 1))
              code += "\n" + colors_params.map { |param| indent(param, depth + 2) }.join(",\n")
              code += "\n" + indent(")", depth + 1)
            end
          end
          
          # Handle enabled attribute
          if json_data.key?('enabled')
            # `enabled` as every other stage reads it (enabled_expression): a
            # nullable binding is `(data.on ?: false)` — the bare `data.on` it
            # was did not type-check against the Boolean parameter.
            enabled = Helpers::ModifierBuilder.enabled_expression(json_data) || 'true'
            code = Helpers::ModifierBuilder.join_argument(code, ",\n" + indent("enabled = #{enabled}", depth + 1))
          end
          
          code += "\n" + indent(")", depth)
          code
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