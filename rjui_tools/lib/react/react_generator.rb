# frozen_string_literal: true

require 'set'
require_relative '../core/type_converter'
require_relative '../core/generated_marker'
require_relative '../core/normalization'
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
require_relative 'converters/icon_label_converter'
require_relative 'converters/circle_view_converter'
require_relative 'converters/web_converter'
require_relative 'converters/blur_converter'
require_relative 'converters/gradient_view_converter'
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
        # EditText / Input are aliases for TextField (attribute_definitions
        # `_alias_of: TextField`; kept for Android / HTML naming compatibility)
        'EditText' => Converters::TextFieldConverter,
        'Input' => Converters::TextFieldConverter,
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
        'Embed' => Converters::EmbedConverter,
        # These five ship the same canonical names as BaseConverter's child
        # dispatch map — the two tables must stay in step or a type renders
        # differently at root vs nested position.
        'IconLabel' => Converters::IconLabelConverter,
        'CircleView' => Converters::CircleViewConverter,
        'Web' => Converters::WebConverter,
        'Blur' => Converters::BlurConverter,
        'GradientView' => Converters::GradientViewConverter
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

      def generate(component_name, json, subdir: '', variants: {}, data_type: nil, source_rel: nil, namespace_stem: nil, screen_id: nil)
        # Store current JSON file name (snake_case) for StringManager resolution.
        # strings.json groups keys by directory-qualified namespace — e.g. a
        # layout at `learn/installation.json` lives under the `learn_installation`
        # namespace, not just `installation`. Including the subdir here makes
        # StringManagerHelper Phase 2 (current-file priority) find the screen's
        # own namespace instead of falling through to Phase 3's linear scan,
        # which would resolve bare keys like `lang_toggle` to whichever
        # namespace appeared first in strings.json.
        snake_basename = namespace_stem || component_name
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

        # Per-file normalization state (same shared-config pattern as
        # `_current_json_name`). Converters read this through
        # BaseConverter#layout_normalized? to take the canonical-only
        # attribute lookup path for L1-normalized layouts.
        @config['_layout_normalized'] = Core::Normalization.canonicalized?(json)

        jsx_content = convert_component(json)

        generate_component_file(component_name, jsx_content, json,
                                subdir: subdir, variants: variants,
                                data_type: data_type, source_rel: source_rel,
                                screen_id: screen_id)
      end

      private

      def convert_component(json, indent = 2)
        # Check if this is an include component
        if json['include']
          converter = Converters::IncludeConverter.new(json, @config)
          return converter.convert_node(indent)
        end

        type = json['type'] || 'View'

        # First check extension converters, then built-in converters
        converter_class = @extension_converters[type] || CONVERTERS[type]
        unless converter_class
          # sjui renders unknown types as a red "Unsupported component" Text
          # and swift dynamic as an error box; silently degrading to a plain
          # View here left react the only face that hid the failure.
          Core::Logger.warn("Unknown component type '#{type}' — rendering as a plain View (no converter registered)") if defined?(Core::Logger)
          converter_class = Converters::ViewConverter
        end

        converter = converter_class.new(json, @config)
        converter.convert_node(indent)
      end

      def generate_component_file(name, jsx_content, json, subdir: '', variants: {}, data_type: nil, source_rel: nil, screen_id: nil)
        # Variant screens (home@regular.json) reuse the BASE screen's Data
        # type — the variant-file data contract is base-canonical.
        data_name = data_type || name
        state_vars = extract_state_variables(json)
        focus_fields = extract_focus_fields(json)
        collection_scrolls = extract_collection_scrolls(json)
        relative_containers = extract_relative_containers(json)
        auto_shrink_targets = extract_auto_shrink_targets(json)
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
        needs_focus = !focus_fields.empty?
        needs_collection_scroll = !collection_scrolls.empty?
        needs_relative_position = !relative_containers.empty?
        needs_auto_shrink = !auto_shrink_targets.empty?
        needs_client = needs_state || uses_string_manager || uses_extensions || needs_landscape || needs_focus ||
                       needs_collection_scroll || needs_relative_position || needs_auto_shrink || variants.any?
        use_client = needs_client ? "\"use client\";\n\n" : ''

        # Build React import
        react_hooks = []
        react_hooks << 'useState' if needs_state
        if needs_focus || needs_collection_scroll || needs_relative_position || needs_auto_shrink
          react_hooks << 'useRef'
          react_hooks << 'useEffect'
        end
        react_import = react_hooks.empty? ? "import React from 'react';" : "import React, { #{react_hooks.join(', ')} } from 'react';"

        # Generate useMediaQuery import for landscape responsive support
        media_query_import = (needs_landscape || variants.any?) ? "\nimport { useMediaQuery } from '@/hooks/useMediaQuery';" : ''

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

        # Collection scroll control. Only the helpers actually used are
        # imported, so a list with just `scrollTo` does not pull in the
        # IntersectionObserver path.
        collection_scroll_import = collection_scroll_import_line(collection_scrolls)

        # Sibling-relative positioning (align*View / align*OfView).
        relative_position_import = needs_relative_position ?
          "\nimport { applyRelativePositions } from '@/generated/relativePosition';" : ''

        # autoShrink / minimumScaleFactor. CSS cannot size text against the
        # element's own box, so the fit is measured at runtime.
        auto_shrink_import = needs_auto_shrink ?
          "\nimport { applyAutoShrink } from '@/generated/autoShrink';" : ''
        screen_marker_import = screen_id ? "\nimport { screenMarker } from '@/generated/screenMarker';" : ''

        # partialAttributes are applied at runtime against the resolved
        # string (a pattern range or a localized text cannot be resolved
        # during the build), so a component that uses them imports the
        # generated renderer.
        partial_text_import = uses_partial_attributes?(json) ? "\nimport { partialText } from '@/generated/partialText';" : ''

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

        # A color attribute that lands in an inline style resolves its
        # colors.json key at runtime (BaseConverter#color_style_expr). Read
        # the requirement off the emitted JSX rather than re-deriving it from
        # the tree: the emitter's own output cannot drift from itself.
        color_manager_import = jsx_content.include?('ColorManager.') ?
                               "\nimport { ColorManager } from '@/generated/ColorManager';" : ''

        # SelectBox dateStringFormat. Detected off the emitted JSX for the same
        # reason as ColorManager: the emitter's own output cannot drift from
        # itself, and only one of the two directions may be present.
        date_format_names = []
        date_format_names << 'formatDateValue' if jsx_content.include?('formatDateValue(')
        date_format_names << 'toIsoDateValue' if jsx_content.include?('toIsoDateValue(')
        date_format_import = date_format_names.empty? ? '' :
          "\nimport { #{date_format_names.sort.join(', ')} } from '@/generated/dateFormat';"

        # Determined early because the Data import shape depends on it:
        # data-consuming components also import the createXxxData factory
        # for the Partial-merge call convention (see props emission below).
        uses_data = jsx_content.match?(/\bdata\./) || !focus_fields.empty? || !collection_scrolls.empty?

        # Generate Data type import (for TypeScript)
        data_import = ''
        if @config['typescript']
          data_import = if uses_data
                          "\nimport { type #{data_name}Data, create#{data_name}Data } from '@/generated/data/#{data_name}Data';"
                        else
                          "\nimport type { #{data_name}Data } from '@/generated/data/#{data_name}Data';"
                        end
          # Also import cell Data types for Collections
          cell_types = extract_collection_cell_types(json)
          cell_types.each do |cell_type|
            data_import += "\nimport type { #{cell_type}Data } from '@/generated/data/#{cell_type}Data';"
          end
        elsif uses_data
          data_import = "\nimport { create#{data_name}Data } from '@/generated/data/#{data_name}Data';"
        end

        # Generate imports for extension components
        embed_isolated = extension_components.include?('EmbedContainer#isolated')
        extension_imports = extension_components.map do |comp_name|
          if comp_name == 'EmbedContainer#isolated'
            nil # marker only — folded into the EmbedContainer import below
          elsif comp_name == 'EmbedContainer' && embed_isolated
            "import { EmbedContainer, buildEmbedScreenResolver } from '@/components/extensions/EmbedContainer';"
          else
            "import { #{comp_name} } from '@/components/extensions/#{comp_name}';"
          end
        end.compact.join("\n")
        extension_imports = "\n#{extension_imports}" unless extension_imports.empty?

        # Generate imports for included components using absolute paths
        component_imports = included_component_map.map do |comp_name, inc_subdir|
          if inc_subdir && !inc_subdir.empty?
            "import #{comp_name} from '@/generated/components/#{inc_subdir}/#{comp_name}';"
          else
            "import #{comp_name} from '@/generated/components/#{comp_name}';"
          end
        end.join("\n")
        component_imports = "\n#{component_imports}" unless component_imports.empty?

        # Variant-file dispatch (home@regular.json): early-return the
        # matching variant component by media-query tier (compact < 768 ≤
        # medium < 1024 ≤ regular — same thresholds as responsive_helper's
        # Tailwind mapping). Whole-tree replacement; the same data prop
        # feeds every branch so VM state (owned by the hook above this
        # component) survives a tier change (06a-design D4/D5).
        variant_component_imports = ''
        variant_dispatch_declaration = ''
        if variants.any?
          variant_component_imports = "\n" + variants.values.map do |comp|
            if subdir && !subdir.empty?
              "import #{comp} from '@/generated/components/#{subdir}/#{comp}';"
            else
              "import #{comp} from '@/generated/components/#{comp}';"
            end
          end.join("\n")

          hooks = []
          if variants['medium'] || variants['compact']
            hooks << "  const jsonuiMinMd = useMediaQuery('(min-width: 768px)');"
          end
          if variants['regular'] || variants['medium']
            hooks << "  const jsonuiMinLg = useMediaQuery('(min-width: 1024px)');"
          end
          guards = []
          guards << "  if (jsonuiMinLg) { return <#{variants['regular']} data={data} />; }" if variants['regular']
          guards << "  if (jsonuiMinMd && !jsonuiMinLg) { return <#{variants['medium']} data={data} />; }" if variants['medium']
          guards << "  if (!jsonuiMinMd) { return <#{variants['compact']} data={data} />; }" if variants['compact']
          variant_dispatch_declaration = "\n" + (hooks + guards).join("\n") + "\n"
        end

        # Generate state declarations
        state_declarations = state_vars.map do |var|
          "  const [#{var[:name]}, set#{capitalize_first(var[:name])}] = useState(#{var[:default]});"
        end.join("\n")
        state_declarations = "\n#{state_declarations}\n" unless state_declarations.empty?

        # Focus-state binding (cross-platform parity with sjui/kjui
        # data.<id>IsFocused): a ref per editable field plus an effect that
        # drives DOM focus from the data prop. The converters attach the ref
        # and report focus changes back via on<Camel>IsFocusedChange.
        focus_declarations = focus_fields.map do |field|
          # The type parameter is TypeScript-only: a JS project emits .jsx, and
          # `useRef<HTMLInputElement | null>(null)` there is a syntax error, not
          # a harmless annotation.
          ref_type =
            if @config['typescript']
              field[:element] == 'textarea' ? '<HTMLTextAreaElement | null>' : '<HTMLInputElement | null>'
            else
              ''
            end
          "  const #{field[:camel]}Ref = useRef#{ref_type}(null);\n" \
            "  useEffect(() => { if (data.#{field[:camel]}IsFocused) { #{field[:camel]}Ref.current?.focus(); } }, [data.#{field[:camel]}IsFocused]);"
        end.join("\n")
        focus_declarations = "\n#{focus_declarations}\n" unless focus_declarations.empty?

        # Collection scroll control: a ref per collection plus one effect per
        # declared attribute. The converter attaches the ref (and the onScroll
        # read-back for currentPage); everything that has to live in the
        # component body is hoisted here.
        collection_scroll_declarations = collection_scrolls.map { |c| collection_scroll_effects(c) }.join("\n")
        unless collection_scroll_declarations.empty?
          collection_scroll_declarations = "\n#{collection_scroll_declarations}\n"
        end

        # Sibling-relative positioning: a ref per container plus one effect that
        # measures and writes the offsets. The helper installs its own
        # ResizeObserver, so the effect has no dependencies — the constraints
        # are static.
        relative_position_declarations =
          relative_containers.map { |c| relative_position_effect(c) }.join("\n")
        unless relative_position_declarations.empty?
          relative_position_declarations = "\n#{relative_position_declarations}\n"
        end

        # autoShrink: a ref per shrinking element plus the effect that fits it.
        # A bound size or factor becomes a dependency, so the text re-fits when
        # the data changes.
        auto_shrink_declarations = auto_shrink_targets.map { |t| auto_shrink_effect(t) }.join("\n")
        auto_shrink_declarations = "\n#{auto_shrink_declarations}\n" unless auto_shrink_declarations.empty?

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

        # Root id passthrough: collections address cells as
        # {collectionId}_item_{index} via an `id` prop (kjui testTag
        # parity — the web test driver clicks `#id` and needs it on the
        # cell's real root box), and include sites may set id too. Inject
        # before the visibility fragment wrap: an expression-container
        # root can't carry an id, so injection is skipped there.
        jsx_content, root_id_injected = inject_root_id_prop(jsx_content)

        # Screen marker: a data attribute on the SAME root element, so it is
        # visible exactly when the screen is. A dedicated node would need a
        # non-empty box to satisfy the driver's visibility predicate, and a
        # stray 1x1 element would join the parent's flex/grid flow.
        jsx_content = inject_root_screen_marker(jsx_content, screen_id)

        # A root element with a visibility binding arrives here as a bare
        # JSX expression container (`{cond && (...)}` from
        # BaseConverter#wrap_with_visibility). That form is only legal as a
        # child of a JSX element — directly under `return (` it parses as a
        # block/object literal (TS1005). Wrap it in a fragment.
        if jsx_content.lstrip.start_with?('{')
          jsx_content = "    <>\n#{jsx_content}\n    </>"
        end

        # Generate data-based props interface and signature.
        # Call convention (rjui-include-data-partial-call-convention-missing):
        # `data` is optional at every call site — bare includes render
        # `<Name />`, data-passing includes render `<Name data={{...}} />`
        # with a Partial, and pages/cells pass the full object. A
        # data-consuming component merges the prop over its createXxxData()
        # defaults so every member is present for the body's reads.
        props_interface = generate_data_props_interface(name, uses_data, data_type: data_name)
        # `id` is destructured only when it was injected into the root —
        # the interface always accepts it (call sites can't know), but an
        # unused binding would trip noUnusedParameters setups.
        id_part = root_id_injected ? ', id' : ''
        props_sig =
          if uses_data
            @config['typescript'] ? "{ data: dataProp#{id_part} }: #{name}Props" : "{ data: dataProp#{id_part} }"
          else
            @config['typescript'] ? "{ data#{id_part} }: #{name}Props" : "{ data#{id_part} }"
          end
        data_merge_declaration =
          if uses_data
            type_annotation = @config['typescript'] ? ": #{data_name}Data" : ''
            "\n  const data#{type_annotation} = { ...create#{data_name}Data(), ...dataProp };"
          else
            ''
          end

        marker_source = name.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                            .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                            .downcase
        marker_header = Core::GeneratedMarker.comment_header(
          source: source_rel || "Layouts/#{marker_source}.json",
          generator: "rjui build"
        )
        marker_footer = Core::GeneratedMarker.comment_footer

        <<~JSX
          #{use_client}#{marker_header}
          #{react_import}#{media_query_import}#{link_import}#{string_manager_import}#{cell_id_import}#{collection_scroll_import}#{relative_position_import}#{auto_shrink_import}#{date_format_import}#{screen_marker_import}#{partial_text_import}#{configuration_import}#{color_manager_import}#{lucide_import}#{data_import}#{extension_imports}#{component_imports}#{variant_component_imports}

          #{props_interface if @config['typescript']}
          export const #{name} = (#{props_sig}) => {#{data_merge_declaration}#{state_declarations}#{focus_declarations}#{collection_scroll_declarations}#{relative_position_declarations}#{auto_shrink_declarations}#{landscape_declaration}#{string_manager_declaration}#{variant_dispatch_declaration}
            return (
          #{jsx_content}
            );
          };

          export default #{name};

          #{marker_footer}
        JSX
      end

      # Generate TypeScript interface for data-based props.
      # `data` is always optional: bare include sites render `<Name />`,
      # data-passing includes provide a Partial that the component merges
      # over its createXxxData() defaults, and pages/cells pass the full
      # object (a full XxxData is assignable to Partial<XxxData>).
      def generate_data_props_interface(name, uses_data = true, data_type: nil)
        data_name = data_type || name
        data_field = uses_data ? "data?: Partial<#{data_name}Data>;" : "data?: #{data_name}Data;"
        <<~TS
          interface #{name}Props {
            #{data_field}
            id?: string;
          }
        TS
      end

      # Inject the `id` prop into the root element's tag so collection
      # cells ({collectionId}_item_{index}) and include sites can address
      # the component's real root box. Returns [jsx, injected?]. A layout
      # root that declares its own id keeps it as the fallback
      # (`id={id ?? "own"}`); an expression-container root (visibility
      # binding) is left untouched.
      def inject_root_id_prop(jsx_content)
        stripped = jsx_content.lstrip
        return [jsx_content, false] unless stripped.start_with?('<') && stripped[1] =~ /[A-Za-z]/

        first_tag = jsx_content[/\A\s*<[^>]*>/m]
        return [jsx_content, false] unless first_tag

        if first_tag =~ /\sid="([^"]*)"/
          [jsx_content.sub(/\sid="([^"]*)"/) { " id={id ?? \"#{Regexp.last_match(1)}\"}" }, true]
        elsif first_tag =~ /\sid=\{([^}]*)\}/
          [jsx_content.sub(/\sid=\{([^}]*)\}/) { " id={id ?? (#{Regexp.last_match(1)})}" }, true]
        else
          [jsx_content.sub(/\A(\s*)<([A-Za-z][\w.]*)/) { "#{Regexp.last_match(1)}<#{Regexp.last_match(2)} id={id}" }, true]
        end
      end

      # Inject `data-screen` into the root element's tag for SCREEN layouts
      # (never cells or partials). Skipped for an expression-container root
      # (visibility binding), exactly like `id` injection.
      #
      # The value is gated on NODE_ENV: the marker is test scaffolding, and
      # React drops an attribute whose value is `undefined`, so a production
      # bundle renders no `data-screen` at all. This mirrors the DEBUG-only
      # markers on iOS and Android.
      def inject_root_screen_marker(jsx_content, screen_id)
        return jsx_content unless screen_id

        stripped = jsx_content.lstrip
        return jsx_content unless stripped.start_with?('<') && stripped[1] =~ /[A-Za-z]/
        return jsx_content unless jsx_content[/\A\s*<[^>]*>/m]

        attribute = %({...screenMarker("#{screen_id}")})
        jsx_content.sub(/\A(\s*)<([A-Za-z][\w.]*)/) { "#{Regexp.last_match(1)}<#{Regexp.last_match(2)} #{attribute}" }
      end

      def capitalize_first(str)
        str[0].upcase + str[1..]
      end

      #: JsonUI attribute -> the field the relativePosition helper expects. The
      #: `OfView` family positions the element BESIDE the anchor (UIKit:
      #: `alignTopOfView` constrains self.bottom to the anchor's top, i.e. self
      #: goes above it); the plain `View` family aligns the same edges.
      RELATIVE_CONSTRAINT_FIELDS = {
        'alignTopOfView' => 'above',
        'alignBottomOfView' => 'below',
        'alignLeftOfView' => 'leftOf',
        'alignRightOfView' => 'rightOf',
        'alignTopView' => 'alignTop',
        'alignBottomView' => 'alignBottom',
        'alignLeftView' => 'alignLeft',
        'alignRightView' => 'alignRight',
        'alignCenterVerticalView' => 'centerVertical',
        'alignCenterHorizontalView' => 'centerHorizontal'
      }.freeze

      # Containers holding at least one sibling-constrained child. MUST stay in
      # sync with ViewConverter#relative_positioned? and
      # #build_relative_position_ref_attr, which attach the ref this targets.
      def extract_relative_containers(json, found = [])
        return found unless json.is_a?(Hash) || json.is_a?(Array)

        if json.is_a?(Hash)
          child = json['child'] || json['children']
          children = child.is_a?(Array) ? child : [child].compact
          if %w[View SafeAreaView].include?(json['type'].to_s) || json['type'].nil?
            specs = children.map { |c| relative_constraint_for(c) }.compact
            found << { ref: relative_position_ref_name(specs.first['id']), specs: specs } if specs.any?
          end
          children.each { |c| extract_relative_containers(c, found) }
        else
          json.each { |item| extract_relative_containers(item, found) }
        end

        found.uniq { |c| c[:ref] }
      end

      # One child's constraint spec, or nil when it has none. A literal id is
      # required: it is how the helper finds the element in the DOM.
      def relative_constraint_for(child)
        return nil unless child.is_a?(Hash)

        id = child['id']
        return nil unless id.is_a?(String) && !id.empty? && !id.include?('@{')

        spec = { 'id' => id }
        RELATIVE_CONSTRAINT_FIELDS.each do |attr, field|
          target = child[attr]
          spec[field] = target if target.is_a?(String) && !target.empty? && !target.include?('@{')
        end
        spec.length > 1 ? spec : nil
      end

      def relative_position_ref_name(child_id)
        "#{snake_to_camel_id(child_id)}RelRef"
      end

      #: Types whose converter attaches the autoShrink ref. Text-bearing
      #: elements only — shrinking a container has no meaning.
      AUTO_SHRINK_TYPES = %w[Label Text].freeze

      # Elements declaring autoShrink with a literal id — each gets a hoisted
      # ref + fit effect, matching the ref LabelConverter attaches. A literal
      # id is what ties the two together, the same contract the focus and
      # collection-scroll helpers use.
      def extract_auto_shrink_targets(json, found = [])
        return found unless json.is_a?(Hash) || json.is_a?(Array)

        if json.is_a?(Hash)
          id = json['id']
          if AUTO_SHRINK_TYPES.include?(json['type'].to_s) && truthy_attr?(json['autoShrink']) &&
             id.is_a?(String) && !id.empty? && !id.include?('@{')
            found << {
              ref: auto_shrink_ref_name(id),
              font_size: json['fontSize'],
              min_scale: json['minimumScaleFactor']
            }
          end

          child = json['child'] || json['children']
          if child.is_a?(Array)
            child.each { |c| extract_auto_shrink_targets(c, found) }
          elsif child
            extract_auto_shrink_targets(child, found)
          end
        else
          json.each { |item| extract_auto_shrink_targets(item, found) }
        end

        found.uniq { |t| t[:ref] }
      end

      def auto_shrink_ref_name(id)
        "#{snake_to_camel_id(id)}ShrinkRef"
      end

      # `autoShrink: "@{flag}"` cannot be resolved at build time, and a
      # component that shrinks only when the data says so still needs the ref
      # — the effect reads the same expression as its dependency.
      def truthy_attr?(value)
        return false if value.nil? || value == false || value == 'false'

        true
      end

      def auto_shrink_effect(target)
        element_type = @config['typescript'] ? '<HTMLElement | null>' : ''
        options = []
        deps = []
        size = auto_shrink_operand(target[:font_size])
        scale = auto_shrink_operand(target[:min_scale])
        if size
          options << "fontSize: #{size[:expr]}"
          deps << size[:expr] if size[:bound]
        end
        if scale
          options << "minimumScaleFactor: #{scale[:expr]}"
          deps << scale[:expr] if scale[:bound]
        end

        "  const #{target[:ref]} = useRef#{element_type}(null);\n" \
          "  useEffect(() => applyAutoShrink(#{target[:ref]}.current, " \
          "{ #{options.join(', ')} }), [#{deps.join(', ')}]);"
      end

      # A number passes through; a binding becomes the data expression (and a
      # dependency). Anything else is dropped — the helper falls back to the
      # computed size, which is what an unreadable declaration deserves.
      def auto_shrink_operand(value)
        return nil if value.nil?
        return { expr: value.to_s, bound: false } if value.is_a?(Numeric)

        text = value.to_s
        if (match = text.match(/\A@\{([A-Za-z_][A-Za-z0-9_.]*)\}\z/))
          { expr: "data.#{match[1]}", bound: true }
        elsif text.match?(/\A-?\d+(\.\d+)?\z/)
          { expr: text, bound: false }
        end
      end

      def relative_position_effect(container)
        element_type = @config['typescript'] ? '<HTMLDivElement | null>' : ''
        spec_literal = container[:specs].map do |spec|
          pairs = spec.map { |k, v| "#{k}: '#{v}'" }
          "{ #{pairs.join(', ')} }"
        end.join(', ')

        "  const #{container[:ref]} = useRef#{element_type}(null);\n" \
          "  useEffect(() => applyRelativePositions(#{container[:ref]}.current, " \
          "[#{spec_literal}]), []);"
      end

      # Collections declaring scroll control (scrollTo / defaultScrollAnchor /
      # currentPage / onItemAppear). Each one gets a hoisted ref plus the
      # effects below, matching the ref CollectionConverter attaches. MUST stay
      # in sync with CollectionConverter::SCROLL_CONTROL_ATTRS and
      # #build_collection_ref_attr — a literal id is what ties the two together.
      def extract_collection_scrolls(json, found = [])
        return found unless json.is_a?(Hash) || json.is_a?(Array)

        if json.is_a?(Hash)
          id = json['id']
          if json['type'] == 'Collection' && id.is_a?(String) && !id.empty? && !id.include?('@{')
            scroll_to = json['scrollTo']
            default_anchor = json['defaultScrollAnchor']
            current_page = json['currentPage']
            on_item_appear = json['onItemAppear']
            if scroll_to || default_anchor || current_page || on_item_appear
              layout = json['orientation'] || json['layout'] || json['scrollDirection'] || 'vertical'
              found << {
                camel: snake_to_camel_id(id),
                horizontal: layout.to_s.downcase == 'horizontal',
                items: json['items'],
                scroll_to: scroll_to,
                scroll_anchor: json['scrollAnchor'],
                scroll_animated: json['scrollAnimated'],
                default_anchor: default_anchor,
                current_page: current_page,
                on_item_appear: on_item_appear
              }
            end
          end

          child = json['child'] || json['children']
          if child.is_a?(Array)
            child.each { |c| extract_collection_scrolls(c, found) }
          elsif child
            extract_collection_scrolls(child, found)
          end
        else
          json.each { |item| extract_collection_scrolls(item, found) }
        end

        found.uniq { |c| c[:camel] }
      end

      # Only the helpers a screen actually uses get imported.
      def collection_scroll_import_line(collections)
        return '' if collections.empty?

        names = []
        names << 'scrollCollectionToItem' if collections.any? { |c| c[:scroll_to] || c[:current_page] }
        names << 'applyCollectionDefaultAnchor' if collections.any? { |c| c[:default_anchor] }
        names << 'currentCollectionPage' if collections.any? { |c| c[:current_page] }
        names << 'observeCollectionItems' if collections.any? { |c| c[:on_item_appear] }
        return '' if names.empty?

        "\nimport { #{names.sort.join(', ')} } from '@/generated/collectionScroll';"
      end

      def collection_scroll_effects(collection)
        camel = collection[:camel]
        ref = "#{camel}Ref"
        horizontal = collection[:horizontal]
        element_type = @config['typescript'] ? '<HTMLDivElement | null>' : ''
        lines = ["  const #{ref} = useRef#{element_type}(null);"]

        # defaultScrollAnchor: where the collection starts, so it runs on mount
        # only. A later re-run would yank the user back to the anchor.
        if (anchor = collection[:default_anchor])
          lines << "  useEffect(() => { applyCollectionDefaultAnchor(#{ref}.current, " \
                   "#{scroll_anchor_expr(anchor)}, #{horizontal}); }, []);"
        end

        # scrollTo: iOS receives a PassthroughSubject, so a repeat send
        # re-scrolls; a React effect keys on a value, so re-scrolling to the
        # same index needs the bound value to change.
        if (target = collection[:scroll_to]) && binding_expression?(target)
          prop = binding_data_path(target)
          anchor_expr = scroll_anchor_expr(collection[:scroll_anchor] || 'bottom')
          animated = collection[:scroll_animated] == false ? 'false' : 'true'
          lines << "  useEffect(() => { scrollCollectionToItem(#{ref}.current, #{prop}, " \
                   "#{anchor_expr}, #{animated}, #{horizontal}); }, [#{prop}]);"
        end

        # currentPage: data -> DOM. The DOM -> data direction is the onScroll
        # handler CollectionConverter puts on the element.
        if (page = collection[:current_page]) && binding_expression?(page)
          prop = binding_data_path(page)
          lines << "  useEffect(() => { scrollCollectionToItem(#{ref}.current, #{prop}, " \
                   "'top', true, #{horizontal}); }, [#{prop}]);"
        end

        # onItemAppear: re-observes when the item list changes, because the
        # observer can only watch the cells that existed when it was created.
        if (appear = collection[:on_item_appear]) && binding_expression?(appear)
          prop = binding_data_path(appear)
          dep = binding_expression?(collection[:items]) ? binding_data_path(collection[:items]) : ''
          lines << "  useEffect(() => observeCollectionItems(#{ref}.current, " \
                   "(index) => #{prop}?.(index)), [#{dep}]);"
        end

        lines.join("\n")
      end

      def scroll_anchor_expr(anchor)
        %w[top center bottom].include?(anchor.to_s) ? "'#{anchor}'" : "'bottom'"
      end

      def binding_expression?(value)
        value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
      end

      def binding_data_path(value)
        "data.#{value[2..-2].strip}"
      end

      # Editable fields (TextField / TextView + aliases) with a literal id —
      # each gets a hoisted ref + focus effect (focus_declarations) matching
      # the ref/handlers the converters attach. MUST stay in sync with
      # BaseConverter#build_focus_binding_attrs and the DataModelGenerator
      # focus bindings.
      def extract_focus_fields(json, fields = [])
        return fields unless json.is_a?(Hash) || json.is_a?(Array)

        if json.is_a?(Hash)
          type = json['type']
          id = json['id']
          if id.is_a?(String) && !id.empty? && !id.include?('@{')
            if %w[TextField EditText Input].include?(type)
              fields << { id: id, camel: snake_to_camel_id(id), element: 'input' }
            elsif type == 'TextView'
              fields << { id: id, camel: snake_to_camel_id(id), element: 'textarea' }
            end
          end

          child = json['child'] || json['children']
          if child.is_a?(Array)
            child.each { |c| extract_focus_fields(c, fields) }
          elsif child
            extract_focus_fields(child, fields)
          end
        else
          json.each { |item| extract_focus_fields(item, fields) }
        end

        fields.uniq { |f| f[:camel] }
      end

      # snake_case id -> lowerCamel stem (sync: BaseConverter#snake_to_camel_id)
      def snake_to_camel_id(str)
        parts = str.split('_')
        parts[0] + parts[1..].map(&:capitalize).join
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
          # Marker (consumed by the import emitter, never rendered): isolated
          # call sites also import buildEmbedScreenResolver — a template v2
          # export, so type-checking against a v1 EmbedContainer.tsx fails
          # instead of silently degrading to delegate (version-skew guard).
          components << 'EmbedContainer#isolated' if json['navigationMode'] == 'isolated'
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
      # Any node carrying a non-empty partialAttributes array, at any depth.
      def uses_partial_attributes?(json)
        case json
        when Hash
          partials = json['partialAttributes']
          return true if partials.is_a?(Array) && !partials.empty?

          json.each_value { |value| return true if uses_partial_attributes?(value) }
          false
        when Array
          json.each { |item| return true if uses_partial_attributes?(item) }
          false
        else
          false
        end
      end

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

        data.map do |item|
          if item.is_a?(Hash) && item['name']
            {
              name: item['name'],
              ts_type: item['tsType'] || Core::TypeConverter.to_typescript_type(item['class'])
            }
          end
        end.compact
      end

    end
  end
end
