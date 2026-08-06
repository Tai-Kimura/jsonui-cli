require_relative 'margin_expression_helper'

module SjuiTools
  module SwiftUI
    module Views
      module PositioningHelper
        include MarginExpressionHelper

        def apply_zstack_positioning(child, index)
          # 各子要素の位置を調整
          # SwiftJsonUIの各種margin属性を使用してoffsetを計算
          offset_x = 0
          offset_y = 0
          
          # 個別のmargin属性から位置を計算
          left_margin = child['leftMargin'] || 0
          right_margin = child['rightMargin'] || 0
          top_margin = child['topMargin'] || 0
          bottom_margin = child['bottomMargin'] || 0
          
          # 相対配置属性の処理（alignTopOfView, alignBottomOfView, alignLeftOfView, alignRightOfView）
          # または代替形式（alignTopView, alignBottomView, alignLeftView, alignRightView）
          has_relative_positioning = child['alignTopOfView'] || child['alignBottomOfView'] || 
                                    child['alignLeftOfView'] || child['alignRightOfView'] ||
                                    child['alignTopView'] || child['alignBottomView'] ||
                                    child['alignLeftView'] || child['alignRightView']
          
          if has_relative_positioning && @view_registry && child['id']
            # ViewRegistryから相対配置のモディファイアを取得
            modifiers = @view_registry.generate_alignment_modifiers(child['id'])
            modifiers.each do |modifier|
              add_modifier_line modifier
            end
          end
          
          # 通常のoffset計算（相対配置がない場合、または追加の調整として）
          if !has_relative_positioning
            # 通常のoffset計算
            # ZStackでは左上を基準にoffsetを計算
            offset_x = margin_difference(left_margin, right_margin)
            offset_y = margin_difference(top_margin, bottom_margin)
            
            # SwiftJsonUIの位置属性を処理
            # centerInParent
            if child['centerInParent']
              # ZStackのalignmentで処理されるため、追加のoffsetは不要。
              # The comment said so; the code did not do it, and kept emitting
              # the margin difference on both axes — moving the child back off
              # the centre it had just been aligned to. semantics.margins
              # disables the margin on a centred axis, and this centres both
              # (the library agrees: zstackMarginOffset returns .zero here).
              offset_x = 0
              offset_y = 0
            end
            
            # centerVertical / centerHorizontal
            if child['centerVertical'] && !child['centerInParent']
              # 垂直方向のみセンタリング（offsetのy成分をリセット）
              offset_y = 0
            end
            
            if child['centerHorizontal'] && !child['centerInParent']
              # 水平方向のみセンタリング（offsetのx成分をリセット）
              offset_x = 0
            end
            
            # offsetを適用
            if offset_component?(offset_x) || offset_component?(offset_y)
              add_modifier_line ".offset(x: #{offset_x}, y: #{offset_y})"
            end
          end

          # NO positional zIndex stamp. `.zIndex(#{index})` per document
          # position replicated SwiftUI's own default (ZStack draws later
          # children on top; every child's default z is 0 and ties break in
          # document order) — redundant when nothing declares a z, and
          # destructive when something does: the stamp landed OUTSIDE the
          # child's modifier chain, overriding the `.zIndex(±N)` that
          # indexAbove/indexBelow put inside it, so `indexAbove` drew the
          # anchor IN FRONT (ios parity, run 4, common_indexAbove d41).
          # The dynamic face has no positional stamps either
          # (DynamicViewContainer zstackContent) — removing this is what
          # makes the two faces one picture.
        end

        private

        # The difference of two opposing margins — the offset a ZStack
        # child gets from the parent (semantics.margins).
        #
        # Margins are declared `["number", "binding"]`, so `"@{gap}"` is a
        # valid value here, and subtracting it as a Ruby String raised
        # NoMethodError: a layout written exactly as the SSoT allows
        # crashed the generator. A bound margin has no value at generation
        # time, but `.offset` takes an expression, so one is emitted —
        # the tool's own output format is not a reason to reject a
        # declaration it accepts.
        def margin_difference(value, opposite)
          left = margin_number(value)
          right = margin_number(opposite)
          return left - right if left && right

          minuend = margin_operand(value)
          subtrahend = margin_operand(opposite)
          # Same expression on both edges cancels — a symmetric bound
          # margin is a pure inset and belongs entirely to the padding
          # SpacingHelper emits.
          return 0 if minuend == subtrahend
          return minuend if subtrahend == '0'
          return "-(#{subtrahend})" if minuend == '0'

          "#{minuend} - #{subtrahend}"
        end

        # An expression cannot be compared to zero here, so it always
        # emits; a number still only emits when it moves the child.
        def offset_component?(offset)
          offset.is_a?(Numeric) ? offset != 0 : true
        end
      end
    end
  end
end