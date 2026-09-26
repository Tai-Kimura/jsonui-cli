# frozen_string_literal: true

require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      class TabViewConverter < BaseViewConverter
        def initialize(component, indent_level = 0, action_manager = nil, converter_factory = nil, view_registry = nil, binding_registry = nil)
          super(component, indent_level, action_manager, binding_registry)
          @converter_factory = converter_factory
          @view_registry = view_registry
        end

        def convert
          tabs = @component['tabs'] || []

          # Build TabView with selection binding if provided
          selected_index = attr_with_alias('selectedIndex', 'selectedTabIndex')
          # The tab-change handler (tab_change_line) observes the selection:
          # without a selectedIndex the tab view holds one of its own.
          handler = tab_change_handler
          selection = nil
          if selected_index && is_binding?(selected_index)
            binding_prop = extract_binding_property(selected_index)
            selection = "data.#{binding_prop}"
            add_line "TabView(selection: $data.#{binding_prop}) {"
          elsif selected_index || handler
            # A literal selectedIndex seeds the initial tab (the dynamic
            # renderer and the UIKit runtime both honor it) — without a
            # selection binding TabView always opened the first tab.
            # No id: its position (position_name), not camelCased.
            state_name = @component['id'] ? "#{to_camel_case(@component['id'])}Selection" : "#{position_name('tabView')}Selection"
            @state_variables << "@State private var #{state_name}: Int = #{selected_index.to_i}"
            selection = state_name
            add_line "TabView(selection: $#{state_name}) {"
          else
            add_line "TabView {"
          end

          indent do
            tabs.each_with_index do |tab, index|
              # Generate content for each tab
              view_name = tab['view']
              if view_name
                # Reference to another layout file
                add_line "#{view_name.split('_').map(&:capitalize).join}View()"
              else
                # Placeholder content
                add_line "Text(#{swift_string_literal(tab['title'] || "Tab #{index + 1}")})"
              end

              # Add tabItem modifier
              indent do
                items_enabled = tab_items_enabled_line
                add_line items_enabled if items_enabled
                add_line ".tabItem {"
                indent do
                  # Build Label with icon
                  icon = tab['icon'] || 'circle'
                  selected_icon = tab['selectedIcon'] || icon
                  title = tab['title'] || "Tab #{index + 1}"
                  icon_type = tab['iconType'] || 'system'

                  # Get selection binding for conditional icon
                  selected_index = attr_with_alias('selectedIndex', 'selectedTabIndex')
                  selection_var = if selected_index && is_binding?(selected_index)
                                    "data.#{extract_binding_property(selected_index)}"
                                  else
                                    "0" # fallback
                                  end

                  # showLabels: false -> icon only. A tabItem whose content is
                  # just an image shows no title; an empty Text would still
                  # reserve the space the label would have taken.
                  if @component['showLabels'] == false
                    if icon_type == 'resource'
                      if icon != selected_icon
                        add_line "Image(#{selection_var} == #{index} ? \"#{selected_icon}\" : \"#{icon}\")"
                      else
                        add_line "Image(\"#{icon}\")"
                      end
                      add_line "    .renderingMode(.template)"
                    elsif icon != selected_icon
                      add_line "Image(systemName: #{selection_var} == #{index} ? \"#{selected_icon}\" : \"#{icon}\")"
                    else
                      add_line "Image(systemName: \"#{icon}\")"
                    end
                  elsif icon_type == 'resource'
                    # Use Image from asset catalog
                    if icon != selected_icon
                      # Different icons for selected/unselected
                      add_line "Label {"
                      indent do
                        add_line "Text(#{swift_string_literal(title)})"
                      end
                      add_line "} icon: {"
                      indent do
                        add_line "Image(#{selection_var} == #{index} ? \"#{selected_icon}\" : \"#{icon}\")"
                        add_line "    .renderingMode(.template)"
                      end
                      add_line "}"
                    else
                      add_line "Label {"
                      indent do
                        add_line "Text(#{swift_string_literal(title)})"
                      end
                      add_line "} icon: {"
                      indent do
                        add_line "Image(\"#{icon}\")"
                        add_line "    .renderingMode(.template)"
                      end
                      add_line "}"
                    end
                  else
                    # Use SF Symbols (system)
                    if icon != selected_icon
                      # Different icons for selected/unselected
                      add_line "Label {"
                      indent do
                        add_line "Text(#{swift_string_literal(title)})"
                      end
                      add_line "} icon: {"
                      indent do
                        add_line "Image(systemName: #{selection_var} == #{index} ? \"#{selected_icon}\" : \"#{icon}\")"
                      end
                      add_line "}"
                    else
                      add_line "Label(#{swift_string_literal(title)}, systemImage: \"#{icon}\")"
                    end
                  end
                end
                add_line "}"

                # Add badge if present
                if tab['badge']
                  badge_value = tab['badge']
                  if is_binding?(badge_value)
                    binding_prop = extract_binding_property(badge_value)
                    add_line ".badge(data.#{binding_prop})"
                  elsif badge_value.is_a?(Integer)
                    add_line ".badge(#{badge_value})"
                  else
                    add_line ".badge(#{swift_string_literal(badge_value)})"
                  end
                end

                # Add tag for selection
                add_line ".tag(#{index})"
              end
            end
          end

          add_line "}"

          # Note: tintColor is handled by BaseViewConverter.apply_modifiers

          # Apply tab bar background (iOS 16+).
          #
          # The bound branch built `Color(data.x)`, which is the ASSET-CATALOG
          # initializer `Color(_ name: String, bundle:)`. It compiles, so
          # nothing complained, and then it looked up an asset named after
          # whatever the property held — a hex string or a colors.json name
          # resolved to nothing. `get_swiftui_color` is the registry route
          # every other colour here takes.
          if @component['tabBarBackground']
            bg_color = @component['tabBarBackground']
            color = get_swiftui_color(bg_color)
            add_modifier_line ".toolbarBackground(#{color}, for: .tabBar)"
            add_modifier_line ".toolbarBackground(.visible, for: .tabBar)"
            # toolbarBackground alone leaves the bar unstyled on the
            # conformance render — the dynamic path routes through the
            # UITabBar appearance proxy for the same reason (33 cross-effect);
            # mirror it so both paths paint the bar (32 parity).
            add_modifier_line ".onAppear {"
            add_modifier_line "    UITabBar.appearance().backgroundColor = UIColor(#{color})"
            add_modifier_line "}"
          end

          # unselectedColor — SwiftUI exposes no modifier for the inactive tab
          # tint (.tint only sets the active one), so it goes through the
          # UITabBar appearance proxy, the same route Segment and Switch take
          # for their UIKit-only appearance keys.
          unselected = @component['unselectedColor']
          if unselected
            # Same asset-catalog trap as tabBarBackground above: `Color(data.x)`
            # compiles and resolves nothing.
            color = get_swiftui_color(unselected)
            add_modifier_line ".onAppear {"
            add_modifier_line "    UITabBar.appearance().unselectedItemTintColor = UIColor(#{color})"
            add_modifier_line "}"
          end

          # The tab-change handler, on the selection the tab view moves (the
          # view model's binding, or the tab view's own), called as the data
          # declares it (get_event_handler_invocation: `(Int)` with the new
          # index, `(String, Int)` with the viewId first, `()` with nothing).
          # It observed `selectedTab`, a name nothing declares: a TabView with
          # an onValueChange did not compile (spec
          # tab_view_enabled_stops_the_tabs_spec, compile_as_swift). The
          # Dynamic runtime calls it on the same change (TabViewWrapperView).
          if handler
            add_modifier_line ".onChange(of: #{selection}) { _, newValue in"
            add_modifier_line "    #{get_event_handler_invocation(handler, view_id, 'newValue')}"
            add_modifier_line "}"
          end

          apply_modifiers
          generated_code
        end

        private

        # `enabled` stops the tab items, not the tab view (4f's ruling,
        # jsonui-cli 1.9.0 — kjui's NavigationBarItem `enabled`, web's
        # `<button disabled>` per tab): the tab view's control is its row of
        # tabs, and what a tab shows is a layout of its own, which
        # `userInteractionEnabled` stops. `.disabled` on the TabView (twice:
        # the bag's and apply_outer_disabled's) disabled every control in the
        # tab shown as well (measured, SwiftJsonUI ConformanceHost
        # -tabEnabledProbe). SwiftUI has no modifier for a tab item's enabled
        # state before iOS 18.4, so SwiftJsonUI's `.jsonuiTabItemsEnabled`
        # sets the tab bar items' isEnabled, from each tab's content (only
        # the one on screen reaches the tab bar). `userInteractionEnabled`
        # stays register_hit_test_gate's.
        def register_interaction_gates
          @interaction_gates_registered = true
          register_hit_test_gate
        end

        # The tab view's own tap and gestures follow `enabled`, as kjui's
        # Scaffold gates them (gesture_gate) — `.disabled` stopped them with
        # everything the tab showed. `enabled: false` attaches no tap
        # (register_click_lines) and no gesture; a binding masks the tap as a
        # bound canTap does and gates each gesture's call.
        def tap_gate_condition
          enabled = @component['enabled']
          own = is_binding?(enabled) ? tap_gate_expr(enabled) : nil
          [own, super].compact.join(' && ').then { |gate| gate.empty? ? nil : gate }
        end

        def apply_long_press_to_bag
          own_gesture(:on_long_press) { super }
        end

        def apply_pan_to_bag
          own_gesture(:on_pan) { super }
        end

        def apply_pinch_to_bag
          own_gesture(:on_pinch) { super }
        end

        def own_gesture(slot)
          enabled = @component['enabled']
          return if enabled == false

          yield
          lines = @modifier_bag[slot]
          return unless lines && is_binding?(enabled)

          gate = tap_gate_expr(enabled)
          @modifier_bag.register(slot, Array(lines).map do |line|
            call = line.lstrip
            call.start_with?('data.') ? "#{line[0...(line.length - call.length)]}if #{gate} { #{call} }" : line
          end)
        end

        # onValueChange, the canonical name — onTabChange / onPageChanged are
        # its definitions aliases (L0 fallback only) — when it is a binding.
        def tab_change_handler
          handler = attr_with_alias('onValueChange', 'onTabChange', 'onPageChanged')
          handler if handler.is_a?(String) && is_binding?(handler)
        end

        # `.jsonuiTabItemsEnabled(false)` for `enabled: false`, the binding
        # for a bound one; nil when `enabled` does not disable.
        def tab_items_enabled_line
          enabled = @component['enabled']
          return '.jsonuiTabItemsEnabled(false)' if enabled == false
          return nil unless is_binding?(enabled)

          ".jsonuiTabItemsEnabled(#{tap_gate_expr(enabled)})"
        end
      end
    end
  end
end
