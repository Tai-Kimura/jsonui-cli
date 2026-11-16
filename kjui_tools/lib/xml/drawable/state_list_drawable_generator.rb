require_relative '../helpers/resource_resolver'

module DrawableGenerator
  class StateListDrawableGenerator
    def generate(json_data, parent_generator)
      return nil unless json_data
      
      @parent_generator = parent_generator
      
      xml = []
      xml << '<?xml version="1.0" encoding="utf-8"?>'
      xml << '<selector xmlns:android="http://schemas.android.com/apk/res/android">'
      
      # Order matters in state list - most specific states first
      
      # Disabled state
      if json_data['disabledBackground'] || json_data['disabledColor']
        generate_state_item(xml, 
          state: 'disabled',
          background: json_data['disabledBackground'],
          color: json_data['disabledColor'],
          original_data: json_data
        )
      end
      
      # Pressed/Tap state
      if json_data['tapBackground'] || json_data['pressedBackground'] || json_data['tapColor']
        generate_state_item(xml,
          state: 'pressed',
          background: json_data['tapBackground'] || json_data['pressedBackground'],
          color: json_data['tapColor'],
          original_data: json_data
        )
      end
      
      # Selected state
      if json_data['selectedBackground'] || json_data['selectedColor']
        generate_state_item(xml,
          state: 'selected',
          background: json_data['selectedBackground'],
          color: json_data['selectedColor'],
          original_data: json_data
        )
      end
      
      # Focused state
      if json_data['focusedBackground'] || json_data['focusedColor']
        generate_state_item(xml,
          state: 'focused',
          background: json_data['focusedBackground'],
          color: json_data['focusedColor'],
          original_data: json_data
        )
      end
      
      # Checked state (for checkboxes, radio buttons, switches)
      if json_data['checkedBackground'] || json_data['checkedColor']
        generate_state_item(xml,
          state: 'checked',
          background: json_data['checkedBackground'],
          color: json_data['checkedColor'],
          original_data: json_data
        )
      end
      
      # Default state (always last)
      generate_default_state(xml, json_data)
      
      xml << '</selector>'
      xml.join("\n")
    end
    
    private
    
    def generate_state_item(xml, state:, background:, color:, original_data:)
      return unless background || color
      
      # Build state attributes
      state_attrs = build_state_attributes(state)
      
      xml << "    <item #{state_attrs}>"
      
      if background
        if needs_shape?(background, original_data)
          # Generate a shape drawable for this state
          generate_state_shape(xml, background, original_data)
        else
          # Simple color
          color_value = parse_color(background)
          xml << "        <color android:color=\"#{color_value}\" />"
        end
      elsif color
        # Text color selector item
        color_value = parse_color(color)
        xml << "        <color android:color=\"#{color_value}\" />"
      end
      
      xml << '    </item>'
    end
    
    def generate_default_state(xml, json_data)
      xml << '    <item>'
      
      if json_data['background'] || json_data['cornerRadius'] || json_data['borderWidth']
        if needs_shape?(json_data['background'], json_data)
          generate_state_shape(xml, json_data['background'], json_data)
        else
          # Simple color background
          color = parse_color(json_data['background'] || '#FFFFFF')
          xml << "        <color android:color=\"#{color}\" />"
        end
      else
        # Transparent default
        xml << '        <color android:color="@android:color/transparent" />'
      end
      
      xml << '    </item>'
    end
    
    def generate_state_shape(xml, background, original_data)
      xml << '        <shape android:shape="rectangle">'
      
      # Corner radius from original data
      if original_data['cornerRadius']
        radius = parse_dimension(original_data['cornerRadius'])
        xml << "            <corners android:radius=\"#{radius}\" />"
      end
      
      # Background color or gradient
      if background.is_a?(Hash) && background['gradient']
        generate_gradient(xml, background['gradient'])
      elsif background
        color = parse_color(background)
        xml << "            <solid android:color=\"#{color}\" />"
      end
      
      # Border from original data (consistent across states)
      if original_data['borderWidth'] && original_data['borderColor']
        width = parse_dimension(original_data['borderWidth'])
        color = parse_color(original_data['borderColor'])
        xml << '            <stroke'
        xml << "                android:width=\"#{width}\""
        xml << "                android:color=\"#{color}\" />"
      end
      
      xml << '        </shape>'
    end
    
    def generate_gradient(xml, gradient_data)
      return unless gradient_data
      
      gradient_type = gradient_data['type'] || 'linear'
      
      xml << '            <gradient'
      
      case gradient_type.downcase
      when 'linear'
        xml << '                android:type="linear"'
        angle = gradient_data['angle'] || 0
        xml << "                android:angle=\"#{angle}\""
      when 'radial'
        xml << '                android:type="radial"'
        radius = parse_dimension(gradient_data['radius'] || '100dp')
        xml << "                android:gradientRadius=\"#{radius}\""
      when 'sweep'
        xml << '                android:type="sweep"'
      end
      
      # Colors
      if gradient_data['startColor']
        color = parse_color(gradient_data['startColor'])
        xml << "                android:startColor=\"#{color}\""
      end
      
      if gradient_data['centerColor']
        color = parse_color(gradient_data['centerColor'])
        xml << "                android:centerColor=\"#{color}\""
      end
      
      if gradient_data['endColor']
        color = parse_color(gradient_data['endColor'])
        xml << "                android:endColor=\"#{color}\""
      end
      
      xml << ' />'
    end
    
    def build_state_attributes(state)
      case state
      when 'disabled'
        'android:state_enabled="false"'
      when 'pressed'
        'android:state_pressed="true"'
      when 'selected'
        'android:state_selected="true"'
      when 'focused'
        'android:state_focused="true"'
      when 'checked'
        'android:state_checked="true"'
      when 'activated'
        'android:state_activated="true"'
      else
        ''
      end
    end
    
    def needs_shape?(background, original_data)
      return true if original_data['cornerRadius']
      return true if original_data['borderWidth']
      return true if background.is_a?(Hash) && background['gradient']
      false
    end
    
    def parse_dimension(value)
      return '0dp' unless value
      
      value_str = value.to_s
      
      # Already has unit
      return value_str if value_str =~ /\d+(dp|sp|px|dip|pt|in|mm)$/
      
      # Just a number, add dp
      return "#{value_str}dp" if value_str =~ /^\d+$/
      
      value_str
    end
    
    def parse_color(value)
      return '#000000' unless value
      
      value_str = value.to_s
      
      # Already a color reference
      return value_str if value_str.start_with?('@color/', '?attr/')
      
      # Special case for transparent
      return '#00000000' if value_str == 'transparent'
      
      # Use ResourceResolver to check for color resources
      KjuiTools::Xml::Helpers::ResourceResolver.process_color(value_str)
    end
  end
end