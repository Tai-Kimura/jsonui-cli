#!/usr/bin/env ruby

require_relative '../resource_resolver'

module XmlGenerator
  module Mappers
    class StyleMapper
      def initialize(text_mapper, drawable_generator = nil)
        @text_mapper = text_mapper
        @drawable_generator = drawable_generator
      end
      
      def map_style_attributes(key, value, json_element = nil, component_type = nil)
        case key
        # Background and appearance
        when 'background', 'backgroundColor'
          # Check if we need to generate a drawable
          if @drawable_generator && json_element && needs_drawable?(json_element, component_type)
            drawable_name = @drawable_generator.get_background_drawable(json_element, component_type)
            if drawable_name
              return { namespace: 'android', name: 'background', value: "@drawable/#{drawable_name}" }
            end
          end
          return { namespace: 'android', name: 'background', value: KjuiTools::Xml::Helpers::ResourceResolver.process_color(value) }
        when 'cornerRadius'
          # Handled in drawable generation
          return nil if @drawable_generator
          return { namespace: 'tools', name: 'cornerRadius', value: convert_dimension(value) }
        when 'borderWidth', 'strokeWidth'
          # Handled in drawable generation
          return nil if @drawable_generator
          return { namespace: 'tools', name: 'strokeWidth', value: convert_dimension(value) }
        when 'borderColor', 'strokeColor'
          # Handled in drawable generation
          return nil if @drawable_generator
          return { namespace: 'tools', name: 'strokeColor', value: KjuiTools::Xml::Helpers::ResourceResolver.process_color(value) }
        when 'borderStyle'
          # Handled in drawable generation if available
          return nil if @drawable_generator
          return { namespace: 'tools', name: 'borderStyle', value: value }
        when 'opacity', 'alpha'
          return { namespace: 'android', name: 'alpha', value: value.to_f.to_s }
        when 'visibility'
          return { namespace: 'android', name: 'visibility', value: map_visibility(value) }
        when 'enabled'
          return { namespace: 'android', name: 'enabled', value: value.to_s }
        when 'clickable'
          return { namespace: 'android', name: 'clickable', value: value.to_s }
        when 'focusable'
          return { namespace: 'android', name: 'focusable', value: value.to_s }
          
        # Image attributes
        when 'src', 'source', 'image'
          return map_image_source(value, component_type)
        when 'url'
          # For NetworkImageView and CircleImageView
          return { namespace: 'app', name: 'url', value: value }
        when 'placeholderImage'
          # For NetworkImageView placeholder image
          if value.start_with?('@drawable/')
            return { namespace: 'app', name: 'placeholderImage', value: value }
          else
            resource_name = value.gsub(/\.\w+$/, '').downcase.gsub(/[^a-z0-9_]/, '_')
            return { namespace: 'app', name: 'placeholderImage', value: "@drawable/#{resource_name}" }
          end
        when 'placeholder'
          # For NetworkImageView/CircleImageView, use placeholderImage
          if component_type && ['NetworkImage', 'CircleImage'].include?(component_type)
            if value.start_with?('@drawable/')
              return { namespace: 'app', name: 'placeholderImage', value: value }
            else
              resource_name = value.gsub(/\.\w+$/, '').downcase.gsub(/[^a-z0-9_]/, '_')
              return { namespace: 'app', name: 'placeholderImage', value: "@drawable/#{resource_name}" }
            end
          end
          # For other components, let input_mapper handle it as hint
          return nil
        when 'errorImage', 'failureImage'
          # For NetworkImageView error image
          if value.start_with?('@drawable/')
            return { namespace: 'app', name: 'errorImage', value: value }
          else
            resource_name = value.gsub(/\.\w+$/, '').downcase.gsub(/[^a-z0-9_]/, '_')
            return { namespace: 'app', name: 'errorImage', value: "@drawable/#{resource_name}" }
          end
        when 'defaultImage', 'fallbackImage'
          # For NetworkImageView default/fallback image
          if value.start_with?('@drawable/')
            return { namespace: 'app', name: 'defaultImage', value: value }
          else
            resource_name = value.gsub(/\.\w+$/, '').downcase.gsub(/[^a-z0-9_]/, '_')
            return { namespace: 'app', name: 'defaultImage', value: "@drawable/#{resource_name}" }
          end
        when 'crossfadeEnabled', 'crossfade'
          return { namespace: 'app', name: 'crossfadeEnabled', value: value.to_s }
        when 'cacheEnabled'
          return { namespace: 'app', name: 'cacheEnabled', value: value.to_s }
        when 'scaleType'
          return { namespace: 'android', name: 'scaleType', value: map_scale_type(value) }
        when 'tint'
          return { namespace: 'android', name: 'tint', value: KjuiTools::Xml::Helpers::ResourceResolver.process_color(value) }
          
        # Blur attributes
        when 'blurRadius'
          return { namespace: 'app', name: 'blurRadius', value: value.to_f.to_s }
        when 'blurOverlayColor'
          return { namespace: 'app', name: 'blurOverlayColor', value: KjuiTools::Xml::Helpers::ResourceResolver.process_color(value) }
        when 'downsampleFactor'
          return { namespace: 'app', name: 'downsampleFactor', value: value.to_f.to_s }
        when 'blurEnabled'
          return { namespace: 'app', name: 'blurEnabled', value: value.to_s }
          
        # Gradient attributes
        when 'gradientStartColor', 'startColor'
          return { namespace: 'app', name: 'gradientStartColor', value: KjuiTools::Xml::Helpers::ResourceResolver.process_color(value) }
        when 'gradientEndColor', 'endColor'
          return { namespace: 'app', name: 'gradientEndColor', value: KjuiTools::Xml::Helpers::ResourceResolver.process_color(value) }
        when 'gradientCenterColor', 'centerColor'
          return { namespace: 'app', name: 'gradientCenterColor', value: KjuiTools::Xml::Helpers::ResourceResolver.process_color(value) }
        when 'gradientColors', 'colors'
          # Handle array of colors - don't process through ResourceResolver
          # gradientColors expects raw color values separated by |
          if value.is_a?(Array)
            colors_string = value.map { |c| normalize_color_for_gradient(c) }.join('|')
            return { namespace: 'app', name: 'gradientColors', value: colors_string }
          else
            return { namespace: 'app', name: 'gradientColors', value: value }
          end
        when 'gradientDirection', 'direction'
          return { namespace: 'app', name: 'gradientOrientation', value: map_gradient_direction(value) }
        when 'gradientAngle', 'angle'
          return { namespace: 'app', name: 'gradientAngle', value: value.to_s }
        when 'gradientType'
          return { namespace: 'app', name: 'gradientType', value: map_gradient_type(value) }
        when 'gradientRadius'
          return { namespace: 'app', name: 'gradientRadius', value: value.to_f.to_s }
        when 'gradientCenterX'
          return { namespace: 'app', name: 'gradientCenterX', value: value.to_f.to_s }
        when 'gradientCenterY'
          return { namespace: 'app', name: 'gradientCenterY', value: value.to_f.to_s }
          
        # SafeAreaView attributes
        when 'safeAreaInsetPositions', 'insetPositions'
          # Handle array of positions
          if value.is_a?(Array)
            positions_string = value.join('|')
            return { namespace: 'app', name: 'safeAreaInsetPositions', value: positions_string }
          else
            return { namespace: 'app', name: 'safeAreaInsetPositions', value: value }
          end
        when 'contentInsetAdjustmentBehavior'
          return { namespace: 'app', name: 'contentInsetAdjustmentBehavior', value: value.to_s }
        when 'applyTopInset'
          return { namespace: 'app', name: 'applyTopInset', value: value.to_s }
        when 'applyBottomInset'
          return { namespace: 'app', name: 'applyBottomInset', value: value.to_s }
        when 'applyLeftInset'
          return { namespace: 'app', name: 'applyLeftInset', value: value.to_s }
        when 'applyRightInset'
          return { namespace: 'app', name: 'applyRightInset', value: value.to_s }
        when 'applyStartInset'
          return { namespace: 'app', name: 'applyStartInset', value: value.to_s }
        when 'applyEndInset'
          return { namespace: 'app', name: 'applyEndInset', value: value.to_s }
          
        # State-specific attributes (handled by drawable generation)
        when 'disabledBackground', 'tapBackground', 'pressedBackground', 
             'selectedBackground', 'focusedBackground', 'checkedBackground',
             'rippleColor', 'rippleBorderless'
          # These are handled by drawable generation
          return nil if @drawable_generator
          return { namespace: 'tools', name: key, value: value.to_s }
        end
        
        nil
      end
      
      private
      
      def needs_drawable?(json_element, component_type)
        return false unless json_element
        
        # Check if any drawable-related attributes exist
        json_element['cornerRadius'] ||
        json_element['borderWidth'] ||
        json_element['borderColor'] ||
        json_element['gradient'] ||
        json_element['disabledBackground'] ||
        json_element['tapBackground'] ||
        json_element['pressedBackground'] ||
        json_element['selectedBackground'] ||
        json_element['focusedBackground'] ||
        json_element['checkedBackground'] ||
        json_element['onClick'] ||
        json_element['onclick'] ||
        json_element['rippleColor'] ||
        ['Button', 'ImageButton', 'Card', 'ListItem'].include?(component_type)
      end
      
      def convert_dimension(value)
        case value
        when Integer, Float
          "#{value.to_i}dp"
        when String
          if value.match?(/^\d+$/)
            "#{value}dp"
          else
            value
          end
        else
          value.to_s
        end
      end
      
      def map_visibility(value)
        case value
        when true, 'visible'
          'visible'
        when false, 'gone'
          'gone'
        when 'invisible'
          'invisible'
        else
          value
        end
      end
      
      def map_image_source(value, component_type = nil)
        # For NetworkImageView and CircleImageView, map src to url attribute
        if component_type && ['NetworkImage', 'CircleImage'].include?(component_type)
          return { namespace: 'app', name: 'url', value: value }
        end
        
        if value.start_with?('http')
          # Network image - use tools for documentation
          { namespace: 'tools', name: 'src', value: value }
        else
          # Local resource
          resource_name = value.gsub(/\.\w+$/, '').downcase.gsub(/[^a-z0-9_]/, '_')
          { namespace: 'android', name: 'src', value: "@drawable/#{resource_name}" }
        end
      end
      
      def map_scale_type(value)
        scale_type_map = {
          'fill' => 'centerCrop',
          'fit' => 'fitCenter',
          'stretch' => 'fitXY',
          'center' => 'center'
        }
        scale_type_map[value] || value
      end
      
      def map_gradient_direction(value)
        direction_map = {
          'vertical' => 'top_bottom',
          'horizontal' => 'left_right',
          'diagonal' => 'tl_br',
          'diagonal_reverse' => 'tr_bl',
          'topBottom' => 'top_bottom',
          'bottomTop' => 'bottom_top',
          'leftRight' => 'left_right',
          'rightLeft' => 'right_left',
          'rightToLeft' => 'right_left',
          'leftToRight' => 'left_right',
          'topToBottom' => 'top_bottom',
          'bottomToTop' => 'bottom_top',
          'tlBr' => 'tl_br',
          'trBl' => 'tr_bl',
          'blTr' => 'bl_tr',
          'brTl' => 'br_tl'
        }
        direction_map[value] || 'top_bottom'  # Default to top_bottom for unknown values
      end
      
      def map_gradient_type(value)
        type_map = {
          'linear' => 'linear',
          'radial' => 'radial',
          'sweep' => 'sweep',
          'angular' => 'sweep'
        }
        type_map[value] || 'linear'
      end
      
      def normalize_color_for_gradient(color)
        return '#00000000' if color == 'clear' || color == 'transparent'
        
        # Ensure hex format for colors
        if color.match?(/^#?[A-Fa-f0-9]{6,8}$/)
          color.start_with?('#') ? color : "##{color}"
        else
          # Return as-is for named colors or other formats
          color
        end
      end
    end
  end
end