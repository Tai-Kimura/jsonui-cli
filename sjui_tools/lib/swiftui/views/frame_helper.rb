require_relative 'responsive_helper'

module SjuiTools
  module SwiftUI
    module Views
      module FrameHelper
        # idealWidth / idealHeight — the SwiftUI layout system's preferred size.
        #
        # Emitted as SEPARATE `.frame()` calls, deliberately, because that is
        # exactly what the SwiftUI Dynamic runtime does
        # (DynamicModifierHelper: `result.frame(idealWidth: iw)`). SwiftUI
        # composes nested frames, so an explicit idealHeight next to a fixed
        # `height` is simply inert rather than conflicting — merging it into the
        # width/height frame instead would fight the auto-derived
        # `.frame(minHeight:idealHeight:maxHeight:)` that the matchParent branch
        # below already emits.
        # Written out per attribute rather than looped on purpose: the
        # attribute-coverage scan looks for a literal `@component['name']`, so a
        # loop over a name list reads as "nobody consumes this" and the ledger
        # keeps counting the attribute as unimplemented after it is implemented.
        def apply_ideal_size
          if @component['idealWidth']
            @modifier_bag.append(:frame_size, ".frame(idealWidth: #{ideal_size_param(@component['idealWidth'])})")
          end
          if @component['idealHeight']
            @modifier_bag.append(:frame_size, ".frame(idealHeight: #{ideal_size_param(@component['idealHeight'])})")
          end
        end

        def ideal_size_param(value)
          is_binding?(value) ? extract_binding_value(value) : value
        end

        def apply_frame_constraints
          apply_ideal_size

          # サイズ制約（minWidth, maxWidth, minHeight, maxHeight）
          if @component['minWidth'] || @component['maxWidth'] || @component['minHeight'] || @component['maxHeight']
            min_width = @component['minWidth']
            max_width = @component['maxWidth']
            min_height = @component['minHeight']
            max_height = @component['maxHeight']

            frame_params = []
            # バインディングサポート: @{propertyName} 形式の場合はそのまま使用
            if min_width
              if is_binding?(min_width)
                frame_params << "minWidth: #{extract_binding_value(min_width)}"
              else
                frame_params << "minWidth: #{min_width}"
              end
            end
            if max_width
              if is_binding?(max_width)
                frame_params << "maxWidth: #{extract_binding_value(max_width)}"
              else
                frame_params << "maxWidth: #{max_width == 'matchParent' ? '.infinity' : max_width}"
              end
            end
            if min_height
              if is_binding?(min_height)
                frame_params << "minHeight: #{extract_binding_value(min_height)}"
              else
                frame_params << "minHeight: #{min_height}"
              end
            end
            if max_height
              if is_binding?(max_height)
                frame_params << "maxHeight: #{extract_binding_value(max_height)}"
              else
                frame_params << "maxHeight: #{max_height == 'matchParent' ? '.infinity' : max_height}"
              end
            end

            # For labels and text components, add alignment based on textAlign and gravity
            if frame_params.any?
              if @component['type'] == 'Label' || @component['type'] == 'Text'
                frame_params << "alignment: #{label_frame_alignment}"
              else
                # Non-Label inner frame alignment is `gravity`-driven, NOT
                # responsive `align*` / `center*` flags. The responsive
                # flags are outer-anchor hints; they're applied at the
                # outer `.frame(.infinity, alignment: ...)` wrap emitted
                # by responsive_helper. Cascading them onto the inner
                # frame pins wrap-content children to the wrong edge
                # (regression: sjui-kjui-responsive-align-cascades-to-
                # inner-ignoring-gravity).
                #
                # When `gravity` is set, derived alignment is used.
                # Otherwise, if any responsive flag is set, fall back to
                # `.center` so the trio contract (centerHorizontal +
                # maxWidth: N → `.frame(maxWidth: N, alignment: .center)`)
                # is preserved. If neither, the alignment is omitted and
                # SwiftUI's implicit `.center` default takes over.
                alignment = ResponsiveHelper.inner_frame_alignment(@component)
                frame_params << "alignment: #{alignment}" if alignment
              end
              @modifier_bag.append(:frame_constraints, ".frame(#{frame_params.join(', ')})")
            end

            # Apply fixedSize for wrapContent without maxWidth/maxHeight constraints
            # With maxWidth, text should wrap within the max constraint (no horizontal fixedSize)
            # Without maxWidth, wrapContent needs fixedSize to prevent expansion
            width_is_wrap = @component['width'].nil? || @component['width'].to_s.downcase == 'wrapcontent' || @component['width'].to_s.downcase == 'wrap_content'
            height_is_wrap = @component['height'].nil? || @component['height'].to_s.downcase == 'wrapcontent' || @component['height'].to_s.downcase == 'wrap_content'
            # Only need fixedSize when wrapContent WITHOUT max constraint
            # maxWidth already constrains the width, so fixedSize(horizontal) would prevent wrapping
            needs_h_fixed = width_is_wrap && !max_width
            needs_v_fixed = height_is_wrap && !max_height
            h_fixed = needs_h_fixed || (needs_v_fixed && width_is_wrap && !max_width)
            v_fixed = needs_v_fixed || (needs_h_fixed && height_is_wrap && !max_height)
            if h_fixed || v_fixed
              @modifier_bag.register(:fixed_size, ".fixedSize(horizontal: #{h_fixed}, vertical: #{v_fixed})")
            end
          end
        end

        def apply_frame_size
          # サイズ
          if @component['width'] || @component['height']
            # weightがある場合、width: 0 or height: 0は無視する
            should_ignore_width = (@component['width'] == 0 || @component['width'] == '0') &&
                                 (@component['weight'] || @component['widthWeight'])
            should_ignore_height = (@component['height'] == 0 || @component['height'] == '0') &&
                                  (@component['weight'] || @component['heightWeight'])

            # widthの処理
            # Skip if already handled by weight-based frame (e.g., label_converter)
            should_ignore_width = true if instance_variable_defined?(:@skip_frame_width) && @skip_frame_width
            if !should_ignore_width
              raw_width = @component['width']
              if is_binding?(raw_width)
                # バインディング式の場合
                width_value = extract_binding_value(raw_width)
                width_param = width_value
                width_is_binding = true
              else
                processed_width = process_template_value(raw_width)
                if processed_width.is_a?(Hash) && processed_width[:template_var]
                  width_value = "data.#{to_camel_case(processed_width[:template_var])}"
                  width_param = "CGFloat(#{width_value})"
                else
                  width_value = size_to_swiftui(raw_width)
                  width_param = width_value
                end
                width_is_binding = false
              end
            else
              width_value = nil
              width_param = nil
              width_is_binding = false
            end

            # heightの処理
            if !should_ignore_height
              raw_height = @component['height']
              if is_binding?(raw_height)
                # バインディング式の場合
                height_value = extract_binding_value(raw_height)
                height_param = height_value
                height_is_binding = true
              else
                processed_height = process_template_value(raw_height)
                if processed_height.is_a?(Hash) && processed_height[:template_var]
                  height_value = "data.#{to_camel_case(processed_height[:template_var])}"
                  height_param = "CGFloat(#{height_value})"
                else
                  height_value = size_to_swiftui(raw_height)
                  height_param = height_value
                end
                height_is_binding = false
              end
            else
              height_value = nil
              height_param = nil
              height_is_binding = false
            end

            # matchParent clamps to a declared max bound (canonical
            # size.maxBoundsClampFill, shared/core/attribute_semantics.json):
            # the fill frame carries the bound itself, so no modifier-order
            # game can lose it — .frame(maxWidth: 120) IS min(parent, 120).
            if width_value == '.infinity' && @component['maxWidth'].is_a?(Numeric)
              width_param = @component['maxWidth']
            end
            if height_value == '.infinity' && @component['maxHeight'].is_a?(Numeric)
              height_param = @component['maxHeight']
            end

            if width_value && height_value
              # Check if either dimension is .infinity
              if width_value == '.infinity' && height_value == '.infinity'
                # For labels and text components, add alignment to honor textAlign and gravity
                if @component['type'] == 'Label' || @component['type'] == 'Text'
                  frame_alignment = label_frame_alignment(both_infinity: true)
                  @modifier_bag.append(:frame_size, ".frame(maxWidth: #{width_param}, maxHeight: #{height_param}, alignment: #{frame_alignment})")
                else
                  ga = gravity_to_frame_alignment
                  if ga
                    @modifier_bag.append(:frame_size, ".frame(maxWidth: #{width_param}, maxHeight: #{height_param}, alignment: #{ga})")
                  else
                    @modifier_bag.append(:frame_size, ".frame(maxWidth: #{width_param}, maxHeight: #{height_param})")
                  end
                end
              elsif width_value == '.infinity'
                # Split into two frame calls for maxWidth with fixed height
                # For labels and text components, add alignment to honor textAlign and gravity
                if @component['type'] == 'Label' || @component['type'] == 'Text'
                  frame_alignment = label_frame_alignment
                  @modifier_bag.append(:frame_size, ".frame(maxWidth: #{width_param}, alignment: #{frame_alignment})")
                else
                  ga = gravity_to_frame_alignment
                  if ga
                    @modifier_bag.append(:frame_size, ".frame(maxWidth: #{width_param}, alignment: #{ga})")
                  else
                    @modifier_bag.append(:frame_size, ".frame(maxWidth: #{width_param})")
                  end
                end
                @modifier_bag.append(:frame_size, ".frame(minHeight: #{height_param}, idealHeight: #{height_param}, maxHeight: #{height_param})")
              elsif height_value == '.infinity'
                # Split into two frame calls for fixed width with maxHeight
                @modifier_bag.append(:frame_size, ".frame(width: #{width_param})")
                @modifier_bag.append(:frame_size, ".frame(maxHeight: #{height_param})")
              else
                ga = gravity_to_frame_alignment
                if ga
                  @modifier_bag.append(:frame_size, ".frame(width: #{width_param}, height: #{height_param}, alignment: #{ga})")
                else
                  @modifier_bag.append(:frame_size, ".frame(width: #{width_param}, height: #{height_param})")
                end
              end
            elsif width_value
              if width_value == '.infinity'
                # For labels and text components, add alignment to honor textAlign and gravity
                if @component['type'] == 'Label' || @component['type'] == 'Text'
                  frame_alignment = label_frame_alignment
                  @modifier_bag.append(:frame_size, ".frame(maxWidth: #{width_param}, alignment: #{frame_alignment})")
                else
                  ga = gravity_to_frame_alignment
                  if ga
                    @modifier_bag.append(:frame_size, ".frame(maxWidth: #{width_param}, alignment: #{ga})")
                  else
                    @modifier_bag.append(:frame_size, ".frame(maxWidth: #{width_param})")
                  end
                end
              else
                # For labels, add alignment to honor textAlign and gravity
                if (@component['type'] == 'Label' || @component['type'] == 'Text') && (@component['textAlign'] || @component['gravity'])
                  frame_alignment = label_frame_alignment
                  @modifier_bag.append(:frame_size, ".frame(width: #{width_param}, alignment: #{frame_alignment})")
                else
                  @modifier_bag.append(:frame_size, ".frame(width: #{width_param})")
                end
              end
            elsif height_value
              if height_value == '.infinity'
                @modifier_bag.append(:frame_size, ".frame(maxHeight: #{height_param})")
              else
                @modifier_bag.append(:frame_size, ".frame(minHeight: #{height_param}, idealHeight: #{height_param}, maxHeight: #{height_param})")
              end
            end
          end
        end

        # gravityからSwiftUI frame alignmentを取得
        def gravity_to_frame_alignment
          gravity = @component['gravity']
          return nil unless gravity

          gravities = if gravity.is_a?(Array)
                        gravity.map { |g| g.to_s.strip.downcase }
                      else
                        gravity.to_s.split('|').map { |g| g.strip.downcase }
                      end

          h = nil
          v = nil
          gravities.each do |g|
            case g
            when 'right', 'end' then h = 'trailing'
            when 'left', 'start' then h = 'leading'
            when 'centerhorizontal', 'center_horizontal' then h = 'center'
            when 'centervertical', 'center_vertical' then v = 'center'
            when 'top' then v = 'top'
            when 'bottom' then v = 'bottom'
            when 'center' then h = 'center'; v = 'center'
            end
          end

          # Build Alignment value
          v ||= 'top'
          h ||= 'leading'
          map = {
            %w[top leading] => '.topLeading',
            %w[top center] => '.top',
            %w[top trailing] => '.topTrailing',
            %w[center leading] => '.leading',
            %w[center center] => '.center',
            %w[center trailing] => '.trailing',
            %w[bottom leading] => '.bottomLeading',
            %w[bottom center] => '.bottom',
            %w[bottom trailing] => '.bottomTrailing'
          }
          map[[v, h]]
        end

        # Label/Text用: textAlignとgravityを組み合わせてframe alignmentを決定
        def label_frame_alignment(both_infinity: false)
          gravity = @component['gravity']
          text_align = @component['textAlign']

          # gravityから縦位置を取得
          v = 'top'  # デフォルト
          if gravity
            gravities = if gravity.is_a?(Array)
                          gravity.map { |g| g.to_s.strip.downcase }
                        else
                          gravity.to_s.split('|').map { |g| g.strip.downcase }
                        end
            gravities.each do |g|
              case g
              when 'centervertical', 'center_vertical' then v = 'center'
              when 'bottom' then v = 'bottom'
              when 'center' then v = 'center'
              end
            end
          end

          # textAlignから横位置を取得
          h = case text_align.to_s.downcase
              when 'center' then 'center'
              when 'right', 'trailing' then 'trailing'
              else 'leading'
              end

          map = {
            %w[top leading] => '.topLeading',
            %w[top center] => both_infinity ? '.top' : '.center',
            %w[top trailing] => both_infinity ? '.topTrailing' : '.trailing',
            %w[center leading] => '.leading',
            %w[center center] => '.center',
            %w[center trailing] => '.trailing',
            %w[bottom leading] => '.bottomLeading',
            %w[bottom center] => '.bottom',
            %w[bottom trailing] => '.bottomTrailing'
          }
          map[[v, h]] || '.topLeading'
        end

        private

        # バインディング式かどうかを判定
        def is_binding?(value)
          value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
        end

        # バインディング式からSwiftUIの値を抽出（frame値はread-only）
        def extract_binding_value(value)
          return value unless value.is_a?(String)
          if value =~ /^@\{(.+)\}$/
            "data.#{$1}"
          else
            value
          end
        end
      end
    end
  end
end
