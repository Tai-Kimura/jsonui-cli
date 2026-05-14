# frozen_string_literal: true

require 'set'
require_relative '../core/type_converter'
require_relative '../core/generated_marker'
require_relative 'converters/base_converter'
require_relative 'converters/view_converter'
require_relative 'converters/label_converter'
require_relative 'converters/button_converter'
require_relative 'converters/image_converter'
require_relative 'converters/text_field_converter'
require_relative 'converters/text_view_converter'
require_relative 'converters/scroll_view_converter'
require_relative 'converters/collection_converter'
require_relative 'converters/switch_converter'  # Primary converter for Switch/Toggle
require_relative 'converters/toggle_converter'  # Kept for backward compatibility
require_relative 'converters/slider_converter'
require_relative 'converters/segment_converter'
require_relative 'converters/radio_converter'
require_relative 'converters/progress_converter'
require_relative 'converters/indicator_converter'
require_relative 'converters/select_box_converter'
require_relative 'converters/include_converter'
require_relative 'converters/tab_view_converter'
require_relative 'converters/embed_converter'
require_relative 'tailwind_mapper'
require_relative 'responsive_helper'
require_relative 'helpers/string_manager_helper'
require_relative 'helpers/lucide_icon_helper'

module RjuiTools
  module React
    class ReactGenerator
      include Helpers::StringManagerHelper

      CONVERTERS = {
        'View' => Converters::ViewConverter,
        'SafeAreaView' => Converters::ViewConverter,
        'Label' => Converters::LabelConverter,
        'Text' => Converters::LabelConverter,
        'Button' => Converters::ButtonConverter,
        'Image' => Converters::ImageConverter,
        'CircleImage' => Converters::ImageConverter,
        'NetworkImage' => Converters::ImageConverter,
        'TextField' => Converters::TextFieldConverter,
        'TextView' => Converters::TextViewConverter,
        'Scroll' => Converters::ScrollViewConverter,
        'ScrollView' => Converters::ScrollViewConverter,
        'Collection' => Converters::CollectionConverter,
        'Table' => Converters::CollectionConverter,
        # Switch is the primary component name, uses SwitchConverter for iOS-style toggle
        'Switch' => Converters::SwitchConverter,
        # Toggle is an alias for Switch (backward compatibility), also uses SwitchConverter
        'Toggle' => Converters::SwitchConverter,
        # CheckBox is the primary component name, uses ToggleConverter for simple checkbox
        'CheckBox' => Converters::ToggleConverter,
        # Check is an alias for CheckBox (backward compatibility), also uses ToggleConverter
        'Check' => Converters::ToggleConverter,
        # Legacy mapping kept for backward compatibility
        'Checkbox' => Converters::ToggleConverter,
        'Slider' => Converters::SliderConverter,
        'Segment' => Converters::SegmentConverter,
        'Radio' => Converters::RadioConverter,
        'Progress' => Converters::ProgressConverter,
        'Indicator' => Converters::IndicatorConverter,
        'SelectBox' => Converters::SelectBoxConverter,
        'Include' => Converters::IncludeConverter,
        'TabView' => Converters::TabViewConverter,
        'Embed' => Converters::EmbedConverter
      }.freeze

      def initialize(config)
        @config = config
        @use_tailwind = config['use_tailwind'] != false
        @extension_converters = load_extension_converters
        # Store extension converters in config so child converters can access them
        @config['_extension_converters'] = @extension_converters
        # Stash the component → attribute-definitions map so BaseConverter
        # can suppress Tailwind decoration mapping for keys that a custom
        # component has claimed as a semantic prop (e.g. CodeBlock#maxHeight).
        @config['_attribute_definitions'] = load_attribute_definitions
      end

      # Load custom converters from extensions directory
      def load_extension_converters
        converters = {}

        # Check for extensions directory
        extensions_dir = find_extensions_dir
        return converters unless extensions_dir && File.directory?(extensions_dir)

        # Load converter mappings if exists
        mappings_file = File.join(extensions_dir, 'converter_mappings.rb')
        return converters unless File.exist?(mappings_file)

        # Load the mappings
        require mappings_file

        # Get the mappings hash
        if defined?(Converters::Extensions::CONVERTER_MAPPINGS)
          Converters::Extensions::CONVERTER_MAPPINGS.each do |type, class_name|
            # Load the converter file
            snake_case = type.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                            .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                            .downcase
            converter_file = File.join(extensions_dir, "#{snake_case}_converter.rb")

            if File.exist?(converter_file)
              require converter_file
              converter_class = Converters::Extensions.const_get(class_name)
              converters[type] = converter_class
            end
          end
        end

        converters
      rescue => e
        Core::Logger.warn("Failed to load extension converters: #{e.message}") if defined?(Core::Logger)
        {}
      end

      # Load every attribute_definitions/*.json (e.g. CodeBlock.json) under
      # the extensions directory and return a flat { ComponentType => { attr => def, ... } }
      # map. Consumed by BaseConverter#decoration_allowed? to skip prop-owned
      # keys from Tailwind class emission.
      def load_attribute_definitions
        definitions = {}
        extensions_dir = find_extensions_dir
        return definitions unless extensions_dir && File.directory?(extensions_dir)

        attr_dir = File.join(extensions_dir, 'attribute_definitions')
        return definitions unless File.directory?(attr_dir)

        Dir.glob(File.join(attr_dir, '*.json')).each do |file|
          parsed = JSON.parse(File.read(file, encoding: 'UTF-8'))
          next unless parsed.is_a?(Hash)
          parsed.each do |type, attrs|
            definitions[type] = attrs if attrs.is_a?(Hash)
          end
        rescue JSON::ParserError => e
          Core::Logger.warn("Invalid attribute definition #{file}: #{e.message}") if defined?(Core::Logger)
        end
        definitions
      end

      def find_extensions_dir
        # Check multiple possible locations
        candidates = [
          File.join(Dir.pwd, 'rjui_tools', 'lib', 'react', 'converters', 'extensions'),
          File.join(File.dirname(__FILE__), 'converters', 'extensions')
        ]

        candidates.find { |dir| File.directory?(dir) }
      end

      def generate(component_name, json, subdir: '')
        # Store current JSON file name (snake_case) for StringManager resolution.
        # strings.json groups keys by directory-qualified namespace — e.g. a
        # layout at `learn/installation.json` lives under the `learn_installation`
        # namespace, not just `installation`. Including the subdir here makes
        # StringManagerHelper Phase 2 (current-file priority) find the screen's
        # own namespace instead of falling through to Phase 3's linear scan,
        # which would resolve bare keys like `lang_toggle` to whichever
        # namespace appeared first in strings.json.
        snake_basename = component_name
          .gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
          .gsub(/([a-z\d])([A-Z])/, '\1_\2')
          .downcase
        # `"."` is what File.dirname returns for root-level layouts — filter
        # it out (and `..` for good measure) so root files become e.g.
        # `learn_index` instead of `._learn_index`.
        namespace_parts = subdir.to_s.split('/')
                                .reject { |p| p.empty? || p == '.' || p == '..' }
                                .map(&:downcase)
        namespace_parts << snake_basename
        @config['_current_json_name'] = namespace_parts.join('_')

        jsx_content = convert_component(json)

        generate_component_file(component_name, jsx_content, json)
      end

      private

      def convert_component(json, indent = 2)
        # Check if this is an include component
        if json['include']
          converter = Converters::IncludeConverter.new(json, @config)
          return converter.convert(indent)
        end

        type = json['type'] || 'View'

        # First check extension converters, then built-in converters
        converter_class = @extension_converters[type] || CONVERTERS[type] || Converters::ViewConverter

        converter = converter_class.new(json, @config)
        converter.convert(indent)
      end

      def generate_component_file(name, jsx_content, json)
        state_vars = extract_state_variables(json)
        included_component_map = extract_included_components(json)  # { CompName => subdir_or_nil }
        included_components = included_component_map.keys
        extension_components = extract_extension_components(json)
        # Primary signal: any converter (standard or custom component) that
        # resolved a snake_case value via `convert_string_key` emits
        # `StringManager.currentLanguage.*` verbatim into the JSX stream.
        # Scanning the already-converted output is exact — it covers
        # standard text-like attrs AND custom component string props
        # without having to teach `uses_string_manager?` every possible
        # prop name. The JSON-structure walk is kept as a belt-and-braces
        # fallback in case a converter ever emits StringManager refs via a
        # path that doesn't go through the jsx_content string.
        uses_string_manager = jsx_content.include?('StringManager.') ||
                              uses_string_manager?(json)
        uses_link = uses_link?(json)
        needs_landscape = ResponsiveHelper.needs_landscape_hook?(json)

        # FontSpec routing: any converter that emits the
        # `Configuration.Font.resolve(...)` JS expression (currently produced
        # by the BaseConverter font block when `fontFamily` is set) needs
        # the host-supplied `Configuration` template imported. Detection
        # mirrors the StringManager scan above — string match in the
        # already-converted JSX is exact and component-agnostic.
        uses_font_provider = jsx_content.include?('Configuration.Font.resolve(')

        # Props come from 'data' attribute - can be at root level or as first child element
        data = extract_data_from_json(json)

        # Determine if we need useState or "use client"
        needs_state = !state_vars.empty?
        uses_extensions = !extension_components.empty?
        needs_client = needs_state || uses_string_manager || uses_extensions || needs_landscape
        use_client = needs_client ? "\"use client\";\n\n" : ''

        # Build React import
        react_hooks = []
        react_hooks << 'useState' if needs_state
        react_import = react_hooks.empty? ? "import React from 'react';" : "import React, { #{react_hooks.join(', ')} } from 'react';"

        # Generate useMediaQuery import for landscape responsive support
        media_query_import = needs_landscape ? "\nimport { useMediaQuery } from '@/hooks/useMediaQuery';" : ''

        # Generate Next.js Link import if needed
        link_import = uses_link ? "\nimport Link from 'next/link';" : ''

        # Generate StringManager import if needed.
        # Generated components consume strings through the reactive hook so
        # `setLanguage` triggers a re-render on every call site (fix for
        # rjui-string-manager-no-persistence-or-reactivity).
        string_manager_import = uses_string_manager ? "\nimport { useStringManager } from '@/generated/StringManager';" : ''

        # Generate cellIdGenerator import if needed
        uses_auto_cell_id = uses_auto_cell_id?(json)
        cell_id_import = uses_auto_cell_id ? "\nimport { enrichCellIds } from '@/generated/cellIdGenerator';" : ''

        # Generate Configuration (FontSpec / fontProvider) import when any
        # text site routed its font through Configuration.Font.resolve(...).
        # The template lives at `<lib_directory>/Configuration.ts`; the
        # default sync_tool destination is `src/lib/jsonui/Configuration.ts`,
        # importable as `@/lib/jsonui/Configuration`.
        configuration_import = uses_font_provider ? "\nimport { Configuration } from '@/lib/jsonui/Configuration';" : ''

        # Generate lucide-react import for TabView icons
        # TabViewConverter#build_icon emits <IconName /> components without
        # adding imports itself. Walking the tree here keeps the import
        # collection in one place, matching the Link / StringManager pattern.
        lucide_icons = collect_lucide_icons(json).to_a.sort
        lucide_import = lucide_icons.empty? ? '' :
                        "\nimport { #{lucide_icons.join(', ')} } from 'lucide-react';"

        # Generate Data type import (for TypeScript)
        data_import = ''
        if @config['typescript']
          data_import = "\nimport type { #{name}Data } from '@/generated/data/#{name}Data';"
          # Also import cell Data types for Collections
          cell_types = extract_collection_cell_types(json)
          cell_types.each do |cell_type|
            data_import += "\nimport type { #{cell_type}Data } from '@/generated/data/#{cell_type}Data';"
          end
        end

        # Generate imports for extension components
        extension_imports = extension_components.map do |comp_name|
          "import { #{comp_name} } from '@/components/extensions/#{comp_name}';"
        end.join("\n")
        extension_imports = "\n#{extension_imports}" unless extension_imports.empty?

        # Generate imports for included components using absolute paths
        component_imports = included_component_map.map do |comp_name, subdir|
          if subdir && !subdir.empty?
            "import #{comp_name} from '@/generated/components/#{subdir}/#{comp_name}';"
          else
            "import #{comp_name} from '@/generated/components/#{comp_name}';"
          end
        end.join("\n")
        component_imports = "\n#{component_imports}" unless component_imports.empty?

        # Generate state declarations
        state_declarations = state_vars.map do |var|
          "  const [#{var[:name]}, set#{capitalize_first(var[:name])}] = useState(#{var[:default]});"
        end.join("\n")
        state_declarations = "\n#{state_declarations}\n" unless state_declarations.empty?

        # Generate landscape hook declaration
        landscape_declaration = needs_landscape ? "\n  #{ResponsiveHelper.landscape_hook_declaration}\n" : ''

        # Generate StringManager hook declaration. The helper emits
        # `StringManager.currentLanguage.xxx` while walking the spec; we
        # rewrite those to `$s.xxx` below so the JSX reads from the
        # subscribed snapshot and re-renders on `setLanguage`.
        string_manager_declaration = uses_string_manager ? "\n  const $s = useStringManager();\n" : ''
        if uses_string_manager
          jsx_content = jsx_content.gsub('StringManager.currentLanguage.', '$s.')
        end

        # Generate data-based props interface and signature
        props_interface = generate_data_props_interface(name)
        props_sig = @config['typescript'] ? "{ data }: #{name}Props" : '{ data }'

        marker_source = name.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                            .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                            .downcase
        marker_header = Core::GeneratedMarker.comment_header(
          source: "Layouts/#{marker_source}.json",
          generator: "rjui build"
        )
        marker_footer = Core::GeneratedMarker.comment_footer

        <<~JSX
          #{use_client}#{marker_header}
          #{react_import}#{media_query_import}#{link_import}#{string_manager_import}#{cell_id_import}#{configuration_import}#{lucide_import}#{data_import}#{extension_imports}#{component_imports}

          #{props_interface if @config['typescript']}
          export const #{name} = (#{props_sig}) => {#{state_declarations}#{landscape_declaration}#{string_manager_declaration}
            return (
          #{jsx_content}
            );
          };

          export default #{name};

          #{marker_footer}
        JSX
      end

      # Generate TypeScript interface for data-based props
      def generate_data_props_interface(name)
        <<~TS
          interface #{name}Props {
            data: #{name}Data;
          }
        TS
      end

      def capitalize_first(str)
        str[0].upcase + str[1..]
      end

      def extract_state_variables(json, vars = [])
        # Check for Segment/Radio that need state
        type = json['type']

        if type == 'Segment'
          id = json['id'] || 'segment'
          selected = json['selectedIndex'] || json['selectedTabIndex']
          unless selected.is_a?(String) && selected.start_with?('@{')
            vars << { name: 'selectedIndex', default: selected || 0 }
          end
        elsif type == 'Radio'
          id = json['id'] || 'radio'
          selected = json['selectedValue']
          unless selected.is_a?(String) && selected.start_with?('@{')
            vars << { name: 'selectedValue', default: '""' }
          end
        end

        # Recurse into children
        json['child']&.each do |child|
          extract_state_variables(child, vars) if child.is_a?(Hash)
        end

        vars.uniq { |v| v[:name] }
      end

      def generate_props_signature(props)
        return '' if props.empty?

        # Props are now hashes with :name and :ts_type
        prop_names = props.map { |p| p[:name] }
        "{ #{prop_names.join(', ')} }"
      end

      def generate_props_interface(name, props)
        return '' if props.empty?

        # Props are now hashes with :name and :ts_type
        <<~TS
          interface #{name}Props {
            #{props.map { |p| "#{p[:name]}?: #{p[:ts_type]};" }.join("\n  ")}
          }
        TS
      end

      # Walk the JSON tree collecting Lucide React icon component names
      # referenced by TabView tabs, so generate_component_file can emit the
      # matching `import { ... } from 'lucide-react'`.
      # Skips iconType:"resource" — those render as <img> from public/icons.
      def collect_lucide_icons(json, icons = ::Set.new)
        if json.is_a?(Hash)
          if json['type'] == 'TabView' && json['tabs'].is_a?(Array)
            json['tabs'].each do |tab|
              next unless tab.is_a?(Hash)
              icon_type = tab['iconType'] || 'system'
              next if icon_type == 'resource'

              [tab['icon'] || 'circle', tab['selectedIcon']].compact.each do |icon|
                mapped = Helpers::LucideIconHelper.map_to_lucide(icon)
                icons << mapped if mapped && !mapped.empty?
              end
            end
          end

          child = json['child'] || json['children']
          if child.is_a?(Array)
            child.each { |c| collect_lucide_icons(c, icons) }
          elsif child.is_a?(Hash)
            collect_lucide_icons(child, icons)
          end
        elsif json.is_a?(Array)
          json.each { |item| collect_lucide_icons(item, icons) }
        end
        icons
      end

      def extract_included_components(json, components = {})
        # Check if this node has an include
        if json['include']
          include_path = json['include']
          parts = include_path.split('/')
          base_name = parts.last
          component_name = to_pascal_case(base_name)
          subdir = parts.length > 1 ? parts[0...-1].join('/') : nil
          components[component_name] ||= subdir
        end

        # Check for Collection headerClasses/cellClasses/footerClasses
        %w[headerClasses cellClasses footerClasses].each do |key|
          json[key]&.each do |class_ref|
            class_name = class_ref.is_a?(Hash) ? class_ref['className'] : class_ref
            next unless class_name.is_a?(String)
            parts = class_name.split('/')
            base_name = parts.last
            component_name = to_pascal_case(base_name)
            subdir = parts.length > 1 ? parts[0...-1].join('/') : nil
            components[component_name] ||= subdir
          end
        end

        # Check for Collection sections (SwiftUI/Compose/React style)
        json['sections']&.each do |section|
          next unless section.is_a?(Hash)

          %w[header cell footer].each do |key|
            class_name = section[key]
            next unless class_name.is_a?(String)
            parts = class_name.split('/')
            base_name = parts.last
            component_name = to_pascal_case(base_name)
            subdir = parts.length > 1 ? parts[0...-1].join('/') : nil
            components[component_name] ||= subdir
          end
        end

        # Check for TabView tabs (view references)
        json['tabs']&.each do |tab|
          next unless tab.is_a?(Hash)
          view_name = tab['view']
          next unless view_name.is_a?(String)
          parts = view_name.split('/')
          base_name = parts.last
          component_name = to_pascal_case(base_name)
          subdir = parts.length > 1 ? parts[0...-1].join('/') : nil
          components[component_name] ||= subdir
        end

        # Check for Embed (screen reference)
        if json['type'] == 'Embed' && json['screen'].is_a?(String)
          parts = json['screen'].split('/')
          base_name = parts.last
          component_name = to_pascal_case(base_name)
          subdir = parts.length > 1 ? parts[0...-1].join('/') : nil
          components[component_name] ||= subdir
        end

        # Recurse into children (both 'child' and 'children' keys)
        (Array(json['child']) + Array(json['children'])).each do |child|
          extract_included_components(child, components) if child.is_a?(Hash)
        end

        components
      end

      def to_pascal_case(name)
        return name if name.match?(/^[A-Z]/) && !name.include?('_')
        name.split('_').map(&:capitalize).join
      end

      def extract_extension_components(json, components = [])
        type = json['type']

        # Check if this type is an extension component
        if type && @extension_converters.key?(type)
          components << type
        end

        # Check for NetworkImage type (built-in but requires separate import)
        if type == 'NetworkImage'
          components << 'NetworkImage'
        end

        # Embed type uses EmbedContainer runtime helper (init-emitted into extensions)
        if type == 'Embed'
          components << 'EmbedContainer'
        end

        # Recurse into children (both 'child' and 'children' keys)
        (Array(json['child']) + Array(json['children'])).each do |child|
          extract_extension_components(child, components) if child.is_a?(Hash)
        end

        components.uniq
      end

      # Extract cell component types from Collection elements (for TypeScript imports)
      def extract_collection_cell_types(json, types = [])
        type = json['type']

        if type == 'Collection'
          # Modern sections format
          json['sections']&.each do |section|
            if section['cell']
              cell_name = section['cell'].split('/').last
              cell_type = cell_name.match?(/^[A-Z]/) && !cell_name.include?('_') ? cell_name : cell_name.split('_').map(&:capitalize).join
              types << cell_type
            end
          end

          # Legacy cellClasses format
          json['cellClasses']&.each do |cell_class|
            cell_name = cell_class.is_a?(Hash) ? cell_class['className'] : cell_class
            next unless cell_name.is_a?(String)
            cell_name = cell_name.split('/').last
            cell_type = cell_name.match?(/^[A-Z]/) && !cell_name.include?('_') ? cell_name : cell_name.split('_').map(&:capitalize).join
            types << cell_type
          end
        end

        # Recurse into children (both 'child' and 'children' keys)
        (Array(json['child']) + Array(json['children'])).each do |child|
          extract_collection_cell_types(child, types) if child.is_a?(Hash)
        end

        types.uniq
      end

      def uses_string_manager?(json)
        # Check text attributes for snake_case string keys
        %w[text hint placeholder label title src url].each do |attr|
          return true if json[attr] && string_key?(json[attr])
        end

        # Recurse into children (handle both array and single object)
        children = json['child']
        if children.is_a?(Array)
          children.each do |child|
            return true if child.is_a?(Hash) && uses_string_manager?(child)
          end
        elsif children.is_a?(Hash)
          return true if uses_string_manager?(children)
        end

        false
      end

      # Detect a Collection node with autoChangeTrackingId enabled anywhere in the tree.
      def uses_auto_cell_id?(json)
        return false unless json.is_a?(Hash)
        return true if json['type'] == 'Collection' &&
                       json['autoChangeTrackingId'] == true &&
                       json['cellIdProperty'] && !json['cellIdProperty'].to_s.empty?

        children = json['child']
        if children.is_a?(Array)
          children.each do |child|
            return true if uses_auto_cell_id?(child)
          end
        elsif children.is_a?(Hash)
          return true if uses_auto_cell_id?(children)
        end

        # Collections may nest cells via sections.cell — those are separate
        # component files, so the tree walk above is enough.
        false
      end

      def uses_link?(json)
        # Check if this element has href attribute
        return true if json['href']

        # Recurse into children
        json['child']&.each do |child|
          return true if child.is_a?(Hash) && uses_link?(child)
        end

        false
      end

      # Extract data from JSON - search for data-only elements in children (recursively)
      # A data-only element is { "data": [...] } with only the data key
      def extract_data_from_json(json)
        return [] unless json['child'].is_a?(Array)

        json['child'].each do |child|
          next unless child.is_a?(Hash)
          # Check if this child has only 'data' key (data-only element)
          if child.keys == ['data'] && child['data'].is_a?(Array)
            # Normalize types using TypeConverter (mode: react)
            return Core::TypeConverter.normalize_data_properties(child['data'], 'react')
          end
          # Recurse into children
          result = extract_data_from_json(child)
          return result unless result.empty?
        end

        []
      end

      # Check if a child element is a data-only element (should not be rendered)
      def data_only_element?(child)
        return false unless child.is_a?(Hash)
        child.keys == ['data'] && child['data'].is_a?(Array)
      end

      # Extract props from 'data' attribute with type information
      # Format: [{"class": "String", "name": "title"}, {"class": "ViewModel", "name": "viewModel"}]
      # Returns array of hashes with :name and :ts_type keys
      def extract_data_props(data)
        return [] unless data.is_a?(Array)

        data.filter_map do |item|
          if item.is_a?(Hash) && item['name']
            {
              name: item['name'],
              ts_type: item['tsType'] || Core::TypeConverter.to_typescript_type(item['class'])
            }
          end
        end
      end

    end
  end
end
