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

          # A static index (or none) seeds the tab view's own state
          # (wrap_seeded); a page that passes `selectedTabIndex` still drives it.
          selected_attr = attributes['selectedIndex']
          @seeded = !(selected_attr && has_binding?(selected_attr))
          selected_binding = build_selected_binding
          on_change = build_on_change

          # Build tab bar items
          tab_items_jsx = tabs.each_with_index.map do |tab, index|
            build_tab_item(tab, index, selected_binding)
          end.join("\n")

          nav_class, nav_style = build_nav_parts

          # Build tab content panels
          tab_panels_jsx = tabs.each_with_index.map do |tab, index|
            build_tab_panel(tab, index, selected_binding, indent + 4)
          end.join("\n")

          # onValueChange is called when the selected tab's value changes — a
          # tap on another tab or a selectedIndex write — and not when the tab
          # view first appears or the selected tab is tapped again (the SSoT's
          # TabView.onValueChange, ruling 2026-10-02, as SwiftJsonUI's
          # `.onChange(of: selection)`). The file's JsonUIValueChange watches
          # the selection; a tap only writes it. Until jsonui-cli 1.9.6 the
          # tab's onClick called the handler, so a second tap on the selected
          # tab called it again and a selectedIndex write never did.
          value_change = if handler_name
                           "\n#{indent_str(indent + 2)}<JsonUIValueChange value={#{selected_binding}} " \
                             "onChange={(value) => #{tab_change_call(on_change, 'value')}} />"
                         else
                           ''
                         end

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}>
            #{indent_str(indent + 2)}<div className="flex-1 overflow-auto">
            #{tab_panels_jsx}
            #{indent_str(indent + 2)}</div>
            #{indent_str(indent + 2)}<nav className="#{nav_class}"#{nav_style}>
            #{tab_items_jsx}
            #{indent_str(indent + 2)}</nav>#{value_change}
            #{indent_str(indent)}</div>
          JSX
          jsx = wrap_seeded(jsx, indent, selected_attr.is_a?(Numeric) ? selected_attr.to_i : 0) if @seeded

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
              @dynamic_styles['backgroundColor'] = color_style_expr(attributes['background'])
            else
              classes << TailwindMapper.map_color(attributes['background'], 'bg')
            end
          end

          finalize_classes(classes)
        end

        # [class, style attribute] for the tab bar.
        #
        # The bound branch used to emit `bg-white # fallback` and stop there,
        # so a bound tabBarBackground was indistinguishable from declaring
        # nothing at all — the binding was dropped without a class, a style or
        # a warning. The <nav> is an inner element, so the root's
        # @dynamic_styles cannot reach it and it carries its own style. The
        # white class stays as the value the runtime falls back to.
        def build_nav_parts
          classes = ['flex', 'border-t', 'border-gray-200']
          style = {}

          # Tab bar background
          tab_bar_background = attributes['tabBarBackground']
          if tab_bar_background
            if has_binding?(tab_bar_background)
              style['backgroundColor'] = color_style_expr(tab_bar_background)
              classes << 'bg-white'
            else
              classes << TailwindMapper.map_color(tab_bar_background, 'bg')
            end
          else
            classes << 'bg-white'
          end

          [finalize_classes(classes), style_attr_for(style)]
        end

        def build_tab_item(tab, index, selected_binding)
          raw_title = tab['title'] || "Tab #{index + 1}"
          resolved_title = convert_text_binding(raw_title)
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
          disabled_attr = tab_disabled_attr
          button_class += ' disabled:opacity-50 disabled:cursor-not-allowed' unless disabled_attr.empty?

          # Build button style for dynamic colors
          button_style = build_tab_button_style(index, selected_binding)
          style_attr = button_style ? "\n#{indent_str(8)}style={#{button_style}}" : ''

          # Show/hide labels
          show_labels = attributes['showLabels'] != false
          label_jsx = show_labels ? "\n#{indent_str(8)}<span className=\"text-xs mt-1\">#{title}</span>" : ''

          # A tap writes the selection; the handler is JsonUIValueChange's.
          write = "#{selection_setter}?.(#{index})"

          # Build tab id for test automation (selectTab action)
          tab_id = extract_id ? "#{extract_id}_tab_#{index}" : nil
          tab_id_attr = tab_id ? " id=\"#{tab_id}\"" : ''

          <<~JSX.chomp
            #{indent_str(6)}<button#{tab_id_attr}
            #{indent_str(8)}className={`#{button_class}`}#{style_attr}
            #{indent_str(8)}onClick={#{@seeded ? "() => { setSeeded(#{index}); #{write}; }" : "() => #{write}"}}#{disabled_attr}
            #{indent_str(6)}>
            #{indent_str(8)}<div className="relative">
            #{icon_jsx}#{badge_jsx ? "\n#{badge_jsx}" : ''}
            #{indent_str(8)}</div>#{label_jsx}
            #{indent_str(6)}</button>
          JSX
        end

        # `enabled` (common: boolean or binding). false leaves the tabs where
        # they are: each tab's button is disabled, and a browser sends no
        # click to a disabled button, so neither the selection nor its
        # handler moves — `enabled: false` stops the operation, the rule the
        # five paths share (ticket control-onclick-is-called-differently-on-
        # every-path). Until 1.9.0 web read no `enabled` on a TabView and
        # its tabs switched regardless. A TabView that does not declare it
        # comes out as it did.
        def tab_disabled_attr
          enabled = attributes['enabled']
          if enabled.is_a?(String) && has_binding?(enabled)
            " disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' disabled'
          else
            ''
          end
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
            binding_prop = attribute_expression(badge)
            span = "<span className=\"absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center\">{#{binding_prop}}</span>"
            # Text around a binding (a template literal), or a binding that is
            # not one (a string), always has text: that badge is always drawn,
            # and a condition on it is one TypeScript rejects as always truthy.
            return "#{indent_str(10)}#{span}" if binding_prop.start_with?('`', '"')

            # A binding alone draws the badge while it has a value. Anything
            # but a plain path is parenthesised: `data.n ?? 'D' && <span>`
            # mixes `??` with `&&`, which JavaScript refuses to parse.
            condition = binding_prop.match?(/\A[\w$]+(?:\??\.[\w$]+)*\z/) ? binding_prop : "(#{binding_prop})"
            "#{indent_str(10)}{#{condition} && #{span}}"
          elsif badge.is_a?(Integer) && badge > 0
            "#{indent_str(10)}<span className=\"absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center\">#{badge}</span>"
          elsif badge.is_a?(String) && !badge.empty?
            "#{indent_str(10)}<span className=\"absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full px-1 min-w-4 h-4 flex items-center justify-center\">#{JsonUIShared::StringLiterals.jsx_text(badge)}</span>"
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
            content = "<div className=\"p-4\">#{JsonUIShared::StringLiterals.jsx_text("#{tab['title'] || "Tab #{index + 1}"} content")}</div>"
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
            "(#{extract_binding_property(selected)} ?? 0)"
          else
            # A literal (or none — tab 0) seeds the tab view's own state; a
            # page passing `selectedTabIndex` still overrides it. Without the
            # state the fallback was the literal itself, so a tap on a page
            # that passes no setter changed nothing.
            '(data.selectedTabIndex ?? seeded)'
          end
        end

        # The tab's call: the selection setter with the index, or a bound
        # onValueChange as the layout's data declares it — `()` with nothing,
        # `(String, X)` with the viewId first, anything else (and a handler
        # the data does not declare, which the Data model types as taking
        # the index) with the index. It was called with the index whatever
        # it took (TS2554 against a declared `() => void`); sjui and kjui call
        # it as declared too (get_event_handler_invocation).
        def tab_change_call(on_change, index)
          handler = attributes['onValueChange']
          name = string_event_handler?(handler) ? string_event_name(handler) : nil
          classes = config['_data_classes'] || {}
          return "#{on_change}?.(#{index})" unless name && classes.key?(name)

          params = self.class.declared_parameters(name, classes)
          return "#{on_change}?.()" if params.empty?
          return "#{on_change}?.(#{view_id_expr}, #{index})" if params.size == 2 && params.first == 'String'

          "#{on_change}?.(#{index})"
        end

        # The bound onValueChange (canonical; onTabChange / onPageChanged are
        # the definitions aliases for TabView) as the data property it names,
        # or nil.
        def handler_name
          handler = attributes['onValueChange']
          return nil unless string_event_handler?(handler)

          resolve_handler_property(has_binding?(handler) ? handler : string_event_name(handler))
        end

        def build_on_change
          handler_name || selection_setter
        end

        # The selection's setter: `set<Prop>` of a bound selectedIndex, else
        # the implicit `selectedTabIndex`'s — the data model declares both
        # (spelling it anything else left the JSX referencing a property no
        # generated Data interface has).
        def selection_setter
          selected = attributes['selectedIndex']
          raw_binding = if selected && has_binding?(selected)
                          extract_raw_binding_property(selected)
                        else
                          'selectedTabIndex'
                        end
          add_viewmodel_data_prefix("set#{raw_binding[0].upcase}#{raw_binding[1..]}")
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
