# frozen_string_literal: true

require_relative 'binding_expression'
require_relative 'resource_resolver'
require_relative '../../core/normalization'

module KjuiTools
  module Compose
    module Helpers
      # Helper class to build Compose modifiers from JSON attributes
      class ModifierBuilder
        def self.build_padding(json_data)
          modifiers = []
          
          # Handle padding attribute (can be array [top, right, bottom, left] or single value)
          if json_data['padding']
            if json_data['padding'].is_a?(Array)
              pad_values = json_data['padding']
              if pad_values.length == 4
                modifiers << ".padding(top = #{pad_values[0]}.dp, end = #{pad_values[1]}.dp, bottom = #{pad_values[2]}.dp, start = #{pad_values[3]}.dp)"
              elsif pad_values.length == 2
                modifiers << ".padding(vertical = #{pad_values[0]}.dp, horizontal = #{pad_values[1]}.dp)"
              elsif pad_values.length == 1
                modifiers << ".padding(#{pad_values[0]}.dp)"
              end
            else
              modifiers << ".padding(#{json_data['padding']}.dp)"
            end
          end
          
          # Handle paddings attribute (same as padding)
          if json_data['paddings']
            if json_data['paddings'].is_a?(Array)
              pad_values = json_data['paddings']
              if pad_values.length == 4
                modifiers << ".padding(top = #{pad_values[0]}.dp, end = #{pad_values[1]}.dp, bottom = #{pad_values[2]}.dp, start = #{pad_values[3]}.dp)"
              elsif pad_values.length == 2
                modifiers << ".padding(vertical = #{pad_values[0]}.dp, horizontal = #{pad_values[1]}.dp)"
              elsif pad_values.length == 1
                modifiers << ".padding(#{pad_values[0]}.dp)"
              end
            else
              modifiers << ".padding(#{json_data['paddings']}.dp)"
            end
          end
          
          # Individual padding attributes (prefix form: paddingTop, and suffix form: topPadding/leftPadding)
          modifiers << ".padding(top = #{json_data['paddingTop'] || json_data['topPadding']}.dp)" if json_data['paddingTop'] || json_data['topPadding']
          modifiers << ".padding(bottom = #{json_data['paddingBottom'] || json_data['bottomPadding']}.dp)" if json_data['paddingBottom'] || json_data['bottomPadding']
          modifiers << ".padding(start = #{json_data['paddingLeft'] || json_data['leftPadding']}.dp)" if json_data['paddingLeft'] || json_data['leftPadding']
          modifiers << ".padding(end = #{json_data['paddingRight'] || json_data['rightPadding']}.dp)" if json_data['paddingRight'] || json_data['rightPadding']
          
          modifiers
        end
        
        def self.build_margins(json_data)
          modifiers = []

          # Handle margins attribute (can be array [top, right, bottom, left] or single value)
          if json_data['margins']
            if json_data['margins'].is_a?(Array)
              margin_values = json_data['margins']
              if margin_values.length == 4
                modifiers << ".padding(top = #{margin_values[0]}.dp, end = #{margin_values[1]}.dp, bottom = #{margin_values[2]}.dp, start = #{margin_values[3]}.dp)"
              elsif margin_values.length == 1
                modifiers << ".padding(#{margin_values[0]}.dp)"
              end
            else
              modifiers << ".padding(#{json_data['margins']}.dp)"
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

        # Convert margin value to Kotlin/Compose format with binding support
        def self.margin_value(value)
          if is_binding?(value)
            # Data binding: @{propertyName} -> data.propertyName.dp
            property = extract_binding_property(value)
            "data.#{property}.dp"
          else
            "#{value}.dp"
          end
        end
        
        def self.build_weight(json_data, parent_orientation = nil)
          modifiers = []
          
          # Weight only works in Row/Column contexts
          # Weight must be greater than 0 in Compose
          if json_data['weight'] && parent_orientation && json_data['weight'].to_f > 0
            modifiers << ".weight(#{json_data['weight']}f)"
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

        def self.build_size(json_data, parent_type = nil)
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
          if json_data['minWidth'] && json_data['maxWidth']
            modifiers << ".widthIn(min = #{json_data['minWidth']}.dp, max = #{json_data['maxWidth']}.dp)"
          elsif json_data['minWidth']
            modifiers << ".widthIn(min = #{json_data['minWidth']}.dp)"
          elsif json_data['maxWidth']
            modifiers << ".widthIn(max = #{json_data['maxWidth']}.dp)"
          end

          # Width - skip if weight is present and width is 0
          if json_data['width'] == 'matchParent'
            modifiers << ".fillMaxWidth()"
          elsif json_data['width'] == 'wrapContent'
            modifiers << ".wrapContentWidth()"
          elsif json_data['width'] && !(json_data['weight'] && json_data['width'] == 0)
            modifiers << ".width(#{process_dimension(json_data['width'])})"
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
            modifiers << ".defaultMinSize(minHeight = #{json_data['minHeight']}.dp)"
            modifiers << ".wrapContentHeight(align = #{label_valign})"
            valign_emitted = true
            # `maxHeight` (if any) is still applied below as a normal heightIn.
            if json_data['maxHeight']
              modifiers << ".heightIn(max = #{json_data['maxHeight']}.dp)"
            end
          elsif json_data['minHeight'] && json_data['maxHeight']
            modifiers << ".heightIn(min = #{json_data['minHeight']}.dp, max = #{json_data['maxHeight']}.dp)"
          elsif json_data['minHeight']
            modifiers << ".heightIn(min = #{json_data['minHeight']}.dp)"
          elsif json_data['maxHeight']
            modifiers << ".heightIn(max = #{json_data['maxHeight']}.dp)"
          end

          # Height - skip if heightWeight is present and height is 0
          fills_height = false
          if json_data['height'] == 'matchParent'
            modifiers << ".fillMaxHeight()"
            fills_height = true
          elsif json_data['height'] == 'wrapContent'
            modifiers << ".wrapContentHeight()"
          elsif json_data['height'] && !(json_data['heightWeight'] && json_data['height'] == 0)
            modifiers << ".height(#{process_dimension(json_data['height'])})"
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
          
          # Aspect ratio
          if json_data['aspectWidth'] && json_data['aspectHeight']
            ratio = json_data['aspectWidth'].to_f / json_data['aspectHeight'].to_f
            modifiers << ".aspectRatio(#{ratio}f)"
          end
          
          modifiers
        end
        
        def self.build_shadow(json_data, required_imports = nil)
          modifiers = []
          
          if json_data['shadow']
            required_imports&.add(:drop_shadow)

            if json_data['shadow'].is_a?(String)
              required_imports&.add(:rectangle_shape)
              modifiers << ".dropShadow(shape = RectangleShape, shadow = Shadow(radius = 4.dp))"
            elsif json_data['shadow'].is_a?(Hash)
              shadow = json_data['shadow']
              radius = shadow['radius'] || 4
              if json_data['cornerRadius']
                shape = "RoundedCornerShape(#{json_data['cornerRadius']}.dp)"
              else
                required_imports&.add(:rectangle_shape)
                shape = "RectangleShape"
              end
              modifiers << ".dropShadow(shape = #{shape}, shadow = Shadow(radius = #{radius}.dp))"
            end
          end
          
          modifiers
        end
        
        def self.build_background(json_data, required_imports = nil)
          modifiers = []
          
          if json_data['background']
            required_imports&.add(:background)
            
            # Use ResourceResolver to process background color
            background_color = ResourceResolver.process_color(json_data['background'], required_imports)
            
            if json_data['cornerRadius'] || json_data['borderColor'] || json_data['borderWidth']
              required_imports&.add(:border)
              required_imports&.add(:shape)

              # border before clip to prevent border being clipped
              if json_data['borderColor'] && json_data['borderWidth']
                modifiers << build_border_modifier(json_data, required_imports)
              end

              if json_data['cornerRadius']
                modifiers << ".clip(RoundedCornerShape(#{json_data['cornerRadius']}.dp))"
              end

              modifiers << ".background(#{background_color})"
            else
              modifiers << ".background(#{background_color})"
            end
          elsif json_data['cornerRadius'] || json_data['borderColor'] || json_data['borderWidth']
            required_imports&.add(:border)
            required_imports&.add(:shape)

            # border before clip
            if json_data['borderColor'] && json_data['borderWidth']
              modifiers << build_border_modifier(json_data, required_imports)
            end

            if json_data['cornerRadius']
              modifiers << ".clip(RoundedCornerShape(#{json_data['cornerRadius']}.dp))"
            end
          end

          # clipToBounds
          if json_data['clipToBounds']
            required_imports&.add(:shape)
            modifiers << ".clipToBounds()"
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
            if alpha_value.is_a?(String) && (inner = BindingExpression.extract_inner(alpha_value))
              modifiers << ".alpha(#{BindingExpression.value_access(inner)}.toFloat())"
            else
              modifiers << ".alpha(#{alpha_value}f)"
            end
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
            if alpha_value.is_a?(String) && (inner = BindingExpression.extract_inner(alpha_value))
              modifiers << ".alpha(#{BindingExpression.value_access(inner)}.toFloat())"
            else
              modifiers << ".alpha(#{alpha_value}f)"
            end
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
          handler = json_data['onclick'] || json_data['onClick']
          enabled = enabled_expression(json_data)
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
            gate = enabled ? "(enabled = #{enabled})" : ''
            modifiers << ".clickable#{gate} { #{handler_call} }"
          end
          modifiers.concat(build_disabled_semantics(json_data, enabled, required_imports))
          modifiers
        end

        # `enabled` — declared boolean|binding on `common`, so it may appear on
        # any node, and the Compose codegen read it on none of them: a View with
        # `enabled: "@{x}"` stayed clickable. Returns the Kotlin boolean
        # expression, or nil when the attribute is absent or literally true
        # (which is the default and needs no gate).
        def self.enabled_expression(json_data)
          value = json_data['enabled']
          return nil if value.nil? || value == true || value == 'true'
          return 'false' if value == false || value == 'false'
          return nil unless is_binding?(value)

          "data.#{extract_binding_property(value)}"
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

        def self.build_alignment(json_data, required_imports = nil, parent_type = nil)
          modifiers = []

          # Scope-free emit context (no surrounding RowScope/ColumnScope/BoxScope).
          # Used by the file-scope responsive helper composables (see
          # compose_builder#generate_responsive_container) — Modifier.align(...)
          # is a *Scope-receiver-bound* extension, so it doesn't resolve here.
          # Translate centering to scope-independent equivalents.
          if parent_type == 'ScopeFree'
            if json_data['centerInParent']
              modifiers << ".wrapContentWidth(Alignment.CenterHorizontally)"
              modifiers << ".wrapContentHeight(Alignment.CenterVertically)"
            else
              # Horizontal axis. centerHorizontal beats align-left/right; the
              # align-both case (left AND right) collapses to center to match
              # the SwiftUI side and the original Android XML semantics.
              if json_data['centerHorizontal']
                modifiers << ".wrapContentWidth(Alignment.CenterHorizontally)"
              elsif json_data['alignLeft'] && json_data['alignRight']
                modifiers << ".wrapContentWidth(Alignment.CenterHorizontally)"
              elsif json_data['alignLeft']
                modifiers << ".wrapContentWidth(Alignment.Start)"
              elsif json_data['alignRight']
                modifiers << ".wrapContentWidth(Alignment.End)"
              end
              # Vertical axis. Same precedence.
              if json_data['centerVertical']
                modifiers << ".wrapContentHeight(Alignment.CenterVertically)"
              elsif json_data['alignTop'] && json_data['alignBottom']
                modifiers << ".wrapContentHeight(Alignment.CenterVertically)"
              elsif json_data['alignTop']
                modifiers << ".wrapContentHeight(Alignment.Top)"
              elsif json_data['alignBottom']
                modifiers << ".wrapContentHeight(Alignment.Bottom)"
              end
            end
            return modifiers
          end

          # For Row, only vertical alignment is allowed
          if parent_type == 'Row'
            if json_data['alignTop']
              modifiers << ".align(Alignment.Top)"
            elsif json_data['alignBottom']
              modifiers << ".align(Alignment.Bottom)"
            elsif json_data['centerVertical']
              modifiers << ".align(Alignment.CenterVertically)"
            end
          # For Column, only horizontal alignment is allowed
          elsif parent_type == 'Column'
            if json_data['alignLeft']
              modifiers << ".align(Alignment.Start)"
            elsif json_data['alignRight']
              modifiers << ".align(Alignment.End)"
            elsif json_data['centerHorizontal']
              modifiers << ".align(Alignment.CenterHorizontally)"
            end
          # For Box and other containers, full alignment options
          elsif parent_type == 'Box'
            # Check if any alignment is specified
            has_alignment = json_data['alignTop'] || json_data['alignBottom'] || 
                          json_data['alignLeft'] || json_data['alignRight'] || 
                          json_data['centerHorizontal'] || json_data['centerVertical'] || 
                          json_data['centerInParent']
            
            # First check for both-direction constraints (centering behavior)
            has_horizontal_both = json_data['alignLeft'] && json_data['alignRight']
            has_vertical_both = json_data['alignTop'] && json_data['alignBottom']
            
            # Handle combined alignments
            if has_horizontal_both && has_vertical_both
              # Both horizontal and vertical constraints - center completely
              modifiers << ".align(Alignment.Center)"
            elsif has_horizontal_both && json_data['alignTop']
              # Center horizontally, align top
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(0f, -1f))"
            elsif has_horizontal_both && json_data['alignBottom']
              # Center horizontally, align bottom
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(0f, 1f))"
            elsif has_horizontal_both
              # Just center horizontally
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(0f, 0f))"
            elsif has_vertical_both && json_data['alignLeft']
              # Center vertically, align left
              modifiers << ".align(Alignment.CenterStart)"
            elsif has_vertical_both && json_data['alignRight']
              # Center vertically, align right
              modifiers << ".align(Alignment.CenterEnd)"
            elsif has_vertical_both
              # Just center vertically
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(0f, 0f))"
            elsif json_data['alignTop'] && json_data['alignLeft']
              modifiers << ".align(Alignment.TopStart)"
            elsif json_data['alignTop'] && json_data['alignRight']
              modifiers << ".align(Alignment.TopEnd)"
            elsif json_data['alignBottom'] && json_data['alignLeft']
              modifiers << ".align(Alignment.BottomStart)"
            elsif json_data['alignBottom'] && json_data['alignRight']
              modifiers << ".align(Alignment.BottomEnd)"
            elsif json_data['alignTop'] && json_data['centerHorizontal']
              # TopCenter doesn't exist in BoxScope, use BiasAlignment
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(0f, -1f))"
            elsif json_data['alignBottom'] && json_data['centerHorizontal']
              # BottomCenter doesn't exist in BoxScope, use BiasAlignment
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(0f, 1f))"
            elsif json_data['alignLeft'] && json_data['centerVertical']
              modifiers << ".align(Alignment.CenterStart)"
            elsif json_data['alignRight'] && json_data['centerVertical']
              modifiers << ".align(Alignment.CenterEnd)"
            elsif json_data['centerInParent']
              modifiers << ".align(Alignment.Center)"
            # Handle single alignments for Box
            elsif json_data['alignTop']
              # Just top alignment - align to top-left
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(-1f, -1f))"
            elsif json_data['alignBottom']
              # Just bottom alignment - align to bottom-left
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(-1f, 1f))"
            elsif json_data['alignLeft']
              # Just left alignment - align to top-left
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(-1f, -1f))"
            elsif json_data['alignRight']
              # Just right alignment - align to top-right
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(1f, -1f))"
            elsif json_data['centerHorizontal']
              # Center horizontally only - align to top-center
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(0f, -1f))"
            elsif json_data['centerVertical']
              # Center vertically only - align to center-left
              required_imports&.add(:bias_alignment)
              modifiers << ".align(BiasAlignment(-1f, 0f))"
            end
            # No default TopStart - let parent's contentAlignment handle it
          end
          
          modifiers
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
            elsif value_expr && class_type.match?(/\(\s*\(?\s*(Bool|Boolean|Int|Float|Double|Number)\s*\)?\s*\)\s*->/)
              # Handler takes a single typed argument (e.g., (Bool) -> Void)
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
            # Data binding: @{propertyName} -> data.propertyName.dp
            property = extract_binding_property(value)
            "data.#{property}.dp"
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
          border_color = ResourceResolver.process_color(json_data['borderColor'], required_imports)
          border_width = json_data['borderWidth']
          border_style = json_data['borderStyle'] || 'solid'
          if json_data['cornerRadius']
            border_shape = "RoundedCornerShape(#{json_data['cornerRadius']}.dp)"
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
            ".dashedBorder(#{border_width}.dp, #{border_color}, #{border_shape})"
          when 'dotted'
            required_imports&.add(:dashed_border)
            ".dottedBorder(#{border_width}.dp, #{border_color}, #{border_shape})"
          else # 'solid' or default
            ".border(#{border_width}.dp, #{border_color}, #{border_shape})"
          end
        end

        # Process dimension value - handles data bindings and numeric values
        def self.process_dimension(value)
          return "#{value}.dp" if value.is_a?(Numeric)

          if value.is_a?(String)
            # Guard: matchParent/wrapContent should not reach here, but handle gracefully
            return nil if value == 'matchParent' || value == 'wrapContent'

            # Check for data binding syntax @{variableName}
            if value.match(/@\{([^}]+)\}/)
              variable = $1
              # Data binding returns Int/Float from ViewModel, append .dp
              return "data.#{variable}.dp"
            end
            # Regular string value (might be percentage or other)
            return "#{value}.dp"
          end

          "0.dp"
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