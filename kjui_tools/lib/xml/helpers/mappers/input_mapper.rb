#!/usr/bin/env ruby

module XmlGenerator
  module Mappers
    class InputMapper
      def map_input_attributes(key, value)
        case key
        # Input attributes
        when 'inputType'
          return { namespace: 'android', name: 'inputType', value: map_input_type(value) }
        when 'placeholder'
          return { namespace: 'android', name: 'hint', value: value }
        when 'editable'
          return { namespace: 'android', name: 'editable', value: value.to_s }
        when 'singleLine'
          return { namespace: 'android', name: 'singleLine', value: value.to_s }
        when 'maxLength'
          return { namespace: 'android', name: 'maxLength', value: value.to_s }
          
        # Switch/Checkbox
        when 'checked', 'isChecked'
          return { namespace: 'android', name: 'checked', value: process_checked_value(value) }
          
        # SelectBox/Spinner
        when 'selectedItem'
          return { namespace: 'app', name: 'selectedValue', value: value }
        when 'entries', 'items'
          if value.is_a?(Array)
            return { namespace: 'app', name: 'items', value: value.join('|') }
          else
            return { namespace: 'app', name: 'items', value: value }
          end
        when 'selectItemType'
          return { namespace: 'tools', name: 'selectItemType', value: value }
        when 'hintColor'
          # Process color value through ResourceResolver
          color_value = KjuiTools::Xml::Helpers::ResourceResolver.process_color(value)
          return { namespace: 'app', name: 'hintColor', value: color_value }
        when 'prompt'
          return { namespace: 'app', name: 'placeholder', value: value }
          
        # Date picker attributes
        when 'datePickerMode', 'datePickerStyle'
          return { namespace: 'app', name: 'datePickerMode', value: value }
        when 'dateFormat'
          return { namespace: 'app', name: 'dateFormat', value: value }
        when 'minDate', 'minimumDate'
          return { namespace: 'app', name: 'minDate', value: value }
        when 'maxDate', 'maximumDate'
          return { namespace: 'app', name: 'maxDate', value: value }
          
        # Progress/Slider
        when 'progress'
          return { namespace: 'android', name: 'progress', value: value.to_s }
        when 'max', 'maxValue', 'maximumValue'
          return { namespace: 'android', name: 'max', value: value.to_f.to_i.to_s }
        when 'min', 'minValue', 'minimumValue'
          return { namespace: 'android', name: 'min', value: value.to_f.to_i.to_s }
        when 'value'
          # For Slider, value maps to progress
          return { namespace: 'android', name: 'progress', value: process_binding_value(value) }
        when 'onValueChange'
          return nil # Handled in code generation
          
        # Events (will be handled in binding)
        when 'onClick', 'onclick'
          return { namespace: 'android', name: 'onClick', value: value }
        when 'onTextChanged'
          return nil # Handled in code
        end
        
        nil
      end
      
      private
      
      def map_input_type(value)
        input_type_map = {
          'text' => 'text',
          'number' => 'number',
          'phone' => 'phone',
          'email' => 'textEmailAddress',
          'password' => 'textPassword',
          'multiline' => 'textMultiLine'
        }
        input_type_map[value] || value
      end
      
      def process_checked_value(value)
        if value.is_a?(String) && value.start_with?('@{')
          value
        else
          value.to_s
        end
      end
      
      def process_binding_value(value)
        if value.is_a?(String) && value.start_with?('@{')
          value
        else
          value.to_s
        end
      end
    end
  end
end