#!/usr/bin/env ruby

require_relative 'data_binding_helper'

module XmlGenerator
  class LayoutAttributeProcessor
    def initialize(attribute_mapper)
      @attribute_mapper = attribute_mapper
    end
    
    # Process layout dimensions with weight support
    def process_dimensions(json_element, is_root, parent_orientation)
      attrs = {}
      
      has_weight = json_element['weight']
      
      # Default dimensions
      default_width = 'wrap_content'
      default_height = 'wrap_content'
      
      # If root element, default to match_parent
      if is_root
        default_width = 'match_parent'
        default_height = 'match_parent'
      # If weight is specified, set the dimension in the orientation direction to 0dp
      elsif has_weight && parent_orientation
        if parent_orientation == 'horizontal'
          default_width = '0dp' if !json_element['width']
        elsif parent_orientation == 'vertical'
          default_height = '0dp' if !json_element['height']
        end
      end
      
      attrs['android:layout_width'] = @attribute_mapper.map_dimension(
        json_element['width'] || default_width
      )
      attrs['android:layout_height'] = @attribute_mapper.map_dimension(
        json_element['height'] || default_height
      )
      
      attrs
    end
    
    # Process all attributes with gravity combination support
    def process_attributes(json_element, parent_type)
      attrs = {}
      gravity_values = []
      constraint_extras = []
      has_constraint_specified = false
      
      # Check if parent is ConstraintLayout
      is_constraint_layout = parent_type&.include?('ConstraintLayout')
      
      # Track which constraints have been set
      constraint_flags = {
        horizontal: false,
        vertical: false
      }
      
      # Map all attributes
      json_element.each do |key, value|
        next if ['type', 'child', 'children', 'id', 'width', 'height', 'style', 'data', 'orientation'].include?(key)
        
        android_attr = @attribute_mapper.map_attribute(key, value, json_element['type'], parent_type, json_element)
        if android_attr
          namespace, attr_name = android_attr[:namespace], android_attr[:name]
          attr_value = android_attr[:value]
          extra = android_attr[:extra]
          
          # Handle data binding
          if attr_value.is_a?(String) && attr_value.start_with?('@{')
            attr_value = DataBindingHelper.process_data_binding(attr_value)
          end
          
          # Track if constraint attributes are being set
          if is_constraint_layout && namespace == 'app'
            if attr_name.include?('constraint')
              has_constraint_specified = true
              # Track horizontal constraints
              if attr_name.include?('Start') || attr_name.include?('End') || attr_name.include?('Left') || attr_name.include?('Right')
                constraint_flags[:horizontal] = true
              end
              # Track vertical constraints
              if attr_name.include?('Top') || attr_name.include?('Bottom')
                constraint_flags[:vertical] = true
              end
            end
          end
          
          # Check for alignment attributes that map to constraints
          if is_constraint_layout && ['alignLeft', 'alignRight', 'alignTop', 'alignBottom', 'alignCenterHorizontal', 'alignCenterVertical', 'alignCenterInParent'].include?(key)
            has_constraint_specified = true
            if key == 'alignLeft' || key == 'alignRight' || key == 'alignCenterHorizontal'
              constraint_flags[:horizontal] = true
            end
            if key == 'alignTop' || key == 'alignBottom' || key == 'alignCenterVertical'
              constraint_flags[:vertical] = true
            end
            if key == 'alignCenterInParent'
              constraint_flags[:horizontal] = true
              constraint_flags[:vertical] = true
            end
          end
          
          # Collect gravity values to combine them
          if attr_name == 'layout_gravity' && parent_type == 'LinearLayout'
            gravity_values << attr_value if value
          elsif extra && is_constraint_layout
            # Handle special ConstraintLayout cases that need multiple attributes
            constraint_extras << { key: key, value: value, extra: extra }
            # Still add the primary attribute
            if namespace == 'android'
              attrs["android:#{attr_name}"] = attr_value
            elsif namespace == 'app'
              attrs["app:#{attr_name}"] = attr_value
            end
          else
            if namespace == 'android'
              attrs["android:#{attr_name}"] = attr_value
            elsif namespace == 'app'
              attrs["app:#{attr_name}"] = attr_value
            elsif namespace == 'tools'
              attrs["tools:#{attr_name}"] = attr_value
            else
              attrs[attr_name] = attr_value
            end
          end
        end
      end
      
      # Process ConstraintLayout special cases
      if is_constraint_layout && constraint_extras.any?
        constraint_extras.each do |item|
          case item[:extra]
          when 'center_horizontal'
            # Add end constraint for horizontal centering
            attrs['app:layout_constraintEnd_toEndOf'] = 'parent'
          when 'center_vertical'
            # Add bottom constraint for vertical centering
            attrs['app:layout_constraintBottom_toBottomOf'] = 'parent'
          when 'center_in_parent'
            # Add all constraints for centering in parent
            attrs['app:layout_constraintEnd_toEndOf'] = 'parent'
            attrs['app:layout_constraintTop_toTopOf'] = 'parent'
            attrs['app:layout_constraintBottom_toBottomOf'] = 'parent'
          when 'center_vertical_to_view'
            # Add bottom constraint to same view for vertical centering
            attrs['app:layout_constraintBottom_toBottomOf'] = "@id/#{item[:value]}"
          when 'center_horizontal_to_view'
            # Add end constraint to same view for horizontal centering
            attrs['app:layout_constraintEnd_toEndOf'] = "@id/#{item[:value]}"
          end
        end
      end
      
      # Add default constraints for ConstraintLayout if none specified
      if is_constraint_layout
        # Add default horizontal constraint (top-left) if no horizontal constraint specified
        if !constraint_flags[:horizontal]
          attrs['app:layout_constraintStart_toStartOf'] = 'parent'
        end
        
        # Add default vertical constraint (top) if no vertical constraint specified
        if !constraint_flags[:vertical]
          attrs['app:layout_constraintTop_toTopOf'] = 'parent'
        end
      end
      
      # Combine gravity values if there are multiple
      if gravity_values.any?
        attrs['android:layout_gravity'] = gravity_values.join('|')
      end
      
      attrs
    end
    
    # Process LinearLayout orientation
    def process_orientation(view_class, json_element)
      attrs = {}
      
      if view_class == 'LinearLayout' && json_element['orientation']
        attrs['android:orientation'] = json_element['orientation']
      elsif view_class == 'LinearLayout'
        # Default to vertical if not specified
        attrs['android:orientation'] = 'vertical'
      end
      
      attrs
    end
    
  end
end