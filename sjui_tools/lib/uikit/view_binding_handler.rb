# frozen_string_literal: true

module SjuiTools
  module UIKit
    class ViewBindingHandler
      def initialize(binding_content_writer, reset_text_views, reset_constraint_views, data_sets = [])
        @binding_content = binding_content_writer
        @reset_text_views = reset_text_views
        @reset_constraint_views = reset_constraint_views
        @data_sets = data_sets
        @data_info = build_data_info(data_sets)
      end

      # Build a hash of variable name -> optional status
      # Optional if: no defaultValue OR class ends with '?'
      # Non-optional only if: has defaultValue AND class doesn't end with '?'
      def build_data_info(data_sets)
        info = {}
        data_sets.each do |data|
          name = data['name']
          next unless name

          has_default = data.key?('defaultValue') && !data['defaultValue'].nil?
          class_type = data['class'] || data['type'] || ''
          class_ends_optional = class_type.end_with?('?')

          # Optional if:
          # 1. no defaultValue, OR
          # 2. class ends with '?'
          # Non-optional only if:
          # 1. has defaultValue AND class doesn't end with '?'
          is_optional = !has_default || class_ends_optional

          info[name] = { optional: is_optional, class_type: class_type }
        end
        info
      end

      # Check if a variable name is optional
      def optional?(var_name)
        return true unless @data_info.key?(var_name)
        @data_info[var_name][:optional]
      end

      # 共通のバインディング処理
      def handle_common_binding(view_name, key, value)
        case key
        when "canTap"
          @binding_content << "        #{view_name}?.canTap = #{value}\n"
          true
        when "visibility"
          # Check if the bound property is String type - need to convert to SJUIView.Visibility
          prop_name = value.sub(/^self\./, '')
          prop_info = @data_info[prop_name]
          if prop_info && prop_info[:class_type].gsub('?', '') == 'String'
            if prop_info[:optional]
              @binding_content << "        #{view_name}?.visibility = SJUIView.Visibility(rawValue: #{value} ?? \"visible\") ?? .visible\n"
            else
              @binding_content << "        #{view_name}?.visibility = SJUIView.Visibility(rawValue: #{value}) ?? .visible\n"
            end
          else
            @binding_content << "        #{view_name}?.visibility = #{value}\n"
          end
          true
        when "background"
          @binding_content << "        #{view_name}?.setBackgroundColor(color: #{value})\n"
          true
        when "defaultBackground"
          @binding_content << "        #{view_name}?.defaultBackgroundColor = #{value}\n"
          true
        # Note: disabledBackground is only for SJUIButton, handled in ButtonBindingHandler
        when "cornerRadius"
          @binding_content << "        #{view_name}?.layer.cornerRadius = #{value}\n"
          true
        when "borderColor"
          prop_name = value.sub(/^self\./, '')
          if optional?(prop_name)
            @binding_content << "        #{view_name}?.layer.borderColor = #{value}?.cgColor\n"
          else
            @binding_content << "        #{view_name}?.layer.borderColor = #{value}.cgColor\n"
          end
          true
        when "borderWidth"
          @binding_content << "        #{view_name}?.layer.borderWidth = #{value}\n"
          true
        when "borderStyle"
          @binding_content << "        #{view_name}?.updateBorderStyle(#{value})\n"
          true
        when "clipToBounds"
          @binding_content << "        #{view_name}?.clipsToBounds = #{value}\n"
          true
        when "alpha", "opacity"
          @binding_content << "        #{view_name}?.alpha = #{value}\n"
          true
        when "bindingScript"
          @binding_content << "        #{value}\n"
          true
        when "width"
          handle_width_binding(view_name, value)
          true
        when "height"
          handle_height_binding(view_name, value)
          true
        when "topMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.topMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "rightMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.rightMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "bottomMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.bottomMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "leftMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.leftMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "widthWeight"
          @binding_content << "        #{view_name}?.constraintInfo?.widthWeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "heightWeight"
          @binding_content << "        #{view_name}?.constraintInfo?.heightWeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        # サイズWeight系
        when "maxWidthWeight"
          @binding_content << "        #{view_name}?.constraintInfo?.maxWidthWeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "minWidthWeight"
          @binding_content << "        #{view_name}?.constraintInfo?.minWidthWeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "maxHeightWeight"
          @binding_content << "        #{view_name}?.constraintInfo?.maxHeightWeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "minHeightWeight"
          @binding_content << "        #{view_name}?.constraintInfo?.minHeightWeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "weight"
          @binding_content << "        #{view_name}?.constraintInfo?.widthWeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "aspectWidth"
          @binding_content << "        #{view_name}?.constraintInfo?.aspectWidth = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "aspectHeight"
          @binding_content << "        #{view_name}?.constraintInfo?.aspectHeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        # Padding系
        when "paddingTop"
          @binding_content << "        #{view_name}?.constraintInfo?.paddingTop = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "paddingBottom"
          @binding_content << "        #{view_name}?.constraintInfo?.paddingBottom = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "paddingLeft"
          @binding_content << "        #{view_name}?.constraintInfo?.paddingLeft = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "paddingRight"
          @binding_content << "        #{view_name}?.constraintInfo?.paddingRight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "paddingStart"
          @binding_content << "        #{view_name}?.constraintInfo?.paddingStart = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "paddingEnd"
          @binding_content << "        #{view_name}?.constraintInfo?.paddingEnd = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        # Note: innerPadding requires parsing - not supported for dynamic binding
        # Margin系 (RTL対応)
        when "startMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.startMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "endMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.endMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        # min/max Margin系
        when "minTopMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.minTopMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "maxTopMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.maxTopMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "minBottomMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.minBottomMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "maxBottomMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.maxBottomMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "minLeftMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.minLeftMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "maxLeftMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.maxLeftMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "minRightMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.minRightMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "maxRightMargin"
          @binding_content << "        #{view_name}?.constraintInfo?.maxRightMargin = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        # Boolean系レイアウト属性
        when "centerInParent"
          @binding_content << "        #{view_name}?.constraintInfo?.centerVertical = #{value}\n"
          @binding_content << "        #{view_name}?.constraintInfo?.centerHorizontal = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "centerVertical"
          @binding_content << "        #{view_name}?.constraintInfo?.centerVertical = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "centerHorizontal"
          @binding_content << "        #{view_name}?.constraintInfo?.centerHorizontal = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "alignTop"
          @binding_content << "        #{view_name}?.constraintInfo?.alignTop = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "alignBottom"
          @binding_content << "        #{view_name}?.constraintInfo?.alignBottom = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "alignLeft"
          @binding_content << "        #{view_name}?.constraintInfo?.alignLeft = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "alignRight"
          @binding_content << "        #{view_name}?.constraintInfo?.alignRight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        # minWidth/maxWidth/minHeight/maxHeight
        when "minWidth"
          @binding_content << "        #{view_name}?.constraintInfo?.minWidth = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "maxWidth"
          @binding_content << "        #{view_name}?.constraintInfo?.maxWidth = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "minHeight"
          @binding_content << "        #{view_name}?.constraintInfo?.minHeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        when "maxHeight"
          @binding_content << "        #{view_name}?.constraintInfo?.maxHeight = #{value}\n"
          @reset_constraint_views[view_name] = true
          true
        # 色系
        when "tapBackground"
          @binding_content << "        #{view_name}?.tapBackgroundColor = #{value}\n"
          true
        when "highlightBackground"
          @binding_content << "        #{view_name}?.highlightBackgroundColor = #{value}\n"
          true
        when "tintColor"
          @binding_content << "        #{view_name}?.tintColor = #{value}\n"
          true
        # UIView標準属性
        when "userInteractionEnabled"
          @binding_content << "        #{view_name}?.isUserInteractionEnabled = #{value}\n"
          true
        when "tag"
          @binding_content << "        #{view_name}?.tag = #{value}\n"
          true
        # Note: spacing is not a property of UILayoutConstraintInfo - not supported for dynamic binding
        else
          false # 処理されなかった場合
        end
      end

      # 各view typeで実装する必要がある抽象メソッド
      def handle_specific_binding(view_name, key, value)
        # デフォルトは何もしない(未知のview typeでも動作する)
        false
      end

      private

      def handle_width_binding(view_name, value)
        if value == "matchParent"
          @binding_content << "        #{view_name}?.constraintInfo?.width = UILayoutConstraintInfo.LayoutParams.matchParent\n"
        elsif value == "wrapContent"
          @binding_content << "        #{view_name}?.constraintInfo?.width = UILayoutConstraintInfo.LayoutParams.wrapContent\n"
        else
          @binding_content << "        #{view_name}?.constraintInfo?.width = #{value}\n"
        end
        @reset_constraint_views[view_name] = true
      end

      def handle_height_binding(view_name, value)
        if value == "matchParent"
          @binding_content << "        #{view_name}?.constraintInfo?.height = UILayoutConstraintInfo.LayoutParams.matchParent\n"
        elsif value == "wrapContent"
          @binding_content << "        #{view_name}?.constraintInfo?.height = UILayoutConstraintInfo.LayoutParams.wrapContent\n"
        else
          @binding_content << "        #{view_name}?.constraintInfo?.height = #{value}\n"
        end
        @reset_constraint_views[view_name] = true
      end
    end
  end
end
