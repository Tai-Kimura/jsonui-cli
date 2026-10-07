# frozen_string_literal: true

require_relative '../helpers/bound_value'
require_relative '../helpers/modifier_builder'
require_relative 'constraintlayout_component'
require_relative '../../core/enum_spelling'

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

          # `distribution: "fill"` is its own measurement pass. G measured both
          # weight encodings on the device: `weight(1f)` + injected matchParent
          # IS fillEqually (the 0px collapse run 4 caught), and
          # `weight(1f, fill = false)` packs children by measured size, which
          # is pixel-identical to the CONTROL — inert (run 5, d25 ×2). Fill is
          # CSS flex-grow with an auto basis — content plus an equal split of
          # the leftover — and Modifier.weight cannot say that. The policy
          # lives ONCE in the base library (DistributionFillRow/Column,
          # KotlinJsonUI c7d2dfb) precisely so this emitter and the dynamic
          # renderer cannot drift; children render plain inside it (no scope,
          # no weight), and a child declaring its own axis size is excluded
          # from growth via `grows` (explicit > fill).
          fill_distribution = json_data['distribution'] == 'fill' &&
                              (layout == 'Column' || layout == 'Row')
          composable = fill_distribution ? "DistributionFill#{layout}" : layout
          required_imports&.add(:distribution_fill) if fill_distribution

          code = indent("#{composable}(", depth)
          
          # Build modifiers (correct order for Compose)
          modifiers = []

          # Add testTag and contentDescription for UI testing

          # 1. Alignment within parent (Box.align, Row.align, Column.align)
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          # 2. Margins (outer spacing) - must be BEFORE size/background for outer margin behavior
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

          # 3. Weight modifier if in Row or Column
          if parent_type == 'Row' || parent_type == 'Column'
            modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          end

          # 3. Size (total element size)
          size_modifiers = Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports)
          Helpers::ModifierBuilder.adjust_for_intrinsic_size!(size_modifiers, json_data, children, layout, required_imports, parent_type)
          modifiers.concat(size_modifiers)

          # 4. Alpha/opacity - BEFORE background so alpha applies to background too
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          # testTag after margins and offset, before alpha: the tagged box (resource-id
          # bounds, TalkBack focus) is the drawn box. Ticket
          # kjui-a11y-bounds-of-a-margined-view-include-its-margin.
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))

          # 4.5 Shadow — declared `shadow` never reached containers on the
          # codegen path (build_shadow existed but only Text called it),
          # while the dynamic ModifierBuilder applies it here: alpha →
          # shadow → background (parity family kjui-codegen-shadow-missing).
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))

          # 5. Background (clip + border + background)
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))

          # 6. Clickable (onClick/onclick)
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))

          # 7. Padding (inner spacing) - applied last
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))

          # 8. A fixed-size row whose children all declare their size along
          # it lays them out in sequence past its edge (ruling S); innermost.
          unless fill_distribution
            overflow = main_axis_overflow_wrapper(json_data, layout, children)
            if overflow
              required_imports&.add(:bias_alignment)
              modifiers << overflow
            end
          end

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
          
          # Add gravity settings. `alignment` is the string alternative to
          # gravity (SwiftUI Alignment spelling), so it normalises into the same
          # parts and travels the same path — gravity wins when both are set,
          # since it is the primary spelling.
          gravity = json_data['gravity'] || alignment_as_gravity(json_data['alignment'])
          # direction: rightToLeft on a Column needs add_gravity_settings even
          # with no gravity declared — its trailing-edge branch is exactly the
          # gravity-less case (it was unreachable behind `if gravity`).
          if gravity || (json_data['direction'] == 'rightToLeft' && layout == 'Column')
            gravity_code = add_gravity_settings(layout, gravity, depth, json_data)
            # Each clause is emitted with a leading comma, which is only correct
            # when an argument precedes it. A container with gravity but no
            # modifiers has none — that emitted `Column(,`, which does not
            # compile. The condition mirrors the modifier emission above exactly.
            gravity_code = gravity_code.sub(/\A,/, '') unless modifiers.any? || is_root
            code += gravity_code
          end
          
          # Add direction settings
          # Note: reverseLayout is only supported by LazyColumn/LazyRow, not Column/Row
          # For regular Row/Column, we need to manually reverse the children order
          if json_data['direction'] && (layout == 'Column' || layout == 'Row')
            # Direction handling will be done by reversing children order
            # No reverseLayout parameter for regular Row/Column
          end
          
          # Add spacing for Column/Row. On the fill layout `spacing` is the
          # `gap` parameter — it pins the gap and growth happens in the space
          # the gaps leave (spacingWins); there is no Arrangement to name.
          if json_data['spacing'] && fill_distribution
            code += ",\n" + indent("gap = #{Helpers::BoundValue.dp(json_data['spacing'])}", depth + 1)
          elsif json_data['spacing'] && (layout == 'Column' || layout == 'Row')
            required_imports&.add(:arrangement)
            # `spacing` is `["number", "binding"]` — the raw interpolation put
            # `@{v}.dp` in code position (plan 49 lane C: View.spacing).
            spacing_dp = Helpers::BoundValue.dp(json_data['spacing'])
            if layout == 'Column'
              spaced = bottom_up?(json_data, layout) ? "Arrangement.spacedBy(#{spacing_dp}, Alignment.Bottom)" : "Arrangement.spacedBy(#{spacing_dp})"
              code += ",\n" + indent("verticalArrangement = #{spaced}", depth + 1)
            end
            if layout == 'Row'
              spaced = end_first?(json_data, layout) ? "Arrangement.spacedBy(#{spacing_dp}, Alignment.End)" : "Arrangement.spacedBy(#{spacing_dp})"
              code += ",\n" + indent("horizontalArrangement = #{spaced}", depth + 1)
            end
          end

          # bottomToTop stacks from the bottom edge (user ruling 2026-10-05);
          # with spacing the spacedBy above carries the alignment.
          if bottom_up?(json_data, layout) && !json_data['spacing']
            required_imports&.add(:arrangement)
            code += ",\n" + indent("verticalArrangement = Arrangement.Bottom", depth + 1)
          end
          # rightToLeft stacks a Row from its right edge (the same ruling).
          if end_first?(json_data, layout) && !json_data['spacing']
            required_imports&.add(:arrangement)
            code += ",\n" + indent("horizontalArrangement = Arrangement.End", depth + 1)
          end

          # A child that declares a NUMERIC size on the grow axis keeps it and
          # is excluded from growth (explicit > fill). `wrapContent` is a child
          # fill grows: width is required, so reading it as explicit left fill
          # no child to grow in a correct layout (user ruling 2026-10-07,
          # attribute_semantics distribution.explicitChildSizeWins). This read
          # the key's presence, as the dynamic caller did; both read only a
          # numeric size now (KotlinJsonUI DynamicContainerComponent.fillGrows).
          # All-grow is the layout's default, so the argument is only emitted
          # when some child opts out.
          if fill_distribution
            axis_key = layout == 'Column' ? 'height' : 'width'
            grows = children.map { |c| !(c.is_a?(Hash) && declares_size_along?(c, axis_key)) }
            unless grows.all?
              code += ",\n" + indent("grows = listOf(#{grows.join(', ')})", depth + 1)
            end
          end
          
          # `distribution` has two halves and they are not the same half.
          #
          # `equalSpacing` / `equalCentering` distribute the SPACE BETWEEN
          # children — an Arrangement, and the corrected pair is the dynamic
          # component's (canonical here): equalSpacing is equal gaps BETWEEN
          # adjacent children with no outer gap (SpaceBetween), and
          # equalCentering is equal centre-to-centre distance, i.e. each child
          # centred in an equal track (SpaceAround) — SpaceEvenly leaves the
          # outer children off-centre in their tracks, so it is neither.
          #
          # The SIZE half is handled above (`fill` → DistributionFillRow/
          # Column) and below (`fillEqually` → child weights); neither is an
          # Arrangement at all, which is what all four used to be emitted as.
          #
          # An explicit `spacing` pins the gap and wins the axis it speaks
          # about; emitting both also produced the same named argument twice,
          # which does not compile (plan 49 lane C, 4th round parity).
          if json_data['distribution'] && (layout == 'Column' || layout == 'Row')
            arrangement = case json_data['distribution']
                          when 'equalSpacing' then 'Arrangement.SpaceBetween'
                          when 'equalCentering' then 'Arrangement.SpaceAround'
                          end

            if arrangement && !json_data['spacing']
              required_imports&.add(:arrangement)
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
          
          # The size half of `distribution`. `fillEqually` is equal shares
          # regardless of content — which is exactly what a child weight of 1
          # plus an injected matchParent means, so it stays a weight per child
          # (G's device measurement: that encoding IS fillEqually). `fill`
          # cannot be said with weights at all and became the DistributionFill
          # composable above; its children render plain, so they must NOT be
          # distributed to here.
          distribute_main_axis!(children, json_data['distribution'], layout) unless fill_distribution
          grow_fill_children!(children, layout) if fill_distribution
          inject_overflow_bias!(children, layout, gravity, json_data) unless fill_distribution

          # Return structure for parent to process children. `layout_type` is
          # what the children see as parent_type: inside DistributionFillRow/
          # Column there is NO Row/Column scope, so the fill name (matching no
          # scope-bound emitter) keeps `.weight(` / `.align(` out of the
          # children — the dynamic side renders them plain the same way.
          { code: code, children: children, closing: "\n" + indent("}", depth), layout_type: composable, json_data: json_data }
        end
        
        private
        
        # Where the container places a child that declares a numeric size, per
        # axis ([h, v], bias −1 start / top, 0 centre, 1 end / bottom), injected
        # for the size stage (ModifierBuilder.overflow_wrapper). An
        # over-constrained declared size was coerced and centred whatever the
        # container said (ticket kjui-oversized-child-is-centred-and-cut-to-its-
        # parent). Each axis is read off what this file and build_alignment
        # actually emit for the child — its own `.align(…)`, else the
        # container's contentAlignment / cross-axis alignment / main-axis
        # gravity — so the wrapper anchors the box exactly where Compose places
        # the child. KotlinJsonUI Dynamic computes the same biases
        # (DynamicContainerComponent.boxBias / columnBias / rowBias / axisBias).
        # A bound (`@{…}`) child placement is decided at run time and is not
        # read here; the container's own placement stands in for it.
        def self.inject_overflow_bias!(children, layout, gravity, json_data)
          return unless %w[Box Column Row].include?(layout)

          parts = gravity_parts_of(gravity)
          parent_h = axis_bias_of(parts, %w[left], %w[right], %w[centerHorizontal center])
          parent_v = axis_bias_of(parts, %w[top], %w[bottom], %w[centerVertical center])
          parent_v = 1.0 if layout == 'Column' && bottom_up?(json_data, layout)
          parent_h = 1.0 if layout == 'Row' && end_first?(json_data, layout)
          # A gravity-less rightToLeft Column anchors its children at the
          # trailing edge (add_gravity_settings).
          parent_h = 1.0 if layout == 'Column' && json_data['direction'] == 'rightToLeft' && parts.empty?
          if layout == 'Box' && (box = resolve_box_alignment(parts))
            parent_h, parent_v = ALIGNMENT_BIAS.fetch(box.sub('Alignment.', ''))
          end

          children.each do |child|
            next unless child.is_a?(Hash) && declares_numeric_size?(child)

            own = Helpers::ModifierBuilder.build_alignment(child, nil, layout).first
            own_bias = own && !own.include?('when') ? alignment_bias_of(own) : nil
            h, v = parent_h, parent_v
            case layout
            when 'Box' then h, v = own_bias if own_bias
            when 'Column' then h = own_bias[0] if own_bias
            when 'Row' then v = own_bias[1] if own_bias
            end
            child[Helpers::ModifierBuilder::OVERFLOW_BIAS_KEY] = [h, v]
          end
        end

        # A fixed-size Row / Column whose children all declare a numeric size
        # along its axis measures them unbounded along it, innermost in its
        # chain, anchored by its gravity. Compose measures a Row's children
        # against the space left, so the child that crosses the edge was
        # coerced to what was left and every child after it moved up — six
        # 40-wide boxes in a 200 row with padding 8 put box_f at 172 where web
        # and iOS put it at 208 (user ruling S, 2026-10-05: children of a
        # fixed-size row are placed in sequence and overflow past the edge).
        # Content that fits reads the same as before: the wrapper reports the
        # declared size and places the content where the gravity would. Not
        # with a distribution (it needs the free space) nor with any child
        # sized by weight, fill or content, all of which need the bound.
        # KotlinJsonUI Dynamic does the same
        # (DynamicContainerComponent.mainAxisOverflowWrapper).
        def self.main_axis_overflow_wrapper(json_data, layout, children)
          return nil unless %w[Row Column].include?(layout)
          return nil if json_data['distribution'] || children.empty?

          axis = layout == 'Row' ? 'width' : 'height'
          numeric = ->(v) { v.is_a?(Numeric) ? v >= 0 : (v.is_a?(String) && v.match?(/\A\d+(\.\d+)?\z/)) }
          return nil unless numeric.call(json_data[axis])
          return nil unless children.all? do |c|
            c.is_a?(Hash) && numeric.call(c[axis]) && !(c['weight'] || c['widthWeight'] || c['heightWeight'])
          end

          parts = gravity_parts_of(json_data['gravity'] || alignment_as_gravity(json_data['alignment']))
          if layout == 'Row'
            h = end_first?(json_data, layout) ? 1.0 : axis_bias_of(parts, %w[left], %w[right], %w[centerHorizontal center])
            ".wrapContentWidth(align = BiasAlignment.Horizontal(#{h}f), unbounded = true)"
          else
            v = bottom_up?(json_data, layout) ? 1.0 : axis_bias_of(parts, %w[top], %w[bottom], %w[centerVertical center])
            ".wrapContentHeight(align = BiasAlignment.Vertical(#{v}f), unbounded = true)"
          end
        end

        # Compose's named alignments as [horizontal, vertical] bias. A
        # one-axis name leaves the other axis nil.
        ALIGNMENT_BIAS = {
          'TopStart' => [-1.0, -1.0], 'TopCenter' => [0.0, -1.0], 'TopEnd' => [1.0, -1.0],
          'CenterStart' => [-1.0, 0.0], 'Center' => [0.0, 0.0], 'CenterEnd' => [1.0, 0.0],
          'BottomStart' => [-1.0, 1.0], 'BottomCenter' => [0.0, 1.0], 'BottomEnd' => [1.0, 1.0],
          'Start' => [-1.0, nil], 'CenterHorizontally' => [0.0, nil], 'End' => [1.0, nil],
          'Top' => [nil, -1.0], 'CenterVertically' => [nil, 0.0], 'Bottom' => [nil, 1.0]
        }.freeze

        # The bias of an emitted `.align(…)`.
        def self.alignment_bias_of(emitted)
          if (m = emitted.match(/BiasAlignment\((-?[\d.]+)f,\s*(-?[\d.]+)f\)/))
            [m[1].to_f, m[2].to_f]
          elsif (m = emitted.match(/Alignment\.(\w+)/))
            ALIGNMENT_BIAS[m[1]]
          end
        end

        # −1 start, 1 end, 0 centre, start when the gravity names none
        # (gravityDefaults). Start, end, centre: Dynamic's axisBias order.
        def self.axis_bias_of(parts, starts, ends, centers)
          return -1.0 if parts.any? { |g| starts.include?(g) }
          return 1.0 if parts.any? { |g| ends.include?(g) }
          return 0.0 if parts.any? { |g| centers.include?(g) }

          -1.0
        end

        def self.gravity_parts_of(gravity)
          return [] if gravity.nil?

          gravity.is_a?(Array) ? gravity.map { |g| g.to_s.strip } : gravity.to_s.split('|').map(&:strip)
        end

        # `direction: bottomToTop` stacks a Column from its bottom edge, the
        # first child at the bottom (user ruling, 2026-10-05); reversing the
        # children alone stacked them from the top. Not when the gravity names
        # a vertical place or a distribution spreads them. KotlinJsonUI
        # Dynamic: DynamicContainerComponent.stacksFromTheBottom.
        def self.bottom_up?(json_data, layout)
          return false unless layout == 'Column' && json_data['direction'] == 'bottomToTop'
          return false if json_data['distribution']

          parts = gravity_parts_of(json_data['gravity'] || alignment_as_gravity(json_data['alignment']))
          (parts & %w[top bottom centerVertical center]).empty?
        end

        # `direction: rightToLeft` stacks a Row from its right edge, the first
        # child rightmost (user ruling, 2026-10-05, bottomToTop's rule turned
        # sideways). Not when the gravity names a horizontal place or a
        # distribution spreads them. KotlinJsonUI Dynamic:
        # DynamicContainerComponent.stacksFromTheEnd.
        def self.end_first?(json_data, layout)
          return false unless layout == 'Row' && json_data['direction'] == 'rightToLeft'
          return false if json_data['distribution']

          parts = gravity_parts_of(json_data['gravity'] || alignment_as_gravity(json_data['alignment']))
          (parts & %w[left right centerHorizontal center]).empty?
        end

        # A numeric size declared along `axis` ('width' / 'height').
        def self.declares_size_along?(child, axis)
          v = child[axis]
          v.is_a?(Numeric) ? v >= 0 : (v.is_a?(String) && v.match?(/\A\d+(\.\d+)?\z/))
        end

        # A numeric width or height (or a frame): the only nodes the size stage
        # wraps. Same predicate as KotlinJsonUI Dynamic's declaresNumericSize.
        def self.declares_numeric_size?(child)
          return true if child['frame'].is_a?(Hash)

          %w[width height].any? do |key|
            v = child[key]
            v.is_a?(Numeric) || (v.is_a?(String) && v.match?(/\A\d+(\.\d+)?\z/))
          end
        end

        # Give each child of a `fillEqually` container its equal share of the
        # main axis. Mutates the child hashes, the way the dynamic component
        # injects into the child JSON — `build_weight` is what emits, so the
        # weight lands in the CHILD's own modifier chain, which is where
        # Compose needs it (`weight` is scope-bound). `fill` does not come
        # here: it is the DistributionFill composable, not a weight.
        def self.distribute_main_axis!(children, distribution, layout)
          return unless distribution == 'fillEqually'
          return unless layout == 'Column' || layout == 'Row'

          axis_weight = layout == 'Column' ? 'heightWeight' : 'weight'
          axis_size = layout == 'Column' ? 'height' : 'width'
          children.each do |child|
            next unless child.is_a?(Hash)
            # A child that declares its own weight keeps it and is not being
            # distributed to.
            next if child['weight'] || child['heightWeight'] || child['widthWeight']
            # A child that declares its own size along the axis keeps it and
            # takes no share; the others split what is left equally (user
            # ruling, 2026-10-05: 60 / 120 / 120, not 60 drawn in an equal 100
            # slot with 40 empty). KotlinJsonUI Dynamic:
            # DynamicContainerComponent.declaresSizeAlong.
            next if declares_size_along?(child, axis_size)

            child[axis_weight] = 1
            # Distribution-injected, not author-declared: an AUTHOR weight
            # owns its axis (the slot wins over a declared size — canonical
            # weight ruling, common_weight__static), but a weight the
            # CONTAINER injected must not override the child's declared size
            # (childSizePrecedence). build_size reads this marker to keep the
            # declared size start-aligned inside the slot, exactly what the
            # dynamic component renders (its Box wrapper takes the weight,
            # the child draws its own size at topStart).
            child['__distributionWeight'] = true
            # The share is a slot; the child has to occupy it or the picture is
            # the child's intrinsic size sitting in an empty slot. The dynamic
            # component does exactly this (`injectFillSize`), and only when the
            # child does not size that axis itself.
            # A declared wrapContent too: it is not an explicit size here
            # (numeric sizes returned above), and kept it drew the content
            # inside an equal share (user ruling 2026-10-07; KotlinJsonUI
            # DynamicContainerComponent.overridesTheChildsSize).
            child[axis_size] = 'matchParent'
          end
        end

        # A growing child of a `distribution: fill` row (column) draws across
        # the slot DistributionFillRow gives it: its own `wrapContent` would be
        # a wrapContentWidth inside that exact width, drawing the content at
        # its own size at the start of a wider slot. The slot is sized from the
        # child's max intrinsic, which a fill modifier leaves alone, so the
        # split is unchanged. KotlinJsonUI Dynamic: DynamicContainerComponent.fillChild.
        def self.grow_fill_children!(children, layout)
          axis_size = layout == 'Column' ? 'height' : 'width'
          children.each do |child|
            next unless child.is_a?(Hash)
            next if declares_size_along?(child, axis_size)

            child[axis_size] = 'matchParent'
          end
        end

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
        
        #: `alignment` -> the gravity parts that mean the same thing. The
        #: SwiftUI reading is authoritative: `top` is top-and-horizontally-
        #: centred, `leading` is leading-and-vertically-centred, and so on
        #: (StackAlignmentHelper#get_zstack_alignment maps the same nine values).
        ALIGNMENT_GRAVITY = {
          'topleading' => %w[top left],
          'top' => %w[top centerHorizontal],
          'toptrailing' => %w[top right],
          'leading' => %w[centerVertical left],
          'center' => %w[center],
          'trailing' => %w[centerVertical right],
          'bottomleading' => %w[bottom left],
          'bottom' => %w[bottom centerHorizontal],
          'bottomtrailing' => %w[bottom right]
        }.freeze

        def self.alignment_as_gravity(alignment)
          return nil unless alignment.is_a?(String)

          ALIGNMENT_GRAVITY[JsonUIShared::EnumSpelling.lowered(alignment, 'common', 'alignment')]
        end

        def self.add_gravity_settings(layout, gravity, depth, json_data = {})
          code = ""

          # Normalize gravity to array of strings
          gravity_parts = if gravity.is_a?(Array)
                            gravity.map { |g| g.to_s.strip }
                          else
                            gravity.to_s.split('|').map(&:strip)
                          end

          if layout == 'Column'
            # RTL on a column mirrors the inline axis — children anchor to
            # the trailing edge (matches ios and the dynamic
            # LocalLayoutDirection path; 33 cross-effect).
            if json_data['direction'] == 'rightToLeft' && gravity_parts.empty?
              code += ",\n" + indent("horizontalAlignment = Alignment.End", depth + 1)
            end
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
            # One contentAlignment from both axes, single value or array.
            box_alignment = resolve_box_alignment(gravity_parts)
            code += ",\n" + indent("contentAlignment = #{box_alignment}", depth + 1) if box_alignment
          end

          code
        end

        # The Box's contentAlignment for a gravity, or nil when it names
        # neither axis (the Box default then applies).
        #
        # Each axis resolves on its own, and an axis the gravity does not name
        # takes the container default (attribute_semantics.json ->
        # gravityDefaults). Until 2026-09-24 a single value centred the axis it
        # did not name — `top` gave TopCenter, `left` CenterStart — and an
        # array without a vertical value centred vertically, while ios drew
        # the same declaration at the leading/top corner.
        def self.resolve_box_alignment(parts)
          has_center_v = parts.include?('centerVertical') || parts.include?('center')
          has_center_h = parts.include?('centerHorizontal') || parts.include?('center')
          has_top = parts.include?('top')
          has_bottom = parts.include?('bottom')
          has_left = parts.include?('left')
          has_right = parts.include?('right')

          names_vertical = has_center_v || has_top || has_bottom
          names_horizontal = has_center_h || has_left || has_right
          return nil unless names_vertical || names_horizontal

          vertical = if has_center_v then 'Center'
                     elsif has_top then 'Top'
                     elsif has_bottom then 'Bottom'
                     else 'Top'
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