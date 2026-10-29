require_relative 'responsive_helper'

module SjuiTools
  module SwiftUI
    module Views
      module ChildRenderingHelper
        # 子要素をレンダリングする共通処理
        def render_child_element(child, orientation, index, weight_value = 0, total_weight = 0)
          # ZStackの場合、位置関係の処理
          if !orientation
            # 通常のZStackでの子要素をグループ化
            add_line "Group {"
            # ZStack children receive their individual margins as the
            # .offset apply_zstack_positioning emits (the full-margin
            # frame-context semantics); the child's own .padding for the
            # SAME margins double-applied them (measured: +12pt for a
            # declared 8 in the centered conformance frame — padding
            # half-shift + offset). One mechanism owns the margin.
            child['_zstack_margin_offset'] = true
          end
          
          # Wrap with VisibilityWrapper if visibility is set
          child_converter = apply_visibility_wrapper(child)
          if !child_converter
            # Normal child without visibility wrapper
            render_child_with_alignment(child, orientation)
          end
          
          # Propagate state variables
          if child_converter && child_converter.respond_to?(:state_variables) && child_converter.state_variables
            @state_variables.concat(child_converter.state_variables)
          end
          
          # ZStackの場合、位置調整を適用
          if !orientation
            apply_zstack_positioning(child, index)
            add_line "}"  # Group終了
          end
        end
        
        private
        
        # アライメント処理を含む子要素のレンダリング
        def render_child_with_alignment(child, orientation)
          return render_child_with_responsive_alignment(child, orientation) if orientation && ResponsiveHelper.overrides_any?(child, STACK_ALIGN_KEYS)

          # Handle alignment properties for HStack and VStack
          alignment_info = calculate_alignment_needs(child, orientation)
          needs_wrapper = alignment_info[:needs_wrapper]
          wrapper_alignment = alignment_info[:wrapper_alignment]
          needs_spacer_before = alignment_info[:needs_spacer_before]
          needs_spacer_after = alignment_info[:needs_spacer_after]
          
          # Add spacer before if needed
          if needs_spacer_before
            add_line "Spacer()"
          end
          
          # Generate child code
          child_copy = remove_alignment_properties(child, orientation, needs_wrapper)

          # centerHorizontal/centerVerticalでラップされる場合、子要素内部のSpacerを抑制
          if needs_wrapper
            child_copy['_skip_trailing_spacer'] = true
          end

          child_converter = @converter_factory.create_converter(child_copy, @indent_level + 1, @action_manager, @converter_factory, @view_registry)
          child_code = child_converter.convert
          child_lines = child_code.split("\n")
          
          # Wrap child if needed for alignment
          wrap_child_for_alignment(child_lines, orientation, needs_wrapper, wrapper_alignment)
          
          # Add spacer after if needed
          if needs_spacer_after
            add_line "Spacer()"
          end
          
          # Propagate state variables
          if child_converter.respond_to?(:state_variables) && child_converter.state_variables
            @state_variables.concat(child_converter.state_variables)
          end
        end

        # The keys a stack draws for its child, as Spacers and an alignment wrapper (calculate_alignment_needs).
        STACK_ALIGN_KEYS = %w[alignTop alignBottom alignLeft alignRight centerVertical centerHorizontal centerInParent].freeze

        # Whether a child of this stack takes the free space along the main axis with a Spacer of its own (alignRight,
        # alignLeft or centerHorizontal in a row; alignBottom, alignTop or centerVertical in a column): 'true', 'false'
        # or the size-class condition under which one does. The gravity's packing Spacer stands down then, as flexbox's
        # justify-content does for an auto margin (the web's face of the same keys). Beside it the two split the free
        # space: alignRight drew in the middle of a row, centerHorizontal a third of the way along (ticket
        # sjui-hstack-alignright-centred-by-trailing-spacer).
        def children_take_main_axis_space(children, orientation)
          takes = ->(attrs) do
            info = calculate_alignment_needs(attrs, orientation)
            info[:needs_spacer_before] || info[:needs_spacer_after] ? 'true' : 'false'
          end
          conditions = children.map do |child|
            # A child in a VisibilityWrapper is drawn without its alignment Spacers (apply_visibility_wrapper).
            next 'false' if !child.is_a?(Hash) || ResponsiveHelper.visibility_declared?(child)
            next takes.(child) unless ResponsiveHelper.overrides_any?(child, STACK_ALIGN_KEYS)

            ResponsiveHelper.per_size_class(child) { |attrs| takes.(attrs) }
          end.uniq - ['false']
          return 'true' if conditions.include?('true')

          conditions.empty? ? 'false' : conditions.join(' || ')
        end

        # The gravity's packing Spacer, unless a child takes the main axis's free space (children_take_main_axis_space).
        def add_gravity_spacer(children_take)
          case children_take
          when 'false' then add_line 'Spacer(minLength: 0)'
          when 'true' then nil
          else add_line "if !(#{children_take}) { Spacer(minLength: 0) }"
          end
        end

        # A size class overrides one of STACK_ALIGN_KEYS: the stack draws the Spacers and the wrapper outside the
        # child's function, so each holds under the size classes whose merged attributes ask for it
        # (ResponsiveHelper.per_size_class) — `if <cond> { Spacer() }`, and a wrapper whose frame stretches only
        # then (a frame of nil bounds passes its child's size through). Written only under `responsive`, they drew
        # nothing (ticket sjui-responsive-align-center-overrides-are-not-drawn).
        def render_child_with_responsive_alignment(child, orientation)
          need = ->(key) { ResponsiveHelper.per_size_class(child) { |a| calculate_alignment_needs(a, orientation)[key] ? 'true' : 'false' } }
          spacer = ->(holds) { holds == 'true' ? add_line('Spacer()') : holds != 'false' && add_line("if #{holds} { Spacer() }") }
          wraps = ResponsiveHelper.per_size_class(child) do |a|
            info = calculate_alignment_needs(a, orientation)
            info[:needs_wrapper] && info[:wrapper_alignment] ? 'true' : 'false'
          end
          alignment = ResponsiveHelper.per_size_class(child) { |a| "Alignment#{calculate_alignment_needs(a, orientation)[:wrapper_alignment] || '.center'}" }

          spacer.(need.(:needs_spacer_before))
          child_copy = remove_alignment_properties(child, orientation, true)
          if child_copy['responsive'].is_a?(Hash)
            child_copy['responsive'] = child_copy['responsive'].transform_values do |o|
              o.is_a?(Hash) ? o.reject { |k, _| STACK_ALIGN_KEYS.include?(k) } : o
            end
          end
          child_copy['_skip_trailing_spacer'] = true unless wraps == 'false'

          child_converter = @converter_factory.create_converter(child_copy, @indent_level + 1, @action_manager, @converter_factory, @view_registry)
          child_lines = child_converter.convert.split("\n")
          if wraps == 'false'
            child_lines.each { |line| @generated_code << line }
          else
            axis = orientation == 'horizontal' ? 'Height' : 'Width'
            stretch = wraps == 'true' ? '.infinity' : "(#{wraps} ? CGFloat.infinity : nil)"
            add_line orientation == 'horizontal' ? 'VStack {' : 'HStack {'
            indent { child_lines.each { |line| @generated_code << line unless line.strip.empty? } }
            add_line "}.frame(max#{axis}: #{stretch}, alignment: #{alignment})"
          end
          spacer.(need.(:needs_spacer_after))

          if child_converter.respond_to?(:state_variables) && child_converter.state_variables
            @state_variables.concat(child_converter.state_variables)
          end
        end
      end
    end
  end
end
