#!/usr/bin/env ruby

require_relative '../resource_resolver'

module XmlGenerator
  module Mappers
    class TextMapper
      def initialize(string_resource_manager = nil)
        @string_resource_manager = string_resource_manager
      end
      
      def map_text_attributes(key, value, component_type)
        case key
        when 'text'
          return { namespace: 'android', name: 'text', value: process_text_value(value) }
        when 'hint'
          hint_value = process_hint_value(value)
          return { namespace: 'android', name: 'hint', value: hint_value }
        when 'fontSize', 'textSize'
          return { namespace: 'android', name: 'textSize', value: convert_text_size(value) }
        when 'fontColor', 'textColor'
          return { namespace: 'android', name: 'textColor', value: convert_color(value) }
        when 'color'
          # Generic color attribute - determine based on component type
          if ['Label', 'Text', 'TextView', 'Button'].include?(component_type)
            return { namespace: 'android', name: 'textColor', value: convert_color(value) }
          else
            return { namespace: 'android', name: 'tint', value: convert_color(value) }
          end
        when 'font'
          # Check if it's a font weight/style or a font file name
          if ['bold', 'italic', 'normal', 'bold_italic'].include?(value.to_s.downcase)
            # It's a text style
            return map_font_weight(value)
          elsif ['Label', 'Text', 'TextView', 'TextField', 'SecureField', 'Button'].include?(component_type)
            # It's a font file name for Kjui views
            # Add .ttf extension if not present
            font_file = value.to_s
            font_file += '.ttf' unless font_file.end_with?('.ttf', '.otf')
            return { namespace: 'app', name: 'kjui_font_name', value: font_file }
          else
            # For non-Kjui views, use as fontFamily
            return { namespace: 'android', name: 'fontFamily', value: value }
          end
        when 'fontFamily'
          # fontFamily is always treated as a font file name
          if ['Label', 'Text', 'TextView', 'TextField', 'SecureField', 'Button'].include?(component_type)
            font_file = value.to_s
            font_file += '.ttf' unless font_file.end_with?('.ttf', '.otf')
            return { namespace: 'app', name: 'kjui_font_name', value: font_file }
          else
            return { namespace: 'android', name: 'fontFamily', value: value }
          end
        when 'fontWeight'
          return map_font_weight(value)
        when 'fontStyle'
          return { namespace: 'android', name: 'textStyle', value: value }
        when 'textAlign', 'textAlignment'
          return { namespace: 'android', name: 'textAlignment', value: map_text_alignment(value) }
        when 'maxLines'
          return { namespace: 'android', name: 'maxLines', value: value.to_s }
        when 'ellipsize'
          return { namespace: 'android', name: 'ellipsize', value: value }
        end
        
        nil
      end
      
      private
      
      def process_hint_value(value)
        # Handle data binding
        if value.is_a?(String) && value.start_with?('@{')
          return value
        end
        
        # Convert value to string
        text = value.to_s
        
        # Use ResourceResolver to check for string resources
        KjuiTools::Xml::Helpers::ResourceResolver.process_text(text)
      end
      
      def process_text_value(value)
        # Handle data binding
        if value.is_a?(String) && value.start_with?('@{')
          return value
        end
        
        # Convert value to string
        text = value.to_s
        
        # Use ResourceResolver to check for string resources
        KjuiTools::Xml::Helpers::ResourceResolver.process_text(text)
      end
      
      def convert_text_size(value)
        case value
        when Integer, Float
          "#{value}sp"
        when String
          if value.match?(/^\d+$/)
            "#{value}sp"
          else
            value
          end
        else
          "14sp"
        end
      end
      
      def convert_color(value)
        return nil if value.nil?
        
        # Handle special color values
        if value.is_a?(String)
          if value == 'clear' || value == 'transparent'
            return '#00000000'
          end
          
          # Use ResourceResolver to check for color resources
          return KjuiTools::Xml::Helpers::ResourceResolver.process_color(value)
        else
          value.to_s
        end
      end
      
      def map_font_weight(value)
        case value.to_s.downcase
        when 'bold'
          { namespace: 'android', name: 'textStyle', value: 'bold' }
        when 'italic'
          { namespace: 'android', name: 'textStyle', value: 'italic' }
        when 'bold_italic', 'bolditalic'
          { namespace: 'android', name: 'textStyle', value: 'bold|italic' }
        when 'normal', 'regular', 'light', 'thin'
          { namespace: 'android', name: 'textStyle', value: 'normal' }
        when 'medium', 'semibold', 'heavy', 'black'
          # Medium and similar weights map to bold in Android
          { namespace: 'android', name: 'textStyle', value: 'bold' }
        else
          # Default to normal for unknown values
          { namespace: 'android', name: 'textStyle', value: 'normal' }
        end
      end
      
      def map_text_alignment(value)
        case value
        when 'left', 'start'
          'textStart'
        when 'right', 'end'
          'textEnd'
        when 'center'
          'center'
        else
          value
        end
      end
    end
  end
end