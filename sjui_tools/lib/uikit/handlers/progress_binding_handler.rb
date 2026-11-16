# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module UIKit
    class ProgressBindingHandler < ViewBindingHandler
      def handle_specific_binding(view_name, key, value)
        case key
        when "progress"
          @binding_content << "        #{view_name}?.progress = Float(#{value})\n"
        when "progressTintColor"
          @binding_content << "        #{view_name}?.progressTintColor = #{value}\n"
        when "trackTintColor"
          @binding_content << "        #{view_name}?.trackTintColor = #{value}\n"
        else
          return false
        end
        true
      end
    end
  end
end
