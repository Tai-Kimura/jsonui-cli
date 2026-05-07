# frozen_string_literal: true

require 'json'
require_relative 'style_loader'

module KjuiTools
  module Compose
    # Module for expanding includes inline with ID prefix support
    # Matches SwiftJsonUI's include_expander.rb behavior
    module IncludeExpander
      module_function

      # Convert snake_case to camelCase
      # e.g., "header1_title_label" -> "header1TitleLabel"
      def to_camel_case(str)
        return str unless str.include?('_')
        parts = str.split('_')
        parts[0] + parts[1..].map(&:capitalize).join
      end

      # Combine prefix and name in camelCase
      # e.g., prefix="header1", name="title" -> "header1Title"
      # e.g., prefix="header1", name="title_label" -> "header1TitleLabel"
      def combine_with_prefix(prefix, name)
        return name unless prefix
        # Convert name to camelCase first, then capitalize first letter
        camel_name = to_camel_case(name)
        prefix + camel_name.sub(/^[a-z]/) { |c| c.upcase }
      end

      # Process includes in JSON data, expanding them inline with ID prefixes
      # @param json_data [Hash] The JSON data to process
      # @param base_dir [String] Base directory for resolving include paths
      # @param id_prefix [String, nil] Optional ID prefix to apply
      # @return [Hash] The processed JSON with includes expanded
      def process_includes(json_data, base_dir, id_prefix = nil)
        return json_data unless json_data.is_a?(Hash)

        # includeがある場合、ファイルを読み込んでインライン展開する
        if json_data['include']
          include_file_path = File.join(base_dir, "#{json_data['include']}.json")
          unless File.exist?(include_file_path)
            raise "Include file not found: #{include_file_path}"
          end

          # include先のJSONを読み込む
          include_content = File.read(include_file_path)
          included_json = JSON.parse(include_content)

          # スタイルを適用
          included_json = StyleLoader.load_and_merge(included_json)

          # include元のidをプレフィックスとして使用 (キャメルケースで結合)
          include_id = json_data['id']
          new_prefix = if id_prefix && include_id
                         combine_with_prefix(id_prefix, include_id)
                       elsif include_id
                         to_camel_case(include_id)
                       else
                         id_prefix
                       end

          # include元のプロパティ（id, include以外）をマージ
          # dataやshared_dataもマージ対象
          json_data.each do |key, value|
            next if ['include', 'id'].include?(key)
            if key == 'data' || key == 'shared_data'
              # data/shared_dataはマージ
              included_json[key] ||= []
              included_json[key] = included_json[key] + value if value.is_a?(Array)
            else
              # その他のプロパティは上書き
              included_json[key] = value
            end
          end

          # IDプレフィックスを適用して再帰処理
          json_data = apply_id_prefix(included_json, new_prefix)
          json_data = process_includes(json_data, File.dirname(include_file_path), new_prefix)
          return json_data
        end

        # IDプレフィックスがある場合、現在の要素のidに適用 (キャメルケースで結合)
        if id_prefix && json_data['id']
          json_data['id'] = combine_with_prefix(id_prefix, json_data['id'])
        end

        # childの処理 (childrenもサポート)
        child_key = json_data['child'] ? 'child' : (json_data['children'] ? 'children' : nil)
        if child_key
          if json_data[child_key].is_a?(Array)
            json_data[child_key] = json_data[child_key].map { |child| process_includes(child, base_dir, id_prefix) }
          else
            json_data[child_key] = process_includes(json_data[child_key], base_dir, id_prefix)
          end

          # childrenをchildに正規化 (後の処理で一貫性を保つため)
          if child_key == 'children'
            json_data['child'] = json_data['children']
            json_data.delete('children')
          end
        end

        json_data
      end

      # IDプレフィックスを全要素に適用し、data定義と@{}参照も更新する
      def apply_id_prefix(json_data, prefix)
        return json_data unless json_data.is_a?(Hash) && prefix

        # data定義のnameにプレフィックスを再帰的に付与 (キャメルケースで結合)
        prefix_data_names(json_data, prefix)

        # 全ての文字列値の@{}参照にプレフィックスを付与
        json_data = transform_bindings(json_data, prefix)

        json_data
      end

      # data定義のnameにプレフィックスを再帰的に付与する
      def prefix_data_names(json_data, prefix)
        return unless json_data.is_a?(Hash)

        if json_data['data'].is_a?(Array)
          json_data['data'] = json_data['data'].map do |data_item|
            if data_item.is_a?(Hash) && data_item['name']
              data_item = data_item.dup
              data_item['name'] = combine_with_prefix(prefix, data_item['name'])
            end
            data_item
          end
        end

        # 子要素のdata定義も再帰的に処理
        child_data = json_data['child'] || json_data['children']
        if child_data.is_a?(Array)
          child_data.each { |child| prefix_data_names(child, prefix) }
        elsif child_data.is_a?(Hash)
          prefix_data_names(child_data, prefix)
        end
      end

      # @{}参照にプレフィックスを付与する (キャメルケースで結合)
      def transform_bindings(data, prefix)
        case data
        when Hash
          data.each do |key, value|
            data[key] = transform_bindings(value, prefix)
          end
        when Array
          data.map! { |item| transform_bindings(item, prefix) }
        when String
          # @{variableName} を @{prefixVariableName} に変換 (キャメルケース)
          # ただし @{this.xxx} や @{item.xxx} は変換しない
          data.gsub(/@\{([^}]+)\}/) do |match|
            var_name = $1
            if var_name.include?('.')
              # this.xxx や item.xxx はそのまま
              match
            else
              "@{#{combine_with_prefix(prefix, var_name)}}"
            end
          end
        else
          data
        end
      end
    end
  end
end
