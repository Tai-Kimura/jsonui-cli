module SjuiTools
  module SwiftUI
    module Views
      module SpacingHelper
        # パディングを適用（UIKitに合わせてpaddingsに統一）
        def apply_padding
          padding = @component['paddings'] || @component['padding']

          if padding
            # Ensure padding is converted to proper format
            if padding.is_a?(Array)
              case padding.length
              when 1
                @modifier_bag.append(:padding, ".padding(#{padding[0].to_i})")
              when 2
                # 縦横のパディング
                @modifier_bag.append(:padding, ".padding(.horizontal, #{padding[1].to_i})")
                @modifier_bag.append(:padding, ".padding(.vertical, #{padding[0].to_i})")
              when 4
                # 上、左、下、右の順 (JsonUI format: [top, left, bottom, right])
                @modifier_bag.append(:padding, ".padding(.top, #{padding[0].to_i})")
                @modifier_bag.append(:padding, ".padding(.leading, #{padding[1].to_i})")
                @modifier_bag.append(:padding, ".padding(.bottom, #{padding[2].to_i})")
                @modifier_bag.append(:padding, ".padding(.trailing, #{padding[3].to_i})")
              end
            else
              @modifier_bag.append(:padding, ".padding(#{padding.to_i})")
            end
          end

          # 個別のパディング設定（paddingLeft / leftPadding 両形式対応）
          left_pad = @component['paddingLeft'] || @component['leftPadding']
          right_pad = @component['paddingRight'] || @component['rightPadding']
          top_pad = @component['paddingTop'] || @component['topPadding']
          bottom_pad = @component['paddingBottom'] || @component['bottomPadding']

          # RTL aware padding
          start_pad = @component['paddingStart']
          end_pad = @component['paddingEnd']

          # RTL aware padding takes precedence over left/right
          if start_pad
            @modifier_bag.append(:padding, ".padding(.leading, #{start_pad.to_i})")
          elsif left_pad
            @modifier_bag.append(:padding, ".padding(.leading, #{left_pad.to_i})")
          end

          if end_pad
            @modifier_bag.append(:padding, ".padding(.trailing, #{end_pad.to_i})")
          elsif right_pad
            @modifier_bag.append(:padding, ".padding(.trailing, #{right_pad.to_i})")
          end

          if top_pad
            @modifier_bag.append(:padding, ".padding(.top, #{top_pad.to_i})")
          end
          if bottom_pad
            @modifier_bag.append(:padding, ".padding(.bottom, #{bottom_pad.to_i})")
          end
        end

        # マージンを適用（SwiftUIではGroup内でpaddingとして実装）
        def apply_margins
          left_margin = @component['leftMargin']
          right_margin = @component['rightMargin']
          top_margin = @component['topMargin']
          bottom_margin = @component['bottomMargin']
          margins = @component['margins']

          # RTL aware margins
          start_margin = @component['startMargin']
          end_margin = @component['endMargin']

          # marginsが配列で指定されている場合
          if margins
            if margins.is_a?(Array)
              case margins.length
              when 1
                # 全方向同じマージン
                @modifier_bag.append(:margin, ".padding(.all, #{margins[0].to_i})")
              when 2
                # 縦横のマージン
                @modifier_bag.append(:margin, ".padding(.vertical, #{margins[0].to_i})")
                @modifier_bag.append(:margin, ".padding(.horizontal, #{margins[1].to_i})")
              when 4
                # 上、右、下、左の順
                @modifier_bag.append(:margin, ".padding(.top, #{margins[0].to_i})")
                @modifier_bag.append(:margin, ".padding(.trailing, #{margins[1].to_i})")
                @modifier_bag.append(:margin, ".padding(.bottom, #{margins[2].to_i})")
                @modifier_bag.append(:margin, ".padding(.leading, #{margins[3].to_i})")
              end
            else
              @modifier_bag.append(:margin, ".padding(.all, #{margins.to_i})")
            end
          else
            # 個別のマージン設定（バインディング対応）
            # ZStack children: the parent's apply_zstack_positioning emits the
            # SAME four individual margins as a .offset (full-margin
            # frame-context semantics) — emitting .padding here too
            # double-applied them (measured +12pt for a declared 8 in the
            # centered conformance frame). start/endMargin are not part of
            # the offset computation and keep their padding.
            offset_owns = @component['_zstack_margin_offset']
            if top_margin && !offset_owns
              @modifier_bag.append(:margin, ".padding(.top, #{margin_value(top_margin)})")
            end
            if bottom_margin && !offset_owns
              @modifier_bag.append(:margin, ".padding(.bottom, #{margin_value(bottom_margin)})")
            end

            # RTL aware margins take precedence over left/right
            if start_margin
              @modifier_bag.append(:margin, ".padding(.leading, #{margin_value(start_margin)})")
            elsif left_margin && !offset_owns
              @modifier_bag.append(:margin, ".padding(.leading, #{margin_value(left_margin)})")
            end

            if end_margin
              @modifier_bag.append(:margin, ".padding(.trailing, #{margin_value(end_margin)})")
            elsif right_margin && !offset_owns
              @modifier_bag.append(:margin, ".padding(.trailing, #{margin_value(right_margin)})")
            end
          end

          apply_flexible_margins
        end

        private

        # min/max{Start,End}Margin — a margin declared as a range instead of a
        # fixed inset. SwiftUI has no flexible padding, so the library turns the
        # bounds into a capped Spacer (see FlexibleMargin.swift); this only has
        # to decide whether the bounds apply at all.
        #
        # A fixed margin on the same side wins, matching UIKit: leftMargin takes
        # the `equal` constraint and the min/max pair is never consulted
        # (UIViewDisposure.applyLeftPaddingConstraint). `margins` sets every
        # side, so it suppresses both.
        def apply_flexible_margins
          return if @component['margins']

          leading_fixed = @component['startMargin'] || @component['leftMargin']
          trailing_fixed = @component['endMargin'] || @component['rightMargin']

          args = []
          unless leading_fixed
            args << "minStart: #{flexible_margin_value(@component['minStartMargin'])}" if flexible_margin?(@component['minStartMargin'])
            args << "maxStart: #{flexible_margin_value(@component['maxStartMargin'])}" if flexible_margin?(@component['maxStartMargin'])
          end
          unless trailing_fixed
            args << "minEnd: #{flexible_margin_value(@component['minEndMargin'])}" if flexible_margin?(@component['minEndMargin'])
            args << "maxEnd: #{flexible_margin_value(@component['maxEndMargin'])}" if flexible_margin?(@component['maxEndMargin'])
          end
          return if args.empty?

          @modifier_bag.append(:margin, ".flexibleHorizontalMargin(#{args.join(', ')})")
        end

        # Declared `type: number`, so a non-numeric value is an authoring error
        # rather than something to coerce — emitting `nil` for it would silently
        # drop the bound.
        def flexible_margin?(value)
          value.is_a?(Numeric) || (value.is_a?(String) && value.match?(/\A-?\d+(\.\d+)?\z/))
        end

        def flexible_margin_value(value)
          value.to_s
        end

        # マージン値を取得（バインディング対応）
        def margin_value(value)
          if is_margin_binding?(value)
            extract_margin_binding_value(value)
          else
            value.to_i
          end
        end

        # バインディング式かどうかを判定
        def is_margin_binding?(value)
          value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
        end

        # バインディング式からSwiftUIの値を抽出
        def extract_margin_binding_value(value)
          return value unless value.is_a?(String)
          if value =~ /^@\{(.+)\}$/
            "data.#{$1}"
          else
            value
          end
        end

        # insetsプロパティを適用（パディングの別形式）
        def apply_insets
          # insets プロパティ（パディングの別形式）
          if @component['insets']
            insets = @component['insets']
            if insets.is_a?(Array)
              case insets.length
              when 1
                @modifier_bag.append(:padding, ".padding(#{insets[0].to_i})")
              when 2
                # 縦横のinsets
                @modifier_bag.append(:padding, ".padding(.vertical, #{insets[0].to_i})")
                @modifier_bag.append(:padding, ".padding(.horizontal, #{insets[1].to_i})")
              when 4
                # 上、右、下、左の順
                @modifier_bag.append(:padding, ".padding(.top, #{insets[0].to_i})")
                @modifier_bag.append(:padding, ".padding(.trailing, #{insets[1].to_i})")
                @modifier_bag.append(:padding, ".padding(.bottom, #{insets[2].to_i})")
                @modifier_bag.append(:padding, ".padding(.leading, #{insets[3].to_i})")
              end
            else
              @modifier_bag.append(:padding, ".padding(#{insets.to_i})")
            end
          end

          # insetHorizontal プロパティ
          if @component['insetHorizontal']
            @modifier_bag.append(:padding, ".padding(.horizontal, #{@component['insetHorizontal'].to_i})")
          end
        end
      end
    end
  end
end
