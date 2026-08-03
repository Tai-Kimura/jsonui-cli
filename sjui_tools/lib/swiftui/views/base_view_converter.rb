# frozen_string_literal: true

require_relative 'template_helper'
require_relative '../binding/binding_expression'
require_relative 'alignment_helper'
require_relative 'frame_helper'
require_relative 'color_helper'
require_relative 'spacing_helper'
require_relative 'modifier_helper'
require_relative 'modifier_bag'
require_relative '../binding/binding_handler_registry'
require_relative '../../core/attribute_validator'
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

        # Extract property name from binding expression
        # "@{propertyName}" -> "propertyName"
        # "@{!propertyName}" -> "propertyName" (negation prefix stripped)
        def extract_binding_property(value)
          return nil unless value.is_a?(String)
          if value =~ /^@\{!?(.+)\}$/
            $1
          else
            value
          end
        end

        # Check if a binding expression is negated
        # "@{!propertyName}" -> true
        # "@{propertyName}" -> false
        def is_negated_binding?(value)
          return false unless value.is_a?(String)
          value =~ /^@\{!.+\}$/
        end

        # Build data access expression from binding value
        # "@{propertyName}" -> "data.propertyName"
        # "@{!propertyName}" -> "!data.propertyName"
        def binding_data_expr(value)
          prop = extract_binding_property(value)
          if is_negated_binding?(value)
            "!data.#{prop}"
          else
            "data.#{prop}"
          end
        end

        # Apply binding modifiers into the modifier bag
        def apply_binding_modifiers
          skip = []
          # Skip keys already handled by converter (registered in bag)
          skip << 'background' if @modifier_bag.key?(:background)
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
          end
          @generated_code.join("\n")
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

          type_name = (@component['type'] || '').downcase
          if ACCESSIBILITY_CONTAINER_TYPES.include?(type_name)
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
          add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}\")"
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
          # Both-attributes guard — the canonical ruling lives in
          # shared/core/attribute_semantics.json (border.widthAlone), verified
          # by `jui conformance gate --cross-effect`.
          if @component['borderWidth'] && @component['borderColor']
            border_color_value = @component['borderColor']
            # Skip if borderColor is a binding - handled by view_binding_handler
            unless border_color_value.is_a?(String) && border_color_value.start_with?('@{')
              color = get_swiftui_color(border_color_value)
              border_code = build_border_overlay(color, (@component['cornerRadius'] || 0).to_i, @component['borderWidth'].to_i)
              @modifier_bag.register(:border, border_code)
            end
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

          # visibility属性はVisibilityWrapperで処理するので、ここでは何もしない
          # The actual wrapping happens in the parent view converter

          # 影
          if @component['shadow']
            shadow_code = build_shadow_modifier(@component['shadow'])
            @modifier_bag.register(:shadow, shadow_code) if shadow_code
          end

          # クリップ
          if @component['clipToBounds']
            @modifier_bag.register(:clip_to_bounds, ".clipped()")
          end

          # オフセット（offsetX, offsetY）
          if @component['offsetX'] || @component['offsetY']
            offset_x = @component['offsetX'] || 0
            offset_y = @component['offsetY'] || 0
            @modifier_bag.register(:offset, ".offset(x: #{offset_x}, y: #{offset_y})")
          end

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

          # disabled状態の処理
          #
          # The binding form used to fall through: `enabled` is declared
          # boolean|binding, and `== false` only matches the literal. A layout
          # that wrote `enabled: "@{isEnabled}"` got nothing at all, on a
          # declared attribute that raises no build warning — which is worse than
          # an unknown one. SwiftUI's `.disabled` also covers interactive
          # descendants, so it is the right modifier for a container.
          if @component['enabled'] == false
            @modifier_bag.register(:disabled, ".disabled(true)")
          elsif is_binding?(@component['enabled'])
            expr = SwiftUI::Binding::BindingExpression.swift_bool_expr(
              @component['enabled'][2..-2]
            )
            @modifier_bag.register(:disabled, ".disabled(!(#{expr}))")
          end

          # tagプロパティの適用（TabViewなどで使用）
          if @component['tag']
            @modifier_bag.register(:tag, ".tag(#{@component['tag']})")
          end

          # classNameプロパティ（SwiftUIではスタイル識別子として記録）
          if @component['className']
            add_line "// className: #{@component['className']}"
          end

          # touchDisabledState（タッチ無効化状態）
          if @component['touchDisabledState']
            @modifier_bag.register(:allows_hit_testing, ".allowsHitTesting(false)")
            add_line "// touchDisabledState applied"
          end

          # userInteractionEnabled（タッチ有効/無効）
          #
          # `canTap` joins it here: the binding forms of both already resolve to
          # `.allowsHitTesting(...)` through ViewBindingHandler, but the literal
          # `canTap: false` matched nothing and did nothing. Same modifier, so
          # the two forms of the same attribute agree.
          if @component['userInteractionEnabled'] == false || @component['canTap'] == false
            @modifier_bag.register(:allows_hit_testing, ".allowsHitTesting(false)")
          end

          # tintColor（アクセントカラー）
          if @component['tintColor']
            tint_color = @component['tintColor']
            if is_binding?(tint_color)
              @modifier_bag.register(:tint_color, ".tint(#{binding_data_expr(tint_color)})")
            else
              color = get_swiftui_color(tint_color)
              @modifier_bag.register(:tint_color, ".tint(#{color})")
            end
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
          # ただし、Buttonの場合は既にactionで処理しているのでスキップ
          unless @component['type'] == 'Button'
            # enabled=falseの場合はクリックイベントを追加しない
            unless @component['enabled'] == false
              if @component['onClick']
                on_click_lines = build_on_click_lines(@component['onClick'])
                @modifier_bag.register(:on_click, on_click_lines)
              elsif @component['onclick']
                @modifier_bag.register(:on_click, build_selector_click_lines(@component['onclick']))
              end
            end
          end

          apply_long_press_to_bag
          apply_pan_to_bag
          apply_pinch_to_bag
          apply_highlighted_to_bag

          # Lifecycle events (SwiftUI only)
          apply_lifecycle_events_to_bag

          # confirmationDialog (iOS 15+)
          apply_confirmation_dialog_to_bag
        end

        # `onclick` values are method names, not bindings: a bare string, or an
        # array of them to call in order.
        def build_selector_click_lines(value)
          names = value.is_a?(Array) ? value : [value]
          calls = names.map { |n| "    data.#{to_camel_case(n.to_s)}?()" }
          [".onTapGesture {"] + calls + ["}"]
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
          @modifier_bag.append(
            :component_specific,
            ".background(#{condition} ? #{get_swiftui_color(highlight_bg)} : Color.clear)"
          )
        end

        # Apply confirmationDialog modifier (iOS 15+) into the bag
        def apply_confirmation_dialog_to_bag
          dialog = @component['confirmationDialog']
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

          # Get titleVisibility (automatic, visible, hidden)
          title_visibility = dialog['titleVisibility'] || 'automatic'
          title_visibility_expr = case title_visibility
          when 'visible'
            '.visible'
          when 'hidden'
            '.hidden'
          else
            '.automatic'
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
          lines << ".confirmationDialog("
          lines << "    #{title_expr},"
          lines << "    isPresented: $data.#{is_presented_var},"
          lines << "    titleVisibility: #{title_visibility_expr}"
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

          @modifier_bag.register(:confirmation_dialog, lines)
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
          when /^\.clipped\(/
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
        def build_border_overlay(color, corner_radius, border_width)
          indent_str = "    " * (@indent_level + 1)
          sub_indent = "    " * (@indent_level + 2)
          [
            ".overlay(",
            "#{indent_str}RoundedRectangle(cornerRadius: #{corner_radius})",
            "#{sub_indent}.stroke(#{color}, lineWidth: #{border_width})",
            "#{indent_str[0...-4]})"
          ].join("\n")
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
            ".onTapGesture {\n#{indent_str}#{handler_call}\n#{indent_str[0...-4]}}"
          ]
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

        # Apply safe area insets into the bag
        def apply_safe_area_insets_to_bag
          positions = @component['safeAreaInsetPositions']
          return unless positions

          if positions.is_a?(Array)
            edges = []
            edges << '.top' if positions.include?('top')
            edges << '.bottom' if positions.include?('bottom')
            edges << '.leading' if positions.include?('leading') || positions.include?('left')
            edges << '.trailing' if positions.include?('trailing') || positions.include?('right')

            if edges.any?
              @modifier_bag.append(:safe_area_insets, ".ignoresSafeArea(.all, edges: [#{edges.join(', ')}])")
            end
          elsif positions == 'all'
            @modifier_bag.append(:safe_area_insets, ".ignoresSafeArea()")
          elsif positions == 'none'
            # デフォルトでセーフエリアを尊重
          else
            add_line "// safeAreaInsetPositions: #{positions}"
          end
        end

        # Legacy method kept for backward compatibility
        def apply_safe_area_insets
          apply_safe_area_insets_to_bag
        end
      end
    end
  end
end
