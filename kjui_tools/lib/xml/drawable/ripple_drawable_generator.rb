require_relative '../helpers/resource_resolver'

module DrawableGenerator
  class RippleDrawableGenerator
    def generate(json_data, component_type)
      return nil unless json_data
      
      xml = []
      xml << '<?xml version="1.0" encoding="utf-8"?>'
      xml << '<ripple xmlns:android="http://schemas.android.com/apk/res/android"'
      
      # Ripple color
      ripple_color = determine_ripple_color(json_data, component_type)
      xml << "    android:color=\"#{ripple_color}\">"
      
      # Content mask and background
      if needs_mask?(json_data, component_type)
        generate_mask_content(xml, json_data)
      else
        generate_background_content(xml, json_data)
      end
      
      xml << '</ripple>'
      xml.join("\n")
    end
    
    private
    
    def determine_ripple_color(json_data, component_type)
      # Check for explicit ripple color
      if json_data['rippleColor']
        return parse_color(json_data['rippleColor'])
      end
      
      # Check for tap background (can be used as ripple hint)
      if json_data['tapBackground']
        return parse_color(json_data['tapBackground'])
      end
      
      # Default ripple colors based on component type
      case component_type
      when 'Button'
        if json_data['background'] && json_data['background'].start_with?('#')
          # Light ripple for dark backgrounds, dark ripple for light
          return is_dark_color?(json_data['background']) ? '#40FFFFFF' : '#40000000'
        end
        return '?attr/colorControlHighlight'
      when 'Card', 'ListItem'
        return '?attr/colorControlHighlight'
      else
        # Default semi-transparent ripple
        return '#20000000'
      end
    end
    
    def needs_mask?(json_data, component_type)
      # Use mask for borderless ripples or specific components
      json_data['rippleBorderless'] == true || 
      component_type == 'ImageButton' ||
      (component_type == 'Button' && !json_data['background'])
    end
    
    def generate_mask_content(xml, json_data)
      xml << '    <item android:id="@android:id/mask">'
      
      if json_data['cornerRadius'] || json_data['shape']
        xml << '        <shape android:shape="rectangle">'
        
        if json_data['cornerRadius']
          radius = parse_dimension(json_data['cornerRadius'])
          xml << "            <corners android:radius=\"#{radius}\" />"
        end
        
        xml << '            <solid android:color="@android:color/white" />'
        xml << '        </shape>'
      else
        xml << '        <color android:color="@android:color/white" />'
      end
      
      xml << '    </item>'
    end
    
    def generate_background_content(xml, json_data)
      # Add background item if specified
      if json_data['background'] || json_data['cornerRadius'] || json_data['borderWidth']
        xml << '    <item>'
        
        if json_data['cornerRadius'] || json_data['borderWidth']
          generate_shape_item(xml, json_data)
        elsif json_data['background']
          if json_data['background'].start_with?('#')
            xml << "        <color android:color=\"#{json_data['background']}\" />"
          elsif json_data['background'].start_with?('@')
            xml << "        <color android:color=\"#{json_data['background']}\" />"
          else
            color = parse_color(json_data['background'])
            xml << "        <color android:color=\"#{color}\" />"
          end
        end
        
        xml << '    </item>'
      end
    end
    
    def generate_shape_item(xml, json_data)
      xml << '        <shape android:shape="rectangle">'
      
      # Corner radius
      if json_data['cornerRadius']
        radius = parse_dimension(json_data['cornerRadius'])
        xml << "            <corners android:radius=\"#{radius}\" />"
      end
      
      # Background color
      if json_data['background']
        color = parse_color(json_data['background'])
        xml << "            <solid android:color=\"#{color}\" />"
      else
        xml << '            <solid android:color="@android:color/transparent" />'
      end
      
      # Border
      if json_data['borderWidth'] && json_data['borderColor']
        width = parse_dimension(json_data['borderWidth'])
        color = parse_color(json_data['borderColor'])
        xml << '            <stroke'
        xml << "                android:width=\"#{width}\""
        xml << "                android:color=\"#{color}\" />"
      end
      
      xml << '        </shape>'
    end
    
    def is_dark_color?(color_str)
      return false unless color_str&.start_with?('#')
      
      # Remove # and parse hex
      hex = color_str[1..]
      
      # Handle different hex formats
      if hex.length == 6
        r = hex[0..1].to_i(16)
        g = hex[2..3].to_i(16)
        b = hex[4..5].to_i(16)
      elsif hex.length == 8
        # Skip alpha
        r = hex[2..3].to_i(16)
        g = hex[4..5].to_i(16)
        b = hex[6..7].to_i(16)
      elsif hex.length == 3
        r = (hex[0] * 2).to_i(16)
        g = (hex[1] * 2).to_i(16)
        b = (hex[2] * 2).to_i(16)
      else
        return false
      end
      
      # Calculate luminance
      luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
      luminance < 0.5
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