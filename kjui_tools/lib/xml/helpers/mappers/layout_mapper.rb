#!/usr/bin/env ruby

module XmlGenerator
  module Mappers
    class LayoutMapper
      def initialize(dimension_mapper)
        @dimension_mapper = dimension_mapper
      end
      
      def map_layout_attributes(key, value, component_type, parent_type)
        case key
        # Dimension attributes
        when 'width'
          return { namespace: 'android', name: 'layout_width', value: @dimension_mapper.map_dimension(value) }
        when 'height'
          return { namespace: 'android', name: 'layout_height', value: @dimension_mapper.map_dimension(value) }
          
        # Padding attributes
        when 'padding', 'paddings'
          if value.is_a?(Array)
            return { namespace: 'android', name: 'padding', value: @dimension_mapper.convert_dimension(value.first || 0) }
          else
            return { namespace: 'android', name: 'padding', value: @dimension_mapper.convert_dimension(value) }
          end
        when 'topPadding', 'paddingTop'
          return { namespace: 'android', name: 'paddingTop', value: @dimension_mapper.convert_dimension(value) }
        when 'bottomPadding', 'paddingBottom'
          return { namespace: 'android', name: 'paddingBottom', value: @dimension_mapper.convert_dimension(value) }
        when 'leftPadding', 'paddingLeft', 'startPadding', 'paddingStart'
          return { namespace: 'android', name: 'paddingStart', value: @dimension_mapper.convert_dimension(value) }
        when 'rightPadding', 'paddingRight', 'endPadding', 'paddingEnd'
          return { namespace: 'android', name: 'paddingEnd', value: @dimension_mapper.convert_dimension(value) }
          
        # Margin attributes
        when 'margin'
          if value.is_a?(Array)
            return { namespace: 'android', name: 'layout_margin', value: @dimension_mapper.convert_dimension(value.first || 0) }
          else
            return { namespace: 'android', name: 'layout_margin', value: @dimension_mapper.convert_dimension(value) }
          end
        when 'topMargin', 'marginTop'
          return { namespace: 'android', name: 'layout_marginTop', value: @dimension_mapper.convert_dimension(value) }
        when 'bottomMargin', 'marginBottom'
          return { namespace: 'android', name: 'layout_marginBottom', value: @dimension_mapper.convert_dimension(value) }
        when 'leftMargin', 'marginLeft', 'startMargin', 'marginStart'
          return { namespace: 'android', name: 'layout_marginStart', value: @dimension_mapper.convert_dimension(value) }
        when 'rightMargin', 'marginRight', 'endMargin', 'marginEnd'
          return { namespace: 'android', name: 'layout_marginEnd', value: @dimension_mapper.convert_dimension(value) }
          
        # Layout specific
        when 'orientation'
          return { namespace: 'android', name: 'orientation', value: value }
        when 'weight'
          return { namespace: 'android', name: 'layout_weight', value: value.to_s }
        when 'gravity'
          return { namespace: 'android', name: 'gravity', value: map_gravity(value) }
        when 'layout_gravity'
          return { namespace: 'android', name: 'layout_gravity', value: map_gravity(value) }
        end
        
        nil
      end
      
      def map_alignment_attributes(key, value, parent_type)
        # Check if parent is ConstraintLayout
        is_constraint_layout = parent_type&.include?('ConstraintLayout')
        
        case key
        when 'alignTop'
          if parent_type == 'LinearLayout'
            return { namespace: 'android', name: 'layout_gravity', value: 'top' } if value
          elsif is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintTop_toTopOf', value: 'parent' } if value
          else
            return { namespace: 'android', name: 'layout_alignParentTop', value: value.to_s }
          end
        when 'alignBottom'
          if parent_type == 'LinearLayout'
            return { namespace: 'android', name: 'layout_gravity', value: 'bottom' } if value
          elsif is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintBottom_toBottomOf', value: 'parent' } if value
          else
            return { namespace: 'android', name: 'layout_alignParentBottom', value: value.to_s }
          end
        when 'alignLeft', 'alignStart'
          if parent_type == 'LinearLayout'
            return { namespace: 'android', name: 'layout_gravity', value: 'start' } if value
          elsif is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintStart_toStartOf', value: 'parent' } if value
          else
            return { namespace: 'android', name: 'layout_alignParentStart', value: value.to_s }
          end
        when 'alignRight', 'alignEnd'
          if parent_type == 'LinearLayout'
            return { namespace: 'android', name: 'layout_gravity', value: 'end' } if value
          elsif is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintEnd_toEndOf', value: 'parent' } if value
          else
            return { namespace: 'android', name: 'layout_alignParentEnd', value: value.to_s }
          end
        when 'centerHorizontal'
          if parent_type == 'LinearLayout'
            return { namespace: 'android', name: 'layout_gravity', value: 'center_horizontal' } if value
          elsif is_constraint_layout
            # For horizontal centering in ConstraintLayout, we need both start and end constraints
            # This will be handled specially
            return { namespace: 'app', name: 'layout_constraintStart_toStartOf', value: 'parent', extra: 'center_horizontal' } if value
          else
            return { namespace: 'android', name: 'layout_centerHorizontal', value: value.to_s }
          end
        when 'centerVertical'
          if parent_type == 'LinearLayout'
            return { namespace: 'android', name: 'layout_gravity', value: 'center_vertical' } if value
          elsif is_constraint_layout
            # For vertical centering in ConstraintLayout, we need both top and bottom constraints
            return { namespace: 'app', name: 'layout_constraintTop_toTopOf', value: 'parent', extra: 'center_vertical' } if value
          else
            return { namespace: 'android', name: 'layout_centerVertical', value: value.to_s }
          end
        when 'centerInParent'
          if parent_type == 'LinearLayout'
            return { namespace: 'android', name: 'layout_gravity', value: 'center' } if value
          elsif is_constraint_layout
            # For centering in ConstraintLayout, we need all four constraints
            return { namespace: 'app', name: 'layout_constraintStart_toStartOf', value: 'parent', extra: 'center_in_parent' } if value
          else
            return { namespace: 'android', name: 'layout_centerInParent', value: value.to_s }
          end
          
        # Relative positioning - align to edges of another view
        when 'alignTopView'
          if is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintTop_toTopOf', value: "@id/#{value}" }
          else
            return { namespace: 'android', name: 'layout_alignTop', value: "@id/#{value}" }
          end
        when 'alignBottomView'
          if is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintBottom_toBottomOf', value: "@id/#{value}" }
          else
            return { namespace: 'android', name: 'layout_alignBottom', value: "@id/#{value}" }
          end
        when 'alignLeftView'
          if is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintStart_toStartOf', value: "@id/#{value}" }
          else
            return { namespace: 'android', name: 'layout_alignStart', value: "@id/#{value}" }
          end
        when 'alignRightView'
          if is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintEnd_toEndOf', value: "@id/#{value}" }
          else
            return { namespace: 'android', name: 'layout_alignEnd', value: "@id/#{value}" }
          end
          
        # Center alignment with another view (ConstraintLayout only)
        when 'alignCenterVerticalView'
          if is_constraint_layout
            # To center vertically with another view, constrain both top and bottom to that view
            return { namespace: 'app', name: 'layout_constraintTop_toTopOf', value: "@id/#{value}", extra: 'center_vertical_to_view' }
          else
            puts "Warning: alignCenterVerticalView requires ConstraintLayout"
            return nil
          end
        when 'alignCenterHorizontalView'
          if is_constraint_layout
            # To center horizontally with another view, constrain both start and end to that view
            return { namespace: 'app', name: 'layout_constraintStart_toStartOf', value: "@id/#{value}", extra: 'center_horizontal_to_view' }
          else
            puts "Warning: alignCenterHorizontalView requires ConstraintLayout"
            return nil
          end
          
        # Position relative to another view (outside edges)
        when 'alignTopOfView', 'above'
          if is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintBottom_toTopOf', value: "@id/#{value}" }
          else
            return { namespace: 'android', name: 'layout_above', value: "@id/#{value}" }
          end
        when 'alignBottomOfView', 'below'
          if is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintTop_toBottomOf', value: "@id/#{value}" }
          else
            return { namespace: 'android', name: 'layout_below', value: "@id/#{value}" }
          end
        when 'alignLeftOfView', 'toLeftOf'
          if is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintEnd_toStartOf', value: "@id/#{value}" }
          else
            return { namespace: 'android', name: 'layout_toStartOf', value: "@id/#{value}" }
          end
        when 'alignRightOfView', 'toRightOf'
          if is_constraint_layout
            return { namespace: 'app', name: 'layout_constraintStart_toEndOf', value: "@id/#{value}" }
          else
            return { namespace: 'android', name: 'layout_toEndOf', value: "@id/#{value}" }
          end
        end
        
        nil
      end
      
      private
      
      def map_gravity(value)
        if value.is_a?(Array)
          value.join('|')
        else
          case value
          when 'center'
            'center'
          when 'left', 'start'
            'start'
          when 'right', 'end'
            'end'
          when 'top'
            'top'
          when 'bottom'
            'bottom'
          else
            value
          end
        end
      end
    end
  end
end