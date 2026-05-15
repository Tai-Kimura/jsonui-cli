# frozen_string_literal: true

require_relative '../helpers/modifier_builder'

module KjuiTools
  module Compose
    module Components
      class ScrollViewComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # スクロール方向の判定
          # horizontalScroll属性、orientation属性、またはchild要素の配置から判定
          is_horizontal = false
          
          # 1. horizontalScroll属性を最優先
          if json_data.key?('horizontalScroll')
            is_horizontal = json_data['horizontalScroll']
          # 2. orientation属性を次に確認
          elsif json_data.key?('orientation')
            is_horizontal = json_data['orientation'] == 'horizontal'
          # 3. child要素の配置から判定
          elsif json_data['child']
            children = json_data['child']
            # childを配列として扱う
            children = [children] unless children.is_a?(Array)
            
            # 配列の中から最初のViewコンポーネントを探す
            first_view = children.find { |child| child.is_a?(Hash) && child['type'] == 'View' }
            if first_view
              is_horizontal = first_view['orientation'] == 'horizontal'
            end
          end
          
          # keyboardAvoidance属性の確認（デフォルトはtrue）
          keyboard_avoidance = json_data['keyboardAvoidance'] != false

          if is_horizontal
            required_imports&.add(:lazy_row)
            code = indent("LazyRow(", depth)
          else
            required_imports&.add(:lazy_column)
            code = indent("LazyColumn(", depth)
          end

          # Build modifiers
          modifiers = []

          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          # Apply keyboard avoidance at the end of modifier chain
          if keyboard_avoidance
            required_imports&.add(:ime_padding)
            modifiers << ".imePadding()"
          end

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?

          # scrollEnabled - controls whether the user can scroll
          if json_data.key?('scrollEnabled')
            scroll_enabled = json_data['scrollEnabled']
            if scroll_enabled.is_a?(String) && scroll_enabled.match(/@\{([^}]+)\}/)
              # Data binding
              prop = $1
              code += ",\n" + indent("userScrollEnabled = data.#{prop}", depth + 1)
            else
              code += ",\n" + indent("userScrollEnabled = #{scroll_enabled}", depth + 1)
            end
          end

          code += "\n" + indent(") {", depth)
          code += "\n" + indent("item {", depth + 1)
          
          # Process children
          children = json_data['child'] || []
          children = [children] unless children.is_a?(Array)
          
          # Return structure for parent to process children.
          #
          # `layout_type: 'ScopeFree'` is important — children render inside
          # the `item { ... }` lambda whose receiver is `LazyItemScope`, not
          # ColumnScope/RowScope. Without this override, handle_container_result
          # falls back to the outer parent_type (e.g. 'Column' when ScrollView
          # is the child of a vertical SafeAreaView), and a child responsive
          # View that emits `Modifier.align(Alignment.CenterHorizontally)` then
          # tries to resolve `.align` against an implicit ColumnScope receiver
          # that isn't actually present. SwiftUI-free centering modifiers
          # (`wrapContentWidth/Height(Alignment.*)`) work in any scope, so the
          # ScopeFree branch of build_alignment routes through those instead.
          {
            code: code,
            children: children,
            closing: "\n" + indent("}", depth + 1) + "\n" + indent("}", depth),
            layout_type: 'ScopeFree',
            json_data: json_data
          }
        end
        
        private
        
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