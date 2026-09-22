# frozen_string_literal: true

require_relative '../helpers/content_inset_helper'
require_relative '../helpers/modifier_builder'

module KjuiTools
  module Compose
    module Components
      class ScrollViewComponent
        # `keyboardAvoidancePadding` in dp; the SSoT default (20) when the
        # layout does not declare it, so the clearance is the same on both
        # platforms whether or not the attribute is written. nil for a
        # non-numeric value (the validator reports the type).
        def self.keyboard_padding_dp(json_data)
          return 20 unless json_data.key?('keyboardAvoidancePadding')
          v = json_data['keyboardAvoidancePadding']
          return nil unless v.is_a?(Numeric)
          v == v.to_i ? v.to_i : v
        end

        def self.generate(json_data, depth, required_imports = nil, parent_type = nil, is_root: false)
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

          # paging: every child becomes its own lazy item and the fling snaps
          # to item bounds — the child IS the page, which is what UIKit's
          # isPagingEnabled gives a full-size-children ScrollView. Without
          # paging the children share one item (plain scroll).
          paging = json_data['paging'] == true
          # defaultScrollAnchor — where the scroll STARTS. The non-paging emit
          # puts every child in ONE lazy item, so item indices cannot anchor;
          # scrollBy is item-agnostic: a huge delta clamps at the end (bottom),
          # and backing up half the consumed extent is the centre. One-shot on
          # first composition, same contract as Collection's anchor.
          anchor = json_data['defaultScrollAnchor'].to_s
          anchor = nil unless %w[center bottom].include?(anchor)
          state_var = nil
          code = ''
          if paging || anchor
            required_imports&.add(:snap_fling) if paging
            required_imports&.add(:lazy_list_state) unless paging
            state_var = "scrollPagingState#{json_data['id'].to_s.gsub(/[^A-Za-z0-9]/, '')}"
            code += indent("val #{state_var} = rememberLazyListState()", depth) + "\n"
          end
          if anchor
            required_imports&.add(:launched_effect)
            required_imports&.add(:scroll_by)
            code += indent("LaunchedEffect(Unit) {", depth) + "\n"
            code += indent("val consumed = #{state_var}.scrollBy(1e9f)", depth + 1) + "\n"
            code += indent("#{state_var}.scrollBy(-consumed / 2f)", depth + 1) + "\n" if anchor == 'center'
            code += indent("}", depth) + "\n"
          end

          if is_horizontal
            required_imports&.add(:lazy_row)
            code += indent("LazyRow(", depth)
          else
            required_imports&.add(:lazy_column)
            code += indent("LazyColumn(", depth)
          end
          if paging
            code += "\n" + indent("state = #{state_var},", depth + 1)
            code += "\n" + indent("flingBehavior = rememberSnapFlingBehavior(lazyListState = #{state_var}),", depth + 1)
          elsif anchor
            code += "\n" + indent("state = #{state_var},", depth + 1)
          end

          # `contentInsetAdjustmentBehavior` — see ContentInsetHelper. UIKit
          # adjusts by default and the attribute stops it; Compose never
          # adjusts, so the values that need code are the opposite ones.
          if (safe_inset = Helpers::ContentInsetHelper.safe_area_padding(
                json_data['contentInsetAdjustmentBehavior'], horizontal: is_horizontal))
            Helpers::ContentInsetHelper.imports_for(json_data['contentInsetAdjustmentBehavior'])
                                       .each { |k| required_imports&.add(k) }
            code += "\n" + indent("contentPadding = #{safe_inset},", depth + 1)
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

          # Apply keyboard avoidance at the end of modifier chain
          if keyboard_avoidance
            required_imports&.add(:ime_padding)
            modifiers << ".imePadding()"
            # keyboardAvoidancePadding (SSoT: number, default 20): while the
            # IME is up, the scrollable's viewport ends this far above it, so
            # Compose's bringIntoView (which stops a focused field at the
            # viewport edge) leaves that clearance. AFTER imePadding and on
            # the LazyColumn itself: a padding inside the scroll content
            # would only add scrollable space, not a margin. Reported
            # 2026-09-22 (iOS first; Android had the same 0 through
            # imePadding alone).
            padding = keyboard_padding_dp(json_data)
            if padding
              required_imports&.add(:window_insets_ime)
              modifiers << ".padding(bottom = if (WindowInsets.ime.getBottom(LocalDensity.current) > 0) #{padding}.dp else 0.dp)"
            end
          end

          if modifiers.any? || is_root
            code += Helpers::ModifierBuilder.format(modifiers, depth, is_root: is_root)
          end

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
          code += "\n" + indent("item {", depth + 1) unless paging
          
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
          result = {
            code: code,
            children: children,
            closing: paging ? "\n" + indent("}", depth) : "\n" + indent("}", depth + 1) + "\n" + indent("}", depth),
            layout_type: 'ScopeFree',
            json_data: json_data
          }
          result[:child_wrapper] = { open: 'item {', close: '}' } if paging
          result
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