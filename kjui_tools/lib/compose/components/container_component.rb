# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative 'constraintlayout_component'

module KjuiTools
  module Compose
    module Components
      class ContainerComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil, is_root: false)
          container_type = json_data['type'] || 'View'
          orientation = json_data['orientation']

          # Check if any child has relative positioning
          children = json_data['child'] || []
          children = [children] unless children.is_a?(Array)

          if has_relative_positioning?(children)
            # Use ConstraintLayout for relative positioning
            return ConstraintLayoutComponent.generate(json_data, depth, required_imports, parent_type, is_root: is_root)
          end
          
          # Determine layout type
          layout = determine_layout(container_type, orientation)
          
          code = indent("#{layout}(", depth)
          
          # Build modifiers (correct order for Compose)
          modifiers = []

          # Add testTag and contentDescription for UI testing
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          # 1. Alignment within parent (Box.align, Row.align, Column.align)
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          # 2. Margins (outer spacing) - must be BEFORE size/background for outer margin behavior
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

          # 3. Weight modifier if in Row or Column
          if parent_type == 'Row' || parent_type == 'Column'
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          end

          # 3. Size (total element size)
          size_modifiers = Helpers::ModifierBuilder.build_size(json_data)
          Helpers::ModifierBuilder.adjust_for_intrinsic_size!(size_modifiers, json_data, children, layout, required_imports, parent_type)
          modifiers.concat(size_modifiers)

          # 4. Alpha/opacity - BEFORE background so alpha applies to background too
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))

          # 5. Background (clip + border + background)
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))

          # 6. Clickable (onClick/onclick)
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))

          # 7. Padding (inner spacing) - applied last
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          # Reorder the alignment-anchor pattern so `.fillMax<Axis>()` sits
          # BEFORE `.wrapContent<Axis>(Alignment.X)` when an `.<axis>In(max =
          # N.dp)` is also present. Without this, a clamped + centered
          # container ends up flush-left on Android while iOS renders it
          # centered. See ModifierBuilder.reorder_alignment_anchor! for the
          # constraint semantics.
          Helpers::ModifierBuilder.reorder_alignment_anchor!(modifiers)

          # `is_root` flows from compose_builder when this container is the
          # *GeneratedView's root composable. ModifierBuilder.format then
          # starts the chain from the caller's `modifier` parameter so
          # external modifiers (gestures, layout) wrap the internal chain.
          # When `is_root && modifiers.empty?`, format still emits a
          # standalone `modifier = modifier` clause — without that, an
          # internally-modifier-less root would silently drop the caller's
          # modifier.
          if modifiers.any? || is_root
            code += Helpers::ModifierBuilder.format(modifiers, depth, is_root: is_root)
          end
          
          # Add gravity settings
          if json_data['gravity']
            code += add_gravity_settings(layout, json_data['gravity'], depth)
          end
          
          # Add direction settings
          # Note: reverseLayout is only supported by LazyColumn/LazyRow, not Column/Row
          # For regular Row/Column, we need to manually reverse the children order
          if json_data['direction'] && (layout == 'Column' || layout == 'Row')
            # Direction handling will be done by reversing children order
            # No reverseLayout parameter for regular Row/Column
          end
          
          # Add spacing for Column/Row
          if json_data['spacing'] && (layout == 'Column' || layout == 'Row')
            required_imports&.add(:arrangement)
            code += ",\n" + indent("verticalArrangement = Arrangement.spacedBy(#{json_data['spacing']}.dp)", depth + 1) if layout == 'Column'
            code += ",\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{json_data['spacing']}.dp)", depth + 1) if layout == 'Row'
          end
          
          # Add distribution for Column/Row
          if json_data['distribution'] && (layout == 'Column' || layout == 'Row')
            required_imports&.add(:arrangement)
            
            arrangement = case json_data['distribution']
            when 'fillEqually'
              'Arrangement.SpaceEvenly'
            when 'fill'
              'Arrangement.SpaceBetween'
            when 'equalSpacing'
              'Arrangement.SpaceAround'
            when 'equalCentering'
              'Arrangement.SpaceEvenly'
            else
              nil
            end
            
            if arrangement
              code += ",\n" + indent("verticalArrangement = #{arrangement}", depth + 1) if layout == 'Column'
              code += ",\n" + indent("horizontalArrangement = #{arrangement}", depth + 1) if layout == 'Row'
            end
          end
          
          code += "\n" + indent(") {", depth)
          
          # Process children
          children = json_data['child'] || []
          children = [children] unless children.is_a?(Array)
          
          # Reverse children order if direction requires it
          if json_data['direction']
            case json_data['direction']
            when 'bottomToTop'
              children = children.reverse if layout == 'Column'
            when 'rightToLeft'
              children = children.reverse if layout == 'Row'
            end
          end
          
          # Return structure for parent to process children
          { code: code, children: children, closing: "\n" + indent("}", depth), layout_type: layout, json_data: json_data }
        end
        
        private
        
        def self.has_relative_positioning?(children)
          relative_attrs = [
            'alignTopOfView', 'alignBottomOfView', 'alignLeftOfView', 'alignRightOfView',
            'alignTopView', 'alignBottomView', 'alignLeftView', 'alignRightView',
            'alignCenterVerticalView', 'alignCenterHorizontalView'
          ]
          
          children.any? do |child|
            next false unless child.is_a?(Hash)
            relative_attrs.any? { |attr| child[attr] }
          end
        end
        
        def self.determine_layout(container_type, orientation)
          # SwiftJsonUI only has 'View' type, not VStack/HStack/ZStack
          # Layout is determined by orientation attribute:
          # - orientation: "vertical" → Column (VStack)
          # - orientation: "horizontal" → Row (HStack)
          # - no orientation → Box (ZStack)
          
          if container_type == 'View'
            if orientation == 'vertical'
              'Column'
            elsif orientation == 'horizontal'
              'Row'
            else
              'Box'
            end
          else
            # For other types (shouldn't happen with proper View type)
            'Box'
          end
        end
        
        def self.add_gravity_settings(layout, gravity, depth)
          code = ""

          # Normalize gravity to array of strings
          gravity_parts = if gravity.is_a?(Array)
                            gravity.map { |g| g.to_s.strip }
                          else
                            gravity.to_s.split('|').map(&:strip)
                          end

          if layout == 'Column'
            gravity_parts.each do |g|
              case g
              when 'top'
                code += ",\n" + indent("verticalArrangement = Arrangement.Top", depth + 1)
              when 'bottom'
                code += ",\n" + indent("verticalArrangement = Arrangement.Bottom", depth + 1)
              when 'centerVertical'
                code += ",\n" + indent("verticalArrangement = Arrangement.Center", depth + 1)
              when 'left'
                code += ",\n" + indent("horizontalAlignment = Alignment.Start", depth + 1)
              when 'right'
                code += ",\n" + indent("horizontalAlignment = Alignment.End", depth + 1)
              when 'centerHorizontal'
                code += ",\n" + indent("horizontalAlignment = Alignment.CenterHorizontally", depth + 1)
              when 'center'
                code += ",\n" + indent("verticalArrangement = Arrangement.Center", depth + 1)
                code += ",\n" + indent("horizontalAlignment = Alignment.CenterHorizontally", depth + 1)
              end
            end
          elsif layout == 'Row'
            gravity_parts.each do |g|
              case g
              when 'left'
                code += ",\n" + indent("horizontalArrangement = Arrangement.Start", depth + 1)
              when 'right'
                code += ",\n" + indent("horizontalArrangement = Arrangement.End", depth + 1)
              when 'centerHorizontal'
                code += ",\n" + indent("horizontalArrangement = Arrangement.Center", depth + 1)
              when 'top'
                code += ",\n" + indent("verticalAlignment = Alignment.Top", depth + 1)
              when 'bottom'
                code += ",\n" + indent("verticalAlignment = Alignment.Bottom", depth + 1)
              when 'centerVertical'
                code += ",\n" + indent("verticalAlignment = Alignment.CenterVertically", depth + 1)
              when 'center'
                code += ",\n" + indent("horizontalArrangement = Arrangement.Center", depth + 1)
                code += ",\n" + indent("verticalAlignment = Alignment.CenterVertically", depth + 1)
              end
            end
          elsif layout == 'Box'
            # For Box with array gravity, resolve to single contentAlignment
            box_alignment = resolve_box_alignment(gravity_parts)
            code += ",\n" + indent("contentAlignment = #{box_alignment}", depth + 1) if box_alignment
            if box_alignment.nil?
              gravity_parts.each do |g|
                case g
                when 'center'
                  code += ",\n" + indent("contentAlignment = Alignment.Center", depth + 1)
                when 'centerHorizontal'
                  code += ",\n" + indent("contentAlignment = Alignment.TopCenter", depth + 1)
                when 'centerVertical'
                  code += ",\n" + indent("contentAlignment = Alignment.CenterStart", depth + 1)
                when 'top'
                  code += ",\n" + indent("contentAlignment = Alignment.TopCenter", depth + 1)
                when 'bottom'
                  code += ",\n" + indent("contentAlignment = Alignment.BottomCenter", depth + 1)
                when 'left'
                  code += ",\n" + indent("contentAlignment = Alignment.CenterStart", depth + 1)
                when 'right'
                  code += ",\n" + indent("contentAlignment = Alignment.CenterEnd", depth + 1)
                end
              end
            end
          end

          code
        end

        # Resolve array gravity to a single Box Alignment for compound gravity
        def self.resolve_box_alignment(parts)
          has_center_v = parts.include?('centerVertical') || parts.include?('center')
          has_center_h = parts.include?('centerHorizontal') || parts.include?('center')
          has_top = parts.include?('top')
          has_bottom = parts.include?('bottom')
          has_left = parts.include?('left')
          has_right = parts.include?('right')

          # Only resolve compound (multi-value) gravity
          return nil if parts.length <= 1

          vertical = if has_center_v then 'Center'
                     elsif has_top then 'Top'
                     elsif has_bottom then 'Bottom'
                     else 'Center'
                     end

          horizontal = if has_center_h then 'Center'
                       elsif has_left then 'Start'
                       elsif has_right then 'End'
                       else 'Start'
                       end

          alignment = case "#{vertical}_#{horizontal}"
                      when 'Top_Start' then 'Alignment.TopStart'
                      when 'Top_Center' then 'Alignment.TopCenter'
                      when 'Top_End' then 'Alignment.TopEnd'
                      when 'Center_Start' then 'Alignment.CenterStart'
                      when 'Center_Center' then 'Alignment.Center'
                      when 'Center_End' then 'Alignment.CenterEnd'
                      when 'Bottom_Start' then 'Alignment.BottomStart'
                      when 'Bottom_Center' then 'Alignment.BottomCenter'
                      when 'Bottom_End' then 'Alignment.BottomEnd'
                      end
          alignment
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