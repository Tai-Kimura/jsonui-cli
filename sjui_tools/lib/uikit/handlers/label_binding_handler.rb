# frozen_string_literal: true

require_relative '../view_binding_handler'
require_relative '../../core/tap_accessibility'
require_relative '../../core/enum_spelling'

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
          # The bound value is matched as written, against each spelling
          # Label.textAlign declares: a value is its declared spelling, case
          # and all (1.9.0). Without the definitions, lowercased as before.
          unjudged = JsonUIShared::EnumSpelling.definitions.empty?
          @binding_content << "        switch #{value}#{unjudged ? '.lowercased()' : ''} {\n"
          { 'left' => '.left', 'center' => '.center', 'right' => '.right' }.each do |lowered, alignment|
            spellings = unjudged ? [lowered] : JsonUIShared::EnumSpelling.declared('Label', 'textAlign').select { |s| s.downcase == lowered }
            next if spellings.empty?

            @binding_content << "        case #{spellings.map { |s| "\"#{s}\"" }.join(', ')}: #{view_name}ParagraphStyle.alignment = #{alignment}\n"
          end
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
            # The range's handler (TapAccessibility.range_handler — the rule
            # the UIKit label reads at run time, SwiftJsonUI
            # PartialRangeHandler): onClick first, then onclick, its alias,
            # each a binding or a name. A binding gets its closure here; a
            # name is the selector the label performs. "@{}" names no method:
            # it emitted `handler: )`.
            kind, handler = JsonUIShared::TapAccessibility.range_handler(pa)
            if kind == :binding
              t = handler.sub(/^@\{/, "").sub(/\}$/, "").gsub(/'/, "\"")
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
