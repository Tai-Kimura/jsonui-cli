require_relative 'margin_expression_helper'

module SjuiTools
  module SwiftUI
    module Views
      module SpacingHelper
        include MarginExpressionHelper

        # One padding edge as Swift. `.to_i` on a binding is 0, which is how
        # every bound padding froze to `.padding(.top, 0)` — the declaration
        # compiled, ran, and inset nothing (plan 49, 6 findings). Numbers keep
        # `.to_i` exactly, so a numeric declaration emits the bytes it always
        # did.
        def padding_value(value)
          bound_number(value) || value.to_i
        end

        # パディングを適用（UIKitに合わせてpaddingsに統一）
        def apply_padding
          padding = @component['paddings'] || @component['padding']

          if padding
            # Ensure padding is converted to proper format
            if padding.is_a?(Array)
              case padding.length
              when 1
                @modifier_bag.append(:padding, ".padding(#{padding_value(padding[0])})")
              when 2
                # 縦横のパディング
                @modifier_bag.append(:padding, ".padding(.horizontal, #{padding_value(padding[1])})")
                @modifier_bag.append(:padding, ".padding(.vertical, #{padding_value(padding[0])})")
              when 4
                # 上、左、下、右の順 (JsonUI format: [top, left, bottom, right])
                @modifier_bag.append(:padding, ".padding(.top, #{padding_value(padding[0])})")
                @modifier_bag.append(:padding, ".padding(.leading, #{padding_value(padding[1])})")
                @modifier_bag.append(:padding, ".padding(.bottom, #{padding_value(padding[2])})")
                @modifier_bag.append(:padding, ".padding(.trailing, #{padding_value(padding[3])})")
              end
            else
              @modifier_bag.append(:padding, ".padding(#{padding_value(padding)})")
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
            @modifier_bag.append(:padding, ".padding(.leading, #{padding_value(start_pad)})")
          elsif left_pad
            @modifier_bag.append(:padding, ".padding(.leading, #{padding_value(left_pad)})")
          end

          if end_pad
            @modifier_bag.append(:padding, ".padding(.trailing, #{padding_value(end_pad)})")
          elsif right_pad
            @modifier_bag.append(:padding, ".padding(.trailing, #{padding_value(right_pad)})")
          end

          if top_pad
            @modifier_bag.append(:padding, ".padding(.top, #{padding_value(top_pad)})")
          end
          if bottom_pad
            @modifier_bag.append(:padding, ".padding(.bottom, #{padding_value(bottom_pad)})")
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
            if offset_owns
              # One shared inset per AXIS, not per edge: both edges pad by
              # the same amount, so computing it twice would spell the same
              # value two ways (min(a, b) and min(b, a)).
              top_pad = bottom_pad = shared_margin_padding(top_margin, bottom_margin, :vertical)
              left_pad = right_pad = shared_margin_padding(left_margin, right_margin, :horizontal)
            else
              top_pad = declared_margin(top_margin)
              bottom_pad = declared_margin(bottom_margin)
              left_pad = declared_margin(left_margin)
              right_pad = declared_margin(right_margin)
            end

            if top_pad
              @modifier_bag.append(:margin, ".padding(.top, #{top_pad})")
            end
            if bottom_pad
              @modifier_bag.append(:margin, ".padding(.bottom, #{bottom_pad})")
            end

            # RTL aware margins take precedence over left/right
            if start_margin
              @modifier_bag.append(:margin, ".padding(.leading, #{margin_value(start_margin)})")
            elsif left_pad
              @modifier_bag.append(:margin, ".padding(.leading, #{left_pad})")
            end

            if end_margin
              @modifier_bag.append(:margin, ".padding(.trailing, #{margin_value(end_margin)})")
            elsif right_pad
              @modifier_bag.append(:margin, ".padding(.trailing, #{right_pad})")
            end
          end

          apply_flexible_margins
        end

        private

        # A declared margin as the Swift value to pad by, nil when the
        # attribute is absent. Outside a ZStack every declared margin is
        # padding, bindings included.
        def declared_margin(value)
          value.nil? ? nil : margin_value(value)
        end

        # The inset one AXIS still pads for itself inside a ZStack, or nil
        # for no padding at all.
        #
        # The parent emits the child's individual margins as an .offset, so
        # padding them here again double-applied them (measured +12pt for a
        # declared 8). But the offset carries the DIFFERENCE of the two
        # opposing margins and nothing more, so suppressing padding outright
        # annihilated a symmetric pair: 10/10 cancels to an offset of zero and
        # the declaration rendered as no margin at all. Split the declaration
        # the way it decomposes — the shared inset min(a, b) belongs to
        # padding, the difference to the offset.
        #
        # A pair where either edge is a binding has no comparable inset HERE,
        # but it does at runtime, so the comparison is emitted as Swift —
        # max(0, min(a, b)), the same expression DynamicModifierHelper
        # evaluates. Leaving it to the offset instead would annihilate a
        # symmetric bound margin exactly the way the numeric one used to.
        #
        # An axis the child centres pads by nothing: semantics.margins
        # disables the margin there outright (apply_zstack_positioning zeroes
        # that component too). A single declared edge has no opposite to share
        # with, and a numeric pair whose smaller side is <= 0 has no inset to
        # lift.
        def shared_margin_padding(value, opposite, axis)
          return nil if centered_axis?(axis)
          return nil if value.nil? || opposite.nil?

          numeric = margin_number(value)
          opposite_numeric = margin_number(opposite)
          if numeric && opposite_numeric
            shared = [numeric, opposite_numeric].min
            return shared.positive? ? shared.to_s : nil
          end

          "max(0, min(#{margin_operand(value)}, #{margin_operand(opposite)}))"
        end

        # centerInParent disables both axes, centerHorizontal/centerVertical
        # one each — the same reading as the library's zstackMarginOffset.
        def centered_axis?(axis)
          return true if @component['centerInParent']

          axis == :horizontal ? !!@component['centerHorizontal'] : !!@component['centerVertical']
        end

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
        #
        # The bound branch used to build `data.<everything between the
        # braces>` with its own regexp — the second copy of the bypass plan 43
        # replaced for the ZStack offset. It carried an inline default out
        # unbracketed (`@{gap ?? 12}` -> `.padding(.top, data.gap ?? 12)`) and
        # never unwrapped an Optional. `margin_operand` is the canonical form
        # and the offset path already uses it, so the two spellings of one
        # margin now go through one emitter.
        def margin_value(value)
          is_margin_binding?(value) ? margin_operand(value) : value.to_i
        end

        # バインディング式かどうかを判定
        def is_margin_binding?(value)
          bound_value?(value)
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
