#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative '../../core/type_synonyms'

module SjuiTools
  module SwiftUI
    module Views
      class ScrollViewConverter < BaseViewConverter
        def initialize(component, indent_level = 0, action_manager = nil, converter_factory = nil, view_registry = nil, binding_registry = nil)
          super(component, indent_level, action_manager, binding_registry)
          @converter_factory = converter_factory
          @view_registry = view_registry
        end
        
        # `keyboardAvoidancePadding` as a Swift CGFloat literal, or nil when
        # the layout does not declare it (the library default then applies).
        # A non-numeric value is not silently a number: it emits nothing and
        # the validator's type check is what reports it.
        def keyboard_padding_arg
          v = @component['keyboardAvoidancePadding']
          return nil unless v.is_a?(Numeric)
          v == v.to_i ? v.to_i.to_s : v.to_s
        end

        def convert
          child_data = @component['child'] || []
          # childが単一要素の場合は配列に変換
          children = child_data.is_a?(Array) ? child_data : [child_data]
          
          # スクロール方向の判定 — horizontalScroll true or orientation
          # horizontal scrolls sideways, anything else vertically. Never from
          # the children: a horizontal child is laid out in a vertical scroll
          # (attribute_definitions.json ScrollView, user ruling 2026-10-14,
          # jui-scrollview-axis-from-child-web-disagrees). A pair that
          # disagrees is refused by jui build (ERROR [scrollview]).
          orientation = @component['orientation']
          horizontal_scroll = @component['horizontalScroll']

          # スクロール軸の設定
          if horizontal_scroll || orientation == 'horizontal'
            axes = '.horizontal'
            stack_type = 'HStack'
          else
            # デフォルトは垂直スクロール
            axes = '.vertical'
            stack_type = 'VStack'
          end
          
          # インジケーターの表示設定
          show_indicators = if orientation == 'horizontal'
            @component['showsHorizontalScrollIndicator'] != false
          else
            @component['showsVerticalScrollIndicator'] != false
          end

          # keyboardAvoidance属性の確認（デフォルトはtrue）
          keyboard_avoidance = @component['keyboardAvoidance'] != false

          # keyboardDismissMode (none|onDrag|interactive, UIKit value names) —
          # opt-in only: unset emits nothing and the component defaults to
          # .never (scrolling does not dismiss the keyboard).
          dismiss_mode = @component['keyboardDismissMode']
          dismiss_arg = %w[onDrag interactive].include?(dismiss_mode) ? ", keyboardDismissMode: \"#{dismiss_mode}\"" : ''

          # keyboardAvoidancePadding (SSoT: ScrollView, number, default 20):
          # the clearance a focused field keeps from the scroll view's
          # visible bottom while the keyboard is up. Declared → passed as
          # KeyboardAvoidanceConfiguration.additionalPadding; absent → the
          # library's own default, which is the SSoT's 20. Until 1.8.108 no
          # layout attribute reached that parameter, and until SwiftJsonUI
          # 10.27.0 the parameter reached nothing on screen (reported
          # 2026-09-22: a focused field flush against the fixed footer).
          padding_arg = keyboard_padding_arg

          # A horizontal ScrollView of height wrapContent is as tall as its
          # content (KotlinJsonUI's horizontalScroll row). Its view,
          # AdvancedKeyboardAvoidingScrollView, is a GeometryReader framing the
          # scroll at the reader's height, and in a vertical ScrollView the
          # reader is offered none: it took the height the outer ScrollView had
          # left — a 28pt row drew 386pt tall in a 420pt ScrollView on
          # SwiftJsonUI's ConformanceHost (ticket
          # 2026-10-23-sjui-geometryreader-in-vertical-scroll-collapses). The
          # content is measured at its own height (content_fit_height) and the
          # ScrollView framed at it.
          fit_height = content_fit_height(axes)

          # AdvancedKeyboardAvoidingScrollViewを使用
          # keyboardAvoidance: falseの場合はconfigurationでisEnabled: falseを指定
          if keyboard_avoidance
            config_arg = padding_arg ? ", configuration: KeyboardAvoidanceConfiguration(additionalPadding: #{padding_arg})" : ''
            add_line "AdvancedKeyboardAvoidingScrollView(#{axes}, showsIndicators: #{show_indicators}#{config_arg}#{dismiss_arg}) {"
          else
            add_line "AdvancedKeyboardAvoidingScrollView(#{axes}, showsIndicators: #{show_indicators}, configuration: KeyboardAvoidanceConfiguration(isEnabled: false)#{dismiss_arg}) {"
          end
          
          indent do
            # The content stack, at the ScrollView's own content gravity
            # (common.gravity is "Content gravity/alignment"; gravityDefaults
            # top|start). A child's gravity is that child's content's and does
            # not place the child: the single-child branch used to read it
            # here, through a reader of its own that did not know
            # centerHorizontal, and placed a narrow child centre / right where
            # Dynamic, Android and web drew it at the start (2026-10-05). The
            # gravity is read by ResponsiveHelper, as a View's is. Dynamic:
            # DynamicScrollViewContainer, the same alignment.
            stack_alignment, frame_alignment =
              if axes == '.vertical'
                case ResponsiveHelper.extract_horizontal(@component['gravity'])
                when 'center', 'centerHorizontal' then ['.center', '.top']
                when 'right' then ['.trailing', '.topTrailing']
                else ['.leading', '.topLeading']
                end
              else
                ['.top', '.topLeading']
              end
            add_line "#{stack_type}(alignment: #{stack_alignment}, spacing: 0) {"
            indent do
              children.each do |child|
                # Through the visibility door (base_view_converter): a
                # `visibility` on a child was dropped here until 1.8.107.
                render_child_honoring_visibility(child)
              end
              add_line "Spacer(minLength: 0)"
            end
            add_line "}"
            if fit_height
              # its own height, before the frame stretches it to the viewport
              add_modifier_line ".fixedSize(horizontal: false, vertical: true)"
              add_modifier_line ".onGeometryChange(for: CGFloat.self) { $0.size.height } action: { #{fit_height} = $0 }"
            end
            # Stretched to the ScrollView's size and placed where the stack is
            # aligned: without an alignment the frame centred the stack, so a
            # leading child of a wider ScrollView drew in its middle (x 25 for
            # a 150 child in 200, frame-parity 2026-10-05).
            add_modifier_line ".frame(maxWidth: .infinity, maxHeight: .infinity, alignment: #{frame_alignment})"
          end
          add_line "}"
          
          add_modifier_line ".frame(height: #{fit_height})" if fit_height

          # scrollEnabled — emit .scrollDisabled(_:) (not .disabled(_:)) so a
          # dynamic toggle does not interrupt an in-flight pan / deceleration.
          scroll_enabled = @component['scrollEnabled']
          if scroll_enabled == false
            add_modifier_line ".scrollDisabled(true)"
          elsif scroll_enabled.is_a?(String) && is_binding?(scroll_enabled)
            prop = extract_binding_property(scroll_enabled)
            add_modifier_line ".scrollDisabled(!data.#{prop})"
          end
          
          # bounces
          if @component['bounces'] == false
            add_modifier_line "// Note: bounce behavior cannot be disabled in SwiftUI"
          end
          
          # contentInsetAdjustmentBehavior
          if @component['contentInsetAdjustmentBehavior']
            case @component['contentInsetAdjustmentBehavior']
            when 'never'
              add_modifier_line ".ignoresSafeArea()"
            when 'scrollableAxes'
              add_modifier_line ".ignoresSafeArea(edges: .horizontal)"
            when 'always', 'automatic'
              # デフォルトの動作
            else
              add_line "// contentInsetAdjustmentBehavior: #{@component['contentInsetAdjustmentBehavior']}"
            end
          end
          
          # paging プロパティの処理
          if @component['paging'] == true || @component['paging'] == 'true'
            # iOS 17+ では.scrollTargetBehavior(.paging)が使える
            add_modifier_line ".scrollTargetBehavior(.paging)"
            add_line "// Note: Paging requires iOS 17+"
          end

          # defaultScrollAnchor プロパティの処理
          default_anchor = @component['defaultScrollAnchor']
          if default_anchor
            if default_anchor.is_a?(String) && is_binding?(default_anchor)
              prop = extract_property_name(default_anchor)
              add_modifier_line ".defaultScrollAnchor(data.#{prop} == \"bottom\" ? .bottom : data.#{prop} == \"center\" ? .center : .top)"
            else
              anchor = case default_anchor
                       when 'top' then '.top'
                       when 'center' then '.center'
                       when 'bottom' then '.bottom'
                       else '.top'
                       end
              add_modifier_line ".defaultScrollAnchor(#{anchor})"
            end
          end

          # maxZoom プロパティの処理（ズーム可能なScrollView）
          if @component['maxZoom']
            add_modifier_line ".scaleEffect(1.0)"  # デフォルトスケール
            add_line "// maxZoom: #{@component['maxZoom']} - Consider using MagnificationGesture"
            add_modifier_line ".gesture("
            indent do
              add_line "MagnificationGesture()"
              add_modifier_line ".onChanged { value in"
              indent do
                add_line "// Scale content based on gesture"
                add_line "// Maximum zoom: #{@component['maxZoom']}"
              end
              add_line "}"
            end
            add_line ")"
          end
          
          # AdvancedKeyboardAvoidingScrollViewは自動的に両方の回避機能を持つため、
          # 追加のモディファイアは不要
          
          # 共通のモディファイアを適用
          apply_modifiers
          
          generated_code
        end

        # A horizontal-only ScrollView of height wrapContent: the name of its
        # content height's state, declared here (nil until measured: no frame,
        # as before); nil for any other ScrollView.
        def content_fit_height(axes)
          return nil unless axes == '.horizontal' && @component['height'] == 'wrapContent'

          name = @component['id'] ? to_camel_case(@component['id']) : to_camel_case(position_name('scrollView'))
          state = "#{name}ContentHeight"
          @state_variables << "@State private var #{state}: CGFloat? = nil"
          state
        end
      end
    end
  end
end