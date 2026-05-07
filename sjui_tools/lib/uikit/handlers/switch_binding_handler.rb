# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module UIKit
    # SwitchBindingHandler handles UIKit binding for both "Switch" and "Toggle" component types.
    # "Switch" is the primary name, "Toggle" is supported as an alias for backward compatibility.
    class SwitchBindingHandler < ViewBindingHandler
      def handle_specific_binding(view_name, key, value)
        case key
        when "on"
          @binding_content << "        #{view_name}?.isOn = #{value}\n"
        when "enabled"
          @binding_content << "        #{view_name}?.isEnabled = #{value}\n"
        when "tint"
          @binding_content << "        #{view_name}?.onTintColor = #{value}\n"
        when "thumbTintColor"
          @binding_content << "        #{view_name}?.thumbTintColor = #{value}\n"
        when "offTintColor"
          @binding_content << "        #{view_name}?.tintColor = #{value}\n"
        else
          return false
        end
        true
      end
    end
  end
end
