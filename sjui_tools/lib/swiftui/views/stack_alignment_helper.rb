#!/usr/bin/env ruby

module SjuiTools
  module SwiftUI
    module Views
      # Helper module for determining stack alignments
      module StackAlignmentHelper
        def get_hstack_alignment
          # HStackの垂直方向のアライメント
          # 注意: 子要素のalignTop/Bottom/centerVerticalは個別の子要素の配置に影響するが、
          # HStack自体のalignmentには影響しない（それはgravityで決まる）

          # gravityから垂直成分を取得
          gravity = @component['gravity'] || 'left|top'
          vertical = 'top'  # デフォルト

          if gravity.is_a?(Array)
            # 配列の場合、垂直方向の値を探す
            # centerVerticalはcenterとして扱う
            vertical = gravity.find { |g| ['top', 'center', 'bottom', 'centerVertical'].include?(g) } || 'top'
            vertical = 'center' if vertical == 'centerVertical'
          elsif gravity.is_a?(String)
            if gravity.include?('|')
              parts = gravity.split('|')
              vertical = parts.find { |p| ['top', 'center', 'bottom', 'centerVertical'].include?(p) } || 'top'
              vertical = 'center' if vertical == 'centerVertical'
            else
              # 単一値でも垂直方向の値なら使用（例: "bottom"だけでもOK）
              # centerVerticalはcenterとして扱う
              if gravity == 'centerVertical'
                vertical = 'center'
              elsif ['top', 'center', 'bottom'].include?(gravity)
                vertical = gravity
              end
            end
          end
          
          case vertical
          when 'top'
            '.top'
          when 'center'
            '.center'
          when 'bottom'
            '.bottom'
          else
            '.top'  # デフォルトは上揃え
          end
        end
        
        def get_vstack_alignment
          # VStackの水平方向のアライメント
          # 注意: 子要素のalignLeft/Right/centerHorizontalは個別の子要素の配置に影響するが、
          # VStack自体のalignmentには影響しない（それはgravityで決まる）

          # gravityから水平成分を取得
          gravity = @component['gravity'] || 'left|top'
          horizontal = 'left'  # デフォルト

          if gravity.is_a?(Array)
            # 配列の場合、水平方向の値を探す
            # centerHorizontalはcenterとして扱う
            horizontal = gravity.find { |g| ['left', 'center', 'right', 'centerHorizontal'].include?(g) } || 'left'
            horizontal = 'center' if horizontal == 'centerHorizontal'
          elsif gravity.is_a?(String)
            if gravity.include?('|')
              parts = gravity.split('|')
              horizontal = parts.find { |p| ['left', 'center', 'right', 'centerHorizontal'].include?(p) } || 'left'
              horizontal = 'center' if horizontal == 'centerHorizontal'
            else
              # 単一値でも水平方向の値なら使用（例: "right"だけでもOK）
              # centerHorizontalはcenterとして扱う
              if gravity == 'centerHorizontal'
                horizontal = 'center'
              elsif ['left', 'center', 'right'].include?(gravity)
                horizontal = gravity
              end
            end
          end
          
          case horizontal
          when 'left'
            '.leading'
          when 'center'
            '.center'
          when 'right'
            '.trailing'
          else
            '.leading'  # デフォルトは左揃え
          end
        end
        
        def get_zstack_alignment_for_child(child)
          # 子要素のアライメント属性から判断
          horizontal = nil
          vertical = nil
          
          # 水平方向のアライメント
          if child['alignLeft']
            horizontal = 'leading'
          elsif child['alignRight']
            horizontal = 'trailing'
          elsif child['centerHorizontal'] || child['centerInParent']
            horizontal = 'center'
          end
          
          # 垂直方向のアライメント
          if child['alignTop']
            vertical = 'top'
            # alignTopだけの場合はleadingをデフォルトにする
            horizontal = horizontal || 'leading'
          elsif child['alignBottom']
            vertical = 'bottom'
            # alignBottomだけの場合はleadingをデフォルトにする
            horizontal = horizontal || 'leading'
          elsif child['centerVertical'] || child['centerInParent']
            vertical = 'center'
          end
          
          # alignLeft/Rightだけの場合はtopをデフォルトにする
          if horizontal && !vertical
            vertical = 'top'
          end
          
          # SwiftUIのアライメントに変換
          if horizontal && vertical
            case "#{vertical}_#{horizontal}"
            when 'top_leading'
              '.topLeading'
            when 'top_center'
              '.top'
            when 'top_trailing'
              '.topTrailing'
            when 'center_leading'
              '.leading'
            when 'center_center'
              '.center'
            when 'center_trailing'
              '.trailing'
            when 'bottom_leading'
              '.bottomLeading'
            when 'bottom_center'
              '.bottom'
            when 'bottom_trailing'
              '.bottomTrailing'
            else
              nil
            end
          elsif horizontal
            case horizontal
            when 'leading'
              '.leading'
            when 'trailing'
              '.trailing'
            when 'center'
              '.center'
            else
              nil
            end
          elsif vertical
            case vertical
            when 'top'
              '.top'
            when 'bottom'
              '.bottom'
            when 'center'
              '.center'
            else
              nil
            end
          else
            nil
          end
        end
        
        def get_zstack_alignment
          # ZStackのalignment決定ロジック
          # 明示的にalignment属性が指定されている場合
          if @component['alignment']
            case @component['alignment']
            when 'topLeading'
              '.topLeading'
            when 'top'
              '.top'
            when 'topTrailing'
              '.topTrailing'
            when 'leading', 'left'
              '.leading'
            when 'center'
              '.center'
            when 'trailing', 'right'
              '.trailing'
            when 'bottomLeading'
              '.bottomLeading'
            when 'bottom'
              '.bottom'
            when 'bottomTrailing'
              '.bottomTrailing'
            else
              '.topLeading'
            end
          elsif @component['child'] && @component['child'].is_a?(Array)
            # 子要素のアライメント属性から判断（最初に見つかったもの）
            children_with_align = @component['child'].select do |child|
              next false unless child.is_a?(Hash)
              child['alignTop'] || child['alignBottom'] || child['alignLeft'] || child['alignRight'] ||
              child['centerHorizontal'] || child['centerVertical'] || child['centerInParent']
            end
            
            if children_with_align.any?
              alignment = get_zstack_alignment_for_child(children_with_align.first)
              alignment || zstack_default_alignment
            else
              zstack_default_alignment
            end
          else
            zstack_default_alignment
          end
        end

        # The ZStack IS the container: its alignment is the declared content
        # gravity (kjui emits Box(contentAlignment:) from the same
        # declaration). The literal .topLeading this replaces predates the
        # gravity read, so `gravity: "center"` on a ZStack View had no
        # rendering at all on ios. An omitted gravity falls to the canon
        # default (top|start) through the same read.
        def zstack_default_alignment
          gravity_to_frame_alignment || '.topLeading'
        end
      end
    end
  end
end