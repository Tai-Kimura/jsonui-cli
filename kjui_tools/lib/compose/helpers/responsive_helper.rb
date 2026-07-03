# frozen_string_literal: true

require_relative '../../core/responsive_resolver'

module KjuiTools
  module Compose
    module Helpers
      # Generates responsive Compose code for components with `responsive` blocks.
      #
      # For containers (components with children): generates a wrapper @Composable
      # that takes `content: @Composable () -> Unit` and switches layout per branch.
      #
      # For leaf components (no children): generates a @Composable that renders
      # the full view per branch.
      class ResponsiveHelper
        # Width thresholds match Material3's window-size-class boundaries
        # (compact <600dp, medium 600..839dp, expanded >=840dp). Width in dp
        # comes from LocalWindowInfo.containerSize (pixels → LocalDensity
        # conversion, truncated to Int so the range check stays Int) — the
        # deprecated LocalConfiguration.screenWidthDp read is gone. Kept as a
        # self-contained expression so the helper doesn't need a
        # `windowSizeClass` variable in scope, which generated screens don't
        # have.
        WIDTH_DP_EXPR =
          'with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp().value.toInt() }'
        WIDTH_CONDITIONS = {
          'compact'  => "#{WIDTH_DP_EXPR} < 600",
          'medium'   => "#{WIDTH_DP_EXPR} in 600..839",
          'regular'  => "#{WIDTH_DP_EXPR} >= 840"
        }.freeze

        # Resolved against a local `isLandscape` val that each generator emits
        # at the top of its function body.
        LANDSCAPE_CONDITION = 'isLandscape'.freeze

        # Landscape = window wider than tall from LocalWindowInfo.containerSize
        # (replaces the deprecated LocalConfiguration.orientation read; also
        # drops the full-qualified android Configuration reference previously
        # needed to avoid clashing with kjui's core Configuration).
        ISLANDSCAPE_DECLARATION =
          'val isLandscape = LocalWindowInfo.current.containerSize.let { it.width > it.height }'.freeze

        # Check if a component has responsive overrides
        def self.responsive?(component)
          JsonUIShared::ResponsiveResolver.responsive?(component)
        end

        # Build the condition expression for a size class key.
        # Returns a Kotlin boolean expression string, or nil for the default branch.
        def self.build_condition(size_class)
          return nil if size_class.nil?

          parsed = JsonUIShared::ResponsiveResolver.parse_size_class(size_class)
          conditions = []

          if parsed[:width]
            width_cond = WIDTH_CONDITIONS[parsed[:width]]
            conditions << width_cond if width_cond
          end

          conditions << LANDSCAPE_CONDITION if parsed[:landscape]

          return nil if conditions.empty?

          conditions.join(' && ')
        end

        # Generate a responsive wrapper composable for a container component.
        #
        # @param function_name [String] Name for the generated @Composable function
        # @param component [Hash] The JSON component with responsive block
        # @param depth [Integer] Indentation depth for the function body
        # @param required_imports [Set] Import set to populate
        # @param component_generator [Proc] A proc that takes (attrs, depth, required_imports)
        #   and returns the container opening code string (e.g., "Column(" with modifiers)
        # @return [Hash] { function_code: String, call_code: String }
        def self.generate_container_wrapper(function_name, component, depth, required_imports, &component_generator)
          add_responsive_imports(required_imports)

          branches = JsonUIShared::ResponsiveResolver.build_branches(component)

          # Build the function. The helper is emitted at file scope (NOT as a
          # nested local function), so `private` here is file-private and the
          # body has no captured `data` / `viewModel` / `windowSizeClass` from
          # any enclosing GeneratedView.
          func_lines = []
          func_lines << indent("@Composable", depth)
          func_lines << indent("private fun #{function_name}(", depth)
          func_lines << indent("    content: @Composable () -> Unit", depth)
          func_lines << indent(") {", depth)
          func_lines << indent("    #{ISLANDSCAPE_DECLARATION}", depth)

          # Build if/else chain
          first = true
          branches.each do |branch|
            condition = build_condition(branch[:size_class])
            attrs = branch[:attrs]

            if condition
              keyword = first ? 'if' : '} else if'
              func_lines << indent("    #{keyword} (#{condition}) {", depth)
              first = false
            else
              # Default branch
              if first
                # No conditional branches at all -- just emit the content directly
                container_code = component_generator.call(attrs, depth + 1, required_imports)
                func_lines << container_code
                func_lines << indent("}", depth)
                return {
                  function_code: func_lines.join("\n"),
                  call_code: nil
                }
              else
                func_lines << indent("    } else {", depth)
              end
            end

            # Generate container for this branch
            container_code = component_generator.call(attrs, depth + 2, required_imports)
            func_lines << container_code
          end

          func_lines << indent("    }", depth)
          func_lines << indent("}", depth)

          {
            function_code: func_lines.join("\n"),
            call_code: nil # call_code is built by caller
          }
        end

        # Generate a responsive composable for a leaf component (no children).
        #
        # @param function_name [String] Name for the generated @Composable function
        # @param component [Hash] The JSON component with responsive block
        # @param depth [Integer] Indentation depth
        # @param required_imports [Set] Import set to populate
        # @param component_generator [Proc] A proc that takes (attrs, depth, required_imports)
        #   and returns the full component code string
        # @return [Hash] { function_code: String }
        def self.generate_leaf_wrapper(function_name, component, depth, required_imports, &component_generator)
          add_responsive_imports(required_imports)

          branches = JsonUIShared::ResponsiveResolver.build_branches(component)

          func_lines = []
          func_lines << indent("@Composable", depth)
          func_lines << indent("private fun #{function_name}() {", depth)
          func_lines << indent("    #{ISLANDSCAPE_DECLARATION}", depth)

          first = true
          branches.each do |branch|
            condition = build_condition(branch[:size_class])
            attrs = branch[:attrs]

            if condition
              keyword = first ? 'if' : '} else if'
              func_lines << indent("    #{keyword} (#{condition}) {", depth)
              first = false
            else
              if first
                # No conditional branches -- just emit directly
                component_code = component_generator.call(attrs, depth + 1, required_imports)
                func_lines << component_code
                func_lines << indent("}", depth)
                return { function_code: func_lines.join("\n") }
              else
                func_lines << indent("    } else {", depth)
              end
            end

            component_code = component_generator.call(attrs, depth + 2, required_imports)
            func_lines << component_code
          end

          func_lines << indent("    }", depth)
          func_lines << indent("}", depth)

          { function_code: func_lines.join("\n") }
        end

        # Build an if/else-if chain string from branches (inline, not as separate function).
        # Returns the Kotlin code for the if/else chain.
        #
        # @param branches [Array<Hash>] From ResponsiveResolver.build_branches
        # @param depth [Integer] Indentation depth
        # @param required_imports [Set] Import set to populate
        # @param block [Proc] Takes (attrs, depth, required_imports) and returns code string
        # @return [String] The if/else chain
        def self.build_if_else_chain(branches, depth, required_imports, &block)
          add_responsive_imports(required_imports)

          lines = []
          lines << indent(ISLANDSCAPE_DECLARATION, depth)

          first = true
          branches.each do |branch|
            condition = build_condition(branch[:size_class])
            attrs = branch[:attrs]

            if condition
              keyword = first ? 'if' : '} else if'
              lines << indent("#{keyword} (#{condition}) {", depth)
              first = false
            else
              if first
                # No conditional branches
                code = block.call(attrs, depth, required_imports)
                lines << code
                return lines.join("\n")
              else
                lines << indent("} else {", depth)
              end
            end

            code = block.call(attrs, depth + 1, required_imports)
            lines << code
          end

          lines << indent("}", depth)
          lines.join("\n")
        end

        # Add required imports for responsive code. `:local_window_info`
        # (LocalWindowInfo + LocalDensity) is the only entry needed now —
        # width branches and the `isLandscape` val both read
        # `LocalWindowInfo.current.containerSize`.
        def self.add_responsive_imports(required_imports)
          return unless required_imports

          required_imports.add(:local_window_info)
        end

        # Helper: indent text
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
