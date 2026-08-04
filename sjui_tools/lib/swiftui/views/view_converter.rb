#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative 'stack_alignment_helper'
require_relative 'relative_positioning_helper'
require_relative 'child_rendering_helper'
require_relative 'modifier_helper'
require_relative 'positioning_helper'
require_relative 'alignment_wrapper_helper'
require_relative 'visibility_helper'
require_relative 'responsive_helper'
require_relative '../../core/responsive_resolver'

module SjuiTools
  module SwiftUI
    module Views
      class ViewConverter < BaseViewConverter
        include StackAlignmentHelper
        include RelativePositioningHelper
        include ChildRenderingHelper
        include ModifierHelper
        include PositioningHelper
        include AlignmentWrapperHelper
        include VisibilityHelper
        include ResponsiveHelper

        # Stores child code/weight for each WeightedStack child (used for body splitting)
        attr_reader :weighted_children_info

        def initialize(component, indent_level = 0, action_manager = nil, converter_factory = nil, view_registry = nil, binding_registry = nil)
          super(component, indent_level, action_manager, binding_registry)
          @converter_factory = converter_factory
          @view_registry = view_registry || SjuiTools::SwiftUI::ViewRegistry.new
          @weighted_children_info = nil
        end

        def should_add_leading_spacer_for_hstack(gravity)
          # HStack with right/trailing gravity needs leading spacer
          # Extract horizontal component from gravity
          horizontal = extract_horizontal_from_gravity(gravity)
          horizontal == 'right'
        end

        def should_add_trailing_spacer_for_hstack(gravity)
          # HStack with left/leading gravity needs trailing spacer
          horizontal = extract_horizontal_from_gravity(gravity)
          horizontal == 'left'
        end

        def should_add_leading_spacer_for_vstack(gravity)
          # VStack with bottom gravity needs leading spacer
          vertical = extract_vertical_from_gravity(gravity)
          vertical == 'bottom'
        end

        def should_add_trailing_spacer_for_vstack(gravity)
          # VStack with top gravity needs trailing spacer
          vertical = extract_vertical_from_gravity(gravity)
          vertical == 'top'
        end

        def extract_horizontal_from_gravity(gravity)
          gravity = gravity || 'left|top'
          if gravity.is_a?(Array)
            # centerHorizontalはcenterとして扱う
            result = gravity.find { |g| ['left', 'center', 'right', 'centerHorizontal'].include?(g) } || 'left'
            result == 'centerHorizontal' ? 'center' : result
          elsif gravity.is_a?(String)
            if gravity.include?('|')
              parts = gravity.split('|')
              result = parts.find { |p| ['left', 'center', 'right', 'centerHorizontal'].include?(p) } || 'left'
              result == 'centerHorizontal' ? 'center' : result
            else
              # centerHorizontalはcenterとして扱う
              return 'center' if gravity == 'centerHorizontal'
              ['left', 'center', 'right'].include?(gravity) ? gravity : 'left'
            end
          else
            'left'
          end
        end

        def extract_vertical_from_gravity(gravity)
          gravity = gravity || 'left|top'
          if gravity.is_a?(Array)
            # centerVerticalはcenterとして扱う
            result = gravity.find { |g| ['top', 'center', 'bottom', 'centerVertical'].include?(g) } || 'top'
            result == 'centerVertical' ? 'center' : result
          elsif gravity.is_a?(String)
            if gravity.include?('|')
              parts = gravity.split('|')
              result = parts.find { |p| ['top', 'center', 'bottom', 'centerVertical'].include?(p) } || 'top'
              result == 'centerVertical' ? 'center' : result
            else
              # centerVerticalはcenterとして扱う
              return 'center' if gravity == 'centerVertical'
              ['top', 'center', 'bottom'].include?(gravity) ? gravity : 'top'
            end
          else
            'top'
          end
        end

        def convert
          # ビューレジストリに自身を登録
          if @component['id'] && @view_registry
            @view_registry.register_view(@component['id'], @component)
          end

          child_data = @component['child'] || []
          # childが単一要素の場合は配列に変換
          children = child_data.is_a?(Array) ? child_data : [child_data]
          # Filter out data declarations - only if it's a data declaration (has 'data' key and no other view properties)
          children = children.reject { |child|
            child.is_a?(Hash) && child['data'] && !child['type'] && !child['include']
          }

          # 子ビューもレジストリに登録
          children.each do |child|
            if child.is_a?(Hash) && child['id'] && @view_registry
              @view_registry.register_view(child['id'], child)
            end
          end

          # Check for responsive container (has children + responsive block)
          if responsive?(@component) && !children.empty? && @converter_factory
            return convert_responsive_container(children)
          end

          # orientationを先に取得
          orientation = @component['orientation']

          # `direction` reverses the children along the orientation axis —
          # UIKit resolves it exactly that way (SJUIView: a vertical stack
          # honours `bottomToTop`, a horizontal one `rightToLeft`, everything
          # else is the natural order), and the Compose converter reverses the
          # child list for the same two values. Nothing here read the
          # attribute, so it was inert on this platform: `jui conformance
          # codegen-effect` measured the same emission for every value.
          case @component['direction']
          when 'bottomToTop'
            children = children.reverse if orientation == 'vertical'
          when 'rightToLeft'
            children = children.reverse if orientation == 'horizontal'
          end

          # 相対配置が必要かチェック
          # orientationが指定されている場合（HStack/VStackになる場合）、
          # centerHorizontal/centerVerticalなどは相対配置ではなく、子要素の配置制御として扱う
          # 相対配置が必要なのはorientationがない場合（ZStackになる場合）のみ
          @needs_relative_positioning = orientation.nil? && has_relative_positioning?(children)
          @has_view_ids = children.any? { |child| child.is_a?(Hash) && child['id'] }

          if children.empty?
            # 子要素がない場合
            # backgroundが設定されている場合はRectangleを使用（dividerなど）
            if @component['background']
              add_line "Rectangle()"
              add_modifier_line ".fill(#{get_swiftui_color(@component['background'])})"
              # Rectangleの場合はbackgroundを適用しない - register background to prevent apply_modifiers from adding it
              @modifier_bag.register(:background, "")
            elsif @component['width'] || @component['height']
              # width/heightが指定されている場合はColor.clearを使用（スペーサーとして機能）
              add_line "Color.clear"
            else
              add_line "EmptyView()"
            end
          else
            # 複数の子要素がある場合
            # orientationが指定されていない場合はZStackを使用

            # 子要素のweightをチェック
            has_weights = children.any? { |child|
              weight_expression(child['weight'] || child['widthWeight'] || child['heightWeight']).first
            }

            # Get spacing value (default 0). A bound spacing lands in the
            # stack's `spacing:` argument, which is a CGFloat — pasting the
            # declaration there emitted `HStack(alignment: .top, spacing:
            # @{gap})` and the build died on the first stack that used it.
            spacing_value = bound_number(@component['spacing']) || @component['spacing'] || 0

            if has_weights && (orientation == 'horizontal' || orientation == 'vertical')
              # weightがある場合はWeightedStack用の子要素を構築
              @weighted_children_info = []  # Track child codes for body splitting
              weighted_children = []
              children.each do |child|
                _applies, weight = weight_expression(child['weight'] || child['widthWeight'] || child['heightWeight'])
                weighted_children << { child: child, weight: weight }
              end

              if orientation == 'horizontal'
                alignment = get_hstack_alignment
                # `hasMatchParentCrossAxis` toggles the inner
                # `.fixedSize(vertical: ...)` in SwiftJsonUI's WeightedHStack.
                # Default false → vertical fixedSize → HStack takes children's
                # natural height. When this View has `height: matchParent`,
                # children may legitimately want the proposed pane height
                # (Embeds with `.frame(maxHeight: .infinity)` overflow), so
                # honor the parent proposal instead. The flag is the *last*
                # named arg in SwiftJsonUI's init (after `children`), so we
                # append it on the closing line, not the opening line.
                @weighted_has_cross_match = @component['height'] == 'matchParent'
                add_line "WeightedHStack(alignment: #{alignment}, spacing: #{spacing_value}, children: ["
              elsif orientation == 'vertical'
                alignment = get_vstack_alignment
                @weighted_has_cross_match = false
                add_line "WeightedVStack(alignment: #{alignment}, spacing: #{spacing_value}, children: ["
              end
            elsif orientation == 'horizontal'
              # HStackでgravityを反映
              alignment = get_hstack_alignment
              add_line "HStack(alignment: #{alignment}, spacing: #{spacing_value}) {"

              # Add Spacer at beginning for right gravity or distribution
              distribution = @component['distribution']
              if should_add_leading_spacer_for_hstack(@component['gravity']) || distribution == 'equalSpacing' || distribution == 'equalCentering'
                indent do
                  add_line "Spacer(minLength: 0)"
                end
              end
            elsif orientation == 'vertical'
              # VStackでgravityを反映
              alignment = get_vstack_alignment
              add_line "VStack(alignment: #{alignment}, spacing: #{spacing_value}) {"

              # Add Spacer at beginning for bottom gravity or distribution
              distribution = @component['distribution']
              if should_add_leading_spacer_for_vstack(@component['gravity']) || distribution == 'equalSpacing' || distribution == 'equalCentering'
                indent do
                  add_line "Spacer(minLength: 0)"
                end
              end
            else
              # orientationがない場合はZStack（重ね合わせ）
              # 相対配置が必要な場合は特別な処理
              if @needs_relative_positioning
                generate_relative_positioning_zstack(children)
                # 相対配置の場合はここで処理完了
              else
                # 通常のZStack
                alignment = get_zstack_alignment
                add_line "ZStack(alignment: #{alignment}) {"
              end
            end

            # 相対配置の場合は子要素の処理をスキップ
            if !@needs_relative_positioning || orientation
              if has_weights && (orientation == 'horizontal' || orientation == 'vertical')
                # WeightedStackの場合は特別な処理
                indent do
                  children.each_with_index do |child, index|
                    weighted, weight = weight_expression(child['weight'] || child['widthWeight'] || child['heightWeight'])

                    # 各子要素を(view: AnyView, weight: CGFloat)のタプルとして追加
                    add_line "("
                    add_line "  view: AnyView("

                    # 子要素を生成
                    # Pass parent orientation to child for proper frame handling
                    child['parent_orientation'] = orientation

                    # weight > 0: set matchParent on main axis so .frame(maxWidth/maxHeight: .infinity)
                    # is applied inside the converter BEFORE .background()
                    if weighted
                      if orientation == 'horizontal'
                        unless child['width'] == 'matchParent' || child['width'] == -1
                          child['width'] = 'matchParent'
                        end
                      else
                        unless child['height'] == 'matchParent' || child['height'] == -1
                          child['height'] = 'matchParent'
                        end
                      end
                    end

                    # Capture full child code including VisibilityWrapper if needed
                    before_count = @generated_code.size

                    has_visibility = child['visibility']
                    # If visibility wrapper is needed, child content goes 1 level deeper
                    child_indent = has_visibility ? @indent_level + 3 : @indent_level + 2

                    child_converter = @converter_factory.create_converter(child, child_indent, @action_manager, @converter_factory, @view_registry)
                    next unless child_converter
                    child_code = child_converter.convert

                    if has_visibility
                      # Wrap with VisibilityWrapper (canonical expression
                      # parsing shared with view_binding_handler#parse_binding)
                      visibility_param = SwiftUI::Binding::BindingExpression.swift_visibility_param(child['visibility'])
                      wrapper_indent = "    " * (@indent_level + 2)
                      @generated_code << "#{wrapper_indent}VisibilityWrapper(#{visibility_param}) {"
                      child_code.split("\n").each { |line| @generated_code << line }
                      @generated_code << "#{wrapper_indent}}"
                    else
                      child_code.split("\n").each { |line| @generated_code << line }
                    end

                    # Capture the full generated code for this child (including VisibilityWrapper)
                    full_child_code = @generated_code[before_count..].join("\n")

                    # weight: 0 の子要素で、サイズ指定がない場合は cross-axis の
                    # .fixedSize() を付与する (wrapContent 契約)。これにより
                    # WeightedHStack/VStack が intrinsic size を正しく計測できる。
                    # inline emit と section 抽出 (view_updater) の両経路で同一の
                    # modifier を使えるよう、ここで文字列を決めて child info に保持する。
                    # info に持たせないと section 抽出時に call-site modifier が消える
                    # (drops-weighted-child-call-site-fixed-size bug)。
                    fixed_size_modifier = nil
                    unless weighted
                      needs_fixed_size = if orientation == 'horizontal'
                        # 横方向: width が wrapContent または未指定の場合
                        child_width = child['width']
                        child_width.nil? || child_width == 'wrapContent'
                      else
                        # 縦方向: height が wrapContent または未指定の場合
                        child_height = child['height']
                        child_height.nil? || child_height == 'wrapContent'
                      end

                      if needs_fixed_size
                        fixed_size_modifier = if orientation == 'horizontal'
                          ".fixedSize(horizontal: true, vertical: false)"
                        else
                          ".fixedSize(horizontal: false, vertical: true)"
                        end
                      end
                    end

                    # Save full child code + fixedSize contract for potential body splitting
                    @weighted_children_info << { code: full_child_code, weight: weight, fixed_size: fixed_size_modifier }

                    # State変数を継承
                    if child_converter.respond_to?(:state_variables) && child_converter.state_variables
                      @state_variables.concat(child_converter.state_variables)
                    end

                    # inline emit: AnyView(...) の内側に fixedSize を追加
                    if fixed_size_modifier
                      add_line "    #{fixed_size_modifier}"
                    end

                    add_line "  ),"
                    add_line "  weight: #{weight}"
                    add_line ")#{index < children.size - 1 ? ',' : ''}"
                  end
                end
                # Close the WeightedStack. `hasMatchParentCrossAxis` is
                # appended here (after `children:`) to match the
                # declaration order in SwiftJsonUI's WeightedHStack init.
                if @weighted_has_cross_match
                  add_line "], hasMatchParentCrossAxis: true)"
                else
                  add_line "])"
                end
              else
                # 通常のStack処理
                distribution = @component['distribution']
                indent do
                  children.each_with_index do |child, index|
                    if @converter_factory
                      render_child_element(child, orientation, index, 0, 0)
                    end

                    # Add Spacer between children for distribution
                    if index < children.size - 1 && (distribution == 'fillEqually' || distribution == 'equalSpacing' || distribution == 'equalCentering')
                      add_line "Spacer(minLength: 0)"
                    end
                  end

                  # Add trailing Spacer based on gravity or distribution
                  # ただし、親からcenterHorizontal/centerVerticalでラップされている場合はSpacerを追加しない
                  # また、wrapContent/具体的なサイズの場合はSpacerを追加しない（matchParentや-1の場合のみ追加）
                  unless @component['_skip_trailing_spacer']
                    width = @component['width']
                    height = @component['height']
                    # Spacerはコンテナが拡大する場合のみ意味がある
                    # wrapContentや具体的なサイズの場合はSpacerを追加しても意味がない
                    width_expands = width == 'matchParent' || width == -1
                    height_expands = height == 'matchParent' || height == -1

                    if orientation == 'horizontal' && width_expands && (should_add_trailing_spacer_for_hstack(@component['gravity']) || distribution == 'equalSpacing' || distribution == 'equalCentering')
                      add_line "Spacer(minLength: 0)"
                    elsif orientation == 'vertical' && height_expands && (should_add_trailing_spacer_for_vstack(@component['gravity']) || distribution == 'equalSpacing' || distribution == 'equalCentering')
                      add_line "Spacer(minLength: 0)"
                    end
                  end
                end
              end

              # 閉じ括弧を追加
              # orientationがある場合（HStack/VStack）は常に閉じ括弧が必要
              # orientationがない場合（ZStack）は相対配置でない場合のみ
              if orientation || !@needs_relative_positioning
                if !has_weights || (orientation != 'horizontal' && orientation != 'vertical')
                  # 通常のStackの場合のみ閉じ括弧が必要
                  # WeightedStackは既に閉じている
                  add_line "}"  # 通常のStack/ZStackを閉じる
                end
              end
            end

            # ZStackで相対配置が必要な場合はcoordinateSpaceを設定
            if !orientation && has_relative_positioning?(children) && !@needs_relative_positioning
              add_modifier_line ".coordinateSpace(name: \"ZStackCoordinateSpace\")"
            end
          end

          # 共通のモディファイアを適用
          # 相対配置の場合、paddingはRelativePositionContainer内部で処理されるのでスキップ
          apply_modifiers(skip_padding: @needs_relative_positioning)

          # グラデーション
          if @component['gradient']
            apply_gradient
          end

          # SafeAreaViewの場合
          if @component['type'] == 'SafeAreaView' && @component['safeAreaInsetPositions']
            apply_safe_area_insets_to_bag
          end

          # Apply binding modifiers (borderColor, background, etc. with @{...})
          apply_binding_modifiers

          generated_code
        end

        private

        # Handle responsive container: generate a wrapper function call + children inline
        def convert_responsive_container(children)
          func_name = @converter_factory.next_responsive_name

          # Generate the responsive wrapper function and register it
          func_code = ResponsiveHelper.generate_container_function(
            func_name, @component, self
          )
          @converter_factory.register_responsive_function(func_code)

          # Generate the function call with children as content closure
          add_line "#{func_name} {"

          orientation = @component['orientation']
          indent do
            children.each_with_index do |child, index|
              if @converter_factory
                render_child_element(child, orientation, index, 0, 0)
              end
            end
          end

          add_line "}"

          # All container modifiers (padding / margin / frame / background /
          # cornerRadius / border / alpha / shadow / etc.) are emitted INSIDE
          # the wrapper function per branch via
          # ResponsiveHelper.generate_container_function +
          # BaseViewConverter#collect_modifiers_for, so the call site adds
          # only binding-driven modifiers that don't make sense per-branch.
          apply_binding_modifiers

          generated_code
        end
      end
    end
  end
end
