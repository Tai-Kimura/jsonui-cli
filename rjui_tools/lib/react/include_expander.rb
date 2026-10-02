# frozen_string_literal: true

require 'json'
require_relative 'style_loader'
require_relative '../core/include_data_map'
require_relative '../core/normalization'
require_relative '../core/node_keys'
require_relative '../core/data_item_platform'

module RjuiTools
  module React
    # Expands includes inline with id prefixes — kjui's / sjui's
    # IncludeExpander, the same rule, for the one thing rjui needs an
    # expanded tree for: a screen's Data type. rjui DRAWS an include as a
    # component call (converters/include_converter.rb); its data is what the
    # expanded tree declares, as on native (ruling 2026-10-02; ticket
    # rjui-include-does-not-read-the-screens-data — until jsonui-cli 1.9.6 a
    # screen's Data type carried none of its partials' declarations).
    #
    # Each expanded include's root carries INCLUDE_ROOT, so the Data walk
    # reads its data as it reads a layout root's.
    module IncludeExpander
      INCLUDE_ROOT = '_jui_include_root'

      module_function

      # Whether a node's data[] is this layout's Data type's: a layout's
      # root, an expanded include's root, or a node that holds data alone
      # (its type at most). The one rule the Data type and the include call
      # site both read — the call site hands the partial exactly the names
      # its Data type declares, and a name the type does not have is an
      # excess property to tsc.
      def declares_data?(node, is_root)
        return false unless node.is_a?(Hash) && node['data'].is_a?(Array)

        written = Core::NodeKeys.written(node)
        is_root || node[INCLUDE_ROOT] || written == ['data'] || (written - %w[data type]).empty?
      end

      # The data names an (expanded) layout's Data type declares, in
      # document order, each once.
      def declared_names(tree, is_root = true, names = [])
        case tree
        when Hash
          if declares_data?(tree, is_root)
            tree['data'].each do |item|
              next unless item.is_a?(Hash) && item['name']
              next unless JsonUIShared::DataItemPlatform.applies?(item, 'react')

              names << item['name'] unless names.include?(item['name'])
            end
          end
          child = tree['child'] || tree['children']
          (child.is_a?(Array) ? child : [child].compact).each { |c| declared_names(c, false, names) }
        when Array
          tree.each { |c| declared_names(c, false, names) }
        end
        names
      end

      # The layouts ROOT every include path resolves from — top level and
      # nested alike (design U8, 2026-09-25). The Python normalizer, rjui and
      # both dynamic runtimes read include paths from the root, and the
      # layouts measured on the consumer faces are written that way (all 3
      # nested references resolve from the root, none from the including
      # file's directory — which this expander used, so a screen or partial in
      # a subdirectory failed with "Include file not found"). Set by the
      # entry points that know the root; unset, a path resolves from
      # base_dir as before.
      class << self
        attr_accessor :layouts_root
      end

      # Convert snake_case to camelCase
      # e.g., "header1_title_label" -> "header1TitleLabel"
      SIMPLE_BINDING = /@\{([A-Za-z_][A-Za-z0-9_]*)\}/.freeze

      # Every plain `@{name}` the layout binds, in document order, each once
      # — a dotted name (`@{item.x}`, `@{this.x}`) is not one. Declarations
      # are not bindings.
      def bound_names(node, names = [])
        case node
        when Hash
          node.each do |key, value|
            next if key == 'data' && value.is_a?(Array)

            bound_names(value, names)
          end
        when Array
          node.each { |item| bound_names(item, names) }
        when String
          node.scan(SIMPLE_BINDING) { |(name)| names << name unless names.include?(name) }
        end
        names
      end

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
      # @param layouts_root [String, nil] The root include paths resolve from
      # @return [Hash] The processed JSON with includes expanded
      def process_includes(json_data, base_dir, id_prefix = nil, layouts_root = IncludeExpander.layouts_root)
        return json_data unless json_data.is_a?(Hash)

        # includeがある場合、ファイルを読み込んでインライン展開する
        if json_data['include']
          include_node = json_data
          include_file_path = File.join(layouts_root || base_dir, "#{json_data['include']}.json")
          unless File.exist?(include_file_path)
            raise "Include file not found: #{include_file_path}"
          end

          # include先のJSONを読み込む
          include_content = File.read(include_file_path)
          included_json = JSON.parse(include_content)

          # A distributed partial may carry its own `$jui` normalization
          # marker; it is root-level build metadata, not a renderable
          # attribute, so it must not leak into the expanded subtree.
          included_json.delete(Core::Normalization::MARKER_KEY)

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

          included_json[INCLUDE_ROOT] = true

          # IDプレフィックスを適用して再帰処理
          json_data = apply_id_prefix(included_json, new_prefix)
          # The include node's maps over the including layout's data
          # (shared_data, then data — JsonUIShared::IncludeDataMap). Read
          # off the include node as written: its values are bindings in the
          # including layout's scope, not this include's. Until jsonui-cli
          # 1.9.6 an object map was dropped here.
          json_data = JsonUIShared::IncludeDataMap.apply!(
            json_data, JsonUIShared::IncludeDataMap.of(include_node),
            ->(name) { new_prefix ? combine_with_prefix(new_prefix, name) : name }
          )
          json_data = process_includes(json_data, layouts_root || File.dirname(include_file_path),
                                       new_prefix, layouts_root)
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
            json_data[child_key] = json_data[child_key].map { |child| process_includes(child, base_dir, id_prefix, layouts_root) }
          else
            json_data[child_key] = process_includes(json_data[child_key], base_dir, id_prefix, layouts_root)
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
