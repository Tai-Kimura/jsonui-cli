# frozen_string_literal: true

require_relative '../helpers/content_inset_helper'
require_relative '../helpers/modifier_builder'
require_relative '../../core/normalization'
require_relative '../../core/string_literals'
require_relative '../../core/attribute_types'
require_relative '../../core/enum_spelling'

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
        # Every arm that emits a cell has to give it the address the test
        # drivers use — `{collectionId}_item_{index}`, what `tapItem` and
        # `waitFor` resolve. The rule lived inline in five arms and was simply
        # absent from two others (FlowRow, and the non-lazy horizontal Row),
        # so whether a cell could be addressed depended on the Collection's
        # `layout` value. It should not: `layout` says how cells are arranged,
        # not whether a test can reach them.
        #
        # One place, so the next arm inherits the rule instead of having to
        # remember it. `index_expr` is the loop variable that arm happens to
        # bind ($cellIndex / $index / $page); `extra` is any modifier chain
        # that arm needs after the tag; `lead` any it needs before the tag
        # (the pager's page padding).
        def self.cell_test_tag_modifier(collection_id, index_expr, depth, extra = '', lead: '')
          tag = collection_id ? ".testTag(\"#{JsonUIShared::StringLiterals.kotlin_body(collection_id)}_item_\$#{index_expr}\")" : ''
          indent("modifier = Modifier#{lead}#{tag}#{extra}", depth)
        end

        # defaultScrollAnchor (center / bottom): where the list starts, applied
        # once, when it first has cells. The cell is counted by the scrollTo
        # rule — across the drawn sections, headers, footers and fillers not
        # counted — and scrolled to as the lazy item that holds it (4f ruling
        # 2026-09-27, round 11). Until jsonui-cli 1.9.0 the count was the first
        # data section's cells and the result the lazy item index, so a header
        # moved the anchor and a later section was not counted.
        # `route` / `grid_columns` / `is_horizontal` as scroll_target_code.
        #
        # Under reverseLayout a lazy list rests at its visual bottom, so top
        # and bottom trade places, as they do for scrollAnchor (4f ruling
        # 2026-09-27, round 12 — where iOS lands, which draws the same order
        # from bottom-anchored content): bottom is where the list rests and
        # moves nothing; top goes to the cell drawn at the visual top — the
        # last one the content emits, which is the first section's last cell
        # when the sections are emitted last-first. Until jsonui-cli 1.9.0
        # bottom went to the last cell, which a reversed list draws at its
        # visual top.
        #
        # `non_lazy` as scroll_to_effect's: a non-lazy container that draws no
        # reverseLayout (the wrapContent Column) rests at its top, and the cell
        # goes to its top edge (collectionScrollToCell anchor 0), as
        # scrollToItem puts a lazy item. `non_lazy_reversed`: the vertical
        # EAGER CollectionStack under reverseLayout, which draws it (round 13):
        # it rests at its bottom, its anchor is the lazy list's (top and bottom
        # traded), and the cell goes where scrollToItem puts a reversed lazy
        # item — the start edge, its bottom (anchor 2).
        def self.default_scroll_anchor_code(json_data, state_var, depth, required_imports, sections: [], route: :stack,
                                            grid_columns: nil, is_horizontal: false, non_lazy: nil, non_lazy_reversed: false)
          lazy_anchor = non_lazy == :only ? nil : resting_default_anchor(json_data)
          declared = json_data['defaultScrollAnchor'].to_s
          eager_anchor = if !non_lazy then nil
                         elsif non_lazy_reversed then resting_default_anchor(json_data)
                         elsif %w[center bottom].include?(declared) then declared
                         end
          return '' unless lazy_anchor || eager_anchor

          property_name = class_list_items_property(json_data)
          return '' unless property_name

          required_imports&.add(:remember_state)
          required_imports&.add(:launched_effect)

          count = scroll_cell_count_expr(json_data, sections, route, is_horizontal)
          return '' unless count

          reversed_sections = json_data['reverseLayout'] == true && sections.any? && %i[stack grid].include?(route)
          last_emitted = "#{scroll_lists_expr(json_data, sections, route, is_horizontal)}.firstOrNull { it.isNotEmpty() }?.let { it.size - 1 } ?: 0"
          eager_code = lambda do |level|
            cell = if eager_anchor == 'center' then 'defaultAnchorCount / 2'
                   elsif non_lazy_reversed && reversed_sections then last_emitted
                   else 'defaultAnchorCount - 1'
                   end
            indent("collectionScrollToCell(#{cell}, #{non_lazy_reversed ? 2 : 0}, false)", level) + "\n"
          end
          lazy_code = lambda do |level|
            cell = if lazy_anchor == 'center' then 'defaultAnchorCount / 2'
                   elsif reversed_sections then last_emitted
                   else 'defaultAnchorCount - 1'
                   end
            out = indent("val cell = #{cell}", level) + "\n"
            out += scroll_item_code(json_data, sections, level - 1, route: route, grid_columns: grid_columns, is_horizontal: is_horizontal)
            out + indent("if (index >= 0) #{state_var}.scrollToItem(index)", level) + "\n"
          end

          code = indent("val defaultAnchorCount = #{count}", depth) + "\n"
          code += indent("val defaultAnchorApplied = remember { mutableStateOf(false) }", depth) + "\n"
          code += indent("LaunchedEffect(defaultAnchorCount) {", depth) + "\n"
          code += indent("if (!defaultAnchorApplied.value && defaultAnchorCount > 0) {", depth + 1) + "\n"
          if non_lazy.is_a?(String) && eager_anchor && lazy_anchor
            code += indent("if (#{non_lazy}) {", depth + 2) + "\n"
            code += eager_code.call(depth + 3)
            code += indent("} else {", depth + 2) + "\n"
            code += lazy_code.call(depth + 3)
            code += indent("}", depth + 2) + "\n"
          elsif non_lazy.is_a?(String)
            code += indent("if (#{eager_anchor ? '' : '!'}(#{non_lazy})) {", depth + 2) + "\n"
            code += eager_anchor ? eager_code.call(depth + 3) : lazy_code.call(depth + 3)
            code += indent("}", depth + 2) + "\n"
          elsif eager_anchor
            code += eager_code.call(depth + 2)
          else
            code += lazy_code.call(depth + 2)
          end
          code += indent("defaultAnchorApplied.value = true", depth + 2) + "\n"
          code += indent("}", depth + 1) + "\n"
          code += indent("}", depth) + "\n"
          code
        end

        # defaultScrollAnchor as a lazy list rests (default_scroll_anchor_code):
        # center / bottom, top and bottom traded under reverseLayout; nil when
        # it moves nothing.
        def self.resting_default_anchor(json_data)
          anchor = json_data['defaultScrollAnchor'].to_s
          anchor = { 'top' => 'bottom', 'bottom' => 'top' }.fetch(anchor, anchor) if json_data['reverseLayout'] == true
          %w[center bottom].include?(anchor) ? anchor : nil
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
        # item's start relative to the viewport start (a NEGATIVE offset
        # pushes it down). Until jsonui-cli 1.9.0 `center` was half a
        # viewport and `bottom` a full one, which put the target's TOP at the
        # viewport's middle and bottom edge — below the edge, for bottom; the
        # offsets now take the item's own size (anchored_scroll_code).
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

        # `scrollAnimated`, one answer for both programmatic-scroll paths (the
        # grid and the CollectionStack): a binding decides at run time; a
        # literal `false` jumps (`scrollToItem`); absent or `true` animates,
        # the declared default. sjui calls `scrollProxy.scrollTo` outside
        # `withAnimation` for a literal false and rjui passes `false` to
        # `scrollCollectionToItem`. Until 1.9.0 only a binding was read here,
        # so a literal false still animated on both paths (measured on
        # 8e4ea3ea, 2026-09-26; ticket
        # collection-attributes-declared-but-not-drawn-on-some-paths).
        #
        # A binding reads as kjui's other boolean bindings (BoundValue.bool):
        # a property declared without a default is `Boolean?`, and an unset
        # value is false — `(data.x ?: false)`, as sjui's `(data.x ?? false)`
        # and rjui's `=== true` read it. The bare `data.x` did not compile
        # against `Boolean?` (measured on 6bdb6aba, 2026-09-26).
        # Returns [:binding, Kotlin Boolean expression] / [:jump, nil] / [:animate, nil].
        def self.scroll_animated_mode(json_data)
          value = json_data['scrollAnimated']
          if value.is_a?(String) && value.match?(/@\{([^}]+)\}/)
            [:binding, Helpers::BoundValue.bool(value)]
          elsif value == false
            [:jump, nil]
          else
            [:animate, nil]
          end
        end

        # What `scrollTo` names, as the lazy item index to scroll to (4f ruling
        # 2026-09-27; the SSoT's Collection.scrollTo, jsonui-cli 1.9.0): an
        # Int is a CELL counted across the drawn sections in section order —
        # a section's header or footer item, and the grid's filler item that
        # ends a part-filled row, is not a cell; a String (cellIdProperty) is
        # the first cell, in section order, whose key — its `cellId`, else
        # its cellIdProperty value — it is. Until jsonui-cli 1.9.0 the value
        # was the lazy item index itself, which counts every header, footer
        # and filler item, and a String was read as that index, so a key
        # scrolled nowhere.
        #
        # A String no cell has as its key, on a Collection with
        # cellIdProperty, is read as it was before jsonui-cli 1.9.0: digits,
        # then optionally `#` and anything (the re-send nonce), as the lazy
        # item index. A consuming Android screen asks its keyed,
        # reverse-laid-out list for its bottom-most item with `"0#<time>"`;
        # read as a cell, "0" would be section 0's first cell, which is not
        # the bottom-most item when a later section has cells. The ruling
        # speaks of an Int and of a key, and this is neither; the reading is
        # the Kotlin paths' own (the SSoT says so) and the other paths scroll
        # nowhere for it.
        #
        # The item index is found by walking the sections in the order the
        # lazy content emits them (reversed under reverseLayout) with the
        # same conditions the content emits its items under: a declared
        # header or footer is an item when its section has that data; on a
        # grid of two or more cell sections a filler item precedes a
        # section's cells when the row before is part filled (`gridLineFill`
        # in the grid body, whose arithmetic this repeats).
        #
        # The declared class decides what the value names (4f ruling
        # 2026-09-27, round 14; the SSoT's Collection.scrollTo): a number is a
        # cell's index, counted across the drawn sections, with or without
        # cellIdProperty; a String is a cell's key — its `cellId`, else its
        # cellIdProperty value when one is set — and the first cell, in section
        # order, that has it. A cell with no key has none. The emit reads the
        # value's runtime class (`is Number`), which is the declared one.
        # Until jsonui-cli 1.9.0 kjui read every value as its text: with
        # cellIdProperty an Int was looked up as a key first and then read as
        # the lazy item index, never as a cell (round 11).
        #
        # A value that names no cell scrolls nowhere — with one exception, ruled
        # (4f 2026-09-27, round 11): a String that is no cell's key and is
        # `<digits>` or `<digits>#<anything>` is read as the legacy lazy item
        # index, and a debuggable app is told so, with the migration (a key, or
        # the cell index). The lazy routes read it (list, grid, pager — a page
        # is its item); a flow has no lazy item, and there such a String
        # scrolls nowhere, as on iOS and the web.
        #
        # The Kotlin lines of the effect after `raw`, ending in `val index`
        # (`val cell` on the flow route), or nil when the shape has nothing
        # to scroll to (no items binding, no drawn section). `prop` is the
        # bound property.
        #   route :stack — the CollectionStack lazy content
        #   route :grid  — the LazyVerticalGrid / LazyHorizontalGrid sections
        #   route :class_list — the grid's class-list body (no sections)
        #   route :pager — the HorizontalPager: a page is a cell
        #   route :flow  — the FlowRow(s): the cell alone
        # `legacy` overrides whether the legacy form is read: true / false, or
        # a Kotlin condition (the CollectionStack whose bound mode may be
        # EAGER, which has no lazy item); `item` whether the lazy item index
        # follows (false on the non-lazy containers: the cell alone).
        def self.scroll_target_code(json_data, sections, depth, prop:, route:, grid_columns: nil, is_horizontal: false,
                                    legacy: nil, item: nil)
          property_name = class_list_items_property(json_data)
          return nil unless property_name

          lists = scroll_lists_expr(json_data, sections, route, is_horizontal, enrich: true)
          return nil unless lists

          cell_id_prop = scroll_cell_id_property(json_data)
          key = cell_id_prop ? "((it[\"cellId\"] as? String) ?: (it[#{cell_id_prop.to_json}] as? String))" : '(it["cellId"] as? String)'
          lines = []
          add = ->(text) { lines << indent(text, depth + 1) }
          digits = 'raw.substringBefore("#").takeIf { it.isNotEmpty() && it.all(Char::isDigit) }?.toIntOrNull()'
          legacy = route != :flow if legacy.nil?
          item = route != :flow if item.nil?
          add.call("val scrollValue: Any? = data.#{prop}")
          add.call("val cell = if (scrollValue is Number) scrollValue.toInt() else #{lists}.flatten().indexOfFirst { #{key} == raw }")
          if legacy
            id = JsonUIShared::StringLiterals.kotlin_body((json_data['id'] || '(unnamed)').to_s)
            gate = legacy.is_a?(String) ? "#{legacy} && " : ''
            add.call("val legacyIndex = if (#{gate}scrollValue !is Number && cell < 0) #{digits} else null")
            add.call('if (cell < 0 && legacyIndex == null) return@LaunchedEffect')
            add.call("if (legacyIndex != null && scrollToDebug) android.util.Log.w(\"Collection\", \"Collection #{id}: scrollTo \\\"$raw\\\" is no cell's key — read as the legacy lazy item index $legacyIndex. \" +")
            add.call("    \"Scroll by a cell's key, or by its index among the cells (jsonui-cli 1.9.0, Collection.scrollTo).\")")
          else
            add.call('if (cell < 0) return@LaunchedEffect')
          end
          return lines.join("\n") + "\n" unless item

          lines.join("\n") + "\n" + scroll_item_code(json_data, sections, depth, route: route, grid_columns: grid_columns,
                                                               is_horizontal: is_horizontal, prefix: legacy ? 'legacyIndex ?: ' : '')
        end

        def self.scroll_cell_id_property(json_data)
          prop = json_data['cellIdProperty']
          prop.is_a?(String) && !prop.empty? ? prop : nil
        end

        # The drawn cells' lists, in section order, as a Kotlin
        # List<List<Map<String, Any>>> — each declared section that draws a
        # cell (its data section's cells, enriched with cellIds under
        # autoChangeTrackingId when `enrich`); with no sections, the class-list
        # shape's every data section, the first on a horizontal route (and the
        # pager and the flow), or the one list an array-typed items is. nil
        # when none is drawn.
        def self.scroll_lists_expr(json_data, sections, route, is_horizontal, enrich: false)
          property_name = class_list_items_property(json_data)
          return nil unless property_name

          cell_id_prop = scroll_cell_id_property(json_data)
          enriching = enrich && json_data['autoChangeTrackingId'] == true && cell_id_prop
          sections_expr = scroll_sections_expr(property_name)
          if sections.any?
            drawn = sections.each_with_index.select { |section, _| section.is_a?(Hash) && section['cell'] }.map(&:last)
            return nil if drawn.empty?

            lists = drawn.map do |i|
              list = "#{sections_expr}.getOrNull(#{i})?.cells?.data.orEmpty()"
              enriching ? "com.kotlinjsonui.utils.CellIdGenerator.enrichCellIds(#{list}, #{cell_id_prop.to_json})" : list
            end
            return "listOf(#{lists.join(', ')})"
          end

          names = class_list(json_data)
          return nil unless names && names[0]

          array = class_list_array_expr(json_data, names[0])
          if array then "listOf(#{array})"
          elsif is_horizontal || %i[pager flow].include?(route) then "listOf(#{sections_expr}.firstOrNull()?.cells?.data.orEmpty())"
          else "#{sections_expr}.map { it.cells?.data.orEmpty() }"
          end
        end

        def self.scroll_sections_expr(property_name)
          if Helpers::ResourceResolver.generated_property_nullable?(property_name)
            "data.#{property_name}?.sections.orEmpty()"
          else
            "data.#{property_name}.sections"
          end
        end

        # The drawn cells, counted (composable scope), or nil.
        def self.scroll_cell_count_expr(json_data, sections, route, is_horizontal)
          lists = scroll_lists_expr(json_data, sections, route, is_horizontal)
          lists && "#{lists}.sumOf { it.size }"
        end

        # `val index`: the lazy item that holds `cell` (the cell counted in
        # section order), or -1. The item index is found by walking the
        # sections in the order the lazy content emits them (reversed under
        # reverseLayout) with the same conditions the content emits its items
        # under: a declared header or footer is an item when its section has
        # that data; on a grid of two or more cell sections a filler item
        # precedes a section's cells when the row before is part filled
        # (`gridLineFill` in the grid body, whose arithmetic this repeats).
        # The class-list grid: a header item, then the cells; the pager: a
        # page per cell. `prefix` goes before the walk (the legacy reading).
        def self.scroll_item_code(json_data, sections, depth, route:, grid_columns: nil, is_horizontal: false, prefix: '')
          lines = []
          add = ->(text, level = 0) { lines << indent(text, depth + 1 + level) }
          if route == :pager || route == :class_list
            lists = scroll_lists_expr(json_data, sections, route, is_horizontal)
            header = route == :class_list && (names = class_list(json_data)) && names[1] && !is_horizontal ? '1 + ' : ''
            if prefix.empty?
              add.call("if (cell < 0 || cell >= #{lists}.sumOf { it.size }) return@LaunchedEffect")
              add.call("val index = #{header}cell")
            else
              add.call("if (legacyIndex == null && cell >= #{lists}.sumOf { it.size }) return@LaunchedEffect")
              add.call("val index = #{prefix}(#{header}cell)")
            end
            return lines.join("\n") + "\n"
          end

          drawn = sections.each_with_index.select { |section, _| section.is_a?(Hash) && section['cell'] }.map(&:last)
          add.call("val scrollSections = #{scroll_sections_expr(class_list_items_property(json_data))}")
          ordered = json_data['reverseLayout'] == true ? drawn.reverse : drawn
          line_breaks = route == :grid && drawn.size > 1
          columns_info = columns_emit_info(json_data)
          default_columns = columns_info[:literal] || grid_columns
          units = columns_info[:is_binding] ? "(#{columns_info[:expr]}).coerceAtLeast(1)" : grid_columns.to_s
          add.call("val index = #{prefix}run {")
          # The cell's section (declaration order) and its place in it.
          add.call('var rest = cell', 1)
          add.call("val target = intArrayOf(#{drawn.join(', ')}).firstOrNull { s ->", 1)
          add.call('val size = scrollSections.getOrNull(s)?.cells?.data?.size ?: 0', 2)
          add.call('if (rest < size) true else { rest -= size; false }', 2)
          add.call('} ?: return@run -1', 1)
          add.call('var item = 0', 1)
          add.call('var fill = 0', 1) if line_breaks
          ordered.each do |i|
            section = sections[i]
            add.call("scrollSections.getOrNull(#{i})?.let { section ->", 1)
            if section['header']
              add.call(line_breaks ? 'if (section.header != null) { item += 1; fill = 0 }' : 'if (section.header != null) item += 1', 2)
            end
            add.call('section.cells?.let { cells ->', 2)
            add.call('if (fill != 0) { item += 1; fill = 0 }', 3) if line_breaks
            add.call("if (target == #{i}) return@run item + rest", 3)
            add.call('item += cells.data.size', 3)
            if line_breaks
              span = columns_info[:is_binding] ? 1 : grid_columns / (section['columns'] || default_columns)
              add.call("fill = (fill + cells.data.size * #{span}) % #{units}", 3)
            end
            add.call('}', 2)
            if section['footer']
              add.call(line_breaks ? 'if (section.footer != null) { item += 1; fill = 0 }' : 'if (section.footer != null) item += 1', 2)
            end
            add.call('}', 1)
          end
          add.call('-1', 1)
          add.call('}')
          lines.join("\n") + "\n"
        end

        # The scrollTo effect of a route (`target` :grid / :stack / :pager /
        # :flow), or '' when the Collection has no scrollTo binding or the
        # shape has nothing to scroll to. `state` is the route's state
        # variable, declared by the caller.
        #
        # It runs on a CHANGE of the bound value (4f ruling 2026-09-27, round
        # 11): the value a Collection first composes with names no scroll, as
        # SwiftUI's `.onChange(of:)` reads it — a list with a header and an
        # initial 0 stays at its top. Until jsonui-cli 1.9.0 the first
        # composition scrolled too (LaunchedEffect runs on entering).
        #
        # `non_lazy` — the containers that scroll without a lazy list (4f
        # ruling 2026-09-27, round 12): :only for a route that is one (target
        # :non_lazy, the wrapContent Column; the CollectionStack declared
        # EAGER), or the Kotlin condition under which the CollectionStack's
        # bound mode is EAGER. There the cell is scrolled to by where it was
        # laid out (non_lazy_scroll_prelude), and the legacy form names no
        # cell: such a container has no lazy item.
        def self.scroll_to_effect(json_data, sections, depth, required_imports, target:, state: nil, grid_columns: nil, is_horizontal: false,
                                  non_lazy: nil, pager_legs: nil)
          raw_binding = json_data['scrollTo']
          return '' unless raw_binding.is_a?(String) && (prop = raw_binding[/\A@\{([^}]+)\}\z/, 1])

          route = target == :grid ? (sections.any? ? :grid : :class_list) : target
          route = sections.any? ? :stack : :class_list if target == :non_lazy
          only_non_lazy = non_lazy == :only || target == :non_lazy
          resolution = if only_non_lazy
                         scroll_target_code(json_data, sections, depth, prop: prop, route: route, is_horizontal: is_horizontal,
                                            legacy: false, item: false)
                       elsif non_lazy
                         scroll_target_code(json_data, sections, depth, prop: prop, route: route, grid_columns: grid_columns,
                                            is_horizontal: is_horizontal, legacy: "!(#{non_lazy})")
                       else
                         scroll_target_code(json_data, sections, depth, prop: prop, route: route, grid_columns: grid_columns, is_horizontal: is_horizontal)
                       end
          return '' unless resolution

          required_imports&.add(:remember_state)
          required_imports&.add(:launched_effect)
          code = indent('val scrollToArmed = remember { mutableStateOf(false) }', depth) + "\n"
          if target != :flow && !only_non_lazy
            code += indent('val scrollToDebug = (androidx.compose.ui.platform.LocalContext.current.applicationInfo.flags and ' \
                           'android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0', depth) + "\n"
          end
          code += indent("LaunchedEffect(data.#{prop}) {", depth) + "\n"
          code += indent('// A change scrolls; the value the Collection first composes with does not (jsonui-cli 1.9.0).', depth + 1) + "\n"
          code += indent('if (!scrollToArmed.value) { scrollToArmed.value = true; return@LaunchedEffect }', depth + 1) + "\n"
          code += indent("val raw = data.#{prop}#{Helpers::BoundValue.string_typed?(prop) ? '.orEmpty()' : '?.toString().orEmpty()'}", depth + 1) + "\n"
          code += indent('if (raw.isEmpty()) return@LaunchedEffect', depth + 1) + "\n"
          code += resolution
          non_lazy_call = "collectionScrollToCell(cell, #{non_lazy_anchor_mode(json_data)}, #{non_lazy_animate_expr(json_data)})"
          if only_non_lazy
            return code + indent(non_lazy_call, depth + 1) + "\n" + indent('}', depth) + "\n"
          end
          if non_lazy
            code += indent("if (#{non_lazy}) {", depth + 1) + "\n"
            code += indent("if (cell >= 0) #{non_lazy_call}", depth + 2) + "\n"
            code += indent('return@LaunchedEffect', depth + 2) + "\n"
            code += indent('}', depth + 1) + "\n"
          end
          code += case target
                  when :pager then pager_scroll_code(json_data, depth + 1, pager_legs)
                  when :flow then flow_scroll_code(json_data, depth + 1)
                  else
                    indent('if (index < 0) return@LaunchedEffect', depth + 1) + "\n" +
                      anchored_scroll_code(json_data, state, depth + 1,
                                           size: target == :grid ? (is_horizontal ? 'size.width' : 'size.height') : 'size')
                  end
          code + indent('}', depth) + "\n"
        end

        # scrollAnchor on a non-lazy container, as collectionScrollToCell
        # takes it: 0 top, 1 center, 2 bottom (the default). These containers
        # draw no reverseLayout, so the anchor is the declared one.
        def self.non_lazy_anchor_mode(json_data)
          anchor = JsonUIShared::EnumSpelling.lowered(json_data['scrollAnchor'] || DEFAULT_SCROLL_ANCHOR, 'Collection', 'scrollAnchor').to_s
          { 'top' => 0, 'center' => 1 }.fetch(anchor, 2)
        end

        # scrollAnimated as a Kotlin Boolean (scroll_animated_mode).
        def self.non_lazy_animate_expr(json_data)
          mode, expr = scroll_animated_mode(json_data)
          case mode
          when :binding then expr
          when :jump then 'false'
          else 'true'
          end
        end

        # The scroll of a container that is not a lazy list — the EAGER
        # CollectionStack, the wrapContent Column (4f rulings 2026-09-27, round
        # 12) — for its scrollTo and defaultScrollAnchor: its ScrollState, the
        # viewport's and each cell's coordinates as they are laid out (the
        # cells by their place among the drawn cells), and
        # `collectionScrollToCell(cell, anchor, animate)`, which lands the cell
        # along the axis (anchor 0 top — its leading edge at the viewport's —,
        # 1 center, 2 bottom — its trailing edge at the viewport's), waiting a
        # few frames for a cell that arrived with the value. The viewport and
        # the cells are recorded by `collectionViewport[0]` /
        # `collectionCellPlaces[n]` modifiers the caller emits.
        # `reversed`: the vertical EAGER CollectionStack under reverseLayout,
        # whose scroll runs from its bottom (reverseScrolling, round 13) — a
        # move down the content is a smaller value.
        # `gate`: a Kotlin Boolean that says the container scrolls at run time
        # (a bound `lazy` that is not NONE); the scroll does nothing when false.
        def self.non_lazy_scroll_prelude(depth, required_imports, is_horizontal:, reversed: false, gate: nil)
          required_imports&.add(:remember_state)
          required_imports&.add(:on_globally_positioned)
          lines = []
          add = ->(text, level = 0) { lines << indent(text, depth + level) }
          add.call('val collectionScroll = androidx.compose.foundation.rememberScrollState()')
          add.call('val collectionCellPlaces = remember { mutableMapOf<Int, androidx.compose.ui.layout.LayoutCoordinates>() }')
          add.call('val collectionViewport = remember { arrayOfNulls<androidx.compose.ui.layout.LayoutCoordinates>(1) }')
          if is_horizontal
            add.call('val collectionRtl = androidx.compose.ui.platform.LocalLayoutDirection.current == androidx.compose.ui.unit.LayoutDirection.Rtl')
          end
          add.call('val collectionScrollToCell: suspend (Int, Int, Boolean) -> Unit = { cell, anchor, animate ->')
          add.call("if (#{gate}) {", 1) if gate
          lines_before_body = lines.size
          add.call('var frames = 0', 1)
          add.call('while ((collectionCellPlaces[cell]?.isAttached != true || collectionViewport[0]?.isAttached != true) && frames < 10) {', 1)
          add.call('frames++', 2)
          add.call('androidx.compose.runtime.withFrameNanos { }', 2)
          add.call('}', 1)
          add.call('val viewport = collectionViewport[0]?.takeIf { it.isAttached }', 1)
          add.call('val placed = collectionCellPlaces[cell]?.takeIf { it.isAttached }', 1)
          add.call('if (viewport != null && placed != null) {', 1)
          add.call('val at = viewport.localPositionOf(placed, androidx.compose.ui.geometry.Offset.Zero)', 2)
          if is_horizontal
            add.call('val size = placed.size.width', 2)
            add.call('val lead = if (collectionRtl) viewport.size.width - (at.x.toInt() + size) else at.x.toInt()', 2)
          else
            add.call('val size = placed.size.height', 2)
            add.call('val lead = at.y.toInt()', 2)
          end
          add.call('val span = collectionScroll.viewportSize - size', 2)
          add.call('val shift = lead - (if (anchor == 1) span / 2 else if (anchor == 2) span else 0)', 2)
          add.call(reversed ? 'val to = (collectionScroll.value - shift).coerceIn(0, collectionScroll.maxValue)' : 'val to = (collectionScroll.value + shift).coerceAtLeast(0)', 2)
          add.call('if (animate) collectionScroll.animateScrollTo(to) else collectionScroll.scrollTo(to)', 2)
          add.call('}', 1)
          if gate
            (lines_before_body...lines.size).each { |i| lines[i] = "    #{lines[i]}" }
            add.call('}', 1)
          end
          add.call('}')
          lines.join("\n") + "\n"
        end

        # The animate / jump call, as scrollAnimated says: [binding, jump,
        # animate] → a Kotlin statement around `call` (a lambda of the method
        # name).
        def self.scroll_call(json_data, call)
          mode, expr = scroll_animated_mode(json_data)
          case mode
          when :binding then "if (#{expr}) #{call.call(true)} else #{call.call(false)}"
          when :jump then call.call(false)
          else call.call(true)
          end
        end

        # Where the target lands: scrollAnchor (default bottom) along the main
        # axis — top: the item's start at the viewport's start; center: its
        # middle at the middle; bottom: its end at the viewport's end — which
        # is what SwiftUI's ScrollViewReader anchors and the web's
        # scrollCollectionToCell compute. Under reverseLayout the list starts
        # at its bottom, so top and bottom trade places. The offset needs the
        # item's size: the item's own when it is laid out, else the laid-out
        # items' average for the scroll, corrected once it is laid out.
        # Until jsonui-cli 1.9.0 the offset was the viewport or half of it,
        # so `bottom` put the target's top at the viewport's bottom edge
        # (measured, 4f round 11).
        def self.anchored_scroll_code(json_data, state, depth, size:)
          anchor = JsonUIShared::EnumSpelling.lowered(json_data['scrollAnchor'] || DEFAULT_SCROLL_ANCHOR, 'Collection', 'scrollAnchor').to_s
          anchor = DEFAULT_SCROLL_ANCHOR unless %w[top center bottom].include?(anchor)
          anchor = { 'top' => 'bottom', 'bottom' => 'top' }.fetch(anchor, anchor) if json_data['reverseLayout'] == true
          if anchor == 'top'
            return indent(scroll_call(json_data, ->(animate) { "#{state}.#{animate ? 'animateScrollToItem' : 'scrollToItem'}(index)" }), depth) + "\n"
          end

          offset = anchor == 'center' ? '-(scrollViewport - it) / 2' : '-(scrollViewport - it)'
          code = indent("val scrollViewport = #{state}.layoutInfo.viewportEndOffset - #{state}.layoutInfo.viewportStartOffset", depth) + "\n"
          code += indent("val scrollOffset: (Int) -> Int = { #{offset} }", depth) + "\n"
          code += indent("val scrollSize = #{state}.layoutInfo.visibleItemsInfo.let { items -> items.firstOrNull { it.index == index }?.let { it.#{size} } " \
                         "?: items.map { it.#{size} }.average().let { if (it.isNaN()) 0 else it.toInt() } }", depth) + "\n"
          code += indent(scroll_call(json_data, ->(animate) { "#{state}.#{animate ? 'animateScrollToItem' : 'scrollToItem'}(index, scrollOffset(scrollSize))" }), depth) + "\n"
          code + indent("#{state}.layoutInfo.visibleItemsInfo.firstOrNull { it.index == index }?.let { it.#{size} }?.let { if (it != scrollSize) #{state}.scrollToItem(index, scrollOffset(it)) }", depth) + "\n"
        end

        # The pager: the page is the cell (pageCount from the pager's own
        # sources); no anchor — a page fills the pager.
        #
        # A pager whose page is bound or whose page change is handled
        # (`legs`) scrolls as its currentPage effect does: quiet while the
        # scroll is in flight, the landing told once (pager_programmatic_scroll).
        # Through jsonui-cli 1.9.5 a scrollTo from 0 to 6 of 7 pages told the
        # callback [5, 6] and wrote 5 and 6 back (measured on a device).
        def self.pager_scroll_code(json_data, depth, legs = nil)
          call = scroll_call(json_data, ->(animate) { "pagerState.#{animate ? 'animateScrollToPage' : 'scrollToPage'}(index)" })
          code = indent('if (index !in 0 until pageCount) return@LaunchedEffect', depth) + "\n"
          return code + indent(call, depth) + "\n" unless legs

          code + pager_programmatic_scroll(call, nil, legs, depth)
        end

        # A programmatic scroll of the pager: the pager -> VM leg (the
        # write-back and the page callback, generate_paging_horizontal) is
        # quiet while it is in flight, and its landing is told once after it —
        # written back if the bound page differs, handed to the callback if
        # the page moved. A cancelled scroll tells nothing. `guard` wraps the
        # scroll in a condition (the currentPage effect's `from != target`).
        def self.pager_programmatic_scroll(call, guard, legs, depth)
          page_prop, handled = legs.values_at(:page_prop, :handled)
          code = indent('val from = pagerState.currentPage', depth) + "\n"
          inner = depth
          if guard
            code += indent("if (#{guard}) {", depth) + "\n"
            inner += 1
          end
          code += indent('programmaticScroll = true', inner) + "\n"
          code += indent('try {', inner) + "\n"
          code += indent(call, inner + 1) + "\n"
          code += indent('} finally {', inner) + "\n"
          code += indent('programmaticScroll = false', inner + 1) + "\n"
          code += indent('}', inner) + "\n"
          code += indent('}', depth) + "\n" if guard
          if page_prop
            code += indent("if (data.#{page_prop} != pagerState.currentPage) viewModel.updateData(mapOf(\"#{page_prop}\" to pagerState.currentPage))", depth) + "\n"
          end
          code += indent('if (pagerState.currentPage != from) pageChangeHandler?.invoke(pagerState.currentPage)', depth) + "\n" if handled
          code
        end

        # The flow: the cell's place in the scrolled content, recorded as it
        # was laid out (flowCellTargets, flowContent — generate_flow_layout),
        # scrolled to by scrollAnchor along the column (a flow is not
        # reversed).
        def self.flow_scroll_code(json_data, depth)
          anchor = JsonUIShared::EnumSpelling.lowered(json_data['scrollAnchor'] || DEFAULT_SCROLL_ANCHOR, 'Collection', 'scrollAnchor').to_s
          anchor = DEFAULT_SCROLL_ANCHOR unless %w[top center bottom].include?(anchor)
          place = case anchor
                  when 'center' then 'top - (flowScrollState.viewportSize - size) / 2'
                  when 'bottom' then 'top - (flowScrollState.viewportSize - size)'
                  else 'top'
                  end
          code = indent('val content = flowContent[0]?.takeIf { it.isAttached } ?: return@LaunchedEffect', depth) + "\n"
          code += indent('val placed = flowCellTargets[cell]?.takeIf { it.isAttached } ?: return@LaunchedEffect', depth) + "\n"
          code += indent('val top = content.localPositionOf(placed, androidx.compose.ui.geometry.Offset.Zero).y.toInt()', depth) + "\n"
          code += indent('val size = placed.size.height', depth) + "\n"
          code += indent("val y = (#{place}).coerceAtLeast(0)", depth) + "\n"
          code + indent(scroll_call(json_data, ->(animate) { "flowScrollState.#{animate ? 'animateScrollTo' : 'scrollTo'}(y)" }), depth) + "\n"
        end

        # The keys of a section's cells as one lazy list may hold them: a
        # cell's key (cellId, else the cellIdProperty value, else its index),
        # and a key an earlier cell of the section already took gets "#2",
        # "#3"… (4f ruling 2026-09-27, round 11) — Compose throws "Key … was
        # already used" on a key two items share, and two cells of one
        # section sharing a key took the list down once both were composed
        # (measured on the Android conformance host). CellIdGenerator's
        # enrichment (autoChangeTrackingId) already writes them apart, the
        # same way.
        def self.unique_keys_line(list_expr, cell_id_prop, var)
          "val #{var} = HashSet<String>().let { seen -> #{list_expr}.mapIndexed { i, cell -> " \
            "((cell[\"cellId\"] as? String) ?: (cell[#{cell_id_prop.to_json}] as? String) ?: i.toString()).let { k -> " \
            "if (seen.add(k)) k else generateSequence(2) { it + 1 }.map { \"$k\#$it\" }.first { seen.add(it) } } } }"
        end

        # A cell's lazy item key: its key (`expr`, a Kotlin String expression)
        # in section 0, "<section>:<key>" in a later one. One lazy list holds
        # every section, and Compose throws on a key two of its items share
        # ("Key … was already used") — two sections sharing a cell key, or
        # two keyless cells answering the same index, took the list down
        # once both were composed (measured on KotlinJsonUI Dynamic, which
        # keys its items the same way; 4f round 10). sjui's later sections
        # carry "<section>:" ids for the same reason (jsonui-cli round 9).
        def self.lazy_key(expr, section_index)
          section_index.to_i.positive? ? "\"#{section_index}:\" + (#{expr})" : expr
        end

        # Spacing on every horizontal Collection, one lane or many (4f ruling,
        # 2026-09-26, the rule SwiftJsonUI Dynamic dde0628 and sjui codegen
        # draw): along the scroll axis lineSpacing (its alias sectionSpacing),
        # else itemSpacing, else 0; between lanes columnSpacing, else
        # itemSpacing, else 0. Pages sit along the scroll axis. `spacing` is
        # kjui's extra spelling of itemSpacing and keeps its place after it.
        # nil where nothing is declared (Compose's own 0).
        def self.horizontal_scroll_spacing(json_data)
          json_data['lineSpacing'] || json_data['sectionSpacing'] || json_data['itemSpacing'] || json_data['spacing']
        end

        def self.horizontal_lane_spacing(json_data)
          json_data['columnSpacing'] || json_data['itemSpacing'] || json_data['spacing']
        end

        # Whether defaultScrollAnchor moves a lazy list (resting_default_anchor),
        # or — `non_lazy` — a container that is not one (the declared anchor).
        # scrollEnabled as a Kotlin Boolean ('true' when undeclared): it stops
        # the user's scrolling only; a programmatic scroll still moves the
        # container (4f ruling 2026-09-27, round 13 — as iOS's scrollDisabled).
        def self.user_scroll_enabled_expr(json_data)
          return 'true' unless json_data.key?('scrollEnabled')

          raw = json_data['scrollEnabled']
          if raw.is_a?(String) && raw.match(/@\{([^}]+)\}/)
            "data.#{$1}"
          else
            raw == false ? 'false' : 'true'
          end
        end

        # `, enabled = …` for a scroll modifier, '' when scrollEnabled is not declared.
        def self.scroll_enabled_arg(json_data)
          json_data.key?('scrollEnabled') ? ", enabled = #{user_scroll_enabled_expr(json_data)}" : ''
        end

        # A vertical list, not reversed, whose defaultScrollAnchor is bottom:
        # content shorter than the list sits at its bottom, where iOS draws it
        # (4f ruling 2026-09-27, round 14; it sat at the top).
        def self.content_at_bottom?(json_data)
          json_data['defaultScrollAnchor'] == 'bottom' && json_data['reverseLayout'] != true
        end

        # Where a horizontal list whose content is shorter than the row sits
        # along it, as a Compose Alignment.Horizontal, or nil for the start
        # (the end under reverseLayout, which the lazy containers already
        # take): defaultScrollAnchor center — its middle; bottom — its end.
        # iOS draws a short row at its leading edge / middle / trailing edge by
        # the anchor (4f ruling 2026-09-27, round 15; measured on sjui codegen
        # and SwiftJsonUI Dynamic); every Compose row sat at its start.
        # A vertical list with defaultScrollAnchor center whose content is
        # shorter than the list sits in its middle, as iOS draws it (4f ruling
        # 2026-09-27, round 16; measured round 15 on sjui codegen and
        # SwiftJsonUI Dynamic): 'Alignment.CenterVertically', or nil — the top,
        # the bottom under reverseLayout or a bottom anchor (content_at_bottom?).
        # It sat at the top (the bottom when reversed) until jsonui-cli 1.9.0.
        def self.column_content_alignment(json_data)
          'Alignment.CenterVertically' if json_data['defaultScrollAnchor'] == 'center'
        end

        def self.row_content_alignment(json_data)
          case json_data['defaultScrollAnchor']
          when 'center' then 'Alignment.CenterHorizontally'
          when 'bottom' then 'Alignment.End'
          end
        end

        def self.default_scroll_anchor?(json_data, non_lazy: false)
          anchor = non_lazy ? (%w[center bottom].include?(json_data['defaultScrollAnchor'].to_s) || resting_default_anchor(json_data)) : resting_default_anchor(json_data)
          return false unless anchor

          json_data['items'].is_a?(String) && json_data['items'].match?(/@\{[^}]+\}/)
        end

        # The listStyle chrome around one cell (51-E) — the generated code
        # emits the SAME library composable the dynamic path renders
        # (CollectionCellChrome). plain/unknown emit nothing; flow/paging
        # routes stay plain, mirroring the dynamic scope.
        def self.chrome_open(json_data, required_imports)
          style = json_data['listStyle'].to_s
          return nil unless %w[grouped insetgrouped sidebar].include?(JsonUIShared::EnumSpelling.lowered(style, 'Collection', 'listStyle'))

          required_imports&.add(:collection_cell_chrome)
          hide = json_data['hideSeparator'] == true
          "CollectionCellChrome(style = \"#{style}\", hideSeparator = #{hide}) {"
        end

        # The declared cell size lives on a WRAPPER Box, not on the cell's own
        # modifier chain: the cell root's requiredSize reports its own size to
        # the modifiers INSIDE the chain, so a clip placed after a call-site
        # .width() clips at the root's size, not the slot's, and the overflow
        # stayed visible (Collection_cellWidth__static d=30, runs
        # 31202080745/31234163967 — only the screen edge clipped it). A Box
        # measures the cell, sizes ITSELF to the declared cell frame, and
        # clips at its own bounds; the child anchors topStart — the web
        # picture (8px sliver, leading edge).
        def self.cell_size_box_open(json_data, required_imports)
          return nil unless json_data['cellWidth'] || json_data['cellHeight']

          required_imports&.add(:shape)
          mods = []
          mods << ".width(#{Helpers::BoundValue.dp(json_data['cellWidth'])})" if json_data['cellWidth']
          mods << ".height(#{Helpers::BoundValue.dp(json_data['cellHeight'])})" if json_data['cellHeight']
          "Box(modifier = Modifier#{mods.join}.clipToBounds()) {"
        end

        # `data.<prop>.sections`, with the safe calls the DECLARATION needs.
        #
        # Both hops hang off the same answer: a nullable property makes
        # `data.x` nullable, and a safe call on it makes `.sections`
        # nullable in turn, so either both are safe calls or neither is.
        # Reading the property's own nullability is the whole point — the
        # first version of this read the TYPE (CollectionDataSource declares
        # every field with a default, so the type is never null) and emitted
        # unsafe calls on properties the model had declared
        # `CollectionDataSource? = null`. That is a different proposition,
        # and downstream it was a build failure (2026-09-03). The local
        # fixtures were green throughout because none of them declares a
        # nullable collection.
        def self.sections_access(property_name)
          if Helpers::ResourceResolver.generated_property_nullable?(property_name)
            "data.#{property_name}?.sections?"
          else
            "data.#{property_name}.sections"
          end
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # `items` is declared ["array", "binding"]; what these emitters draw
          # from is the binding (the data's sections). An array names no data:
          # it is set aside here, as the sjui and rjui Collections set it
          # aside, where it used to reach `.match` and raise NoMethodError —
          # the build down (ticket kjui-codegen-table-crashes-on-an-items-array).
          unless json_data['items'].nil? || json_data['items'].is_a?(String)
            json_data = json_data.reject { |key, _| key == 'items' }
          end

          # A section's header / cell / footer names its layout. A node written
          # inline there is declared nowhere and drawn by no path (4f's ruling,
          # 1.9.0; the validator names it — inline_layout?): it is set aside,
          # where its Hash reached `.split` and the build stopped.
          if json_data['sections'].is_a?(Array)
            json_data = json_data.merge('sections' => json_data['sections'].map do |section|
              next section unless section.is_a?(Hash)

              section.reject { |key, value| %w[header cell footer].include?(key) && !value.is_a?(String) }
            end)
          end

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
          is_flow = %w[flow leftaligned].include?(JsonUIShared::EnumSpelling.lowered(layout, 'Collection', 'layout'))

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
          # It scrolls inside the height its parent bounds it to (4f ruling
          # 2026-09-27, round 12; generate_non_lazy's scroll_within_bounds).
          height_value = json_data['height']
          if !is_horizontal && height_value == 'wrapContent'
            return generate_non_lazy(json_data, sections, depth, required_imports, parent_type, scroll_within_bounds: true)
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
          required_imports&.add(:remember) # seed_view_model_line
          
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

          # Content padding: contentPadding / insets, insetHorizontal /
          # insetVertical, the safe area — the one reading the stack path takes
          # (collection_stack_content_padding_expr). This path read its own
          # copy until jsonui-cli 1.9.0: the four values in another order, and
          # no string form.
          if (padding_expr = collection_stack_content_padding_expr(json_data, is_horizontal: is_horizontal))
            code += "\n" + indent("contentPadding = #{padding_expr},", depth + 1)
          end
          
          # Item spacing
          # lineSpacing: vertical spacing between rows (minimumLineSpacing in iOS)
          # columnSpacing: horizontal spacing between columns (minimumInteritemSpacing in iOS)
          # itemSpacing/spacing: uniform spacing (fallback)
          # `sectionSpacing` is the declared alias of lineSpacing (the dynamic
          # table folds it; sjui reads both spellings) — this path read only
          # the canonical one, so the alias fixture measured a parity gap
          # against the dynamic render (d=18, run 31202080745). Canonical
          # spelling wins when both are written.
          line_spacing = json_data['lineSpacing'] || json_data['sectionSpacing'] || json_data['itemSpacing'] || json_data['spacing']
          column_spacing = json_data['columnSpacing'] || json_data['itemSpacing'] || json_data['spacing']

          if is_horizontal
            # The horizontal rule (horizontal_scroll_spacing): the scroll axis
            # (horizontalArrangement) by lineSpacing, else itemSpacing; the
            # lanes (verticalArrangement) by columnSpacing, else itemSpacing.
            # The scroll axis fell back to columnSpacing and the lanes were
            # never spaced until jsonui-cli 1.9.0.
            # A short reversed grid sits at its end, as the reversed list does
            # (4f ruling 2026-09-27, round 13; spacedBy alone packs to the start).
            # A short grid sits where defaultScrollAnchor says (row_content_alignment,
            # round 15); with no spacing the grid's own default is the start,
            # the end when reversed.
            row_alignment = row_content_alignment(json_data)
            if (along = horizontal_scroll_spacing(json_data))
              required_imports&.add(:arrangement)
              along_arg = if row_alignment then ", #{row_alignment}"
                          elsif json_data['reverseLayout'] == true then ', Alignment.End'
                          else ''
                          end
              required_imports&.add(:alignment) unless along_arg.empty?
              code += "\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(along)}#{along_arg}),", depth + 1)
            elsif row_alignment
              required_imports&.add(:arrangement)
              required_imports&.add(:alignment)
              code += "\n" + indent("horizontalArrangement = Arrangement.aligned(#{row_alignment}),", depth + 1)
            end
            # Lanes only where there are several (a bound count is the
            # sentinel 2 here): one row has nothing between it.
            if columns > 1 && (between = horizontal_lane_spacing(json_data))
              required_imports&.add(:arrangement)
              code += "\n" + indent("verticalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(between)}),", depth + 1)
            end
          elsif (content_at_bottom?(json_data) || column_content_alignment(json_data)) && !line_spacing
            required_imports&.add(:arrangement)
            along = column_content_alignment(json_data) ? 'Arrangement.Center' : 'Arrangement.Bottom'
            code += "\n" + indent("verticalArrangement = #{along},", depth + 1)
            if column_spacing
              code += "\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(column_spacing)}),", depth + 1)
            end
          elsif line_spacing || column_spacing
            required_imports&.add(:arrangement)
            # Vertical scroll: lineSpacing = vertical spacing between rows,
            # columnSpacing = horizontal spacing between columns
            # A short reversed grid sits at its bottom — where iOS draws such a
            # list, bottom-anchored (4f ruling 2026-09-27, round 13). With no
            # spacing the grid's own default is already Bottom when reversed;
            # spacedBy alone packed it to the top. Not reversed, defaultScrollAnchor
            # bottom puts short content at the bottom too, as iOS draws it (round 14).
            if line_spacing
              line_arg = if (centered = column_content_alignment(json_data)) then ", #{centered}"
                         elsif json_data['reverseLayout'] == true || content_at_bottom?(json_data) then ', Alignment.Bottom'
                         else ''
                         end
              required_imports&.add(:alignment) unless line_arg.empty?
              code += "\n" + indent("verticalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(line_spacing)}#{line_arg}),", depth + 1)
            end
            if column_spacing
              code += "\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(column_spacing)}),", depth + 1)
            end
          end

          # Parse gravity for item alignment (Box contentAlignment uses Alignment, not Alignment.Vertical/Horizontal)
          # Horizontal scroll: default is TopStart, can be Center/BottomStart
          # Vertical scroll: default is TopStart, can be TopCenter/TopEnd
          gravity = json_data['gravity']
          if is_horizontal
            # Horizontal scroll - vertical alignment
            gravity_alignment = case JsonUIShared::EnumSpelling.lowered(gravity, 'Collection', 'gravity')
            when 'center', 'centervertical'
              'Alignment.CenterStart'
            when 'bottom'
              'Alignment.BottomStart'
            else # 'top' is default for horizontal scroll
              'Alignment.TopStart'
            end
          else
            # Vertical scroll - horizontal alignment
            gravity_alignment = case JsonUIShared::EnumSpelling.lowered(gravity, 'Collection', 'gravity')
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
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          # 4. Padding last (inner spacing)
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # onItemAppear support - callback with index when cell appears
          if Helpers::ModifierBuilder.string_event_name(json_data['onItemAppear'])
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

            scroll_code = indent("val gridState = rememberLazyGridState()", depth) + "\n" +
                          indent("// Programmatic scrolling", depth) + "\n"
            scroll_code += scroll_to_effect(json_data, sections, depth, required_imports, target: :grid, state: 'gridState',
                                            grid_columns: columns, is_horizontal: is_horizontal)
            scroll_code += default_scroll_anchor_code(json_data, 'gridState', depth, required_imports, sections: sections,
                                                      route: sections.any? ? :grid : :class_list, grid_columns: columns,
                                                      is_horizontal: is_horizontal)
            code = scroll_code + code
          elsif has_default_anchor
            required_imports&.add(:lazy_grid_state)
            code = indent("val gridState = rememberLazyGridState()", depth) + "\n" +
                   default_scroll_anchor_code(json_data, 'gridState', depth, required_imports, sections: sections,
                                              route: sections.any? ? :grid : :class_list, grid_columns: columns,
                                              is_horizontal: is_horizontal) +
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
                enrichment_hoist += indent("val section#{idx} = #{sections_access(hoist_property_name)}.getOrNull(#{idx})", depth) + "\n"
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
          chrome_style = JsonUIShared::EnumSpelling.lowered(json_data['listStyle'], 'Collection', 'listStyle').to_s
          if %w[grouped insetgrouped sidebar].include?(chrome_style)
            required_imports&.add(:shape)
            required_imports&.add(:material_theme)
            if %w[insetgrouped sidebar].include?(chrome_style)
              modifiers << ".padding(horizontal = 16.dp)"
              corner = chrome_style == 'insetgrouped' ? 12 : 8
              modifiers << ".clip(RoundedCornerShape(#{Helpers::BoundValue.dp(corner)}))"
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
          elsif (names = class_list(json_data))
            code += class_list_lazy_body(json_data, names, is_horizontal, depth + 1, required_imports, gravity_alignment)
          else
            # Declaration-faithful (2026-08-02 ruling): no cell class
            # declared → nothing rendered (was a 10-item placeholder Card).
            code += "\n" + indent("// No cellClasses — nothing rendered (declaration-faithful)", depth + 1)
          end
          
          code += "\n" + indent("}", depth)
          code
        end

        # The class-list shape: `cellClasses` (with `headerClasses` /
        # `footerClasses`), `items` and no `sections`. Drawn as sjui codegen
        # draws it, from the data's own sections (CollectionDataSource, the
        # type kjui gives the property — data_model_updater.rb):
        #
        #   lazy vertical, 1 column or a grid   every data section; header before, footer after
        #   lazy horizontal, flow               the first data section; no header / footer
        #   lazy:none or wrapContent, vertical  every data section; header before, footer after
        #   lazy:none horizontal                the first data section; no header / footer
        #   paging                              nothing
        #
        # A header / footer is its view with its own ViewModel and no item
        # data, and is drawn whether or not there are items. Until 1.9.0
        # only the lazy routes drew this shape at all, reading the cells as
        # `data.<items>?.get("<cellClass>")` — a map keyed by cell class, which
        # CollectionDataSource is not, so it did not compile — through a
        # `<cellClass>View(data = …)` the cell scaffold does not have, with a
        # no-items branch that used an undeclared `item`; the lazy horizontal
        # grid drew a header and footer sjui does not; every other route drew
        # nothing (measured on 8e4ea3ea, 2026-09-26; ticket
        # collection-attributes-declared-but-not-drawn-on-some-paths).
        #
        # [cell, header, footer] as declared (the first of each; several
        # cells are the validator's to refuse), or nil when none is.
        #
        # Each attribute is read by name: `jui conformance coverage` finds
        # a face's reads by the `json_data['<attribute>']` text, and a read
        # through a key variable reads as none.
        def self.class_list(json_data)
          names = [json_data['cellClasses'], json_data['headerClasses'], json_data['footerClasses']].map do |declared|
            first = declared.is_a?(Array) ? declared.first : nil
            first = first['className'] if first.is_a?(Hash)
            first.is_a?(String) && !first.empty? ? first : nil
          end
          names.any? ? names : nil
        end

        # The `data.<items>` property the cells come from, or nil.
        def self.class_list_items_property(json_data)
          items = json_data['items']
          items.is_a?(String) ? items[/\A@\{([^}]+)\}\z/, 1] : nil
        end

        # Collection.items is a CollectionDataSource or an array (4f ruling,
        # 2026-09-26). An items property the layout DECLARES a list —
        # `Array`, `[T]` (AttributeTypes.list_element) — is one section:
        # every element with cellClasses[0], on the routes a one-section data
        # source draws. Any other declaration, or none, is the canonical
        # CollectionDataSource. The list as a Kotlin `List<Map<String, Any>>`
        # expression — what the cell's ViewModel reads (updateData takes a
        # map) — or nil when items is not a declared list: a list of the
        # cell's own Data (`[<Cell>Data]` = List<<Cell>Data>) becomes its
        # maps (`toMap()`); an untyped list (`Array` = List<Any?>) is read
        # element by element as maps. A list of any other type is named: its
        # elements are no map, so its cells draw with no data. Until
        # jsonui-cli 1.9.0 every class-list route read `.sections`, which a
        # List does not have.
        def self.class_list_array_expr(json_data, cell_name)
          property_name = class_list_items_property(json_data)
          return nil unless property_name

          element = JsonUIShared::AttributeTypes.list_element(Helpers::ResourceResolver.get_property_class(property_name))
          return nil unless element

          own_data = cell_name && "#{cell_class_name(cell_name)}Data"
          conversion =
            if !element.any? && element.name == own_data
              '.map { it.toMap() }'
            else
              unless element.any?
                Core::Logger.warn("Collection #{json_data['id'] || '(unnamed)'}: items '#{property_name}' is a list of " \
                                  "#{element.name}; a cell reads its own #{own_data || 'Data'} or a map, so its cells draw with no data.")
              end
              '.mapNotNull { it as? Map<String, Any> }'
            end
          receiver = Helpers::ResourceResolver.generated_property_nullable?(property_name) ? "data.#{property_name}.orEmpty()" : "data.#{property_name}"
          "#{receiver}#{conversion}"
        end

        # A cell's (or a section header's / footer's) ViewModel handed its
        # data BEFORE its view composes, emitted right after the
        # `viewModel(key = …)` line and before the LaunchedEffect that feeds it.
        #
        # `viewModel(key = …)` makes a fresh ViewModel for a key it has not
        # seen — a cell composed for the first time, or a cell whose key
        # moved with its contents (autoChangeTrackingId) — and the
        # LaunchedEffect runs only once the frame is composed. So that first
        # frame drew the cell from its layout's defaults (a label bound
        # `gone` by the data drew visible: a cell of another height for one
        # frame, and in a reverseLayout list every row above it jumped).
        #
        # The cell view reads `viewModel.data.collectAsState()`, whose first
        # value is the StateFlow's value when it is first composed; this runs
        # earlier in the same composition, so the view's first frame has the
        # cell's data. The data lives in a MutableStateFlow, not snapshot
        # state, so this is no composition-time snapshot write. Keyed on the
        # ViewModel and the data, it runs once per new ViewModel or new data
        # and never on a plain recomposition, so a cell's own writes to its
        # ViewModel stay until its data changes — as with the effect. It
        # returns the data rather than Unit (Compose lint RememberReturnType).
        #
        # Not `viewModel(key = …) { … }` (the initializer overload): the cell
        # ViewModel is the project's own class (an AndroidViewModel as
        # scaffolded, its constructor the project's to change), so kjui cannot
        # construct it; and a reused ViewModel would not be seeded by it.
        #
        # The LaunchedEffect stays: on the first frame it re-applies the same
        # data, which changes nothing (an equal Data; a MutableStateFlow
        # conflates it).
        def self.seed_view_model_line(view_model, data, depth)
          indent("remember(#{view_model}, #{data}) { #{view_model}.updateData(#{data}); #{data} }", depth)
        end

        # One cell, with `sectionIndex`, `cellIndex` and `currentCellData` in
        # scope: its own ViewModel fed the cell's data — the scaffold's
        # `XView(viewModel, modifier)`, as the sections path calls it.
        def self.class_list_cell(json_data, cell_name, depth, required_imports, cell_extra: '')
          cell_class = cell_class_name(cell_name)
          code = "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_class}_cell_\${sectionIndex}_\${cellIndex}_\${viewModel.hashCode()}\")", depth)
          code += "\n" + seed_view_model_line("cellViewModel", "currentCellData", depth)
          code += "\n" + indent("LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }", depth)
          on_item_appear = json_data['onItemAppear']
          if (appear_name = Helpers::ModifierBuilder.string_event_name(on_item_appear))
            code += "\n" + indent("LaunchedEffect(Unit) { data.#{Helpers::BindingExpression.path_only(appear_name)}?.invoke(cellIndex) }", depth)
          end
          closers = 0
          if (chrome = chrome_open(json_data, required_imports))
            code += "\n" + indent(chrome, depth)
            closers += 1
          end
          if (cell_box = cell_size_box_open(json_data, required_imports))
            code += "\n" + indent(cell_box, depth)
            closers += 1
          end
          code += "\n" + indent("#{cell_class}View(", depth)
          code += "\n" + indent("viewModel = cellViewModel,", depth + 1)
          code += "\n" + cell_test_tag_modifier(json_data['id'], 'cellIndex', depth + 1, cell_extra)
          code += "\n" + indent(")", depth)
          closers.times { code += "\n" + indent("}", depth) }
          code
        end

        # A header / footer view: its own ViewModel, no item data.
        def self.class_list_edge_call(class_name, role, depth)
          code = "\n" + indent("val #{role}ViewModel: #{class_name}ViewModel = viewModel(key = \"#{class_name}_#{role}_\${viewModel.hashCode()}\")", depth)
          code + "\n" + edge_view_call(class_name, "#{role}ViewModel", depth)
        end

        # A header or footer view in a row of its own: the ROW is full width
        # and the view keeps its own size at the row's start — as KotlinJsonUI
        # Dynamic draws it (the view in its row, no fill of its own), and sjui
        # (`.frame(maxWidth: .infinity, alignment: .leading)`). Until
        # jsonui-cli 1.9.0 the view itself was handed `Modifier.fillMaxWidth()`,
        # and a fixed-width root (`requiredWidth`, modifier_builder) answers a
        # fill constraint by centring itself in the row (4f ruling 2026-09-26,
        # round 8; the flow's edges took this shape in round 7).
        def self.edge_view_call(edge_class, view_model, depth)
          indent("Box(modifier = Modifier.fillMaxWidth()) { #{edge_class}View(viewModel = #{view_model}) }", depth)
        end

        def self.register_class_list_imports(names, required_imports)
          required_imports&.add(:launched_effect)
          required_imports&.add(:remember) # seed_view_model_line
          names.compact.each { |name| required_imports&.add("cell:#{name}") }
        end

        # The body of the lazy grid (a LazyGridScope): cells as `items`, a
        # header / footer as a full-width item.
        def self.class_list_lazy_body(json_data, names, is_horizontal, depth, required_imports, gravity_alignment)
          cell_name, header_name, footer_name = names
          header_name = footer_name = nil if is_horizontal
          register_class_list_imports([cell_name, header_name, footer_name], required_imports)
          property_name = class_list_items_property(json_data)
          code = ''
          if header_name
            code += "\n" + indent("item(span = { GridItemSpan(maxLineSpan) }) {", depth)
            code += class_list_edge_call(cell_class_name(header_name), 'header', depth + 1)
            code += "\n" + indent("}", depth)
          end
          if cell_name && property_name
            # The cells of the list `list` names, at depth `d`.
            cells = lambda do |d, list = 'cellData.data'|
              out = "\n" + indent("items(#{list}.size) { cellIndex ->", d)
              out += "\n" + indent("Box(", d + 1)
              out += "\n" + indent("modifier = Modifier.fillMaxSize(),", d + 2)
              out += "\n" + indent("contentAlignment = #{gravity_alignment}", d + 2)
              out += "\n" + indent(") {", d + 1)
              out += "\n" + indent("val currentCellData = #{list}[cellIndex]", d + 2)
              out += class_list_cell(json_data, cell_name, d + 2, required_imports)
              out += "\n" + indent("}", d + 1)
              out + "\n" + indent("}", d)
            end
            if (array = class_list_array_expr(json_data, cell_name))
              code += "\n" + indent("// #{cell_name}: the declared list, one section", depth)
              code += "\n" + indent("#{array}.let { cellItems ->", depth)
              code += "\n" + indent("val sectionIndex = 0", depth + 1)
              code += cells.call(depth + 1, 'cellItems')
            elsif is_horizontal
              code += "\n" + indent("// #{cell_name}: the first data section", depth)
              code += "\n" + indent("#{sections_access(property_name)}.firstOrNull()?.cells?.let { cellData ->", depth)
              code += "\n" + indent("val sectionIndex = 0", depth + 1)
              code += cells.call(depth + 1)
            else
              code += "\n" + indent("// #{cell_name}: every data section", depth)
              code += "\n" + indent("#{sections_access(property_name)}.forEachIndexed { sectionIndex, section ->", depth)
              code += "\n" + indent("section.cells?.let { cellData ->", depth + 1)
              code += cells.call(depth + 2)
              code += "\n" + indent("}", depth + 1)
            end
            code += "\n" + indent("}", depth)
          end
          if footer_name
            code += "\n" + indent("item(span = { GridItemSpan(maxLineSpan) }) {", depth)
            code += class_list_edge_call(cell_class_name(footer_name), 'footer', depth + 1)
            code += "\n" + indent("}", depth)
          end
          code
        end

        # The body of a composable container (Column / Row / FlowRow): cells
        # and a header / footer as calls. `first_only` draws the first data
        # section and no header / footer (the horizontal and flow routes);
        # `columns` > 1 (or a binding) lays the cells out in rows of that
        # many.
        # `places`: each cell records where it was laid out, by its place among
        # the drawn cells (non_lazy_scroll_prelude) — the every-section and
        # grid bodies of the wrapContent Column.
        def self.class_list_eager_body(json_data, names, depth, required_imports, first_only:, columns_info: nil, cell_extra: '',
                                       places: false)
          cell_name, header_name, footer_name = names
          header_name = footer_name = nil if first_only
          register_class_list_imports([cell_name, header_name, footer_name], required_imports)
          property_name = class_list_items_property(json_data)
          grid = columns_info && (columns_info[:is_binding] || columns_info[:literal] > 1)
          code = ''
          code += class_list_edge_call(cell_class_name(header_name), 'header', depth) if header_name
          array = cell_name && property_name && class_list_array_expr(json_data, cell_name)
          place = ->(expr) { places ? ".onGloballyPositioned { collectionCellPlaces[#{expr}] = it }" : '' }
          if array && !grid
            code += "\n" + indent("// #{cell_name}: the declared list, one section", depth)
            code += "\n" + indent("#{array}.forEachIndexed { cellIndex, currentCellData ->", depth)
            code += "\n" + indent("val sectionIndex = 0", depth + 1)
            code += class_list_cell(json_data, cell_name, depth + 1, required_imports, cell_extra: cell_extra + place.call('cellIndex'))
            code += "\n" + indent("}", depth)
          elsif cell_name && property_name
            if first_only
              code += "\n" + indent("// #{cell_name}: the first data section", depth)
              code += "\n" + indent("#{sections_access(property_name)}.firstOrNull()?.cells?.data?.forEachIndexed { cellIndex, currentCellData ->", depth)
              code += "\n" + indent("val sectionIndex = 0", depth + 1)
              code += class_list_cell(json_data, cell_name, depth + 1, required_imports, cell_extra: cell_extra)
              code += "\n" + indent("}", depth)
            elsif grid
              count = columns_info[:expr]
              if array
                code += "\n" + indent("// #{cell_name}: the declared list, one section, in rows of #{count}", depth)
                code += "\n" + indent("val classListCells = #{array}.mapIndexed { cellIndex, cellData -> Triple(0, cellIndex, cellData) }", depth)
              else
                code += "\n" + indent("// #{cell_name}: every data section, in rows of #{count}", depth)
                code += "\n" + indent("val classListCells = #{sections_access(property_name)}.flatMapIndexed { sectionIndex, section ->", depth)
                code += "\n" + indent("section.cells?.data.orEmpty().mapIndexed { cellIndex, cellData -> Triple(sectionIndex, cellIndex, cellData) }", depth + 1)
                code += "\n" + indent("}.orEmpty()", depth)
              end
              spacing = json_data['columnSpacing'] || json_data['itemSpacing']
              required_imports&.add(:arrangement) if spacing
              row_args = spacing ? "modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(spacing)})" : 'modifier = Modifier.fillMaxWidth()'
              if places
                code += "\n" + indent("classListCells.chunked(#{count}).forEachIndexed { rowIndex, rowCells ->", depth)
                code += "\n" + indent("Row(#{row_args}) {", depth + 1)
                code += "\n" + indent("rowCells.forEachIndexed { columnIndex, (sectionIndex, cellIndex, currentCellData) ->", depth + 2)
              else
                code += "\n" + indent("classListCells.chunked(#{count}).forEach { rowCells ->", depth)
                code += "\n" + indent("Row(#{row_args}) {", depth + 1)
                code += "\n" + indent("rowCells.forEach { (sectionIndex, cellIndex, currentCellData) ->", depth + 2)
              end
              code += "\n" + indent("Box(modifier = Modifier.weight(1f)) {", depth + 3)
              code += class_list_cell(json_data, cell_name, depth + 4, required_imports,
                                      cell_extra: place.call("rowIndex * #{count.include?('.') || count.include?('(') ? "(#{count})" : count} + columnIndex"))
              code += "\n" + indent("}", depth + 3)
              code += "\n" + indent("}", depth + 2)
              code += "\n" + indent("repeat(#{count} - rowCells.size) { Spacer(modifier = Modifier.weight(1f)) }", depth + 2)
              code += "\n" + indent("}", depth + 1)
              code += "\n" + indent("}", depth)
            else
              code += "\n" + indent("// #{cell_name}: every data section", depth)
              code += "\n" + indent("#{sections_access(property_name)}.forEachIndexed { sectionIndex, section ->", depth)
              code += "\n" + indent("section.cells?.data?.forEachIndexed { cellIndex, currentCellData ->", depth + 1)
              code += class_list_cell(json_data, cell_name, depth + 2, required_imports,
                                      cell_extra: place.call("#{scroll_sections_expr(property_name)}.take(sectionIndex).sumOf { it.cells?.data?.size ?: 0 } + cellIndex"))
              code += "\n" + indent("}", depth + 1)
              code += "\n" + indent("}", depth)
            end
          end
          code += class_list_edge_call(cell_class_name(footer_name), 'footer', depth) if footer_name
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

            # A grid per section: each section's cells start a row of their
            # own, as sjui codegen and SwiftJsonUI Dynamic draw them. One
            # LazyVerticalGrid holds every section here, so without a break
            # section 2 continued section 1's last row unless a header item
            # sat between (measured on d084cfb2, 2026-09-26). The builder
            # counts how much of the current row the cells laid out so far
            # fill, in grid units; before a section's cells, a row left part
            # filled is closed by an empty item spanning what it has left
            # (`maxCurrentLineSpan`) — no row is added when it is full.
            # Full-span header / footer items close a row themselves.
            line_breaks = sections.count { |s| s['cell'] } > 1
            if line_breaks
              required_imports&.add(:grid_item_span)
              grid_units = columns_binding ? "(#{columns_info[:expr]}).coerceAtLeast(1)" : grid_columns.to_s
              code += "\n" + indent("var gridLineFill = 0", depth + 1)
            end

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
                code += "\n" + indent("// Section #{index + 1}: #{Helpers::ModifierBuilder.comment_text(cell_view_name)} (#{Helpers::ModifierBuilder.comment_text(section_columns_comment)} columns)", depth + 1)
                if use_hoisted
                  # `section#{index}` is hoisted; just guard null.
                  code += "\n" + indent("if (#{section_var} != null) {", depth + 1)
                else
                  code += "\n" + indent("#{sections_access(property_name)}.getOrNull(#{index})?.let { #{section_var} ->", depth + 1)
                end

                # Generate header if present
                if section['header']
                  header_view_name = section['header']
                  header_class = cell_class_name(header_view_name)
                  code += "\n" + indent("// Section #{index + 1} Header: #{Helpers::ModifierBuilder.comment_text(header_view_name)}", depth + 2)
                  code += "\n" + indent("#{section_var}.header?.let { headerData ->", depth + 2)
                  code += "\n" + indent("item(span = { GridItemSpan(maxLineSpan) }) {", depth + 3)
                  code += "\n" + indent("val headerViewModel: #{header_class}ViewModel = viewModel(key = \"#{header_view_name}_header_#{index}_\${viewModel.hashCode()}\")", depth + 4)
                  code += "\n" + seed_view_model_line("headerViewModel", "headerData.data", depth + 4)
                  code += "\n" + indent("LaunchedEffect(headerData.data) {", depth + 4)
                  code += "\n" + indent("headerViewModel.updateData(headerData.data)", depth + 5)
                  code += "\n" + indent("}", depth + 4)
                  code += "\n" + edge_view_call(header_class, 'headerViewModel', depth + 4)
                  code += "\n" + indent("}", depth + 3)
                  code += "\n" + indent("gridLineFill = 0", depth + 3) if line_breaks
                  code += "\n" + indent("}", depth + 2)
                end

                # Generate cells with optional cellIdProperty for stable identity
                if use_hoisted
                  # enrichedData#{index} is hoisted; guard null and use directly.
                  code += "\n" + indent("if (enrichedData#{index} != null) {", depth + 2)
                  key_expr = "key = { #{lazy_key("(enrichedData#{index}[it][\"cellId\"] as? String) ?: it.toString()", index)} }"
                  data_access = "enrichedData#{index}"
                else
                  code += "\n" + indent("#{section_var}.cells?.let { #{cell_data_var} ->", depth + 2)
                  if cell_id_prop
                    code += "\n" + indent(unique_keys_line("#{cell_data_var}.data", cell_id_prop, 'lazyKeys'), depth + 3)
                    key_expr = "key = { #{lazy_key('lazyKeys[it]', index)} }"
                  else
                    key_expr = nil
                  end
                  data_access = "#{cell_data_var}.data"
                end

                if line_breaks
                  code += "\n" + indent("if (gridLineFill != 0) {", depth + 3)
                  code += "\n" + indent("item(span = { GridItemSpan(maxCurrentLineSpan) }) {}", depth + 4)
                  code += "\n" + indent("gridLineFill = 0", depth + 4)
                  code += "\n" + indent("}", depth + 3)
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
                if (appear_name = Helpers::ModifierBuilder.string_event_name(on_item_appear))
                  code += "\n" + indent("LaunchedEffect(Unit) { data.#{Helpers::BindingExpression.path_only(appear_name)}?.invoke(cellIndex) }", depth + 4)
                end
                # Wrap cell in Box for alignment
                code += "\n" + indent("Box(", depth + 4)
                code += "\n" + indent("modifier = Modifier.fillMaxSize(),", depth + 5)
                code += "\n" + indent("contentAlignment = #{gravity_alignment}", depth + 5)
                code += "\n" + indent(") {", depth + 4)
                cell_class = cell_class_name(cell_view_name)
                code += "\n" + indent("val currentCellData = #{data_access}[cellIndex]", depth + 5)
                if cell_id_prop && !use_hoisted
                  # The section's disambiguated key (lazyKeys): two cells sharing
                  # a key shared one ViewModel, and the later one's data drew in
                  # both (measured, 4f round 11).
                  code += "\n" + indent("val cellId = lazyKeys[cellIndex]", depth + 5)
                  code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 5)
                elsif cell_id_prop
                  code += "\n" + indent("val cellId = (currentCellData[\"cellId\"] as? String) ?: (currentCellData[\"#{cell_id_prop}\"] as? String) ?: \"$cellIndex\"", depth + 5)
                  code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 5)
                else
                  code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", depth + 5)
                end
                code += "\n" + seed_view_model_line("cellViewModel", "currentCellData", depth + 5)
                code += "\n" + indent("LaunchedEffect(currentCellData) {", depth + 5)
                code += "\n" + indent("cellViewModel.updateData(currentCellData)", depth + 6)
                code += "\n" + indent("}", depth + 5)
                if (chrome = chrome_open(json_data, required_imports))
                  code += "\n" + indent(chrome, depth + 5)
                end
                if (cell_box = cell_size_box_open(json_data, required_imports))
                  code += "\n" + indent(cell_box, depth + 5)
                end
                code += "\n" + indent("#{cell_class}View(", depth + 5)
                code += "\n" + indent("viewModel = cellViewModel,", depth + 6)
                # Add testTag for test automation (tapItem action)
                collection_id = json_data['id']
                code += "\n" + cell_test_tag_modifier(collection_id, 'cellIndex', depth + 6)
                code += "\n" + indent(")", depth + 5)
                if cell_size_box_open(json_data, nil)
                  code += "\n" + indent("}", depth + 5)
                end
                if chrome_open(json_data, nil)
                  code += "\n" + indent("}", depth + 5)
                end
                code += "\n" + indent("}", depth + 4)
                code += "\n" + indent("}", depth + 3)
                if line_breaks
                  code += "\n" + indent("gridLineFill = (gridLineFill + #{data_access}.size * #{item_span}) % #{grid_units}", depth + 3)
                end
                code += "\n" + indent("}", depth + 2)
                
                # Generate footer if present
                if section['footer']
                  footer_view_name = section['footer']
                  footer_class = cell_class_name(footer_view_name)
                  code += "\n" + indent("// Section #{index + 1} Footer: #{Helpers::ModifierBuilder.comment_text(footer_view_name)}", depth + 2)
                  code += "\n" + indent("#{section_var}.footer?.let { footerData ->", depth + 2)
                  code += "\n" + indent("item(span = { GridItemSpan(maxLineSpan) }) {", depth + 3)
                  code += "\n" + indent("val footerViewModel: #{footer_class}ViewModel = viewModel(key = \"#{footer_view_name}_footer_#{index}_\${viewModel.hashCode()}\")", depth + 4)
                  code += "\n" + seed_view_model_line("footerViewModel", "footerData.data", depth + 4)
                  code += "\n" + indent("LaunchedEffect(footerData.data) {", depth + 4)
                  code += "\n" + indent("footerViewModel.updateData(footerData.data)", depth + 5)
                  code += "\n" + indent("}", depth + 4)
                  code += "\n" + edge_view_call(footer_class, 'footerViewModel', depth + 4)
                  code += "\n" + indent("}", depth + 3)
                  code += "\n" + indent("gridLineFill = 0", depth + 3) if line_breaks
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
          required_imports&.add(:remember) # seed_view_model_line
          required_imports&.add(:remember_state)
          required_imports&.add(:snapshot_flow)

          items_property = json_data['items']
          item_binding = items_property&.match(/@\{([^}]+)\}/)&.captures&.first
          # Pages sit along the scroll axis (horizontal_scroll_spacing); this
          # read itemSpacing, then columnSpacing, until jsonui-cli 1.9.0.
          page_spacing = horizontal_scroll_spacing(json_data)

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
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          # The clickable stage — onClick, enabled, userInteractionEnabled and
          # the node's gestures — which every other Collection emitter applies
          # here, between the background and the padding; the pager applied
          # none (kjui-dynamic-components-that-skip-the-common-modifiers, B1).
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # Always add cell imports
          sections.each do |section|
            required_imports&.add("cell:#{section['cell']}") if section['cell']
          end

          code = ""

          # One page per cell, every drawn section's cells in order (4f ruling
          # 2026-09-26, round 6; what sjui, rjui and both Dynamic renderers
          # draw). One declared section keeps the text this emitter always
          # wrote. Until jsonui-cli 1.9.0 the pager read data section 0 only —
          # its page count and its cells — so a second section drew nothing;
          # and the class-list shape (cellClasses, no `sections`) drew no page.
          sources = paging_sources(json_data, sections, item_binding)
          sources.each { |cell, _| required_imports&.add("cell:#{cell}") }
          one_section = sources.size == 1 && sections.any? && sources.first == [sections.first['cell'], 0]

          # Page count from data source
          if one_section
            code += indent("val pageCount = #{sections_access(item_binding)}.firstOrNull()?.cells?.data?.size ?: 0", depth) + "\n"
          elsif sources.any?
            code += paging_source_lists(json_data, sources, item_binding, depth, required_imports)
          else
            code += indent("val pageCount = 0", depth) + "\n"
          end

          # PagerState
          if page_prop
            code += indent("val pagerState = rememberPagerState(initialPage = (data.#{page_prop}).coerceIn(0, (pageCount - 1).coerceAtLeast(0))) { pageCount }", depth) + "\n"
          else
            code += indent("val pagerState = rememberPagerState { pageCount }", depth) + "\n"
          end

          # Sync data binding -> pager. While this programmatic scroll is in
          # flight the pager -> VM leg below stays quiet: the pager's
          # currentPage passes through the pages between (and an animation
          # more than 3 pages away first jumps near the target), and writing
          # those back moved data.<page>, which re-keyed this effect and
          # cancelled its own animateScrollToPage short of the target — 0 -> 6
          # of 7 pages stopped on 5, 0 -> 2 of 3 on 1, measured on a device
          # through jsonui-cli 1.9.5 (kjui-pager-writeback-cancels-its-own-
          # programmatic-scroll). The page callback is quiet too: a handler
          # that sets the bound page itself (the usual one) cancelled the
          # scroll the same way, on 5 of 7. The scroll's landing is told once
          # — written back if data.<page> differs (a value past the last page
          # settles on the last page) and handed to the callback if the page
          # moved, as iOS's onChange tells a selection change once. A scrollTo
          # scrolls the same way (pager_scroll_code).
          # Keyed on pageCount too: a page bound before the pages exist (a
          # restored page, items that load later) is scrolled to when they
          # arrive; through 1.9.5 the pager stayed on 0 and wrote 0 back.
          # The same guard KotlinJsonUI Dynamic keeps (`programmaticScroll`).
          #
          # The callback is read through rememberUpdatedState: the effects
          # outlive the composition they start in, and through 1.9.5 they
          # called the handler the data held then — a handler the ViewModel
          # set after the pager appeared was never called (measured).
          pager_legs = (page_prop || page_callback_prop) && { page_prop: page_prop, handled: !page_callback_prop.nil? }
          if pager_legs
            code += indent("var programmaticScroll by remember { mutableStateOf(false) }", depth) + "\n"
          end
          if page_callback_prop
            required_imports&.add(:remember_updated_state)
            code += indent("val pageChangeHandler by rememberUpdatedState(data.#{page_callback_prop})", depth) + "\n"
          end
          if page_prop
            code += indent("LaunchedEffect(data.#{page_prop}, pageCount) {", depth) + "\n"
            code += indent("if (pageCount == 0) return@LaunchedEffect", depth + 1) + "\n"
            code += indent("val target = data.#{page_prop}.coerceIn(0, pageCount - 1)", depth + 1) + "\n"
            code += pager_programmatic_scroll('pagerState.animateScrollToPage(target)', 'from != target', pager_legs, depth + 1)
            code += indent("}", depth) + "\n"
          end

          # scrollTo: the page is the cell the value names, counted across the
          # sources (4f ruling 2026-09-27, round 11). The pager read no
          # scrollTo until jsonui-cli 1.9.0.
          code += scroll_to_effect(json_data, sections, depth, required_imports, target: :pager, is_horizontal: true, pager_legs: pager_legs)

          # Sync pager -> binding + callback: a page the pager moved to, not
          # the page it appeared on (`drop(1)`). Through 1.9.5 the collector's
          # first value told the callback and the binding the appearance page
          # — 0 on a fresh pager, before the pages exist — which iOS and web
          # do not; the ruling of 2026-10-02 is "only on a change"
          # (pager-page-change-callback-initial-call-differs-by-platform).
          if page_prop || page_callback_prop
            required_imports&.add(:flow_drop)
            code += indent("LaunchedEffect(pagerState) {", depth) + "\n"
            code += indent("snapshotFlow { pagerState.currentPage }.drop(1).collect { page ->", depth + 1) + "\n"
            code += indent("if (!programmaticScroll) {", depth + 2) + "\n"
            code += indent("viewModel.updateData(mapOf(\"#{page_prop}\" to page))", depth + 3) + "\n" if page_prop
            code += indent("pageChangeHandler?.invoke(page)", depth + 3) + "\n" if page_callback_prop
            code += indent("}", depth + 2) + "\n"
            code += indent("}", depth + 1) + "\n"
            code += indent("}", depth) + "\n"
          end

          # The content padding — contentPadding / insets, insetHorizontal /
          # insetVertical and the safe area, added side by side as on every
          # other route (collection_stack_content_padding_expr) — pads EACH
          # PAGE'S CELL inside the page, as sjui pads the page's cell
          # (add_paging_cell) and KotlinJsonUI Dynamic its page box: a page
          # stays the pager's width, so no neighbouring page shows in the
          # padding, which HorizontalPager's own `contentPadding` would do.
          # The pager read no insets through jsonui-cli 1.9.0.
          page_padding = collection_stack_content_padding_expr(json_data, is_horizontal: true)
          code += indent("val pagePadding = #{page_padding}", depth) + "\n" if page_padding
          cell_lead = page_padding ? '.padding(pagePadding)' : ''

          # HorizontalPager
          code += indent("HorizontalPager(", depth)
          code += "\n" + indent("state = pagerState", depth + 1)
          # scrollEnabled false stops the user's paging only (round 13); the
          # pager read no scrollEnabled until then.
          if json_data.key?('scrollEnabled')
            code += ",\n" + indent("userScrollEnabled = #{user_scroll_enabled_expr(json_data)}", depth + 1)
          end
          if page_spacing
            code += ",\n" + indent("pageSpacing = #{Helpers::BoundValue.dp(page_spacing)}", depth + 1)
          end
          if modifiers.any?
            code += "," + Helpers::ModifierBuilder.format(modifiers, depth)
          end
          code += "\n" + indent(") { page ->", depth)

          # onItemAppear callback for paging
          on_item_appear = json_data['onItemAppear']
          if (appear_name = Helpers::ModifierBuilder.string_event_name(on_item_appear))
            required_imports&.add(:launched_effect)
            code += "\n" + indent("LaunchedEffect(Unit) { data.#{appear_name}?.invoke(page) }", depth + 1)
          end

          # Render cell content
          if !one_section && sources.any?
            code += paging_cells(json_data, sources, depth + 1, cell_lead)
          elsif one_section
            cell_view_name = sections.first['cell']
            if cell_view_name
              cell_class = cell_class_name(cell_view_name)
              cell_id_prop = json_data['cellIdProperty']
              auto_tracking = json_data['autoChangeTrackingId'] == true
              # Use val + if instead of .let { cellData -> ... } so remember(...)
              # (which is @Composable) isn't called from a non-@Composable lambda.
              code += "\n" + indent("val cellData = #{sections_access(item_binding)}.firstOrNull()?.cells", depth + 1)
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
              code += "\n" + seed_view_model_line("cellViewModel", "item", depth + 3)
              code += "\n" + indent("LaunchedEffect(item) {", depth + 3)
              code += "\n" + indent("cellViewModel.updateData(item)", depth + 4)
              code += "\n" + indent("}", depth + 3)
              code += "\n" + indent("#{cell_class}View(", depth + 3)
              code += "\n" + indent("viewModel = cellViewModel,", depth + 4)
              collection_id = json_data['id']
              code += "\n" + cell_test_tag_modifier(collection_id, 'page', depth + 4, '.fillMaxSize()', lead: cell_lead)
              code += "\n" + indent(")", depth + 3)
              code += "\n" + indent("}", depth + 2)
              code += "\n" + indent("}", depth + 1)
            end
          end

          code += "\n" + indent("}", depth)
          code
        end

        # The pager's sources: [cell, data section index] for each declared
        # section that draws a cell, in order; the class-list shape is one —
        # cellClasses[0] over data section 0, or [cell, :list] when the layout
        # declares items a list (class_list_array_expr).
        def self.paging_sources(json_data, sections, item_binding)
          return [] unless item_binding

          if sections.any?
            sections.each_with_index.select { |section, _| section['cell'] }.map { |section, index| [section['cell'], index] }
          elsif (cell = class_list(json_data)&.first)
            [[cell, class_list_array_expr(json_data, cell) ? :list : 0]]
          else
            []
          end
        end

        # One list per source (`pageSection<n>`, List<Map<String, Any>>) and
        # their total, `pageCount`. autoChangeTrackingId enriches each list
        # with cell ids, as the one-section pager does.
        def self.paging_source_lists(json_data, sources, item_binding, depth, required_imports)
          cell_id_prop = json_data['cellIdProperty']
          auto_tracking = json_data['autoChangeTrackingId'] == true
          code = ''
          sources.each_with_index do |(cell, source), n|
            list = source == :list ? class_list_array_expr(json_data, cell) : "#{sections_access(item_binding)}.getOrNull(#{source})?.cells?.data.orEmpty()"
            if auto_tracking && cell_id_prop
              required_imports&.add(:remember_state)
              code += indent("val pageSource#{n} = #{list}", depth) + "\n"
              code += indent("val pageSection#{n} = remember(pageSource#{n}) { com.kotlinjsonui.utils.CellIdGenerator.enrichCellIds(pageSource#{n}, \"#{cell_id_prop}\") }", depth) + "\n"
            else
              code += indent("val pageSection#{n} = #{list}", depth) + "\n"
            end
          end
          code += indent("val pageCount = #{sources.each_index.map { |n| "pageSection#{n}.size" }.join(' + ')}", depth) + "\n"
          code
        end

        # The page body: the source the page falls in, and its cell there. A
        # page's index counts across all the sources, so `page` is the pager's
        # own index and the item's test tag and ViewModel key are unique.
        # `lead`: the page's padding (generate_paging_horizontal), before the
        # cell's test tag so the tag's bounds are the padded cell's.
        def self.paging_cells(json_data, sources, depth, lead = '')
          code = "\n" + indent("var pageStart = 0", depth)
          sources.each_with_index do |(cell, _), n|
            cell_class = cell_class_name(cell)
            code += "\n" + indent("if (page >= pageStart && page < pageStart + pageSection#{n}.size) {", depth)
            code += "\n" + indent("val item = pageSection#{n}[page - pageStart]", depth + 1)
            code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell}_page_\${page}_\${viewModel.hashCode()}\")", depth + 1)
            code += "\n" + seed_view_model_line("cellViewModel", "item", depth + 1)
            code += "\n" + indent("LaunchedEffect(item) {", depth + 1)
            code += "\n" + indent("cellViewModel.updateData(item)", depth + 2)
            code += "\n" + indent("}", depth + 1)
            code += "\n" + indent("#{cell_class}View(", depth + 1)
            code += "\n" + indent("viewModel = cellViewModel,", depth + 2)
            code += "\n" + cell_test_tag_modifier(json_data['id'], 'page', depth + 2, '.fillMaxSize()', lead: lead)
            code += "\n" + indent(")", depth + 1)
            code += "\n" + indent("}", depth)
            code += "\n" + indent("pageStart += pageSection#{n}.size", depth) if n < sources.size - 1
          end
          code
        end

        # `clipToBounds` defaults to false on every component (SSoT
        # common.clipToBounds; attribute_semantics 51-E, 2026-08-07: absent means
        # no clip, and hit testing follows clipping). FlowRow does not lay out
        # the rows that exceed its max height, so a lazy:"none" flow in a
        # fixed-height box drew the rows that fit and nothing else while iOS and
        # web drew every row past the box. Measuring the FlowRow without regard
        # for the incoming max height and aligning the result over that space
        # is what "overflow visible" is in Compose (foundation-layout Size.kt:
        # wrapContentHeight, unbounded); FlowRow's own `overflow` parameter says
        # the same but is deprecated in foundation-layout 1.11 and draws the rows
        # overlapping inside the box. Last on the FlowRow, after size, background,
        # scroll and padding — the same place KotlinJsonUI's dynamic renderer
        # applies it (renderFlowLayout). `clipToBounds: true` keeps its opt-in
        # `.clipToBounds()` from build_background, which is now what decides.
        # APPENDED, NOT SUBSTITUTED, and that is deliberate: `build_size` still
        # emits its own `.wrapContentHeight()` when the layout declares
        # `height: "wrapContent"`, so that shape renders through two stacked
        # wrapContentHeight modifiers. Measured rather than assumed
        # (flowOverflow__noneWrap{InBox,InScroll}, whose controls are the same
        # layouts with the height key absent — one modifier instead of two):
        # the pictures are byte-identical, on the dynamic host and the codegen
        # host, under a finite 150x100 parent and under a ScrollView. Twelve
        # cells, six rows, drawn TOP-aligned and spilling below the parent in
        # every one.
        #
        # That also disposes of the reason to substitute. The worry was that
        # the outer modifier's default alignment (CenterVertically) would win
        # over the Top this one asks for and split the overflow above and
        # below; it does not — the corpus arms say so in pictures. Leaving the
        # append also keeps this arm independent of what `build_size` chooses
        # to emit, which substitution would couple.
        FLOW_OVERFLOW_MODIFIER = '.wrapContentHeight(Alignment.Top, unbounded = true)'

        # See generate_flow_layout: `lazy` in effect AND a height that is finite
        # by declaration. A bound height (`@{...}`) is unknown here and stays
        # with the parent.
        def self.flow_scrolls_in_own_bounds?(json_data)
          return false if json_data['lazy'] == 'none'

          finite_dimension?(json_data['height']) || finite_dimension?(json_data['maxHeight'])
        end

        # The shape the static predicate above leaves with the parent because it
        # cannot see the parent: `height: matchParent` with `lazy` in effect.
        # KotlinJsonUI's dynamic renderer (db891a9) resolves it at runtime —
        # BoxWithConstraints, scroll only when the parent handed it a bounded
        # height — so under a finite parent the same JSON scrolled there and not
        # here (the residue the parity ticket recorded). Emitting the same
        # BoxWithConstraints closes it: the decision moves to the device, where
        # the parent is visible. A bound `@{...}` height takes the same arm:
        # its value is unknown here but is a number at runtime (build_size
        # emits `requiredHeight(data.h?.dp ?: 0.dp)`), so the box IS bounded
        # on the device and the FlowRow scrolls inside it — the dynamic
        # renderer resolves a bound height the same way. wrapContent stays
        # out (nothing to scroll inside, and the crash shape); an undeclared
        # height is wrapContent by default and stays out with it; numbers
        # keep the static modifier.
        def self.flow_scrolls_if_parent_bounded?(json_data)
          return false if json_data['lazy'] == 'none'
          return false if flow_scrolls_in_own_bounds?(json_data)

          height = json_data['height']
          height == 'matchParent' || Helpers::ModifierBuilder.is_binding?(height)
        end

        def self.finite_dimension?(value)
          case value
          when Numeric then true
          when String then value.match?(/\A\d+(\.\d+)?\z/)
          else false
          end
        end

        # Generate FlowLayout using Compose FlowRow
        def self.generate_flow_layout(json_data, sections, depth, required_imports, parent_type)
          required_imports&.add(:flow_row)
          required_imports&.add(:arrangement)
          required_imports&.add(:launched_effect)
          required_imports&.add(:remember) # seed_view_model_line
          # FLOW_OVERFLOW_MODIFIER names Alignment.Top; wrapContentHeight itself
          # rides the foundation.layout.* import every generated file carries.
          required_imports&.add(:alignment)

          # Spacing. Undeclared means 0, the platform default — the dynamic
          # renderer falls back to 0f, and the silent 8 here was the parity
          # residue on Collection/layout__flow_2 after the enum fix.
          h_spacing = json_data['columnSpacing'] || json_data['itemSpacing'] || json_data['spacing'] || 0
          v_spacing = json_data['lineSpacing'] || json_data['sectionSpacing'] || json_data['itemSpacing'] || json_data['spacing'] || 0

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
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          # A flow Collection with `lazy` in effect (default or "eager") scrolls
          # vertically inside its own bounds; `lazy: "none"` only wraps and the
          # parent must scroll (Collection.layout / lazy descriptions, 2026-09-03
          # ruling). sjui's default-lazy flow arm and iOS Dynamic already wrap
          # in a ScrollView; this arm emitted a bare FlowRow, so the same JSON
          # scrolled on iOS and did not on Android. After size and background —
          # the size is the viewport, the background paints it, the content
          # scrolls inside.
          #
          # "Its own bounds" is literal: only a node whose height is finite by
          # its own declaration (a number, or a maxHeight) gets the modifier.
          # Compose throws when a vertically scrollable node is measured with
          # an infinite max height — which is what wrapContent, or matchParent
          # under a LazyColumn cell or a scrolling sheet, hands it — and a node
          # without bounds of its own has nothing to scroll inside: the parent
          # scrolls. The static emit cannot see the parent, so matchParent is
          # left to the parent too; the dynamic renderer checks the parent's
          # constraints at runtime for that one shape.
          # scrollTo on a flow that scrolls (4f ruling 2026-09-27, round 11):
          # the scroll state is the flow's own, the scrolled content and each
          # cell record where they were laid out, and the effect scrolls to the
          # cell by scrollAnchor (flow_scroll_code). A flow read no scrollTo
          # until jsonui-cli 1.9.0. A flow that does not scroll (lazy: none, a
          # height that is not its own) has nothing to scroll: the parent does.
          flow_scroll_to = (flow_scrolls_in_own_bounds?(json_data) || flow_scrolls_if_parent_bounded?(json_data)) &&
                           json_data['scrollTo'].is_a?(String) && json_data['scrollTo'].match?(/\A@\{[^}]+\}\z/)
          flow_scroll = flow_scroll_to ? 'flowScrollState' : 'rememberScrollState()'
          flow_content = flow_scroll_to ? '.onGloballyPositioned { flowContent[0] = it }' : ''
          if flow_scrolls_in_own_bounds?(json_data)
            required_imports&.add(:vertical_scroll)
            modifiers << ".verticalScroll(#{flow_scroll}#{scroll_enabled_arg(json_data)})"
            modifiers << flow_content if flow_scroll_to
          end
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          padding_modifiers = Helpers::ModifierBuilder.build_padding(json_data)
          # contentPadding / insets pad the cells, after the node's padding and
          # inside the scroll where the flow scrolls (4f ruling 2026-09-27,
          # round 15), as KotlinJsonUI Dynamic's flow pads them. A flow applied
          # none until jsonui-cli 1.9.0.
          content_padding = non_lazy_content_padding(json_data, is_horizontal: false)
          padding_modifiers += [content_padding] if content_padding
          modifiers.concat(padding_modifiers) unless flow_scrolls_if_parent_bounded?(json_data)
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # A flow per section: with two or more sections that draw cells,
          # each section's cells wrap in a FlowRow of their own, one under the
          # other, spaced by the line spacing (its alias sectionSpacing) — as
          # sjui draws a FlowLayout per section in a VStack. One FlowRow held
          # every section, so section 2 continued section 1's last row
          # (measured on 6bdb6aba, 2026-09-26). The node's own modifiers stay
          # on the outer container, a Column then.
          # A section's declared header and footer (4f ruling 2026-09-26,
          # round 7) are rows of their own, full width, above and below the
          # section's wrap — so a Collection that declares one takes the
          # Column too. Rows (header, wrap, footer) and section blocks are
          # spaced as the lines. Until jsonui-cli 1.9.0 a flow drew neither.
          items_bound = json_data['items'].is_a?(String) && json_data['items'].match?(/@\{([^}]+)\}/)
          per_section = items_bound && (sections.count { |section| section['cell'] } > 1 ||
                                        sections.any? { |section| section['header'] || section['footer'] })
          container = per_section ? 'Column' : 'FlowRow'
          flow_arrangements = "horizontalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(h_spacing)}), " \
                              "verticalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(v_spacing)})"

          outer_depth = depth
          prelude = ''
          if flow_scroll_to
            effect = scroll_to_effect(json_data, sections, depth, required_imports, target: :flow)
            if effect.empty?
              flow_scroll_to = false
              flow_scroll = 'rememberScrollState()'
              modifiers.map! { |m| m == ".verticalScroll(flowScrollState#{scroll_enabled_arg(json_data)})" ? ".verticalScroll(rememberScrollState()#{scroll_enabled_arg(json_data)})" : m }
              modifiers.delete(flow_content)
              flow_content = ''
            else
              required_imports&.add(:on_globally_positioned)
              required_imports&.add(:vertical_scroll)
              required_imports&.add(:remember_state)
              prelude = indent('val flowScrollState = rememberScrollState()', depth) + "\n" +
                        indent('val flowCellTargets = remember { mutableMapOf<Int, androidx.compose.ui.layout.LayoutCoordinates>() }', depth) + "\n" +
                        indent('val flowContent = remember { arrayOfNulls<androidx.compose.ui.layout.LayoutCoordinates>(1) }', depth) + "\n" +
                        effect
            end
          end
          if flow_scrolls_if_parent_bounded?(json_data)
            # matchParent: the node's own modifiers (address, size, background,
            # click, weight) sit on a BoxWithConstraints; the FlowRow fills it
            # and scrolls only when the box was measured with a bounded height
            # — the same arm the dynamic renderer takes. Padding stays on the
            # FlowRow so it pads the content, not the viewport.
            required_imports&.add(:box_with_constraints)
            required_imports&.add(:vertical_scroll)
            code = prelude + indent("BoxWithConstraints(", depth)
            code += Helpers::ModifierBuilder.format(modifiers, depth)
            code += "\n" + indent(") {", depth)
            depth += 1
            code += "\n" + indent("#{container}(", depth)
            code += "\n" + indent("modifier = (if (constraints.hasBoundedHeight) Modifier.fillMaxSize().verticalScroll(#{flow_scroll}#{scroll_enabled_arg(json_data)}) else Modifier.fillMaxWidth())#{flow_content}", depth + 1)
            padding_modifiers.each { |mod| code += "\n" + indent(indent(mod, 1), depth + 1) }
            code += "\n" + indent(indent(FLOW_OVERFLOW_MODIFIER, 1), depth + 1)
          else
            modifiers << FLOW_OVERFLOW_MODIFIER
            code = prelude + indent("#{container}(", depth)
            code += Helpers::ModifierBuilder.format(modifiers, depth)
          end
          unless per_section
            code += ",\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(h_spacing)}),", depth + 1)
          end
          code += (per_section ? ",\n" : "\n") + indent("verticalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(v_spacing)})", depth + 1)
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
              required_imports&.add("cell:#{section['header']}") if section['header']
              required_imports&.add("cell:#{section['footer']}") if section['footer']
            end

            sections.each_with_index do |section, index|
              cell_view_name = section['cell']
              next unless cell_view_name || section['header'] || section['footer']

              auto_tracking = json_data['autoChangeTrackingId'] == true
              use_val_if = auto_tracking && cell_id_property
              section_var = use_val_if ? "section#{index}" : 'section'
              cell_data_var = use_val_if ? "cellData#{index}" : 'cellData'

              # The loop's depth: one deeper inside the section's own FlowRow.
              ld = per_section ? depth + 4 : depth + 3
              if use_val_if
                code += "\n" + indent("val #{section_var} = #{sections_access(property_name)}.getOrNull(#{index})", depth + 1)
                code += "\n" + indent("if (#{section_var} != null) {", depth + 1)
                code += flow_section_edge(section, 'header', section_var, index, depth + 2)
                unless cell_view_name
                  code += flow_section_edge(section, 'footer', section_var, index, depth + 2)
                  code += "\n" + indent("}", depth + 1)
                  next
                end
                code += "\n" + indent("val #{cell_data_var} = #{section_var}.cells", depth + 2)
                code += "\n" + indent("if (#{cell_data_var} != null) {", depth + 2)
                required_imports&.add(:remember_state)
                code += "\n" + indent("val enrichedData#{index} = remember(#{cell_data_var}.data) { com.kotlinjsonui.utils.CellIdGenerator.enrichCellIds(#{cell_data_var}.data, \"#{cell_id_property}\") }", depth + 3)
                code += "\n" + indent("FlowRow(modifier = Modifier.fillMaxWidth(), #{flow_arrangements}) {", depth + 3) if per_section
                code += "\n" + indent("enrichedData#{index}.forEachIndexed { cellIndex, item ->", ld)
              else
                code += "\n" + indent("#{sections_access(property_name)}.getOrNull(#{index})?.let { #{section_var} ->", depth + 1)
                code += flow_section_edge(section, 'header', section_var, index, depth + 2)
                unless cell_view_name
                  code += flow_section_edge(section, 'footer', section_var, index, depth + 2)
                  code += "\n" + indent("}", depth + 1)
                  next
                end
                code += "\n" + indent("#{section_var}.cells?.let { #{cell_data_var} ->", depth + 2)
                code += "\n" + indent(unique_keys_line("#{cell_data_var}.data", cell_id_property, 'flowKeys'), depth + 3) if cell_id_property
                code += "\n" + indent("FlowRow(modifier = Modifier.fillMaxWidth(), #{flow_arrangements}) {", depth + 3) if per_section
                code += "\n" + indent("#{cell_data_var}.data.forEachIndexed { cellIndex, item ->", ld)
              end

              if cell_id_property && !use_val_if
                code += "\n" + indent("val cellId = flowKeys[cellIndex]", ld + 1)
                code += "\n" + indent("key(cellId) {", ld + 1)
                inner_depth = ld + 2
              elsif cell_id_property
                code += "\n" + indent("val cellId = (item[\"cellId\"] as? String) ?: (item[\"#{cell_id_property}\"] as? String) ?: cellIndex.toString()", ld + 1)
                code += "\n" + indent("key(cellId) {", ld + 1)
                inner_depth = ld + 2
              else
                inner_depth = ld + 1
              end

              cell_class = cell_class_name(cell_view_name)
              # The key carries the section (#{index}), as the sectioned
              # grid's `<cell>_cell_<section>_<cellIndex>` does: without it
              # two sections of the same cell class shared their cells'
              # ViewModels, and the later section's data drew in both
              # (measured on 137468b2; collection_flow_sections_spec.rb).
              if cell_id_property && !use_val_if
                code += "\n" + indent("val flowCellId = cellId", inner_depth)
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_flow_#{index}_\${flowCellId}_\${viewModel.hashCode()}\")", inner_depth)
              elsif cell_id_property
                code += "\n" + indent("val flowCellId = (item[\"cellId\"] as? String) ?: (item[\"#{cell_id_property}\"] as? String) ?: \"$cellIndex\"", inner_depth)
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_flow_#{index}_\${flowCellId}_\${viewModel.hashCode()}\")", inner_depth)
              else
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_flow_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", inner_depth)
              end
              code += "\n" + seed_view_model_line("cellViewModel", "item", inner_depth)
              code += "\n" + indent("LaunchedEffect(item) {", inner_depth)
              code += "\n" + indent("cellViewModel.updateData(item)", inner_depth + 1)
              code += "\n" + indent("}", inner_depth)
              code += "\n" + indent("#{cell_class}View(", inner_depth)
              code += "\n" + indent("viewModel = cellViewModel,", inner_depth + 1)
              # The cell's place among the drawn sections' cells: the cells of
              # the drawn sections before this one, then its own index.
              flow_extra = ''
              if flow_scroll_to
                before = sections.first(index).each_with_index.select { |s, _| s.is_a?(Hash) && s['cell'] }
                                 .map { |_, j| "(#{scroll_sections_expr(property_name)}.getOrNull(#{j})?.cells?.data?.size ?: 0) + " }.join
                flow_extra = ".onGloballyPositioned { flowCellTargets[#{before}cellIndex] = it }"
              end
              code += "\n" + cell_test_tag_modifier(json_data['id'], 'cellIndex', inner_depth + 1, flow_extra)
              code += "\n" + indent(")", inner_depth)

              if cell_id_property
                code += "\n" + indent("}", ld + 1)
              end

              code += "\n" + indent("}", ld)
              code += "\n" + indent("}", depth + 3) if per_section
              code += "\n" + indent("}", depth + 2)
              code += flow_section_edge(section, 'footer', section_var, index, depth + 2)
              code += "\n" + indent("}", depth + 1)
            end
          elsif sections.empty? && (names = class_list(json_data))
            code += class_list_eager_body(json_data, names, depth + 1, required_imports, first_only: true,
                                          cell_extra: flow_scroll_to ? '.onGloballyPositioned { flowCellTargets[cellIndex] = it }' : '')
          end

          code += "\n" + indent("}", depth)
          code += "\n" + indent("}", outer_depth) if depth > outer_depth
          code
        end

        # A flow section's header or footer: its view with its own ViewModel
        # and the section's header / footer data, in a full-width row of its
        # own in the section Column. The ROW is full width and the view keeps
        # its own size at the row's start — as KotlinJsonUI Dynamic's flow
        # (a fillMaxWidth Box around the view), sjui's (`.frame(maxWidth:
        # .infinity, alignment: .leading)`) and rjui's (a flex-column row) —
        # rather than the other routes' `modifier = Modifier.fillMaxWidth()`
        # into the view, which a fixed-width root (`requiredWidth`) answers by
        # centring itself in the row. Empty when the section declares none.
        def self.flow_section_edge(section, kind, section_var, index, depth)
          name = section[kind]
          return '' unless name

          edge_class = cell_class_name(name)
          code = "\n" + indent("#{section_var}.#{kind}?.let { #{kind}Data ->", depth)
          code += "\n" + indent("val #{kind}ViewModel: #{edge_class}ViewModel = viewModel(key = \"#{name}_#{kind}_#{index}_\${viewModel.hashCode()}\")", depth + 1)
          code += "\n" + seed_view_model_line("#{kind}ViewModel", "#{kind}Data.data", depth + 1)
          code += "\n" + indent("LaunchedEffect(#{kind}Data.data) { #{kind}ViewModel.updateData(#{kind}Data.data) }", depth + 1)
          code += "\n" + edge_view_call(edge_class, "#{kind}ViewModel", depth + 1)
          code + "\n" + indent("}", depth)
        end

        # Generate non-lazy Column-based collection for wrapContent height.
        # Used when a vertical Collection has height: "wrapContent" to avoid
        # Compose crash from nesting LazyVerticalGrid inside another Lazy container.
        # The row width of a section on the composable (non-lazy) route: the
        # section's own `columns`, else the Collection's — a Kotlin expression
        # when that is more than 1 (or a binding), nil for one cell per row.
        def self.non_lazy_section_columns(json_data, section)
          own = section['columns']
          return own > 1 ? own.to_s : nil if own.is_a?(Integer)

          info = columns_emit_info(json_data)
          return "(#{info[:expr]}).coerceAtLeast(1)" if info[:is_binding]

          info[:literal] > 1 ? info[:literal].to_s : nil
        end

        # `scroll_within_bounds` — the wrapContent Column (a vertical Collection
        # whose height wraps its content, `lazy` lazy or eager): it scrolls
        # inside the height its parent bounds it to, and under a parent that
        # does not bound it (a scrolling ancestor) it is its content's height,
        # with nothing of its own to scroll (4f ruling 2026-09-27, round 12:
        # what iOS — a ScrollView as tall as its parent lets it be — and the
        # web — a fit-content box a flex parent shrinks, overflow auto — draw,
        # measured on both). The layout step hands the verticalScroll a
        # bounded height where the parent gave none, so it measures instead of
        # throwing ("measured with an infinity maximum height constraints");
        # no subcomposition, so a parent may still ask its intrinsics.
        # scrollTo and defaultScrollAnchor then reach its cells by the rule the
        # lazy routes follow (non_lazy_scroll_prelude). Until jsonui-cli 1.9.0
        # it never scrolled: its cells ran past a bounded parent. `lazy: none`
        # comes here without it and scrolls nowhere; a bound `lazy` that is
        # NONE at run time does not scroll either (round 13 — it did in 1.9.0's
        # first cut, where the route was chosen at codegen), as KotlinJsonUI
        # Dynamic reads it. scrollEnabled false stops the user's scrolling only.
        def self.generate_non_lazy(json_data, sections, depth, required_imports, parent_type, scroll_within_bounds: false)
          required_imports&.add(:launched_effect)
          required_imports&.add(:remember) # seed_view_model_line
          bound_mode = json_data['lazy'].is_a?(String) && json_data['lazy'][/\A@\{([^}]+)\}\z/, 1]

          items_property = json_data['items']
          scroll_to = json_data['scrollTo'].is_a?(String) && json_data['scrollTo'].match?(/\A@\{[^}]+\}\z/)
          declared_anchor = %w[center bottom].include?(json_data['defaultScrollAnchor'].to_s) &&
                            items_property.is_a?(String) && items_property.match?(/@\{[^}]+\}/)
          places = scroll_within_bounds && (scroll_to || declared_anchor)
          prelude = ''
          if places
            prelude = non_lazy_scroll_prelude(depth, required_imports, is_horizontal: false, gate: bound_mode ? 'collectionScrolls' : nil)
            route = sections.any? ? :stack : :class_list
            prelude += scroll_to_effect(json_data, sections, depth, required_imports, target: :non_lazy)
            prelude += default_scroll_anchor_code(json_data, nil, depth, required_imports, sections: sections, route: route, non_lazy: :only)
            places = false if prelude == non_lazy_scroll_prelude(depth, nil, is_horizontal: false, gate: bound_mode ? 'collectionScrolls' : nil)
          end
          if scroll_within_bounds && bound_mode
            required_imports&.add(:collection_stack)
            prelude = indent("val collectionScrolls = CollectionStackMode.fromJson(data.#{bound_mode}) != CollectionStackMode.NONE", depth) + "\n" + (places ? prelude : '')
            places ||= :gate_only
          end

          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          # contentPadding / insets pad the cells, inside the scroll where the
          # Column scrolls (4f ruling 2026-09-27, round 15), as KotlinJsonUI
          # Dynamic's Column and the lazy routes pad them. Until jsonui-cli
          # 1.9.0 the wrapContent and `lazy: none` Columns applied none.
          content_padding = non_lazy_content_padding(json_data, is_horizontal: false)
          if scroll_within_bounds
            required_imports&.add(:vertical_scroll)
            required_imports&.add(:layout_modifier)
            records = places && places != :gate_only
            modifiers << '.onGloballyPositioned { collectionViewport[0] = it }' if records
            bounded = '.layout { measurable, constraints -> val placeable = measurable.measure(if (constraints.hasBoundedHeight) constraints ' \
                      'else androidx.compose.ui.unit.Constraints.fitPrioritizingWidth(constraints.minWidth, constraints.maxWidth, ' \
                      'constraints.minHeight, Int.MAX_VALUE - 1)); layout(placeable.width, placeable.height) { placeable.place(0, 0) } }'
            scroll = ".verticalScroll(#{records ? 'collectionScroll' : 'rememberScrollState()'}#{scroll_enabled_arg(json_data)})"
            if bound_mode
              modifiers << ".then(if (collectionScrolls) Modifier#{bounded}#{scroll} else Modifier)"
            else
              modifiers << bounded
              modifiers << scroll
            end
          end
          modifiers << content_padding if content_padding
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # Spacing
          line_spacing = json_data['lineSpacing'] || json_data['sectionSpacing'] || json_data['itemSpacing'] || json_data['spacing']

          code = (places ? prelude : '') + indent("Column(", depth)
          places = false if places == :gate_only
          code += Helpers::ModifierBuilder.format(modifiers, depth)
          if line_spacing
            required_imports&.add(:arrangement)
            code += ",\n" + indent("verticalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(line_spacing)})", depth + 1)
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

              code += "\n" + indent("// Section #{index + 1}: #{Helpers::ModifierBuilder.comment_text(cell_view_name)}", depth + 1)
              if use_val_if
                code += "\n" + indent("val #{section_var} = #{sections_access(property_name)}.getOrNull(#{index})", depth + 1)
                code += "\n" + indent("if (#{section_var} != null) {", depth + 1)
              else
                code += "\n" + indent("#{sections_access(property_name)}.getOrNull(#{index})?.let { #{section_var} ->", depth + 1)
              end

              # Header
              if section['header']
                header_class = cell_class_name(section['header'])
                code += "\n" + indent("#{section_var}.header?.let { headerData ->", depth + 2)
                code += "\n" + indent("val headerViewModel: #{header_class}ViewModel = viewModel(key = \"#{section['header']}_header_#{index}_\${viewModel.hashCode()}\")", depth + 3)
                code += "\n" + seed_view_model_line("headerViewModel", "headerData.data", depth + 3)
                code += "\n" + indent("LaunchedEffect(headerData.data) { headerViewModel.updateData(headerData.data) }", depth + 3)
                code += "\n" + edge_view_call(header_class, 'headerViewModel', depth + 3)
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
                code += "\n" + indent(unique_keys_line(data_access, cell_id_prop, 'sectionKeys'), depth + 3) if cell_id_prop
              end
              # The cell, with `cellIndex` in scope, at depth `d`.
              cell = lambda do |d|
                out = "\n" + indent("val currentCellData = #{data_access}[cellIndex]", d)
                if cell_id_prop
                  key = use_val_if ? "(currentCellData[\"cellId\"] as? String) ?: (currentCellData[\"#{cell_id_prop}\"] as? String) ?: \"$cellIndex\"" : 'sectionKeys[cellIndex]'
                  out += "\n" + indent("val cellId = #{key}", d)
                  out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", d)
                else
                  out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", d)
                end
                out += "\n" + seed_view_model_line("cellViewModel", "currentCellData", d)
                out += "\n" + indent("LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }", d)
                out += "\n" + indent("#{cell_class}View(", d)
                out += "\n" + indent("viewModel = cellViewModel,", d + 1)
                # No fillMaxWidth: the cell view defines its own size (dynamic
                # honors the declared width; a full-width cell declares
                # matchParent itself). Stretching here was the parity deviation
                # measured across every android Collection fixture.
                place = if places
                          before = drawn_cells_before(sections, index) { |j| "#{scroll_sections_expr(property_name)}.getOrNull(#{j})?.cells?.data?.size" }
                          ".onGloballyPositioned { collectionCellPlaces[#{before}cellIndex] = it }"
                        else
                          ''
                        end
                out += "\n" + cell_test_tag_modifier(json_data['id'], 'cellIndex', d + 1, place)
                out + "\n" + indent(")", d)
              end
              # A grid per section: a section of more than one column (its own
              # `columns`, else the Collection's) is laid out in rows of that
              # many, as sjui codegen and SwiftJsonUI Dynamic draw it. This
              # drew one cell per row (measured on d084cfb2, 2026-09-26).
              per_row = non_lazy_section_columns(json_data, section)
              if per_row
                spacing = json_data['columnSpacing'] || json_data['itemSpacing']
                required_imports&.add(:arrangement) if spacing
                row_args = spacing ? "modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(spacing)})" : 'modifier = Modifier.fillMaxWidth()'
                code += "\n" + indent("#{data_access}.chunked(#{per_row}).forEachIndexed { rowIndex, rowCells ->", depth + 3)
                code += "\n" + indent("Row(#{row_args}) {", depth + 4)
                code += "\n" + indent("rowCells.indices.forEach { columnIndex ->", depth + 5)
                code += "\n" + indent("val cellIndex = rowIndex * #{per_row} + columnIndex", depth + 6)
                code += "\n" + indent("Box(modifier = Modifier.weight(1f)) {", depth + 6)
                code += cell.call(depth + 7)
                code += "\n" + indent("}", depth + 6)
                code += "\n" + indent("}", depth + 5)
                code += "\n" + indent("repeat(#{per_row} - rowCells.size) { Spacer(modifier = Modifier.weight(1f)) }", depth + 5)
                code += "\n" + indent("}", depth + 4)
                code += "\n" + indent("}", depth + 3)
              else
                code += "\n" + indent("#{data_access}.forEachIndexed { cellIndex, _ ->", depth + 3)
                code += cell.call(depth + 4)
                code += "\n" + indent("}", depth + 3)
              end
              code += "\n" + indent("}", depth + 2)

              # Footer
              if section['footer']
                footer_class = cell_class_name(section['footer'])
                code += "\n" + indent("#{section_var}.footer?.let { footerData ->", depth + 2)
                code += "\n" + indent("val footerViewModel: #{footer_class}ViewModel = viewModel(key = \"#{section['footer']}_footer_#{index}_\${viewModel.hashCode()}\")", depth + 3)
                code += "\n" + seed_view_model_line("footerViewModel", "footerData.data", depth + 3)
                code += "\n" + indent("LaunchedEffect(footerData.data) { footerViewModel.updateData(footerData.data) }", depth + 3)
                code += "\n" + edge_view_call(footer_class, 'footerViewModel', depth + 3)
                code += "\n" + indent("}", depth + 2)
              end

              code += "\n" + indent("}", depth + 1)
            end
          elsif sections.empty? && (names = class_list(json_data))
            code += class_list_eager_body(json_data, names, depth + 1, required_imports, first_only: false,
                                          columns_info: columns_emit_info(json_data), places: places)
          end

          code += "\n" + indent("}", depth)
          code
        end

        # Non-lazy horizontal path: Row + forEachIndexed, no LazyRow, no
        # horizontalScroll. Expects an already-scrollable parent.
        def self.generate_non_lazy_row(json_data, sections, depth, required_imports, parent_type)
          required_imports&.add(:launched_effect)
          required_imports&.add(:remember) # seed_view_model_line

          items_property = json_data['items']

          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          # contentPadding / insets pad the cells (round 15), as KotlinJsonUI
          # Dynamic's Row pads them; this Row applied none until jsonui-cli 1.9.0.
          content_padding = non_lazy_content_padding(json_data, is_horizontal: true)
          modifiers << content_padding if content_padding
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # Along the scroll axis (horizontal_scroll_spacing); this read
          # columnSpacing, then itemSpacing, until jsonui-cli 1.9.0.
          column_spacing = horizontal_scroll_spacing(json_data)

          code = indent("Row(", depth)
          code += Helpers::ModifierBuilder.format(modifiers, depth)
          if column_spacing
            required_imports&.add(:arrangement)
            code += ",\n" + indent("horizontalArrangement = Arrangement.spacedBy(#{Helpers::BoundValue.dp(column_spacing)})", depth + 1)
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

              code += "\n" + indent("// Section #{index + 1}: #{Helpers::ModifierBuilder.comment_text(cell_view_name)}", depth + 1)
              code += "\n" + indent("#{sections_access(property_name)}.getOrNull(#{index})?.let { section ->", depth + 1)
              code += "\n" + indent("section.cells?.let { cellData ->", depth + 2)
              code += "\n" + indent(unique_keys_line('cellData.data', cell_id_prop, 'sectionKeys'), depth + 3) if cell_id_prop
              code += "\n" + indent("cellData.data.forEachIndexed { cellIndex, _ ->", depth + 3)
              code += "\n" + indent("val currentCellData = cellData.data[cellIndex]", depth + 4)
              if cell_id_prop
                code += "\n" + indent("val cellId = sectionKeys[cellIndex]", depth + 4)
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_rowCell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 4)
              else
                code += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_rowCell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", depth + 4)
              end
              code += "\n" + seed_view_model_line("cellViewModel", "currentCellData", depth + 4)
              code += "\n" + indent("LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }", depth + 4)
              code += "\n" + indent("#{cell_class}View(", depth + 4)
              code += "\n" + indent("viewModel = cellViewModel,", depth + 5)
              code += "\n" + cell_test_tag_modifier(json_data['id'], 'cellIndex', depth + 5)
              code += "\n" + indent(")", depth + 4)
              code += "\n" + indent("}", depth + 3)
              code += "\n" + indent("}", depth + 2)
              code += "\n" + indent("}", depth + 1)
            end
          elsif sections.empty? && (names = class_list(json_data))
            code += class_list_eager_body(json_data, names, depth + 1, required_imports, first_only: true)
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
          required_imports&.add(:remember) # seed_view_model_line
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
                           # The horizontal rule; this read itemSpacing, then
                           # columnSpacing, then lineSpacing until jsonui-cli 1.9.0.
                           horizontal_scroll_spacing(json_data)
                         else
                           json_data['lineSpacing'] || json_data['sectionSpacing'] || json_data['itemSpacing'] || json_data['spacing']
                         end

          # userScrollEnabled (binding aware)
          user_scroll_enabled_expr = user_scroll_enabled_expr(json_data)

          # Content padding
          content_padding_expr = collection_stack_content_padding_expr(json_data, is_horizontal: is_horizontal)

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
          modifiers.concat(Helpers::ModifierBuilder.build_shadow(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          # Container-level listStyle chrome, same recipe as the grid route:
          # the dynamic component paints it on every route, so the
          # CollectionStack face leaving it off drew the declared box's own
          # background below the cells while dynamic drew the chrome surface
          # (Collection_hideSeparator/control listStyle-grouped, d=10, runs
          # 31202080745/31234163967). Emitted after the declared background —
          # the chrome is the list's inner surface.
          chrome_style = JsonUIShared::EnumSpelling.lowered(json_data['listStyle'], 'Collection', 'listStyle').to_s
          if %w[grouped insetgrouped sidebar].include?(chrome_style)
            required_imports&.add(:shape)
            required_imports&.add(:material_theme)
            if %w[insetgrouped sidebar].include?(chrome_style)
              modifiers << ".padding(horizontal = 16.dp)"
              corner = chrome_style == 'insetgrouped' ? 12 : 8
              modifiers << ".clip(RoundedCornerShape(#{Helpers::BoundValue.dp(corner)}))"
            end
            surface = chrome_style == 'sidebar' ? 'surfaceContainerLow' : 'surfaceContainer'
            modifiers << ".background(MaterialTheme.colorScheme.#{surface})"
          end
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          # The EAGER container scrolls to its cells by the rule the lazy one
          # follows (4f ruling 2026-09-27, round 12): an Int the counted cell,
          # a String a key, on a change, landed by scrollAnchor; and
          # defaultScrollAnchor applies. Its scroll is the caller's
          # (eagerScrollState) and its cells are found where they were laid out
          # (non_lazy_scroll_prelude): the viewport is recorded here, after the
          # padding — the verticalScroll CollectionStack adds comes next. A
          # bound `lazy` decides at run time. Until jsonui-cli 1.9.0 neither
          # attribute moved an EAGER CollectionStack.
          scroll_to_raw = json_data['scrollTo']
          has_scroll_to = scroll_to_raw && scroll_to_raw.match(/@\{([^}]+)\}/)
          eager = case json_data['lazy']
                  when 'eager' then :only
                  when /\A@\{[^}]+\}\z/ then 'collectionStackMode == CollectionStackMode.EAGER'
                  end
          stack_default_anchor = default_scroll_anchor?(json_data, non_lazy: !eager.nil?)
          eager_scroll = eager && (has_scroll_to || stack_default_anchor) ? eager : nil
          # The vertical EAGER container draws reverseLayout (CollectionStack's
          # ReversedColumn, round 13): its content is emitted as the reversed
          # lazy content is, and its scroll runs from its bottom.
          eager_reversed = !is_horizontal && json_data['reverseLayout'] == true
          modifiers << '.onGloballyPositioned { collectionViewport[0] = it }' if eager_scroll
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
          code = ""

          if eager_scroll
            code += indent("val collectionStackMode = #{mode_expr}", depth) + "\n"
            mode_expr = 'collectionStackMode'
            code += non_lazy_scroll_prelude(depth, required_imports, is_horizontal: is_horizontal, reversed: eager_reversed)
          end
          lazy_state = (has_scroll_to || stack_default_anchor) && eager_scroll != :only
          if lazy_state
            required_imports&.add(:lazy_grid_state)
            code += indent("val collectionStackState = androidx.compose.foundation.lazy.rememberLazyListState()", depth) + "\n"
          end
          if has_scroll_to || stack_default_anchor
            code += scroll_to_effect(json_data, sections, depth, required_imports, target: :stack, state: 'collectionStackState',
                                     is_horizontal: is_horizontal, non_lazy: eager_scroll)
            code += default_scroll_anchor_code(json_data, 'collectionStackState', depth, required_imports, sections: sections,
                                               route: :stack, is_horizontal: is_horizontal, non_lazy: eager_scroll,
                                               non_lazy_reversed: eager_reversed)
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
              code += indent("val section#{idx} = #{sections_access(property_name)}.getOrNull(#{idx})", depth) + "\n"
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
            code += "\n" + indent("spacing = #{Helpers::BoundValue.dp(spacing_value)},", depth + 1)
          end
          if user_scroll_enabled_expr != 'true'
            code += "\n" + indent("userScrollEnabled = #{user_scroll_enabled_expr},", depth + 1)
          end
          if content_padding_expr
            code += "\n" + indent("contentPadding = #{content_padding_expr},", depth + 1)
          end
          # insetHorizontal rides in contentPadding with everything else
          # (collection_stack_content_padding_expr): on a row it was also
          # handed as CollectionStack's insetLeading / insetTrailing, which
          # replace contentPadding on the LAZY row and stand in for it with
          # spacers on the EAGER and NONE rows — so insetVertical and the safe
          # area dropped there, and a spaced EAGER row put its spacing after the
          # leading spacer too. KotlinJsonUI Dynamic's rows pad by contentPadding
          # (4f ruling 2026-09-27, round 17).
          if reverse_layout
            code += "\n" + indent("reverseLayout = true,", depth + 1)
          end
          if !is_horizontal && content_at_bottom?(json_data)
            code += "\n" + indent("// Requires KotlinJsonUI >= 2.42.0 (CollectionStack contentAtBottom)", depth + 1)
            code += "\n" + indent("contentAtBottom = true,", depth + 1)
          end
          # A short vertical list sits in the middle for a center anchor, on the
          # LAZY and EAGER containers (column_content_alignment, round 16).
          if !is_horizontal && (column_alignment = column_content_alignment(json_data))
            required_imports&.add(:alignment)
            code += "\n" + indent("// Requires KotlinJsonUI >= 2.42.0 (CollectionStack columnContentAlignment)", depth + 1)
            code += "\n" + indent("columnContentAlignment = #{column_alignment},", depth + 1)
          end
          # A short row sits where defaultScrollAnchor says, on the LAZY and
          # EAGER rows (row_content_alignment, round 15).
          if is_horizontal && (row_alignment = row_content_alignment(json_data))
            required_imports&.add(:alignment)
            code += "\n" + indent("// Requires KotlinJsonUI >= 2.42.0 (CollectionStack rowContentAlignment)", depth + 1)
            code += "\n" + indent("rowContentAlignment = #{row_alignment},", depth + 1)
          end
          if lazy_state
            code += "\n" + indent("lazyState = collectionStackState,", depth + 1)
          end
          if eager_scroll
            code += "\n" + indent("// Requires KotlinJsonUI >= 2.42.0 (CollectionStack eagerScrollState)", depth + 1)
            code += "\n" + indent("eagerScrollState = collectionScroll,", depth + 1)
          end

          # lazyContent block
          code += "\n" + indent("lazyContent = {", depth + 1)
          code += generate_collection_stack_lazy_content(json_data, sections, depth + 2, required_imports)
          code += "\n" + indent("},", depth + 1)

          # eagerContent block
          code += "\n" + indent("eagerContent = {", depth + 1)
          code += generate_collection_stack_eager_content(json_data, sections, depth + 2, required_imports, places: !eager_scroll.nil?,
                                                          reversed: eager_reversed)
          code += "\n" + indent("}", depth + 1)

          code += "\n" + indent(")", depth)
          code
        end

        # `.padding(…)` of the content padding for a container that is not a
        # lazy list (the non-lazy Column and Row, the flow), or nil: the same
        # PaddingValues the lazy routes take (collection_stack_content_padding_expr).
        def self.non_lazy_content_padding(json_data, is_horizontal:)
          expr = collection_stack_content_padding_expr(json_data, is_horizontal: is_horizontal)
          expr ? ".padding(#{expr})" : nil
        end

        # The values of a contentPadding / insets declaration as the SSoT's
        # Collection.insets declares them, or nil: a number, or 1, 2 or 4 values
        # — an array, or a string separated by `|` (whitespace and commas too) —
        # read as `paddings` reads them: one, every side; two, [vertical,
        # horizontal]; four, [top, right, bottom, left]. KotlinJsonUI Dynamic
        # reads the same (parseCollectionPadding). Until jsonui-cli 1.9.0 this
        # read four values as [top, left, bottom, right], only an array of
        # four, and no string (4f ruling 2026-09-27, round 16).
        def self.content_padding_values(value)
          values = case value
                   when Numeric then [value]
                   when Array then value
                   when String then value.split(/[|\s,]+/).map { |v| Float(v, exception: false) }.compact
                   end
          values if values && [1, 2, 4].include?(values.length)
        end

        # PaddingValues of those values (content_padding_values), right and
        # left as end and start.
        def self.content_padding_expr(values)
          dp = ->(v) { Helpers::BoundValue.dp(v.is_a?(Float) && v == v.floor ? v.to_i : v) }
          case values.length
          when 1 then "PaddingValues(#{dp.(values[0])})"
          when 2 then "PaddingValues(horizontal = #{dp.(values[1])}, vertical = #{dp.(values[0])})"
          else "PaddingValues(top = #{dp.(values[0])}, start = #{dp.(values[3])}, bottom = #{dp.(values[2])}, end = #{dp.(values[1])})"
          end
        end

        # PaddingValues expression for CollectionStack.contentPadding, or nil to
        # use the default (zero padding).
        #
        # A declared contentPadding / insets, insetHorizontal / insetVertical
        # and the safe area `contentInsetAdjustmentBehavior` asks for are
        # ADDED, side by side, as iOS adds them — measured 2026-09-27 on sjui
        # codegen and SwiftJsonUI Dynamic: insets [8,0,0,0] with insetVertical
        # 8 at the top of a 62pt safe area put the first cell at 78 (4f
        # rulings, rounds 16 and 17). Until jsonui-cli 1.9.0 a declared insets
        # replaced the other two (plan 49 lane C, #4: "the author named an
        # exact value" — adding keeps it too), and before round 16 the insets
        # replaced the safe area. Both of Collection's emitters go through this
        # one method (the grid path and the stack path, chosen by
        # `single_column_sections?`).
        def self.collection_stack_content_padding_expr(json_data, is_horizontal:)
          declared = [json_data['contentPadding'], json_data['insets']].lazy.map { |v| content_padding_values(v) }.find(&:itself)
          inset_h = json_data['insetHorizontal']
          inset_v = json_data['insetVertical']
          safe = Helpers::ContentInsetHelper.safe_area_padding(json_data['contentInsetAdjustmentBehavior'], horizontal: is_horizontal)
          return safe unless declared || inset_h || inset_v

          own = if declared && !inset_h && !inset_v
                  content_padding_expr(declared)
                elsif !declared
                  "PaddingValues(horizontal = #{Helpers::BoundValue.dp(inset_h || 0)}, vertical = #{Helpers::BoundValue.dp(inset_v || 0)})"
                end
          sides = content_padding_sides(declared, inset_h, inset_v)
          own ||= "PaddingValues(top = #{sides[0]}, start = #{sides[3]}, bottom = #{sides[2]}, end = #{sides[1]})"
          return own unless safe

          # Added to the safe area side by side, start and end in the layout's
          # direction.
          "#{safe}.let { safe -> val dir = androidx.compose.ui.platform.LocalLayoutDirection.current; " \
            "PaddingValues(start = safe.calculateStartPadding(dir) + #{sides[3]}, top = safe.calculateTopPadding() + #{sides[0]}, " \
            "end = safe.calculateEndPadding(dir) + #{sides[1]}, bottom = safe.calculateBottomPadding() + #{sides[2]}) }"
        end

        # [top, end, bottom, start] as Dp expressions: the declared values
        # (content_padding_values; right the end, left the start) plus
        # insetVertical on the top and bottom and insetHorizontal on the start
        # and end. Numbers are summed here; a binding is its own term.
        def self.content_padding_sides(declared, inset_h, inset_v)
          base = case declared&.length
                 when 1 then [declared[0]] * 4
                 when 2 then [declared[0], declared[1], declared[0], declared[1]]
                 when 4 then declared
                 else [0, 0, 0, 0]
                 end
          adds = [inset_v, inset_h, inset_v, inset_h]
          base.zip(adds).map do |terms|
            numbers, bound = terms.compact.partition { |t| t.is_a?(Numeric) }
            total = numbers.sum
            total = total.to_i if total.is_a?(Float) && total == total.floor
            parts = bound.map { |b| Helpers::BoundValue.dp(b) }
            parts << Helpers::BoundValue.dp(total) if total != 0 || parts.empty?
            parts.join(' + ')
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

            out += "\n" + indent("// Section #{index + 1}: #{Helpers::ModifierBuilder.comment_text(cell_view_name)}", depth)
            out += "\n" + indent("if (section#{index} != null) {", depth)

            if section['header']
              header_class = cell_class_name(section['header'])
              out += "\n" + indent("// Section #{index + 1} Header: #{Helpers::ModifierBuilder.comment_text(section['header'])}", depth + 1)
              out += "\n" + indent("section#{index}.header?.let { headerData ->", depth + 1)
              out += "\n" + indent("item {", depth + 2)
              out += "\n" + indent("val headerViewModel: #{header_class}ViewModel = viewModel(key = \"#{section['header']}_header_#{index}_\${viewModel.hashCode()}\")", depth + 3)
              out += "\n" + seed_view_model_line("headerViewModel", "headerData.data", depth + 3)
              out += "\n" + indent("LaunchedEffect(headerData.data) { headerViewModel.updateData(headerData.data) }", depth + 3)
              out += "\n" + edge_view_call(header_class, 'headerViewModel', depth + 3)
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

            key_expr = if cell_id_prop && auto_tracking
                         "key = { idx -> #{lazy_key("(#{data_access}[idx][\"cellId\"] as? String) ?: (#{data_access}[idx][\"#{cell_id_prop}\"] as? String) ?: idx.toString()", index)} }"
                       elsif cell_id_prop
                         out += "\n" + indent(unique_keys_line(data_access, cell_id_prop, "lazyKeys#{index}"), depth + 2)
                         "key = { idx -> #{lazy_key("lazyKeys#{index}[idx]", index)} }"
                       end

            if key_expr
              out += "\n" + indent("items(#{data_access}.size, #{key_expr}) { cellIndex ->", depth + 2)
            else
              out += "\n" + indent("items(#{data_access}.size) { cellIndex ->", depth + 2)
            end

            on_item_appear = json_data['onItemAppear']
            if (appear_name = Helpers::ModifierBuilder.string_event_name(on_item_appear))
              out += "\n" + indent("LaunchedEffect(Unit) { data.#{Helpers::BindingExpression.path_only(appear_name)}?.invoke(cellIndex) }", depth + 3)
            end

            out += "\n" + indent("val currentCellData = #{data_access}[cellIndex]", depth + 3)
            if cell_id_prop
              out += "\n" + indent("val cellId = #{auto_tracking ? "(currentCellData[\"cellId\"] as? String) ?: (currentCellData[\"#{cell_id_prop}\"] as? String) ?: \"$cellIndex\"" : "lazyKeys#{index}[cellIndex]"}", depth + 3)
              out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 3)
            else
              out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", depth + 3)
            end
            out += "\n" + seed_view_model_line("cellViewModel", "currentCellData", depth + 3)
            out += "\n" + indent("LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }", depth + 3)
            # The CollectionStack route is the one the sectioned single-column
            # fixtures take — the chrome and the declared cell sizes must
            # apply HERE, not only on the grid route (C0 until 2026-08-08).
            if (stack_chrome = chrome_open(json_data, required_imports))
              out += "\n" + indent(stack_chrome, depth + 3)
            end
            if (cell_box = cell_size_box_open(json_data, required_imports))
              out += "\n" + indent(cell_box, depth + 3)
            end
            out += "\n" + indent("#{cell_class}View(", depth + 3)
            out += "\n" + indent("viewModel = cellViewModel,", depth + 4)
            collection_id = json_data['id']
            # No fillMaxWidth on cells — see the grid path note above.
            out += "\n" + cell_test_tag_modifier(collection_id, 'cellIndex', depth + 4)
            out += "\n" + indent(")", depth + 3)
            if cell_size_box_open(json_data, nil)
              out += "\n" + indent("}", depth + 3)
            end
            if chrome_open(json_data, nil)
              out += "\n" + indent("}", depth + 3)
            end
            out += "\n" + indent("}", depth + 2)
            out += "\n" + indent("}", depth + 1)

            if section['footer']
              footer_class = cell_class_name(section['footer'])
              out += "\n" + indent("// Section #{index + 1} Footer: #{Helpers::ModifierBuilder.comment_text(section['footer'])}", depth + 1)
              out += "\n" + indent("section#{index}.footer?.let { footerData ->", depth + 1)
              out += "\n" + indent("item {", depth + 2)
              out += "\n" + indent("val footerViewModel: #{footer_class}ViewModel = viewModel(key = \"#{section['footer']}_footer_#{index}_\${viewModel.hashCode()}\")", depth + 3)
              out += "\n" + seed_view_model_line("footerViewModel", "footerData.data", depth + 3)
              out += "\n" + indent("LaunchedEffect(footerData.data) { footerViewModel.updateData(footerData.data) }", depth + 3)
              out += "\n" + edge_view_call(footer_class, 'footerViewModel', depth + 3)
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
        # `places`: each cell records where it was laid out, by its place among
        # the drawn cells (non_lazy_scroll_prelude).
        # `reversed`: the sections last-first, as the reversed lazy content emits
        # them — CollectionStack's ReversedColumn draws the EAGER content from
        # the bottom up, so the two modes draw one picture (round 13).
        def self.generate_collection_stack_eager_content(json_data, sections, depth, required_imports, places: false, reversed: false)
          items_property = json_data['items']
          property_name = items_property && items_property.match(/@\{([^}]+)\}/) ? $1 : nil
          cell_id_prop = json_data['cellIdProperty']
          auto_tracking = json_data['autoChangeTrackingId'] == true

          out = ""
          unless property_name
            out += "\n" + indent("// No items binding specified", depth)
            return out
          end

          ordered = sections.each_with_index.to_a
          ordered = ordered.reverse if reversed
          ordered.each do |(section, index)|
            cell_view_name = section['cell']
            next unless cell_view_name
            cell_class = cell_class_name(cell_view_name)

            out += "\n" + indent("// Section #{index + 1}: #{Helpers::ModifierBuilder.comment_text(cell_view_name)}", depth)
            out += "\n" + indent("if (section#{index} != null) {", depth)

            if section['header']
              header_class = cell_class_name(section['header'])
              out += "\n" + indent("section#{index}.header?.let { headerData ->", depth + 1)
              out += "\n" + indent("val headerViewModel: #{header_class}ViewModel = viewModel(key = \"#{section['header']}_header_#{index}_\${viewModel.hashCode()}\")", depth + 2)
              out += "\n" + seed_view_model_line("headerViewModel", "headerData.data", depth + 2)
              out += "\n" + indent("LaunchedEffect(headerData.data) { headerViewModel.updateData(headerData.data) }", depth + 2)
              out += "\n" + edge_view_call(header_class, 'headerViewModel', depth + 2)
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

            out += "\n" + indent(unique_keys_line(data_access, cell_id_prop, "eagerKeys#{index}"), depth + 2) if cell_id_prop && !auto_tracking
            out += "\n" + indent("#{data_access}.forEachIndexed { cellIndex, _ ->", depth + 2)
            on_item_appear = json_data['onItemAppear']
            if (appear_name = Helpers::ModifierBuilder.string_event_name(on_item_appear))
              out += "\n" + indent("LaunchedEffect(Unit) { data.#{Helpers::BindingExpression.path_only(appear_name)}?.invoke(cellIndex) }", depth + 3)
            end

            out += "\n" + indent("val currentCellData = #{data_access}[cellIndex]", depth + 3)
            if cell_id_prop
              out += "\n" + indent("val cellId = #{auto_tracking ? "(currentCellData[\"cellId\"] as? String) ?: (currentCellData[\"#{cell_id_prop}\"] as? String) ?: \"$cellIndex\"" : "eagerKeys#{index}[cellIndex]"}", depth + 3)
              out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellId}_\${viewModel.hashCode()}\")", depth + 3)
            else
              out += "\n" + indent("val cellViewModel: #{cell_class}ViewModel = viewModel(key = \"#{cell_view_name}_cell_#{index}_\${cellIndex}_\${viewModel.hashCode()}\")", depth + 3)
            end
            out += "\n" + seed_view_model_line("cellViewModel", "currentCellData", depth + 3)
            out += "\n" + indent("LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }", depth + 3)
            # The CollectionStack route is the one the sectioned single-column
            # fixtures take — the chrome and the declared cell sizes must
            # apply HERE, not only on the grid route (C0 until 2026-08-08).
            if (stack_chrome = chrome_open(json_data, required_imports))
              out += "\n" + indent(stack_chrome, depth + 3)
            end
            if (cell_box = cell_size_box_open(json_data, required_imports))
              out += "\n" + indent(cell_box, depth + 3)
            end
            out += "\n" + indent("#{cell_class}View(", depth + 3)
            out += "\n" + indent("viewModel = cellViewModel,", depth + 4)
            collection_id = json_data['id']
            # No fillMaxWidth on cells — see the grid path note above.
            place = places ? ".onGloballyPositioned { collectionCellPlaces[#{drawn_cells_before(sections, index) { |j| "section#{j}?.cells?.data?.size" }}cellIndex] = it }" : ''
            out += "\n" + cell_test_tag_modifier(collection_id, 'cellIndex', depth + 4, place)
            out += "\n" + indent(")", depth + 3)
            if cell_size_box_open(json_data, nil)
              out += "\n" + indent("}", depth + 3)
            end
            if chrome_open(json_data, nil)
              out += "\n" + indent("}", depth + 3)
            end
            out += "\n" + indent("}", depth + 2)
            out += "\n" + indent("}", depth + 1)

            if section['footer']
              footer_class = cell_class_name(section['footer'])
              out += "\n" + indent("// Section #{index + 1} Footer: #{Helpers::ModifierBuilder.comment_text(section['footer'])}", depth + 1)
              out += "\n" + indent("section#{index}.footer?.let { footerData ->", depth + 1)
              out += "\n" + indent("val footerViewModel: #{footer_class}ViewModel = viewModel(key = \"#{section['footer']}_footer_#{index}_\${viewModel.hashCode()}\")", depth + 2)
              out += "\n" + seed_view_model_line("footerViewModel", "footerData.data", depth + 2)
              out += "\n" + indent("LaunchedEffect(footerData.data) { footerViewModel.updateData(footerData.data) }", depth + 2)
              out += "\n" + edge_view_call(footer_class, 'footerViewModel', depth + 2)
              out += "\n" + indent("}", depth + 1)
            end

            out += "\n" + indent("}", depth)
          end

          out
        end

        # The drawn cells before section `index` (the sections that name a
        # cell, in order), as a Kotlin sum ending in " + ", or "" for none;
        # the block gives a section's cell count expression (nullable Int).
        def self.drawn_cells_before(sections, index)
          before = sections.first(index).each_with_index.select { |section, _| section.is_a?(Hash) && section['cell'] }.map(&:last)
          before.map { |j| "(#{yield(j)} ?: 0) + " }.join
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