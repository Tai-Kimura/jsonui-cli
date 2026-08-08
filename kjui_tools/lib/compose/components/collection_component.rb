# frozen_string_literal: true

require_relative '../helpers/content_inset_helper'
require_relative '../helpers/modifier_builder'
require_relative '../../core/normalization'

module KjuiTools
  module Compose
    module Components
      class CollectionComponent

        # defaultScrollAnchor — "Initial scroll position anchor. Sets where the
        # scroll view starts." Compose has no equivalent of SwiftUI's
        # `.defaultScrollAnchor`, and `reverseLayout` is not one: it flips the
        # item order as well. So it is a one-shot scroll instead.
        #
        # Keyed on the item count rather than Unit because the list is usually
        # empty on first composition (the data arrives async) and an anchor
        # applied to an empty list does nothing. The remembered flag is what
        # stops a later append from yanking the user back.
        def self.default_scroll_anchor_code(json_data, state_var, depth, required_imports)
          anchor = json_data['defaultScrollAnchor']
          return '' unless %w[center bottom].include?(anchor.to_s)

          items_property = json_data['items']
          match = items_property.is_a?(String) ? items_property.match(/@\{([^}]+)\}/) : nil
          return '' unless match

          required_imports&.add(:remember_state)
          required_imports&.add(:launched_effect)

          target = anchor.to_s == 'center' ? 'defaultAnchorCount / 2' : 'defaultAnchorCount - 1'
          code = indent("val defaultAnchorCount = data.#{match[1]}?.sections?.firstOrNull()?.cells?.data?.size ?: 0", depth) + "\n"
          code += indent("val defaultAnchorApplied = remember { mutableStateOf(false) }", depth) + "\n"
          code += indent("LaunchedEffect(defaultAnchorCount) {", depth) + "\n"
          code += indent("if (!defaultAnchorApplied.value && defaultAnchorCount > 0) {", depth + 1) + "\n"
          code += indent("#{state_var}.scrollToItem(#{target})", depth + 2) + "\n"
          code += indent("defaultAnchorApplied.value = true", depth + 2) + "\n"
          code += indent("}", depth + 1) + "\n"
          code += indent("}", depth) + "\n"
          code
        end

        # `scrollTo` carries an index, and the data section may declare it as
        # a String or a number — E has it open as "no class compiles on all
        # three platforms at once". The emit used to assume String and call
        # `isEmpty` / `substringBefore` straight on the property, so a numeric
        # declaration produced a view that does not compile. `?.toString()
        # .orEmpty()` reads the same for either, and for a nullable one too.
        # Same family as the `Int.lowercase()` this lane hit on fontWeight: a
        # binding spelling carries no type (plan 49 lane C).
        # `scrollAnchor` decides WHERE the scrollTo target lands in the
        # viewport. kjui read the attribute into a local (line ~289) and then
        # used it nowhere — neither the grid path nor the stack path (plan 49
        # lane C, handed over from D). sjui expresses it as
        # `scrollProxy.scrollTo(i, anchor: .center)`; Compose's equivalent is
        # the second parameter of `animateScrollToItem`, which positions the
        # item relative to the viewport start (a NEGATIVE offset pushes it
        # down, so `center` is half a viewport and `bottom` a full one).
        #
        # Emitted only when the attribute is EXPLICITLY declared. The SSoT
        # says the default is `bottom`, but every existing Compose layout has
        # been scrolling to the top since this path was written, so applying
        # the documented default here would silently move real screens. That
        # discrepancy is a finding for the SSoT lane, not something to close
        # by changing behaviour under existing consumers.
        # The declared default, in ONE place. It used to be written only in the
        # grid path — a dead local `json_data['scrollAnchor'] || 'bottom'` that
        # nothing read — while the stack/list path had no default at all, so
        # the same component carried two different answers for the same
        # question (plan 49 lane C; E measured ios / web / Compose grid at
        # `bottom` and Compose list at `top`, making list the lone outlier).
        # The declared default, in ONE place, and actually applied.
        #
        # It used to be written only in the grid path — a dead local
        # `json_data['scrollAnchor'] || 'bottom'` that nothing read — while the
        # stack/list path had no default at all. Measured on both paths: with
        # no `scrollAnchor` declared, BOTH emitted a bare
        # `animateScrollToItem(index)`, i.e. both landed at the TOP. So the two
        # paths did not disagree with each other; together they disagreed with
        # everyone else:
        #
        #   ios   bottom   sjui collection_converter.rb:1138
        #   web   bottom   rjui react_generator.rb:768
        #   SSoT  bottom   Collection.scrollAnchor "default"
        #   kjui  top      <- the outlier, on both paths
        #
        # Three against one, so the outlier moves. This IS a behaviour change
        # for existing Compose screens that scroll programmatically — they have
        # been landing at the top — and it is the correct one: those screens
        # have been drawing a different picture from their iOS and web
        # counterparts the whole time (plan 49 lane C, orchestrator ruling
        # 2026-08-05; goes in the v1.4.1 release notes).
        DEFAULT_SCROLL_ANCHOR = 'bottom'

        def self.scroll_anchor_offset_code(json_data, state_var, depth)
          # Both paths come through this one gate, so neither can drift from
          # the other, and the declared default applies when the attribute is
          # absent — see DEFAULT_SCROLL_ANCHOR for why that is a deliberate
          # behaviour change rather than an oversight.
          anchor = (json_data['scrollAnchor'] || DEFAULT_SCROLL_ANCHOR).to_s
          return ['', ''] unless %w[center bottom].include?(anchor)

          viewport = "(#{state_var}.layoutInfo.viewportEndOffset - #{state_var}.layoutInfo.viewportStartOffset)"
          offset = anchor == 'center' ? "-(#{viewport} / 2)" : "-#{viewport}"
          [indent("val scrollAnchorOffset = #{offset}", depth + 1) + "\n", ', scrollAnchorOffset']
        end

        def self.default_scroll_anchor?(json_data)
          return false unless %w[center bottom].include?(json_data['defaultScrollAnchor'].to_s)

          json_data['items'].is_a?(String) && json_data['items'].match?(/@\{[^}]+\}/)
        end

        # The listStyle chrome around one cell (51-E) — the generated code
        # emits the SAME library composable the dynamic path renders
        # (CollectionCellChrome). plain/unknown emit nothing; flow/paging
        # routes stay plain, mirroring the dynamic scope.
        def self.chrome_open(json_data, required_imports)
          style = json_data['listStyle'].to_s
          return nil unless %w[grouped insetgrouped sidebar].include?(style.downcase)

          required_imports&.add(:collection_cell_chrome)
          hide = json_data['hideSeparator'] == true
          "CollectionCellChrome(style = \"#{style}\", hideSeparator = #{hide}) {"
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # Registered here, before the routing: `generate` forks into the
          # grid emitter and the CollectionStack emitter, and the inset can
          # come out of either. Registering inside one of them is how half a
          # feature ships (plan 49 lane C, #4).
          Helpers::ContentInsetHelper.imports_for(json_data['contentInsetAdjustmentBehavior'])
                                     .each { |k| required_imports&.add(k) }

          # Check if sections are defined
          sections = json_data['sections'] || []
          # Support both 'layout' and 'orientation' attributes for horizontal/vertical/flow.
          # `horizontalScroll: true` is ScrollView's boolean spelling of the
          # same direction fact — real carousels were measured using it here.
          layout = json_data['layout'] || json_data['orientation'] || 'vertical'
          layout = 'horizontal' if json_data['horizontalScroll'] == true
          is_horizontal = layout == 'horizontal'
          # Case-insensitive: the declared enum admits 'Flow' as well as
          # 'flow', and the dynamic path sees the value AFTER the runtime
          # normalizer downcases it — reading it raw here rendered 'Flow'
          # as a vertical stack while dynamic wrapped it (parity d=32).
          # 'leftAligned' is an alias spelling of flow (SSoT valueAliases,
          # 2026-08-03 unification) — dynamic folds it via the generated
          # enum, so the raw-reading codegen must accept it too.
          is_flow = %w[flow leftaligned].include?(layout.to_s.downcase)

          # lazy: "none" → emit Row/Column + forEachIndexed, no LazyColumn/LazyVerticalGrid
          # and no verticalScroll/horizontalScroll. Intended for Collections nested
          # inside an already-scrollable parent. Paging still wins (HorizontalPager is
          # inherently lazy but supports the core use case); flow is already non-lazy.
          lazy = json_data['lazy'] != 'none'

          # FlowLayout uses FlowRow instead of LazyGrid (FlowRow itself is non-lazy)
          if is_flow
            return generate_flow_layout(json_data, sections, depth, required_imports, parent_type)
          end

          # Paging horizontal uses HorizontalPager instead of LazyHorizontalGrid
          if is_horizontal && json_data['paging'] == true
            return generate_paging_horizontal(json_data, sections, depth, required_imports, parent_type)
          end

          # lazy: "none" explicitly selects non-lazy rendering
          if !lazy
            if is_horizontal
              return generate_non_lazy_row(json_data, sections, depth, required_imports, parent_type)
            else
              return generate_non_lazy(json_data, sections, depth, required_imports, parent_type)
            end
          end

          # wrapContent height on vertical Collection → use Column instead of LazyVerticalGrid
          # to avoid crash when nested inside another LazyVerticalGrid (infinite height constraint).
          height_value = json_data['height']
          if !is_horizontal && height_value == 'wrapContent'
            return generate_non_lazy(json_data, sections, depth, required_imports, parent_type)
          end

          # Single-column section-based collections route through CollectionStack
          # so the outer container choice (lazy/eager/none) becomes a parameter
          # instead of branching the generator. Multi-column grids fall through
          # to the existing LazyVerticalGrid / LazyHorizontalGrid path.
          if sections.any? && single_column_sections?(sections, json_data)
            return generate_collection_stack(json_data, sections, depth, required_imports, parent_type, is_horizontal: is_horizontal)
          end

          required_imports&.add(:lazy_grid)
          required_imports&.add(:grid_item_span)
          required_imports&.add(:launched_effect)
          
          # Legacy: Extract cellClasses, headerClasses, footerClasses (string arrays)
          cell_classes = json_data['cellClasses'] || []
          header_classes = json_data['headerClasses'] || []
          footer_classes = json_data['footerClasses'] || []
          
          # Use the class names directly
          cell_class_name = cell_classes.first if cell_classes.any?
          header_class_name = header_classes.first if header_classes.any?
          footer_class_name = footer_classes.first if footer_classes.any?
          
          # Resolve the grid column count. The top-level `columns` attribute
          # accepts either a literal Int or a `@{prop}` binding (see
          # attribute_definitions.json#columns). For a binding we forfeit
          # any compile-time LCM with per-section overrides — the runtime
          # column count is unknown — and the grid count is just the
          # resolved binding expression. Per-section `columns` overrides
          # still emit `GridItemSpan` spans against this grid below; that
          # span math runs against the literal section value, so a section
          # explicitly setting `columns: 1` inside a binding-driven grid
          # still spans 1 cell wide regardless of total column count.
          columns_info = columns_emit_info(json_data)
          columns_expr = columns_info[:expr]
          if columns_info[:is_binding]
            # Sentinel: any value > 1 makes the downstream `columns > 1`
            # checks emit the grid-mode cell modifiers (fillMaxWidth on
            # cells). Compile-time LCM with section-level overrides is
            # disabled because the runtime column count is unknown.
            columns = 2
          elsif sections.any?
            default_columns = columns_info[:literal] || 1
            section_columns = sections.map { |s| s['columns'] || default_columns }.uniq
            columns = section_columns.size > 1 ? calculate_lcm(section_columns) : section_columns.first
            columns_expr = columns.to_s
          else
            columns = columns_info[:literal] || 1
            columns_expr = columns.to_s
          end
          
          # Determine grid type based on layout
          direction = is_horizontal ? 'horizontal' : 'vertical'
          
          if direction == 'horizontal'
            code = indent("LazyHorizontalGrid(", depth)
            code += "\n" + indent("rows = GridCells.Fixed(#{columns_expr}),", depth + 1)
          else
            code = indent("LazyVerticalGrid(", depth)
            code += "\n" + indent("columns = GridCells.Fixed(#{columns_expr}),", depth + 1)
          end

          # Reverse layout
          if json_data['reverseLayout'] == true
            code += "\n" + indent("reverseLayout = true,", depth + 1)
          end

          # scrollEnabled - controls whether the user can scroll
          if json_data.key?('scrollEnabled')
            scroll_enabled = json_data['scrollEnabled']
            if scroll_enabled.is_a?(String) && scroll_enabled.match(/@\{([^}]+)\}/)
              # Data binding
              prop = $1
              code += "\n" + indent("userScrollEnabled = data.#{prop},", depth + 1)
            else
              code += "\n" + indent("userScrollEnabled = #{scroll_enabled},", depth + 1)
            end
          end

          # Content padding
          # Support contentPadding, insets (array or number), insetHorizontal, insetVertical
          content_padding = json_data['contentPadding'] || json_data['insets']
          inset_horizontal = json_data['insetHorizontal']
          inset_vertical = json_data['insetVertical']

          if content_padding
            if content_padding.is_a?(Array) && content_padding.length == 4
              code += "\n" + indent("contentPadding = PaddingValues(top = #{content_padding[0]}.dp, start = #{content_padding[1]}.dp, bottom = #{content_padding[2]}.dp, end = #{content_padding[3]}.dp),", depth + 1)
            elsif content_padding.is_a?(Numeric)
              code += "\n" + indent("contentPadding = PaddingValues(#{content_padding}.dp),", depth + 1)
            end
          elsif inset_horizontal || inset_vertical
            # Use insetHorizontal and/or insetVertical
            h_inset = inset_horizontal || 0
            v_inset = inset_vertical || 0
            code += "\n" + indent("contentPadding = PaddingValues(horizontal = #{h_inset}.dp, vertical = #{v_inset}.dp),", depth + 1)
          elsif (safe_inset = Helpers::ContentInsetHelper.safe_area_padding(
                   json_data['contentInsetAdjustmentBehavior'], horizontal: is_horizontal))
            # A DECLARED numeric contentPadding/insets wins: the author named
            # an exact value, and this attribute only says "clear the system
            # bars" — it cannot also mean "and discard the number I wrote".
            # `never` emits nothing, which is Compose's own default, so
            # existing screens do not move (plan 49 lane C, #4).
            code += "\n" + indent("contentPadding = #{safe_inset},", depth + 1)
          end
          
          # Item spacing
          # lineSpacing: vertical spacing between rows (minimumLineSpacing in iOS)
          # columnSpacing: horizontal spacing between columns (minimumInteritemSpacing in iOS)
          # itemSpacing/spacing: uniform spacing (fallback)
          line_spacing = json_data['lineSpacing'] || json_data['itemSpacing'] || json_data['spacing']
          column_spacing = json_data['columnSpacing'] || json_data['itemSpacing'] || json_data['spacing']

          if line_spacing || column_spacing
            required_imports&.add(:arrangement)
            if is_horizontal
              # Horizontal scroll: both lineSpacing and columnSpacing map to
              # horizontalArrangement (item spacing along scroll direction).
              # For single-row horizontal grids, verticalArrangement is not needed.
              h_spacing = line_spacing || column_spacing
              code += "\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{h_spacing}.dp),", depth + 1)
            else
              # Vertical scroll: lineSpacing = vertical spacing between rows,
              # columnSpacing = horizontal spacing between columns
              if line_spacing
                code += "\n" + indent("verticalArrangement = Arrangement.spacedBy(#{line_spacing}.dp),", depth + 1)
              end
              if column_spacing
                code += "\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{column_spacing}.dp),", depth + 1)
              end
            end
          end

          # Parse gravity for item alignment (Box contentAlignment uses Alignment, not Alignment.Vertical/Horizontal)
          # Horizontal scroll: default is TopStart, can be Center/BottomStart
          # Vertical scroll: default is TopStart, can be TopCenter/TopEnd
          gravity = json_data['gravity']
          if is_horizontal
            # Horizontal scroll - vertical alignment
            gravity_alignment = case gravity.to_s.downcase
            when 'center', 'centervertical'
              'Alignment.CenterStart'
            when 'bottom'
              'Alignment.BottomStart'
            else # 'top' is default for horizontal scroll
              'Alignment.TopStart'
            end
          else
            # Vertical scroll - horizontal alignment
            gravity_alignment = case gravity.to_s.downcase
            when 'center', 'centerhorizontal'
              'Alignment.TopCenter'
            when 'right'
              'Alignment.TopEnd'
            else # 'left' is default for vertical scroll
              'Alignment.TopStart'
            end
          end
          
          # Build modifiers
          modifiers = []

          # Add testTag and contentDescription for UI testing
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          # 1. Margins first (outer spacing)
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

          # 2. Size - IMPORTANT: LazyVerticalGrid requires bounded width from parent
          # LazyHorizontalGrid requires bounded height from parent
          # If width/height is wrapContent, we MUST change it to avoid runtime crash
          width_value = json_data['width']
          height_value = json_data['height']

          if !is_horizontal && width_value == 'wrapContent'
            modified_json = json_data.merge('width' => 'matchParent')
            modifiers.concat(Helpers::ModifierBuilder.build_size(modified_json, parent_type, required_imports))
          elsif is_horizontal && height_value == 'wrapContent'
            modified_json = json_data.merge('height' => 'matchParent')
            modifiers.concat(Helpers::ModifierBuilder.build_size(modified_json, parent_type, required_imports))
          else
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          end

          # 3. Alpha + Background (clip + background)
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          # 4. Padding last (inner spacing)
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # onItemAppear support - callback with index when cell appears
          if json_data['onItemAppear'] && json_data['onItemAppear'].match(/@\{([^}]+)\}/)
            required_imports&.add(:launched_effect)
          end

          # scrollTo support - add LazyGridState
          scroll_to = json_data['scrollTo']
          cell_id_property = json_data['cellIdProperty']
          has_scroll_to = scroll_to && scroll_to.match(/@\{([^}]+)\}/)

          has_default_anchor = default_scroll_anchor?(json_data)
          needs_grid_state = has_scroll_to || has_default_anchor

          if has_scroll_to
            required_imports&.add(:lazy_grid_state)
            required_imports&.add(:launched_effect)
            scroll_prop = $1

            # Check for scrollAnimated binding
            scroll_animated = json_data['scrollAnimated']
            has_animated_binding = scroll_animated && scroll_animated.to_s.match(/@\{([^}]+)\}/)
            animated_prop = has_animated_binding ? $1 : nil

            scroll_code = indent("val gridState = rememberLazyGridState()", depth) + "\n" +
                          indent("// Programmatic scrolling", depth) + "\n" +
                          indent("LaunchedEffect(data.#{scroll_prop}) {", depth) + "\n" +
                          indent("val raw = data.#{scroll_prop}?.toString().orEmpty()", depth + 1) + "\n" +
                          indent("if (raw.isEmpty()) return@LaunchedEffect", depth + 1) + "\n" +
                          indent("val index = raw.substringBefore(\"#\").toIntOrNull() ?: return@LaunchedEffect", depth + 1) + "\n"

            anchor_decl, anchor_arg = scroll_anchor_offset_code(json_data, 'gridState', depth)
            scroll_code += anchor_decl
            if animated_prop
              scroll_code += indent("if (index >= 0) {", depth + 1) + "\n" +
                             indent("if (data.#{animated_prop}) {", depth + 2) + "\n" +
                             indent("gridState.animateScrollToItem(index#{anchor_arg})", depth + 3) + "\n" +
                             indent("} else {", depth + 2) + "\n" +
                             indent("gridState.scrollToItem(index#{anchor_arg})", depth + 3) + "\n" +
                             indent("}", depth + 2) + "\n" +
                             indent("}", depth + 1) + "\n"
            else
              scroll_code += indent("if (index >= 0) gridState.animateScrollToItem(index#{anchor_arg})", depth + 1) + "\n"
            end

            scroll_code += indent("}", depth) + "\n"
            scroll_code += default_scroll_anchor_code(json_data, 'gridState', depth, required_imports)
            code = scroll_code + code
          elsif has_default_anchor
            required_imports&.add(:lazy_grid_state)
            code = indent("val gridState = rememberLazyGridState()", depth) + "\n" +
                   default_scroll_anchor_code(json_data, 'gridState', depth, required_imports) +
                   code
          end

          # Hoist remember() for autoChangeTrackingId OUT of the LazyXxx body,
          # because LazyGridScope/LazyListScope content lambdas are not
          # @Composable and remember cannot be called there. We compute
          # per-section enriched data here (in the enclosing @Composable scope)
          # and reference it inside the grid body via section<N> / enrichedData<N>.
          hoist_cell_id_prop = json_data['cellIdProperty']
          hoist_auto_tracking = json_data['autoChangeTrackingId'] == true
          if hoist_auto_tracking && hoist_cell_id_prop && sections.any?
            hoist_items_property = json_data['items']
            if hoist_items_property && hoist_items_property.match(/@\{([^}]+)\}/)
              hoist_property_name = $1
              required_imports&.add(:remember_state)
              enrichment_hoist = ''
              sections.each_with_index do |sec, idx|
                next unless sec['cell']
                enrichment_hoist += indent("val section#{idx} = data.#{hoist_property_name}?.sections?.getOrNull(#{idx})", depth) + "\n"
                enrichment_hoist += indent("val cellData#{idx} = section#{idx}?.cells", depth) + "\n"
                enrichment_hoist += indent("val enrichedData#{idx} = if (cellData#{idx} != null) remember(cellData#{idx}.data) { com.kotlinjsonui.utils.CellIdGenerator.enrichCellIds(cellData#{idx}.data, \"#{hoist_cell_id_prop}\") } else null", depth) + "\n"
              end
              code = enrichment_hoist + code
            end
          end

          # Container-level listStyle chrome: an EMPTY collection must still
          # discriminate the four values (the conformance probes carry no
          # cells), the way an empty ios List still shows its style's
          # background. Emitted after the declared background so the chrome
          # surface reads as the list's inner chrome; the per-cell wrap
          # handles populated lists.
          chrome_style = json_data['listStyle'].to_s.downcase
          if %w[grouped insetgrouped sidebar].include?(chrome_style)
            required_imports&.add(:shape)
            required_imports&.add(:material_theme)
            if %w[insetgrouped sidebar].include?(chrome_style)
              modifiers << ".padding(horizontal = 16.dp)"
              corner = chrome_style == 'insetgrouped' ? 12 : 8
              modifiers << ".clip(RoundedCornerShape(#{corner}.dp))"
            end
            surface = chrome_style == 'sidebar' ? 'surfaceContainerLow' : 'surfaceContainer'
            modifiers << ".background(MaterialTheme.colorScheme.#{surface})"
          end

          code += Helpers::ModifierBuilder.format(modifiers, depth)

          # Add state parameter if scrollTo or defaultScrollAnchor needs one
          if needs_grid_state
            code += ",\n" + indent("state = gridState", depth + 1)
          end

          code += "\n" + indent(") {", depth)
          
          # Check if sections are defined
          if sections.any?
            # Generate section-based collection
            code += generate_sections_content(json_data, sections, columns, depth, required_imports, gravity_alignment)
          elsif cell_class_name
            # Check if items property is specified (e.g., "@{items}")
            items_property = json_data['items']
            
            if items_property && items_property.match(/@\{([^}]+)\}/)
              # Extract property name from @{propertyName}
              property_name = $1
              
              # Items should be a Map<String, List<Any>> where key is cell class name
              # Get the items for this specific cell class
              code += "\n" + indent("// Collection with data source: #{property_name}[\"#{cell_class_name}\"]", depth + 1)
              code += "\n" + indent("val cellItems = data.#{property_name}?.get(\"#{cell_class_name}\") ?: emptyList()", depth + 1)
              code += "\n" + indent("items(cellItems.size) { index ->", depth + 1)
              code += "\n" + indent("val item = cellItems[index]", depth + 2)
            else
              # Default to empty list
              code += "\n" + indent("// Collection with no data source", depth + 1)
              code += "\n" + indent("items(0) { index ->", depth + 1)
              code += "\n" + indent("// No items", depth + 2)
            end
            
            # Create cell view with data
            if (nonsection_chrome = chrome_open(json_data, required_imports))
              code += "\n" + indent(nonsection_chrome, depth + 2)
            end
            code += "\n" + indent("when (val itemData = item) {", depth + 2)
            code += "\n" + indent("is #{cell_class_name}Data -> {", depth + 3)
            code += "\n" + indent("#{cell_class_name}View(", depth + 4)
            code += "\n" + indent("data = itemData,", depth + 5)
            code += "\n" + indent("viewModel = viewModel(),", depth + 5)
            # Add testTag for test automation (tapItem action)
            if json_data['id']
              code += "\n" + indent("modifier = Modifier.testTag(\"#{json_data['id']}_item_\$index\")", depth + 5)
            else
              code += "\n" + indent("modifier = Modifier", depth + 5)
            end

            # Cell-specific modifiers
            if json_data['cellHeight']
              code += "\n" + indent("    .height(#{json_data['cellHeight']}.dp)", depth + 5)
            end

            # For grid layouts, ensure cells expand to fill width
            if columns > 1
              code += "\n" + indent("    .fillMaxWidth()", depth + 5)
            end

            code += "\n" + indent(")", depth + 4)
            code += "\n" + indent("}", depth + 3)
            code += "\n" + indent("is Map<*, *> -> {", depth + 3)
            code += "\n" + indent("// Convert map to data class", depth + 4)
            code += "\n" + indent("val data = #{cell_class_name}Data.fromMap(itemData as Map<String, Any>)", depth + 4)
            code += "\n" + indent("#{cell_class_name}View(", depth + 4)
            code += "\n" + indent("data = data,", depth + 5)
            code += "\n" + indent("viewModel = viewModel(),", depth + 5)
            # Add testTag for test automation (tapItem action)
            if json_data['id']
              code += "\n" + indent("modifier = Modifier.testTag(\"#{json_data['id']}_item_\$index\")", depth + 5)
            else
              code += "\n" + indent("modifier = Modifier", depth + 5)
            end

            # Cell-specific modifiers
            if json_data['cellHeight']
              code += "\n" + indent("    .height(#{json_data['cellHeight']}.dp)", depth + 5)
            end

            # For grid layouts, ensure cells expand to fill width
            if columns > 1
              code += "\n" + indent("    .fillMaxWidth()", depth + 5)
            end

            code += "\n" + indent(")", depth + 4)
            code += "\n" + indent("}", depth + 3)
            code += "\n" + indent("else -> {", depth + 3)
            code += "\n" + indent("// Unsupported item type", depth + 4)
            code += "\n" + indent("}", depth + 3)
            code += "\n" + indent("}", depth + 2)
            if chrome_open(json_data, nil)
              code += "\n" + indent("}", depth + 2)
            end
            code += "\n" + indent("}", depth + 1)
          else
            # Declaration-faithful (2026-08-02 ruling): no cell class
            # declared → nothing rendered (was a 10-item placeholder Card).
            code += "\n" + indent("// No cellClasses — nothing rendered (declaration-faithful)", depth + 1)
          end
          
          code += "\n" + indent("}", depth)
          code
        end
        
        def self.generate_sections_content(json_data, sections, grid_columns, depth, required_imports, gravity_alignment)
          code = ""
          items_property = json_data['items']
          # `columns` may be a literal int or a `@{binding}`. In the binding
          # case `json_data['columns']` is the string `"@{prop}"` and using
          # it as a numeric `default_columns` crashes the LCM / item_span
          # math below ("String can't be coerced into Integer"). Consult
          # `columns_emit_info` exactly like the top-level `generate` path
          # does, and fall back to `grid_columns` (the sentinel set by the
          # caller for the binding case — see `generate`).
          columns_info = columns_emit_info(json_data)
          columns_binding = columns_info[:is_binding]
          default_columns = columns_info[:literal] || grid_columns

          # Check if we need GridItemSpan
          # Need it for headers/footers or when sections have different column counts
          has_headers_or_footers = sections.any? { |s| s['header'] || s['footer'] }
          section_columns_vary = sections.map { |s| s['columns'] || default_columns }.uniq.size > 1
          needs_span = sections.any? { |s| s['columns'] && s['columns'] != grid_columns }
          
          if has_headers_or_footers || section_columns_vary || needs_span
            required_imports&.add(:grid_item_span)
          end

          # Always add cell imports for all sections (regardless of items binding)
          sections.each do |section|
            cell_view_name = section['cell']
            if cell_view_name
              required_imports&.add("cell:#{cell_view_name}")
            end
            if section['header']
              required_imports&.add("cell:#{section['header']}")
            end
            if section['footer']
              required_imports&.add("cell:#{section['footer']}")
            end
          end

          if items_property && items_property.match(/@\{([^}]+)\}/)
            property_name = $1

            # When reverseLayout is true, reverse section order so that
            # JSON definition order matches iOS display (iOS cannot reverse layout)
            reverse_layout = json_data['reverseLayout'] == true
            ordered_sections = reverse_layout ? sections.each_with_index.to_a.reverse : sections.each_with_index.to_a

            # Generate sections with GridItemSpan for different column counts
            cell_id_prop = json_data['cellIdProperty']
            auto_tracking = json_data['autoChangeTrackingId'] == true
            # When auto_tracking + cellIdProperty is set, section<N> /
            # cellData<N> / enrichedData<N> are hoisted BEFORE the LazyXxx
            # opening (see the caller): lazy-scope body lambdas are not
            # @Composable, so remember must live in the enclosing scope.
            use_hoisted = auto_tracking && cell_id_prop

            ordered_sections.each do |(section, index)|
              cell_view_name = section['cell']
              section_columns = section['columns'] || default_columns

              # Calculate the span for items in this section. Under a
              # binding-driven grid the runtime column count is unknown, so
              # the LCM-based span math is meaningless — force span = 1 so
              # each cell occupies one runtime column and we fall through
              # to the `items(size)` branch below. (A literal per-section
              # override under a binding-grid still gets span = 1 here for
              # the same reason; a different span would assume a known
              # grid width.)
              item_span = columns_binding ? 1 : grid_columns / section_columns

              if cell_view_name
                section_var = use_hoisted ? "section#{index}" : 'section'
                cell_data_var = use_hoisted ? "cellData#{index}" : 'cellData'

                # Under a binding-driven grid, the actual column count is
                # resolved at runtime; reflect that in the comment instead
                # of printing the sentinel (~= 2) which would be misleading.
                section_columns_comment = columns_binding && !section['columns'] ? columns_info[:expr] : section_columns
                code += "\n" + indent("// Section #{index + 1}: #{cell_view_name} (#{section_columns_comment} columns)", depth + 1)
                if use_hoisted
                  # `section#{index}` is hoisted; just guard null.
                  code += "\n" + indent("if (#{section_var} != null) {", depth + 1)
                else
                  code += "\n" + indent("data.#{property_name}?.sections?.getOrNull(#{index})?.let { #{section_var} ->", depth + 1)
                end

                # Generate header if present
                if section['header']
                  header_view_name = section['header']
                  header_class = cell_class_name(header_view_name)
                  code += "\n" + indent("// Section #{index + 1} Header: #{header_view_name}", depth + 2)
                  code += "\n" + indent("#{section_var}.header?.let { headerData ->", depth + 2)
                  code += "\n" + indent("item(span = { GridItemSpan(maxLineSpan) }) {", depth + 3)
                  code += "\n" + indent("val headerViewModel: #{header_class}ViewModel = viewModel(key = \"#{header_view_name}_header_#{index}_\${viewModel.hashCode()}\")", depth + 4)
                  code += "\n" + indent("LaunchedEffect(headerData.data) {", depth + 4)
                  code += "\n" + indent("headerViewModel.updateData(headerData.data)", depth + 5)
                  code += "\n" + indent("}", depth + 4)
                  code += "\n" + indent("#{header_class}View(", depth + 4)
                  code += "\n" + indent("viewModel = headerViewModel,", depth + 5)
                  code += "\n" + indent("modifier = Modifier.fillMaxWidth()", depth + 5)
                  code += "\n" + indent(")", depth + 4)
                  code += "\n" + indent("}", depth + 3)
                  code += "\n" + indent("}", depth + 2)
                end

                # Generate cells with optional cellIdProperty for stable identity
                if use_hoisted
                  # enrichedData#{index} is hoisted; guard null and use directly.
                  code += "\n" + indent("if (enrichedData#{index} != null) {", depth + 2)
                  key_expr = "key = { (enrichedData#{index}[it][\"cellId\"] as? String) ?: it.toString() }"
                  data_access = "enrichedData#{index}"
                else
                  code += "\n" + indent("#{section_var}.cells?.let { #{cell_data_var} ->", depth + 2)
                  if cell_id_prop
                    key_expr = "key = { (#{cell_data_var}.data[it][\"cellId\"] as? String) ?: (#{cell_data_var}.data[it][\"#{cell_id_prop}\"] as? String) ?: it.toString() }"
                  else
                    key_expr = nil
                  end
                  data_access = "#{cell_data_var}.data"
                end

                if key_expr && item_span > 1
                  code += "\n" + indent("items(#{data_access}.size, #{key_expr}, span = { GridItemSpan(#{item_span}) }) { cellIndex ->", depth + 3)
                elsif key_expr
                  code += "\n" + indent("items(#{data_access}.size, #{key_expr}) { cellIndex ->", depth + 3)
                elsif item_span > 1
                  code += "\n" + indent("items(#{data_access}.size, span = { GridItemSpan(#{item_span}) }) { cellIndex ->", depth + 3)
                else
                  code += "\n" + indent("items(#{data_access}.size) { cellIndex ->", depth + 3)
                end
                # onItemAppear callback
                on_item_appear = json_data['onItemAppear']
                if on_item_appear && on_item_appear.match(/@\{([^}]+)\}/)
                  code += "\n" + indent("LaunchedEffect(Unit) { data.#{Helpers::BindingExpression.path_only($1)}?.invoke(cellIndex) }", depth + 4)
                end
                # Wrap cell in Box for alignment
                code += "\n" + indent("Box(", depth + 4)
                code += "\n" + indent("modifier = Modifier.fillMaxSize(),", depth + 5)
                code += "\n" + indent("contentAlignment = #{gravity_alignment}", depth + 5)
                code += "\n" + indent(") {", depth + 4)
                cell_class = cell_class_name(cell_view_name)
                code += "\n" + indent("val currentCellData = #{data_access}[cellIndex]", depth + 5)
                if cell_id_prop
                  code += "\n" + indent("val cellId = (currentCellData[\"cellId\"] as? String) ?: (currentCellData[\"#{cell_id_prop}\"] as? String) ?: \"$cellIndex\"", depth + 5)
                  code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 5)
                else
                  code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", depth + 5)
                end
                code += "\n" + indent("LaunchedEffect(currentCellData) {", depth + 5)
                code += "\n" + indent("cellViewModel.updateData(currentCellData)", depth + 6)
                code += "\n" + indent("}", depth + 5)
                if (chrome = chrome_open(json_data, required_imports))
                  code += "\n" + indent(chrome, depth + 5)
                end
                code += "\n" + indent("#{cell_class}View(", depth + 5)
                code += "\n" + indent("viewModel = cellViewModel,", depth + 6)
                # Add testTag for test automation (tapItem action)
                collection_id = json_data['id']
                if collection_id
                  code += "\n" + indent("modifier = Modifier.testTag(\"#{collection_id}_item_\$cellIndex\")", depth + 6)
                else
                  code += "\n" + indent("modifier = Modifier", depth + 6)
                end
                # cellWidth/cellHeight size every cell on the SECTIONED path
                # too — the emit lived only on the non-sectioned items route,
                # so the declared sizes were unread on the path the
                # conformance fixtures actually take.
                if json_data['cellWidth']
                  code += "\n" + indent("    .requiredWidth(#{json_data['cellWidth']}.dp)", depth + 6)
                end
                if json_data['cellHeight']
                  code += "\n" + indent("    .requiredHeight(#{json_data['cellHeight']}.dp)", depth + 6)
                end
                code += "\n" + indent(")", depth + 5)
                if chrome_open(json_data, nil)
                  code += "\n" + indent("}", depth + 5)
                end
                code += "\n" + indent("}", depth + 4)
                code += "\n" + indent("}", depth + 3)
                code += "\n" + indent("}", depth + 2)
                
                # Generate footer if present
                if section['footer']
                  footer_view_name = section['footer']
                  footer_class = cell_class_name(footer_view_name)
                  code += "\n" + indent("// Section #{index + 1} Footer: #{footer_view_name}", depth + 2)
                  code += "\n" + indent("#{section_var}.footer?.let { footerData ->", depth + 2)
                  code += "\n" + indent("item(span = { GridItemSpan(maxLineSpan) }) {", depth + 3)
                  code += "\n" + indent("val footerViewModel: #{footer_class}ViewModel = viewModel(key = \"#{footer_view_name}_footer_#{index}_\${viewModel.hashCode()}\")", depth + 4)
                  code += "\n" + indent("LaunchedEffect(footerData.data) {", depth + 4)
                  code += "\n" + indent("footerViewModel.updateData(footerData.data)", depth + 5)
                  code += "\n" + indent("}", depth + 4)
                  code += "\n" + indent("#{footer_class}View(", depth + 4)
                  code += "\n" + indent("viewModel = footerViewModel,", depth + 5)
                  code += "\n" + indent("modifier = Modifier.fillMaxWidth()", depth + 5)
                  code += "\n" + indent(")", depth + 4)
                  code += "\n" + indent("}", depth + 3)
                  code += "\n" + indent("}", depth + 2)
                end
                
                  code += "\n" + indent("}", depth + 1)
                end
              end
          else
            code += "\n" + indent("// No items binding specified", depth + 1)
          end
          
          code
        end
        
        # Generate horizontal paging collection using HorizontalPager
        def self.generate_paging_horizontal(json_data, sections, depth, required_imports, parent_type)
          required_imports&.add(:horizontal_pager)
          required_imports&.add(:launched_effect)
          required_imports&.add(:remember_state)
          required_imports&.add(:snapshot_flow)

          items_property = json_data['items']
          item_binding = items_property&.match(/@\{([^}]+)\}/)&.captures&.first
          page_spacing = json_data['itemSpacing'] || json_data['columnSpacing'] || json_data['spacing']

          # currentPage binding
          current_page_raw = json_data['currentPage']
          page_prop = current_page_raw&.match(/@\{([^}]+)\}/)&.captures&.first

          # Page-change callback: canonical 'onValueChange' with the
          # 'onValueChanged' / 'onPageChanged' alias fallbacks (skipped on
          # L1-normalized layouts).
          on_page_raw = Core::Normalization.attr_lookup(json_data, 'onValueChange', 'onValueChanged', 'onPageChanged')
          page_callback_prop = on_page_raw&.match(/@\{([^}]+)\}/)&.captures&.first

          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # Always add cell imports
          sections.each do |section|
            required_imports&.add("cell:#{section['cell']}") if section['cell']
          end

          code = ""

          # Page count from data source
          if item_binding && sections.any?
            code += indent("val pageCount = data.#{item_binding}?.sections?.firstOrNull()?.cells?.data?.size ?: 0", depth) + "\n"
          else
            code += indent("val pageCount = 0", depth) + "\n"
          end

          # PagerState
          if page_prop
            code += indent("val pagerState = rememberPagerState(initialPage = (data.#{page_prop}).coerceIn(0, (pageCount - 1).coerceAtLeast(0))) { pageCount }", depth) + "\n"
          else
            code += indent("val pagerState = rememberPagerState { pageCount }", depth) + "\n"
          end

          # Sync data binding -> pager
          if page_prop
            code += indent("LaunchedEffect(data.#{page_prop}) {", depth) + "\n"
            code += indent("val target = data.#{page_prop}.coerceIn(0, (pageCount - 1).coerceAtLeast(0))", depth + 1) + "\n"
            code += indent("if (pagerState.currentPage != target) pagerState.animateScrollToPage(target)", depth + 1) + "\n"
            code += indent("}", depth) + "\n"
          end

          # Sync pager -> binding + callback
          if page_prop || page_callback_prop
            code += indent("LaunchedEffect(pagerState) {", depth) + "\n"
            code += indent("snapshotFlow { pagerState.currentPage }.collect { page ->", depth + 1) + "\n"
            if page_prop
              code += indent("viewModel.updateData(mapOf(\"#{page_prop}\" to page))", depth + 2) + "\n"
            end
            if page_callback_prop
              code += indent("data.#{page_callback_prop}?.invoke(page)", depth + 2) + "\n"
            end
            code += indent("}", depth + 1) + "\n"
            code += indent("}", depth) + "\n"
          end

          # HorizontalPager
          code += indent("HorizontalPager(", depth)
          code += "\n" + indent("state = pagerState", depth + 1)
          if page_spacing
            code += ",\n" + indent("pageSpacing = #{page_spacing}.dp", depth + 1)
          end
          if modifiers.any?
            code += "," + Helpers::ModifierBuilder.format(modifiers, depth)
          end
          code += "\n" + indent(") { page ->", depth)

          # onItemAppear callback for paging
          on_item_appear = json_data['onItemAppear']
          if on_item_appear && on_item_appear.match(/@\{([^}]+)\}/)
            required_imports&.add(:launched_effect)
            code += "\n" + indent("LaunchedEffect(Unit) { data.#{$1}?.invoke(page) }", depth + 1)
          end

          # Render cell content
          if item_binding && sections.any?
            cell_view_name = sections.first['cell']
            if cell_view_name
              cell_class = cell_class_name(cell_view_name)
              cell_id_prop = json_data['cellIdProperty']
              auto_tracking = json_data['autoChangeTrackingId'] == true
              # Use val + if instead of .let { cellData -> ... } so remember(...)
              # (which is @Composable) isn't called from a non-@Composable lambda.
              code += "\n" + indent("val cellData = data.#{item_binding}?.sections?.firstOrNull()?.cells", depth + 1)
              code += "\n" + indent("if (cellData != null) {", depth + 1)
              if auto_tracking && cell_id_prop
                required_imports&.add(:remember_state)
                code += "\n" + indent("val enrichedData = remember(cellData.data) { com.kotlinjsonui.utils.CellIdGenerator.enrichCellIds(cellData.data, \"#{cell_id_prop}\") }", depth + 2)
                code += "\n" + indent("val item = enrichedData.getOrNull(page)", depth + 2)
              else
                code += "\n" + indent("val item = cellData.data.getOrNull(page)", depth + 2)
              end
              code += "\n" + indent("if (item != null) {", depth + 2)
              code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_page_\${page}_\${viewModel.hashCode()}\")", depth + 3)
              code += "\n" + indent("LaunchedEffect(item) {", depth + 3)
              code += "\n" + indent("cellViewModel.updateData(item)", depth + 4)
              code += "\n" + indent("}", depth + 3)
              code += "\n" + indent("#{cell_class}View(", depth + 3)
              code += "\n" + indent("viewModel = cellViewModel,", depth + 4)
              collection_id = json_data['id']
              if collection_id
                code += "\n" + indent("modifier = Modifier.testTag(\"#{collection_id}_item_\$page\").fillMaxSize()", depth + 4)
              else
                code += "\n" + indent("modifier = Modifier.fillMaxSize()", depth + 4)
              end
              code += "\n" + indent(")", depth + 3)
              code += "\n" + indent("}", depth + 2)
              code += "\n" + indent("}", depth + 1)
            end
          end

          code += "\n" + indent("}", depth)
          code
        end

        # Generate FlowLayout using Compose FlowRow
        def self.generate_flow_layout(json_data, sections, depth, required_imports, parent_type)
          required_imports&.add(:flow_row)
          required_imports&.add(:arrangement)
          required_imports&.add(:launched_effect)

          # Spacing. Undeclared means 0, the platform default — the dynamic
          # renderer falls back to 0f, and the silent 8 here was the parity
          # residue on Collection/layout__flow_2 after the enum fix.
          h_spacing = json_data['columnSpacing'] || json_data['itemSpacing'] || json_data['spacing'] || 0
          v_spacing = json_data['lineSpacing'] || json_data['itemSpacing'] || json_data['spacing'] || 0

          # Flow alignment
          flow_alignment = json_data['flowAlignment'] || 'leading'
          arrangement = case flow_alignment
          when 'center'
            'Arrangement.Center'
          when 'trailing', 'end'
            'Arrangement.End'
          else
            'Arrangement.Start'
          end

          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code = indent("FlowRow(", depth)
          code += Helpers::ModifierBuilder.format(modifiers, depth)
          code += ",\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{h_spacing}.dp),", depth + 1)
          code += "\n" + indent("verticalArrangement = Arrangement.spacedBy(#{v_spacing}.dp)", depth + 1)
          code += "\n" + indent(") {", depth)

          items_property = json_data['items']
          cell_id_property = json_data['cellIdProperty']
          required_imports&.add(:compose_key) if cell_id_property

          if sections.any? && items_property && items_property.match(/@\{([^}]+)\}/)
            property_name = $1

            # Add cell imports
            sections.each do |section|
              cell_view_name = section['cell']
              required_imports&.add("cell:#{cell_view_name}") if cell_view_name
            end

            sections.each_with_index do |section, index|
              cell_view_name = section['cell']
              next unless cell_view_name

              auto_tracking = json_data['autoChangeTrackingId'] == true
              use_val_if = auto_tracking && cell_id_property
              section_var = use_val_if ? "section#{index}" : 'section'
              cell_data_var = use_val_if ? "cellData#{index}" : 'cellData'

              if use_val_if
                code += "\n" + indent("val #{section_var} = data.#{property_name}?.sections?.getOrNull(#{index})", depth + 1)
                code += "\n" + indent("if (#{section_var} != null) {", depth + 1)
                code += "\n" + indent("val #{cell_data_var} = #{section_var}.cells", depth + 2)
                code += "\n" + indent("if (#{cell_data_var} != null) {", depth + 2)
                required_imports&.add(:remember_state)
                code += "\n" + indent("val enrichedData#{index} = remember(#{cell_data_var}.data) { com.kotlinjsonui.utils.CellIdGenerator.enrichCellIds(#{cell_data_var}.data, \"#{cell_id_property}\") }", depth + 3)
                code += "\n" + indent("enrichedData#{index}.forEachIndexed { cellIndex, item ->", depth + 3)
              else
                code += "\n" + indent("data.#{property_name}?.sections?.getOrNull(#{index})?.let { #{section_var} ->", depth + 1)
                code += "\n" + indent("#{section_var}.cells?.let { #{cell_data_var} ->", depth + 2)
                code += "\n" + indent("#{cell_data_var}.data.forEachIndexed { cellIndex, item ->", depth + 3)
              end

              if cell_id_property
                code += "\n" + indent("val cellId = (item[\"cellId\"] as? String) ?: (item[\"#{cell_id_property}\"] as? String) ?: cellIndex.toString()", depth + 4)
                code += "\n" + indent("key(cellId) {", depth + 4)
                inner_depth = depth + 5
              else
                inner_depth = depth + 4
              end

              cell_class = cell_class_name(cell_view_name)
              if cell_id_property
                code += "\n" + indent("val flowCellId = (item[\"cellId\"] as? String) ?: (item[\"#{cell_id_property}\"] as? String) ?: \"$cellIndex\"", inner_depth)
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_flow_\${flowCellId}_\${viewModel.hashCode()}\")", inner_depth)
              else
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_flow_\${cellIndex}_\${viewModel.hashCode()}\")", inner_depth)
              end
              code += "\n" + indent("LaunchedEffect(item) {", inner_depth)
              code += "\n" + indent("cellViewModel.updateData(item)", inner_depth + 1)
              code += "\n" + indent("}", inner_depth)
              code += "\n" + indent("#{cell_class}View(", inner_depth)
              code += "\n" + indent("viewModel = cellViewModel", inner_depth + 1)
              code += "\n" + indent(")", inner_depth)

              if cell_id_property
                code += "\n" + indent("}", depth + 4)
              end

              code += "\n" + indent("}", depth + 3)
              code += "\n" + indent("}", depth + 2)
              code += "\n" + indent("}", depth + 1)
            end
          end

          code += "\n" + indent("}", depth)
          code
        end

        # Generate non-lazy Column-based collection for wrapContent height.
        # Used when a vertical Collection has height: "wrapContent" to avoid
        # Compose crash from nesting LazyVerticalGrid inside another Lazy container.
        def self.generate_non_lazy(json_data, sections, depth, required_imports, parent_type)
          required_imports&.add(:launched_effect)

          items_property = json_data['items']
          default_columns = json_data['columns'] || 1

          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # Spacing
          line_spacing = json_data['lineSpacing'] || json_data['itemSpacing'] || json_data['spacing']

          code = indent("Column(", depth)
          code += Helpers::ModifierBuilder.format(modifiers, depth)
          if line_spacing
            required_imports&.add(:arrangement)
            code += ",\n" + indent("verticalArrangement = Arrangement.spacedBy(#{line_spacing}.dp)", depth + 1)
          end
          code += "\n" + indent(") {", depth)

          if sections.any? && items_property && items_property.match(/@\{([^}]+)\}/)
            property_name = $1

            # Add cell imports
            sections.each do |section|
              required_imports&.add("cell:#{section['cell']}") if section['cell']
              required_imports&.add("cell:#{section['header']}") if section['header']
              required_imports&.add("cell:#{section['footer']}") if section['footer']
            end

            sections.each_with_index do |section, index|
              cell_view_name = section['cell']
              next unless cell_view_name

              cell_class = cell_class_name(cell_view_name)
              cell_id_prop = json_data['cellIdProperty']
              auto_tracking = json_data['autoChangeTrackingId'] == true
              use_val_if = auto_tracking && cell_id_prop
              section_var = use_val_if ? "section#{index}" : 'section'
              cell_data_var = use_val_if ? "cellData#{index}" : 'cellData'

              code += "\n" + indent("// Section #{index + 1}: #{cell_view_name}", depth + 1)
              if use_val_if
                code += "\n" + indent("val #{section_var} = data.#{property_name}?.sections?.getOrNull(#{index})", depth + 1)
                code += "\n" + indent("if (#{section_var} != null) {", depth + 1)
              else
                code += "\n" + indent("data.#{property_name}?.sections?.getOrNull(#{index})?.let { #{section_var} ->", depth + 1)
              end

              # Header
              if section['header']
                header_class = cell_class_name(section['header'])
                code += "\n" + indent("#{section_var}.header?.let { headerData ->", depth + 2)
                code += "\n" + indent("val headerViewModel: #{header_class}ViewModel = viewModel(key = \"#{section['header']}_header_#{index}_\${viewModel.hashCode()}\")", depth + 3)
                code += "\n" + indent("LaunchedEffect(headerData.data) { headerViewModel.updateData(headerData.data) }", depth + 3)
                code += "\n" + indent("#{header_class}View(viewModel = headerViewModel, modifier = Modifier.fillMaxWidth())", depth + 3)
                code += "\n" + indent("}", depth + 2)
              end

              # Cells
              if use_val_if
                code += "\n" + indent("val #{cell_data_var} = #{section_var}.cells", depth + 2)
                code += "\n" + indent("if (#{cell_data_var} != null) {", depth + 2)
                required_imports&.add(:remember_state)
                code += "\n" + indent("val enrichedData#{index} = remember(#{cell_data_var}.data) { com.kotlinjsonui.utils.CellIdGenerator.enrichCellIds(#{cell_data_var}.data, \"#{cell_id_prop}\") }", depth + 3)
                data_access = "enrichedData#{index}"
              else
                code += "\n" + indent("#{section_var}.cells?.let { #{cell_data_var} ->", depth + 2)
                data_access = "#{cell_data_var}.data"
              end
              code += "\n" + indent("#{data_access}.forEachIndexed { cellIndex, _ ->", depth + 3)
              code += "\n" + indent("val currentCellData = #{data_access}[cellIndex]", depth + 4)
              if cell_id_prop
                code += "\n" + indent("val cellId = (currentCellData[\"cellId\"] as? String) ?: (currentCellData[\"#{cell_id_prop}\"] as? String) ?: \"$cellIndex\"", depth + 4)
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 4)
              else
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", depth + 4)
              end
              code += "\n" + indent("LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }", depth + 4)
              code += "\n" + indent("#{cell_class}View(", depth + 4)
              code += "\n" + indent("viewModel = cellViewModel,", depth + 5)
              collection_id = json_data['id']
              # No fillMaxWidth: the cell view defines its own size (dynamic
              # honors the declared width; a full-width cell declares
              # matchParent itself). Stretching here was the parity deviation
              # measured across every android Collection fixture.
              if collection_id
                code += "\n" + indent("modifier = Modifier.testTag(\"#{collection_id}_item_\$cellIndex\")", depth + 5)
              else
                code += "\n" + indent("modifier = Modifier", depth + 5)
              end
              code += "\n" + indent(")", depth + 4)
              code += "\n" + indent("}", depth + 3)
              code += "\n" + indent("}", depth + 2)

              # Footer
              if section['footer']
                footer_class = cell_class_name(section['footer'])
                code += "\n" + indent("#{section_var}.footer?.let { footerData ->", depth + 2)
                code += "\n" + indent("val footerViewModel: #{footer_class}ViewModel = viewModel(key = \"#{section['footer']}_footer_#{index}_\${viewModel.hashCode()}\")", depth + 3)
                code += "\n" + indent("LaunchedEffect(footerData.data) { footerViewModel.updateData(footerData.data) }", depth + 3)
                code += "\n" + indent("#{footer_class}View(viewModel = footerViewModel, modifier = Modifier.fillMaxWidth())", depth + 3)
                code += "\n" + indent("}", depth + 2)
              end

              code += "\n" + indent("}", depth + 1)
            end
          end

          code += "\n" + indent("}", depth)
          code
        end

        # Non-lazy horizontal path: Row + forEachIndexed, no LazyRow, no
        # horizontalScroll. Expects an already-scrollable parent.
        def self.generate_non_lazy_row(json_data, sections, depth, required_imports, parent_type)
          required_imports&.add(:launched_effect)

          items_property = json_data['items']

          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          column_spacing = json_data['columnSpacing'] || json_data['itemSpacing']

          code = indent("Row(", depth)
          code += Helpers::ModifierBuilder.format(modifiers, depth)
          if column_spacing
            required_imports&.add(:arrangement)
            code += ",\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{column_spacing}.dp)", depth + 1)
          end
          code += "\n" + indent(") {", depth)

          if sections.any? && items_property && items_property.match(/@\{([^}]+)\}/)
            property_name = $1

            sections.each do |section|
              required_imports&.add("cell:#{section['cell']}") if section['cell']
            end

            sections.each_with_index do |section, index|
              cell_view_name = section['cell']
              next unless cell_view_name

              cell_class = cell_class_name(cell_view_name)
              cell_id_prop = json_data['cellIdProperty']

              code += "\n" + indent("// Section #{index + 1}: #{cell_view_name}", depth + 1)
              code += "\n" + indent("data.#{property_name}?.sections?.getOrNull(#{index})?.let { section ->", depth + 1)
              code += "\n" + indent("section.cells?.let { cellData ->", depth + 2)
              code += "\n" + indent("cellData.data.forEachIndexed { cellIndex, _ ->", depth + 3)
              code += "\n" + indent("val currentCellData = cellData.data[cellIndex]", depth + 4)
              if cell_id_prop
                code += "\n" + indent("val cellId = (currentCellData[\"cellId\"] as? String) ?: (currentCellData[\"#{cell_id_prop}\"] as? String) ?: \"$cellIndex\"", depth + 4)
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_rowCell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 4)
              else
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_rowCell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", depth + 4)
              end
              code += "\n" + indent("LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }", depth + 4)
              code += "\n" + indent("#{cell_class}View(", depth + 4)
              code += "\n" + indent("viewModel = cellViewModel", depth + 5)
              code += "\n" + indent(")", depth + 4)
              code += "\n" + indent("}", depth + 3)
              code += "\n" + indent("}", depth + 2)
              code += "\n" + indent("}", depth + 1)
            end
          end

          code += "\n" + indent("}", depth)
          code
        end

        # True when every section uses (or defaults to) `columns: 1` AND defines
        # a `cell`. CollectionStack is a single-column container; anything wider
        # or section-skeletons-without-cells stay on the existing LazyVerticalGrid
        # emission so spec expectations and edge cases keep working.
        def self.single_column_sections?(sections, json_data)
          # A `@{prop}` binding on the top-level `columns` attribute means
          # the runtime column count is unknown at codegen time. Forfeit
          # the single-column CollectionStack fast-path and always render
          # the binding-driven grid (LazyVerticalGrid / LazyHorizontalGrid)
          # so the layout stays consistent if the binding resolves to >1.
          return false if columns_emit_info(json_data)[:is_binding]
          default_columns = json_data['columns'] || 1
          sections.all? do |s|
            (s['columns'] || default_columns) == 1 && s['cell']
          end
        end

        # Resolve the top-level `columns` attribute into its Kotlin emit
        # expression. A literal int returns `{ expr: "5", literal: 5,
        # is_binding: false }`; a `@{prop}` binding returns
        # `{ expr: "data.prop", literal: nil, is_binding: true }`. The
        # caller interpolates `expr` into `GridCells.Fixed(...)` and uses
        # `is_binding` to suppress compile-time fast-paths (single-column
        # CollectionStack, per-section LCM) that require a known column
        # count.
        def self.columns_emit_info(json_data)
          value = json_data['columns']
          if value.is_a?(String) && value =~ /^@\{(.+)\}$/
            { expr: "data.#{$1}", literal: nil, is_binding: true }
          else
            literal = (value || 1).to_i
            { expr: literal.to_s, literal: literal, is_binding: false }
          end
        end

        # Compose-source expression evaluating to a CollectionStackMode value.
        def self.collection_stack_mode_expr(json_data)
          value = json_data['lazy']
          if value.is_a?(String) && value.match(/@\{([^}]+)\}/)
            "CollectionStackMode.fromJson(data.#{$1})"
          else
            case value
            when 'eager' then 'CollectionStackMode.EAGER'
            when 'none' then 'CollectionStackMode.NONE'
            else 'CollectionStackMode.LAZY'
            end
          end
        end

        # Single-column CollectionStack emission. Wraps cell content in both
        # `lazyContent` (LazyListScope) and `eagerContent` (@Composable) so the
        # library can switch axes/modes without forcing the generator to fork.
        def self.generate_collection_stack(json_data, sections, depth, required_imports, parent_type, is_horizontal:)
          required_imports&.add(:collection_stack)
          required_imports&.add(:launched_effect)
          required_imports&.add(:remember_state)

          axis_kotlin = is_horizontal ? 'CollectionStackAxis.HORIZONTAL' : 'CollectionStackAxis.VERTICAL'
          mode_expr = collection_stack_mode_expr(json_data)

          # Spacing
          # `lineSpacing` historically named the inter-line gap; with a
          # horizontal single-column CollectionStack, the inter-cell gap IS
          # the inter-line gap (one cell per line), so authoring `lineSpacing`
          # for a horizontal Collection should still set the spacing. The
          # LazyHorizontalGrid path (line ~150) already accepts `lineSpacing`
          # as the horizontal-spacing source; CollectionStack must match.
          spacing_value = if is_horizontal
                           json_data['itemSpacing'] || json_data['columnSpacing'] || json_data['lineSpacing'] || json_data['spacing']
                         else
                           json_data['lineSpacing'] || json_data['itemSpacing'] || json_data['spacing']
                         end

          # userScrollEnabled (binding aware)
          user_scroll_enabled_expr =
            if json_data.key?('scrollEnabled')
              raw = json_data['scrollEnabled']
              if raw.is_a?(String) && raw.match(/@\{([^}]+)\}/)
                "data.#{$1}"
              else
                raw == false ? 'false' : 'true'
              end
            else
              'true'
            end

          # Content padding
          content_padding_expr = collection_stack_content_padding_expr(json_data, is_horizontal: is_horizontal)

          # Inset spacers (horizontal only)
          inset_horizontal = json_data['insetHorizontal'] || 0

          reverse_layout = json_data['reverseLayout'] == true

          # Build outer modifier
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          width_value = json_data['width']
          height_value = json_data['height']
          # CollectionStack.LAZY uses LazyColumn/Row internally which require
          # bounded cross-axis size. Promote wrapContent → matchParent for safety.
          if !is_horizontal && width_value == 'wrapContent'
            modified = json_data.merge('width' => 'matchParent')
            modifiers.concat(Helpers::ModifierBuilder.build_size(modified, parent_type, required_imports))
          elsif is_horizontal && height_value == 'wrapContent'
            modified = json_data.merge('height' => 'matchParent')
            modifiers.concat(Helpers::ModifierBuilder.build_size(modified, parent_type, required_imports))
          else
            modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          end
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          # Multi-line modifier formatting so `wrap_with_visibility` regex can
          # detect and hoist `.weight(...)` onto the VisibilityWrapper. Single-
          # line emission breaks the `\n\s*\.weight(...)` lookup.
          modifier_prefix = '    ' * (depth + 2)
          modifier_lines = if modifiers.empty?
                             "Modifier"
                           else
                             ["Modifier"].concat(modifiers).join("\n#{modifier_prefix}")
                           end

          # scrollTo support
          scroll_to_raw = json_data['scrollTo']
          has_scroll_to = scroll_to_raw && scroll_to_raw.match(/@\{([^}]+)\}/)
          scroll_prop = has_scroll_to ? $1 : nil
          stack_default_anchor = default_scroll_anchor?(json_data)

          code = ""

          if has_scroll_to
            required_imports&.add(:lazy_grid_state)
            scroll_animated = json_data['scrollAnimated']
            animated_match = scroll_animated && scroll_animated.to_s.match(/@\{([^}]+)\}/)
            animated_prop = animated_match ? $1 : nil

            code += indent("val collectionStackState = androidx.compose.foundation.lazy.rememberLazyListState()", depth) + "\n"
            code += indent("LaunchedEffect(data.#{scroll_prop}) {", depth) + "\n"
            code += indent("val raw = data.#{scroll_prop}?.toString().orEmpty()", depth + 1) + "\n"
            code += indent("if (raw.isEmpty()) return@LaunchedEffect", depth + 1) + "\n"
            code += indent("val index = raw.substringBefore(\"#\").toIntOrNull() ?: return@LaunchedEffect", depth + 1) + "\n"
            stack_anchor_decl, stack_anchor_arg = scroll_anchor_offset_code(json_data, 'collectionStackState', depth)
            code += stack_anchor_decl
            if animated_prop
              code += indent("if (index >= 0) {", depth + 1) + "\n"
              code += indent("if (data.#{animated_prop}) collectionStackState.animateScrollToItem(index#{stack_anchor_arg}) else collectionStackState.scrollToItem(index#{stack_anchor_arg})", depth + 2) + "\n"
              code += indent("}", depth + 1) + "\n"
            else
              code += indent("if (index >= 0) collectionStackState.animateScrollToItem(index#{stack_anchor_arg})", depth + 1) + "\n"
            end
            code += indent("}", depth) + "\n"
            code += default_scroll_anchor_code(json_data, 'collectionStackState', depth, required_imports)
          elsif stack_default_anchor
            required_imports&.add(:lazy_grid_state)
            code += indent("val collectionStackState = androidx.compose.foundation.lazy.rememberLazyListState()", depth) + "\n"
            code += default_scroll_anchor_code(json_data, 'collectionStackState', depth, required_imports)
          end

          # Hoist section / cellData / enrichedData out of the CollectionStack
          # call so `remember(...)` (which is @Composable) lives in the enclosing
          # @Composable scope. lazyContent (LazyListScope) cannot host @Composable
          # calls, and we want eagerContent to read the same values as well so the
          # inner closures stay symmetric.
          items_property = json_data['items']
          property_name = items_property && items_property.match(/@\{([^}]+)\}/) ? $1 : nil
          cell_id_prop = json_data['cellIdProperty']
          auto_tracking = json_data['autoChangeTrackingId'] == true

          if property_name
            sections.each_with_index do |section, idx|
              next unless section['cell']
              code += indent("val section#{idx} = data.#{property_name}?.sections?.getOrNull(#{idx})", depth) + "\n"
              code += indent("val cellData#{idx} = section#{idx}?.cells", depth) + "\n"
              if auto_tracking && cell_id_prop
                required_imports&.add(:remember_state)
                code += indent("val enrichedData#{idx} = if (cellData#{idx} != null) remember(cellData#{idx}.data) { com.kotlinjsonui.utils.CellIdGenerator.enrichCellIds(cellData#{idx}.data, \"#{cell_id_prop}\") } else null", depth) + "\n"
              end
            end
          end

          code += indent("CollectionStack(", depth)
          code += "\n" + indent("mode = #{mode_expr},", depth + 1)
          code += "\n" + indent("axis = #{axis_kotlin},", depth + 1)
          code += "\n" + indent("modifier = #{modifier_lines},", depth + 1)
          if spacing_value
            code += "\n" + indent("spacing = #{spacing_value}.dp,", depth + 1)
          end
          if user_scroll_enabled_expr != 'true'
            code += "\n" + indent("userScrollEnabled = #{user_scroll_enabled_expr},", depth + 1)
          end
          if content_padding_expr
            code += "\n" + indent("contentPadding = #{content_padding_expr},", depth + 1)
          end
          if is_horizontal && inset_horizontal.to_i > 0
            code += "\n" + indent("insetLeading = #{inset_horizontal}.dp,", depth + 1)
            code += "\n" + indent("insetTrailing = #{inset_horizontal}.dp,", depth + 1)
          end
          if reverse_layout
            code += "\n" + indent("reverseLayout = true,", depth + 1)
          end
          if has_scroll_to || stack_default_anchor
            code += "\n" + indent("lazyState = collectionStackState,", depth + 1)
          end

          # lazyContent block
          code += "\n" + indent("lazyContent = {", depth + 1)
          code += generate_collection_stack_lazy_content(json_data, sections, depth + 2, required_imports)
          code += "\n" + indent("},", depth + 1)

          # eagerContent block
          code += "\n" + indent("eagerContent = {", depth + 1)
          code += generate_collection_stack_eager_content(json_data, sections, depth + 2, required_imports)
          code += "\n" + indent("}", depth + 1)

          code += "\n" + indent(")", depth)
          code
        end

        # PaddingValues expression for CollectionStack.contentPadding, or nil to
        # use the default (zero padding).
        def self.collection_stack_content_padding_expr(json_data, is_horizontal:)
          content_padding = json_data['contentPadding'] || json_data['insets']
          if content_padding.is_a?(Array) && content_padding.length == 4
            "PaddingValues(top = #{content_padding[0]}.dp, start = #{content_padding[1]}.dp, bottom = #{content_padding[2]}.dp, end = #{content_padding[3]}.dp)"
          elsif content_padding.is_a?(Numeric)
            "PaddingValues(#{content_padding}.dp)"
          else
            inset_h = json_data['insetHorizontal']
            inset_v = json_data['insetVertical']
            if inset_h || inset_v
              "PaddingValues(horizontal = #{inset_h || 0}.dp, vertical = #{inset_v || 0}.dp)"
            else
              # Same precedence as the grid path: a declared numeric padding
              # wins, and only when none is declared does
              # `contentInsetAdjustmentBehavior` get to ask for the safe-area
              # inset. Both of Collection's emitters go through this one
              # method now — the grid path and the stack path are chosen by
              # `single_column_sections?`, and a change that reaches only one
              # of them reaches roughly half the collections in a project
              # (plan 49 lane C, #4).
              Helpers::ContentInsetHelper.safe_area_padding(
                json_data['contentInsetAdjustmentBehavior'], horizontal: is_horizontal
              )
            end
          end
        end

        # Emit cell ForEach inside LazyListScope. Single-column so no GridItemSpan.
        # Assumes section / cellData / enrichedData vals are hoisted in the
        # enclosing @Composable scope by `generate_collection_stack`.
        def self.generate_collection_stack_lazy_content(json_data, sections, depth, required_imports)
          items_property = json_data['items']
          property_name = items_property && items_property.match(/@\{([^}]+)\}/) ? $1 : nil
          cell_id_prop = json_data['cellIdProperty']
          auto_tracking = json_data['autoChangeTrackingId'] == true

          out = ""
          sections.each do |s|
            required_imports&.add("cell:#{s['cell']}") if s['cell']
            required_imports&.add("cell:#{s['header']}") if s['header']
            required_imports&.add("cell:#{s['footer']}") if s['footer']
          end

          unless property_name
            out += "\n" + indent("// No items binding specified", depth)
            return out
          end

          # LazyColumn/LazyRow with reverseLayout=true places the FIRST emitted
          # item visually at the bottom (vertical) or trailing edge (horizontal).
          # To preserve JSON section order as the visual top→bottom order
          # (chat: section 0 = oldest at top, last section = newest at bottom),
          # emit sections in reverse when reverseLayout=true.
          ordered_sections = if json_data['reverseLayout'] == true
                               sections.each_with_index.to_a.reverse
                             else
                               sections.each_with_index.to_a
                             end

          ordered_sections.each do |(section, index)|
            cell_view_name = section['cell']
            next unless cell_view_name
            cell_class = cell_class_name(cell_view_name)

            out += "\n" + indent("// Section #{index + 1}: #{cell_view_name}", depth)
            out += "\n" + indent("if (section#{index} != null) {", depth)

            if section['header']
              header_class = cell_class_name(section['header'])
              out += "\n" + indent("// Section #{index + 1} Header: #{section['header']}", depth + 1)
              out += "\n" + indent("section#{index}.header?.let { headerData ->", depth + 1)
              out += "\n" + indent("item {", depth + 2)
              out += "\n" + indent("val headerViewModel: #{header_class}ViewModel = viewModel(key = \"#{section['header']}_header_#{index}_\${viewModel.hashCode()}\")", depth + 3)
              out += "\n" + indent("LaunchedEffect(headerData.data) { headerViewModel.updateData(headerData.data) }", depth + 3)
              out += "\n" + indent("#{header_class}View(viewModel = headerViewModel, modifier = Modifier.fillMaxWidth())", depth + 3)
              out += "\n" + indent("}", depth + 2)
              out += "\n" + indent("}", depth + 1)
            end

            data_access = if auto_tracking && cell_id_prop
                            "enrichedData#{index}"
                          else
                            "cellData#{index}.data"
                          end

            # Both branches need a non-null guard on cellData / enrichedData.
            if auto_tracking && cell_id_prop
              out += "\n" + indent("if (enrichedData#{index} != null) {", depth + 1)
            else
              out += "\n" + indent("if (cellData#{index} != null) {", depth + 1)
            end

            key_expr = if cell_id_prop
                         "key = { idx -> (#{data_access}[idx][\"cellId\"] as? String) ?: (#{data_access}[idx][\"#{cell_id_prop}\"] as? String) ?: idx.toString() }"
                       else
                         nil
                       end

            if key_expr
              out += "\n" + indent("items(#{data_access}.size, #{key_expr}) { cellIndex ->", depth + 2)
            else
              out += "\n" + indent("items(#{data_access}.size) { cellIndex ->", depth + 2)
            end

            on_item_appear = json_data['onItemAppear']
            if on_item_appear && on_item_appear.match(/@\{([^}]+)\}/)
              out += "\n" + indent("LaunchedEffect(Unit) { data.#{Helpers::BindingExpression.path_only($1)}?.invoke(cellIndex) }", depth + 3)
            end

            out += "\n" + indent("val currentCellData = #{data_access}[cellIndex]", depth + 3)
            if cell_id_prop
              out += "\n" + indent("val cellId = (currentCellData[\"cellId\"] as? String) ?: (currentCellData[\"#{cell_id_prop}\"] as? String) ?: \"$cellIndex\"", depth + 3)
              out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 3)
            else
              out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", depth + 3)
            end
            out += "\n" + indent("LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }", depth + 3)
            # The CollectionStack route is the one the sectioned single-column
            # fixtures take — the chrome and the declared cell sizes must
            # apply HERE, not only on the grid route (C0 until 2026-08-08).
            if (stack_chrome = chrome_open(json_data, required_imports))
              out += "\n" + indent(stack_chrome, depth + 3)
            end
            out += "\n" + indent("#{cell_class}View(", depth + 3)
            out += "\n" + indent("viewModel = cellViewModel,", depth + 4)
            collection_id = json_data['id']
            # No fillMaxWidth on cells — see the grid path note above.
            if collection_id
              out += "\n" + indent("modifier = Modifier.testTag(\"#{collection_id}_item_\$cellIndex\")", depth + 4)
            else
              out += "\n" + indent("modifier = Modifier", depth + 4)
            end
            if json_data['cellWidth']
              out += "\n" + indent("    .requiredWidth(#{json_data['cellWidth']}.dp)", depth + 4)
            end
            if json_data['cellHeight']
              out += "\n" + indent("    .requiredHeight(#{json_data['cellHeight']}.dp)", depth + 4)
            end
            out += "\n" + indent(")", depth + 3)
            if chrome_open(json_data, nil)
              out += "\n" + indent("}", depth + 3)
            end
            out += "\n" + indent("}", depth + 2)
            out += "\n" + indent("}", depth + 1)

            if section['footer']
              footer_class = cell_class_name(section['footer'])
              out += "\n" + indent("// Section #{index + 1} Footer: #{section['footer']}", depth + 1)
              out += "\n" + indent("section#{index}.footer?.let { footerData ->", depth + 1)
              out += "\n" + indent("item {", depth + 2)
              out += "\n" + indent("val footerViewModel: #{footer_class}ViewModel = viewModel(key = \"#{section['footer']}_footer_#{index}_\${viewModel.hashCode()}\")", depth + 3)
              out += "\n" + indent("LaunchedEffect(footerData.data) { footerViewModel.updateData(footerData.data) }", depth + 3)
              out += "\n" + indent("#{footer_class}View(viewModel = footerViewModel, modifier = Modifier.fillMaxWidth())", depth + 3)
              out += "\n" + indent("}", depth + 2)
              out += "\n" + indent("}", depth + 1)
            end

            out += "\n" + indent("}", depth)
          end

          out
        end

        # Emit cell ForEach inside @Composable scope (Column / Row body).
        # Assumes section / cellData / enrichedData vals are hoisted in the
        # enclosing @Composable scope by `generate_collection_stack`.
        def self.generate_collection_stack_eager_content(json_data, sections, depth, required_imports)
          items_property = json_data['items']
          property_name = items_property && items_property.match(/@\{([^}]+)\}/) ? $1 : nil
          cell_id_prop = json_data['cellIdProperty']
          auto_tracking = json_data['autoChangeTrackingId'] == true

          out = ""
          unless property_name
            out += "\n" + indent("// No items binding specified", depth)
            return out
          end

          sections.each_with_index do |section, index|
            cell_view_name = section['cell']
            next unless cell_view_name
            cell_class = cell_class_name(cell_view_name)

            out += "\n" + indent("// Section #{index + 1}: #{cell_view_name}", depth)
            out += "\n" + indent("if (section#{index} != null) {", depth)

            if section['header']
              header_class = cell_class_name(section['header'])
              out += "\n" + indent("section#{index}.header?.let { headerData ->", depth + 1)
              out += "\n" + indent("val headerViewModel: #{header_class}ViewModel = viewModel(key = \"#{section['header']}_header_#{index}_\${viewModel.hashCode()}\")", depth + 2)
              out += "\n" + indent("LaunchedEffect(headerData.data) { headerViewModel.updateData(headerData.data) }", depth + 2)
              out += "\n" + indent("#{header_class}View(viewModel = headerViewModel, modifier = Modifier.fillMaxWidth())", depth + 2)
              out += "\n" + indent("}", depth + 1)
            end

            data_access = if auto_tracking && cell_id_prop
                            "enrichedData#{index}"
                          else
                            "cellData#{index}.data"
                          end

            if auto_tracking && cell_id_prop
              out += "\n" + indent("if (enrichedData#{index} != null) {", depth + 1)
            else
              out += "\n" + indent("if (cellData#{index} != null) {", depth + 1)
            end

            out += "\n" + indent("#{data_access}.forEachIndexed { cellIndex, _ ->", depth + 2)
            on_item_appear = json_data['onItemAppear']
            if on_item_appear && on_item_appear.match(/@\{([^}]+)\}/)
              out += "\n" + indent("LaunchedEffect(Unit) { data.#{Helpers::BindingExpression.path_only($1)}?.invoke(cellIndex) }", depth + 3)
            end

            out += "\n" + indent("val currentCellData = #{data_access}[cellIndex]", depth + 3)
            if cell_id_prop
              out += "\n" + indent("val cellId = (currentCellData[\"cellId\"] as? String) ?: (currentCellData[\"#{cell_id_prop}\"] as? String) ?: \"$cellIndex\"", depth + 3)
              out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 3)
            else
              out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", depth + 3)
            end
            out += "\n" + indent("LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }", depth + 3)
            # The CollectionStack route is the one the sectioned single-column
            # fixtures take — the chrome and the declared cell sizes must
            # apply HERE, not only on the grid route (C0 until 2026-08-08).
            if (stack_chrome = chrome_open(json_data, required_imports))
              out += "\n" + indent(stack_chrome, depth + 3)
            end
            out += "\n" + indent("#{cell_class}View(", depth + 3)
            out += "\n" + indent("viewModel = cellViewModel,", depth + 4)
            collection_id = json_data['id']
            # No fillMaxWidth on cells — see the grid path note above.
            if collection_id
              out += "\n" + indent("modifier = Modifier.testTag(\"#{collection_id}_item_\$cellIndex\")", depth + 4)
            else
              out += "\n" + indent("modifier = Modifier", depth + 4)
            end
            if json_data['cellWidth']
              out += "\n" + indent("    .requiredWidth(#{json_data['cellWidth']}.dp)", depth + 4)
            end
            if json_data['cellHeight']
              out += "\n" + indent("    .requiredHeight(#{json_data['cellHeight']}.dp)", depth + 4)
            end
            out += "\n" + indent(")", depth + 3)
            if chrome_open(json_data, nil)
              out += "\n" + indent("}", depth + 3)
            end
            out += "\n" + indent("}", depth + 2)
            out += "\n" + indent("}", depth + 1)

            if section['footer']
              footer_class = cell_class_name(section['footer'])
              out += "\n" + indent("// Section #{index + 1} Footer: #{section['footer']}", depth + 1)
              out += "\n" + indent("section#{index}.footer?.let { footerData ->", depth + 1)
              out += "\n" + indent("val footerViewModel: #{footer_class}ViewModel = viewModel(key = \"#{section['footer']}_footer_#{index}_\${viewModel.hashCode()}\")", depth + 2)
              out += "\n" + indent("LaunchedEffect(footerData.data) { footerViewModel.updateData(footerData.data) }", depth + 2)
              out += "\n" + indent("#{footer_class}View(viewModel = footerViewModel, modifier = Modifier.fillMaxWidth())", depth + 2)
              out += "\n" + indent("}", depth + 1)
            end

            out += "\n" + indent("}", depth)
          end

          out
        end

        private

        def self.calculate_lcm(numbers)
          numbers.reduce(1) { |lcm, n| lcm.lcm(n) }
        end
        
        def self.extract_view_name(class_name)
          return nil unless class_name
          
          # Convert cell class name to Compose view name
          # Remove common suffixes and add appropriate naming
          view_name = class_name
          
          # Remove common UIKit/Android suffixes
          view_name = view_name.sub(/CollectionViewCell$/, '')
          view_name = view_name.sub(/Cell$/, '')
          view_name = view_name.sub(/cell$/, '')
          
          # Convert to proper case and add View suffix if needed
          view_name = to_pascal_case(view_name)
          view_name += 'View' unless view_name.end_with?('View')
          
          view_name
        end
        
        def self.to_pascal_case(str)
          return str if str.nil? || str.empty?

          # Handle snake_case or kebab-case to PascalCase
          # Preserve existing PascalCase/camelCase (uppercase first letter without downcasing rest)
          parts = str.split(/[_-]/)
          parts.map { |x| x.empty? ? x : x[0].upcase + x[1..-1].to_s }.join
        end

        # Extract a valid Kotlin class name from a cell view name that may contain subdirectory paths
        # e.g., "chat/message_cell" -> "MessageCell", "simple_cell" -> "SimpleCell"
        def self.cell_class_name(cell_view_name)
          return nil unless cell_view_name
          # Take only the filename part (after last /)
          basename = cell_view_name.include?('/') ? cell_view_name.split('/').last : cell_view_name
          to_pascal_case(basename)
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