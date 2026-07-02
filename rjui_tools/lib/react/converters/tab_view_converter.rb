# frozen_string_literal: true

require_relative 'base_converter'
require_relative '../helpers/lucide_icon_helper'

module RjuiTools
  module React
    module Converters
      class TabViewConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          tabs = attributes['tabs'] || []

          selected_binding = build_selected_binding
          on_change = build_on_change

          # Build tab bar items
          tab_items_jsx = tabs.each_with_index.map do |tab, index|
            build_tab_item(tab, index, selected_binding)
          end.join("\n")

          # Build tab content panels
          tab_panels_jsx = tabs.each_with_index.map do |tab, index|
            build_tab_panel(tab, index, selected_binding, indent + 4)
          end.join("\n")

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}>
            #{indent_str(indent + 2)}<div className="flex-1 overflow-auto">
            #{tab_panels_jsx}
            #{indent_str(indent + 2)}</div>
            #{indent_str(indent + 2)}<nav className="#{build_nav_class}">
            #{tab_items_jsx}
            #{indent_str(indent + 2)}</nav>
            #{indent_str(indent)}</div>
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = ['flex', 'flex-col', 'h-screen']

          # Width/Height
          classes << TailwindMapper.map_width(attributes['width'])
          classes << TailwindMapper.map_height(attributes['height'])

          # Background
          if attributes['background']
            if has_binding?(attributes['background'])
              @dynamic_styles ||= {}
              @dynamic_styles['backgroundColor'] = convert_binding(attributes['background'])
            else
              classes << TailwindMapper.map_color(attributes['background'], 'bg')
            end
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_nav_class
          classes = ['flex', 'border-t', 'border-gray-200']

          # Tab bar background
          if attributes['tabBarBackground']
            if has_binding?(attributes['tabBarBackground'])
              # Handle binding - will need dynamic style
              classes << 'bg-white' # fallback
            else
              classes << TailwindMapper.map_color(attributes['tabBarBackground'], 'bg')
            end
          else
            classes << 'bg-white'
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_tab_item(tab, index, selected_binding)
          raw_title = tab['title'] || "Tab #{index + 1}"
          resolved_title = convert_binding(raw_title)
          title = if resolved_title != raw_title && resolved_title.include?('{')
                    resolved_title
                  else
                    raw_title
                  end
          icon = tab['icon'] || 'circle'
          badge = tab['badge']
          icon_type = tab['iconType'] || 'system'

          # Build icon component
          icon_jsx = build_icon(icon, tab['selectedIcon'], index, selected_binding, icon_type)

          # Build badge if present
          badge_jsx = build_badge(badge) if badge

          # Build button classes
          button_class = build_tab_button_class(index, selected_binding)

          # Build button style for dynamic colors
          button_style = build_tab_button_style(index, selected_binding)
          style_attr = button_style ? "\n#{indent_str(8)}style={#{button_style}}" : ''

          # Show/hide labels
          show_labels = attributes['showLabels'] != false
          label_jsx = show_labels ? "\n#{indent_str(8)}<span className=\"text-xs mt-1\">#{title}</span>" : ''

          on_change = build_on_change

          # Build tab id for test automation (selectTab action)
          tab_id = extract_id ? "#{extract_id}_tab_#{index}" : nil
          tab_id_attr = tab_id ? " id=\"#{tab_id}\"" : ''

          <<~JSX.chomp
            #{indent_str(6)}<button#{tab_id_attr}
            #{indent_str(8)}className={`#{button_class}`}#{style_attr}
            #{indent_str(8)}onClick={() => #{on_change}?.(#{index})}
            #{indent_str(6)}>
            #{indent_str(8)}<div className="relative">
            #{icon_jsx}#{badge_jsx ? "\n#{badge_jsx}" : ''}
            #{indent_str(8)}</div>#{label_jsx}
            #{indent_str(6)}</button>
          JSX
        end

        def build_tab_button_class(index, selected_binding)
          tint = attributes['tintColor'] || 'blue-600'
          unselected = attributes['unselectedColor'] || 'gray-500'

          # `cursor-pointer` is required because Tailwind's preflight resets
          # the default browser pointer cursor on <button> back to the regular
          # arrow — tabs would otherwise feel non-interactive on hover.
          base_classes = 'flex-1 flex flex-col items-center justify-center py-2 px-1 transition-colors cursor-pointer'

          # Check if colors are bindings - use dynamic Tailwind class names
          if has_binding?(tint) || has_binding?(unselected)
            tint_prop = has_binding?(tint) ? extract_binding_property(tint) : "'#{tint}'"
            unselected_prop = has_binding?(unselected) ? extract_binding_property(unselected) : "'#{unselected}'"
            # Generate dynamic Tailwind class: text-${colorName}
            "${#{selected_binding} === #{index} ? '#{base_classes} text-' + #{tint_prop} : '#{base_classes} text-' + #{unselected_prop} + ' hover:opacity-80'}"
          else
            tint_class = TailwindMapper.map_color(tint, 'text')
            unselected_class = TailwindMapper.map_color(unselected, 'text')
            "${#{selected_binding} === #{index} ? '#{base_classes} #{tint_class}' : '#{base_classes} #{unselected_class} hover:text-gray-700'}"
          end
        end

        def build_tab_button_style(index, selected_binding)
          # No longer needed - using Tailwind classes instead
          nil
        end

        def build_icon(icon, selected_icon, index, selected_binding, icon_type = 'system')
          if icon_type == 'resource'
            # Use image from public/icons folder
            # Convert icon names: ic_home -> home, ic_home_filled -> home-filled
            icon_path = convert_icon_name_to_path(icon)
            selected_icon_path = selected_icon ? convert_icon_name_to_path(selected_icon) : icon_path
            if icon_path != selected_icon_path
              "#{indent_str(10)}{#{selected_binding} === #{index} ? <img src=\"/icons/#{selected_icon_path}.svg\" className=\"w-6 h-6\" alt=\"\" /> : <img src=\"/icons/#{icon_path}.svg\" className=\"w-6 h-6\" alt=\"\" />}"
            else
              "#{indent_str(10)}<img src=\"/icons/#{icon_path}.svg\" className=\"w-6 h-6\" alt=\"\" />"
            end
          else
            # Map SF Symbol/Material icon names to Lucide React icons
            icon_name = map_to_lucide_icon(icon)
            selected_icon_name = selected_icon ? map_to_lucide_icon(selected_icon) : icon_name

            if selected_icon
              "#{indent_str(10)}{#{selected_binding} === #{index} ? <#{selected_icon_name} className=\"w-6 h-6\" /> : <#{icon_name} className=\"w-6 h-6\" />}"
            else
              "#{indent_str(10)}<#{icon_name} className=\"w-6 h-6\" />"
            end
          end
        end

        def build_badge(badge)
          if has_binding?(badge)
            binding_prop = extract_binding_property(badge)
            "#{indent_str(10)}{#{binding_prop} && <span className=\"absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center\">{#{binding_prop}}</span>}"
          elsif badge.is_a?(Integer) && badge > 0
            "#{indent_str(10)}<span className=\"absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center\">#{badge}</span>"
          elsif badge.is_a?(String) && !badge.empty?
            "#{indent_str(10)}<span className=\"absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full px-1 min-w-4 h-4 flex items-center justify-center\">#{badge}</span>"
          end
        end

        def build_tab_panel(tab, index, selected_binding, indent)
          view_name = tab['view']

          if view_name
            # Strip path separators so we never emit `learn/indexData` as a
            # TS identifier. Use the last segment of the path — that matches
            # the file name build_command.rb derives components from
            # (Layouts/learn/index.json → learn/Index.tsx) and the subdir
            # logic in react_generator.rb's import collector.
            base_name = view_name.split('/').last
            # Convert snake_case to PascalCase for React component name
            pascal_name = base_name.split('_').map(&:capitalize).join
            # Generate data prop name from view name (e.g., home -> homeData, item_card -> itemCardData)
            data_prop_name = base_name.split('_').each_with_index.map { |part, i| i == 0 ? part.downcase : part.capitalize }.join + 'Data'
            content = "<#{pascal_name} data={data.#{data_prop_name}!} />"
          else
            content = "<div className=\"p-4\">#{tab['title'] || "Tab #{index + 1}"} content</div>"
          end

          <<~JSX.chomp
            #{indent_str(indent)}{#{selected_binding} === #{index} && (
            #{indent_str(indent + 2)}#{content}
            #{indent_str(indent)})}
          JSX
        end

        def build_selected_binding
          # selectedTabIndex is the definitions alias of selectedIndex
          selected = attributes['selectedIndex']

          if selected && has_binding?(selected)
            extract_binding_property(selected)
          else
            'data.selectedTab'
          end
        end

        def build_on_change
          # Canonical name is onValueChange; onTabChange / onPageChanged
          # are the definitions aliases for TabView.
          handler = attributes['onValueChange']

          if handler && has_binding?(handler)
            extract_binding_property(handler)
          else
            # Generate setter from the binding
            selected = attributes['selectedIndex']
            raw_binding = if selected && has_binding?(selected)
                            extract_raw_binding_property(selected)
                          else
                            'selectedTab'
                          end
            setter_name = "set#{raw_binding[0].upcase}#{raw_binding[1..]}"
            add_viewmodel_data_prefix(setter_name)
          end
        end

        # Convert icon name to file path - just use the icon name as-is
        def convert_icon_name_to_path(icon_name)
          icon_name
        end

        # Map SF Symbol/Material icon names to Lucide React icon component names
        # Delegates to LucideIconHelper so react_generator.rb can share the
        # same mapping when collecting icons for the `lucide-react` import.
        def map_to_lucide_icon(icon)
          Helpers::LucideIconHelper.map_to_lucide(icon)
        end
      end
    end
  end
end
