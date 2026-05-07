# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class TabviewComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # TabView maps to NavigationBar with NavigationBarItem in Compose (Material 3)
          required_imports&.add(:navigation_bar)
          required_imports&.add(:remember_state)
          required_imports&.add(:scaffold)
          required_imports&.add(:painter_resource)
          required_imports&.add(:r_class)
          required_imports&.add(:safe_area_config)
          required_imports&.add(:composition_local_provider)

          tabs = json_data['tabs'] || []

          # Add imports for tab views
          tabs.each do |tab|
            if tab['view']
              pascal_name = tab['view'].split('_').map(&:capitalize).join
              required_imports&.add("tabview:#{pascal_name}")
            end
          end

          # Generate state variable for selected tab
          state_var = "selectedTab"
          selected_binding = json_data['selectedIndex']

          code = indent("// TabView with NavigationBar", depth)

          # If there's a binding, use it; otherwise create local state
          if selected_binding && selected_binding.is_a?(String) && selected_binding.start_with?('@{')
            binding_prop = selected_binding.gsub(/@\{|\}/, '')
            state_expr = "data.#{binding_prop}"
            setter_expr = "viewModel.updateData(mapOf(\"#{binding_prop}\" to it))"
          else
            code += "\n" + indent("var #{state_var} by remember { mutableStateOf(0) }", depth)
            state_expr = state_var
            setter_expr = "#{state_var} = it"
          end

          code += "\n\n" + indent("Scaffold(", depth)
          code += "\n" + indent("bottomBar = {", depth + 1)

          # NavigationBar
          code += "\n" + indent("NavigationBar(", depth + 2)

          # Tab bar background color
          if json_data['tabBarBackground']
            bg_color = Helpers::ResourceResolver.process_color(json_data['tabBarBackground'], required_imports)
            code += "\n" + indent("containerColor = #{bg_color},", depth + 3)
          end

          code += "\n" + indent(") {", depth + 2)

          # Generate NavigationBarItem for each tab
          tabs.each_with_index do |tab, index|
            title = tab['title'] || "Tab #{index + 1}"
            icon = tab['icon'] || 'circle'
            selected_icon = tab['selectedIcon'] || icon
            icon_type = tab['iconType'] || 'system'

            code += "\n" + indent("NavigationBarItem(", depth + 3)
            code += "\n" + indent("selected = #{state_expr} == #{index},", depth + 4)
            code += "\n" + indent("onClick = { #{setter_expr.gsub('it', index.to_s)} },", depth + 4)

            # Icon - handle iconType for system vs resource
            code += "\n" + indent("icon = {", depth + 4)
            if icon_type == 'resource'
              # Use drawable resource
              if icon != selected_icon
                # Different icons for selected/unselected
                code += "\n" + indent("Icon(", depth + 5)
                code += "\n" + indent("painter = if (#{state_expr} == #{index}) painterResource(R.drawable.#{selected_icon}) else painterResource(R.drawable.#{icon}),", depth + 6)
                code += "\n" + indent("contentDescription = \"#{title}\"", depth + 6)
                code += "\n" + indent(")", depth + 5)
              else
                code += "\n" + indent("Icon(", depth + 5)
                code += "\n" + indent("painter = painterResource(R.drawable.#{icon}),", depth + 6)
                code += "\n" + indent("contentDescription = \"#{title}\"", depth + 6)
                code += "\n" + indent(")", depth + 5)
              end
            else
              # Use Material Icons (system)
              required_imports&.add(:material_icons)
              material_icon = to_icon_name(icon)
              material_selected_icon = to_icon_name(selected_icon)
              if icon != selected_icon
                code += "\n" + indent("Icon(", depth + 5)
                code += "\n" + indent("imageVector = if (#{state_expr} == #{index}) Icons.Filled.#{material_selected_icon} else Icons.Outlined.#{material_icon},", depth + 6)
                code += "\n" + indent("contentDescription = \"#{title}\"", depth + 6)
                code += "\n" + indent(")", depth + 5)
              else
                code += "\n" + indent("Icon(", depth + 5)
                code += "\n" + indent("imageVector = Icons.Filled.#{material_icon},", depth + 6)
                code += "\n" + indent("contentDescription = \"#{title}\"", depth + 6)
                code += "\n" + indent(")", depth + 5)
              end
            end
            code += "\n" + indent("},", depth + 4)

            # Label (show/hide based on showLabels)
            show_labels = json_data['showLabels'] != false
            if show_labels
              code += "\n" + indent("label = { Text(\"#{title}\") },", depth + 4)
            end

            # Tint colors
            if json_data['tintColor'] || json_data['unselectedColor']
              tint = json_data['tintColor'] ? Helpers::ResourceResolver.process_color(json_data['tintColor'], required_imports) : 'MaterialTheme.colorScheme.primary'
              unselected = json_data['unselectedColor'] ? Helpers::ResourceResolver.process_color(json_data['unselectedColor'], required_imports) : 'MaterialTheme.colorScheme.onSurfaceVariant'
              code += "\n" + indent("colors = NavigationBarItemDefaults.colors(", depth + 4)
              code += "\n" + indent("selectedIconColor = #{tint},", depth + 5)
              code += "\n" + indent("selectedTextColor = #{tint},", depth + 5)
              code += "\n" + indent("unselectedIconColor = #{unselected},", depth + 5)
              code += "\n" + indent("unselectedTextColor = #{unselected}", depth + 5)
              code += "\n" + indent(")", depth + 4)
            end

            # Badge
            if tab['badge']
              badge_value = tab['badge']
              if badge_value.is_a?(String) && badge_value.start_with?('@{')
                binding_prop = badge_value.gsub(/@\{|\}/, '')
                code = code.gsub(/icon = \{/, "icon = {\n#{indent('BadgedBox(badge = { Badge { Text(\"${data.' + binding_prop + '}\") } }) {', depth + 5)}")
              elsif badge_value.is_a?(Integer) && badge_value > 0
                code = code.gsub(/icon = \{/, "icon = {\n#{indent("BadgedBox(badge = { Badge { Text(\"#{badge_value}\") } }) {", depth + 5)}")
              end
            end

            code += "\n" + indent(")", depth + 3)
          end

          code += "\n" + indent("}", depth + 2)
          code += "\n" + indent("}", depth + 1)
          code += "\n" + indent(") { innerPadding ->", depth)

          # Tab content using when expression
          # Only apply bottom padding for NavigationBar - child views handle their own top safe area
          if tabs.any?
            code += "\n" + indent("Box(modifier = Modifier.padding(bottom = innerPadding.calculateBottomPadding())) {", depth + 1)
            # Provide SafeAreaConfig to tell child views to ignore bottom safe area
            code += "\n" + indent("CompositionLocalProvider(", depth + 2)
            code += "\n" + indent("LocalSafeAreaConfig provides SafeAreaConfig(ignoreBottom = true)", depth + 3)
            code += "\n" + indent(") {", depth + 2)
            code += "\n" + indent("when (#{state_expr}) {", depth + 3)

            tabs.each_with_index do |tab, index|
              code += "\n" + indent("#{index} -> {", depth + 4)

              # Content for each tab - reference view by name
              view_name = tab['view']
              if view_name
                # Convert snake_case to PascalCase for Kotlin class name
                pascal_name = view_name.split('_').map(&:capitalize).join
                code += "\n" + indent("#{pascal_name}View()", depth + 5)
              else
                code += "\n" + indent("Text(\"#{tab['title'] || "Tab #{index + 1}"} content\")", depth + 5)
              end

              code += "\n" + indent("}", depth + 4)
            end

            code += "\n" + indent("}", depth + 3)
            code += "\n" + indent("}", depth + 2)
            code += "\n" + indent("}", depth + 1)
          end

          code += "\n" + indent("}", depth)
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

        # Convert icon name to Material Icons format
        # e.g., "house" -> "Home", "person" -> "Person"
        def self.to_icon_name(icon)
          # Map common SF Symbol names to Material Icons
          icon_map = {
            'house' => 'Home',
            'house.fill' => 'Home',
            'person' => 'Person',
            'person.fill' => 'Person',
            'gearshape' => 'Settings',
            'gearshape.fill' => 'Settings',
            'gear' => 'Settings',
            'magnifyingglass' => 'Search',
            'heart' => 'Favorite',
            'heart.fill' => 'Favorite',
            'star' => 'Star',
            'star.fill' => 'Star',
            'bell' => 'Notifications',
            'bell.fill' => 'Notifications',
            'cart' => 'ShoppingCart',
            'cart.fill' => 'ShoppingCart',
            'list.bullet' => 'List',
            'square.grid.2x2' => 'GridView',
            'circle' => 'Circle'
          }
          icon_map[icon] || icon.split('.').first.capitalize
        end
      end
    end
  end
end
