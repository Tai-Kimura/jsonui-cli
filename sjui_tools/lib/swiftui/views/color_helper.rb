module SjuiTools
  module SwiftUI
    module Views
      module ColorHelper
        # Thread-local storage for data definitions during build
        def self.data_definitions
          Thread.current[:sjui_data_definitions] || {}
        end

        def self.data_definitions=(definitions)
          Thread.current[:sjui_data_definitions] = definitions
        end

        # Check if a property has a default value (non-optional)
        def self.has_default_value?(property_name)
          return false unless data_definitions[property_name]
          !data_definitions[property_name]['defaultValue'].nil?
        end

        def size_to_swiftui(size)
          return nil if size.nil?
          
          case size
          when 'matchParent'
            '.infinity'
          when 'wrapContent'
            nil  # SwiftUIのデフォルト動作
          when Integer, Float
            size.to_s
          when String
            if size.match?(/^\d+$/)
              size
            else
              # その他の文字列はそのまま返す（変数名など）
              size
            end
          else
            size.to_s
          end
        end

        def get_swiftui_color(color_value)
          return "Color.clear" if color_value.nil? || color_value.empty?

          # Check if it's a binding expression
          if color_value.is_a?(String) && color_value.start_with?('@{') && color_value.end_with?('}')
            # Extract property name and use data binding
            property_name = color_value[2...-1]
            data_def = ColorHelper.data_definitions[property_name]
            if data_def && data_def['class'].to_s == 'String'
              # String type: resolve color name at runtime
              return "SwiftJsonUIConfiguration.shared.getColor(for: data.#{property_name}) ?? Color.clear"
            end
            # Color type: use directly
            if ColorHelper.has_default_value?(property_name)
              return "data.#{property_name}"
            else
              return "data.#{property_name} ?? Color.clear"
            end
          end

          # SwiftJsonUIConfiguration.shared.getColor(for:) を使用して色を取得
          # これにより、colorProviderが設定されていればそれを使用し、
          # そうでなければhex変換にフォールバックする
          "SwiftJsonUIConfiguration.shared.getColor(for: \"#{color_value}\") ?? Color.black"
        end
        
        def gradient_direction_to_swiftui(direction)
          # directionプロパティをSwiftUIのグラデーション方向に変換
          case direction
          when 'vertical', 'top_bottom'
            'startPoint: .top, endPoint: .bottom'
          when 'horizontal', 'left_right'
            'startPoint: .leading, endPoint: .trailing'
          when 'bottom_top'
            'startPoint: .bottom, endPoint: .top'
          when 'right_left'
            'startPoint: .trailing, endPoint: .leading'
          when 'topLeft_bottomRight', 'diagonal'
            'startPoint: .topLeading, endPoint: .bottomTrailing'
          when 'topRight_bottomLeft'
            'startPoint: .topTrailing, endPoint: .bottomLeading'
          when 'bottomLeft_topRight'
            'startPoint: .bottomLeading, endPoint: .topTrailing'
          when 'bottomRight_topLeft'
            'startPoint: .bottomTrailing, endPoint: .topLeading'
          else
            'startPoint: .top, endPoint: .bottom'  # デフォルト
          end
        end
      end
    end
  end
end