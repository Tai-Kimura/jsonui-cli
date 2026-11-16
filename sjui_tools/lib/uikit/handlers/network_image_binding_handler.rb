# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module UIKit
    class NetworkImageBindingHandler < ViewBindingHandler
      def handle_specific_binding(view_name, key, value)
        case key
        when "url", "src", "source"
          if optional?(value)
            @binding_content << "        #{view_name}?.setImageURL(string: #{value})\n"
          else
            @binding_content << "        #{view_name}?.setImageURL(string: #{value})\n"
          end
        when "contentMode"
          @binding_content << "        #{view_name}?.contentMode = #{value}\n"
        else
          return false
        end
        true
      end
    end

    # CircleImageも同じ処理なのでエイリアスとして使用
    CircleImageBindingHandler = NetworkImageBindingHandler
  end
end
