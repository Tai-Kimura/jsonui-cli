require_relative 'value_expression_helper'
require_relative 'responsive_helper'
require_relative '../../core/enum_spelling'

module SjuiTools
  module SwiftUI
    module Views
      module FrameHelper
        include ValueExpressionHelper

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
              if @component['type'] == 'Label'
                # A min / max HEIGHT bound is a box taller than the text: the
                # text's vertical position is the Label rule (label_vertical).
                frame_params << "alignment: #{label_frame_alignment(both_infinity: !(min_height || max_height).nil?)}"
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
                alignment = ResponsiveHelper.inner_frame_alignment(@component, container_content_node?)
                frame_params << "alignment: #{alignment}" if alignment
              end
              @modifier_bag.append(:frame_constraints, ".frame(#{frame_params.join(', ')})")
            end

            # Apply fixedSize for wrapContent without maxWidth/maxHeight constraints
            # With maxWidth, text should wrap within the max constraint (no horizontal fixedSize)
            # Without maxWidth, wrapContent needs fixedSize to prevent expansion
            width_is_wrap = @component['width'].nil? || @component['width'].to_s.downcase == 'wrapcontent' || @component['width'].to_s.downcase == 'wrap_content'
            height_is_wrap = @component['height'].nil? || @component['height'].to_s.downcase == 'wrapcontent' || @component['height'].to_s.downcase == 'wrap_content'

            # A wrapContent axis with a max sizes to its content, capped by the
            # max (the user's ruling, 2026-09-27): `.frame(maxWidth:)` takes
            # the width it is offered up to the max, so a wrapContent chip
            # with maxWidth 160 and the text "chip" was 160 wide on iOS where
            # Compose drew 57dp and the web 58px. contentFit (SwiftJsonUI
            # 10.29.0, CollectionContentFit) gives the view its ideal size on
            # that axis — the frame's, which is the content's clamped to the
            # max — capped by the parent: a longer text still wraps at the max.
            # Not an axis a weight gives the node (the weighted stack sizes it).
            weighted = @component['weight']
            if width_is_wrap && content_cap?(max_width) && !(weighted || @component['widthWeight'])
              @modifier_bag.append(:frame_constraints, '.contentFit(.horizontal)')
            end
            if height_is_wrap && content_cap?(max_height) && !(weighted || @component['heightWeight'])
              @modifier_bag.append(:frame_constraints, '.contentFit(.vertical)')
            end
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
          apply_wrap_cap
        end

        # A max that caps a wrapContent axis: a number or a binding, not
        # matchParent (which fills).
        def content_cap?(value)
          return false if value.nil?

          !%w[matchparent match_parent .infinity].include?(value.to_s.downcase)
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
                if @component['type'] == 'Label'
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
                if @component['type'] == 'Label'
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
                @modifier_bag.append(:frame_size, ".frame(minHeight: #{height_param}, idealHeight: #{height_param}, maxHeight: #{height_param}#{single_axis_alignment})")
              elsif height_value == '.infinity'
                # Split into two frame calls for fixed width with maxHeight
                # (a Label's width frame places its text across by the
                # Label rule, label_horizontal)
                width_alignment = label_node? ? ", alignment: #{label_frame_alignment}" : single_axis_alignment
                @modifier_bag.append(:frame_size, ".frame(width: #{width_param}#{width_alignment})")
                @modifier_bag.append(:frame_size, ".frame(maxHeight: #{height_param}#{single_axis_alignment})")
              else
                # A Label: its text by the Label rule on both axes - across,
                # textAlign, else gravity's horizontal part, else the start;
                # down, label_vertical. Until jsonui-cli 1.9.0 this took
                # gravity_to_frame_alignment, which read no textAlign, and gave
                # no alignment when gravity was omitted: a 200 x 44 label with
                # neither drew its text in the middle.
                ga = label_node? ? label_frame_alignment(both_infinity: true) : gravity_to_frame_alignment
                if ga
                  @modifier_bag.append(:frame_size, ".frame(width: #{width_param}, height: #{height_param}, alignment: #{ga})")
                else
                  @modifier_bag.append(:frame_size, ".frame(width: #{width_param}, height: #{height_param})")
                end
              end
            elsif width_value
              if width_value == '.infinity'
                # For labels and text components, add alignment to honor textAlign and gravity
                if @component['type'] == 'Label'
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
                # A Label: its text across by the Label rule (label_horizontal)
                # - always, so one with neither textAlign nor gravity is at the
                # start. Until jsonui-cli 1.9.0 it took no alignment then and
                # SwiftUI drew the text in the middle of the fixed width.
                if @component['type'] == 'Label'
                  frame_alignment = label_frame_alignment
                  @modifier_bag.append(:frame_size, ".frame(width: #{width_param}, alignment: #{frame_alignment})")
                else
                  @modifier_bag.append(:frame_size, ".frame(width: #{width_param}#{single_axis_alignment})")
                end
              end
            elsif height_value
              if height_value == '.infinity'
                @modifier_bag.append(:frame_size, ".frame(maxHeight: #{height_param}#{single_axis_alignment})")
              else
                @modifier_bag.append(:frame_size, ".frame(minHeight: #{height_param}, idealHeight: #{height_param}, maxHeight: #{height_param}#{single_axis_alignment})")
              end
            end
          end
        end

        # `, alignment: <gravity alignment>` for a frame that sizes ONE axis of
        # a container (or of a node with a declared gravity) — a fixed size,
        # or a matchParent height with no fixed width — else ''. The
        # user's ruling of 2026-09-27: iOS puts content smaller than such a
        # frame at top | start (gravityDefaults), as Compose (Column / Box)
        # and the web (flex-start) do; a declared center* gravity still
        # centres. Until jsonui-cli 1.9.0 these frames carried no alignment,
        # so SwiftUI centred the content on that axis — a 60pt-tall
        # matchParent View drew a 20pt label 19pt down. A Label keeps its own
        # text alignment (label_frame_alignment), and a leaf with no gravity
        # its content channel (gravity_to_frame_alignment is nil there).
        def single_axis_alignment
          if @component['type'] == 'Label'
            lv = label_vertical_alignment
            return lv ? ", alignment: #{lv}" : ''
          end

          ga = gravity_to_frame_alignment
          ga ? ", alignment: #{ga}" : ''
        end

        # gravityからSwiftUI frame alignmentを取得
        def gravity_to_frame_alignment
          gravity = @component['gravity']

          # An OMITTED gravity is not "no alignment": `gravityDefaults`
          # (ruled 2026-08-07) says the container default is top | start, and
          # `omittedEntirely` states it for this case explicitly — if a partial
          # gravity fills its unnamed axis with the default, an absent one
          # fills both. Returning nil here dropped the argument entirely and
          # left SwiftUI's own `.center`, which is the deviation the
          # 2026-08-03 ruling named ("a platform centering by default is the
          # deviant"). The axis defaults below already do the right thing; the
          # early return was what stopped them being reached.
          #
          # SCOPE: the canon says "on every CONTAINER". A leaf's own-frame
          # content — a fit image's bitmap, a custom component's internals —
          # is a different channel, and there the platform truth is Center
          # (Compose's Image/extension alignment default, which kjui never
          # overrides). Injecting the container default on leaves pinned
          # every fit photo to the top-left on ios only — the exact
          # divergence the ruling set out to close. A DECLARED gravity still
          # applies to any node.
          gravities = if gravity.nil?
                        return nil unless container_content_node?

                        []
                      elsif gravity.is_a?(Array)
                        gravity.map { |g| JsonUIShared::EnumSpelling.lowered(g.to_s.strip, 'common', 'gravity') }.compact
                      else
                        gravity.to_s.split('|').map { |g| JsonUIShared::EnumSpelling.lowered(g.strip, 'common', 'gravity') }.compact
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

          # Build Alignment value. The axis a gravity does not name: a
          # container's is the canon default (top | start); a LEAF's (a
          # TextField, an Image — anything with no children, a Label aside)
          # stays centred. A leaf's partial gravity fixes only its own axis:
          # Compose and the web centre a TextField's and a Button's text
          # vertically in a 44pt frame whatever the gravity (measured
          # 2026-09-27; kjui's emit and the web's are the same for left,
          # right, center and none). Until jsonui-cli 1.9.0 a leaf's `left`
          # filled the vertical axis with `top`, and a TextField's text sat at
          # the top of a 44pt frame (a Button's label is centred by
          # StateAwareButtonView itself, before and after).
          # A reversed stack starts at the edge its direction starts from
          # when its gravity does not name that axis (user ruling 2026-10-05,
          # attribute_semantics stackDirection; SwiftJsonUI's DirectionStart).
          case direction_start_edge
          when 'bottom' then v ||= 'bottom'
          when 'right' then h ||= 'trailing'
          end
          cross = centred_cross_axis? ? 'center' : nil
          # A Label's text sits at the centre of a taller box unless its
          # gravity names the vertical axis (label_vertical); its horizontal
          # default stays start.
          v ||= cross || (label_node? ? 'center' : 'top')
          h ||= cross || 'leading'
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

        # "bottom" for a bottomToTop column, "right" for a rightToLeft row,
        # when the container's gravity does not name that axis; else nil.
        def direction_start_edge
          return nil unless container_content_node?

          direction = JsonUIShared::EnumSpelling.lowered(@component['direction'], 'View', 'direction')
          orientation = JsonUIShared::EnumSpelling.lowered(@component['orientation'], 'View', 'orientation')
          gravity = @component['gravity']
          words = (gravity.is_a?(Array) ? gravity : gravity.to_s.split('|')).map { |g| g.to_s.strip.downcase }
          if direction == 'bottomtotop' && orientation == 'vertical'
            (words & %w[top bottom center centervertical center_vertical]).empty? ? 'bottom' : nil
          elsif direction == 'righttoleft' && orientation == 'horizontal'
            (words & %w[left right start end center centerhorizontal center_horizontal]).empty? ? 'right' : nil
          end
        end

        def label_node?
          JsonUIShared::TypeSynonyms.drawn_type(@component['type']) == 'Label'
        end

        # A Label's vertical text position in a box taller than the text: the
        # vertical its gravity names (top, bottom, centerVertical / center),
        # else centre — the canon's leafOwnFrameChannel default for "a text
        # block smaller than its fixed box", as the web draws an omitted
        # gravity. Until jsonui-cli 1.9.0 this depended on the frame's shape:
        # a matchParent- or wrapContent-wide Label of height 44 was centred
        # whatever its gravity (`top` and `bottom` did nothing), a 200 × 44 one
        # put `left` / `right` at the top, and a matchParent × matchParent or
        # min-height one with no gravity at the top (ConformanceHost, iOS 26.5).
        def label_vertical
          label_vertical_named || 'center'
        end

        # Where a Label's text sits across its frame: textAlign's position,
        # else the horizontal its gravity names (left / right /
        # centerHorizontal, center), else the start - 'leading', 'center' or
        # 'trailing' (the SSoT's Label.textAlign, 4f ruling 2026-09-27). A
        # bound textAlign is textAlign's (its value is not known here: the
        # start). Until jsonui-cli 1.9.0 a Label's gravity did not place its
        # text across a frame wider than it, and one with neither sat in the
        # middle of a fixed width.
        def label_horizontal
          text_align = @component['textAlign']
          if text_align
            return case JsonUIShared::EnumSpelling.lowered(text_align, @component['type'], 'textAlign')
                   when 'center' then 'center'
                   when 'right', 'trailing' then 'trailing'
                   else 'leading'
                   end
          end

          gravity = @component['gravity']
          return 'leading' if gravity.nil?

          parts = gravity.is_a?(Array) ? gravity.map(&:to_s) : gravity.to_s.split('|')
          named = parts.map { |g| JsonUIShared::EnumSpelling.lowered(g.strip, 'common', 'gravity') }.compact
          # center / centerHorizontal first, then right, then left - the
          # order rjui's TailwindMapper.map_label_gravity reads them in.
          return 'center' if (named & %w[center centerhorizontal center_horizontal]).any?
          return 'trailing' if (named & %w[right end]).any?

          'leading'
        end

        # The vertical a Label's gravity names — 'top', 'bottom', 'center'
        # (centerVertical / center) — or nil.
        def label_vertical_named
          gravity = @component['gravity']
          return nil if gravity.nil?

          parts = gravity.is_a?(Array) ? gravity.map(&:to_s) : gravity.to_s.split('|')
          named = parts.map { |g| JsonUIShared::EnumSpelling.lowered(g.strip, 'common', 'gravity') }.compact
          return 'top' if named.include?('top')
          return 'bottom' if named.include?('bottom')
          return 'center' if (named & %w[center centervertical center_vertical]).any?

          nil
        end

        # The alignment a height-only frame of a Label carries: `.top` /
        # `.bottom`, or nil for centre (SwiftUI's default). Its horizontal half
        # is the frame's own width, so it does not move the text sideways.
        def label_vertical_alignment
          case label_vertical
          when 'top' then '.top'
          when 'bottom' then '.bottom'
          end
        end

        # A leaf that is not a Label: the axis its gravity does not name stays
        # centred (gravity_to_frame_alignment). A Label is not in this rule —
        # its text has its own channel (label_frame_alignment, textAlign), and
        # where this method's caller reaches it (a frame of both sizes) it
        # keeps what it drew.
        def centred_cross_axis?
          return false if container_content_node?

          JsonUIShared::TypeSynonyms.drawn_type(@component['type']) != 'Label'
        end

        # True for a node whose content the codegen itself lays out — the
        # nodes the gravityDefaults canon means by "container". A childless
        # node's own-frame alignment is its content channel (fit bitmap,
        # custom-component internals), which is not this ruling's subject.
        # A wrapContent container stops at its parent's size (SwiftJsonUI
        # WrapCap, 10.29.6; user ruling 2026-10-05, attribute_semantics
        # wrapContentCap). After any fixedSize, as Dynamic applies it. Not an
        # axis a max bounds, nor one a weight gives the node.
        def apply_wrap_cap
          return unless container_content_node?

          wrap = ->(v) { v.nil? || %w[wrapcontent wrap_content].include?(v.to_s.downcase) }
          weighted = @component['weight']
          cap_w = wrap.call(@component['width']) && !@component['maxWidth'] && !(weighted || @component['widthWeight'])
          cap_h = wrap.call(@component['height']) && !@component['maxHeight'] && !(weighted || @component['heightWeight'])
          return unless cap_w || cap_h

          @modifier_bag.append(:fixed_size, ".wrapCap(width: #{cap_w}, height: #{cap_h})")
        end

        def container_content_node?
          # A Collection lays out its cells, not `child`: it is a container
          # (4f ruling 2026-09-27). Its frame fell to SwiftUI's `.center`, so
          # a `lazy: none` column narrower than a matchParent Collection stood
          # in the middle, and a bounded one in the middle of its height too,
          # where the lazy route's cells start at the top leading corner.
          return true if JsonUIShared::TypeSynonyms.drawn_type(@component['type']) == 'Collection'

          children = @component['child'] || @component['children']
          children.is_a?(Array) ? children.any? : !children.nil?
        end

        # Label/Text用: textAlignとgravityを組み合わせてframe alignmentを決定
        def label_frame_alignment(both_infinity: false)
          text_align = @component['textAlign']

          # The vertical position: in a frame that sizes the height
          # (`both_infinity`, a min / max height bound) the Label rule —
          # label_vertical; in one that sizes only the width it does not show,
          # and the old `top` spelling is kept so those frames' text does not
          # change.
          v = both_infinity ? label_vertical : (label_vertical_named || 'top')

          # 横位置: the Label rule (label_horizontal)
          h = label_horizontal

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
        # A bound dimension as the Swift operand a frame slot needs.
        #
        # Every caller is a length — `idealWidth`, `minWidth`/`maxWidth`,
        # `minHeight`/`maxHeight`, `width`, `height` — and every one of those
        # slots is a CGFloat. This built `data.<everything between the
        # braces>` with its own regexp instead: the FIFTH copy of the bypass
        # plan 43 replaced for margins and this lane replaced for
        # `extract_binding_property`, `extract_margin_binding_value` and the
        # button text interpolation (kjui's `process_dimension` is the same
        # shape). It carried an inline `?? default` out unbracketed, never
        # unwrapped an Optional, and — the part that stopped the build — never
        # cast, so a `minWidth` declared `Int` emitted
        # `.frame(minWidth: data.w)`.
        #
        # `bound_number` is the canonical answer to all three.
        def extract_binding_value(value)
          return value unless value.is_a?(String)

          bound_number(value) || value
        end
      end
    end
  end
end
