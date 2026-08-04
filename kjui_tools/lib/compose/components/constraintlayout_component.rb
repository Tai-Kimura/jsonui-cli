# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'
require_relative '../helpers/font_spec_helper'

module KjuiTools
  module Compose
    module Components
      class ConstraintLayoutComponent
        # Per-file determinism: compose_builder calls this before each layout
        # so resolved_* local names don't drift with process build history.
        def self.reset_counter!
          @counter = 0
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil, is_root: false)
          required_imports&.add(:constraint_layout)

          # Check if any child has relative positioning attributes
          children = json_data['child'] || []
          children = [children] unless children.is_a?(Array)

          has_constraints = children.any? { |child| has_relative_positioning?(child) }

          if has_constraints
            generate_constraint_layout(json_data, children, depth, required_imports, parent_type, is_root: is_root)
          else
            # Fall back to regular Box/Column/Row
            Components::ContainerComponent.generate(json_data, depth, required_imports, parent_type, is_root: is_root)
          end
        end
        
        private
        
        def self.has_relative_positioning?(component)
          return false unless component.is_a?(Hash)
          
          relative_attrs = [
            'alignTopOfView', 'alignBottomOfView', 'alignLeftOfView', 'alignRightOfView',
            'alignTopView', 'alignBottomView', 'alignLeftView', 'alignRightView',
            'alignCenterVerticalView', 'alignCenterHorizontalView',
            'alignTop', 'alignBottom', 'alignLeft', 'alignRight',
            'centerHorizontal', 'centerVertical', 'centerInParent'
          ]
          
          relative_attrs.any? { |attr| component[attr] }
        end
        
        def self.has_positioning_constraints?(component)
          return false unless component.is_a?(Hash)
          
          # These are constraints that use margins in linkTo()
          # For alignXxxView, margins should be applied as padding modifiers
          # For alignTop/Bottom/Left/Right to parent, margins are applied in linkTo()
          positioning_attrs = [
            'alignTopOfView', 'alignBottomOfView', 'alignLeftOfView', 'alignRightOfView',
            'alignTopView', 'alignBottomView', 'alignLeftView', 'alignRightView',
            'alignCenterVerticalView', 'alignCenterHorizontalView',
            'alignTop', 'alignBottom', 'alignLeft', 'alignRight'
          ]
          
          # centerInParent, centerHorizontal, centerVertical don't use margins in linkTo()
          # so they should still apply margins as padding
          positioning_attrs.any? { |attr| component[attr] }
        end
        
        def self.should_apply_margins_as_padding?(component)
          return false unless component.is_a?(Hash)
          
          # Don't apply margins as padding if they're already handled in linkTo()
          # All positioning constraints now handle margins in linkTo()
          return !has_positioning_constraints?(component)
        end
        
        def self.generate_constraint_layout(json_data, children, depth, required_imports, parent_type = nil, is_root: false)
          code = indent("ConstraintLayout(", depth)

          # Build modifiers
          modifiers = []
          # id → testTag first, same contract as every other container.
          # This path used to drop it, which made every layout whose root
          # takes the ConstraintLayout branch (any child with align*View
          # relative positioning) unfindable by the test driver — the
          # conformance align* fixtures were uncapturable ("'root' not
          # found") until this line.
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, nil, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          if modifiers.any? || is_root
            code += Helpers::ModifierBuilder.format(modifiers, depth, is_root: is_root)
          end
          code += "\n" + indent(") {", depth)

          # One createRef per child — constrainAs below references every
          # child, so every ref must exist (the old code declared refs only
          # for id/positioned children but constrained all of them).
          hash_children = children.select { |c| c.is_a?(Hash) }
          hash_children.each_with_index do |child, index|
            ref_name = child['id'] || "view_#{index}"
            code += "\n" + indent("val #{ref_name} = createRef()", depth + 1)
          end
          code += "\n" if hash_children.any?

          # Children go through the REAL component dispatch
          # (compose_builder.generate_component via handle_container_result)
          # and get `.constrainAs(ref)` injected afterwards — the old local
          # mini-generators emitted bare `Box() { // Content }` placeholders
          # that dropped size/background/nested children (parity family
          # constraintlayout-child-pipeline; same pattern the SafeAreaView
          # constraint path already uses).
          #
          # A child whose margins are consumed by linkTo() (relative
          # positioning) must not ALSO apply them as padding modifiers —
          # strip the margin keys from the dispatched copy, mirroring the
          # old should_apply_margins_as_padding? gate.
          prepared_children = hash_children.map do |child|
            if has_positioning_constraints?(child)
              child.reject { |k, _| MARGIN_KEYS.include?(k) }
            else
              child
            end
          end

          {
            code: code,
            children: prepared_children,
            layout_type: 'ConstraintLayout',
            json_data: json_data,
            closing: "\n" + indent("}", depth),
            # The decorator receives the margin-STRIPPED dispatch copy, but
            # linkTo() must read the margins — resolve the ORIGINAL child by
            # index (order is preserved 1:1 with prepared_children).
            child_decorator: lambda do |_child, child_code, child_depth, index|
              inject_constrain_as(hash_children[index], child_code, child_depth, index)
            end
          }
        end

        # Margin spellings consumed by build_relative_positioning's linkTo()
        # offsets for positioned children.
        MARGIN_KEYS = %w[
          margins topMargin bottomMargin leftMargin rightMargin
          startMargin endMargin marginTop marginBottom marginLeft
          marginRight marginStart marginEnd
        ].freeze

        def self.inject_constrain_as(child_data, component_code, depth, index)
          ref_name = child_data['id'] || "view_#{index}"
          constraints = Helpers::ModifierBuilder.build_relative_positioning(child_data)
          constraint_content = constraints.any? ? constraints.map { |c| indent(c, depth + 2) }.join("\n") : ""
          block = "modifier = Modifier.constrainAs(#{ref_name}) {"
          block += "\n#{constraint_content}" unless constraint_content.empty?
          block += "\n" + indent("}", depth + 1)

          if component_code.include?("modifier = Modifier")
            # Chain constrainAs right after `Modifier`; the child's own
            # modifiers continue on the following lines. Block replacer —
            # the content may contain `$` (Kotlin templates).
            component_code.sub("modifier = Modifier") { block }
          else
            # Rare: a child that emitted no modifier argument at all (real
            # components with an id always emit at least the testTag chain).
            insert_pos = component_code.index("(") + 1
            component_code.dup.insert(insert_pos, "\n" + indent(block, 0) + ",")
          end
        end
        
        def self.quote(text)
          # Escape special characters properly
          escaped = text.gsub('\\', '\\\\\\\\')  # Escape backslashes first
                       .gsub('"', '\\"')           # Escape quotes
                       .gsub("\n", '\\n')           # Escape newlines
                       .gsub("\r", '\\r')           # Escape carriage returns
                       .gsub("\t", '\\t')           # Escape tabs
          "\"#{escaped}\""
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