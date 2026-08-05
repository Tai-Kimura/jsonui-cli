# frozen_string_literal: true

require_relative 'binding_expression'
require_relative 'bound_value'
require_relative 'resource_resolver'
require_relative '../../core/normalization'

module KjuiTools
  module Compose
    module Helpers
      # Helper class to build Compose modifiers from JSON attributes
      class ModifierBuilder
        # Every `.dp` below comes out of BoundValue so a `@{...}` padding emits
        # a real Dp expression instead of interpolating the binding text into
        # code position (`.padding(top = @{v}.dp)` — plan 49 lane C, 29
        # `bound-uncompilable`). Numeric declarations are untouched: BoundValue
        # only leaves the literal path when the value actually carries a
        # binding.
        def self.build_padding(json_data)
          modifiers = []

          # Handle padding attribute (can be array [top, right, bottom, left] or single value)
          modifiers.concat(padding_group(json_data['padding'])) if json_data['padding']

          # Handle paddings attribute (same as padding)
          modifiers.concat(padding_group(json_data['paddings'])) if json_data['paddings']

          # Individual padding attributes (prefix form: paddingTop, and suffix form: topPadding/leftPadding)
          modifiers << ".padding(top = #{BoundValue.dp(json_data['paddingTop'] || json_data['topPadding'])})" if json_data['paddingTop'] || json_data['topPadding']
          modifiers << ".padding(bottom = #{BoundValue.dp(json_data['paddingBottom'] || json_data['bottomPadding'])})" if json_data['paddingBottom'] || json_data['bottomPadding']
          modifiers << ".padding(start = #{BoundValue.dp(json_data['paddingLeft'] || json_data['leftPadding'])})" if json_data['paddingLeft'] || json_data['leftPadding']
          modifiers << ".padding(end = #{BoundValue.dp(json_data['paddingRight'] || json_data['rightPadding'])})" if json_data['paddingRight'] || json_data['rightPadding']
          # RTL-aware padding (canonical paddingStart/paddingEnd; suffix
          # spellings accepted like the dynamic reader)
          modifiers << ".padding(start = #{BoundValue.dp(json_data['paddingStart'] || json_data['startPadding'])})" if json_data['paddingStart'] || json_data['startPadding']
          modifiers << ".padding(end = #{BoundValue.dp(json_data['paddingEnd'] || json_data['endPadding'])})" if json_data['paddingEnd'] || json_data['endPadding']

          modifiers
        end

        # The shared array/scalar shape behind `padding` and `paddings`.
        def self.padding_group(value)
          unless value.is_a?(Array)
            return [".padding(#{BoundValue.dp(value)})"]
          end

          case value.length
          when 4
            [".padding(top = #{BoundValue.dp(value[0])}, end = #{BoundValue.dp(value[1])}, " \
             "bottom = #{BoundValue.dp(value[2])}, start = #{BoundValue.dp(value[3])})"]
          when 2
            [".padding(vertical = #{BoundValue.dp(value[0])}, horizontal = #{BoundValue.dp(value[1])})"]
          when 1
            [".padding(#{BoundValue.dp(value[0])})"]
          else
            []
          end
        end

        def self.build_margins(json_data)
          modifiers = []

          # Handle margins attribute (can be array [top, right, bottom, left] or single value)
          if json_data['margins']
            margin_values = json_data['margins']
            if margin_values.is_a?(Array)
              if margin_values.length == 4
                modifiers << ".padding(top = #{BoundValue.dp(margin_values[0])}, end = #{BoundValue.dp(margin_values[1])}, " \
                             "bottom = #{BoundValue.dp(margin_values[2])}, start = #{BoundValue.dp(margin_values[3])})"
              elsif margin_values.length == 1
                modifiers << ".padding(#{BoundValue.dp(margin_values[0])})"
              end
            else
              modifiers << ".padding(#{BoundValue.dp(margin_values)})"
            end
          end

          # Individual margin attributes (with binding support)
          modifiers << ".padding(top = #{margin_value(json_data['topMargin'])})" if json_data['topMargin']
          modifiers << ".padding(bottom = #{margin_value(json_data['bottomMargin'])})" if json_data['bottomMargin']
          modifiers << ".padding(start = #{margin_value(json_data['leftMargin'])})" if json_data['leftMargin']
          modifiers << ".padding(end = #{margin_value(json_data['rightMargin'])})" if json_data['rightMargin']
          # RTL aware margins
          modifiers << ".padding(start = #{margin_value(json_data['startMargin'])})" if json_data['startMargin']
          modifiers << ".padding(end = #{margin_value(json_data['endMargin'])})" if json_data['endMargin']

          modifiers
        end

        # Convert margin value to Kotlin/Compose format with binding support.
        # The old hand-rolled form (`data.#{property}.dp`) passed `??` through
        # verbatim and ignored nullability, so `@{gap ?? 8}` emitted
        # `data.gap ?? 8.dp`. BoundValue is the canonical emitter now.
        def self.margin_value(value)
          BoundValue.dp(value)
        end

        def self.build_weight(json_data, parent_orientation = nil)
          modifiers = []

          # Weight only works in Row/Column contexts
          # Weight must be greater than 0 in Compose
          weight = json_data['weight']
          return modifiers unless weight && parent_orientation

          if BoundValue.bound?(weight)
            # `"@{w}".to_f == 0.0`, so the static guard below dropped every
            # bound weight. Lift the SAME guard to runtime instead: Compose
            # throws on `weight <= 0`, so the zero case must stay unweighted.
            expr = BoundValue.float(weight, fallback: 0)
            modifiers << ".then(if (#{expr} > 0f) Modifier.weight(#{expr}) else Modifier)"
          elsif weight.to_f > 0
            modifiers << ".weight(#{weight}f)"
          end

          modifiers
        end
        
        # Compose's `Row` / `Column` measure their cross axis with `wrapContent`
        # by default, which means a child using `fillMaxHeight()` (Row) or
        # `fillMaxWidth()` (Column) collapses to 0. iOS / HTML / Android Views
        # treat "matchParent inside wrapContent siblings" as "match the tallest
        # sibling", so generated code must ask Compose for the same behavior
        # via `Modifier.height(IntrinsicSize.Min)` (or `width(...)` for Column).
        # This mutates `size_modifiers` in place, replacing the wrap modifier
        # with the intrinsic one when needed.
        #
        # Skip the intrinsic switch when either:
        #   (a) the node is a weighted child of a Row/Column — the weight slot
        #       provides a bounded constraint on the relevant axis, so the
        #       matchParent child resolves through `.fillMaxWidth/Height()` on
        #       its own. The intrinsic wrap is unnecessary AND, when a
        #       SubcomposeLayout descendant exists, would crash anyway.
        #   (b) any descendant emits a SubcomposeLayout (LazyColumn/LazyRow/
        #       LazyVerticalGrid/LazyHorizontalGrid/HorizontalPager etc.).
        #       `Modifier.width/height(IntrinsicSize.Min)` asks descendants for
        #       `minIntrinsicWidth/Height`, and SubcomposeLayout throws on that
        #       query. Falling back to `fillMax<axis>()` keeps the layout
        #       intent (parent fills the parent's slot) without triggering the
        #       intrinsic measurement cascade.
        # Regression: kjui-intrinsicsize-min-cascades-to-lazy-descendant.
        def self.adjust_for_intrinsic_size!(size_modifiers, json_data, children, layout, required_imports = nil, parent_type = nil)
          return size_modifiers unless layout == 'Row' || layout == 'Column'
          return size_modifiers unless children.is_a?(Array) && children.any?

          frame = json_data['frame'].is_a?(Hash) ? json_data['frame'] : nil

          if layout == 'Row'
            parent_h = json_data['height'] || (frame ? frame['height'] : nil)
            return size_modifiers if parent_h && parent_h != 'wrapContent'
            return size_modifiers unless children.any? { |c| child_dimension(c, 'height') == 'matchParent' }

            if weighted_on_axis?(json_data, parent_type, :height) || subcompose_descendant?(children)
              replace_or_append!(size_modifiers, '.wrapContentHeight()', '.fillMaxHeight()')
              return size_modifiers
            end

            required_imports&.add(:intrinsic_size)
            replace_or_append!(size_modifiers, '.wrapContentHeight()', '.height(IntrinsicSize.Min)')
          else
            parent_w = json_data['width'] || (frame ? frame['width'] : nil)
            return size_modifiers if parent_w && parent_w != 'wrapContent'
            return size_modifiers unless children.any? { |c| child_dimension(c, 'width') == 'matchParent' }

            if weighted_on_axis?(json_data, parent_type, :width) || subcompose_descendant?(children)
              replace_or_append!(size_modifiers, '.wrapContentWidth()', '.fillMaxWidth()')
              return size_modifiers
            end

            required_imports&.add(:intrinsic_size)
            replace_or_append!(size_modifiers, '.wrapContentWidth()', '.width(IntrinsicSize.Min)')
          end

          size_modifiers
        end

        # `weight: N` set with a parent that distributes on the matching axis
        # (Row → width, Column → height) means the parent already pins this
        # node's axis to its allocated slot — no intrinsic measurement needed.
        def self.weighted_on_axis?(json_data, parent_type, axis)
          return false unless json_data['weight'] && json_data['weight'].to_f > 0
          (axis == :width && parent_type == 'Row') ||
            (axis == :height && parent_type == 'Column')
        end

        # Recursively scan for components that emit SubcomposeLayout-based
        # Compose primitives. Those reject `IntrinsicSize.Min` ancestor
        # queries with `Asking for intrinsic measurements of SubcomposeLayout
        # layouts is not supported`.
        def self.subcompose_descendant?(nodes)
          return false unless nodes.is_a?(Array)
          nodes.any? { |n| subcompose_node?(n) }
        end

        def self.subcompose_node?(node)
          return false unless node.is_a?(Hash)

          case node['type']
          when 'Scroll', 'Table'
            # ScrollView always emits LazyRow/LazyColumn; Table emits
            # LazyColumn unconditionally.
            return true
          when 'Collection'
            # Collection emits a non-Lazy fallback when `lazy: "none"` or when
            # vertical + `height: wrapContent`. Flow layout uses FlowRow
            # (non-Lazy). Paging horizontal uses HorizontalPager which IS
            # SubcomposeLayout-based. Everything else is Lazy.
            layout = node['layout'] || node['orientation'] || 'vertical'
            return false if layout == 'flow'
            return false if node['lazy'] == 'none'
            return false if layout != 'horizontal' && node['height'] == 'wrapContent'
            return true
          end

          subcompose_descendant?(node['child'])
        end

        def self.child_dimension(child, axis)
          return nil unless child.is_a?(Hash)
          return child[axis] if child[axis]
          frame = child['frame']
          frame.is_a?(Hash) ? frame[axis] : nil
        end

        def self.replace_or_append!(modifiers, old_modifier, new_modifier)
          if (idx = modifiers.index(old_modifier))
            modifiers[idx] = new_modifier
          else
            modifiers << new_modifier unless modifiers.include?(new_modifier)
          end
        end

        # When `wrapContent<Axis>(Alignment.X)` coexists with `.fillMax<Axis>()`
        # and an `.<axis>In(max = N.dp)` bound (the
        # `width: matchParent` + `maxWidth: N` + `centerHorizontal/alignLeft/
        # alignRight: true` combo in spec), the Compose chain must be
        # ordered:
        #
        #   .fillMax<Axis>()              # claim full parent <axis> for the frame
        #   .wrapContent<Axis>(Alignment) # align the (clamped) child within full frame
        #   .<axis>In(max = N.dp)         # clamp the child to N
        #
        # The natural build_alignment-first / build_size-second emit produces
        # `wrapContent<Axis>(...) → <axis>In → fillMax<Axis>()` instead. With
        # that order, `wrapContent<Axis>` runs against the child's own
        # (clamped) bounds — there is no surrounding full-parent frame for
        # the alignment to offset against — so a maxWidth-clamped child
        # sits at the left edge of the parent instead of centered. Mirrors
        # the SwiftUI side which uses `.frame(maxWidth: N, alignment:
        # .center)` as a single API and is unaffected.
        #
        # Regression: kjui-responsive-centerhorizontal-modifier-order-not-centered.
        def self.reorder_alignment_anchor!(modifiers)
          reorder_axis!(modifiers, 'Width', 'width')
          reorder_axis!(modifiers, 'Height', 'height')
          modifiers
        end

        def self.reorder_axis!(modifiers, pascal_axis, lower_axis)
          fill = ".fillMax#{pascal_axis}()"
          fill_idx = modifiers.index(fill)
          return unless fill_idx

          wrap_prefix = ".wrapContent#{pascal_axis}(Alignment."
          wrap_idx = modifiers.index { |m| m.is_a?(String) && m.start_with?(wrap_prefix) }
          return unless wrap_idx

          # Only reorder when the bound is also present — that's the trigger
          # for the misalignment. If `.<axis>In(...)` isn't there, the
          # current order is fine.
          in_prefix = ".#{lower_axis}In("
          has_in = modifiers.any? { |m| m.is_a?(String) && m.start_with?(in_prefix) }
          return unless has_in

          # Already in correct order (fill < wrap).
          return if fill_idx < wrap_idx

          modifiers.delete_at(fill_idx)
          wrap_idx = modifiers.index { |m| m.is_a?(String) && m.start_with?(wrap_prefix) }
          modifiers.insert(wrap_idx, fill)
        end

        def self.build_size(json_data, parent_type = nil, required_imports = nil)
          modifiers = []

          # Handle 'frame' attribute - object with width/height
          # frame: { width: 100, height: 50 }
          if json_data['frame'].is_a?(Hash)
            frame = json_data['frame']
            if frame['width']
              if frame['width'] == 'matchParent'
                modifiers << ".fillMaxWidth()"
              elsif frame['width'] == 'wrapContent'
                modifiers << ".wrapContentWidth()"
              else
                modifiers << ".width(#{process_dimension(frame['width'])})"
              end
            end
            if frame['height']
              if frame['height'] == 'matchParent'
                modifiers << ".fillMaxHeight()"
              elsif frame['height'] == 'wrapContent'
                modifiers << ".wrapContentHeight()"
              else
                modifiers << ".height(#{process_dimension(frame['height'])})"
              end
            end
            # If frame is specified, skip individual width/height processing
            return modifiers
          end

          # Min/Max constraints must be emitted BEFORE the fill/wrap
          # structural modifiers. Compose modifier semantics chain
          # constraints outside-in: an outer `.fillMaxWidth()` locks
          # min == max == parent's maxWidth, and a later `.widthIn(max =
          # N.dp)` can no longer narrow it because minWidth is already
          # pinned to parent's maxWidth. Putting widthIn first caps the
          # maxWidth bound, then fillMaxWidth fills WITHIN that cap.
          # Regression: kjui-responsive-widthin-after-fillmaxwidth-no-op.
          #
          # An EXPLICIT numeric width is the opposite case: the declared
          # width wins over min/max bounds (all render paths agree — the
          # dynamic chain is `.width(N).widthIn(...)`, where the fixed
          # width pins the constraints and the bound is inert). Emitting
          # widthIn first would clamp the declared width instead.
          width_constraint =
            if json_data['minWidth'] && json_data['maxWidth']
              ".widthIn(min = #{BoundValue.dp(json_data['minWidth'])}, max = #{BoundValue.dp(json_data['maxWidth'], null_expr: 'Dp.Infinity')})"
            elsif json_data['minWidth']
              ".widthIn(min = #{BoundValue.dp(json_data['minWidth'])})"
            elsif json_data['maxWidth']
              ".widthIn(max = #{BoundValue.dp(json_data['maxWidth'], null_expr: 'Dp.Infinity')})"
            end
          explicit_width = json_data['width'] &&
                           json_data['width'] != 'matchParent' &&
                           json_data['width'] != 'wrapContent' &&
                           !(json_data['weight'] && json_data['width'] == 0)
          modifiers << width_constraint if width_constraint && !explicit_width

          # Width - skip if weight is present and width is 0
          if json_data['width'] == 'matchParent'
            modifiers << ".fillMaxWidth()"
          elsif json_data['width'] == 'wrapContent'
            modifiers << ".wrapContentWidth()"
          elsif explicit_width
            modifiers << ".width(#{process_dimension(json_data['width'])})"
            modifiers << width_constraint if width_constraint
          end

          # Same outside-in argument applies to height: heightIn must be
          # before fillMaxHeight / height.
          #
          # Label/Text vertical glyph alignment: Compose `Text` has no vertical
          # text-align, so whenever a Label fills a taller area (minHeight,
          # height:matchParent, or a vertical-container weight) and its gravity
          # asks for vertical center/bottom, we pair the fill with
          # `.wrapContentHeight(align = ...)` to move the glyphs within the filled
          # area — matching iOS `.frame(alignment: .center)`.
          # Regression: kjui-label-gravity-center-not-vertically-centered
          #             (extends the original minHeight-only handling).
          is_label = json_data['type'] == 'Label' || json_data['type'] == 'Text'
          label_valign = nil
          if is_label && json_data['gravity']
            gravity_parts = if json_data['gravity'].is_a?(Array)
                              json_data['gravity'].map { |g| g.to_s.strip.downcase }
                            else
                              json_data['gravity'].to_s.split('|').map { |g| g.strip.downcase }
                            end
            if gravity_parts.include?('bottom')
              label_valign = 'Alignment.Bottom'
            elsif gravity_parts.include?('center') ||
                  gravity_parts.include?('centervertical') ||
                  gravity_parts.include?('center_vertical') ||
                  gravity_parts.include?('centerinparent') ||
                  gravity_parts.include?('center_in_parent')
              label_valign = 'Alignment.CenterVertically'
            end
          end

          valign_emitted = false
          if label_valign && json_data['minHeight']
            # minHeight + vertical gravity: defaultMinSize floor + wrapContentHeight.
            modifiers << ".defaultMinSize(minHeight = #{BoundValue.dp(json_data['minHeight'])})"
            modifiers << ".wrapContentHeight(align = #{label_valign})"
            valign_emitted = true
            # `maxHeight` (if any) is still applied below as a normal heightIn.
            if json_data['maxHeight']
              modifiers << ".heightIn(max = #{BoundValue.dp(json_data['maxHeight'], null_expr: 'Dp.Infinity')})"
            end
          end

          # Same explicit-size rule as the width axis: a declared numeric
          # height wins over the heightIn bounds (mirror of the dynamic
          # `.height(N).heightIn(...)` chain, where the bound is inert).
          height_constraint =
            if valign_emitted
              nil # handled above (defaultMinSize + optional heightIn(max))
            elsif json_data['minHeight'] && json_data['maxHeight']
              ".heightIn(min = #{BoundValue.dp(json_data['minHeight'])}, max = #{BoundValue.dp(json_data['maxHeight'], null_expr: 'Dp.Infinity')})"
            elsif json_data['minHeight']
              ".heightIn(min = #{BoundValue.dp(json_data['minHeight'])})"
            elsif json_data['maxHeight']
              ".heightIn(max = #{BoundValue.dp(json_data['maxHeight'], null_expr: 'Dp.Infinity')})"
            end
          explicit_height = json_data['height'] &&
                            json_data['height'] != 'matchParent' &&
                            json_data['height'] != 'wrapContent' &&
                            !(json_data['heightWeight'] && json_data['height'] == 0)
          modifiers << height_constraint if height_constraint && !explicit_height

          # Height - skip if heightWeight is present and height is 0
          fills_height = false
          if json_data['height'] == 'matchParent'
            modifiers << ".fillMaxHeight()"
            fills_height = true
          elsif json_data['height'] == 'wrapContent'
            modifiers << ".wrapContentHeight()"
          elsif explicit_height
            modifiers << ".height(#{process_dimension(json_data['height'])})"
            modifiers << height_constraint if height_constraint
          elsif parent_type == 'Column' && (json_data['weight'] || json_data['heightWeight'])
            # Weight in a vertical container fills the height slice (the
            # `.weight(..)` modifier itself is emitted by build_weight); no
            # explicit height modifier here, but it still fills for valign.
            fills_height = true
          end

          # Pair the height-fill with wrapContentHeight(align) so a centered/
          # bottom Label actually moves its glyphs within the filled area.
          if label_valign && fills_height && !valign_emitted
            modifiers << ".wrapContentHeight(align = #{label_valign})"
          end
          
          # Aspect ratio. A bound side cannot be divided in Ruby (`"@{w}".to_f`
          # is 0.0, and 0/0 is NaN), so the division moves into the emit.
          if json_data['aspectWidth'] && json_data['aspectHeight']
            if BoundValue.bound?(json_data['aspectWidth']) || BoundValue.bound?(json_data['aspectHeight'])
              w = BoundValue.float(json_data['aspectWidth'], fallback: 1)
              h = BoundValue.float(json_data['aspectHeight'], fallback: 1)
              modifiers << ".aspectRatio(#{w} / #{h})"
            else
              ratio = json_data['aspectWidth'].to_f / json_data['aspectHeight'].to_f
              modifiers << ".aspectRatio(#{ratio}f)"
            end
          end
          
          # `Dp.Infinity` is the unresolved value of a BOUND max, so the
          # import follows the emitted text rather than the declaration.
          if required_imports && modifiers.any? { |m| m.include?('Dp.Infinity') }
            required_imports.add(:dp_infinity)
          end

          modifiers
        end
        
        def self.build_shadow(json_data, required_imports = nil)
          modifiers = []
          
          if json_data['shadow']
            if json_data['cornerRadius']
              shape = "RoundedCornerShape(#{BoundValue.dp(json_data['cornerRadius'])})"
            else
              shape = "RectangleShape"
            end

            shadow_args = nil
            if json_data['shadow'].is_a?(String)
              # The string form is the UIKit pipe contract
              # 'color|offsetX|offsetY|opacity|radius' — exactly five
              # fields; anything else draws nothing (the canonical guard
              # all render paths share).
              parts = json_data['shadow'].split('|', -1)
              if parts.length == 5
                color = ResourceResolver.process_color(parts[0], required_imports)
                required_imports&.add(:dp_offset)
                shadow_args = "radius = #{parts[4].to_f}.dp, color = #{color}, " \
                              "offset = DpOffset(#{parts[1].to_f}.dp, #{parts[2].to_f}.dp), alpha = #{parts[3].to_f}f"
              end
            elsif json_data['shadow'].is_a?(Hash)
              shadow = json_data['shadow']
              args = ["radius = #{shadow['radius'] || 4}.dp"]
              if shadow['color']
                args << "color = #{ResourceResolver.process_color(shadow['color'], required_imports)}"
              end
              if shadow['offsetX'] || shadow['offsetY']
                required_imports&.add(:dp_offset)
                args << "offset = DpOffset(#{(shadow['offsetX'] || 0).to_f}.dp, #{(shadow['offsetY'] || 0).to_f}.dp)"
              end
              args << "alpha = #{shadow['opacity'].to_f}f" if shadow['opacity']
              shadow_args = args.join(', ')
            end

            if shadow_args
              required_imports&.add(:drop_shadow)
              required_imports&.add(:rectangle_shape) if shape == "RectangleShape"
              modifiers << ".dropShadow(shape = #{shape}, shadow = Shadow(#{shadow_args}))"
            end
          end
          
          modifiers
        end
        
        def self.build_background(json_data, required_imports = nil)
          modifiers = []
          
          # highlighted — UIKit's pressed/selected appearance flag: when set
          # (literal true, or a bool binding) the background swaps to
          # highlightBackground, matching sjui's apply_highlighted_to_bag.
          #
          # `tapBackground` is the declared cross-platform spelling of the same
          # colour and no Compose path read it (plan 49 lane C:
          # common.tapBackground, C0 unread + C1 dropped). sjui and rjui both
          # accept `tapBackground || highlightBackground`; so does this now.
          highlight_bg = json_data['tapBackground'] || json_data['highlightBackground']
          highlight_cond = case json_data['highlighted']
                           when true, 'true' then 'true'
                           when String
                             if is_binding?(json_data['highlighted'])
                               "data.#{extract_binding_property(json_data['highlighted'])}"
                             end
                           end

          if json_data['background']
            required_imports&.add(:background)
            
            # Use ResourceResolver to process background color
            background_color = ResourceResolver.process_color(json_data['background'], required_imports)
            if highlight_cond && highlight_bg
              hl = ResourceResolver.process_color(highlight_bg, required_imports)
              background_color = highlight_cond == 'true' ? hl : "if (#{highlight_cond}) #{hl} else #{background_color}"
            end
            
            if json_data['cornerRadius'] || json_data['borderColor'] || json_data['borderWidth']
              required_imports&.add(:border)
              required_imports&.add(:shape)

              # border before clip to prevent border being clipped
              if json_data['borderColor'] && json_data['borderWidth']
                modifiers << build_border_modifier(json_data, required_imports)
              end

              if json_data['cornerRadius']
                modifiers << ".clip(RoundedCornerShape(#{BoundValue.dp(json_data['cornerRadius'])}))"
              end

              modifiers << ".background(#{background_color})"
            else
              modifiers << ".background(#{background_color})"
            end
          elsif highlight_cond && highlight_bg
            # No base background: the highlight IS the background when the
            # flag holds (transparent otherwise, which is what no-background
            # renders anyway).
            required_imports&.add(:background)
            hl = ResourceResolver.process_color(highlight_bg, required_imports)
            expr = highlight_cond == 'true' ? hl : "if (#{highlight_cond}) #{hl} else Color.Transparent"
            modifiers << ".background(#{expr})"
          elsif json_data['cornerRadius'] || json_data['borderColor'] || json_data['borderWidth']
            required_imports&.add(:border)
            required_imports&.add(:shape)

            # border before clip
            if json_data['borderColor'] && json_data['borderWidth']
              modifiers << build_border_modifier(json_data, required_imports)
            end

            if json_data['cornerRadius']
              modifiers << ".clip(RoundedCornerShape(#{BoundValue.dp(json_data['cornerRadius'])}))"
            end
          end

          # `safeAreaInsetPositions` on a PLAIN node. The SSoT declares it on
          # View as well as SafeAreaView on purpose — sjui runs
          # `apply_safe_area_insets_to_bag` for every component and rjui emits
          # `env(safe-area-inset-*)` padding from `safe_area_edges`, while
          # kjui read the spelling only inside the SafeAreaView builder
          # (compose_builder.rb:722). Same edge vocabulary and the same
          # Compose primitives that builder uses, so the two agree.
          edges = json_data['safeAreaInsetPositions']
          if edges && json_data['type'] != 'SafeAreaView'
            edges = [edges] unless edges.is_a?(Array)
            edges = edges.map(&:to_s)
            required_imports&.add(:safe_area_padding)
            if edges.include?('all')
              modifiers << '.systemBarsPadding()'
            else
              modifiers << '.statusBarsPadding()' if edges.include?('top') || edges.include?('vertical')
              modifiers << '.navigationBarsPadding()' if edges.include?('bottom') || edges.include?('vertical')
            end
          end

          # clipToBounds — declared boolean|binding. A plain truthiness test
          # froze `"@{flag}"` permanently ON (plan 49 lane C, bound-frozen).
          clip_state = BoundValue.bool(json_data['clipToBounds'])
          if (clip = BoundValue.conditional_modifier(clip_state, '.clipToBounds()'))
            required_imports&.add(:shape)
            modifiers << clip
          end

          modifiers
        end

        def self.build_test_tag(json_data, required_imports = nil)
          modifiers = []

          if json_data['id']
            id_value = json_data['id']
            required_imports&.add(:semantics)
            required_imports&.add(:test_tag)
            required_imports&.add(:test_tags_as_resource_id)
            # Add testTag for UI testing (used by Espresso/UI Automator)
            modifiers << ".testTag(\"#{id_value}\")"
            # Expose testTag as resource-id for UIAutomator compatibility (Compose 1.2+)
            modifiers << ".semantics { testTagsAsResourceId = true }"
          end

          modifiers
        end

        def self.build_visibility(json_data, required_imports = nil)
          modifiers = []
          visibility_info = {}
          
          # Handle visibility attribute (static or data-bound)
          if json_data['visibility']
            if json_data['visibility'].is_a?(String) && json_data['visibility'].start_with?('@{')
              # Data binding for visibility (string value context —
              # canonical parse so a `?? 'gone'` default emits a real elvis)
              inner = json_data['visibility'][2..-2]
              visibility_info[:visibility_binding] = BindingExpression.value_access(inner)
              required_imports&.add(:visibility_wrapper)
            else
              # Static visibility
              visibility_info[:visibility] = json_data['visibility']
              required_imports&.add(:visibility_wrapper)
            end
          end

          # Handle hidden attribute (boolean or data binding)
          if json_data['hidden']
            if json_data['hidden'].is_a?(String) && json_data['hidden'].start_with?('@{')
              # Data binding for hidden (boolean value context — `@{!flag}`
              # emits a real Kotlin negation, `?? true/false` a real elvis)
              inner = json_data['hidden'][2..-2]
              visibility_info[:hidden_binding] = BindingExpression.value_access(inner, negatable: true)
              required_imports&.add(:visibility_wrapper)
            elsif json_data['hidden'] == true
              visibility_info[:hidden] = true
              required_imports&.add(:visibility_wrapper)
            end
          end
          
          # Handle alpha/opacity attribute separately (not part of visibility wrapper)
          # Canonical spelling is 'opacity' ('alpha' is its alias; alias
          # fallback is skipped for L1-normalized layouts).
          alpha_value = Core::Normalization.attr_lookup(json_data, 'opacity', 'alpha')
          if alpha_value
            required_imports&.add(:alpha)
            # A nullable bound opacity used to emit `data.x.toFloat()`, which
            # does not compile on a `Double?`. BoundValue coalesces it.
            modifiers << ".alpha(#{BoundValue.float(alpha_value, fallback: 1)})"
          end

          # Return both visibility info and modifiers
          { modifiers: modifiers, visibility_info: visibility_info }
        end
        
        # Build alpha/opacity modifier separately (can be used independently of visibility)
        def self.build_alpha(json_data, required_imports = nil)
          modifiers = []
          alpha_value = Core::Normalization.attr_lookup(json_data, 'opacity', 'alpha')
          if alpha_value
            required_imports&.add(:alpha)
            # A nullable bound opacity used to emit `data.x.toFloat()`, which
            # does not compile on a `Double?`. BoundValue coalesces it.
            modifiers << ".alpha(#{BoundValue.float(alpha_value, fallback: 1)})"
          end
          modifiers
        end

        # Build .clickable modifier for non-Button components with onClick/onclick.
        # onLongPress rides the same sink: its detector is emitted BEFORE
        # .clickable (mirrors dynamic ModifierBuilder.applyClickable) so a
        # fired long press consumes the gesture and the click never fires.
        def self.build_clickable(json_data, required_imports = nil)
          modifiers = []
          modifiers.concat(build_long_pressable(json_data, required_imports))
          modifiers.concat(build_pannable(json_data, required_imports))
          modifiers.concat(build_pinchable(json_data, required_imports))
          handler = json_data['onclick'] || json_data['onClick']
          enabled = enabled_expression(json_data)
          # `canTap` is the tap gate specifically — UIKit's SJUIView has the
          # property and uses it to decide whether the tap recogniser fires. Both
          # gate the click, so both apply.
          can_tap = boolean_expression(json_data['canTap'])
          tap_gate = [enabled, can_tap].compact
          if handler
            required_imports&.add(:clickable)
            view_id = json_data['id']
            if json_data['onClick'] && is_binding?(json_data['onClick'])
              handler_call = get_event_handler_invocation(json_data['onClick'], view_id, nil)
            elsif json_data['onClick']
              handler_call = get_event_handler_call(json_data['onClick'], is_camel_case: true)
            else
              handler_call = get_event_handler_call(json_data['onclick'], is_camel_case: false)
            end
            gate = tap_gate.any? ? "(enabled = #{tap_gate.join(' && ')})" : ''
            modifiers << ".clickable#{gate} { #{handler_call} }"
          end
          # `disabled()` follows `enabled` only: a view that is merely not
          # tappable is not "disabled" to a screen reader.
          modifiers.concat(build_disabled_semantics(json_data, enabled, required_imports))
          modifiers.concat(build_interaction_blocker(json_data, required_imports))
          modifiers
        end

        # userInteractionEnabled — blocks touches for this node AND its
        # descendants, which is what UIKit's flag does and what
        # `.allowsHitTesting(false)` does on iOS. Compose has no such modifier, so
        # the events are consumed in the Initial pass, before any child sees
        # them. The same pass build_long_pressable already uses.
        def self.build_interaction_blocker(json_data, required_imports = nil)
          expr = boolean_expression(json_data['userInteractionEnabled'])
          return [] if expr.nil?

          required_imports&.add(:interaction_blocker)
          consume = <<~KOTLIN.rstrip
            awaitPointerEventScope {
                while (true) {
                    awaitPointerEvent(PointerEventPass.Initial).changes.forEach { it.consume() }
                }
            }
          KOTLIN

          # A literal `false` is decided here, not at runtime: emitting
          # `if (!(false))` would trip the Kotlin "condition is always true"
          # warning, and the kjui build gate tolerates zero warnings.
          if expr == 'false'
            return [".pointerInput(Unit) {\n#{indent_block(consume, 1)}\n}"]
          end

          [".pointerInput(#{expr}) {\n    if (!(#{expr})) {\n#{indent_block(consume, 2)}\n    }\n}"]
        end

        def self.indent_block(text, levels)
          pad = '    ' * levels
          text.split("\n").map { |line| line.empty? ? line : pad + line }.join("\n")
        end

        # `enabled` — declared boolean|binding on `common`, so it may appear on
        # any node, and the Compose codegen read it on none of them: a View with
        # `enabled: "@{x}"` stayed clickable. Returns the Kotlin boolean
        # expression, or nil when the attribute is absent or literally true
        # (which is the default and needs no gate).
        def self.enabled_expression(json_data)
          boolean_expression(json_data['enabled'])
        end

        # A boolean|binding attribute as a Kotlin expression. `true` yields nil:
        # it is the default for every one of these gates, so emitting it would
        # only add noise.
        # The bound branch used to be `data.#{$1}` — the inner expression
        # spliced in verbatim, so `@{on ?? true}` emitted `data.on ?? true`.
        # `??` is not Kotlin, and no validator rule fires here: only
        # attributes DECLARED `binding_direction: "two-way"` are checked for a
        # complex expression, and `enabled` is not one of them. Measured on
        # Button / Slider / TextField before the fix (plan 49 lane C, the
        # audit the "the validator rejects it anyway" claim did not survive).
        def self.boolean_expression(value)
          # ABSENT is not the same as `false` here: an absent flag means "no
          # gate at all", while a declared `false` means "gate, permanently
          # shut". BoundValue#bool folds both into :off, so absence is checked
          # before asking it.
          return nil if value.nil?

          state = BoundValue.bool(value)
          case state
          when :on then nil     # the default for every gate that calls this
          when :off then 'false'
          else state
          end
        end

        # A click-gated node is still `enabled` in the a11y tree, and the a11y
        # tree is the only thing a UI test can observe (`assert: "disabled"`
        # reads it). The check lives inside the semantics lambda so a binding
        # needs no conditional Modifier.
        def self.build_disabled_semantics(json_data, enabled, required_imports)
          return [] if enabled.nil?

          required_imports&.add(:semantics_disabled)
          return [".semantics { disabled() }"] if enabled == 'false'

          [".semantics { if (!#{enabled}) disabled() }"]
        end

        # onLongPress (common attribute, platform swift/kotlin) → long-press
        # gesture modifier. Mirrors the dynamic fix
        # (ModifierBuilder.applyLongPressable, KotlinJsonUI 2.9.2):
        #
        # `Modifier.pointerInput { detectTapGestures(onLongPress) }` does NOT
        # work on components with an inner clickable (Button's own .clickable,
        # or the .clickable emitted after this modifier) — the inner handler
        # consumes the down event in the Main pass and awaitFirstDown
        # (requireUnconsumed = true) starves. combinedClickable on Button's
        # modifier races the same way. Instead the detector watches the
        # Initial pass, which sees every gesture before any inner handler;
        # when the press outlives the long-press timeout it fires the handler
        # and consumes the remaining events so the inner onClick is cancelled.
        #
        # `pointerInput(data)` keys the gesture coroutine on the data holder
        # so a rebuilt handler set restarts it with fresh closures — same
        # contract as the dynamic pointerInput(handler, data) keys.
        #
        # Handler resolution follows camelCase onClick conventions:
        # @{binding} → get_event_handler_invocation (data-definition aware),
        # plain name → data.<name>?.invoke().
        def self.build_long_pressable(json_data, required_imports = nil)
          handler = json_data['onLongPress']
          return [] unless handler

          required_imports&.add(:long_press_gesture)
          view_id = json_data['id']
          handler_call = if is_binding?(handler)
                           get_event_handler_invocation(handler, view_id, nil)
                         else
                           get_event_handler_call(handler, is_camel_case: true)
                         end

          gesture = <<~KOTLIN.rstrip
            .pointerInput(data) {
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
                    val longPressed = try {
                        withTimeout(viewConfiguration.longPressTimeoutMillis) {
                            var event: PointerEvent
                            do {
                                event = awaitPointerEvent(PointerEventPass.Initial)
                            } while (event.changes.any { it.pressed })
                        }
                        false
                    } catch (_: PointerEventTimeoutCancellationException) {
                        true
                    }
                    if (longPressed) {
                        #{handler_call}
                        var event: PointerEvent
                        do {
                            event = awaitPointerEvent(PointerEventPass.Initial)
                            event.changes.forEach { it.consume() }
                        } while (event.changes.any { it.pressed })
                    }
                }
            }
          KOTLIN
          [gesture]
        end

        # onPan (common attribute) → drag gesture. The handler fires on every
        # drag event with the cumulative translation since the gesture began
        # (an Offset — accumulated from per-event deltas so the payload matches
        # SwiftUI's DragGesture.Value.translation). Declaring onPan means this
        # node owns drags: detectDragGestures consumes them, so a surrounding
        # scroll container will not also scroll from touches on this node —
        # same trade a native drag handler makes.
        #
        # Handler resolution is data-definition aware (get_event_handler_invocation):
        # () -> Unit stays bare, (Offset) — optionally after a String id —
        # receives the payload.
        def self.build_pannable(json_data, required_imports = nil)
          handler = json_data['onPan']
          return [] unless handler && is_binding?(handler)

          required_imports&.add(:pan_gesture)
          handler_call = get_event_handler_invocation(handler, json_data['id'], 'total')

          gesture = <<~KOTLIN.rstrip
            .pointerInput(data) {
                var total = Offset.Zero
                detectDragGestures(
                    onDragStart = { total = Offset.Zero },
                    onDrag = { change, dragAmount ->
                        change.consume()
                        total += dragAmount
                        #{handler_call}
                    }
                )
            }
          KOTLIN
          [gesture]
        end

        # onPinch (common attribute) → pinch/zoom gesture. The handler fires
        # with the cumulative scale factor since the gesture began (Float,
        # matching MagnifyGesture.Value.magnification on iOS). A raw
        # awaitEachGesture loop rather than detectTransformGestures because the
        # scale must reset per gesture and detectTransformGestures has no
        # gesture-start hook. calculateZoom() is 1f for single-pointer events,
        # so taps and one-finger drags pass through untouched (onPan and
        # onClick on the same node keep working).
        def self.build_pinchable(json_data, required_imports = nil)
          handler = json_data['onPinch']
          return [] unless handler && is_binding?(handler)

          required_imports&.add(:pinch_gesture)
          handler_call = get_event_handler_invocation(handler, json_data['id'], 'scale')

          gesture = <<~KOTLIN.rstrip
            .pointerInput(data) {
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false)
                    var scale = 1f
                    var event: PointerEvent
                    do {
                        event = awaitPointerEvent()
                        val zoom = event.calculateZoom()
                        if (zoom != 1f) {
                            scale *= zoom
                            event.changes.forEach { it.consume() }
                            #{handler_call}
                        }
                    } while (event.changes.any { it.pressed })
                }
            }
          KOTLIN
          [gesture]
        end

        # The seven alignment flags are declared `["boolean", "binding"]` in the
        # SSoT, and this method used to read them with plain Ruby truthiness —
        # so `alignTop: "@{flag}"` was a non-empty String, i.e. permanently ON
        # (plan 49 lane C, 7 of the 18 `bound-frozen`).
        #
        # The decision tree is a pure function of those seven booleans, so it
        # is expressed once, as a priority-ordered list, and evaluated in one
        # of two modes (BoundValue#priority_modifier):
        #
        #   * every flag static  -> folded in Ruby, first match wins. This is
        #     the same answer the old if/elsif chain gave, character for
        #     character.
        #   * any flag bound     -> the SAME list becomes a Kotlin `when`,
        #     spliced in with `.then(...)`. `Modifier.align` stays resolvable
        #     because the expression is evaluated at the call site, inside the
        #     surrounding Row/Column/BoxScope content lambda.
        def self.build_alignment(json_data, required_imports = nil, parent_type = nil)
          top = BoundValue.bool(json_data['alignTop'])
          bottom = BoundValue.bool(json_data['alignBottom'])
          left = BoundValue.bool(json_data['alignLeft'])
          right = BoundValue.bool(json_data['alignRight'])
          center_h = BoundValue.bool(json_data['centerHorizontal'])
          center_v = BoundValue.bool(json_data['centerVertical'])
          center_both = BoundValue.bool(json_data['centerInParent'])

          modifiers =
            case parent_type
            when 'ScopeFree'
              build_scope_free_alignment(top, bottom, left, right, center_h, center_v, center_both)
            when 'Row'
              # For Row, only vertical alignment is allowed
              [BoundValue.priority_modifier([
                [top, '.align(Alignment.Top)'],
                [bottom, '.align(Alignment.Bottom)'],
                [center_v, '.align(Alignment.CenterVertically)']
              ])]
            when 'Column'
              # For Column, only horizontal alignment is allowed
              [BoundValue.priority_modifier([
                [left, '.align(Alignment.Start)'],
                [right, '.align(Alignment.End)'],
                [center_h, '.align(Alignment.CenterHorizontally)']
              ])]
            when 'Box'
              # For Box and other containers, full alignment options
              [BoundValue.priority_modifier(
                box_alignment_pairs(top, bottom, left, right, center_h, center_v, center_both)
              )]
              # No default TopStart - let parent's contentAlignment handle it
            else
              []
            end.compact

          # A runtime `when` can carry BiasAlignment in ANY of its arms, so the
          # import follows the emitted text rather than the branch taken.
          if required_imports && modifiers.any? { |m| m.include?('BiasAlignment') }
            required_imports.add(:bias_alignment)
          end

          modifiers
        end

        # Scope-free emit context (no surrounding RowScope/ColumnScope/BoxScope).
        # Used by the file-scope responsive helper composables (see
        # compose_builder#generate_responsive_container) — Modifier.align(...)
        # is a *Scope-receiver-bound* extension, so it doesn't resolve here.
        # Translate centering to scope-independent equivalents.
        #
        # `centerInParent` short-circuited both axes in the original; folding it
        # in as the top branch of each axis says the same thing without needing
        # the outer branch.
        def self.build_scope_free_alignment(top, bottom, left, right, center_h, center_v, center_both)
          # Horizontal axis. centerHorizontal beats align-left/right; the
          # align-both case (left AND right) collapses to center to match
          # the SwiftUI side and the original Android XML semantics.
          horizontal = BoundValue.priority_modifier([
            [center_both, '.wrapContentWidth(Alignment.CenterHorizontally)'],
            [center_h, '.wrapContentWidth(Alignment.CenterHorizontally)'],
            [BoundValue.all_of(left, right), '.wrapContentWidth(Alignment.CenterHorizontally)'],
            [left, '.wrapContentWidth(Alignment.Start)'],
            [right, '.wrapContentWidth(Alignment.End)']
          ])
          # Vertical axis. Same precedence.
          vertical = BoundValue.priority_modifier([
            [center_both, '.wrapContentHeight(Alignment.CenterVertically)'],
            [center_v, '.wrapContentHeight(Alignment.CenterVertically)'],
            [BoundValue.all_of(top, bottom), '.wrapContentHeight(Alignment.CenterVertically)'],
            [top, '.wrapContentHeight(Alignment.Top)'],
            [bottom, '.wrapContentHeight(Alignment.Bottom)']
          ])
          [horizontal, vertical]
        end

        # The BoxScope decision tree, in the original priority order. `hb`/`vb`
        # are the both-direction constraints that mean "centre on that axis".
        def self.box_alignment_pairs(top, bottom, left, right, center_h, center_v, center_both)
          hb = BoundValue.all_of(left, right)
          vb = BoundValue.all_of(top, bottom)

          [
            # Both horizontal and vertical constraints - center completely
            [BoundValue.all_of(hb, vb), '.align(Alignment.Center)'],
            # Center horizontally, align top / bottom
            [BoundValue.all_of(hb, top), '.align(BiasAlignment(0f, -1f))'],
            [BoundValue.all_of(hb, bottom), '.align(BiasAlignment(0f, 1f))'],
            # Just center horizontally
            [hb, '.align(BiasAlignment(0f, 0f))'],
            # Center vertically, align left / right
            [BoundValue.all_of(vb, left), '.align(Alignment.CenterStart)'],
            [BoundValue.all_of(vb, right), '.align(Alignment.CenterEnd)'],
            # Just center vertically
            [vb, '.align(BiasAlignment(0f, 0f))'],
            [BoundValue.all_of(top, left), '.align(Alignment.TopStart)'],
            [BoundValue.all_of(top, right), '.align(Alignment.TopEnd)'],
            [BoundValue.all_of(bottom, left), '.align(Alignment.BottomStart)'],
            [BoundValue.all_of(bottom, right), '.align(Alignment.BottomEnd)'],
            # TopCenter / BottomCenter don't exist in BoxScope, use BiasAlignment
            [BoundValue.all_of(top, center_h), '.align(BiasAlignment(0f, -1f))'],
            [BoundValue.all_of(bottom, center_h), '.align(BiasAlignment(0f, 1f))'],
            [BoundValue.all_of(left, center_v), '.align(Alignment.CenterStart)'],
            [BoundValue.all_of(right, center_v), '.align(Alignment.CenterEnd)'],
            [center_both, '.align(Alignment.Center)'],
            # Handle single alignments for Box
            [top, '.align(BiasAlignment(-1f, -1f))'],
            [bottom, '.align(BiasAlignment(-1f, 1f))'],
            [left, '.align(BiasAlignment(-1f, -1f))'],
            [right, '.align(BiasAlignment(1f, -1f))'],
            [center_h, '.align(BiasAlignment(0f, -1f))'],
            [center_v, '.align(BiasAlignment(-1f, 0f))']
          ]
        end
        
        def self.build_relative_positioning(json_data)
          # These attributes require ConstraintLayout
          # They generate constraint references instead of modifiers
          constraints = []

          # Extract margins for use in constraints (with binding support)
          top_margin = constraint_margin_value(json_data['topMargin'])
          bottom_margin = constraint_margin_value(json_data['bottomMargin'])
          start_margin = constraint_margin_value(json_data['leftMargin'])
          end_margin = constraint_margin_value(json_data['rightMargin'])

          if json_data['margins'] && json_data['margins'].is_a?(Array) && json_data['margins'].length == 4
            top_margin = json_data['margins'][0].to_s + ".dp" unless json_data['topMargin']
            end_margin = json_data['margins'][1].to_s + ".dp" unless json_data['rightMargin']
            bottom_margin = json_data['margins'][2].to_s + ".dp" unless json_data['bottomMargin']
            start_margin = json_data['margins'][3].to_s + ".dp" unless json_data['leftMargin']
          end
          
          # Relative to other views
          if json_data['alignTopOfView']
            margin = has_constraint_margin?(bottom_margin) ? ", margin = #{bottom_margin}" : ""
            constraints << "bottom.linkTo(#{json_data['alignTopOfView']}.top#{margin})"
          end

          if json_data['alignBottomOfView']
            margin = has_constraint_margin?(top_margin) ? ", margin = #{top_margin}" : ""
            constraints << "top.linkTo(#{json_data['alignBottomOfView']}.bottom#{margin})"
          end

          if json_data['alignLeftOfView']
            margin = has_constraint_margin?(end_margin) ? ", margin = #{end_margin}" : ""
            constraints << "end.linkTo(#{json_data['alignLeftOfView']}.start#{margin})"
          end

          if json_data['alignRightOfView']
            margin = has_constraint_margin?(start_margin) ? ", margin = #{start_margin}" : ""
            constraints << "start.linkTo(#{json_data['alignRightOfView']}.end#{margin})"
          end

          # Align edges with other views
          # For align operations, use negative margins to move in the expected direction
          if json_data['alignTopView']
            # alignTop with topMargin means move DOWN from the aligned position
            # linkTo margin pushes away, so use negative to pull closer (move down)
            margin = has_constraint_margin?(top_margin) ? ", margin = (-#{top_margin})" : ""
            constraints << "top.linkTo(#{json_data['alignTopView']}.top#{margin})"
          end

          if json_data['alignBottomView']
            # alignBottom with bottomMargin means move UP from the aligned position
            # linkTo margin pushes away, so use negative to pull closer (move up)
            margin = has_constraint_margin?(bottom_margin) ? ", margin = (-#{bottom_margin})" : ""
            constraints << "bottom.linkTo(#{json_data['alignBottomView']}.bottom#{margin})"
          end

          if json_data['alignLeftView']
            # alignLeft with leftMargin means move RIGHT from the aligned position
            # linkTo margin pushes away, so use negative to pull closer (move right)
            margin = has_constraint_margin?(start_margin) ? ", margin = (-#{start_margin})" : ""
            constraints << "start.linkTo(#{json_data['alignLeftView']}.start#{margin})"
          end

          if json_data['alignRightView']
            # alignRight with rightMargin means move LEFT from the aligned position
            # linkTo margin pushes away, so use negative to pull closer (move left)
            margin = has_constraint_margin?(end_margin) ? ", margin = (-#{end_margin})" : ""
            constraints << "end.linkTo(#{json_data['alignRightView']}.end#{margin})"
          end

          # Center with other views
          if json_data['alignCenterVerticalView']
            constraints << "top.linkTo(#{json_data['alignCenterVerticalView']}.top)"
            constraints << "bottom.linkTo(#{json_data['alignCenterVerticalView']}.bottom)"
          end

          if json_data['alignCenterHorizontalView']
            constraints << "start.linkTo(#{json_data['alignCenterHorizontalView']}.start)"
            constraints << "end.linkTo(#{json_data['alignCenterHorizontalView']}.end)"
          end

          # Parent constraints
          # For parent alignment, margins should work normally as offsets
          if json_data['alignTop']
            margin = has_constraint_margin?(top_margin) ? ", margin = #{top_margin}" : ""
            constraints << "top.linkTo(parent.top#{margin})"
          end

          if json_data['alignBottom']
            margin = has_constraint_margin?(bottom_margin) ? ", margin = #{bottom_margin}" : ""
            constraints << "bottom.linkTo(parent.bottom#{margin})"
          end

          if json_data['alignLeft']
            margin = has_constraint_margin?(start_margin) ? ", margin = #{start_margin}" : ""
            constraints << "start.linkTo(parent.start#{margin})"
          end

          if json_data['alignRight']
            margin = has_constraint_margin?(end_margin) ? ", margin = #{end_margin}" : ""
            constraints << "end.linkTo(parent.end#{margin})"
          end
          
          if json_data['centerHorizontal']
            constraints << "start.linkTo(parent.start)"
            constraints << "end.linkTo(parent.end)"
          end
          
          if json_data['centerVertical']
            constraints << "top.linkTo(parent.top)"
            constraints << "bottom.linkTo(parent.bottom)"
          end
          
          if json_data['centerInParent']
            constraints << "top.linkTo(parent.top)"
            constraints << "bottom.linkTo(parent.bottom)"
            constraints << "start.linkTo(parent.start)"
            constraints << "end.linkTo(parent.end)"
          end
          
          constraints
        end
        
        # is_root: when true, start the modifier chain from the caller's
        # `modifier` (lowercase) parameter instead of a fresh `Modifier`.
        # The generated *GeneratedView function signature exposes
        # `modifier: Modifier = Modifier` to callers (e.g. for
        # combinedClickable, weight, layout). Chaining from the parameter
        # puts caller modifiers OUTSIDE the internal chain so they apply
        # to the full element area (e.g. padding-inclusive). When
        # `is_root` and the internal chain is empty we still emit a
        # `modifier = modifier` clause so the caller's modifier is wired
        # in — otherwise root composables with no internal modifiers
        # would silently drop the caller's modifier.
        def self.format(modifiers, depth, is_root: false)
          return "" if modifiers.empty? && !is_root

          base = is_root ? "modifier = modifier" : "modifier = Modifier"

          if modifiers.empty?
            return "\n" + indent(base, depth + 1)
          end

          # Check if first modifier is already "Modifier"
          if modifiers[0] == "Modifier"
            code = "\n" + indent(base, depth + 1)
            # Skip the first "Modifier" and process the rest
            modifiers[1..-1].each do |mod|
              # indent(mod, 1) first so continuation lines of multi-line
              # modifiers (e.g. the onLongPress pointerInput block) keep
              # their relative indentation; identical output for the
              # single-line case.
              code += "\n" + indent(indent(mod, 1), depth + 1)
            end
          else
            code = "\n" + indent(base, depth + 1)

            # The inline shortcut is only valid for single-line modifiers;
            # a multi-line modifier appended inline would lose the base
            # indentation on its continuation lines.
            if modifiers.length == 1 && modifiers[0].start_with?('.') && !modifiers[0].include?("\n")
              code += modifiers[0]
            else
              modifiers.each do |mod|
                code += "\n" + indent(indent(mod, 1), depth + 1)
              end
            end
          end

          code
        end

        # Build lifecycle event effects (onAppear/onDisappear)
        # Returns a hash with :before (code before content) and :after (code after content)
        def self.build_lifecycle_effects(json_data, depth, required_imports = nil)
          result = { before: "", after: "" }

          if json_data['onAppear']
            required_imports&.add(:launched_effect)
            handler = json_data['onAppear']
            # Strip @{} binding syntax if present
            property = is_binding?(handler) ? extract_binding_property(handler) : handler
            # Also strip : prefix if present
            property = property.gsub(':', '') if property.include?(':')

            result[:before] += indent("// onAppear lifecycle event", depth)
            result[:before] += "\n" + indent("LaunchedEffect(Unit) {", depth)
            result[:before] += "\n" + indent("data.#{property}?.invoke()", depth + 1)
            result[:before] += "\n" + indent("}", depth)
            result[:before] += "\n"
          end

          if json_data['onDisappear']
            required_imports&.add(:disposable_effect)
            handler = json_data['onDisappear']
            # Strip @{} binding syntax if present
            property = is_binding?(handler) ? extract_binding_property(handler) : handler
            # Also strip : prefix if present
            property = property.gsub(':', '') if property.include?(':')

            result[:before] += indent("// onDisappear lifecycle event", depth)
            result[:before] += "\n" + indent("DisposableEffect(Unit) {", depth)
            result[:before] += "\n" + indent("onDispose {", depth + 1)
            result[:before] += "\n" + indent("data.#{property}?.invoke()", depth + 2)
            result[:before] += "\n" + indent("}", depth + 1)
            result[:before] += "\n" + indent("}", depth)
            result[:before] += "\n"
          end

          result
        end

        # Check if component has lifecycle events
        def self.has_lifecycle_events?(json_data)
          json_data['onAppear'] || json_data['onDisappear']
        end

        # Convert event handler to method call
        # onClick -> binding format only: @{functionName} -> data.functionName?.invoke()
        def self.get_event_handler_call(handler, is_camel_case: false)
          # Extract function name from binding format @{functionName}
          if handler.match?(/^@\{(.+)\}$/)
            method_name = handler.match(/^@\{(.+)\}$/)[1]
            "data.#{method_name}?.invoke()"
          else
            # Direct function name (non-binding)
            "data.#{handler}?.invoke()"
          end
        end

        # Generate event handler invocation code based on data section type definition
        # @param handler [String] The event handler value from JSON (e.g., "@{onToggle}")
        # @param view_id [String] The view's id attribute value
        # @param value_expr [String] The Kotlin expression for the value (e.g., "it", "newValue")
        # @return [String] The Kotlin code to invoke the handler
        #
        # Examples:
        #   - If data section has `() -> Unit`: returns "data.onToggle?.invoke()"
        #   - If data section has `(Event) -> Unit` or `(String, Boolean) -> Unit`:
        #     returns "data.onToggle?.invoke(\"viewId\", it)"
        def self.get_event_handler_invocation(handler, view_id, value_expr)
          method_name = extract_binding_property(handler) || handler

          # Look up the handler's type in data_definitions
          data_def = ResourceResolver.data_definitions[method_name]

          if data_def && data_def['class']
            class_type = data_def['class'].to_s

            # Check if the type has parameters (contains Event or has tuple like (String, Boolean))
            # Pattern: ((Event) -> ...) or ((String, Type) -> ...) or ((String) -> ...)
            if class_type.include?('Event') || class_type.match?(/\(\s*\(?\s*String\s*[,)]/)
              # Handler expects viewId (and optionally value) arguments
              if value_expr.nil?
                # Click events without value - only pass viewId
                "data.#{method_name}?.invoke(\"#{view_id}\")"
              else
                "data.#{method_name}?.invoke(\"#{view_id}\", #{value_expr})"
              end
            elsif class_type.match?(/\(\s*\)\s*->/)
              # Handler is () -> Unit (no arguments)
              "data.#{method_name}?.invoke()"
            elsif value_expr && class_type.match?(/\(\s*\(?\s*(Bool|Boolean|Int|Float|Double|Number|Offset)\s*\)?\s*\)\s*->/)
              # Handler takes a single typed argument (e.g., (Bool) -> Void).
              # Offset is the onPan gesture payload; Float covers onPinch.
              "data.#{method_name}?.invoke(#{value_expr})"
            else
              # Default: assume no arguments
              "data.#{method_name}?.invoke()"
            end
          else
            # No data definition found, default to no arguments
            "data.#{method_name}?.invoke()"
          end
        end

        # Check if handler is binding format (@{functionName})
        def self.is_binding?(value)
          value.is_a?(String) && value.match?(/^@\{.+\}$/)
        end

        # Extract property name from binding expression
        # "@{propertyName}" -> "propertyName"
        def self.extract_binding_property(value)
          return nil unless value.is_a?(String)
          if value.match(/^@\{(.+)\}$/)
            $1
          else
            value
          end
        end

        # Convert margin value to Kotlin/Compose format for constraint linkTo() with binding support
        # Returns nil for no margin, or the formatted value (e.g., "8.dp" or "data.margin.dp")
        def self.constraint_margin_value(value)
          return nil if value.nil?

          if is_binding?(value)
            # Same bypass process_dimension had: the hand-rolled emit ignored
            # `??` and nullability. BoundValue is the canonical Dp emitter.
            BoundValue.dp(value)
          elsif value.is_a?(Numeric) && value > 0
            "#{value}.dp"
          elsif value.is_a?(String)
            # Try to parse as number
            num = value.to_i
            num > 0 ? "#{num}.dp" : nil
          else
            nil
          end
        end

        # Check if constraint margin value is present
        def self.has_constraint_margin?(margin_value)
          return false if margin_value.nil?
          return true if margin_value.is_a?(String) && margin_value.length > 0
          false
        end

        private

        # Build border modifier with support for solid/dashed/dotted styles
        def self.build_border_modifier(json_data, required_imports = nil)
          # The width+color PAIR is what requests a border; neither half
          # summons one on its own, and there is no default border colour.
          # That is a recorded ruling, not an inference —
          # `shared/core/attribute_semantics.json#semantics.border` carries it
          # (2026-08-03 user ruling, superseding the transient gray-default of
          # d2c8628, unified across toolchains in 3e87b96; re-measured
          # 2026-08-04 at 0px on all three platforms). `borderStyle` alone
          # likewise renders nothing: it styles a border the pair requested.
          # The five `observable` entries are a machine gate — making any
          # single declaration active turns `gate --cross-effect` red.
          #
          # NOTE: `TextField.borderStyle` is a DIFFERENT attribute (UIKit
          # text-field chrome) and is outside this rule.
          border_color = ResourceResolver.process_color(json_data['borderColor'], required_imports)
          # The width used to be interpolated raw and suffixed with `.dp` at
          # each use site — the canonical example of an emit that stops being
          # a program once the width is bound. BoundValue returns the whole Dp
          # expression, so the `.dp` moved inside it.
          border_width = BoundValue.dp(json_data['borderWidth'])
          border_style = json_data['borderStyle'] || 'solid'
          if json_data['cornerRadius']
            border_shape = "RoundedCornerShape(#{BoundValue.dp(json_data['cornerRadius'])})"
          else
            # `RectangleShape` is in `androidx.compose.ui.graphics`, NOT the
            # `androidx.compose.foundation.shape` namespace covered by
            # `:shape`. Register a separate import key so the generated
            # file actually resolves the reference.
            required_imports&.add(:rectangle_shape)
            border_shape = "RectangleShape"
          end

          case border_style
          when 'dashed'
            required_imports&.add(:dashed_border)
            ".dashedBorder(#{border_width}, #{border_color}, #{border_shape})"
          when 'dotted'
            required_imports&.add(:dashed_border)
            ".dottedBorder(#{border_width}, #{border_color}, #{border_shape})"
          else # 'solid' or default
            ".border(#{border_width}, #{border_color}, #{border_shape})"
          end
        end

        # Process dimension value - handles data bindings and numeric values.
        #
        # This used to own its own binding branch (`data.#{$1}.dp`), which
        # passed a `??` default through verbatim (`@{w ?? 10}` →
        # `data.w ?? 10.dp`) and dereferenced nullable properties. It is a thin
        # wrapper over BoundValue now — the only remaining job is the
        # matchParent/wrapContent guard and the "absent means 0.dp" contract
        # its callers rely on.
        def self.process_dimension(value)
          if value.is_a?(String) && (value == 'matchParent' || value == 'wrapContent')
            return nil
          end

          BoundValue.dp(value) || '0.dp'
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