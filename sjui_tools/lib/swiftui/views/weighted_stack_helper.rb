require_relative 'value_expression_helper'
module SjuiTools
  module SwiftUI
    module Views
      module WeightedStackHelper
        # `get_child_weight` renders a bound weight as a Swift expression, so
        # it needs the shared emitters. The module is mixed into converters
        # that already have them, and into bare test doubles that do not.
        include ValueExpressionHelper

        # WeightedHStackを生成
        def generate_weighted_hstack(children, alignment)
          add_line "GeometryReader { geometry in"
          indent do
            add_line "HStack(alignment: #{alignment}, spacing: 0) {"
            indent do
              render_weighted_children(children, 'horizontal')
            end
            add_line "}"
          end
          add_line "}"
        end
        
        # WeightedVStackを生成
        def generate_weighted_vstack(children, alignment)
          add_line "GeometryReader { geometry in"
          indent do
            add_line "VStack(alignment: #{alignment}, spacing: 0) {"
            indent do
              render_weighted_children(children, 'vertical')
            end
            add_line "}"
          end
          add_line "}"
        end
        
        private
        
        # 重み付けされた子要素をレンダリング
        def render_weighted_children(children, orientation)
          # 固定サイズの子要素のサイズを格納
          fixed_sizes = []
          weighted_children = []
          total_weight = 0.0
          
          # 子要素を分類
          children.each_with_index do |child, index|
            weight = get_child_weight(child, orientation)
            if weight > 0
              weighted_children << { child: child, weight: weight, index: index }
              total_weight += weight
            else
              fixed_sizes << { child: child, index: index }
            end
          end
          
          # 固定サイズの子要素を先にレンダリング（サイズ測定のため）
          fixed_sizes.each do |item|
            child = item[:child]
            add_line "// Fixed size child"
            render_child_without_weight(child, orientation)
          end
          
          # 重み付けされた子要素をレンダリング
          if weighted_children.any? && total_weight > 0
            # 固定サイズの合計を計算するためのGeometryReaderを追加
            weighted_children.each do |item|
              child = item[:child]
              weight = item[:weight]
              weight_ratio = weight / total_weight
              
              add_line "// Weighted child (weight: #{weight})"
              render_weighted_child(child, orientation, weight_ratio)
            end
          end
        end
        
        # 子要素のweightを取得
        #
        # Numeric only, deliberately. This module divides the weight by the
        # sibling total to compute a ratio at GENERATION time, and a bound
        # weight has no value here to divide — the live path
        # (`ViewConverter`, which builds `WeightedHStack(children:)`) hands
        # the weight to the library as a `CGFloat` expression instead and
        # lets the layout do the division at run time. Nothing includes this
        # module today; if something does, the bound form has to go through
        # `ValueExpressionHelper#weight_expression` there too.
        def get_child_weight(child, orientation)
          return 0 unless child.is_a?(Hash)

          declared = child['weight']
          declared = child['widthWeight'] if declared.nil? && orientation == 'horizontal'
          declared = child['heightWeight'] if declared.nil? && orientation == 'vertical'
          return 0 if declared.nil? || bound_value?(declared)

          declared.to_f
        end
        
        # 重みなしの子要素をレンダリング
        def render_child_without_weight(child, orientation)
          child_copy = child.dup
          child_copy['parent_orientation'] = orientation
          
          child_converter = @converter_factory.create_converter(
            child_copy, 
            @indent_level, 
            @action_manager, 
            @converter_factory, 
            @view_registry
          )
          
          child_code = child_converter.convert
          child_lines = child_code.split("\n")
          child_lines.each { |line| add_line line }
          
          # State変数を継承
          if child_converter.respond_to?(:state_variables) && child_converter.state_variables
            @state_variables.concat(child_converter.state_variables)
          end
        end
        
        # 重み付けされた子要素をレンダリング
        def render_weighted_child(child, orientation, weight_ratio)
          child_copy = child.dup
          child_copy['parent_orientation'] = orientation
          
          # GeometryReaderでラップ
          if orientation == 'horizontal'
            # 水平方向の重み付け
            # 利用可能な幅を計算
            add_line "FixedSizeReader { fixedWidth in"
            indent do
              add_line "let availableWidth = geometry.size.width - fixedWidth"
              add_line "let childWidth = availableWidth * #{weight_ratio.round(4)}"
              
              child_converter = @converter_factory.create_converter(
                child_copy, 
                @indent_level + 1, 
                @action_manager, 
                @converter_factory, 
                @view_registry
              )
              
              child_code = child_converter.convert
              child_lines = child_code.split("\n")
              
              # 最初の行にframeモディファイアを追加
              if child_lines.any?
                first_line = child_lines.shift
                add_line first_line
                indent do
                  add_modifier_line ".frame(width: childWidth)"
                  # 残りの行を追加
                  child_lines.each { |line| add_line line.strip }
                end
              end
            end
            add_line "}"
          else
            # 垂直方向の重み付け
            add_line "FixedSizeReader { fixedHeight in"
            indent do
              add_line "let availableHeight = geometry.size.height - fixedHeight"
              add_line "let childHeight = availableHeight * #{weight_ratio.round(4)}"
              
              child_converter = @converter_factory.create_converter(
                child_copy, 
                @indent_level + 1, 
                @action_manager, 
                @converter_factory, 
                @view_registry
              )
              
              child_code = child_converter.convert
              child_lines = child_code.split("\n")
              
              # 最初の行にframeモディファイアを追加
              if child_lines.any?
                first_line = child_lines.shift
                add_line first_line
                indent do
                  add_modifier_line ".frame(height: childHeight)"
                  # 残りの行を追加
                  child_lines.each { |line| add_line line.strip }
                end
              end
            end
            add_line "}"
          end
          
          # State変数を継承
          if child_converter.respond_to?(:state_variables) && child_converter.state_variables
            @state_variables.concat(child_converter.state_variables)
          end
        end
      end
    end
  end
end