# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      # CircleView: a Box clipped to a circle, its children centred in it —
      # what KotlinJsonUI Dynamic draws (DynamicCircleViewComponent), in the
      # same order of stages:
      #
      #   testTag → margins → size → offset → alpha → shadow(circle) →
      #   clip(circle) → clip(cornerRadius) → border(circle) → background →
      #   clickable → padding
      #
      # Until 1.9.0 the codegen had no case for it: a CircleView fell to the
      # custom-component lookup and emitted `// TODO: Implement component
      # type: CircleView`, while Dynamic drew it (component_metadata.json
      # declared kotlin_generated false and kotlin_dynamic true).
      class CircleviewComponent
        # The diameter when neither width nor height is declared — Dynamic's
        # default for its undeclared legacy `size`.
        DEFAULT_SIZE = 20

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil, is_root: false)
          required_imports&.add(:box)
          required_imports&.add(:alignment)
          required_imports&.add(:shape)
          required_imports&.add(:circle_shape)

          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          # The declared width / height, as on every component; without them,
          # the legacy `size` (Dynamic reads it the same way).
          if json_data['width'] || json_data['height']
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          else
            modifiers << ".size(#{legacy_size(json_data)}.dp)"
          end
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          # testTag after margins and offset, before alpha: the tagged box (resource-id
          # bounds, TalkBack focus) is the drawn box. Ticket
          # kjui-a11y-bounds-of-a-margined-view-include-its-margin.
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports, shape: 'CircleShape'))
          modifiers << '.clip(CircleShape)'
          # cornerRadius applies as declared, inside the circle (Dynamic's
          # ruling of 2026-09-26: no exception for circles).
          modifiers.concat(Helpers::ModifierBuilder.build_corner_clip(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_border(json_data, required_imports, shape: 'CircleShape'))
          # The fill: `color` (an undeclared legacy spelling Dynamic still
          # reads first), else the declared `background`. Painted after the
          # circle clip, so it is the circle Dynamic paints with
          # `.background(color, CircleShape)`.
          fill = json_data['color'] || json_data['background']
          if fill
            required_imports&.add(:background)
            modifiers << ".background(#{Helpers::ResourceResolver.process_color(fill, required_imports)})"
          end
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code = indent('Box(', depth)
          code += Helpers::ModifierBuilder.format(modifiers, depth, is_root: is_root)
          code += ','
          code += "\n" + indent('contentAlignment = Alignment.Center', depth + 1)
          code += "\n" + indent(') {', depth)

          children = json_data['child'] || json_data['children'] || []
          children = [children] unless children.is_a?(Array)

          # The parent draws the children (handle_container_result).
          { code: code, children: children, closing: "\n" + indent('}', depth), json_data: json_data }
        end

        def self.legacy_size(json_data)
          size = json_data['size']
          size.is_a?(Numeric) ? size : DEFAULT_SIZE
        end

        def self.indent(text, level)
          return text if level.zero?

          spaces = '    ' * level
          text.split("\n").map { |line| line.empty? ? line : spaces + line }.join("\n")
        end
      end
    end
  end
end
