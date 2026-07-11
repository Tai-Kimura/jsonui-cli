# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class ImageConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          src = build_src
          alt = attributes['alt'] || attributes['accessibilityLabel'] || ''
          id_attr = build_id_attr
          onclick_attr = build_onclick_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          # Build src attribute
          src_attr = if src.start_with?('`')
                       " src={#{src}}"
                     elsif src.include?('{')
                       " src={#{src.gsub(/[{}]/, '')}}"
                     else
                       " src=\"#{src}\""
                     end

          jsx = "#{indent_str(indent)}<img#{id_attr} className=\"#{class_name}\"#{style_attr}#{src_attr} alt=\"#{alt}\"#{onclick_attr}#{testid_attr}#{tag_attr} />"

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_src
          # Priority: srcName > src > url > defaultImage
          if attributes['srcName']
            if has_binding?(attributes['srcName'])
              binding_prop = extract_binding_property(attributes['srcName'])
              "`/images/${#{binding_prop}}`"
            else
              "/images/#{resolve_image_extension(attributes['srcName'])}"
            end
          elsif attributes['src']
            convert_binding(attributes['src'])
          elsif attributes['url']
            convert_binding(attributes['url'])
          elsif attributes['defaultImage']
            "/images/#{resolve_image_extension(attributes['defaultImage'])}"
          else
            '/images/placeholder.png'
          end
        end

        # Resolve image file extension by checking public/images/ directory
        def resolve_image_extension(name)
          return name if name.include?('.')

          images_dir = File.join(Dir.pwd, 'public', 'images')
          %w[.svg .png .jpg .webp].each do |ext|
            return "#{name}#{ext}" if File.exist?(File.join(images_dir, "#{name}#{ext}"))
          end
          # Fallback to .svg if file not found
          "#{name}.svg"
        end

        def build_class_name
          classes = [super]

          # Content mode (canonical enum: fit/fill/center/top/... plus the
          # iOS long forms — see attribute_definitions Image.contentMode)
          case attributes['contentMode']&.downcase
          when 'fit', 'aspectfit', 'aspect_fit'
            classes << 'object-contain'
          when 'fill', 'aspectfill', 'aspect_fill'
            classes << 'object-cover'
          when 'center'
            classes << 'object-none object-center'
          when 'top'
            classes << 'object-none object-top'
          when 'bottom'
            classes << 'object-none object-bottom'
          when 'left'
            classes << 'object-none object-left'
          when 'right'
            classes << 'object-none object-right'
          when 'scaletofill', 'scale_to_fill'
            classes << 'object-fill'
          else
            classes << 'object-cover'
          end

          # CircleImage type
          if json['type'] == 'CircleImage'
            classes << 'rounded-full'
          end

          # Clickable cursor
          if attributes['canTap'] || attributes['onclick'] || attributes['onClick']
            classes << 'cursor-pointer'
          end

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_style_attr
          super

          # Corner radius (for non-circle images)
          if attributes['cornerRadius'] && json['type'] != 'CircleImage'
            @dynamic_styles['borderRadius'] = "'#{attributes['cornerRadius']}px'"
          end

          return '' if @dynamic_styles.nil? || @dynamic_styles.empty?

          # Delegate per-entry rendering to BaseConverter so the SPREAD
          # sentinel (Configuration.Font.resolve(...) emission) is handled
          # consistently across every converter.
          style_pairs = @dynamic_styles.map do |key, value|
            format_dynamic_style_pair(key, value)
          end

          " style={{ #{style_pairs.join(', ')} }}"
        end

        def build_onclick_attr
          return '' unless attributes['canTap'] || attributes['onclick'] || attributes['onClick']

          onclick = attributes['onclick'] || attributes['onClick']
          return '' unless onclick

          if onclick.end_with?(':')
            # Selector format: "methodName:"
            method_name = onclick.chomp(':')
            " onClick={() => #{method_name}(this)}"
          elsif has_binding?(onclick)
            # Binding format: "@{functionName}"
            handler = extract_binding_property(onclick)
            " onClick={#{handler}}"
          else
            " onClick={#{onclick}}"
          end
        end
      end
    end
  end
end
