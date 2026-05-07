# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module UIKit
    class LabelBindingHandler < ViewBindingHandler
      def handle_specific_binding(view_name, key, value)
        case key
        when "text"
          @reset_text_views[view_name] = {text: value}
        when "selected"
          @binding_content << "        #{view_name}?.selected = #{value}\n"
        when "font"
          @binding_content << "        let #{view_name}FontSize = (#{view_name}?.attributes[NSAttributedString.Key.font] as? UIFont ?? UIFont.systemFont(ofSize: 14.0)).pointSize\n"
          @binding_content << "        #{view_name}?.attributes[NSAttributedString.Key.font] = UIFont(name: #{value.gsub("'", "\"")}, size: #{view_name}FontSize)\n"
          @reset_text_views[view_name] = {} if @reset_text_views[view_name].nil?
        when "fontSize"
          @binding_content << "        let #{view_name}FontName = (#{view_name}?.attributes[NSAttributedString.Key.font] as? UIFont ?? UIFont.systemFont(ofSize: 14.0)).fontName\n"
          @binding_content << "        #{view_name}?.attributes[NSAttributedString.Key.font] = UIFont(name: #{view_name}FontName, size: #{value})\n"
          @reset_text_views[view_name] = {} if @reset_text_views[view_name].nil?
        when "fontColor"
          @binding_content << "        #{view_name}?.attributes[NSAttributedString.Key.foregroundColor] = #{value}\n"
          @reset_text_views[view_name] = {} if @reset_text_views[view_name].nil?
        when "highlightColor"
          @binding_content << "        #{view_name}?.highlightAttributes?[NSAttributedString.Key.foregroundColor] = #{value}\n"
          @reset_text_views[view_name] = {} if @reset_text_views[view_name].nil?
        when "hintColor"
          @binding_content << "        #{view_name}?.hintAttributes?[NSAttributedString.Key.foregroundColor] = #{value}\n"
          @reset_text_views[view_name] = {} if @reset_text_views[view_name].nil?
        when "lines"
          @binding_content << "        #{view_name}?.numberOfLines = #{value}\n"
        when "lineSpacing"
          @binding_content << "        let #{view_name}ParagraphStyle = (#{view_name}?.attributes[NSAttributedString.Key.paragraphStyle] as? NSMutableParagraphStyle) ?? NSMutableParagraphStyle()\n"
          @binding_content << "        #{view_name}ParagraphStyle.lineSpacing = #{value}\n"
          @binding_content << "        #{view_name}?.attributes[NSAttributedString.Key.paragraphStyle] = #{view_name}ParagraphStyle\n"
          @reset_text_views[view_name] = {} if @reset_text_views[view_name].nil?
        when "lineHeightMultiple"
          @binding_content << "        let #{view_name}ParagraphStyle = (#{view_name}?.attributes[NSAttributedString.Key.paragraphStyle] as? NSMutableParagraphStyle) ?? NSMutableParagraphStyle()\n"
          @binding_content << "        #{view_name}ParagraphStyle.lineHeightMultiple = #{value}\n"
          @binding_content << "        #{view_name}?.attributes[NSAttributedString.Key.paragraphStyle] = #{view_name}ParagraphStyle\n"
          @reset_text_views[view_name] = {} if @reset_text_views[view_name].nil?
        when "minimumScaleFactor"
          @binding_content << "        #{view_name}?.minimumScaleFactor = #{value}\n"
        when "linkable"
          @binding_content << "        #{view_name}?.linkable = #{value}\n"
          @reset_text_views[view_name] = {} if @reset_text_views[view_name].nil?
        when "textAlign"
          @binding_content << "        let #{view_name}ParagraphStyle = (#{view_name}?.attributes[NSAttributedString.Key.paragraphStyle] as? NSMutableParagraphStyle) ?? NSMutableParagraphStyle()\n"
          @binding_content << "        switch #{value}.lowercased() {\n"
          @binding_content << "        case \"left\": #{view_name}ParagraphStyle.alignment = .left\n"
          @binding_content << "        case \"center\": #{view_name}ParagraphStyle.alignment = .center\n"
          @binding_content << "        case \"right\": #{view_name}ParagraphStyle.alignment = .right\n"
          @binding_content << "        default: break\n"
          @binding_content << "        }\n"
          @binding_content << "        #{view_name}?.attributes[NSAttributedString.Key.paragraphStyle] = #{view_name}ParagraphStyle\n"
          @reset_text_views[view_name] = {} if @reset_text_views[view_name].nil?
        when "partialAttributes"
          value.each_with_index do |pa, pa_index|
            if pa["range"].is_a?(Array)
              pa["range"].each_with_index do |r, r_index|
                if r.is_a?(String) && r.start_with?("@{")
                  t = r.sub(/^@\{/, "").sub(/\}$/, "").gsub(/'/, "\"")
                  if t.end_with?("!!")
                    # Force non-optional with !! suffix
                    @binding_content << "        #{view_name}?.partialAttributesJSON?[#{pa_index}][\"range\"][#{r_index}] = JSON(#{t.sub(/!!$/, "")})\n"
                  elsif optional?(t)
                    # Optional variable - use nil coalescing
                    @binding_content << "        #{view_name}?.partialAttributesJSON?[#{pa_index}][\"range\"][#{r_index}] = JSON(#{t} ?? \"\")\n"
                  else
                    # Non-optional variable - no nil coalescing needed
                    @binding_content << "        #{view_name}?.partialAttributesJSON?[#{pa_index}][\"range\"][#{r_index}] = JSON(#{t})\n"
                  end
                end
              end
            end
            # Handle onClick/onclick binding in partialAttributes
            onclick_key = pa.key?("onClick") ? "onClick" : (pa.key?("onclick") ? "onclick" : nil)
            if onclick_key && pa[onclick_key].is_a?(String) && pa[onclick_key].start_with?("@{")
              t = pa[onclick_key].sub(/^@\{/, "").sub(/\}$/, "").gsub(/'/, "\"")
              # Set closure-based onclick handler using setPartialAttributeOnClick
              @binding_content << "        #{view_name}?.setPartialAttributeOnClick(at: #{pa_index}, handler: #{t})\n"
            end
          end
        else
          return false
        end
        true
      end
    end
  end
end
