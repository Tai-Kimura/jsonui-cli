# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module UIKit
    class SliderBindingHandler < ViewBindingHandler
      def handle_specific_binding(view_name, key, value)
        case key
        when "value"
          @binding_content << "        #{view_name}?.value = Float(#{value})\n"
        when "minValue", "minimum"
          @binding_content << "        #{view_name}?.minimumValue = Float(#{value})\n"
        when "maxValue", "maximum"
          @binding_content << "        #{view_name}?.maximumValue = Float(#{value})\n"
        else
          return false
        end
        true
      end
    end
  end
end
