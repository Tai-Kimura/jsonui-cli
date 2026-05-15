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
        # Keys that `build_responsive_modifiers` coalesces into a single
        # `.frame(...)` call. `collect_modifiers_for` is invoked with these
        # in `exclude_keys` so apply_modifiers' own frame_constraints emit
        # doesn't duplicate the line.
        FRAME_CENTER_KEYS = %w[
          minWidth maxWidth minHeight maxHeight
          centerHorizontal centerVertical centerInParent
        ].freeze

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

            # Apply modifiers that change per branch. Three emit phases:
            #   1. build_responsive_modifiers — single combined `.frame(...)`
            #      for min/max width/height + center* (its own logic for
            #      coalescing center + max into one .frame call). Inner.
            #   2. collect_modifiers_for — runs apply_modifiers against the
            #      branch-merged attrs and returns the full modifier set
            #      (padding / margin / background / cornerRadius / border /
            #      alpha / shadow / etc.). FRAME_CENTER_KEYS are excluded so
            #      we don't double-emit alongside (1).
            #   3. Optional outer `.frame(.infinity, alignment: .center)` —
            #      only when both a numeric center-on-axis AND a matchParent
            #      width/height collide in the same branch. The inner frame
            #      from (1) constrains to N, decorations from (2) paint on
            #      that constrained layer, and this outer frame expands to
            #      parent width so the constrained-and-decorated block is
            #      centered in the parent. Without this split, the bare
            #      `width: matchParent → .infinity` emit from apply_frame_size
            #      lands BETWEEN the inner frame and the decorations,
            #      causing background/border to paint on a full-width layer
            #      (regression: sjui-view-responsive-maxwidth-border-overflow).
            modifiers = build_responsive_modifiers(attrs, converter)
            modifiers.each { |mod| lines << "#{indent}#{mod}" }

            center_h_overrides_width =
              (attrs['centerHorizontal'] == true || attrs['centerInParent'] == true) &&
              attrs['width'] == 'matchParent' &&
              numeric_dimension?(attrs['maxWidth'])
            center_v_overrides_height =
              (attrs['centerVertical'] == true || attrs['centerInParent'] == true) &&
              attrs['height'] == 'matchParent' &&
              numeric_dimension?(attrs['maxHeight'])

            extra_exclude = []
            extra_exclude << 'width' if center_h_overrides_width
            extra_exclude << 'height' if center_v_overrides_height

            if converter.respond_to?(:collect_modifiers_for)
              extra = converter.collect_modifiers_for(
                attrs, exclude_keys: FRAME_CENTER_KEYS + extra_exclude
              )
              extra.each { |mod| lines << "#{indent}#{mod}" }
            end

            if center_h_overrides_width || center_v_overrides_height
              outer_args = []
              outer_args << 'maxWidth: .infinity' if center_h_overrides_width
              outer_args << 'maxHeight: .infinity' if center_v_overrides_height
              outer_args << 'alignment: .center'
              lines << "#{indent}.frame(#{outer_args.join(', ')})"
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

            # When the branch combines a center flag with a matchParent on the
            # same axis AND a finite maxWidth/maxHeight, the inner-constraint
            # frame supersedes matchParent. Strip the matchParent value so
            # apply_frame_size doesn't emit a redundant `.frame(.infinity)`
            # at the wrong position in the chain (between the maxWidth
            # constraint and the decorations). Mirrors the same rule applied
            # in generate_container_function.
            center_h_overrides_width =
              (branch_component['centerHorizontal'] == true || branch_component['centerInParent'] == true) &&
              branch_component['width'] == 'matchParent' &&
              numeric_dimension?(branch_component['maxWidth'])
            center_v_overrides_height =
              (branch_component['centerVertical'] == true || branch_component['centerInParent'] == true) &&
              branch_component['height'] == 'matchParent' &&
              numeric_dimension?(branch_component['maxHeight'])
            branch_component.delete('width') if center_h_overrides_width
            branch_component.delete('height') if center_v_overrides_height

            converter = converter_factory.create_converter(branch_component, 3, action_manager, converter_factory, view_registry)
            if converter
              branch_code = converter.convert
              branch_lines = branch_code.split("\n")
              branch_indent = condition || index > 0 ? "    " : ""
              branch_lines.each do |bl|
                lines << "#{branch_indent}#{bl}"
              end

              # Outer `.frame(.infinity, alignment: .center)` so the
              # constrained-and-decorated inner block centers in its parent.
              # See regression: sjui-markdowntext-custom-converter-
              # centerhorizontal-missing — without this, MarkdownText (or any
              # leaf-path extension converter) keeps `maxWidth: N` but
              # silently drops the centerHorizontal positioning.
              needs_outer_center_h =
                (attrs['centerHorizontal'] == true || attrs['centerInParent'] == true) &&
                numeric_dimension?(attrs['maxWidth'])
              needs_outer_center_v =
                (attrs['centerVertical'] == true || attrs['centerInParent'] == true) &&
                numeric_dimension?(attrs['maxHeight'])
              if needs_outer_center_h || needs_outer_center_v
                outer_args = []
                outer_args << 'maxWidth: .infinity' if needs_outer_center_h
                outer_args << 'maxHeight: .infinity' if needs_outer_center_v
                outer_args << 'alignment: .center'
                outer_indent = condition || index > 0 ? "            " : "        "
                lines << "#{outer_indent}.frame(#{outer_args.join(', ')})"
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
        #
        # Container size + center-alignment overrides (`maxWidth`, `maxHeight`,
        # `minWidth`, `minHeight`, `centerHorizontal`, `centerVertical`,
        # `centerInParent`) are emitted here as a single combined `.frame(...)`
        # so multiple calls don't stack incorrectly. The outer
        # `apply_non_responsive_modifiers` path strips overridden keys, so any
        # frame modifier for these keys MUST be (re-)emitted per branch — both
        # for the overridden branch and the default branch — otherwise nothing
        # is applied.
        #
        # Out of scope (handled v2):
        #   width/height structural overrides, padding/margin/background.
        #
        # @param attrs [Hash] merged attributes for a branch
        # @param converter [BaseViewConverter] for helper access (currently unused)
        # @return [Array<String>] modifier lines
        def self.build_responsive_modifiers(attrs, _converter)
          frame_args = []

          max_width = attrs['maxWidth']
          max_height = attrs['maxHeight']
          min_width = attrs['minWidth']
          min_height = attrs['minHeight']
          center_h = attrs['centerHorizontal'] == true
          center_v = attrs['centerVertical'] == true
          center_p = attrs['centerInParent'] == true

          # centerInParent expands into both axes.
          center_h ||= center_p
          center_v ||= center_p

          # If center is requested without an explicit max on that axis, fall
          # back to .infinity so the parent gives us room to center within.
          if center_h && max_width.nil?
            max_width = '.infinity'
          end
          if center_v && max_height.nil?
            max_height = '.infinity'
          end

          frame_args << "minWidth: #{format_dimension(min_width)}" unless min_width.nil?
          frame_args << "maxWidth: #{format_dimension(max_width)}" unless max_width.nil?
          frame_args << "minHeight: #{format_dimension(min_height)}" unless min_height.nil?
          frame_args << "maxHeight: #{format_dimension(max_height)}" unless max_height.nil?

          # Any center request → `.center`. SwiftUI's frame alignment only
          # matters along the constrained axis, so a uniform `.center` is the
          # least surprising choice for the centerHorizontal-only case (which
          # the bug report explicitly expects).
          frame_args << 'alignment: .center' if center_h || center_v

          modifiers = []
          modifiers << ".frame(#{frame_args.join(', ')})" unless frame_args.empty?
          modifiers
        end

        # True when the value is a finite numeric dimension (Number or
        # all-digit String). `.infinity` / `matchParent` / bindings return
        # false. Used to decide whether a `maxWidth` / `maxHeight` override
        # forms a real constraint that justifies the inner+outer two-frame
        # responsive layout.
        def self.numeric_dimension?(value)
          case value
          when Numeric then true
          when String then value.match?(/\A\d+(\.\d+)?\z/)
          else false
          end
        end

        # Render a dimension literal. Numeric stays numeric; `.infinity` stays
        # as-is; everything else is passed through (caller is expected to have
        # validated upstream).
        def self.format_dimension(value)
          case value
          when Numeric then value.to_s
          when '.infinity' then '.infinity'
          else value.to_s
          end
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
