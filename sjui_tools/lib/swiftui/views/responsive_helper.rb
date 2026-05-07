# frozen_string_literal: true

require_relative '../../core/responsive_resolver'

module SjuiTools
  module SwiftUI
    module Views
      # Helper module for generating responsive SwiftUI code.
      #
      # When a component has a "responsive" block, instead of generating inline code,
      # we generate a separate @ViewBuilder function with if/else branches for each
      # size class. The inline code is replaced with a function call.
      #
      # For containers (View/ScrollView with children): generates a wrapper function
      # that takes a @ViewBuilder content closure. Children are rendered once via content().
      #
      # For leaf components (Label, Image, etc.): generates a function with the full
      # view per branch.
      module ResponsiveHelper
        # Check if a component has responsive overrides
        # @param component [Hash] the JSON component
        # @return [Boolean]
        def responsive?(component)
          JsonUIShared::ResponsiveResolver.responsive?(component)
        end

        # Check if any component in the tree has responsive overrides.
        # Used to determine if @Environment vars are needed in the generated struct.
        # @param component [Hash] root JSON component
        # @return [Boolean]
        def self.has_responsive_descendant?(component)
          return false unless component.is_a?(Hash)
          return true if JsonUIShared::ResponsiveResolver.responsive?(component)

          children = component['child'] || component['children']
          if children.is_a?(Array)
            children.any? { |child| has_responsive_descendant?(child) }
          elsif children.is_a?(Hash)
            has_responsive_descendant?(children)
          else
            false
          end
        end

        # Build the Swift condition expression for a size class key.
        # @param size_class [String] e.g. "regular", "landscape", "regular-landscape"
        # @return [String] Swift condition expression
        def self.size_class_condition(size_class)
          parsed = JsonUIShared::ResponsiveResolver.parse_size_class(size_class)
          conditions = []

          case parsed[:width]
          when 'compact'
            conditions << 'horizontalSizeClass == .compact'
          when 'regular'
            conditions << 'horizontalSizeClass == .regular'
          when 'medium'
            # No medium size class on iOS; fall back to compact
            conditions << 'horizontalSizeClass == .compact'
          end

          if parsed[:landscape]
            conditions << 'verticalSizeClass == .compact'
          end

          conditions.join(' && ')
        end

        # Generate a responsive wrapper function for a container component.
        # The function takes a @ViewBuilder content closure and renders the
        # container (HStack/VStack) per branch, passing children via content().
        #
        # @param func_name [String] the function name (e.g. "responsiveSection0")
        # @param component [Hash] the JSON component with responsive block
        # @param converter [BaseViewConverter] converter instance for accessing helpers
        # @return [String] Swift function code
        def self.generate_container_function(func_name, component, converter)
          branches = JsonUIShared::ResponsiveResolver.build_branches(component)
          lines = []
          lines << "    @ViewBuilder private func #{func_name}<Content: View>("
          lines << "        @ViewBuilder content: () -> Content"
          lines << "    ) -> some View {"

          branches.each_with_index do |branch, index|
            condition = branch[:size_class] ? size_class_condition(branch[:size_class]) : nil
            attrs = branch[:attrs]

            if index == 0 && condition
              lines << "        if #{condition} {"
            elsif condition
              lines << "        } else if #{condition} {"
            else
              # Default branch (last)
              if index > 0
                lines << "        } else {"
              end
            end

            # Generate the container line for this branch
            container_code = build_container_line(attrs, converter)
            indent = condition || index > 0 ? "            " : "        "
            lines << "#{indent}#{container_code} {"
            lines << "#{indent}    content()"
            lines << "#{indent}}"

            # Apply modifiers that change per branch
            modifiers = build_responsive_modifiers(attrs, converter)
            modifiers.each do |mod|
              lines << "#{indent}#{mod}"
            end
          end

          lines << "        }" if branches.size > 1
          lines << "    }"
          lines << ""
          lines.join("\n")
        end

        # Generate a responsive function for a leaf component.
        # Each branch generates the full view with its overridden attributes.
        #
        # @param func_name [String] the function name
        # @param component [Hash] the JSON component with responsive block
        # @param converter_factory [ConverterFactory] factory to create converters per branch
        # @param indent_level [Integer] current indent level
        # @param action_manager [ActionManager] action manager
        # @param view_registry [ViewRegistry] view registry
        # @param binding_registry [BindingHandlerRegistry] binding registry
        # @return [String] Swift function code
        def self.generate_leaf_function(func_name, component, converter_factory, indent_level, action_manager, view_registry, binding_registry)
          branches = JsonUIShared::ResponsiveResolver.build_branches(component)
          lines = []
          lines << "    @ViewBuilder private func #{func_name}() -> some View {"

          branches.each_with_index do |branch, index|
            condition = branch[:size_class] ? size_class_condition(branch[:size_class]) : nil
            attrs = branch[:attrs]

            if index == 0 && condition
              lines << "        if #{condition} {"
            elsif condition
              lines << "        } else if #{condition} {"
            else
              if index > 0
                lines << "        } else {"
              end
            end

            # Create a converter for this branch's attributes and generate the view
            branch_component = attrs.dup
            branch_component.delete('responsive')
            converter = converter_factory.create_converter(branch_component, 3, action_manager, converter_factory, view_registry)
            if converter
              branch_code = converter.convert
              branch_lines = branch_code.split("\n")
              branch_indent = condition || index > 0 ? "    " : ""
              branch_lines.each do |bl|
                lines << "#{branch_indent}#{bl}"
              end
            end
          end

          lines << "        }" if branches.size > 1
          lines << "    }"
          lines << ""
          lines.join("\n")
        end

        # Build the container opening (e.g., "HStack(alignment: .leading, spacing: 24)")
        # based on attributes.
        # @param attrs [Hash] merged attributes for a branch
        # @param converter [BaseViewConverter] for helper access
        # @return [String] container Swift code (without trailing " {")
        def self.build_container_line(attrs, converter)
          orientation = attrs['orientation']
          spacing = attrs['spacing'] || 0
          gravity = attrs['gravity']

          if orientation == 'horizontal'
            alignment = resolve_hstack_alignment(gravity)
            "HStack(alignment: #{alignment}, spacing: #{spacing})"
          else
            alignment = resolve_vstack_alignment(gravity)
            "VStack(alignment: #{alignment}, spacing: #{spacing})"
          end
        end

        # Build modifiers that vary across responsive branches.
        # Currently returns an empty array — modifiers like padding, background, etc.
        # that change per branch are included in the container itself.
        # This hook exists for future extension.
        # @param attrs [Hash] merged attributes for a branch
        # @param converter [BaseViewConverter] for helper access
        # @return [Array<String>] modifier lines
        def self.build_responsive_modifiers(attrs, _converter)
          []
        end

        # Resolve VStack alignment from gravity string
        # @param gravity [String, nil] gravity value
        # @return [String] SwiftUI alignment value
        def self.resolve_vstack_alignment(gravity)
          return '.leading' unless gravity

          horizontal = extract_horizontal(gravity)
          case horizontal
          when 'center', 'centerHorizontal' then '.center'
          when 'right' then '.trailing'
          else '.leading'
          end
        end

        # Resolve HStack alignment from gravity string
        # @param gravity [String, nil] gravity value
        # @return [String] SwiftUI alignment value
        def self.resolve_hstack_alignment(gravity)
          return '.center' unless gravity

          vertical = extract_vertical(gravity)
          case vertical
          when 'center', 'centerVertical' then '.center'
          when 'bottom' then '.bottom'
          when 'top' then '.top'
          else '.center'
          end
        end

        # @return [String] horizontal component from gravity
        def self.extract_horizontal(gravity)
          if gravity.is_a?(String) && gravity.include?('|')
            parts = gravity.split('|')
            parts.find { |p| %w[left center right centerHorizontal].include?(p) } || 'left'
          elsif gravity.is_a?(Array)
            gravity.find { |g| %w[left center right centerHorizontal].include?(g) } || 'left'
          else
            %w[left center right centerHorizontal].include?(gravity) ? gravity : 'left'
          end
        end

        # @return [String] vertical component from gravity
        def self.extract_vertical(gravity)
          if gravity.is_a?(String) && gravity.include?('|')
            parts = gravity.split('|')
            parts.find { |p| %w[top center bottom centerVertical].include?(p) } || 'top'
          elsif gravity.is_a?(Array)
            gravity.find { |g| %w[top center bottom centerVertical].include?(g) } || 'top'
          else
            %w[top center bottom centerVertical].include?(gravity) ? gravity : 'top'
          end
        end

        # State variable declarations needed when responsive is used
        # @return [Array<String>] Swift state variable lines
        def self.environment_declarations
          [
            '@Environment(\.horizontalSizeClass) private var horizontalSizeClass',
            '@Environment(\.verticalSizeClass) private var verticalSizeClass'
          ]
        end
      end
    end
  end
end
