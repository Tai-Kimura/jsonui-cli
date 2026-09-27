# frozen_string_literal: true

require 'set'
require_relative '../core/type_synonyms'
require_relative '../core/type_converter'
require_relative '../core/bind_fold'
require_relative '../core/logger'
require_relative '../core/attribute_validator'
require_relative '../core/generated_marker'
require_relative '../core/frameworks'
require_relative '../core/normalization'
require_relative '../core/tap_accessibility'
require 'json'
require_relative '../core/string_manager_core'
require_relative '../core/layout_path'
require_relative 'include_paths'
require_relative '../core/node_keys'
require_relative 'component_name'
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
require_relative 'converters/converter_table'
require_relative 'tailwind_mapper'
require_relative 'responsive_helper'
require_relative 'helpers/string_manager_helper'
require_relative 'helpers/lucide_icon_helper'
require_relative '../core/enum_spelling'

module RjuiTools
  module React
    class ReactGenerator
      include Helpers::StringManagerHelper

      # The one table, shared with the child dispatch (BaseConverter
      # #get_converter_class): converters/converter_table.rb. This kept a
      # second copy until jsonui-cli 1.9.0, and a root NetworkImage / Toggle
      # rendered differently from a nested one.
      CONVERTERS = Converters::ConverterTable.table

      # The validator whose sentence a type drawn as nothing says: the build's
      # own (BuildCommand hands it), else one made the first time such a type
      # is met — one per build either way. A validator per node read the
      # definitions again for each, and a copy that left its links dangling
      # said "attribute_definitions.json not found" once per such node.
      attr_writer :unknown_type_validator

      def unknown_type_validator
        @unknown_type_validator ||= Core::AttributeValidator.new(:react)
      end

      def initialize(config)
        @config = config
        @framework = Core::Frameworks.for(config)
        @use_tailwind = config['use_tailwind'] != false
        @extension_converters = load_extension_converters
        # a spelling the app registers is the app's, for what classifies a
        # node by its drawn type too (TypeSynonyms.app_types)
        JsonUIShared::TypeSynonyms.app_types = @extension_converters.keys
        # Store extension converters in config so child converters can access them
        @config['_extension_converters'] = @extension_converters
        # The validator whose sentences name what no converter draws, for the
        # child converters too (BaseConverter#type_validator): this build's.
        @config['_type_validator'] = method(:unknown_type_validator)
        # Stash the component → attribute-definitions map so BaseConverter
        # can suppress Tailwind decoration mapping for keys that a custom
        # component has claimed as a semantic prop (e.g. CodeBlock#maxHeight).
        @config['_attribute_definitions'] = load_attribute_definitions
      end

      # The spellings this project registers converters of its own for: the
      # keys of the extensions directory's converter_mappings.rb.
      def self.extension_types
        allocate.send(:load_extension_converters).keys
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
        # Own-section spellings via the CANONICAL function
        # (StringManagerCore.namespace_candidates) — the same one the
        # sjui/kjui builders and jui lint-strings consult. It normalizes
        # each segment the way the extractor writes sections (camel split,
        # kebab hyphens folded) and keeps the raw spellings as trailing
        # candidates; hand-rolling this here is how the kebab own-miss
        # family started (own-spelling normalization filing, 2026-08-11).
        # `"."` is what File.dirname returns for root-level layouts —
        # filter it (and `..`) so root files become `learn_index`, not
        # `._learn_index`. `namespace_stem` carries the RAW file stem
        # (build_command); component_name is the PascalCase fallback, which
        # the canonical normalization folds to the same snake spelling.
        stem = namespace_stem || component_name
        rel = (subdir.to_s.split('/')
                     .reject { |p| p.empty? || p == '.' || p == '..' } + [stem]).join('/')
        @config['_current_json_name'] =
          JsonUIShared::StringManagerCore.namespace_candidates(rel, preferred: :relative).first
        @config['_current_namespaces'] =
          JsonUIShared::StringManagerCore.namespace_candidates(rel, preferred: :basename)

        # Per-file normalization state (same shared-config pattern as
        # `_current_json_name`). Converters read this through
        # BaseConverter#layout_normalized? to take the canonical-only
        # attribute lookup path for L1-normalized layouts.
        @config['_layout_normalized'] = Core::Normalization.canonicalized?(json)
        # Each node's position, for the name its handlers are handed when the
        # layout gives it no id (JsonUIShared::LayoutPath.view_id) — the rule
        # the sjui and kjui codegen stamp too. An include is its own
        # component here, so the nodes in it are stamped from that file's
        # own root (spec/core/layout_path_spec.rb).
        JsonUIShared::LayoutPath.stamp!(json) unless JsonUIShared::LayoutPath.stamped?(json)
        # The classes the layout's data declares, for a handler whose
        # arguments its declaration decides (SelectBox.onValueChange).
        @config['_data_classes'] = IncludePaths.declared_data_classes(json)
        # Whether this layout takes `jsonuiPath`, its root's path in the
        # include-expanded tree (IncludePaths; `jui build` names them).
        @config['_path_prop'] = Array(@config['_path_stems']).include?(stem)

        # The layout's declared data classes, raw (`name => class`): the
        # class-list Collection reads its `items` by what the property
        # declares (CollectionConverter#legacy_items_list_element).
        @config['_data_classes'] = declared_data_classes(json)

        # The tap rule's shape of every tap (shared/core/tap_accessibility.rb),
        # which the converters read for the keyboard's button
        # (BaseConverter#keyboard_tap_attrs) — on a copy, after validation.
        json = JsonUIShared::TapAccessibility.annotate!(JSON.parse(JSON.generate(json)))

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

        # First check extension converters (with the spelling as written, and
        # the node as written), then built-in converters. A type-synonym
        # spelling (HStack, WebView, …) is drawn as its type, from
        # shared/core/type_synonyms.json, and a declared alias section
        # (EditText, Check, Toggle, …: `_alias_of`) as its canonical one; the
        # map below holds canonical declared sections. A built-in draws the
        # node with its `bind` folded (the child path,
        # BaseConverter#create_converter_for_child, does the same).
        converter_class = @extension_converters[type]
        unless converter_class
          json = JsonUIShared::ComponentAliases.resolve(JsonUIShared::TypeSynonyms.canonicalize(json))
          type = json['type'] || 'View'
          json = JsonUIShared::BindFold.fold(json, type)
          converter_class = CONVERTERS[type]
        end
        unless converter_class
          # No converter draws it. A type the validator knows (an extension
          # definition with no converter, say) is named in its own sentence
          # and drawn as a View, its children in it; an unknown type is named
          # in the validator's sentence (JsonUIShared::AttributeValidatorCore
          # .unknown_component_type_message) and drawn as nothing — the
          # sentence in a JSX comment where the node would be, as kjui and
          # sjui draw it. It was drawn as a View (4f's ruling, jsonui-cli
          # 1.9.0). The child path, BaseConverter#create_converter_for_child,
          # follows the same rule.
          if unknown_type_validator.known_component_type?(type.to_s)
            Core::Logger.warn(Core::AttributeValidator.declared_without_drawer_message(type.to_s, 'web')) if defined?(Core::Logger)
            converter_class = Converters::ViewConverter
          else
            sentence = unknown_type_validator.unknown_component_type_message(type.to_s)
            Core::Logger.warn(sentence) if defined?(Core::Logger)
            return Converters::UnknownTypeConverter.new(json, @config, sentence).convert_node(indent)
          end
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

        # Determine if we need useState or "use client". A control seeded from
        # a static value (BaseConverter#wrap_seeded) holds its state in the
        # file's JsonUISeeded.
        uses_seeded = jsx_content.include?('<JsonUISeeded')
        needs_state = !state_vars.empty? || uses_seeded
        uses_extensions = !extension_components.empty?
        needs_focus = !focus_fields.empty?
        needs_collection_scroll = !collection_scrolls.empty?
        needs_relative_position = !relative_containers.empty?
        needs_auto_shrink = !auto_shrink_targets.empty?
        needs_client = needs_state || uses_string_manager || uses_extensions || needs_landscape || needs_focus ||
                       needs_collection_scroll || needs_relative_position || needs_auto_shrink || variants.any?
        use_client = needs_client ? @framework.use_client_prefix : ''

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

        # Generate the framework's Link import if needed
        link_import = uses_link && !@framework.link_import_line.empty? ? "\n#{@framework.link_import_line}" : ''

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
        # userInteractionEnabled false or bound: the stopped element's inert
        # (BaseConverter#apply_interaction_inert, build_command
        # emit_interaction_stop_helper).
        interaction_stop_import = jsx_content.include?("#{Converters::BaseConverter::INERT_HELPER}(") ?
          "\nimport { #{Converters::BaseConverter::INERT_HELPER} } from '@/generated/interactionStop';" : ''

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
        #
        # The hoisted declarations count too — a bound autoShrink operand
        # references `data.` from its effect, which is NOT in jsx_content, so
        # scanning the JSX alone left `data` an optional prop with no merge and
        # the effect read `data.x` off possibly-undefined (TS18048).
        auto_shrink_reads_data = auto_shrink_targets.any? do |t|
          "#{t[:font_size]}#{t[:min_scale]}".include?('@{')
        end
        uses_data = jsx_content.match?(/\bdata\./) || !focus_fields.empty? ||
                    !collection_scrolls.empty? || auto_shrink_reads_data

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
        include_prefix = @config['_include_id_prefix']
        uses_id_prefix = include_prefix && jsx_content.match?(/\bidPrefix\b/)
        props_interface = generate_data_props_interface(name, uses_data, data_type: data_name,
                                                                    id_prefix: include_prefix,
                                                                    path: @config['_path_prop'])
        # `id` is destructured only when it was injected into the root —
        # the interface always accepts it (call sites can't know), but an
        # unused binding would trip noUnusedParameters setups.
        id_part = root_id_injected ? ', id' : ''
        id_part += ', idPrefix' if uses_id_prefix
        # A screen (not included) has no path above its root: `0`.
        id_part += ', jsonuiPath = "0"' if @config['_path_prop'] && jsx_content.match?(/\bjsonuiPath\b/)
        include_id_names = %w[jsonuiIncludeId jsonuiIncludePrefix].select { |f| jsx_content.include?("#{f}(") }
        include_id_import =
          if include_prefix && include_id_names.any?
            "\nimport { #{include_id_names.join(', ')} } from '@/generated/includeId';"
          else
            ''
          end
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
          #{react_import}#{media_query_import}#{link_import}#{string_manager_import}#{cell_id_import}#{collection_scroll_import}#{relative_position_import}#{auto_shrink_import}#{date_format_import}#{screen_marker_import}#{interaction_stop_import}#{partial_text_import}#{include_id_import}#{configuration_import}#{color_manager_import}#{lucide_import}#{data_import}#{extension_imports}#{component_imports}#{variant_component_imports}

          #{props_interface if @config['typescript']}#{seeded_helper(@config['typescript']) if uses_seeded}
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
      def generate_data_props_interface(name, uses_data = true, data_type: nil, id_prefix: false, path: false)
        data_name = data_type || name
        data_field = uses_data ? "data?: Partial<#{data_name}Data>;" : "data?: #{data_name}Data;"
        # `idPrefix`: the include prefix above this component (design U8) —
        # declared only when `jui build` turned it on, so an unchanged build
        # emits unchanged bytes.
        prefix_field = id_prefix ? "\n  idPrefix?: string;" : ''
        # `jsonuiPath`: this layout's root's position in the include-expanded
        # tree (IncludePaths) — declared only for a layout that takes it.
        prefix_field += "\n  jsonuiPath?: string;" if path
        <<~TS
          interface #{name}Props {
            #{data_field}
            id?: string;#{prefix_field}
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
      # The type a node is drawn as, which the passes below classify on so
      # they agree with the converter that draws it (they walk the layout as
      # written): the spelling itself when an app's converter is registered
      # under it — that node is the app's — else its type-synonym target,
      # then its alias section's canonical one (shared/core/type_synonyms.rb).
      def drawn_type_of(json)
        type = json['type']
        return type if type && @extension_converters.key?(type)

        JsonUIShared::TypeSynonyms.drawn_type(type)
      end

      def extract_relative_containers(json, found = [])
        return found unless json.is_a?(Hash) || json.is_a?(Array)

        if json.is_a?(Hash)
          child = json['child'] || json['children']
          children = child.is_a?(Array) ? child : [child].compact
          if %w[View SafeAreaView].include?(drawn_type_of(json).to_s) || json['type'].nil?
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
      AUTO_SHRINK_TYPES = %w[Label].freeze

      # Elements declaring autoShrink with a literal id — each gets a hoisted
      # ref + fit effect, matching the ref LabelConverter attaches. A literal
      # id is what ties the two together, the same contract the focus and
      # collection-scroll helpers use.
      def extract_auto_shrink_targets(json, found = [])
        return found unless json.is_a?(Hash) || json.is_a?(Array)

        if json.is_a?(Hash)
          id = json['id']
          if AUTO_SHRINK_TYPES.include?(drawn_type_of(json).to_s) && truthy_attr?(json['autoShrink']) &&
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

      #: Scroll containers that are not Collections. They get the anchor effect
      #: only — MUST stay in sync with ScrollViewConverter#build_scroll_ref_attr.
      SCROLL_CONTAINER_TYPES = %w[ScrollView].freeze

      # Collections declaring scroll control (scrollTo / defaultScrollAnchor /
      # currentPage / onItemAppear). Each one gets a hoisted ref plus the
      # effects below, matching the ref CollectionConverter attaches. MUST stay
      # in sync with CollectionConverter::SCROLL_CONTROL_ATTRS and
      # #build_collection_ref_attr — a literal id is what ties the two together.
      def extract_collection_scrolls(json, found = [])
        return found unless json.is_a?(Hash) || json.is_a?(Array)

        if json.is_a?(Hash)
          id = json['id']
          # A ScrollView is a scroll container too, and `defaultScrollAnchor`
          # is declared for it — the anchor helper takes any scrollable
          # element, so it starts where the layout says without a second
          # implementation. The other three are Collection-only (they address
          # ITEMS; a ScrollView has none).
          drawn = drawn_type_of(json)
          scrollable = drawn == 'Collection' ||
                       (SCROLL_CONTAINER_TYPES.include?(drawn.to_s) && json['defaultScrollAnchor'])
          if scrollable && id.is_a?(String) && !id.empty? && !id.include?('@{')
            collection = drawn == 'Collection'
            scroll_to = collection ? json['scrollTo'] : nil
            default_anchor = json['defaultScrollAnchor']
            current_page = collection ? json['currentPage'] : nil
            on_item_appear = collection ? json['onItemAppear'] : nil
            # The page-change callback: a paging Collection's, as on sjui and
            # kjui (both emit it in their paging path only). The raw node here,
            # so the definitions' alias spellings are looked up too.
            page_change = if collection && json['paging'] == true
                            json['onValueChange'] || json['onValueChanged'] || json['onPageChanged']
                          end
            if scroll_to || default_anchor || current_page || on_item_appear || page_change
              layout = json['orientation'] || json['layout'] || json['scrollDirection'] || 'vertical'
              lowered_layout = JsonUIShared::EnumSpelling.lowered(layout, 'Collection', 'layout')
              found << {
                id: id,
                camel: snake_to_camel_id(id),
                horizontal: lowered_layout == 'horizontal' || !!json['horizontalScroll'],
                flow: %w[flow leftaligned].include?(lowered_layout),
                items: json['items'],
                sections: json['sections'],
                cell_id_property: json['cellIdProperty'],
                auto_tracking: json['autoChangeTrackingId'] == true,
                scroll_to: scroll_to,
                scroll_anchor: json['scrollAnchor'],
                scroll_animated: json['scrollAnimated'],
                default_anchor: default_anchor,
                current_page: current_page,
                on_item_appear: on_item_appear,
                page_change: page_change
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
        names << 'scrollCollectionToItem' if collections.any? { |c| c[:current_page] }
        names << 'scrollCollectionToCell' if collections.any? { |c| scroll_to_binding?(c) }
        names << 'collectionCellKeys' if collections.any? { |c| scroll_to_binding?(c) && collection_cell_key_lists(c) }
        names << 'applyCollectionDefaultAnchor' if collections.any? { |c| c[:default_anchor] }
        names << 'currentCollectionPage' if collections.any? { |c| c[:current_page] || c[:page_change] }
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

        # scrollTo: the request is a CHANGE of the bound value (the SSoT's
        # Collection.scrollTo, jsonui-cli 1.9.0) — the value the Collection is
        # drawn with scrolls nowhere, and sending the same value again does
        # not re-scroll. The value names a CELL (scrollCollectionToCell): a
        # number its place among the drawn sections' cells, a string — with
        # cellIdProperty — the first cell whose key it is, from the keys the
        # effect reads off the data. The effect runs on mount too, so it
        # compares with the value it last saw (a ref seeded with the first);
        # until jsonui-cli 1.9.0 it scrolled on mount to whatever the value
        # was. `Object.is`, and a ref rather than a "mounted" flag: React's
        # StrictMode runs a mount effect twice, and the second would have
        # scrolled.
        if scroll_to_binding?(collection)
          prop = binding_data_path(collection[:scroll_to])
          seen = "#{camel}ScrollToSeen"
          anchor_expr = scroll_anchor_expr(collection[:scroll_anchor] || 'bottom')
          animated = scroll_animated_arg(collection[:scroll_animated])
          lists = collection_cell_key_lists(collection)
          keys = lists ? "collectionCellKeys(#{lists}, #{cell_key_property(collection).to_json})" : 'null'
          lines << "  const #{seen} = useRef(#{prop});"
          lines << "  useEffect(() => { if (Object.is(#{seen}.current, #{prop})) return; #{seen}.current = #{prop}; " \
                   "scrollCollectionToCell(#{ref}.current, #{collection[:id].to_json}, #{prop}, " \
                   "#{keys}, #{anchor_expr}, #{animated}, #{horizontal}); }, [#{prop}]);"
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

      def scroll_to_binding?(collection)
        binding_expression?(collection[:scroll_to])
      end

      # The drawn cells' lists, in section order, as a JS array expression —
      # the keys scrollTo matches a string against (a cell's cellId, else its
      # cellIdProperty value when the Collection has one) — or nil when the
      # Collection has no items binding. Until jsonui-cli 1.9.0 it was nil
      # with no cellIdProperty too, so a string never met a cellId there.
      # The lists are the ones CollectionConverter draws:
      # each section that declares a cell (its cells enriched with their
      # cellIds under autoChangeTrackingId); with no sections, the class-list
      # shape's every data section, the first only on a flow or a horizontal
      # Collection, or the one list an array-typed items is.
      def collection_cell_key_lists(collection)
        prop = cell_key_property(collection)
        items = collection[:items]
        return nil unless binding_expression?(items)

        path = binding_data_path(items)
        sections = collection[:sections]
        if sections.is_a?(Array) && !sections.empty?
          lists = sections.each_with_index.select { |section, _| section.is_a?(Hash) && section['cell'] }.map do |_, index|
            source = "(#{path}?.sections?.[#{index}]?.cells?.data ?? [])"
            collection[:auto_tracking] && prop ? "enrichCellIds(#{source}, #{prop.to_json})" : source
          end
          "[#{lists.join(', ')}]"
        elsif collection_items_list?(items)
          "[#{path} ?? []]"
        elsif collection[:flow] || collection[:horizontal]
          "[#{path}?.sections?.[0]?.cells?.data ?? []]"
        else
          "(#{path}?.sections ?? []).map((section) => section.cells?.data ?? [])"
        end
      end

      # The Collection's cellIdProperty, or nil — a cell's key is its cellId
      # then (the SSoT's Collection.scrollTo).
      def cell_key_property(collection)
        prop = collection[:cell_id_property]
        prop.is_a?(String) && !prop.empty? ? prop : nil
      end

      # items bound to a property the layout declares as a list (`[T]`,
      # `Array`) — CollectionConverter#legacy_items_list_element's reading.
      def collection_items_list?(items)
        name = items[/\A@\{\s*([A-Za-z_]\w*)\s*\}\z/, 1]
        return false unless name

        !JsonUIShared::AttributeTypes.list_element((@config['_data_classes'] || {})[name]).nil?
      end

      def scroll_anchor_expr(anchor)
        %w[top center bottom].include?(anchor.to_s) ? "'#{anchor}'" : "'bottom'"
      end

      # `scrollAnimated` as scrollCollectionToItem's `animated`: a literal
      # false jumps, absent or true animates (the declared default), and a
      # binding decides at run time — true only when the bound value is true,
      # the reading sjui (`(data.x ?? false)`) and kjui (`(data.x ?: false)`)
      # give an unset bound value. Until 1.9.0 a binding was read as `true`
      # (measured on 46a54fc3, 2026-09-26; ticket
      # collection-attributes-declared-but-not-drawn-on-some-paths).
      def scroll_animated_arg(value)
        return "(#{binding_data_path(value)}) === true" if binding_expression?(value)

        value == false ? 'false' : 'true'
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
          type = drawn_type_of(json)
          id = json['id']
          if id.is_a?(String) && !id.empty? && !id.include?('@{')
            if type == 'TextField'
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

      # Component-level state hooks. None today: a static Segment / Radio used
      # to declare `selectedIndex` / `selectedValue` here — one fixed name per
      # kind, folded by name, and read by no markup — while the controls
      # stayed where they started (ticket
      # static-valued-controls-do-not-change-on-a-users-tap). A control's
      # own state is now the file's JsonUISeeded (#seeded_helper).
      def extract_state_variables(_json)
        []
      end

      # The one holder of every static-seeded control's state in a file:
      # `seed` starts it, the markup gets the value and its setter.
      def seeded_helper(typescript)
        signature = if typescript
                      '<T,>({ seed, children }: { seed: T; children: (value: T, set: (value: T) => void) => React.ReactNode })'
                    else
                      '({ seed, children })'
                    end
        <<~TSX.chomp

          // A control written with a static value starts there and the user changes it
          // (the value is a seed, as `defaultChecked` is): its state, handed to its markup.
          const JsonUISeeded = #{signature} => {
            const [value, setValue] = useState(seed);
            return <>{children(value, setValue)}</>;
          };
        TSX
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
          if drawn_type_of(json) == 'TabView' && json['tabs'].is_a?(Array)
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
            component_name = ComponentName.for_reference(class_name)
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
            component_name = ComponentName.for_reference(class_name)
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
        if drawn_type_of(json) == 'Embed' && json['screen'].is_a?(String)
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
        type = drawn_type_of(json)

        # Check for NetworkImage type (built-in but requires separate import)
        if type == 'NetworkImage'
          components << 'NetworkImage'
        end

        # Label linkable renders through the LinkifyText built-in — both the
        # literal and bound text shapes, and both arms of a bound-flag ternary.
        if type == 'Label' && json['linkable']
          components << 'LinkifyText'
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
        type = drawn_type_of(json)

        if type == 'Collection'
          # Modern sections format
          json['sections']&.each do |section|
            cell_type = ComponentName.for_reference(section['cell'])
            types << cell_type if cell_type
          end

          # Legacy cellClasses format
          json['cellClasses']&.each do |cell_class|
            cell_type = ComponentName.for_reference(cell_class)
            types << cell_type if cell_type
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
        return true if drawn_type_of(json) == 'Collection' &&
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

      # Every `data` declaration in this layout's own tree, raw: name => class.
      def declared_data_classes(json, found = {})
        case json
        when Hash
          if json['data'].is_a?(Array)
            json['data'].each { |d| found[d['name']] ||= d['class'] if d.is_a?(Hash) && d['name'].is_a?(String) }
          end
          json.each_value { |v| declared_data_classes(v, found) if v.is_a?(Hash) || v.is_a?(Array) }
        when Array
          json.each { |v| declared_data_classes(v, found) }
        end
        found
      end

      # Extract data from JSON - search for data-only elements in children (recursively)
      # A data-only element is { "data": [...] } with only the data key
      def extract_data_from_json(json)
        return [] unless json['child'].is_a?(Array)

        json['child'].each do |child|
          next unless child.is_a?(Hash)
          # Check if this child has only 'data' key (data-only element)
          if data_only_element?(child)
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
      # Its keys are the ones the layout wrote (Core::NodeKeys): the generator's
      # position stamp is not among them.
      def data_only_element?(child)
        return false unless child.is_a?(Hash)
        Core::NodeKeys.written(child) == ['data'] && child['data'].is_a?(Array)
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
