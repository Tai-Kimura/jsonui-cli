# frozen_string_literal: true

require_relative '../helpers/binding_expression'
require_relative '../helpers/modifier_builder'

# Generates Compose code for the `Embed` view type. Embeds another screen as
# a region of the parent layout; the embedded screen owns its own ViewModel.
#
# v1 (P1): emits EmbedContainer wrapping a direct call to the embedded
# screen's generated composable. params/events wiring is added in P2.
#
# See jsonui-cli/docs/plans/2026-05-11-embed-feature.md.

module KjuiTools
  module Compose
    module Components
      class EmbedComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          screen = json_data['screen']
          if screen.nil? || screen.to_s.empty?
            return indent('// Embed: missing required `screen` attribute', depth)
          end

          embed_id = json_data['id'] || 'embed'
          navigation_mode = json_data['navigationMode'] || 'delegate'
          isolated = navigation_mode == 'isolated'
          nav_mode_kotlin = isolated ? 'EmbedNavigationMode.Isolated' : 'EmbedNavigationMode.Delegate'
          params = json_data['params'] || {}
          events = json_data['events'] || {}

          # Imports needed in the generated parent screen file.
          required_imports&.add(:embed_container)
          # `hiltViewModel(...)` works for BOTH Hilt-injected and no-arg
          # ViewModels — Hilt VMs resolve via HiltViewModelFactory, plain
          # VMs fall back to NewInstanceFactory. The old emit of
          # `androidx.lifecycle.viewmodel.compose.viewModel(...)` crashed
          # at runtime for Hilt VMs (NoSuchMethodException on no-arg ctor).
          required_imports&.add(:hilt_viewmodel)
          # The embedded screen's composable lives alongside other view files;
          # compose_builder's import resolver maps "tabview:Name" → import path
          # and APPENDS "View" itself (compose_builder.rb:1092). So we must
          # register the PascalCase name WITHOUT the "View" suffix — same
          # convention as TabView (`tabview_component.rb:25-26`). Registering
          # "HomeView" here would round-trip to "HomeViewView".
          required_imports&.add("tabview:#{embedded_screen_pascal(screen)}")
          required_imports&.add(:embedded_event) unless events.empty?
          required_imports&.add(:embed_isolated_navigation) if isolated

          code  = indent("// Embed: #{screen}", depth)
          if isolated
            # Version-skew guard: the isolated call site references
            # EmbedIsolatedNavigation (new in 2.12.0), so building against an
            # older KotlinJsonUI fails at compile time instead of silently
            # degrading to delegate mode.
            code += "\n" + indent('// Requires KotlinJsonUI >= 2.12.0 (navigationMode: "isolated")', depth)
          end
          code += "\n" + indent('EmbedContainer(', depth)

          # Build a modifier chain for the EmbedContainer call so authoring-
          # time attributes (weight, width/height, margins, paddings) actually
          # take effect on Android. Prior to this, those attrs were silently
          # dropped — `Row { Embed(weight=1) Embed(weight=1) }` rendered as a
          # full-width first pane with the second pane sized to 0px. Library
          # support (KotlinJsonUI >= 2.8.4) wraps the embedded content in a
          # Box(modifier=modifier) so scope-bound modifiers like RowScope.weight
          # reach a Layout node.
          modifier_str = build_embed_modifier(json_data, depth, required_imports, parent_type)
          unless modifier_str.empty?
            code += modifier_str + ','
          end

          code += "\n" + indent("embedId = \"#{embed_id}\",", depth + 1)
          unless params.empty?
            code += "\n" + indent('params = mapOf(', depth + 1)
            params.each_with_index do |(key, value), idx|
              expr = render_param_value(value)
              comma = idx == params.size - 1 ? '' : ','
              code += "\n" + indent("\"#{key}\" to #{expr}#{comma}", depth + 2)
            end
            code += "\n" + indent('),', depth + 1)
          end
          trailing_after_mode = isolated || !events.empty?
          code += "\n" + indent("navigationMode = #{nav_mode_kotlin}#{trailing_after_mode ? ',' : ''}", depth + 1)
          if isolated
            code += "\n" + indent("isolatedNavigation = EmbedIsolatedNavigation.Automatic#{events.empty? ? '' : ','}", depth + 1)
          end
          unless events.empty?
            code += "\n" + indent('eventBridge = { event ->', depth + 1)
            code += "\n" + indent('if (event is EmbeddedEvent.Named) {', depth + 2)
            code += "\n" + indent('when (event.name) {', depth + 3)
            events.each do |event_name, handler|
              code += "\n" + indent("\"#{event_name}\" -> viewModel.#{handler}(event.payload)", depth + 4)
            end
            code += "\n" + indent('}', depth + 3)
            code += "\n" + indent('}', depth + 2)
            code += "\n" + indent('}', depth + 1)
          end
          code += "\n" + indent(') { embedScope ->', depth)
          code += "\n" + indent("#{embedded_view_class(screen)}(", depth + 1)
          code += "\n" + indent('viewModel = androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel(', depth + 2)
          code += "\n" + indent('viewModelStoreOwner = embedScope.viewModelStoreOwner,', depth + 3)
          code += "\n" + indent("key = \"#{embed_id}\"", depth + 3)
          code += "\n" + indent(')', depth + 2)
          code += "\n" + indent(')', depth + 1)
          code += "\n" + indent('}', depth)
          code
        end

        # Build the modifier chain for the EmbedContainer call site. Mirrors
        # the order used by ContainerComponent so behavior is consistent with
        # `View` / other containers: testTag → margins → weight (if Row/Column
        # parent) → size → padding. The full set is intentionally narrower
        # than ContainerComponent — Embed does not need alignment, alpha,
        # background, clickable, or the size-intrinsic adjustment (the embed
        # content composable owns those concerns internally).
        def self.build_embed_modifier(json_data, depth, required_imports, parent_type)
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          if parent_type == 'Row' || parent_type == 'Column'
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          end
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          return '' if modifiers.empty?
          Helpers::ModifierBuilder.format(modifiers, depth)
        end

        # Convert screen value (layout JSON filename, snake_case) to its
        # generated composable class name (PascalCase + "View").
        # PascalCase input passes through for backward compat.
        def self.embedded_view_class(screen)
          "#{embedded_screen_pascal(screen)}View"
        end

        # Just the PascalCase form of the screen name, without the "View" suffix.
        # Used for import registration (compose_builder appends "View" itself).
        def self.embedded_screen_pascal(screen)
          if screen.include?('_')
            screen.split('_').map(&:capitalize).join
          else
            screen[0].to_s.upcase + screen[1..].to_s
          end
        end

        # Render a single params value as Kotlin expression. Supports literals,
        # @{binding} → `data.{prop}` (leaf-only — the validator rejects
        # bindings at object positions), and nested literal objects →
        # inline `mapOf(...)` (recursive).
        def self.render_param_value(value)
          if value.is_a?(String) && value =~ /^@\{(.+)\}$/
            # Params-leaf context: path only. `??` defaults are forbidden
            # here (binding-default-in-params — defaults belong to the
            # embedded screen's data section); the shared parser keeps the
            # emit valid Kotlin even for invalid authoring.
            "data.#{Helpers::BindingExpression.path_only(Regexp.last_match(1))}"
          elsif value.is_a?(String)
            "\"#{value}\""
          elsif value == true || value == false
            value.to_s
          elsif value.is_a?(Integer)
            value.to_s
          elsif value.is_a?(Float)
            "#{value}f"
          elsif value.is_a?(Hash)
            return 'emptyMap<String, Any>()' if value.empty?
            entries = value.map { |k, v| "\"#{k}\" to #{render_param_value(v)}" }
            "mapOf(#{entries.join(', ')})"
          else
            # Fallback (arrays are a validate error upstream; unreachable
            # for valid layouts)
            value.inspect
          end
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
