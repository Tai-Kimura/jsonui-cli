# frozen_string_literal: true

require_relative 'base_view_converter'
require_relative '../helpers/font_helper'
require_relative '../helpers/string_manager_helper'
require_relative 'frame_helper'

module SjuiTools
  module SwiftUI
    module Views
      # Generated code label/text converter
      # Dynamic mode equivalent: Sources/SwiftJsonUI/Classes/SwiftUI/Dynamic/Converters/TextConverter.swift
      class LabelConverter < BaseViewConverter
        include SjuiTools::SwiftUI::Helpers::FontHelper
        include SjuiTools::SwiftUI::Helpers::StringManagerHelper
        include SjuiTools::SwiftUI::Views::FrameHelper
        def convert
          # Get text handler for this component
          label_handler = @binding_handler.is_a?(SjuiTools::SwiftUI::Binding::LabelBindingHandler) ?
                          @binding_handler :
                          SjuiTools::SwiftUI::Binding::LabelBindingHandler.new

          # Get text content with binding support
          text_content = get_text_with_string_manager(label_handler.get_text_content(@component))

          # Use PartialAttributedText for all text rendering
          add_line "PartialAttributedText("
          indent do
            add_line "#{text_content},"

            # Add partialAttributes if present
            if @component['partialAttributes'] && @component['partialAttributes'].is_a?(Array) && !@component['partialAttributes'].empty?
              add_line "partialAttributes: ["
              indent do
                @component['partialAttributes'].each_with_index do |partial, index|
                  add_line "PartialAttribute("
                  indent do
                    # Handle range - either array, binding, or string
                    if partial['range']
                      if partial['range'].is_a?(Array) && partial['range'].length == 2
                        add_line "range: #{partial['range'][0]}..<#{partial['range'][1]},"
                      elsif partial['range'].is_a?(String) && is_binding?(partial['range'])
                        prop = extract_binding_property(partial['range'])
                        add_line "textPattern: data.#{prop},"
                      elsif partial['range'].is_a?(String)
                        # Use StringManager for snake_case range text
                        range_text = get_text_with_string_manager("\"#{partial['range']}\"")
                        add_line "textPattern: #{range_text},"
                      end
                    end

                    # Add fontColor
                    if partial['fontColor']
                      color = get_swiftui_color(partial['fontColor'])
                      add_line "fontColor: #{color},"
                    end

                    # Add fontSize
                    if partial['fontSize']
                      add_line "fontSize: #{partial['fontSize']},"
                    end

                    # Add fontWeight
                    if partial['fontWeight']
                      weight = font_weight_to_swiftui(partial['fontWeight'])
                      add_line "fontWeight: #{weight},"
                    end

                    # Add underline
                    if partial['underline']
                      add_line "underline: true,"
                    end

                    # Add strikethrough
                    if partial['strikethrough']
                      add_line "strikethrough: true,"
                    end

                    # Add backgroundColor
                    if partial['background']
                      bg_color = get_swiftui_color(partial['background'])
                      add_line "backgroundColor: #{bg_color},"
                    end

                    # Add onClick as closure (SwiftUI uses onClick, not onclick)
                    if partial['onClick']
                      method_name = extract_binding_property(partial['onClick'])
                      add_line "onClick: { data.#{method_name}?() },"
                    end

                    # Remove trailing comma from last item
                    @generated_code[-1] = @generated_code[-1].chomp(',')
                  end
                  add_line ")#{ index < @component['partialAttributes'].length - 1 ? ',' : '' }"
                end
              end
              add_line "],"
            end

            # Add fontSize
            if @component['fontSize']
              add_line "fontSize: #{@component['fontSize']},"
            end

            # Add fontWeight (handle both fontWeight and font:"bold")
            if @component['fontWeight']
              add_line "fontWeight: \"#{@component['fontWeight']}\","
            elsif @component['font'] == 'bold'
              add_line "fontWeight: \"bold\","
            end

            # Add fontFamily (with binding support)
            if @component['fontFamily']
              if is_binding?(@component['fontFamily'])
                property_name = extract_binding_property(@component['fontFamily'])
                add_line "fontFamily: data.#{property_name},"
              else
                add_line "fontFamily: \"#{@component['fontFamily']}\","
              end
            end

            # Add fontColor (with binding support)
            if @component['enabled'] == false && @component['disabledFontColor']
              color = get_font_color_with_binding(@component['disabledFontColor'])
              add_line "fontColor: #{color},"
            elsif @component['fontColor']
              color = get_font_color_with_binding(@component['fontColor'])
              add_line "fontColor: #{color},"
            end

            # Add highlightColor
            if @component['highlightColor']
              add_line "// highlightColor: #{@component['highlightColor']} - Note: Text highlighting handled via selection in SwiftUI"
            end

            # Add underline
            if @component['underline']
              add_line "underline: true,"
            end

            # Add strikethrough
            if @component['strikethrough']
              add_line "strikethrough: true,"
            end

            # Add lineSpacing
            if @component['lineHeightMultiple']
              line_spacing = (@component['lineHeightMultiple'].to_f - 1) * (@component['fontSize'] || 17).to_i
              add_line "lineSpacing: #{line_spacing},"
            elsif @component['lineSpacing']
              add_line "lineSpacing: #{@component['lineSpacing'].to_f},"
            end

            # Add lineLimit
            if @component['lines']
              lines_value = @component['lines'].to_i
              if lines_value == 0
                add_line "lineLimit: nil,"
              else
                add_line "lineLimit: #{lines_value},"
              end
            elsif @component['autoShrink']
              add_line "lineLimit: 1,"
            end

            # Add textAlignment (default to .leading)
            alignment = @component['textAlign'] ?
                       text_alignment_to_swiftui(@component['textAlign']) :
                       '.leading'
            add_line "textAlignment: #{alignment},"

            # Add linkable if true
            if @component['linkable'] == true || @component['linkable'] == 'true'
              add_line "linkable: true,"
            end

            # Remove trailing comma from last parameter
            @generated_code[-1] = @generated_code[-1].chomp(',')
          end
          add_line ")"

          # lineBreakMode (SwiftJsonUI uses short forms: Char, Clip, Word, Head, Middle, Tail)
          if @component['lineBreakMode']
            mode = case @component['lineBreakMode']
                   when 'Head'
                     '.head'
                   when 'Middle'
                     '.middle'
                   when 'Tail'
                     '.tail'
                   when 'Clip'
                     '.tail'
                   else
                     nil
                   end
            @modifier_bag.append(:component_specific, ".truncationMode(#{mode})") if mode
          end

          # autoShrink & minimumScaleFactor
          if @component['autoShrink']
            scale_factor = @component['minimumScaleFactor'] || 0.5
            @modifier_bag.append(:component_specific, ".minimumScaleFactor(#{scale_factor})")
          elsif @component['minimumScaleFactor']
            @modifier_bag.append(:component_specific, ".minimumScaleFactor(#{@component['minimumScaleFactor']})")
          end

          # edgeInset (Label内部パディング - UIKitに合わせて配列形式対応)
          if @component['edgeInset']
            edge_inset = @component['edgeInset']
            if edge_inset.is_a?(Array)
              case edge_inset.length
              when 1
                @modifier_bag.append(:padding, ".padding(#{edge_inset[0].to_i})")
              when 2
                @modifier_bag.append(:padding, ".padding(.vertical, #{edge_inset[0].to_i})")
                @modifier_bag.append(:padding, ".padding(.horizontal, #{edge_inset[1].to_i})")
              when 3
                @modifier_bag.append(:padding, ".padding(.top, #{edge_inset[0].to_i})")
                @modifier_bag.append(:padding, ".padding(.horizontal, #{edge_inset[1].to_i})")
                @modifier_bag.append(:padding, ".padding(.bottom, #{edge_inset[2].to_i})")
              when 4
                @modifier_bag.append(:padding, ".padding(EdgeInsets(top: #{edge_inset[0].to_i}, leading: #{edge_inset[1].to_i}, bottom: #{edge_inset[2].to_i}, trailing: #{edge_inset[3].to_i}))")
              end
            elsif edge_inset.is_a?(String) && edge_inset.include?('|')
              # パイプ区切り形式もサポート (UIKit互換)
              parts = edge_inset.split('|').map(&:to_i)
              case parts.length
              when 1
                @modifier_bag.append(:padding, ".padding(#{parts[0]})")
              when 2
                @modifier_bag.append(:padding, ".padding(.vertical, #{parts[0]})")
                @modifier_bag.append(:padding, ".padding(.horizontal, #{parts[1]})")
              when 3
                @modifier_bag.append(:padding, ".padding(.top, #{parts[0]})")
                @modifier_bag.append(:padding, ".padding(.horizontal, #{parts[1]})")
                @modifier_bag.append(:padding, ".padding(.bottom, #{parts[2]})")
              when 4
                @modifier_bag.append(:padding, ".padding(EdgeInsets(top: #{parts[0]}, leading: #{parts[1]}, bottom: #{parts[2]}, trailing: #{parts[3]}))")
              end
            else
              @modifier_bag.append(:padding, ".padding(#{edge_inset.to_i})")
            end
          end

          # Apply frame modifiers for weighted views FIRST
          # If this label has a weight in a horizontal/vertical container, make it fill the appropriate dimension
          @skip_frame_width = false
          if @component['weight'] && @component['weight'].to_f > 0
            parent_orientation = @component['parent_orientation']

            if parent_orientation == 'horizontal'
              # In horizontal stack with weight - fill width
              # Add alignment based on textAlign
              frame_alignment = case @component['textAlign'].to_s.downcase
              when 'center'
                '.center'
              when 'right', 'trailing'
                '.trailing'
              else
                '.leading'
              end
              @modifier_bag.append(:frame_size, ".frame(maxWidth: .infinity, alignment: #{frame_alignment})")
              @skip_frame_width = true  # Prevent frame_helper from adding duplicate maxWidth
            elsif parent_orientation == 'vertical'
              # In vertical stack with weight - fill height
              @modifier_bag.append(:frame_size, ".frame(maxHeight: .infinity)")
            end
          end

          # Apply padding (internal spacing) first
          apply_padding

          # Apply frame size (width/height) after padding -- skip width if already set by weight
          apply_frame_size

          # Apply frame constraints (minWidth, maxWidth, minHeight, maxHeight)
          apply_frame_constraints

          # Apply background and corner radius AFTER padding
          # This ensures the background includes the padding area
          if @component['background']
            color = get_swiftui_color(@component['background'])
            @modifier_bag.register(:background, ".background(#{color})")
          end

          if @component['cornerRadius']
            @modifier_bag.register(:corner_radius, ".cornerRadius(#{@component['cornerRadius'].to_i})")
          end

          # ボーダー（cornerRadiusの直後、marginsの前に適用）
          if @component['borderWidth'] && @component['borderColor']
            border_color_value = @component['borderColor']
            unless border_color_value.is_a?(String) && border_color_value.start_with?('@{')
              color = get_swiftui_color(border_color_value)
              border_code = build_border_overlay(color, (@component['cornerRadius'] || 0).to_i, @component['borderWidth'].to_i)
              @modifier_bag.register(:border, border_code)
            end
          end

          # Apply binding-specific modifiers (borderColor, fontColor, etc.)
          # Must be BEFORE margins so borders don't include margin area
          apply_binding_modifiers

          # Apply margins (external spacing)
          apply_margins

          # Opacity (alpha/opacity)
          alpha_value = attr_with_alias('opacity', 'alpha')
          if alpha_value
            if is_binding?(alpha_value)
              @modifier_bag.register(:opacity, ".opacity(#{binding_data_expr(alpha_value)})")
            else
              @modifier_bag.register(:opacity, ".opacity(#{alpha_value})")
            end
          end

          # Hidden
          hidden_value = @component['hidden']
          if hidden_value == true
            @modifier_bag.register(:hidden, ".hidden()")
          elsif is_binding?(hidden_value)
            @modifier_bag.register(:hidden, ".opacity(#{binding_data_expr(hidden_value)} ? 0 : 1)")
          end

          # onClick
          if @component['onClick'] && is_binding?(@component['onClick']) && @component['enabled'] != false
            on_click_lines = build_on_click_lines(@component['onClick'])
            @modifier_bag.register(:on_click, on_click_lines)
          end

          generated_code
        end

        private

        def text_alignment_to_swiftui(alignment)
          case alignment.downcase
          when 'left', 'leading'
            '.leading'
          when 'right', 'trailing'
            '.trailing'
          when 'center'
            '.center'
          else
            '.leading'
          end
        end

        def font_weight_to_swiftui(weight)
          return '.regular' unless weight
          case weight.downcase
          when 'ultralight'
            '.ultraLight'
          when 'thin'
            '.thin'
          when 'light'
            '.light'
          when 'regular'
            '.regular'
          when 'medium'
            '.medium'
          when 'semibold'
            '.semibold'
          when 'bold'
            '.bold'
          when 'heavy'
            '.heavy'
          when 'black'
            '.black'
          else
            '.regular'
          end
        end

        # Get fontColor with binding support
        # Supports both direct color values and @{propertyName} binding expressions
        def get_font_color_with_binding(font_color)
          return nil unless font_color

          if is_binding?(font_color)
            # Binding expression - get color from data
            property_name = extract_binding_property(font_color)
            data_def = ColorHelper.data_definitions[property_name]
            if data_def && data_def['class'].to_s == 'String'
              # String type: resolve via configuration (no cast needed)
              "SwiftJsonUIConfiguration.shared.getColor(for: data.#{property_name})"
            else
              # Color type: use directly
              "data.#{property_name}"
            end
          else
            # Direct color value
            get_swiftui_color(font_color)
          end
        end
      end
    end
  end
end
