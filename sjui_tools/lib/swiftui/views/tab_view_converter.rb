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
          selected_index = @component['selectedIndex']
          if selected_index && is_binding?(selected_index)
            binding_prop = extract_binding_property(selected_index)
            add_line "TabView(selection: $data.#{binding_prop}) {"
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
                add_line "Text(\"#{tab['title'] || "Tab #{index + 1}"}\")"
              end

              # Add tabItem modifier
              indent do
                add_line ".tabItem {"
                indent do
                  # Build Label with icon
                  icon = tab['icon'] || 'circle'
                  selected_icon = tab['selectedIcon'] || icon
                  title = tab['title'] || "Tab #{index + 1}"
                  icon_type = tab['iconType'] || 'system'

                  # Get selection binding for conditional icon
                  selected_index = @component['selectedIndex']
                  selection_var = if selected_index && is_binding?(selected_index)
                                    "data.#{extract_binding_property(selected_index)}"
                                  else
                                    "0" # fallback
                                  end

                  if icon_type == 'resource'
                    # Use Image from asset catalog
                    if icon != selected_icon
                      # Different icons for selected/unselected
                      add_line "Label {"
                      indent do
                        add_line "Text(\"#{title}\")"
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
                        add_line "Text(\"#{title}\")"
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
                        add_line "Text(\"#{title}\")"
                      end
                      add_line "} icon: {"
                      indent do
                        add_line "Image(systemName: #{selection_var} == #{index} ? \"#{selected_icon}\" : \"#{icon}\")"
                      end
                      add_line "}"
                    else
                      add_line "Label(\"#{title}\", systemImage: \"#{icon}\")"
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
                    add_line ".badge(\"#{badge_value}\")"
                  end
                end

                # Add tag for selection
                add_line ".tag(#{index})"
              end
            end
          end

          add_line "}"

          # Note: tintColor is handled by BaseViewConverter.apply_modifiers

          # Apply tab bar background (iOS 16+)
          if @component['tabBarBackground']
            bg_color = @component['tabBarBackground']
            if is_binding?(bg_color)
              binding_prop = extract_binding_property(bg_color)
              add_modifier_line ".toolbarBackground(Color(data.#{binding_prop}), for: .tabBar)"
            else
              color = get_swiftui_color(bg_color)
              add_modifier_line ".toolbarBackground(#{color}, for: .tabBar)"
            end
            add_modifier_line ".toolbarBackground(.visible, for: .tabBar)"
          end

          # Apply onTabChange handler
          if @component['onTabChange']
            handler = @component['onTabChange']
            if is_binding?(handler)
              handler_prop = extract_binding_property(handler)
              add_modifier_line ".onChange(of: selectedTab) { _, newValue in"
              add_modifier_line "    data.#{handler_prop}?(newValue)"
              add_modifier_line "}"
            end
          end

          apply_modifiers
          generated_code
        end
      end
    end
  end
end
