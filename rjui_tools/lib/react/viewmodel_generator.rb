# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative '../core/config_manager'
require_relative '../core/generated_marker'
require_relative 'style_loader'

module RjuiTools
  module React
    class ViewModelGenerator
      def initialize
        @config = Core::ConfigManager.load_config
        @source_path = @config['source_path'] || Dir.pwd
        @layouts_dir = File.join(@source_path, @config['layouts_directory'] || 'Layouts')
        @viewmodels_dir = File.join(@source_path, @config['viewmodels_directory'] || 'src/viewmodels')
        @generated_viewmodels_dir = File.join(@source_path, @config['generated_viewmodels_directory'] || 'src/generated/viewmodels')
        @data_dir = File.join(@source_path, @config['data_directory'] || 'src/generated/data')
        @styles_dir = File.join(@source_path, @config['styles_directory'] || 'Styles')
        @use_typescript = @config['typescript'] != false
      end

      def generate_viewmodels
        # Ensure directories exist
        FileUtils.mkdir_p(@generated_viewmodels_dir)
        FileUtils.mkdir_p(@viewmodels_dir)

        # Find all JSON layouts
        json_files = Dir.glob(File.join(@layouts_dir, '**/*.json')).reject do |file|
          file.include?(File.join(@layouts_dir, 'Resources')) ||
            file.include?(File.join(@layouts_dir, 'Styles'))
        end

        json_files.each do |json_file|
          process_json_file(json_file)
        end
      end

      private

      def process_json_file(json_file)
        base_name = File.basename(json_file, '.json')
        view_name = to_pascal_case(base_name)

        # Check if ViewModel exists - only generate Base if ViewModel exists
        existing_vm = find_existing_viewmodel(view_name)
        return unless existing_vm  # Skip if no ViewModel

        # Read and parse JSON
        json_content = File.read(json_file, encoding: 'UTF-8')
        json_data = JSON.parse(json_content)
        expanded_data = StyleLoader.load_and_merge(json_data, @styles_dir)

        # Extract handlers defined in data section to avoid duplicates
        data_section_handlers = extract_data_section_handlers(expanded_data)

        # Extract onclick actions and TextField bindings
        onclick_actions = extract_onclick_actions(expanded_data)
        text_field_bindings = extract_text_field_bindings(expanded_data)
        event_handlers = extract_event_handler_bindings(expanded_data)

        # Skip handlers that are already defined in data section (they use (Event) -> Void type)
        event_handlers.reject! { |name, _| data_section_handlers.include?(name) }

        is_typescript = existing_vm.end_with?('.ts')

        # Generate Base ViewModel (always overwritten when ViewModel exists)
        generate_base_viewmodel(view_name, onclick_actions, text_field_bindings, event_handlers, is_typescript)
      end

      def find_existing_viewmodel(view_name)
        ts_path = File.join(@viewmodels_dir, "#{view_name}ViewModel.ts")
        js_path = File.join(@viewmodels_dir, "#{view_name}ViewModel.js")

        return ts_path if File.exist?(ts_path)
        return js_path if File.exist?(js_path)
        nil
      end

      def generate_base_viewmodel(view_name, onclick_actions, text_field_bindings, event_handlers, is_typescript)
        extension = is_typescript ? '.ts' : '.js'
        file_path = File.join(@generated_viewmodels_dir, "#{view_name}ViewModelBase#{extension}")

        content = if is_typescript
                    generate_typescript_base(view_name, onclick_actions, text_field_bindings, event_handlers)
                  else
                    generate_javascript_base(view_name, onclick_actions, text_field_bindings, event_handlers)
                  end

        File.write(file_path, content)
        puts "  Generated ViewModelBase: #{file_path}"
      end

      def generate_viewmodel_stub(view_name, is_typescript)
        extension = is_typescript ? '.ts' : '.js'
        file_path = File.join(@viewmodels_dir, "#{view_name}ViewModel#{extension}")

        content = if is_typescript
                    generate_typescript_stub(view_name)
                  else
                    generate_javascript_stub(view_name)
                  end

        File.write(file_path, content)
        puts "  Generated ViewModel stub: #{file_path}"
      end

      def generate_typescript_base(view_name, onclick_actions, text_field_bindings, event_handlers)
        data_type = "#{view_name}Data"

        # Generate onclick handler stubs
        onclick_methods = onclick_actions.map do |action|
          "  #{action} = () => {\n    // TODO: Implement #{action}\n    console.log('[#{view_name}ViewModel] #{action}');\n  };"
        end.join("\n\n")

        # Generate event handler stubs
        event_handler_methods = event_handlers.map do |handler_name, info|
          ts_type = info[:type]
          "  #{handler_name} = (value: #{ts_type}) => {\n    // TODO: Implement #{handler_name}\n    console.log('[#{view_name}ViewModel] #{handler_name}:', value);\n  };"
        end.join("\n\n")

        all_methods = [onclick_methods, event_handler_methods].reject(&:empty?).join("\n\n")

        # Combine all handlers for initializeEventHandlers
        all_handler_assignments = []
        all_handler_assignments += onclick_actions.map { |a| "      #{a}: this.#{a}," }
        all_handler_assignments += event_handlers.keys.map { |h| "      #{h}: this.#{h}," }

        marker_header = Core::GeneratedMarker.comment_header(
          source: "#{view_name}ViewModelBase",
          generator: "rjui build"
        )
        marker_footer = Core::GeneratedMarker.comment_footer

        <<~TS
          #{marker_header}

          import { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";
          import { #{data_type} } from "@/generated/data/#{data_type}";

          export class #{view_name}ViewModelBase {
            protected router: AppRouterInstance;
            protected _getData: () => #{data_type};
            protected _setData: (data: #{data_type} | ((prev: #{data_type}) => #{data_type})) => void;

            get data(): #{data_type} {
              return this._getData();
            }

            constructor(
              router: AppRouterInstance,
              getData: () => #{data_type},
              setData: (data: #{data_type} | ((prev: #{data_type}) => #{data_type})) => void
            ) {
              this.router = router;
              this._getData = getData;
              this._setData = setData;
            }

            // Update data and trigger re-render
            updateData = (updates: Partial<#{data_type}>) => {
              this._setData((prev) => ({ ...prev, ...updates }));
            };

            // Set external variables (e.g., route params, props from parent)
            setVars = (vars: Partial<#{data_type}>) => {
              this.updateData(vars);
            };

            // Initialize event handlers - call this in subclass constructor
            protected initializeEventHandlers = () => {
              this.updateData({
          #{all_handler_assignments.join("\n")}
              });
            };

          #{all_methods}
          }

          #{marker_footer}
        TS
      end

      def generate_javascript_base(view_name, onclick_actions, text_field_bindings, event_handlers)
        data_type = "#{view_name}Data"

        onclick_methods = onclick_actions.map do |action|
          "  #{action} = () => {\n    // TODO: Implement #{action}\n    console.log('[#{view_name}ViewModel] #{action}');\n  };"
        end.join("\n\n")

        # Generate event handler stubs
        event_handler_methods = event_handlers.map do |handler_name, info|
          js_type = info[:type]
          "  #{handler_name} = (value) => {\n    // TODO: Implement #{handler_name}\n    console.log('[#{view_name}ViewModel] #{handler_name}:', value);\n  };"
        end.join("\n\n")

        all_methods = [onclick_methods, event_handler_methods].reject(&:empty?).join("\n\n")

        # Combine all handlers for initializeEventHandlers
        all_handler_assignments = []
        all_handler_assignments += onclick_actions.map { |a| "      #{a}: this.#{a}," }
        all_handler_assignments += event_handlers.keys.map { |h| "      #{h}: this.#{h}," }

        marker_header = Core::GeneratedMarker.comment_header(
          source: "#{view_name}ViewModelBase",
          generator: "rjui build"
        )
        marker_footer = Core::GeneratedMarker.comment_footer

        <<~JS
          #{marker_header}

          /**
           * Base ViewModel for #{view_name}
           */
          export class #{view_name}ViewModelBase {
            /**
             * @param {import("next/dist/shared/lib/app-router-context.shared-runtime").AppRouterInstance} router
             * @param {() => import("@/generated/data/#{data_type}").#{data_type}} getData
             * @param {(data: any) => void} setData
             */
            constructor(router, getData, setData) {
              this.router = router;
              this._getData = getData;
              this._setData = setData;
            }

            get data() {
              return this._getData();
            }

            // Update data and trigger re-render
            updateData = (updates) => {
              this._setData((prev) => ({ ...prev, ...updates }));
            };

            // Set external variables (e.g., route params, props from parent)
            setVars = (vars) => {
              this.updateData(vars);
            };

            // Initialize event handlers - call this in subclass constructor
            initializeEventHandlers = () => {
              this.updateData({
          #{all_handler_assignments.join("\n")}
              });
            };

          #{all_methods}
          }

          #{marker_footer}
        JS
      end

      def generate_typescript_stub(view_name)
        data_type = "#{view_name}Data"

        <<~TS
          // ViewModel for #{view_name}
          // This file is NOT auto-generated after initial creation - safe to edit

          import { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";
          import { #{data_type} } from "@/generated/data/#{data_type}";
          import { #{view_name}ViewModelBase } from "@/generated/viewmodels/#{view_name}ViewModelBase";

          export class #{view_name}ViewModel extends #{view_name}ViewModelBase {
            constructor(
              router: AppRouterInstance,
              getData: () => #{data_type},
              setData: (data: #{data_type} | ((prev: #{data_type}) => #{data_type})) => void
            ) {
              super(router, getData, setData);
              this.initializeEventHandlers();
            }

            // Override methods or add custom logic here
          }
        TS
      end

      def generate_javascript_stub(view_name)
        <<~JS
          // ViewModel for #{view_name}
          // This file is NOT auto-generated after initial creation - safe to edit

          import { #{view_name}ViewModelBase } from "@/generated/viewmodels/#{view_name}ViewModelBase";

          export class #{view_name}ViewModel extends #{view_name}ViewModelBase {
            constructor(router, getData, setData) {
              super(router, getData, setData);
              this.initializeEventHandlers();
            }

            // Override methods or add custom logic here
          }
        JS
      end

      def extract_onclick_actions(json_data, actions = Set.new)
        if json_data.is_a?(Hash)
          if json_data['onclick'] && json_data['onclick'].is_a?(String)
            actions.add(json_data['onclick'])
          end

          child = json_data['child'] || json_data['children']
          if child
            if child.is_a?(Array)
              child.each { |c| extract_onclick_actions(c, actions) }
            else
              extract_onclick_actions(child, actions)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| extract_onclick_actions(item, actions) }
        end

        actions.to_a
      end

      def extract_text_field_bindings(json_data, bindings = Set.new)
        if json_data.is_a?(Hash)
          if json_data['type'] == 'TextField' && json_data['text']
            text_value = json_data['text']
            if text_value.is_a?(String) && text_value.start_with?('@{') && text_value.end_with?('}')
              unless json_data['onTextChange'] || json_data['onChange']
                property_name = text_value[2...-1]
                bindings.add(property_name)
              end
            end
          end

          child = json_data['child'] || json_data['children']
          if child
            if child.is_a?(Array)
              child.each { |c| extract_text_field_bindings(c, bindings) }
            else
              extract_text_field_bindings(child, bindings)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| extract_text_field_bindings(item, bindings) }
        end

        bindings.to_a
      end

      # Extract event handler bindings from components (Switch, SelectBox, etc.)
      def extract_event_handler_bindings(json_data, handlers = {})
        if json_data.is_a?(Hash)
          component_type = json_data['type']

          # Switch, Toggle - onValueChange with boolean
          if %w[Switch Toggle].include?(component_type)
            extract_handler_binding(json_data, 'onValueChange', 'boolean', handlers)
          # Slider - onValueChange with number
          elsif component_type == 'Slider'
            extract_handler_binding(json_data, 'onValueChange', 'number', handlers)
          # Radio, Segment - onValueChange with string
          elsif %w[Radio Segment].include?(component_type)
            extract_handler_binding(json_data, 'onValueChange', 'string', handlers)
          # SelectBox - onValueChanged or onChange with string
          elsif component_type == 'SelectBox'
            handler_key = json_data['onValueChanged'] ? 'onValueChanged' : 'onChange'
            extract_handler_binding(json_data, handler_key, 'string', handlers)
          # TextView - onTextChange or onChange with string
          elsif component_type == 'TextView'
            handler_key = json_data['onTextChange'] ? 'onTextChange' : 'onChange'
            extract_handler_binding(json_data, handler_key, 'string', handlers) if json_data[handler_key]
          end

          # Process children
          child = json_data['child'] || json_data['children']
          if child
            if child.is_a?(Array)
              child.each { |c| extract_event_handler_bindings(c, handlers) }
            else
              extract_event_handler_bindings(child, handlers)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| extract_event_handler_bindings(item, handlers) }
        end

        handlers
      end

      def extract_handler_binding(json_data, handler_key, value_type, handlers)
        handler = json_data[handler_key]
        return unless handler.is_a?(String) && handler.start_with?('@{') && handler.end_with?('}')

        handler_name = handler[2...-1]
        handlers[handler_name] = { type: value_type }
      end

      # Extract handler names defined in JSON data section with (Event) -> Void type
      def extract_data_section_handlers(json_data, handlers = Set.new)
        if json_data.is_a?(Hash)
          # Check for data section
          if json_data['data'].is_a?(Array)
            json_data['data'].each do |prop|
              next unless prop.is_a?(Hash)

              # Check for event handler type definitions
              prop_class = prop['class']
              if prop_class && prop_class.include?('->') && prop_class.include?('Void')
                handlers.add(prop['name']) if prop['name']
              end
            end
          end

          # Process children
          child = json_data['child'] || json_data['children']
          if child
            if child.is_a?(Array)
              child.each { |c| extract_data_section_handlers(c, handlers) }
            else
              extract_data_section_handlers(child, handlers)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| extract_data_section_handlers(item, handlers) }
        end

        handlers
      end

      def to_pascal_case(str)
        snake = str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                   .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                   .downcase
        snake.split(/[_\-]/).map(&:capitalize).join
      end
    end
  end
end
