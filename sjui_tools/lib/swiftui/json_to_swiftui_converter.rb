# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative 'converter_factory'
require_relative 'scrolling_cell_index'
require_relative 'collection_cell_index'
require_relative 'views/base_view_converter'
require_relative 'views/responsive_helper'
require_relative 'action_manager'
require_relative 'binding/binding_handler_registry'
require_relative 'style_loader'
require_relative 'helpers/string_manager_helper'
require_relative 'include_expander'
require_relative '../core/attribute_validator'
require_relative '../core/layout_validator'
require_relative '../core/normalization'
require_relative 'views/color_helper'

module SjuiTools
  module SwiftUI
    class JsonToSwiftUIConverter
      def initialize
        @indent_level = 0
        @generated_code = []
        @binding_registry = SjuiTools::SwiftUI::Binding::BindingHandlerRegistry.new
        @converter_factory = ConverterFactory.new(@binding_registry)
        @action_manager = ActionManager.new
        @state_variables = []
      end

      def convert_file(json_file_path, output_path = nil)
        unless File.exist?(json_file_path)
          raise "JSON file not found: #{json_file_path}"
        end

        # JSONファイルを読み込み
        json_content = File.read(json_file_path)
        json_data = JSON.parse(json_content)

        # Skip partial files (they are included in other views, not standalone)
        if json_data['partial'] == true
          return nil
        end

        # L1-normalized layouts (`$jui` marker from `jui build`) take the
        # canonical-only attribute lookup path; raw layouts keep the
        # alias-tolerant L0 path. Class-level per-file state, same
        # pattern as validation_enabled.
        Views::BaseViewConverter.layout_normalized = Core::Normalization.canonicalized?(json_data)

        # Which strings.json sections this layout owns — string resolution
        # prefers them over a section that merely holds the same text.
        Helpers::StringManagerHelper.begin_layout(json_file_path)

        # Styleファイルを適用
        json_data = StyleLoader.load_and_merge(json_data)

        # Validate AFTER style merge
        # StyleLoaderがスタイルファイルのtypeを削除するため、
        # マージ後もコンポーネントの元のtypeが保持される
        if Views::BaseViewConverter.validation_enabled?
          validate_json_tree(json_data, File.basename(json_file_path))
          Views::BaseViewConverter.validation_enabled = false
          @validation_was_enabled = true

          # A declaration violation the converters cannot survive: they
          # would receive a String where the declaration promises a list
          # and raise on `.each`. Refuse the layout by name here; the
          # ledger turns it into a non-zero exit and every other layout
          # still generates.
          if blocking_layout_errors?
            begin
              require_relative '../core/stage_failures'
              JsonUI::StageFailures.record(
                'layout',
                "#{json_file_path} was not generated: #{@blocking_layout_reason}"
              )
            rescue LoadError
              nil
            end
            return nil
          end
        end

        # includeを処理
        json_data = process_includes(json_data, File.dirname(json_file_path))
        mark_root_if_scrolling_cell(json_data, json_file_path)
        mark_root_if_collection_cell(json_data, json_file_path)

        # ファイル名からビュー名を生成
        base_name = File.basename(json_file_path, '.json')
        # _プレフィックスを削除
        base_name = base_name.sub(/^_/, '')
        # スネークケースをパスカルケースに変換
        view_name = base_name.split('_').map(&:capitalize).join

        # SwiftUIコードを生成
        swift_code = generate_swiftui_view(view_name, json_data)

        # 出力パスが指定されていない場合は、入力ファイルと同じディレクトリに出力
        if output_path.nil?
          output_path = File.join(File.dirname(json_file_path), "#{view_name}View.swift")
        end

        # ファイルに書き込み
        File.write(output_path, swift_code)
        puts "Generated SwiftUI view: #{output_path}"

        # Restore validation setting
        Views::BaseViewConverter.validation_enabled = true if @validation_was_enabled

        output_path
      end

      # In-tree containers that scroll their content. A Collection is not
      # here: its cells are other layout files, not `child` nodes, so a
      # Collection never has in-tree descendants to mark.
      SCROLLING_ANCESTOR_TYPES = %w[scroll scrollview].freeze
      SCROLLING_ANCESTOR_KEY = Views::BaseViewConverter::SCROLLING_ANCESTOR_KEY
      COLLECTION_CELL_ROOT_KEY = Views::BaseViewConverter::COLLECTION_CELL_ROOT_KEY

      # Mark every node that has a scrolling ancestor in THIS tree. The
      # converters are built one node at a time and see only their own hash,
      # the way `parent_orientation` is handed down by injection; this walks
      # once from the root (after includes are expanded) so a node three
      # levels under a ScrollView knows it as well as a direct child does.
      # What it cannot see: a layout used as a Collection cell — that file is
      # converted on its own, and its root has no ancestor here even though
      # on the device it sits inside a scrolling Collection.
      # Screen ids (ScrollingCellIndex.build) whose layouts render inside a
      # vertically scrolling Collection of ANOTHER layout. Set by `sjui
      # build`, which sees the whole project; a single-file conversion (a
      # spec, `sjui convert`) has none, and converts as before.
      attr_accessor :scrolling_cell_ids

      # Screen ids (CollectionCellIndex.build) whose layouts render as a
      # Collection's cell / header / footer anywhere in the project — ANY
      # Collection, not only a vertically scrolling one: the host wraps every
      # cell with `{collectionId}_item_{index}` regardless of direction.
      attr_accessor :collection_cell_ids

      # The project-wide half of the mark: a layout that is a cell / header /
      # footer of a vertically scrolling Collection is under a scrolling
      # ancestor from its root, though its own tree shows none.
      def mark_root_if_scrolling_cell(json_data, json_file_path)
        return unless json_data.is_a?(Hash) && scrolling_cell_ids

        id = JsonUIShared::ScreenIndex.screen_id_for_path(json_file_path)
        json_data[SCROLLING_ANCESTOR_KEY] = true if scrolling_cell_ids.include?(id)
      end

      # The cell root's own file cannot see that a Collection wraps it.
      # Marks the ROOT only — deliberately NOT propagated, unlike the
      # scrolling mark: what must become an accessibility container is the
      # one node the wrapper's identifier would otherwise be pushed onto.
      def mark_root_if_collection_cell(json_data, json_file_path)
        return unless json_data.is_a?(Hash) && collection_cell_ids

        id = JsonUIShared::ScreenIndex.screen_id_for_path(json_file_path)
        json_data[COLLECTION_CELL_ROOT_KEY] = true if collection_cell_ids.include?(id)
      end

      def mark_scrolling_ancestors(component, inside = false)
        return unless component.is_a?(Hash)
        return if component.key?('data') && !component.key?('type')

        # A root already marked (a cell of a scrolling Collection in another
        # layout) is inside for everything below it.
        inside ||= component[SCROLLING_ANCESTOR_KEY] == true
        component[SCROLLING_ANCESTOR_KEY] = true if inside
        inside ||= SCROLLING_ANCESTOR_TYPES.include?(component['type'].to_s.downcase)
        child_data = component['child'] || component['children']
        children = child_data.is_a?(Array) ? child_data : [child_data]
        children.each { |child| mark_scrolling_ancestors(child, inside) }
      end

      def convert_component(json_data, indent_level = 0)
        @indent_level = indent_level
        mark_scrolling_ancestors(json_data)
        converter = @converter_factory.create_converter(json_data, @indent_level, @action_manager)

        # Skip if converter is nil (e.g., data definition objects)
        return nil unless converter

        @last_root_converter = converter  # Save for weighted_children_info access

        result = converter.convert

        # Collect state variables from converter
        if converter.respond_to?(:state_variables) && converter.state_variables
          @state_variables.concat(converter.state_variables)
        end

        result
      end

      # Simple method to convert JSON file to SwiftUI view code only
      def convert_json_to_view(json_file_path)
        unless File.exist?(json_file_path)
          raise "JSON file not found: #{json_file_path}"
        end

        # Read and parse JSON
        json_content = File.read(json_file_path)
        json_data = JSON.parse(json_content)

        # Per-file normalization state (see convert_file)
        Views::BaseViewConverter.layout_normalized = Core::Normalization.canonicalized?(json_data)
        Helpers::StringManagerHelper.begin_layout(json_file_path)

        # Apply styles
        json_data = StyleLoader.load_and_merge(json_data)

        # Process includes
        json_data = process_includes(json_data, File.dirname(json_file_path))
        mark_root_if_scrolling_cell(json_data, json_file_path)
        mark_root_if_collection_cell(json_data, json_file_path)

        # Convert to SwiftUI code
        @state_variables = []
        @action_manager = ActionManager.new
        @onclick_actions = Set.new

        # Reset responsive state for this file
        @converter_factory.reset_responsive

        # Extract data_properties from JSON and set to converter_factory
        data_properties = extract_data_properties(json_data)
        @converter_factory.data_properties = data_properties

        # Build data_definitions hash for ColorHelper to check optional/non-optional
        data_definitions = {}
        data_properties.each do |prop|
          data_definitions[prop['name']] = prop if prop['name']
        end
        Views::ColorHelper.data_definitions = data_definitions

        # Extract onclick actions from JSON
        extract_onclick_actions(json_data)

        # Check if any component in the tree uses responsive
        has_responsive = Views::ResponsiveHelper.has_responsive_descendant?(json_data)

        # Convert the main component
        view_code = convert_component(json_data, 0)  # Indent level 0, will be indented by view_updater

        # Add @Environment vars if responsive is used
        if has_responsive
          Views::ResponsiveHelper.environment_declarations.each do |decl|
            @state_variables << decl
          end
        end

        # Get root children info for potential body splitting
        root_children = nil
        if @last_root_converter.respond_to?(:weighted_children_info)
          root_children = @last_root_converter.weighted_children_info
        end

        # Collect responsive functions
        responsive_functions = @converter_factory.responsive_functions

        [view_code, @onclick_actions.to_a, @state_variables.uniq, root_children, responsive_functions]
      end

      # Extract data properties from JSON (similar to DataModelUpdater)
      def extract_data_properties(json_data, properties = [])
        if json_data.is_a?(Hash)
          # Check for data section
          if json_data['data'] && json_data['data'].is_a?(Array)
            json_data['data'].each do |data_item|
              if data_item.is_a?(Hash)
                # Platform/mode filter: skip if not matching
                next if data_item['platform'] && data_item['platform'] != 'swift'
                next if data_item['mode'] && data_item['mode'] != 'swiftui'
                properties << data_item
              end
            end
          end

          # Process children
          child_data = json_data['child'] || json_data['children']
          if child_data
            if child_data.is_a?(Array)
              child_data.each do |child|
                extract_data_properties(child, properties)
              end
            else
              extract_data_properties(child_data, properties)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_data_properties(item, properties)
          end
        end

        properties
      end

      def extract_onclick_actions(json_data)
        if json_data.is_a?(Hash)
          # Check for onClick attribute (binding format: @{functionName})
          if json_data['onClick'] && json_data['onClick'].is_a?(String)
            # Extract function name from binding format
            method_name = json_data['onClick'].gsub(/^@\{|\}$/, '')
            @onclick_actions.add(method_name)
          end

          # Process children (support both 'child' and 'children')
          child_data = json_data['child'] || json_data['children']
          if child_data
            if child_data.is_a?(Array)
              child_data.each do |child|
                extract_onclick_actions(child)
              end
            else
              extract_onclick_actions(child_data)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_onclick_actions(item)
          end
        end
      end

      # Delegate to shared IncludeExpander module
      def process_includes(json_data, base_dir, id_prefix = nil)
        IncludeExpander.process_includes(json_data, base_dir, id_prefix)
      end

      private

      def generate_swiftui_view(view_name, json_data)
        # Reset state for new view
        @state_variables = []

        # SwiftUIとSwiftJsonUIのインポート
        code = "import SwiftUI\n"
        code += "import SwiftJsonUI\n"
        code += "\n"

        # 相対配置が必要な場合はPreferenceKeyを定義
        if needs_preference_key?(json_data)
          code += generate_preference_key_definition
        end

        # ビュー構造体の定義
        code += "struct #{view_name}View: View {\n"

        # JSONコンポーネントをSwiftUIに変換（状態変数を収集）
        converter = @converter_factory.create_converter(json_data, 2, @action_manager)
        body_code = converter.convert

        # Collect state variables from converter
        if converter.respond_to?(:state_variables) && converter.state_variables
          @state_variables.concat(converter.state_variables)
        end

        # Add state variables
        if @state_variables.any?
          @state_variables.uniq.each do |state_var|
            code += "    #{state_var}\n"
          end
          code += "    \n"
        end

        # Add body
        code += "    var body: some View {\n"
        code += body_code
        code += "    }\n"

        # Add action handlers
        action_handlers = @action_manager.generate_action_handlers
        if action_handlers.any?
          code += "    \n"
          code += "    // MARK: - Action Handlers\n"
          action_handlers.each do |handler_lines|
            handler_lines.each do |line|
              code += "    #{line}\n"
            end
          end
        end

        # ビュー構造体の終了
        code += "}\n\n"

        # プレビューの追加
        code += "struct #{view_name}View_Previews: PreviewProvider {\n"
        code += "    static var previews: some View {\n"
        code += "        #{view_name}View()\n"
        code += "    }\n"
        code += "}\n"

        code
      end

      def needs_preference_key?(json_data)
        return false unless json_data.is_a?(Hash)

        # childまたはchildrenの取得
        child_data = json_data['child'] || json_data['children']

        # childが配列の場合
        if child_data.is_a?(Array)
          child_data.any? do |child|
            child['alignTopOfView'] || child['alignBottomOfView'] ||
            child['alignLeftOfView'] || child['alignRightOfView'] ||
            needs_preference_key?(child)
          end
        elsif child_data
          child_data['alignTopOfView'] || child_data['alignBottomOfView'] ||
          child_data['alignLeftOfView'] || child_data['alignRightOfView'] ||
          needs_preference_key?(child_data)
        else
          false
        end
      end

      def generate_preference_key_definition
        <<~SWIFT
        // PreferenceKey for collecting view frames
        struct ViewFramePreferenceKey: PreferenceKey {
            static var defaultValue: [String: CGRect] = [:]
            static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) {
                value.merge(nextValue()) { _, new in new }
            }
        }

        SWIFT
      end

      # Validate JSON tree BEFORE style merge
      # This ensures style attributes are not incorrectly flagged
      def validate_json_tree(json_data, file_name = nil)
        @validator ||= Core::AttributeValidator.new(:swiftui)
        # Canonical-only validation for L1-normalized layouts
        @validator.normalized = Core::Normalization.canonicalized?(json_data)
        @current_validation_file = file_name
        validate_component_recursive(json_data, nil)
        @validator.print_warnings

        shared_warnings = JsonUIShared::LayoutValidator.validate_layout(
          json_data, source_path: file_name || '(unknown)'
        )
        JsonUIShared::LayoutValidator.print_warnings(shared_warnings) unless shared_warnings.empty?
        @blocking_layout_errors = JsonUIShared::LayoutValidator.blocking?(shared_warnings)
        @blocking_layout_reason = blocking_layout_reason(shared_warnings)
      end

      # True when the last validated layout declared something the
      # converters cannot survive (a binding where the declaration takes a
      # list). The caller skips conversion and records the layout as not
      # generated, rather than letting a converter raise on `.each`.
      def blocking_layout_errors?
        @blocking_layout_errors == true
      end

      def blocking_layout_reason(warnings)
        Array(warnings).select { |w| w[:level] == :error }.map { |w| w[:message] }.join('; ')
      end

      # @param component [Hash] The component to validate
      # @param parent_orientation [String, nil] The parent's orientation ('horizontal' or 'vertical')
      # @param hierarchy [String] The hierarchy path (e.g., "child[0].child[1]")
      def validate_component_recursive(component, parent_orientation = nil, hierarchy = nil)
        return unless component.is_a?(Hash)

        # Skip data definition objects (they have 'data' array but no 'type')
        return if component.key?('data') && !component.key?('type')

        # Warn if include directive is missing id in SwiftUI mode
        if component.key?('include') && !component.key?('id')
          loc = hierarchy || 'root'
          puts "\e[33m⚠️  [SJUI Warning] [#{@current_validation_file} #{loc}] Include '#{component['include']}' is missing 'id'. In SwiftUI mode, included data properties need an id prefix to avoid name collisions.\e[0m"
        end

        # Warn if Collection has items binding but no sections defined
        if component['type']&.downcase == 'collection' && component['items'] && (!component['sections'] || component['sections'].empty?)
          loc = hierarchy || 'root'
          puts "\e[33m⚠️  [SJUI Warning] [#{@current_validation_file} #{loc}] Collection has 'items' binding but no 'sections' defined. In SwiftUI mode, collections with 'items' should define 'sections' for proper cell rendering.\e[0m"
        end

        # Warn if a Collection names cells but no data source to read them
        # from. There is no emit for this shape: the old fallback wrote
        # `data.collectionDataSource.getCellData(for:)`, and NEITHER half of
        # that exists — no layout in the corpus or in either consuming iOS
        # face declares `collectionDataSource`, and `getCellData` has no
        # implementation anywhere in SwiftJsonUI. It was uncompilable Swift
        # that nothing had ever compiled, because every other Collection
        # declares `items`. Naming it here is what the old fallback owed:
        # silence produced a file that failed at build with an error pointing
        # at the generated line rather than at the layout.
        if component['type']&.downcase == 'collection' &&
           !component['items'] &&
           (!(component['sections'] || []).empty? || !(component['cellClasses'] || []).empty?)
          loc = hierarchy || 'root'
          id = component['id'] ? " '#{component['id']}'" : ''
          puts "\e[33m⚠️  [SJUI Warning] [#{@current_validation_file} #{loc}] " \
               "Collection#{id} names cells but declares no 'items' data source, " \
               "so no cells are emitted. Add 'items' bound to a " \
               "CollectionDataSource property.\e[0m"
        end

        # NOTE: "several cellClasses with no sections" is NOT checked here.
        # It lives in JsonUIShared::LayoutValidator#check_collection, which
        # this file already runs (below) and which kjui and rjui run too — the
        # rule is identical on all three faces, so it gets one implementation
        # rather than three copies that drift.

        # Validate this component (without style-merged attributes)
        if component['type']
          @validator.validate(component, nil, parent_orientation,
                              file_name: @current_validation_file,
                              view_id: component['id'],
                              hierarchy: hierarchy)
        end

        # Determine current orientation for passing to children
        current_orientation = component['orientation'] || parent_orientation

        # Recursively validate children
        child_data = component['child'] || component['children']
        if child_data.is_a?(Array)
          child_data.each_with_index do |child, index|
            child_hierarchy = hierarchy ? "#{hierarchy}.child[#{index}]" : "child[#{index}]"
            validate_component_recursive(child, current_orientation, child_hierarchy)
          end
        elsif child_data
          child_hierarchy = hierarchy ? "#{hierarchy}.child" : "child"
          validate_component_recursive(child_data, current_orientation, child_hierarchy)
        end
      end
    end
  end
end
