#!/usr/bin/env ruby

require_relative 'responsive_helper'

module SjuiTools
  module SwiftUI
    module Views
      # Helper module for relative positioning logic
      module RelativePositioningHelper
        # The keys that make the parent a RelativePositionContainer: the declared relative ones (attribute_definitions).
        # toLeftOf, toRightOf, toStartOf, toEndOf and alignBaseline were here too, but no definition declares them —
        # the validator calls each an unknown attribute, Compose and web read none of them, and no constraint was ever
        # written for them — so a key outside the language turned the parent into a RelativePositionContainer and drew
        # nothing (ticket sjui-relative-toleftof-toendof-alignbaseline-not-drawn; the orchestrator's ruling 10-30: a key
        # with no declaration is not in the language, and does not change the parent).
        RELATIVE_KEYS = %w[
          above below alignTop alignBottom alignLeft alignRight
          alignTopView alignBottomView alignLeftView alignRightView
          alignTopOfView alignBottomOfView alignLeftOfView alignRightOfView
          alignCenterVerticalView alignCenterHorizontalView
          centerHorizontal centerVertical centerInParent
        ].freeze

        # The margins RelativePositionContainer draws as the child's inset.
        RELATIVE_MARGIN_KEYS = %w[
          margins topMargin bottomMargin leftMargin rightMargin startMargin endMargin
          marginTop marginBottom marginLeft marginRight marginStart marginEnd
          minStartMargin maxStartMargin minEndMargin maxEndMargin
        ].freeze

        # 相対配置のプロパティをチェック — in the base, or in a size class: one written only under `responsive` made
        # the parent a plain ZStack and was drawn nowhere (ticket sjui-responsive-align-center-overrides-are-not-drawn).
        def has_relative_constraint?(child)
          return false unless child.is_a?(Hash)

          RELATIVE_KEYS.any? { |k| child[k] } || ResponsiveHelper.overrides_any?(child, RELATIVE_KEYS)
        end
        
        def has_relative_positioning?(children)
          return false unless children.is_a?(Array)
          
          children.any? do |child|
            next false unless child.is_a?(Hash)
            has_relative_constraint?(child)
          end
        end
        
        def calculate_relative_positions(children)
          # 相対配置の計算を行う
          positions = {}
          children.each_with_index do |child, index|
            next unless child.is_a?(Hash)
            
            # 各子要素のIDまたはインデックスをキーとして使用
            child_id = child['id'] || "child_#{index}"
            
            # 相対配置の制約を解析
            constraints = []
            
            # 水平方向の制約
            if child['toLeftOf']
              constraints << { type: :toLeftOf, target: child['toLeftOf'] }
            elsif child['toRightOf']
              constraints << { type: :toRightOf, target: child['toRightOf'] }
            elsif child['toStartOf']
              constraints << { type: :toStartOf, target: child['toStartOf'] }
            elsif child['toEndOf']
              constraints << { type: :toEndOf, target: child['toEndOf'] }
            end
            
            # 垂直方向の制約
            if child['above']
              constraints << { type: :above, target: child['above'] }
            elsif child['below']
              constraints << { type: :below, target: child['below'] }
            end
            
            # アライメント制約
            if child['alignLeft']
              if child['alignLeft'].is_a?(String)
                constraints << { type: :alignLeft, target: child['alignLeft'] }
              else
                constraints << { type: :alignLeft, target: :parent }
              end
            end
            
            if child['alignRight']
              if child['alignRight'].is_a?(String)
                constraints << { type: :alignRight, target: child['alignRight'] }
              else
                constraints << { type: :alignRight, target: :parent }
              end
            end
            
            if child['alignTop']
              if child['alignTop'].is_a?(String)
                constraints << { type: :alignTop, target: child['alignTop'] }
              else
                constraints << { type: :alignTop, target: :parent }
              end
            end
            
            if child['alignBottom']
              if child['alignBottom'].is_a?(String)
                constraints << { type: :alignBottom, target: child['alignBottom'] }
              else
                constraints << { type: :alignBottom, target: :parent }
              end
            end
            
            if child['centerHorizontal']
              if child['centerHorizontal'].is_a?(String)
                constraints << { type: :centerHorizontal, target: child['centerHorizontal'] }
              else
                constraints << { type: :centerHorizontal, target: :parent }
              end
            end
            
            if child['centerVertical']
              if child['centerVertical'].is_a?(String)
                constraints << { type: :centerVertical, target: child['centerVertical'] }
              else
                constraints << { type: :centerVertical, target: :parent }
              end
            end
            
            if child['centerInParent']
              constraints << { type: :centerInParent, target: :parent }
            end
            
            positions[child_id] = {
              constraints: constraints,
              margins: {
                top: child['topMargin'] || child['marginTop'] || 0,
                bottom: child['bottomMargin'] || child['marginBottom'] || 0,
                # Bounded margins collapse to their lower bound: a relative
                # position is a fixed inset, with no slack to flex into.
                left: child['leftMargin'] || child['marginLeft'] || child['startMargin'] || child['marginStart'] || child['minStartMargin'] || 0,
                right: child['rightMargin'] || child['marginRight'] || child['endMargin'] || child['marginEnd'] || child['minEndMargin'] || 0
              }
            }
          end
          
          positions
        end
        
        def generate_relative_positioning_zstack(children)
          # RelativePositionContainerを使用した実装
          # alignmentはデフォルトで.topLeadingを使用
          # 各ビューの位置は個々の制約で決定される
          # RelativePositionContainerのalignmentは、制約がないビューのデフォルト位置にのみ影響
          alignment = '.topLeading'
          
          # 親のpaddingを取得
          parent_padding_top = 0
          parent_padding_right = 0
          parent_padding_bottom = 0
          parent_padding_left = 0
          
          # paddingsプロパティの処理（UIKitに合わせてpaddingsに統一）
          if @component['paddings']
            padding = @component['paddings']
            if padding.is_a?(Array)
              case padding.length
              when 1
                parent_padding_top = parent_padding_right = parent_padding_bottom = parent_padding_left = padding[0].to_i
              when 2
                # 縦横のパディング
                parent_padding_top = parent_padding_bottom = padding[0].to_i
                parent_padding_left = parent_padding_right = padding[1].to_i
              when 4
                # 上、右、下、左の順
                parent_padding_top = padding[0].to_i
                parent_padding_right = padding[1].to_i
                parent_padding_bottom = padding[2].to_i
                parent_padding_left = padding[3].to_i
              end
            else
              parent_padding_top = parent_padding_right = parent_padding_bottom = parent_padding_left = padding.to_i
            end
          else
            # 個別のパディング設定（UIKitに合わせてpaddingTop形式に統一）
            parent_padding_top = (@component['paddingTop'] || 0).to_i
            parent_padding_right = (@component['paddingRight'] || 0).to_i
            parent_padding_bottom = (@component['paddingBottom'] || 0).to_i
            parent_padding_left = (@component['paddingLeft'] || 0).to_i
          end
          
          add_line "RelativePositionContainer("
          indent do
            add_line "children: ["
            indent do
              children.each_with_index do |child, index|
                if @converter_factory
                  # 子ビューの設定を生成
                  add_line "RelativeChildConfig("
                  indent do
                    # ID
                    child_id = child['id'] || "view_#{index}"
                    add_line "id: \"#{child_id}\","
                    
                    # View (with optional VisibilityWrapper)
                    visibility_value = child['visibility']
                    has_visibility = visibility_value.is_a?(String) && visibility_value.start_with?('@{') && visibility_value.end_with?('}')
                    # Canonical expression parsing shared with parse_binding
                    vis_param = has_visibility ? SwiftUI::Binding::BindingExpression.swift_visibility_param(visibility_value) : nil
                    if ResponsiveHelper.overrides_any?(child, %w[visibility])
                      # a size class overrides it: the wrapper takes it per size class, as outside this container
                      has_visibility = true
                      vis_param = ResponsiveHelper.visibility_param(child)
                    end

                    add_line "view: AnyView("
                    if has_visibility
                      indent do
                        add_line "VisibilityWrapper(#{vis_param}) {"
                      end
                    end
                    indent do
                      # Special handling for views with padding in relative positioning
                      # We need to ensure padding doesn't affect the view's alignment edges
                      if (child['padding'] || child['paddings']) && child['background']
                        # Extract padding value and remove it from the child temporarily
                        padding_value = child['padding'] || child['paddings']
                        background_color = child['background']
                        child_without_padding = without_margins(child)
                        child_without_padding.delete('padding')
                        child_without_padding.delete('paddings')
                        child_without_padding.delete('background')
                        # Margins are handled separately by RelativePositionContainer; bounded ones collapse to
                        # their floor there — see relative_margin_edges.

                        # Generate the view without padding and background
                        # Use current indent_level + 1 for proper nesting inside view: AnyView(...)
                        child_converter = @converter_factory.create_converter(child_without_padding, @indent_level + 1, @action_manager, @converter_factory, @view_registry)
                        child_code = child_converter.convert
                        adopt_state_variables(child_converter)
                        child_lines = child_code.split("\n")
                        child_lines.each do |line|
                          # Add child code directly to preserve its indentation
                          @generated_code << line unless line.strip.empty?
                        end
                        
                        # Now apply padding and background together
                        if padding_value.is_a?(Array)
                          case padding_value.length
                          when 1
                            add_modifier_line ".padding(#{padding_value[0]})"
                          when 2
                            # [Vertical, Horizontal]
                            add_modifier_line ".padding(.vertical, #{padding_value[0]})"
                            add_modifier_line ".padding(.horizontal, #{padding_value[1]})"
                          when 4
                            # [Top, Right, Bottom, Left]
                            add_modifier_line ".padding(.top, #{padding_value[0]})"
                            add_modifier_line ".padding(.trailing, #{padding_value[1]})"
                            add_modifier_line ".padding(.bottom, #{padding_value[2]})"
                            add_modifier_line ".padding(.leading, #{padding_value[3]})"
                          else
                            add_modifier_line ".padding(0)"
                          end
                        else
                          add_modifier_line ".padding(#{padding_value.to_i})"
                        end
                        color = get_swiftui_color(background_color)
                        add_modifier_line ".background(#{color})"
                      else
                        # Normal conversion for views without padding or without background
                        # Remove margin properties before conversion (they're handled separately by RelativePositionContainer)
                        child_without_margins = without_margins(child)

                        # Use current indent_level + 1 for proper nesting inside view: AnyView(...)
                        child_converter = @converter_factory.create_converter(child_without_margins, @indent_level + 1, @action_manager, @converter_factory, @view_registry)
                        child_code = child_converter.convert
                        adopt_state_variables(child_converter)
                        child_lines = child_code.split("\n")
                        child_lines.each do |line|
                          # Add child code directly to preserve its indentation
                          @generated_code << line unless line.strip.empty?
                        end
                      end
                    end
                    if has_visibility
                      indent do
                        add_line "}"
                      end
                    end
                    add_line "),"

                    # Constraints, margins and size modes. The parent draws these from the child's attributes,
                    # outside the child's own function (responsive0), so a size class that overrides one is drawn
                    # here, per size class — as the ZStack's offset is (ticket
                    # sjui-responsive-align-center-overrides-are-not-drawn: alignTop … centerInParent written only
                    # under `responsive` drew nothing, and a margin override was added to the base one).
                    emit_relative_constraints(child)
                    add_line "margins: #{relative_margins(child)},"
                    add_line "widthMode: #{relative_size_mode(child, 'width')},"
                    add_line "heightMode: #{relative_size_mode(child, 'height')}"
                  end
                  add_line index < children.length - 1 ? ")," : ")"
                end
              end
            end
            add_line "],"
            add_line "alignment: #{alignment},"
            
            # 背景色
            if @component['background']
              bg_color = get_swiftui_color(@component['background'])
              add_line "backgroundColor: #{bg_color},"
            else
              add_line "backgroundColor: nil,"
            end
            
            # 親のpadding
            add_line "parentPadding: EdgeInsets(top: #{parent_padding_top}, leading: #{parent_padding_left}, bottom: #{parent_padding_bottom}, trailing: #{parent_padding_right}),"

            # コンテナ自身のサイズ意図。これを渡さないと matchParent の親が
            # コンテンツサイズに縮み、alignTop / centerVertical などの
            # 親相対制約が「子と同じ大きさの箱」の中で解決されて全て無効化される
            # (SwiftJsonUI >= 10.13.0 の RelativePositionContainer 引数)
            add_line "containerWidthMode: #{get_size_mode(@component['width'])},"
            add_line "containerHeightMode: #{get_size_mode(@component['height'])}"
          end
          add_line ")"
        end

        # One parent-relative constraint (`alignTop`, `centerVertical`,
        # `centerInParent`, …).
        #
        # These are declared `["boolean", "binding"]`. A String is not a legal
        # spelling and never was — but the emitter branched on `is_a?(String)`
        # to mean "align to the view with this id", so a `@{...}` was read as
        # a TARGET ID and the constraint pointed at a view called
        # "@{juiProbeValue}". That is where six of plan 49's ios leaks came
        # from, and it is the "settle the binding before you evaluate it"
        # shape: the binding has to be recognised BEFORE the type test.
        #
        # A bound flag cannot be resolved at generation time, so the element
        # becomes conditional and the array is compacted (see the caller).
        # *target_type* is nil for a constraint with no view-relative form.
        # The child's own declarations (@State, @FocusState: a field's focus, a pager's page heights …) go up to the
        # struct, as every other parent passes them. This container dropped them: a child it placed lost every
        # declaration while its body still used them, and the build failed (cannot find 'nameFieldIsFocused'). Few
        # parents were relative until 2.3.29 made a responsive align or centre one (ticket
        # sjui-relative-container-drops-state-and-focusstate-declarations).
        def adopt_state_variables(child_converter)
          return unless child_converter.respond_to?(:state_variables) && child_converter.state_variables

          @state_variables.concat(child_converter.state_variables)
        end

        def parent_constraint_item(value, target_type, parent_type)
          if (condition = bound_bool(value))
            return ["RelativePositionConstraint(type: .#{parent_type}, targetId: \"\")", condition]
          end

          if target_type && value.is_a?(String)
            ["RelativePositionConstraint(type: .#{target_type}, targetId: \"#{value}\")", nil]
          else
            ["RelativePositionConstraint(type: .#{parent_type}, targetId: \"\")", nil]
          end
        end

        # The constraints *attrs* declare, each as [the constraint, the Swift condition it holds under, or nil].
        def relative_constraint_items(attrs)
          items = []
          view = ->(type, target) { items << ["RelativePositionConstraint(type: .#{type}, targetId: \"#{target}\")", nil] }
          if attrs['above']
            view.(:above, attrs['above'])
          elsif attrs['below']
            view.(:below, attrs['below'])
          end
          # alignTopView … alignRightView: align edges to another view
          view.(:alignTop, attrs['alignTopView']) if attrs['alignTopView']
          view.(:alignBottom, attrs['alignBottomView']) if attrs['alignBottomView']
          view.(:alignLeft, attrs['alignLeftView']) if attrs['alignLeftView']
          view.(:alignRight, attrs['alignRightView']) if attrs['alignRightView']
          # alignTopOfView … alignRightOfView: position relative to another view's edge
          view.(:above, attrs['alignTopOfView']) if attrs['alignTopOfView']
          view.(:below, attrs['alignBottomOfView']) if attrs['alignBottomOfView']
          view.(:leftOf, attrs['alignLeftOfView']) if attrs['alignLeftOfView']
          view.(:rightOf, attrs['alignRightOfView']) if attrs['alignRightOfView']
          # アライメント制約（水平方向を先に）
          items << parent_constraint_item(attrs['alignLeft'], 'left', 'parentLeft') if attrs['alignLeft']
          items << parent_constraint_item(attrs['alignRight'], 'right', 'parentRight') if attrs['alignRight']
          items << parent_constraint_item(attrs['alignTop'], 'top', 'parentTop') if attrs['alignTop']
          items << parent_constraint_item(attrs['alignBottom'], 'bottom', 'parentBottom') if attrs['alignBottom']
          items << parent_constraint_item(attrs['centerHorizontal'], 'centerHorizontal', 'parentCenterHorizontal') if attrs['centerHorizontal']
          items << parent_constraint_item(attrs['centerVertical'], 'centerVertical', 'parentCenterVertical') if attrs['centerVertical']
          view.(:centerVertical, attrs['alignCenterVerticalView']) if attrs['alignCenterVerticalView']
          view.(:centerHorizontal, attrs['alignCenterHorizontalView']) if attrs['alignCenterHorizontalView']
          items << parent_constraint_item(attrs['centerInParent'], nil, 'parentCenter') if attrs['centerInParent']
          # Default to parentTop + parentLeft when no constraints specified
          # so that margins are properly applied
          if items.empty?
            view.(:parentTop, '')
            view.(:parentLeft, '')
          end
          items
        end

        # `constraints: [...]`. With a size class overriding any of them, each constraint holds under the size classes
        # whose merged attributes declare it (ResponsiveHelper.per_size_class), the base's order first.
        #
        # A bound flag cannot be resolved at generation time either, so a conditional element is `cond ? c : nil`
        # and the array is compacted; the cast is what lets the mixed literal type-check.
        def emit_relative_constraints(child)
          items = relative_constraint_items(child)
          if ResponsiveHelper.overrides_any?(child, RELATIVE_KEYS)
            branches = JsonUIShared::ResponsiveResolver.build_branches(child).reverse
            exprs = branches.flat_map { |b| relative_constraint_items(b[:attrs]).map(&:first) }.uniq
            items = exprs.filter_map do |expr|
              holds = ResponsiveHelper.per_size_class(child) do |attrs|
                found = relative_constraint_items(attrs).find { |e, _| e == expr }
                found ? (found[1] || 'true') : 'false'
              end
              [expr, holds == 'true' ? nil : holds] unless holds == 'false'
            end
          end
          bound = items.any? { |_, condition| condition }
          add_line bound ? 'constraints: ([' : 'constraints: ['
          indent do
            items.each_with_index do |(expr, condition), i|
              line = condition ? "#{condition} ? #{expr} : nil" : expr
              add_line i < items.size - 1 ? "#{line}," : line
            end
          end
          add_line bound ? '] as [RelativePositionConstraint?]).compactMap { $0 },' : '],'
        end

        # [top, leading, bottom, trailing] of *attrs*' margins, and whether they came from `margins`.
        def relative_margin_edges(attrs)
          if attrs['margins']
            m = Array(attrs['margins'])
            edges = case m.length
                    when 1 then [m[0]] * 4
                    when 2 then [m[0], m[1], m[0], m[1]]      # [Vertical, Horizontal]
                    when 4 then m                             # [Top, Left, Bottom, Right]
                    else [0, 0, 0, 0]
                    end
            return [edges.map(&:to_s), [1, 2, 4].include?(m.length)]
          end
          # RelativePositionContainer places children at a fixed inset,
          # so a bounded margin has no slack to flex into: it
          # collapses to its lower bound, which is what the library's
          # min-only case resolves to as well.
          edges = [
            attrs['topMargin'] || attrs['marginTop'] || 0,
            attrs['leftMargin'] || attrs['marginLeft'] || attrs['startMargin'] || attrs['marginStart'] || attrs['minStartMargin'] || 0,
            attrs['bottomMargin'] || attrs['marginBottom'] || 0,
            attrs['rightMargin'] || attrs['marginRight'] || attrs['endMargin'] || attrs['marginEnd'] || attrs['minEndMargin'] || 0
          ]
          [edges.map { |v| convert_margin_binding(v).to_s }, false]
        end

        def relative_margins(child)
          if ResponsiveHelper.overrides_any?(child, RELATIVE_MARGIN_KEYS)
            top, leading, bottom, trailing = (0..3).map do |i|
              ResponsiveHelper.per_size_class(child) { |attrs| relative_margin_edges(attrs)[0][i] }
            end
            return "EdgeInsets(top: #{top}, leading: #{leading}, bottom: #{bottom}, trailing: #{trailing})"
          end
          edges, declared = relative_margin_edges(child)
          # デフォルト値でない場合のみマージンを設定（バインディングも含む）
          return '.init()' unless declared || edges.any? { |v| v != '0' }

          "EdgeInsets(top: #{edges[0]}, leading: #{edges[1]}, bottom: #{edges[2]}, trailing: #{edges[3]})"
        end

        def relative_size_mode(child, key)
          return get_size_mode(child[key]) unless ResponsiveHelper.overrides_any?(child, [key])

          ResponsiveHelper.per_size_class(child) { |attrs| "RelativeSizeMode#{get_size_mode(attrs[key])}" }
        end

        # A child's margins with the keys RelativePositionContainer draws taken out — from the base and from every
        # size class, or an override would be drawn twice (the container's inset and the function's padding).
        def without_margins(child)
          out = child.dup
          RELATIVE_MARGIN_KEYS.each { |k| out.delete(k) }
          if out['responsive'].is_a?(Hash)
            out['responsive'] = out['responsive'].transform_values do |o|
              o.is_a?(Hash) ? o.reject { |k, _| RELATIVE_MARGIN_KEYS.include?(k) } : o
            end
          end
          out
        end

        # バインディング式をSwiftUI形式に変換
        def convert_margin_binding(value)
          return value if value.is_a?(Numeric)
          return value.to_s unless value.is_a?(String)

          if value.start_with?('@{') && value.end_with?('}')
            # @{propertyName [?? default]} -> data.propertyName [?? default]
            SwiftUI::Binding::BindingExpression.swift_value_expr(value[2..-2], kind: :number)
          else
            value
          end
        end

        # サイズモードをSwiftUI形式に変換
        # matchParent: 親のサイズに合わせる
        # wrapContent: コンテンツのサイズに合わせる
        # 数値: 固定サイズ
        def get_size_mode(value)
          case value
          when 'matchParent', 'match_parent'
            '.matchParent'
          when 'wrapContent', 'wrap_content', nil
            '.wrapContent'
          when Numeric
            ".fixed(#{value})"
          else
            if value.is_a?(String) && value.match?(/^\d+(\.\d+)?$/)
              ".fixed(#{value})"
            else
              '.wrapContent'
            end
          end
        end
      end
    end
  end
end