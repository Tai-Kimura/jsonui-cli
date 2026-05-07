require_relative 'base_view_converter'

module SjuiTools
  module SwiftUI
    module Views
      class IncludeConverter < BaseViewConverter
      def convert
        # includeプロパティからファイル名を取得
        include_path = @component['include']
        
        unless include_path
          raise "Include component must have 'include' property"
        end
        
        # ファイル名からビュー名を生成
        # included_1 -> Included1View, main_menu -> MainMenuView
        base_name = include_path.split('/').last
        view_name = base_name.split('_').map(&:capitalize).join + 'View'
        
        # shared_dataとdataをマージ
        merged_data = {}

        # shared_dataを先に追加
        if @component['shared_data'] && @component['shared_data'].is_a?(Hash)
          merged_data.merge!(@component['shared_data'])
        end

        # dataで上書き
        if @component['data'] && @component['data'].is_a?(Hash)
          merged_data.merge!(@component['data'])
        end

        # _idPrefix for accessibilityIdentifier in included views
        # If this include has an id, pass it as _idPrefix to child views
        # This allows nested includes to build up a prefix like "parent_child_element"
        include_id = @component['id']
        
        # マージしたデータがある場合
        unless merged_data.empty?
          # @{}参照があるかチェック
          has_reactive_data = merged_data.values.any? { |v| v.is_a?(String) && v.match?(/@\{/) }
          
          if has_reactive_data
            # リアクティブなデータ用 - SwiftUIのビューを再作成させる
            # Dynamic mode support: merge with parent's toDictionary to include handlers
            reactive_keys = extract_reactive_keys(merged_data)
            # Create a combined string for the ID
            id_parts = reactive_keys.map { |key| "\\(data.#{key})" }
            id_expression = id_parts.join("_")
            
            # For Dynamic mode compatibility, merge parent's toDictionary with the specific data overrides
            add_line "#{view_name}(data: {"
            indent do
              add_line "var mergedData = data.toDictionary(viewModel: viewModel)"
              # Add/override specific data values
              merged_data.each do |key, value|
                formatted_value = format_value(value)
                add_line "mergedData[\"#{key}\"] = #{formatted_value}"
              end
              # Add _idPrefix for accessibilityIdentifier in child views
              if include_id
                add_line "// Build _idPrefix: combine parent's prefix with this include's id"
                add_line "if let parentPrefix = mergedData[\"_idPrefix\"] as? String {"
                indent do
                  add_line "mergedData[\"_idPrefix\"] = \"\\(parentPrefix)_#{include_id}\""
                end
                add_line "} else {"
                indent do
                  add_line "mergedData[\"_idPrefix\"] = \"#{include_id}\""
                end
                add_line "}"
              end
              add_line "return mergedData"
            end
            add_line "}())"
            indent do
              add_line ".id(\"#{id_expression}\")"
            end
          else
            # 静的データの場合
            # Add _idPrefix if include has id
            if include_id
              merged_data['_idPrefix'] = include_id
            end
            dict_content = process_data_hash(merged_data)
            add_line "#{view_name}(data: [#{dict_content}])"
          end
        else
          # データがない場合
          if include_id
            add_line "#{view_name}(data: [\"_idPrefix\": \"#{include_id}\"])"
          else
            add_line "#{view_name}()"
          end
        end
        
        # 共通プロパティの適用
        apply_modifiers
        
        generated_code
      end
      
      private
      
      def process_data_hash(hash)
        hash.map { |key, value|
          formatted_value = format_value(value)
          "\"#{key}\": #{formatted_value}"
        }.join(", ")
      end
      
      def extract_reactive_keys(hash)
        keys = []
        hash.each do |_, value|
          if value.is_a?(String) && value.match?(/@\{([^}]+)\}/)
            value.scan(/@\{([^}]+)\}/) do |match|
              var_name = match[0]
              # Remove 'this.' prefix if present
              var_name = var_name.gsub(/^this\./, '')
              keys << var_name unless keys.include?(var_name)
            end
          end
        end
        keys
      end
      
      def format_value(value)
        case value
        when String
          if value.match?(/@\{([^}]+)\}/)
            # @{xxx}形式の場合、変数参照として処理
            value.gsub(/@\{([^}]+)\}/) do |match|
              var_name = $1
              # this.をdata.に変換
              if var_name.start_with?('this.')
                var_name.gsub(/^this\./, 'data.')
              else
                # this.がない場合もdata.を付ける
                "data.#{var_name}"
              end
            end
          else
            # 通常の文字列
            "\"#{value}\""
          end
        when Hash
          # ネストされたHashの処理
          "[#{process_data_hash(value)}]"
        when Array
          # 配列の処理
          "[#{value.map { |v| format_value(v) }.join(", ")}]"
        when Numeric
          value.to_s
        when TrueClass, FalseClass
          value.to_s
        when NilClass
          "nil"
        else
          "\"#{value}\""
        end
      end
      end
    end
  end
end