# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class CircleImageComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          # CircleImage can be local or network image
          is_network = json_data['url'] || (json_data['source'] && json_data['source'].start_with?('http'))
          
          if is_network
            required_imports&.add(:async_image)
            url = process_data_binding(json_data['url'] || json_data['source'] || json_data['src'] || '')
            
            code = indent("AsyncImage(", depth)
            code += "\n" + indent("model = #{url},", depth + 1)
          else
            # Local image
            image_name = json_data['source'] || json_data['src'] || 'placeholder'
            # Remove file extension and convert to resource name
            resource_name = image_name.gsub('.png', '').gsub('.jpg', '').gsub('-', '_').downcase
            
            code = indent("Image(", depth)
            code += "\n" + indent("painter = painterResource(id = R.drawable.#{Helpers::ResourceResolver.drawable_name(resource_name)}),", depth + 1)
          end
          
          content_description = json_data['contentDescription'] || 'Profile Image'
          code += "\n" + indent("contentDescription = \"#{content_description}\",", depth + 1)
          
          # Content scale - typically Crop for circular images
          required_imports&.add(:content_scale)
          code += "\n" + indent("contentScale = ContentScale.Crop,", depth + 1)
          
          # Build modifiers for circular shape
          modifiers = []

          # Add testTag and contentDescription for UI testing
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))

          # Size (use 'size' attribute or default to 48dp)
          size = json_data['size'] || 48
          modifiers << ".size(#{size}.dp)"
          
          # Circular clip: CircleShape lives in foundation.shape (registered under
          # :circle_shape); :shape only brings RoundedCornerShape + clip helpers.
          required_imports&.add(:shape)
          required_imports&.add(:circle_shape)
          modifiers << ".clip(CircleShape)"
          
          # Border for circle
          if json_data['borderWidth'] && json_data['borderColor']
            required_imports&.add(:border)
            modifiers << ".border(#{json_data['borderWidth']}.dp, Helpers::ResourceResolver.process_color('#{json_data['borderColor']}', required_imports), CircleShape)"
          end
          
          # Background (in case image doesn't load)
          if json_data['background']
            required_imports&.add(:background)
            modifiers << ".background(Helpers::ResourceResolver.process_color('#{json_data['background']}', required_imports))"
          end
          
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))
          modifiers.concat(Helpers::ModifierBuilder.build_alignment(json_data, required_imports, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth)
          
          # Error handling for network images
          if is_network && json_data['errorImage']
            code += ",\n" + indent("error = painterResource(R.drawable.#{Helpers::ResourceResolver.drawable_name(json_data['errorImage'])})", depth + 1)
          end
          
          code += "\n" + indent(")", depth)
          code
        end
        
        private
        
        def self.process_data_binding(text)
          return quote(text) unless text.is_a?(String)

          if (inner = Helpers::BindingExpression.extract_inner(text))
            # Value context (src): canonical parse; a `??` default becomes a
            # real Kotlin elvis on nullable properties (see BindingExpression).
            Helpers::BindingExpression.value_access(inner)
          else
            quote(text)
          end
        end
        
        def self.quote(text)
          "\"#{text.gsub('"', '\\"')}\""
        end
        
        def self.indent(text, level)
          return text if level == 0
          spaces = '    ' * level
          text.split("\n").map { |line| 
            line.empty? ? line : spaces + line 
          }.join("\n")
        end
      end
    end
  end
end