require_relative '../helpers/resource_resolver'

module DrawableGenerator
  class ShapeDrawableGenerator
    def generate(json_data)
      return nil unless json_data
      
      xml = []
      xml << '<?xml version="1.0" encoding="utf-8"?>'
      
      # Determine if we need a layer-list for gradient + border
      if json_data['gradient'] && json_data['borderWidth']
        generate_layered_shape(xml, json_data)
      else
        generate_simple_shape(xml, json_data)
      end
      
      xml.join("\n")
    end
    
    private
    
    def generate_simple_shape(xml, json_data)
      xml << '<shape xmlns:android="http://schemas.android.com/apk/res/android"'
      xml << '    android:shape="rectangle">'
      
      # Corner radius
      if json_data['cornerRadius']
        radius = parse_dimension(json_data['cornerRadius'])
        xml << "    <corners android:radius=\"#{radius}\" />"
      end
      
      # Background color or gradient
      if json_data['gradient']
        generate_gradient(xml, json_data['gradient'])
      elsif json_data['background']
        color = parse_color(json_data['background'])
        xml << "    <solid android:color=\"#{color}\" />"
      end
      
      # Border
      if json_data['borderWidth'] && json_data['borderColor']
        width = parse_dimension(json_data['borderWidth'])
        color = parse_color(json_data['borderColor'])
        xml << "    <stroke"
        xml << "        android:width=\"#{width}\""
        xml << "        android:color=\"#{color}\" />"
      end
      
      # Padding
      if json_data['padding']
        padding = parse_dimension(json_data['padding'])
        xml << "    <padding"
        xml << "        android:left=\"#{padding}\""
        xml << "        android:top=\"#{padding}\""
        xml << "        android:right=\"#{padding}\""
        xml << "        android:bottom=\"#{padding}\" />"
      elsif json_data['paddingLeft'] || json_data['paddingTop'] || 
            json_data['paddingRight'] || json_data['paddingBottom']
        xml << "    <padding"
        xml << "        android:left=\"#{parse_dimension(json_data['paddingLeft'] || '0dp')}\""
        xml << "        android:top=\"#{parse_dimension(json_data['paddingTop'] || '0dp')}\""
        xml << "        android:right=\"#{parse_dimension(json_data['paddingRight'] || '0dp')}\""
        xml << "        android:bottom=\"#{parse_dimension(json_data['paddingBottom'] || '0dp')}\" />"
      end
      
      xml << '</shape>'
    end
    
    def generate_layered_shape(xml, json_data)
      xml << '<layer-list xmlns:android="http://schemas.android.com/apk/res/android">'
      
      # Background layer with gradient
      xml << '    <item>'
      xml << '        <shape android:shape="rectangle">'
      
      if json_data['cornerRadius']
        radius = parse_dimension(json_data['cornerRadius'])
        xml << "            <corners android:radius=\"#{radius}\" />"
      end
      
      generate_gradient(xml, json_data['gradient'], '            ')
      
      xml << '        </shape>'
      xml << '    </item>'
      
      # Border layer
      if json_data['borderWidth'] && json_data['borderColor']
        xml << '    <item>'
        xml << '        <shape android:shape="rectangle">'
        
        if json_data['cornerRadius']
          radius = parse_dimension(json_data['cornerRadius'])
          xml << "            <corners android:radius=\"#{radius}\" />"
        end
        
        width = parse_dimension(json_data['borderWidth'])
        color = parse_color(json_data['borderColor'])
        xml << "            <stroke"
        xml << "                android:width=\"#{width}\""
        xml << "                android:color=\"#{color}\" />"
        
        xml << '        </shape>'
        xml << '    </item>'
      end
      
      xml << '</layer-list>'
    end
    
    def generate_gradient(xml, gradient_data, indent = '    ')
      return unless gradient_data
      
      # Parse gradient type
      gradient_type = gradient_data['type'] || 'linear'
      
      xml << "#{indent}<gradient"
      
      case gradient_type.downcase
      when 'linear'
        xml << "#{indent}    android:type=\"linear\""
        angle = gradient_data['angle'] || 0
        xml << "#{indent}    android:angle=\"#{angle}\""
      when 'radial'
        xml << "#{indent}    android:type=\"radial\""
        radius = parse_dimension(gradient_data['radius'] || '100dp')
        xml << "#{indent}    android:gradientRadius=\"#{radius}\""
      when 'sweep'
        xml << "#{indent}    android:type=\"sweep\""
      end
      
      # Colors
      if gradient_data['startColor']
        color = parse_color(gradient_data['startColor'])
        xml << "#{indent}    android:startColor=\"#{color}\""
      end
      
      if gradient_data['centerColor']
        color = parse_color(gradient_data['centerColor'])
        xml << "#{indent}    android:centerColor=\"#{color}\""
      end
      
      if gradient_data['endColor']
        color = parse_color(gradient_data['endColor'])
        xml << "#{indent}    android:endColor=\"#{color}\""
      end
      
      # Center position for radial
      if gradient_type.downcase == 'radial'
        centerX = gradient_data['centerX'] || 0.5
        centerY = gradient_data['centerY'] || 0.5
        xml << "#{indent}    android:centerX=\"#{centerX}\""
        xml << "#{indent}    android:centerY=\"#{centerY}\""
      end
      
      xml << " />"
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
      return value_str if value_str.start_with?('@color/')
      
      # Special case for transparent
      return '#00000000' if value_str == 'transparent'
      
      # Use ResourceResolver to check for color resources
      KjuiTools::Xml::Helpers::ResourceResolver.process_color(value_str)
    end
  end
end