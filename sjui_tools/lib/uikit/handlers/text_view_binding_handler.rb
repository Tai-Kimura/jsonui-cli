# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module UIKit
    class TextViewBindingHandler < ViewBindingHandler
      def handle_specific_binding(view_name, key, value)
        case key
        when "enabled"
          @binding_content << "        #{view_name}?.isEditable = #{value}\n"
        when "text"
          @binding_content << "        if !isInitialized {\n"
          @binding_content << "            #{view_name}?.text = #{value}\n"
          @binding_content << "        }\n"
        when "font"
          @binding_content << "        let #{view_name}FontSize = #{view_name}?.font?.pointSize ?? 14.0\n"
          @binding_content << "        #{view_name}?.font = UIFont(name: #{value.gsub("'", "\"")}, size: #{view_name}FontSize)\n"
        when "fontSize"
          @binding_content << "        let #{view_name}FontName = #{view_name}?.font?.fontName ?? \"System\"\n"
          @binding_content << "        #{view_name}?.font = UIFont(name: #{view_name}FontName, size: #{value})\n"
        when "fontColor"
          @binding_content << "        #{view_name}?.textColor = #{value}\n"
        when "hint"
          @binding_content << "        #{view_name}?.hint = #{value}.localized()\n"
        when "hintColor"
          @binding_content << "        #{view_name}?.hintColor = #{value}\n"
          @binding_content << "        #{view_name}?.placeHolder?.textColor = #{value}\n"
        else
          return false
        end
        true
      end
    end
  end
end
