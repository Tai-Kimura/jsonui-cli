# frozen_string_literal: true

require 'json'
require_relative 'base_converter'
require_relative '../../core/layout_path'
require_relative '../include_expander'
require_relative '../included_members'
require_relative '../style_loader'

module RjuiTools
  module React
    module Converters
      class IncludeConverter < BaseConverter
        def convert(indent = 2)
          include_path = json['include']

          unless include_path
            return "#{indent_str(indent)}{/* Error: Include component must have 'include' property */}"
          end

          # Generate component name from include path
          # included_1 -> Included1, main_menu -> MainMenu
          base_name = include_path.split('/').last
          component_name = base_name.split('_').map(&:capitalize).join

          # Merge shared_data and data
          merged_data = {}
          merged_data.merge!(attributes['shared_data']) if attributes['shared_data'].is_a?(Hash)
          merged_data.merge!(json['data']) if json['data'].is_a?(Hash)

          # The partial reads the including layout's data (ruling
          # 2026-10-02; design-philosophy: an include is an inline expansion
          # and the parent owns the VM): every name the partial's Data type
          # declares, read off this layout's data — prefixed by the include's
          # id, as the expanded Data type spells it — with the include node's
          # maps over it (shared_data, then data). Until jsonui-cli 1.9.6 a
          # bare include rendered `<Name />` and handed nothing (ticket
          # rjui-include-does-not-read-the-screens-data).
          #
          # One `data` prop (Partial<XxxData> — the component merges it over
          # its createXxxData() defaults). Map bindings resolve through
          # add_viewmodel_data_prefix like every built-in converter.
          data_prop = build_data_prop(merged_data, including_data_pairs(merged_data))

          id_attr = include_id_attr + include_path_attr(base_name)

          if data_prop.empty?
            "#{indent_str(indent)}<#{component_name}#{id_attr} />"
          else
            "#{indent_str(indent)}<#{component_name}#{id_attr} #{data_prop} />"
          end
        end

        private

        # `jsonuiPath` for a layout that takes it (IncludePaths): this include
        # node's position in the expanded tree — `"0_3"`, or, where this
        # layout takes it too, its own root's path and the rest.
        def include_path_attr(stem)
          return '' unless Array(@config['_path_stems']).include?(stem)

          path = json[JsonUIShared::LayoutPath::KEY] || '0'
          if @config['_path_prop']
            " jsonuiPath={`${jsonuiPath}#{path.sub(/\A0/, '')}`}"
          else
            " jsonuiPath=\"#{path}\""
          end
        end

        # Design U8, when `jui build` turned the prefix on: the include's id is
        # not an element of its own — it is the prefix of the ids inside
        # (combined with the prefix above it), as on native; an include
        # without an id hands the prefix above it straight through.
        def include_id_attr
          return build_id_attr unless @config['_include_id_prefix']

          include_id = attributes['id']
          if include_id.is_a?(String) && !include_id.empty? && !has_binding?(include_id)
            " idPrefix={jsonuiIncludePrefix(idPrefix, \"#{include_id}\")}"
          elsif include_id
            build_id_attr
          else
            ' idPrefix={idPrefix}'
          end
        end

        def build_data_prop(data, leading = [])
          pairs = leading + data.map do |key, value|
            "#{key}: #{format_prop_value(value)}"
          end
          return '' if pairs.empty?

          "data={{ #{pairs.join(', ')} }}"
        end

        # `member: data.<what the including layout calls it>` for each member
        # of the partial's Data type that no map sets (IncludedMembers: its
        # declared data, its handlers and bound values, and the names it binds
        # without declaring — each spelled as the expanded tree spells it).
        def including_data_pairs(map)
          root = @config['_layouts_dir'] || (@config['layouts_directory'] && File.expand_path(@config['layouts_directory']))
          return [] unless root

          path = File.join(root, "#{json['include']}.json")
          return [] unless File.file?(path)

          tree = StyleLoader.load_and_merge(JSON.parse(File.read(path, encoding: 'UTF-8')))
          tree = IncludeExpander.process_includes(tree, File.dirname(path), nil, root)
          IncludedMembers.pairs(tree, include_data_prefix, map).map do |member, including|
            "#{member}: data.#{including}"
          end
        end

        # The include's id as the prefix of the partial's data names
        # (IncludeExpander's rule); a bound id names no prefix.
        def include_data_prefix
          id = attributes['id']
          return nil unless id.is_a?(String) && !id.empty? && !has_binding?(id)

          IncludeExpander.to_camel_case(id)
        end

        def format_prop_value(value)
          case value
          when String
            if (m = value.match(/\A@\{([^}]+)\}\z/))
              # Whole-value binding -> parent data reference
              add_viewmodel_data_prefix(m[1].gsub(/^this\./, ''))
            elsif value.match?(/@\{([^}]+)\}/)
              # Interpolated binding(s) -> template literal; the text
              # between them is escaped by StringLiterals.ts_template_body
              interpolated = value.split(/(@\{[^}]+\})/).map do |part|
                if (inner = part[/\A@\{([^}]+)\}\z/, 1])
                  "${#{add_viewmodel_data_prefix(inner.gsub(/^this\./, ''))}}"
                else
                  JsonUIShared::StringLiterals.ts_template_body(part)
                end
              end.join
              "`#{interpolated}`"
            else
              # Regular string
              JsonUIShared::StringLiterals.ts(value)
            end
          when Hash
            # Nested object
            pairs = value.map { |k, v| "#{k}: #{format_prop_value(v)}" }
            "{ #{pairs.join(', ')} }"
          when Array
            # Array
            items = value.map { |v| format_prop_value(v) }
            "[#{items.join(', ')}]"
          when Numeric
            value.to_s
          when TrueClass, FalseClass
            value.to_s
          when NilClass
            'null'
          else
            JsonUIShared::StringLiterals.ts(value)
          end
        end
      end
    end
  end
end
