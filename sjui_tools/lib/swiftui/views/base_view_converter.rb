# frozen_string_literal: true

require_relative 'template_helper'
require_relative '../binding/binding_expression'
require_relative 'alignment_helper'
require_relative 'frame_helper'
require_relative 'color_helper'
require_relative 'spacing_helper'
require_relative 'value_expression_helper'
require_relative 'modifier_helper'
require_relative 'modifier_bag'
require_relative '../binding/binding_handler_registry'
require_relative '../../core/attribute_validator'
require_relative '../../core/tap_accessibility'
require_relative '../../core/string_literals'
require_relative '../helpers/string_manager_helper'

module SjuiTools
  module SwiftUI
    module Views
      class BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::StringManagerHelper
        include TemplateHelper
        include AlignmentHelper
        include FrameHelper
        include ColorHelper
        include SpacingHelper
        include ValueExpressionHelper
        include ModifierHelper

        # Class-level validator instance (shared across all converters)
        @@validator = nil
        @@validation_enabled = true

        # Enable or disable validation
        def self.validation_enabled=(enabled)
          @@validation_enabled = enabled
        end

        def self.validation_enabled?
          @@validation_enabled
        end

        # Per-file normalization state, set by JsonToSwiftUIConverter from
        # the root `$jui` marker (Core::Normalization.canonicalized?)
        # before converting a layout. When true, alias attribute
        # spellings were already rewritten to their canonical names by
        # `jui build` normalizeLayouts, and converters take the
        # canonical-only lookup path (see #attr_with_alias). Class-level
        # for the same reason as validation_enabled: converters are
        # instantiated per node deep inside helpers without a shared
        # per-conversion config object.
        @@layout_normalized = false

        def self.layout_normalized=(normalized)
          @@layout_normalized = normalized
        end

        def self.layout_normalized?
          @@layout_normalized
        end

        attr_reader :state_variables, :modifier_bag

        # Injected onto every node under a scrolling container by
        # JsonToSwiftUIConverter#mark_scrolling_ancestors (one walk from the
        # root, after includes are expanded) — the same channel as
        # `parent_orientation`: a converter sees only its own hash.
        SCROLLING_ANCESTOR_KEY = '_scrolling_ancestor'
        # Set on the ROOT of a layout that some Collection renders as a cell
        # / header / footer (CollectionCellIndex). Not propagated.
        COLLECTION_CELL_ROOT_KEY = '_collection_cell_root'

        def initialize(component, indent_level = 0, action_manager = nil, binding_registry = nil)
          @component = component
          @indent_level = indent_level
          @action_manager = action_manager
          @generated_code = []
          @state_variables = []
          @binding_registry = binding_registry || SjuiTools::SwiftUI::Binding::BindingHandlerRegistry.new
          @binding_handler = @binding_registry.get_handler(@component['type'] || 'View')
          @modifier_bag = ModifierBag.new

          # Note: Validation is now done in json_to_swiftui_converter.rb's validate_json_tree
          # which properly passes parent_orientation to handle weight validation correctly

          # includeとvariables処理
          handle_include_and_variables
        end

        def convert
          raise NotImplementedError, "Subclasses must implement convert method"
        end

        def add_line(line)
          @generated_code << ("    " * @indent_level + line)
        end

        def add_modifier_line(modifier)
          add_line "    #{modifier}"
        end

        # Canonical-name attribute lookup with alias fallback.
        #
        # Reads `canonical` from @component first; when absent, each
        # alias spelling (from attribute_definitions.json `aliases`) is
        # consulted in order — but only for raw (L0) layouts. For
        # L1-normalized layouts (`$jui` marker) the normalizer has
        # already rewritten alias spellings, so the fallback is skipped
        # entirely and only the canonical name is honored.
        def attr_with_alias(canonical, *aliases)
          value = @component[canonical]
          return value unless value.nil?
          return nil if self.class.layout_normalized?

          aliases.each do |alias_name|
            value = @component[alias_name]
            return value unless value.nil?
          end
          nil
        end

        # Compute the modifier lines apply_modifiers WOULD register for the
        # supplied attributes, without mutating persistent converter state or
        # writing anything to @generated_code. Used by the responsive
        # container path so each branch can emit padding / margin /
        # background / etc. derived from the branch-merged attrs.
        #
        # `exclude_keys` are stripped from the temp attrs before
        # apply_modifiers runs — used to suppress duplicates with the
        # frame/center handling that
        # ResponsiveHelper.build_responsive_modifiers already emits.
        def collect_modifiers_for(attrs, exclude_keys: [])
          cleaned = (attrs || {}).dup
          cleaned.delete('responsive')
          exclude_keys.each { |k| cleaned.delete(k) }
          # Stack-line concerns (orientation / spacing) are baked into
          # build_container_line per branch; they're not modifiers.
          cleaned.delete('orientation')
          cleaned.delete('spacing')

          saved_component = @component
          saved_bag = @modifier_bag
          saved_code = @generated_code

          @component = cleaned
          @modifier_bag = ModifierBag.new
          @generated_code = []

          begin
            apply_modifiers
            @modifier_bag.to_lines
          ensure
            @component = saved_component
            @modifier_bag = saved_bag
            @generated_code = saved_code
          end
        end

        protected

        # Get value with binding support
        def get_binding_value(key, default = nil)
          value = @component[key]
          @binding_handler.get_value(value, default)
        end

        # Check if a value is a binding expression
        def is_binding?(value)
          @binding_handler.is_binding?(value)
        end

        # The PATH a binding expression names.
        # "@{propertyName}"        -> "propertyName"
        # "@{!propertyName}"       -> "propertyName" (negation stripped)
        # "@{propertyName ?? 12}"  -> "propertyName" (default stripped)
        #
        # Callers paste the result after `data.` / `$data.`, so what they need
        # is the path and nothing else. The regexp this used to run captured
        # everything between the braces, which carried the inline default out
        # with it: `@{gap ?? 12}` produced `$data.gap ?? 12` in a two-way
        # position and `data.gap ?? 12` unbracketed in a value one. Both are
        # the canonical parser being bypassed rather than a spelling gap
        # (plan 49; the same shape as kjui's `process_dimension`), so the
        # answer comes from `BindingExpression.parse` instead.
        #
        # A value that is not a binding is returned unchanged — several
        # callers pass a name that is already bare.
        def extract_binding_property(value)
          return nil unless value.is_a?(String)
          return value unless SjuiTools::SwiftUI::Binding::BindingExpression.binding?(value)

          SjuiTools::SwiftUI::Binding::BindingExpression.parse(value[2..-2]).path
        end

        # Check if a binding expression is negated
        # "@{!propertyName}" -> true
        # "@{propertyName}" -> false
        def is_negated_binding?(value)
          return false unless value.is_a?(String)
          value =~ /^@\{!.+\}$/
        end

        # Read-only Swift value expression for a binding.
        # "@{propertyName}"        -> "data.propertyName"
        # "@{!propertyName}"       -> "!data.propertyName"
        # "@{propertyName ?? 12}"  -> "data.propertyName ?? 12" (optional only)
        #
        # Routed through the canonical emitter rather than string-building the
        # `data.` prefix here: negation of an Optional needs the unwrap that
        # `swift_value_expr` writes, and an inline default on a NON-optional
        # property is dead code the canonical precedence rule drops.
        def binding_data_expr(value)
          return "data.#{value}" unless SjuiTools::SwiftUI::Binding::BindingExpression.binding?(value)

          SjuiTools::SwiftUI::Binding::BindingExpression.swift_value_expr(value[2..-2])
        end

        # Apply binding modifiers into the modifier bag
        def apply_binding_modifiers
          skip = []
          # Skip keys already handled by converter (registered in bag)
          skip << 'background' if @modifier_bag.key?(:background)
          # canTap is the tap's gate (tap_gesture_line), never hit testing.
          skip << 'canTap'
          skip << 'userInteractionEnabled' if @interaction_gates_registered
          modifiers = @binding_handler.process_bindings(@component, skip_keys: skip)
          modifiers.each do |modifier|
            next unless modifier
            # Categorize binding modifier into the correct bag key
            bag_key = categorize_binding_modifier(modifier)
            if bag_key
              @modifier_bag.register(bag_key, modifier)
            else
              # Unknown modifier - append as component_specific
              @modifier_bag.append(:component_specific, modifier)
            end
          end
        end

        def handle_include_and_variables
          # include処理は専用のIncludeConverterで処理するため、
          # ここではメタデータのみを記録
          if @component['include']
            # includeがある場合は、IncludeConverterが処理することを示すコメントを追加
            add_line "// Component will be replaced by IncludeConverter"
            add_line "// include: #{@component['include']}"

            if @component['shared_data']
              add_line "// shared_data: #{@component['shared_data'].to_json}"
            end

            if @component['data']
              add_line "// data: #{@component['data'].to_json}"
            end

            if @component['variables']
              add_line "// variables: #{@component['variables'].to_json}"
            end
          end
        end

        def indent(&block)
          @indent_level += 1
          yield
          @indent_level -= 1
        end

        # Component types whose SwiftUI representation is a plain layout
        # container (HStack/VStack/ZStack/ScrollView wrapper) that does not
        # become an accessibility element on its own. Keep in sync with
        # SwiftJsonUI DynamicModifierHelper.accessibilityContainerTypes.
        ACCESSIBILITY_CONTAINER_TYPES = %w[
          view safeareaview scrollview scroll
          blur blurview gradientview gradient
          embed
        ].freeze
        # `embed` is here because EmbedContainer is a plain wrapper view: a
        # bare .accessibilityIdentifier on it is pushed down into the
        # embedded screen and clobbers the identifier of that screen's root
        # container (its nearest descendant element) — the embedded root id
        # then never resolves in XCUITest while pane leaves still do. The
        # merge-hazard anchor is always emitted for an id-bearing Embed
        # (its subtree is unknown at codegen time, contribution 0).

        # Component types that are guaranteed to surface at least one
        # accessibility element of their own when visible (text, controls,
        # images). Used to decide whether a container can ever collapse to a
        # single accessibility child (the "merge hazard" — see
        # apply_accessibility_identifier). Types NOT listed here (Collection,
        # Table, Web, TabView, Include, Embed, DynamicComponent, bare
        # decorative Views…) may yield zero elements at runtime, so they are
        # conservatively not counted.
        CERTAIN_ACCESSIBILITY_ELEMENT_TYPES = %w[
          label text iconlabel button
          textfield edittext input textview
          image circleimage networkimage
          switch toggle checkbox check radio
          segment progress slider indicator selectbox
        ].freeze

        def generated_code
          # Emit all modifiers from the bag in correct order
          @modifier_bag.emit_all(self)

          # accessibilityIdentifier for UI testing - auto-added for all components with id
          # ID prefixes from includes are already applied during JSON processing
          if @component['id'] && !@accessibility_identifier_added
            apply_accessibility_identifier
            @accessibility_identifier_added = true
            apply_outer_disabled
          elsif collection_cell_root_without_id?
            apply_collection_cell_root_container
          end
          @generated_code.join("\n")
        end

        # `.disabled` again, OUTSIDE the accessibility element.
        #
        # The bag emits `.disabled(...)` before the identifier, and
        # `apply_accessibility_identifier` then forms the container's
        # accessibility element ON TOP of it. An element formed outside the
        # disabled environment never receives the notEnabled trait, so
        # XCUITest reads the target as enabled while the view really is
        # disabled.
        #
        # Not a deduction: the dynamic face hit this on the same fixture and
        # wrote the finding down. `DynamicModifierHelper.standardOrder` carries
        # a second `Stage("disabledOuter")` after `Stage("accessibilityId")`,
        # annotated "measured: the View-hosted enabled__false conformance
        # fixture". This mirrors that stage.
        #
        # Double application is harmless — `.disabled(true)` is idempotent and
        # the inner one still governs the subtree's own controls — and this is
        # NOT a duplicate to be tidied away.
        #
        # A responsive container emits its modifiers per size class INSIDE its
        # `responsiveN` wrapper (ResponsiveHelper.generate_container_function),
        # so its own bag holds no `:disabled` while the identifier is applied
        # at the call site, outside the wrapper — and nothing followed the
        # identifier: XCUITest read the node as enabled while it was disabled
        # (a View with `responsive` and a bound `enabled`, measured on an iOS
        # simulator by a UI test). `@outer_disabled` carries the
        # line for that path.
        def apply_outer_disabled
          line = @modifier_bag[:disabled] || @outer_disabled
          add_modifier_line line if line
        end

        # A Collection wraps every cell it renders with
        # `.accessibilityIdentifier("{collectionId}_item_{index}")`. A plain
        # SwiftUI container is not an accessibility element, so that
        # identifier is pushed down onto the nearest descendants — the cell
        # root's own direct children — and they answer to `{id}_item_{N}`
        # instead of the identifiers they declared.
        #
        # A cell root that declares an `id` never had this problem: the
        # id-bearing path above makes it an explicit container first, and the
        # wrapper's identifier then lands on the wrapper. That is the whole
        # discriminator, measured across 8 cells of one consumer: 8/8
        # explained by "does the cell root declare an id".
        #
        # So a cell root becomes a container whether or not it has an id.
        # WITHOUT an identifier of its own — it has none to emit, and the
        # wrapper's `{id}_item_{N}` is the address the drivers use.
        #
        # Scope is deliberately the cell ROOT only, not every id-less
        # container: emitting accessibility scaffolding for all of them is
        # what exhausted a device's main-thread stack once already (see the
        # DEPTH BUDGET note below).
        #
        # WHY THE TWO FACES DIFFER (declared, so it reads as design and not
        # as drift). Here the container goes on the cell ROOT, which is
        # possible because `sjui build` sees the whole project and marks the
        # layouts some Collection renders (CollectionCellIndex) before
        # conversion. The dynamic renderer has no such pass at the point it
        # wraps a cell: the cell's JSON is loaded inside DynamicView, so the
        # root's `id` is not knowable there without reading a file per cell.
        # It makes the WRAPPER the element instead
        # (CollectionConverter.buildCellView). Same outcome for the
        # children; different node carries the container.
        #
        # The consequence of that difference is the single-child merge: this
        # side can compute `accessibility_merge_hazard?` from the root's
        # declaration and emits the anchor only where it is needed, while
        # the dynamic side cannot, and an unconditional anchor there would
        # be the DEPTH BUDGET regression on every cell. Whether dynamic
        # needs one is left to the conformance fixtures that run through it.
        def apply_collection_cell_root_container
          # A root combined into one button (tap_accessibility_lines) is an
          # element already; a container around it would hide it again.
          return if combined_tap?

          # The same single-child merge the id path guards against, for the
          # same reason and by the same means. `.contain` alone is not enough
          # when the container can end up with fewer than two accessibility
          # children: SwiftUI collapses it into that single child, and the
          # WRAPPER's `{id}_item_{N}` then lands on the child after all —
          # the defect this method exists to remove, surviving in cells with
          # one child. Found by reading the id path's own hazard check rather
          # than by a failing test; the arms below pin both sides.
          if accessibility_merge_hazard?
            add_modifier_line ".overlay(alignment: .topLeading) {"
            indent do
              add_modifier_line "Color.clear"
              add_modifier_line "    .frame(width: 0.5, height: 0.5)"
              add_modifier_line "    .accessibilityElement(children: .ignore)"
            end
            add_modifier_line "}"
          end
          add_modifier_line ".accessibilityElement(children: .contain)"
        end

        # The root of a layout some Collection renders as a cell, which
        # declares no id of its own. The mark is set on the root only, by
        # JsonToSwiftUIConverter, from the project-wide CollectionCellIndex.
        def collection_cell_root_without_id?
          return false unless @component[COLLECTION_CELL_ROOT_KEY] == true
          return false if @component['id']
          # Same suppression as the id path: a statically invisible node must
          # not become an accessibility element.
          return false if @component['visibility'] == 'invisible' || @component['hidden'] == true

          accessibility_container?
        end

        # Emit the accessibilityIdentifier for this component, matching the
        # Dynamic-mode semantics of DynamicModifierHelper.applyAccessibilityId:
        #
        # - Statically invisible components must not become accessibility
        #   elements at all — explicit accessibility containers ignore an
        #   ancestor's .accessibilityHidden(true), so emitting one here would
        #   leave an invisible view findable by VoiceOver / UI tests.
        #   (The library VisibilityWrapper collapses + hides the subtree.)
        # - Plain SwiftUI containers are not accessibility elements, so a bare
        #   .accessibilityIdentifier is pushed down onto the nearest descendant
        #   element — it never surfaces for the container itself and can
        #   clobber a child's own identifier (e.g. a screen root "root" View
        #   overwriting the id of the single control inside it). Make the
        #   container an explicit accessibility container first; this matches
        #   the UIKit path, where every UIView with an id is queryable by
        #   XCUITest, and keeps all descendant elements accessible.
        # - The invisible 0.5pt anchor overlay prevents SwiftUI from merging
        #   two nested containers when the outer one has exactly one
        #   accessibility child (the merge drops the inner container's
        #   identifier): with the anchor the container has at least two
        #   children, so it is never collapsed into its single child.
        #
        # DEPTH BUDGET (device stack-overflow regression, see
        # docs/bugs report sjui-container-accessibility-anchor-overlay-
        # stack-overflow-on-device): the anchor overlay adds several
        # ModifiedContent layers plus an overlay-content subtree to the
        # screen's single generic body expression. Emitted unconditionally it
        # is an O(all-containers) depth cost — on a real device (smaller main
        # thread stack than the simulator) a large screen exhausted the stack
        # during one DEBUG body evaluation. The merge hazard only exists when
        # the container can end up with fewer than two accessibility
        # children, so the anchor is now emitted only for those containers
        # (accessibility_merge_hazard?); every other id-bearing container
        # gets just .accessibilityElement(children: .contain) +
        # .accessibilityIdentifier (2 flat modifier lines).
        def apply_accessibility_identifier
          # hidden: true is the boolean shorthand for visibility:"invisible"
          # (space-kept, not drawn, hidden from accessibility) — both static
          # spellings must suppress the identifier for the same reason.
          return if @component['visibility'] == 'invisible' || @component['hidden'] == true

          # A tappable combined into one button carries its own element
          # (tap_accessibility_lines): the identifier lands on it, and the
          # container — and its anchor — would split it back into children.
          if accessibility_container? && !combined_tap?
            if accessibility_merge_hazard?
              add_modifier_line ".overlay(alignment: .topLeading) {"
              indent do
                add_modifier_line "Color.clear"
                add_modifier_line "    .frame(width: 0.5, height: 0.5)"
                add_modifier_line "    .accessibilityElement(children: .ignore)"
              end
              add_modifier_line "}"
            end
            add_modifier_line ".accessibilityElement(children: .contain)"
          end
          # Third candidate for a BOUND `hidden` (the first two were measured
          # wrong and reverted). The static spelling returns above and emits no
          # identifier at all — that is what makes a statically hidden view
          # unfindable, and the dynamic face does the same thing
          # (`applyAccessibilityId` returns early for visibility "invisible").
          #
          # A binding cannot return early at codegen time, and the two things
          # tried instead both failed on the host: `.accessibilityHidden` after
          # the identifier, and collapsing the container with `children:
          # .ignore`. The library says why — an explicit accessibility
          # container ignores `.accessibilityHidden` — but collapsing it was
          # not enough either, and the one difference left against the working
          # dynamic recipe is that dynamic emits NO IDENTIFIER while hidden.
          #
          # A flat modifier chain cannot skip a line conditionally, so the
          # identifier itself carries the condition: the declared id while
          # visible, and an empty one while hidden, which no query for the id
          # matches.
          hidden_binding = @component['hidden'] if is_binding?(@component['hidden'])
          if hidden_binding
            expr = binding_data_expr(hidden_binding)
            add_modifier_line ".accessibilityIdentifier(#{expr} ? \"\" : #{swift_string_literal(@component['id'])})"
          else
            add_modifier_line ".accessibilityIdentifier(#{swift_string_literal(@component['id'])})"
          end
        end

        # Whether the container this converter EMITS becomes an accessibility
        # element on its own. Type is enough for every component whose emitted
        # shape is fixed, which is what ACCESSIBILITY_CONTAINER_TYPES lists.
        # A converter whose shape depends on the declaration overrides this
        # rather than adding its type to that list — the list's own sentence
        # ("types whose SwiftUI representation is a plain layout container")
        # would become false for the shapes that do not match.
        def accessibility_container?
          ACCESSIBILITY_CONTAINER_TYPES.include?((@component['type'] || '').downcase) || custom_container?
        end

        # A project's own component (a converter `sjui g converter` scaffolded
        # into views/extensions) that the layout gives children. Its view draws
        # them inside a content slot that is no more an accessibility element
        # than a VStack is, so the bare identifier was pushed down onto them:
        # measured (XCUITest, iOS 26.5, 2026-09-25, the codegen host) a custom
        # container with one child had its id found on the child and the
        # child's own id 0 times; with two, its id twice. The list above names
        # this tool's types and cannot name a project's. SwiftJsonUI's
        # DynamicModifierHelper.isCustomContainer answers the same for a
        # registered adapter. Ticket
        # sjui-custom-container-takes-its-childrens-identifiers.
        def custom_container?
          return false unless self.class.name.to_s.start_with?('SjuiTools::SwiftUI::Views::Extensions::')

          JsonUIShared::TapAccessibility.children(@component).any? { |c| c['type'] || c['include'] }
        end

        # A container is at risk of the single-child accessibility merge
        # (which drops the inner element's identifier) only when its subtree
        # can yield fewer than two accessibility children at runtime. This is
        # a conservative static approximation: a child contributes only when
        # it is *guaranteed* to be present and to surface accessibility
        # elements —
        #   - statically always visible (no visibility attribute, or the
        #     literal "visible"; bindings / invisible / gone may vanish)
        #   - a guaranteed element type (CERTAIN_ACCESSIBILITY_ELEMENT_TYPES)
        #     contributes 1; an id-bearing container contributes 1 (it becomes
        #     an explicit accessibility container itself under this same
        #     rule); an id-less plain container contributes its own
        #     guaranteed children (they are promoted to the grandparent's
        #     accessibility children)
        # Anything uncertain (includes, Collection/Table/Web, data-driven
        # subtrees) contributes 0, so uncertainty errs toward emitting the
        # anchor, never toward dropping a needed one.
        #
        # Keep in sync with SwiftJsonUI
        # DynamicModifierHelper.accessibilityMergeHazard.
        def accessibility_merge_hazard?
          guaranteed_accessible_child_count(@component) < 2
        end

        def guaranteed_accessible_child_count(component)
          child_nodes(component).sum { |c| guaranteed_accessibility_contribution(c) }
        end

        def child_nodes(component)
          raw = component['child'] || []
          nodes = raw.is_a?(Array) ? raw : [raw]
          # Ignore data declarations ({"data": ...} without type/include)
          nodes.select { |c| c.is_a?(Hash) && (c['type'] || c['include']) }
        end

        def guaranteed_accessibility_contribution(child)
          return 0 if child['include'] # unknown subtree at this stage

          visibility = child['visibility']
          return 0 if visibility && visibility != 'visible'

          type = (child['type'] || '').downcase
          if ACCESSIBILITY_CONTAINER_TYPES.include?(type)
            # id-bearing container: becomes an explicit accessibility
            # container (a single element) under apply_accessibility_identifier
            return 1 if child['id']

            # plain container: its accessible descendants are promoted to the
            # grandparent's accessibility children (2 is enough — the caller
            # only compares against 2)
            return [guaranteed_accessible_child_count(child), 2].min
          end

          CERTAIN_ACCESSIBILITY_ELEMENT_TYPES.include?(type) ? 1 : 0
        end

        # 共通のモディファイア適用メソッド
        def apply_modifiers(skip_padding: false, skip_insets: false)
          # アライメント処理を先に適用
          apply_center_alignment
          apply_edge_alignment

          # パディング（内側のスペース）を先に適用
          apply_padding unless skip_padding

          # サイズ制約とサイズをパディングの後に適用
          apply_frame_constraints
          apply_frame_size

          # insetsとinsetHorizontalの処理（Collectionではspacerで処理するためスキップ可能）
          apply_insets unless skip_insets

          # 背景色（Rectangleの場合はfillで設定済みなのでスキップ）
          # enabled状態に応じて背景色を変更
          if @component['enabled'] == false && @component['disabledBackground']
            # 無効状態の背景色
            color = get_swiftui_color(@component['disabledBackground'])
            @modifier_bag.register(:background, ".background(#{color})")
          elsif gradient_wins_over_background?
            # `backgroundFill` ruling (2026-08-07): one fill per surface and
            # the more specific declaration wins, so a declared gradient makes
            # `background` the fallback rather than a layer underneath it.
            # Emitting both put `.background(colour)` immediately before
            # `.background(gradient)` in MODIFIER_ORDER, and SwiftUI lays the
            # later one further back — the declared gradient never showed.
            @modifier_bag.register(:background, "")
          elsif @component['background'] && !@modifier_bag.key?(:background)
            bg_value = @component['background']
            if bg_value.is_a?(String) && bg_value.start_with?('@{')
              # Binding background - resolve here at the correct position (before margins)
              bg_expr = SwiftUI::Binding::BindingExpression.swift_value_expr(bg_value[2..-2])
              @modifier_bag.register(:background, ".background(SwiftJsonUIConfiguration.shared.getColor(for: #{bg_expr}) ?? Color.clear)")
            else
              processed_bg = process_template_value(bg_value)
              if processed_bg.is_a?(Hash) && processed_bg[:template_var]
                @modifier_bag.register(:background, ".background(#{get_swiftui_color(bg_value)})")
              else
                color = get_swiftui_color(bg_value)
                @modifier_bag.register(:background, ".background(#{color})")
              end
            end
          end

          # コーナー半径（背景の直後に適用）
          if @component['cornerRadius']
            @modifier_bag.register(:corner_radius, ".cornerRadius(#{@component['cornerRadius'].to_i})")
          end

          # ボーダー（cornerRadiusの直後、marginsの前に適用）
          # Dynamic mode: CommonModifiers.swift line 59
          if (border_code = border_overlay)
            @modifier_bag.register(:border, border_code)
          end

          # マージン（外側のスペース - SwiftUIではpaddingで実装）
          apply_margins

          # 透明度 (alphaとopacityの両方をサポート)
          alpha_value = attr_with_alias('opacity', 'alpha')
          if alpha_value
            if is_binding?(alpha_value)
              @modifier_bag.register(:opacity, ".opacity(#{binding_data_expr(alpha_value)})")
            else
              @modifier_bag.register(:opacity, ".opacity(#{alpha_value})")
            end
          end

          # Liquid Glass (iOS 26+). Emits ONE call to the library helper, never
          # an `if #available` here: an availability check in generated code
          # would be duplicated at every site that declares `glass`, and each
          # copy asks the RUNNING OS, so the picture would vary by device. The
          # helper holds the single check (ruling: iOS lane, 2026-09-14).
          #
          # `shape` is deliberately NOT resolved here. `rounded(N)` and `rect`
          # could be, but `capsule` and `circle` depend on the laid-out height,
          # which codegen does not know — so all four go to the helper as a
          # value and the mapping stays in one place rather than being split
          # across two layers by what happens to be statically knowable.
          apply_glass

          # visibility属性はVisibilityWrapperで処理するので、ここでは何もしない
          # The actual wrapping happens in the parent view converter

          # 影
          if @component['shadow']
            shadow_code = build_shadow_modifier(@component['shadow'])
            @modifier_bag.register(:shadow, shadow_code) if shadow_code
          end

          # クリップ
          # A binding is truthy in Ruby, so this used to clip every
          # declaration that used one regardless of the property's value. The
          # bound form is ViewBindingHandler's now — SwiftJsonUI's
          # `clipToBounds(_:)` takes the flag as a PARAMETER, so it resolves
          # at render time instead of freezing at whatever the generator saw.
          # A literal keeps emitting `.clipped()`: same view, same bytes.
          if @component['clipToBounds'] == true || @component['clipToBounds'] == 'true'
            @modifier_bag.register(:clip_to_bounds, ".clipped()")
          end

          # オフセット（offsetX, offsetY）
          register_offset_modifier

          # 表示/非表示 — hidden は visibility:"invisible" のブールショートハンド:
          # レイアウトスペースは保持したまま描画とアクセシビリティのみ消す
          # (.hidden() や条件付き削除でスペースを潰さない)
          hidden_value = @component['hidden']
          if hidden_value == true
            @modifier_bag.register(:hidden, ".opacity(0).accessibilityHidden(true)")
          elsif is_binding?(hidden_value)
            # Binding: "@{isErrorHidden}" ->
            #   .opacity(data.isErrorHidden ? 0 : 1).accessibilityHidden(data.isErrorHidden)
            # Binding: "@{!isVisible}" ->
            #   .opacity(!data.isVisible ? 0 : 1).accessibilityHidden(!data.isVisible)
            hidden_expr = binding_data_expr(hidden_value)
            @modifier_bag.register(:hidden, ".opacity(#{hidden_expr} ? 0 : 1).accessibilityHidden(#{hidden_expr})")
          end

          # safeAreaInsetPositions
          apply_safe_area_insets_to_bag

          # enabled, canTap, userInteractionEnabled, touchDisabledState
          register_interaction_gates

          # tagプロパティの適用（TabViewなどで使用）
          if @component['tag']
            @modifier_bag.register(:tag, ".tag(#{@component['tag']})")
          end

          # classNameプロパティ（SwiftUIではスタイル識別子として記録）
          if @component['className']
            add_line "// className: #{@component['className']}"
          end

          if @component['touchDisabledState']
            add_line "// touchDisabledState applied"
          end

          # tintColor（アクセントカラー）
          #
          # The bound branch used to emit the property bare — `.tint(data.x)`
          # — and `.tint()` takes a `Color`. Against the usual String property
          # naming a colour that is `cannot convert value of type 'String' to
          # expected argument type 'Color'`, which stopped the whole ios
          # conformance host on `common/tintColor__binding`. Nothing caught it
          # earlier because the binding DID reach the output: `codegen-effect`
          # asks whether it survived, not whether it typechecks.
          #
          # `get_swiftui_color` handles both spellings and both data types —
          # a String property is wrapped in `getColor(for:)`, a Color-typed
          # one passes through — so the branch goes away with the defect.
          if @component['tintColor']
            @modifier_bag.register(:tint_color, ".tint(#{get_swiftui_color(@component['tintColor'])})")
          end

          # バインディング関連プロパティ（コメントとして記録）
          if @component['bindingScript']
            add_line "// bindingScript: #{@component['bindingScript']}"
          end
          if @component['binding_group']
            add_line "// binding_group: #{@component['binding_group']}"
          end
          if @component['binding_id']
            add_line "// binding_id: #{@component['binding_id']}"
          end
          if @component['shared_data']
            add_line "// shared_data: #{@component['shared_data']}"
          end

          # indexBelow（Z軸順序の指定）
          if @component['indexBelow']
            # indexBelowは指定した他のビューの下に配置することを意味する可能性
            # SwiftUIではzIndexを使用して相対的な前後関係を制御
            add_line "// indexBelow: #{@component['indexBelow']} - Place below specified view"
            # 数値の場合はzIndexとして使用、文字列の場合は他のビューIDを参照
            if @component['indexBelow'].to_s =~ /^\d+$/
              @modifier_bag.append(:z_index, ".zIndex(-#{@component['indexBelow'].to_i})")
            else
              add_line "// Reference to view ID: #{@component['indexBelow']}"
              @modifier_bag.append(:z_index, ".zIndex(-1)")  # デフォルトで背面に配置
            end
          end

          # indexAbove — the mirror of indexBelow: in front. The view-ID form
          # degrades to zIndex(+1), a numeric to zIndex(+N) (same degradation
          # indexBelow ships; a true relative order would need the other
          # view's resolved z).
          if @component['indexAbove']
            if @component['indexAbove'].to_s =~ /^\d+$/
              @modifier_bag.append(:z_index, ".zIndex(#{@component['indexAbove'].to_i})")
            else
              @modifier_bag.append(:z_index, ".zIndex(1)")
            end
          end

          # クリックイベント
          # onClick (camelCase) -> binding format only (@{functionName})
          # `onclick` (lowercase) names a method directly — no binding — and is
          # what UIKit wires to a UITapGestureRecognizer selector
          # (SJUIView: `Selector(onclick)`). It was declared, used in real
          # layouts, and read by nobody on the SwiftUI path, so every screen
          # migrating from UIKit lost its taps silently. camelCase wins when
          # both are present.
          register_click_lines

          apply_long_press_to_bag
          apply_pan_to_bag
          apply_pinch_to_bag
          apply_highlighted_to_bag

          # Lifecycle events (SwiftUI only)
          apply_lifecycle_events_to_bag

          # confirmationDialog / alert (iOS 15+)
          apply_confirmation_dialog_to_bag
          apply_alert_to_bag
        end

        # The gates on a view's interaction, static or bound, for every
        # converter (label_converter calls it too — it builds its own
        # modifiers, and a Label with a tap used to keep it under
        # `canTap: false` and ignore a bound `enabled`):
        #
        # - `enabled` is `.disabled` (the literal, or the binding negated).
        #   SwiftUI's `.disabled` also covers interactive descendants, so it
        #   is the right modifier for a container.
        # - `userInteractionEnabled` and `touchDisabledState` are
        #   `.allowsHitTesting`: one modifier, their conditions joined — they
        #   stop the whole view. The bound form was ViewBindingHandler's,
        #   which only the converters that process bindings reach;
        #   `apply_binding_modifiers` leaves it to this method once it has run.
        # - `canTap` is not here: it gates the tap's handler, not the view
        #   (register_click_lines, tap_gesture_line).
        def register_interaction_gates
          @interaction_gates_registered = true
          disabled = disabled_line(@component['enabled'])
          @modifier_bag.register(:disabled, disabled) if disabled

          register_hit_test_gate
        end

        # `userInteractionEnabled` and `touchDisabledState`: one
        # `.allowsHitTesting`, which the bag writes outside the view's own
        # gestures (MODIFIER_ORDER). The converters that build their own
        # modifiers and handle `enabled` themselves — Button, TextField,
        # TextView, SelectBox — call this alone: they read neither flag, and
        # a TextField read the binding only (ViewBindingHandler).
        def register_hit_test_gate
          @interaction_gates_registered = true
          gates = []
          gates << 'false' if @component['touchDisabledState']
          value = @component['userInteractionEnabled']
          if value == false
            gates << 'false'
          elsif is_binding?(value)
            gates << tap_gate_expr(value)
          end
          return if gates.empty?

          condition = gates.include?('false') ? 'false' : gates.join(' && ')
          @modifier_bag.register(:allows_hit_testing, ".allowsHitTesting(#{condition})")
        end

        # `.disabled` for an `enabled` value: the literal false, or the binding
        # negated; nil when it does not disable.
        def disabled_line(enabled)
          return '.disabled(true)' if enabled == false
          return nil unless is_binding?(enabled)

          ".disabled(!(#{tap_gate_expr(enabled)}))"
        end

        def tap_gate_expr(binding)
          SwiftUI::Binding::BindingExpression.swift_bool_expr(binding[2..-2])
        end

        # The tap, one rule for every converter (label_converter calls it too:
        # it builds its own modifiers and had kept only the binding onClick, so
        # the `onclick` fix above never reached a Label). camelCase wins when
        # both are present; a Button's tap is its action; a statically
        # disabled view gets none. A handler names a method
        # (TapAccessibility.handler?): `""`, `"   "`, `"@{}"`, `[]` and `[""]`
        # are no tap — they emitted `data.?()`, which is not Swift.
        #
        # `canTap` (attribute_definitions common.canTap, the SwiftUI tap gate)
        # stops the handler's call and nothing else: `false` emits no tap —
        # and so no button trait — and a binding gates the gesture itself
        # (tap_gesture_line). It was `.allowsHitTesting`, which stopped the
        # whole view: a control's own operation (a Switch, a Slider, a
        # TextField's input) and every control inside a tappable container,
        # which only `enabled` / `userInteractionEnabled` are for. The
        # dynamic runtime attaches no tap while the gate is shut and leaves
        # the view as it is (DynamicEventHelper.applyOnClick).
        def register_click_lines
          return if @component['type'] == 'Button'
          return if @component['enabled'] == false
          return if @component['canTap'] == false

          tap = JsonUIShared::TapAccessibility
          if tap.handler?(@component['onClick'])
            @modifier_bag.register(:on_click, build_on_click_lines(@component['onClick']))
          elsif tap.handler?(@component['onclick'])
            @modifier_bag.register(:on_click, build_selector_click_lines(@component['onclick']))
          end
        end

        # `onclick` values are method names, not bindings: a bare string, or an
        # array of them to call in order. A blank element is not called.
        def build_selector_click_lines(value)
          names = JsonUIShared::TapAccessibility.handler_values(value)
          calls = names.map { |n| "    data.#{to_camel_case(n)}?()" }
          can_tap = @component['canTap']
          if is_binding?(can_tap)
            return [".gesture(TapGesture().onEnded {"] + calls +
                   ["}, including: #{tap_gate_expr(can_tap)} ? .all : .subviews)"] + tap_accessibility_lines
          end
          [".onTapGesture {"] + calls + ["}"] + tap_accessibility_lines
        end

        # The tap for one handler call. Under a bound `canTap` the gesture is
        # masked while the binding is false — `including: .subviews` takes
        # this view's tap away and leaves its subviews' gestures (a control's
        # own, a child's tap) as they are.
        def tap_gesture_line(handler_call)
          indent_str = "    " * (@indent_level + 1)
          can_tap = @component['canTap']
          unless is_binding?(can_tap)
            return ".onTapGesture {\n#{indent_str}#{handler_call}\n#{indent_str[0...-4]}}"
          end

          ".gesture(TapGesture().onEnded {\n#{indent_str}#{handler_call}\n#{indent_str[0...-4]}}, " \
            "including: #{tap_gate_expr(can_tap)} ? .all : .subviews)"
        end

        # A handler call that a component makes from its own operation — a
        # Radio's selection, a CheckBox's value change, an IconLabel's action —
        # gated as the tap is: under a bound `canTap` it runs while the
        # binding is true. (`canTap: false` makes no call; the caller leaves it
        # out.) The component's own operation runs either way.
        def gated_handler_call(call)
          can_tap = @component['canTap']
          return call unless is_binding?(can_tap)

          "if #{tap_gate_expr(can_tap)} { #{call} }"
        end

        # What a screen reader is told about this tap
        # (shared/core/tap_accessibility.rb, set on the node before conversion):
        # a button as it is, one button made of its content, or — where it
        # holds a control of its own — nothing. Measured with XCUITest
        # (elementType, 2026-09-25): `.onTapGesture` alone is not a button;
        # `.isButton` under `.contain` makes every child a button; `.combine`
        # + `.isButton` is one button named by its content.
        def tap_accessibility_lines
          case @component[JsonUIShared::TapAccessibility::SHAPE_KEY]
          when 'button' then [button_trait_line]
          when 'combine'
            # The anchor the id path uses, for the same single-child merge:
            # with one accessible child, `.combine` took the child's own
            # identifier away (measured: the child's id found 0 times; with
            # the anchor, or two children, it is found). BEFORE `.combine`,
            # so the anchor is one of the children it combines.
            anchor = []
            if accessibility_merge_hazard?
              indent_str = "    " * (@indent_level + 1)
              anchor << ".overlay(alignment: .topLeading) {\n#{indent_str}Color.clear\n" \
                        "#{indent_str}    .frame(width: 0.5, height: 0.5)\n" \
                        "#{indent_str}    .accessibilityElement(children: .ignore)\n#{indent_str[0...-4]}}"
            end
            # An id-less combined tap takes its children's identifiers as its
            # own (measured, XCUITest 2026-09-25): one child's id was found
            # twice — on the button and on the child — and two children's
            # were joined ("a-b") on the button. An explicit empty identifier
            # keeps the button's own; a container with an id gets that id on
            # the button from the id path instead.
            own_id = @component['id'] ? [] : ['.accessibilityIdentifier("")']
            anchor + ['.accessibilityElement(children: .combine)', button_trait_line] + own_id
          else []
          end
        end

        # `.isButton`, or — under a bound canTap — `.isButton` while the gate is
        # open: the dynamic runtime attaches neither the tap nor its traits
        # while the binding is false (DynamicEventHelper.applyOnClick), and a
        # tap `.allowsHitTesting` has shut is not a button to VoiceOver either.
        def button_trait_line
          can_tap = @component['canTap']
          return '.accessibilityAddTraits(.isButton)' unless is_binding?(can_tap)

          ".accessibilityAddTraits(#{tap_gate_expr(can_tap)} ? AccessibilityTraits.isButton : [])"
        end

        def combined_tap?
          @component[JsonUIShared::TapAccessibility::SHAPE_KEY] == 'combine'
        end

        # onLongPress — binding-only (`@{handler}`), applied by the SwiftUI
        # Dynamic runtime (DynamicEventHelper) and by nothing in the codegen.
        def apply_long_press_to_bag
          handler = @component['onLongPress']
          return if handler.nil?
          return unless is_binding?(handler)

          prop = extract_binding_property(handler)
          @modifier_bag.register(:on_long_press, [
            ".onLongPressGesture {",
            "    data.#{prop}?()",
            "}"
          ])
        end

        # onPan — binding-only (`@{handler}`), fired repeatedly while the user
        # drags. simultaneousGesture so it composes with onClick taps and
        # Button actions; contentShape makes a background-less container
        # hittable across its full bounds (a transparent SwiftUI view is not).
        #
        # Payload: `value.translation` — cumulative CGSize since the gesture
        # began (the Compose emit accumulates deltas to match). The call shape
        # follows the declared closure class: () -> Void stays bare, (CGSize)
        # (optionally after a String id) receives the payload.
        def apply_pan_to_bag
          handler = @component['onPan']
          return if handler.nil?
          return unless is_binding?(handler)

          invocation = get_event_handler_invocation(handler, @component['id'], 'value.translation')
          @modifier_bag.register(:on_pan, [
            ".contentShape(Rectangle())",
            ".simultaneousGesture(",
            "    DragGesture(minimumDistance: 10).onChanged { value in",
            "        #{invocation}",
            "    }",
            ")"
          ])
        end

        # onPinch — binding-only, fired repeatedly while the user pinches with
        # `value.magnification` (cumulative CGFloat scale). MagnifyGesture is
        # the iOS 17+ replacement for the deprecated MagnificationGesture;
        # SwiftJsonUI's platform floor is iOS 17, so generated code can use it
        # unconditionally without deprecation warnings.
        def apply_pinch_to_bag
          handler = @component['onPinch']
          return if handler.nil?
          return unless is_binding?(handler)

          invocation = get_event_handler_invocation(handler, @component['id'], 'value.magnification')
          @modifier_bag.register(:on_pinch, [
            ".contentShape(Rectangle())",
            ".simultaneousGesture(",
            "    MagnifyGesture().onChanged { value in",
            "        #{invocation}",
            "    }",
            ")"
          ])
        end

        # highlighted — the pressed/selected appearance.
        #
        # UIKit swaps to `highlightBackgroundColor` when the flag is set
        # (SJUIView:187). SwiftUI has no such state, so this emits the same
        # swap against `highlightBackground`, driven by the flag. A binding lets
        # the screen control it; a literal `true` pins it on, which is what
        # UIKit's `attr["highlighted"].boolValue` does.
        def apply_highlighted_to_bag
          value = @component['highlighted']
          return if value.nil?
          highlight_bg = @component['highlightBackground']
          return if highlight_bg.nil?

          condition = if is_binding?(value)
                        "data.#{extract_binding_property(value)}"
                      elsif value == true || value == 'true'
                        'true'
                      else
                        return
                      end
          # The swap REPLACES the background in its own slot. Appending it to
          # :component_specific put the `.background` BEFORE `.frame(w, h)`,
          # so the highlight painted only the children's bounds while the
          # ordinary background painted the declared frame on top of the
          # order (View_highlighted__true parity, run 31202080745 — a 40pt
          # highlight patch inside a 200pt grey box). UIKit swaps the whole
          # view's backgroundColor (SJUIView:187); registering :background
          # wins over the unconditional registration and keeps the slot's
          # position after frame_size.
          else_color = @component['background'] ? get_swiftui_color(@component['background']) : 'Color.clear'
          @modifier_bag.register(
            :background,
            ".background(#{condition} ? #{get_swiftui_color(highlight_bg)} : #{else_color})"
          )
        end

        # Apply confirmationDialog modifier (iOS 15+) into the bag
        def apply_confirmation_dialog_to_bag
          apply_presented_dialog_to_bag(
            @component['confirmationDialog'], 'confirmationDialog', :confirmation_dialog
          )
        end

        # Apply alert modifier (iOS 15+) into the bag.
        #
        # `.alert` and `.confirmationDialog` take the same arguments except
        # for titleVisibility, so they share one emitter rather than a second
        # copy that can drift. The attribute exists because the two APIs do
        # NOT render the same: in a regular size class `.confirmationDialog`
        # draws no cancel button, while `.alert` draws it in both classes
        # (measured on iPhone 16 Pro / iPad A16 / iPad Pro M4 against the same
        # button set). The SSoT declares no titleVisibility for `alert`
        # because `.alert` has no such parameter — it always shows its title.
        def apply_alert_to_bag
          apply_presented_dialog_to_bag(@component['alert'], 'alert', :alert)
        end

        # The body of both. *attribute* names the SwiftUI modifier to emit,
        # which is spelled exactly like the attribute that drives it — an
        # attribute whose name disagrees with the API it emits is a name that
        # lies. *slot* is the modifier-bag key.
        #
        # The config is passed IN rather than read from @component here: the
        # conformance coverage scanner recognises a read by the literal
        # `@component['x']` form, so a computed key would report both
        # attributes as unread by any converter (measured — it did).
        def apply_presented_dialog_to_bag(dialog, attribute, slot)
          return unless dialog.is_a?(Hash)

          is_presented = dialog['isPresented']
          return unless is_presented

          # Extract binding property name for isPresented
          is_presented_var = extract_binding_property(is_presented)
          return unless is_presented_var

          # Get title (can be string or binding)
          title_value = dialog['title'] || ''
          if is_binding?(title_value)
            title_var = extract_binding_property(title_value)
            title_expr = "data.#{title_var}"
          else
            title_expr = get_text_with_string_manager("\"#{title_value}\"")
          end

          # titleVisibility is confirmationDialog's alone: `.alert` has no
          # such parameter, and the SSoT declares none for it.
          has_title_visibility = attribute == 'confirmationDialog'
          if has_title_visibility
            title_visibility = dialog['titleVisibility'] || 'automatic'
            title_visibility_expr = case title_visibility
            when 'visible'
              '.visible'
            when 'hidden'
              '.hidden'
            else
              '.automatic'
            end
          end

          # Check for layout or actions (one of them is required)
          layout_config = dialog['layout']
          actions = dialog['actions']

          # Return if neither layout nor actions is specified
          return unless layout_config || actions

          # Get message (optional, can be string or binding)
          message_value = dialog['message']
          has_message = !message_value.nil? && !message_value.to_s.empty?

          # Build the full confirmation dialog code as multi-line string
          lines = []
          lines << ".#{attribute}("
          lines << "    #{title_expr},"
          if has_title_visibility
            lines << "    isPresented: $data.#{is_presented_var},"
            lines << "    titleVisibility: #{title_visibility_expr}"
          else
            lines << "    isPresented: $data.#{is_presented_var}"
          end
          if has_message
            lines << ") {"
          else
            lines << ", actions: {"
          end

          # Generate actions content based on layout or actions binding
          if layout_config.is_a?(Hash)
            layout_name = layout_config['name']&.sub(/\.json$/, '')
            layout_data = layout_config['data']

            if layout_name && layout_data
              view_name = to_pascal_case(layout_name) + "View"
              data_var = extract_binding_property(layout_data)
              lines << "    #{view_name}(data: data.#{data_var})"
            end
          elsif actions
            actions_var = extract_binding_property(actions)
            lines << "    if let actionsView = data.#{actions_var}?() {"
            lines << "        actionsView"
            lines << "    }"
          end

          if has_message
            if is_binding?(message_value)
              message_var = extract_binding_property(message_value)
              message_expr = "data.#{message_var}"
            else
              message_expr = get_text_with_string_manager("\"#{message_value}\"")
            end
            lines << "} message: {"
            lines << "    Text(#{message_expr})"
            lines << "}"
          else
            lines << "})"
          end

          @modifier_bag.register(slot, lines)
        end

        # Legacy method - kept for backward compatibility with converters that call it directly
        def apply_confirmation_dialog
          apply_confirmation_dialog_to_bag
        end

        # Convert snake_case or kebab-case to PascalCase
        def to_pascal_case(str)
          str.split(/[-_]/).map(&:capitalize).join
        end

        # Apply lifecycle event modifiers into the bag
        def apply_lifecycle_events_to_bag
          if @component['onAppear']
            handler = @component['onAppear']
            lines = build_lifecycle_handler_lines('.onAppear', handler)
            @modifier_bag.register(:on_appear, lines)
          end

          if @component['onDisappear']
            handler = @component['onDisappear']
            lines = build_lifecycle_handler_lines('.onDisappear', handler)
            @modifier_bag.register(:on_disappear, lines)
          end
        end

        # Legacy method - kept for backward compatibility
        def apply_lifecycle_events
          apply_lifecycle_events_to_bag
        end

        # ヘルパーメソッド

        # Convert event handler to method call
        # SwiftUI uses onClick only (binding format: @{functionName})
        # If handler ends with ':', pass self as parameter
        def get_event_handler_call(handler)
          if is_binding?(handler)
            method_name = extract_binding_property(handler)
            if method_name.end_with?(':')
              "data.#{method_name.chomp(':')}?(self)"
            else
              "data.#{method_name}?()"
            end
          else
            # Direct function name (non-binding)
            if handler.end_with?(':')
              "data.#{handler.chomp(':')}?(self)"
            else
              "data.#{handler}?()"
            end
          end
        end

        # Draw one child of THIS container, honoring the child's `visibility`.
        #
        # 🚨 THE ONE DOOR FOR A CONTAINER THAT CALLS THE FACTORY ITSELF. A
        # plain View's children go through ChildRenderingHelper, which wraps a
        # child that declares `visibility` in `VisibilityWrapper(...)`. Three
        # containers (ScrollView, Blur, GradientView) drew their children with
        # `@converter_factory.create_converter(...)` directly and never asked
        # about visibility, so a `visibility: "@{x}"` on a ScrollView's direct
        # child compiled, built with 0 warnings, and was ALWAYS SHOWN on iOS —
        # while kjui wrapped the same child in VisibilityWrapper. Reported
        # 2026-09-20 from two consumer screens that had just moved a
        # visibility binding from the ScrollView to its child.
        #
        # The wrapper goes where the caller stands: inside the VStack a
        # single-child ScrollView builds, so the Spacer beside the child stays
        # (wrapping the VStack would hide the Spacer too and change what
        # weight / alignment mean). Returns the child's converter for state
        # propagation, or nil when the factory produced none.
        #
        # 🚨 A CONVERTER SCAFFOLDED BY `jui g converter` 1.8.107–1.8.111 STORES
        # THE FACTORY UNDER OTHER NAMES. Its `initialize` sets `@factory` /
        # `@registry`, the scaffold's own names, and never `@converter_factory`
        # / `@view_registry` — so once its `process_children` came through this
        # door (1.8.107), every child of a custom container was dropped: the
        # block came out `{\n}`, the build had 0 warnings, and the content was
        # missing on iOS only (kjui renders the same layout's children).
        # Reported 2026-09-24. The template now sets both names, but a scaffold
        # is user-owned once written and `jui sync_tool` never touches
        # `views/extensions/`, so a fix in the template alone would leave every
        # converter scaffolded in those five releases broken until someone
        # re-scaffolds it. Reading the scaffold's names as a fallback fixes
        # those in place with the next sync. Only the scaffold uses them
        # (`git grep -P '@factory\b|@registry\b' sjui_tools/lib`: the template
        # and nothing else).
        def render_child_honoring_visibility(child)
          factory = @converter_factory || @factory
          registry = @view_registry || @registry
          return nil unless factory
          if child.is_a?(Hash) && child['visibility']
            visibility_param = SwiftUI::Binding::BindingExpression.swift_visibility_param(child['visibility'])
            child_converter = factory.create_converter(child, @indent_level + 1, @action_manager, factory, registry)
            return nil unless child_converter
            add_line "VisibilityWrapper(#{visibility_param}) {"
            child_converter.convert.split("\n").each { |line| @generated_code << line }
            add_line "}"
          else
            child_converter = factory.create_converter(child, @indent_level, @action_manager, factory, registry)
            return nil unless child_converter
            child_converter.convert.split("\n").each { |line| @generated_code << line }
          end
          if child_converter.respond_to?(:state_variables) && child_converter.state_variables
            @state_variables.concat(child_converter.state_variables)
          end
          child_converter
        end

        # Get event handler invocation based on handler type definition
        # Checks data_definitions to determine if handler takes (viewId, value) or no arguments
        # @param handler [String] The handler binding expression (e.g., "@{onValueChange}")
        # @param view_id [String] The view ID to pass as first argument
        # @param value_expr [String, nil] The value expression to pass as second argument (nil for click events)
        # @return [String] The Swift code to invoke the handler
        def get_event_handler_invocation(handler, view_id, value_expr = nil)
          method_name = extract_binding_property(handler) || handler
          data_def = ColorHelper.data_definitions[method_name]

          if data_def && data_def['class']
            class_type = data_def['class'].to_s
            # Check for Event type or (String, Type) pattern
            # SwiftUI uses Void instead of Unit
            if class_type.include?('Event') || class_type.match?(/\(\s*\(?\s*String\s*[,)]/)
              if value_expr.nil?
                "data.#{method_name}?(\"#{view_id}\")"
              else
                "data.#{method_name}?(\"#{view_id}\", #{value_expr})"
              end
            elsif value_expr && class_type.match?(/\(\s*\(?\s*(Int|Bool|Boolean|Float|Double|Number|String|CGSize|CGFloat)\s*\)?\s*\)\s*->/)
              # Handler takes a single typed argument (e.g., (Int) -> Void).
              # CGSize / CGFloat are the onPan / onPinch gesture payloads.
              "data.#{method_name}?(#{value_expr})"
            elsif class_type.match?(/\(\s*\)\s*->/)
              # () -> Void type - no arguments
              "data.#{method_name}?()"
            else
              # Default to no arguments
              "data.#{method_name}?()"
            end
          else
            # No type definition found - default to no arguments
            "data.#{method_name}?()"
          end
        end

        private

        # `.offset(x:y:)` from the declared offsetX / offsetY.
        #
        # Both are declared with a binding face, and the emit interpolated the
        # raw JSON value into CODE position: `@{dx}` arrived in the generated
        # source verbatim, which is not a wrong program but not a program at
        # all — the build dies on it. `bound_number` is the arbiter that was
        # already resolving the same union everywhere else.
        #
        # One home, because this had grown a second copy in the TextField
        # converter and a vocabulary that exists twice drifts (plan 40).
        def register_offset_modifier
          return unless @component['offsetX'] || @component['offsetY']

          x = offset_component('offsetX')
          y = offset_component('offsetY')
          @modifier_bag.register(:offset, ".offset(x: #{x}, y: #{y})")
        end

        def offset_component(key)
          value = @component[key]
          return 0 if value.nil?

          bound_number(value) || value
        end

        # Categorize a binding modifier string into the correct bag key
        def categorize_binding_modifier(modifier)
          case modifier
          when /^\.background\(/
            :background
          when /^\.cornerRadius\(/
            :corner_radius
          when /^\.overlay\(/
            :border
          when /^\.foregroundColor\(/
            :foreground_color
          when /^\.opacity\(/
            :opacity
          when /^\.disabled\(/
            :disabled
          when /^\.frame\(/
            :frame_size
          when /^\.clipped\(/, /^\.clipToBounds\(/
            :clip_to_bounds
          when /^\.allowsHitTesting\(/
            :allows_hit_testing
          when /^\.tint\(/
            :tint_color
          when /^\.padding\(\.top/
            :padding
          when /^\.padding\(\.bottom/
            :padding
          when /^\.padding\(\.leading/
            :padding
          when /^\.padding\(\.trailing/
            :padding
          when /^\.padding\(/
            :padding
          when /^\.font\(/
            :component_specific
          when /^\.fontWeight\(/
            :component_specific
          else
            nil
          end
        end

        # Build border overlay code as a single multi-line string
        #: `indicatorStyle` / `style` as a scale factor. One home because two
        #: components read the same declared vocabulary — Indicator and
        #: Progress — and a second copy is how they drift (plan 40).
        INDICATOR_SIZE_SCALES = { 'large' => 1.5, 'small' => 0.8 }.freeze

        def indicator_size_scale(style)
          INDICATOR_SIZE_SCALES.fetch(style.to_s.downcase, 1.0)
        end

        # The border overlay this component declares, or nil when it declares
        # no border.
        #
        # **The rule lives in `shared/core/attribute_semantics.json`
        # (`semantics.border`), not here, and not in the type/enum/default of
        # `attribute_definitions.json`.** A border is drawn only when BOTH
        # `borderWidth` and `borderColor` are declared. There is no default
        # border colour: `borderWidth` alone draws nothing, `borderColor`
        # alone draws nothing, and `borderStyle` alone draws nothing — style
        # decorates a border the pair requests, it never summons one.
        # (2026-08-03 user rulings, measured 0 px on all three platforms in
        # plan 34's 2026-08-04 re-measure. A gray-default direction was tried
        # in d2c8628 and withdrawn; the ruling has since reversed direction
        # more than once whenever someone re-derived it from the declaration
        # instead of reading the contract.)
        #
        # `TextField.borderStyle` is a DIFFERENT attribute (UIKit text-field
        # chrome: roundedRect / line / bezel / none) and is outside this rule
        # — its converter passes `style_source: nil`.
        def border_overlay(corner_default = 0, style_source: @component['borderStyle'])
          width = @component['borderWidth']
          color = @component['borderColor']
          return nil if width.nil? || color.nil?

          corner = (@component['cornerRadius'] || corner_default).to_i
          build_border_overlay(border_color_expr(color), corner,
                               border_width_operand(width), style_source)
        end

        # The stroke width. A bound one is an expression — `.to_i` on a
        # binding is 0, which drew a zero-width border for every bound pair.
        def border_width_operand(width)
          bound_number(width) || width.to_i
        end

        # The stroke colour. A binding resolves through the same colour
        # registry a literal does; it used to be skipped here and re-emitted
        # by the binding handler as a SECOND overlay.
        # `glass` is declared on `common` with type [boolean, object]:
        #   true                      -> the default treatment
        #   {style:, tint:, interactive:, shape:}  -> each key optional
        #   false / absent            -> nothing emitted
        #
        # ⚠️ THE DECLARED VALUE SET IS NOT THE SAME ON BOTH iOS MODES.
        # SwiftUI's `Glass` has regular/clear/identity and `.glassEffect` takes
        # a shape; UIKit's `UIGlassEffectStyle` has only Regular and Clear and
        # `UIGlassEffect` (a UIVisualEffect subclass) has no shape parameter.
        # This emitter is the SwiftUI path, so it passes all four keys through;
        # the UIKit path cannot honour `identity` or `shape` and the
        # declaration says so.
        def apply_glass
          value = @component['glass']
          return if value.nil? || value == false || value == 'false'

          args = []
          if value.is_a?(Hash)
            style = value['style']
            args << "style: #{swift_string_literal(style)}" if style
            if (tint = value['tint'])
              args << "tint: #{get_swiftui_color(tint)}"
            end
            unless value['interactive'].nil?
              interactive = value['interactive'] == true || value['interactive'] == 'true'
              args << "interactive: #{interactive}"
            end
            if (shape = value['shape'])
              warn_unknown_glass_shape(shape) unless glass_shape_declared?(shape)
              args << "shape: #{swift_string_literal(shape)}"
            end
          end

          @modifier_bag.register(:glass, ".sjuiGlassEffect(#{args.join(', ')})")
        end

        # Is this shape spelling one the SSoT declares?
        #
        # The vocabulary is READ from attribute_definitions.json, never written here.
        # A copy in this file would be a second list to keep in step, and the one that
        # drifts is always the copy — the library already carried `rectangle`, which no
        # declaration ever defined, because it was written from SwiftUI's type name
        # instead of from the declaration.
        #
        # Two shapes of declaration are accepted, because the SSoT is mid-migration:
        # `properties.shape.enum` when it exists (machine-readable, preferred), and
        # otherwise the `shape: a|b|c` clause in the prose description. When the enum
        # lands, the prose path stops being used without this code changing.
        def glass_shape_declared?(shape)
            # ⚠️ `BaseViewConverter.` explicitly, not `self.class.` — every converter
            # subclass would otherwise memoise (and parse) its own copy, and a test
            # that swaps the declaration on the base class would not reach them.
            # Measured: the arm below failed for exactly this reason.
            vocabulary = BaseViewConverter.declared_glass_shapes
            if vocabulary.empty?
              # Nothing to check against, so every spelling passes. That is the right
              # behaviour and the wrong silence: "checked and fine" and "could not
              # check" must not look alike, or a declaration that loses its enum turns
              # this validation off with nothing said.
              #
              # This is NOT the population of the fallback removed above. That branch
              # could not run at all; this one can: `jui sync_tool` copies the tools
              # into a face, and a face carrying an older vendored definition while
              # running a newer sjui_tools reaches exactly this state.
              BaseViewConverter.warn_shape_validation_unavailable
              return true
            end

            spelling = shape.to_s.downcase
            return true if vocabulary.include?(spelling)

            # `rounded(N)` is a FORM, not a spelling: it carries a number, so it cannot
            # be an enum member. The declaration therefore lists it in prose while the
            # enum holds the three fixed words, and a check that only reads the enum
            # rejects every `rounded(12)` a consumer writes. Measured: with the enum
            # present, `rounded(12)` came back undeclared until this branch existed.
            BaseViewConverter.declares_rounded_form? && spelling.start_with?('rounded')
        end

        def warn_unknown_glass_shape(shape)
            declared = BaseViewConverter.declared_glass_shapes.join(', ')
            puts "\e[33m[SwiftUI Warning] glass shape #{shape.inspect} is not declared " \
                 "(declared: #{declared}). Emitting it anyway; the library falls back to " \
                 "the SDK default, so the screen renders but not as written.\e[0m"
        end

        # Does the declaration describe the parameterised `rounded(N)` form?
        #
        # Read from the prose deliberately: a form with an argument has no enum to live
        # in, so prose is where it can be declared at all. This is not a fallback for a
        # missing enum — the enum and this coexist.
        def self.declares_rounded_form?
            return @declares_rounded_form unless @declares_rounded_form.nil?

            description = find_glass_definition(load_attribute_definitions)&.fetch('description', nil).to_s
            @declares_rounded_form = description.downcase.include?('rounded(n)')
        end

        # Clears the parsed vocabulary. Exists for the arm that proves this code READS
        # the declaration: it swaps the declaration, clears, and checks the emitter's
        # answers follow. Without that arm, a hard-coded list passes every other test.
        def self.reset_declared_glass_shapes!
            @declared_glass_shapes = nil
            @declares_rounded_form = nil
            @warned_shape_validation_unavailable = nil
        end

        # Parsed once per process: the file does not change while a build runs.
        def self.declared_glass_shapes
            @declared_glass_shapes ||= begin
            glass = find_glass_definition(load_attribute_definitions)
            # ⚠️ A prose fallback used to sit here (`|| from_description(glass)`).
            # It was unreachable, and the reason is stronger than "the copies agree":
            # in the repository there is ONE file. `sjui_tools/lib/core/
            # attribute_definitions.json` is a symlink (mode 120000) to
            # `shared/core/attribute_definitions.json`, as are kjui's and rjui's — the
            # same blob, so they cannot disagree. In a distribution they become real
            # files, copied from the shared one by `installer/bootstrap.sh` (it removes
            # each symlink and copies the shared file over it), so they start life
            # identical there too.
            #
            # Removed rather than armed: an arm for a branch that cannot run protects
            # nothing and reads as coverage.
            from_enum(glass) || []
            end
        end

        # Said once per process, not per component: a build with fifty glass views
        # should report an unusable declaration once, not fifty times.
        def self.warn_shape_validation_unavailable
            return if @warned_shape_validation_unavailable

            @warned_shape_validation_unavailable = true
            puts "\e[33m[SwiftUI Warning] glass shape spellings were not checked: " \
                 "attribute_definitions.json declares no shape vocabulary " \
                 "(properties.shape.enum). Spellings are emitted as written.\e[0m"
        end

        def self.from_enum(glass)
            values = glass&.dig('properties', 'shape', 'enum')
            return nil unless values.is_a?(Array) && !values.empty?

            values.map { |v| v.to_s.downcase }
        end

        def self.find_glass_definition(node)
            case node
            when Hash
            return node['glass'] if node.key?('glass')

            node.each_value do |child|
                found = find_glass_definition(child)
                return found if found
            end
            nil
            when Array
            node.each do |child|
                found = find_glass_definition(child)
                return found if found
            end
            nil
            end
        end

        def self.load_attribute_definitions
            path = File.expand_path('../../core/attribute_definitions.json', __dir__)
            return {} unless File.exist?(path)

            JSON.parse(File.read(path))
        rescue JSON::ParserError
            {}
        end

        # Swift string literal, escaped (the shared escaper): a style or
        # shape spelling arrives from JSON and goes into generated source.
        def swift_string_literal(value)
          JsonUIShared::StringLiterals.swift(value)
        end

        def border_color_expr(value)
          return get_swiftui_color(value) unless bound_value?(value)

          expr = SjuiTools::SwiftUI::Binding::BindingExpression.swift_value_expr(value[2..-2])
          "SwiftJsonUIConfiguration.shared.getColor(for: #{expr}) ?? Color.black"
        end

        def build_border_overlay(color, corner_radius, border_width, style = nil)
          indent_str = "    " * (@indent_level + 1)
          sub_indent = "    " * (@indent_level + 2)
          [
            ".overlay(",
            "#{indent_str}RoundedRectangle(cornerRadius: #{corner_radius})",
            "#{sub_indent}.stroke(#{color}, #{stroke_style_argument(border_width, style)})",
            "#{indent_str[0...-4]})"
          ].join("\n")
        end

        # `lineWidth:` for a solid border, a full `style: StrokeStyle(...)`
        # for the dashed and dotted spellings.
        #
        # `common.borderStyle` (solid / dashed / dotted) is honoured by the
        # web mapper and by Compose's dashedBorder/dottedBorder, and by
        # nothing on ios — `view_binding_handler.rb` even carries a note
        # saying dashed and dotted "require StrokeStyle", which SwiftUI has.
        # The dash patterns are Compose's, so a layout that declares one
        # border gets one border: [6, 3] for dashed and [width, width * 2]
        # for dotted (DashedBorderModifier.kt).
        #
        # `TextField.borderStyle` is a DIFFERENT attribute with a different
        # vocabulary (none / line / bezel / roundedRect) and its own handler;
        # the two must not be merged, and are not — the TextField converter
        # never reaches this overlay.
        def stroke_style_argument(border_width, style)
          case style.to_s.downcase
          when 'dashed'
            "style: StrokeStyle(lineWidth: #{border_width}, dash: [6, 3])"
          when 'dotted'
            "style: StrokeStyle(lineWidth: #{border_width}, lineCap: .round, " \
              "dash: [#{border_width}, #{border_width} * 2])"
          else
            "lineWidth: #{border_width}"
          end
        end

        # Build shadow modifier code
        def build_shadow_modifier(shadow)
          if shadow.is_a?(Hash)
            radius = shadow['radius'] || 5
            x = shadow['offsetX'] || 0
            y = shadow['offsetY'] || 0
            color_hex = shadow['color']
            opacity = shadow['opacity']

            if color_hex
              color = get_swiftui_color(color_hex)
              if opacity
                ".shadow(color: (#{color}).opacity(#{opacity}), radius: #{radius}, x: #{x}, y: #{y})"
              else
                ".shadow(color: #{color}, radius: #{radius}, x: #{x}, y: #{y})"
              end
            else
              ".shadow(radius: #{radius}, x: #{x}, y: #{y})"
            end
          else
            # The string form is the UIKit pipe contract
            # 'color|offsetX|offsetY|opacity|radius' — exactly five fields;
            # anything else draws nothing (SJUIViewCreator's count == 5
            # guard, the canonical semantics all render paths share).
            parts = shadow.to_s.split('|', -1)
            return nil unless parts.length == 5
            color = get_swiftui_color(parts[0])
            ".shadow(color: (#{color}).opacity(#{parts[3].to_f}), radius: #{parts[4].to_f}, x: #{parts[1].to_f}, y: #{parts[2].to_f})"
          end
        end

        # Build onClick lines as array of code strings
        def build_on_click_lines(handler)
          handler_call = get_event_handler_call(handler)
          indent_str = "    " * (@indent_level + 1)
          [
            ".contentShape(Rectangle())",
            tap_gesture_line(handler_call)
          ] + tap_accessibility_lines
        end

        # Build lifecycle handler lines
        def build_lifecycle_handler_lines(modifier_name, handler)
          indent_str = "    " * (@indent_level + 1)
          if handler.include?(':')
            method_name = handler.gsub(':', '')
            body = "data.#{method_name}?(self)"
          else
            body = "data.#{handler}?()"
          end
          ["#{modifier_name} {\n#{indent_str}#{body}\n#{indent_str[0...-4]}}"]
        end

        # `safeAreaInsetPositions` — the edges that RESERVE the safe area.
        #
        # This emitted `.ignoresSafeArea(.all, edges: …)`, which is the exact
        # opposite: it lets the view draw THROUGH the safe area on those
        # edges. The declaration means the other thing everywhere else —
        #
        #   SSoT   "Which edges reserve the safe area"
        #   rjui   `padding<Side>: env(safe-area-inset-*)`  (view_converter)
        #   kjui   windowInsetsPadding via SafeAreaConfig   (compose_builder)
        #   UIKit  `SJUIView#applySafeAreaInsets` ADDS the inset to the
        #          constraint — this library's own original implementation,
        #          on this same platform
        #
        # so the SwiftUI codegen was the single outlier, and it contradicted
        # the UIKit runtime shipped beside it. `.safeAreaPadding(_:)` is the
        # SwiftUI spelling of "reserve" and lines up one-for-one with rjui's
        # `env(safe-area-inset-*)` padding. It is iOS 17+, which is the
        # package's floor already.
        #
        # (The SSoT description cites `apply_safe_area_insets_to_bag` running
        # for every component as evidence that every platform honours the
        # attribute on a plain view. The routing claim was right; what the
        # method did was not.)
        def apply_safe_area_insets_to_bag
          positions = @component['safeAreaInsetPositions']
          return unless positions

          edges = safe_area_edge_set(positions)
          return if edges.nil?

          @modifier_bag.append(:safe_area_insets, ".safeAreaPadding(#{edges})")
        end

        #: Declared spelling -> `SwiftUI.Edge.Set` member. `left` / `right` /
        #: `horizontal` are not in the declared enum but were accepted here
        #: before, so they keep working rather than starting to warn.
        SAFE_AREA_EDGES = {
          'top' => '.top',
          'bottom' => '.bottom',
          'leading' => '.leading',
          'left' => '.leading',
          'trailing' => '.trailing',
          'right' => '.trailing',
          'vertical' => '.vertical',
          'horizontal' => '.horizontal'
        }.freeze

        # The `Edge.Set` argument for a declared position list, or nil when
        # the declaration selects no edge. `Edge.Set` is an OptionSet, so an
        # array literal is a legal set literal.
        def safe_area_edge_set(positions)
          list = positions.is_a?(Array) ? positions : [positions]
          list = list.map(&:to_s)
          return '.all' if list.include?('all')
          return nil if list.include?('none') && list.length == 1

          members = list.map { |edge| SAFE_AREA_EDGES[edge] }.compact.uniq
          return nil if members.empty?

          "[#{members.join(', ')}]"
        end

        # Legacy method kept for backward compatibility
        def apply_safe_area_insets
          apply_safe_area_insets_to_bag
        end
      end
    end
  end
end
