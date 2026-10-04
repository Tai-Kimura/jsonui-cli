# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative '../../core/config_manager'
require_relative '../../core/node_keys'
require_relative '../../core/frameworks'
require_relative '../../core/generated_marker'
require_relative '../../core/logger'
require_relative '../../core/templates'
require_relative '../../core/attribute_validator'
require_relative '../../core/normalization'
require_relative '../../core/binding_validator'
require_relative '../../core/resources/color_manager'
require_relative '../../react/react_generator'
require_relative '../../react/style_loader'
require_relative '../../core/layout_validator'
require_relative '../../core/generated_orphans'
require_relative '../../core/plural_validator'
require_relative '../../react/data_model_generator'
require_relative '../../react/viewmodel_generator'
require_relative '../../react/hook_generator'
require_relative '../../core/layout_variant'
require_relative '../../core/screen_index'
# Loaded here, not at the point that reports: the recording calls run
# earlier in the build than the report does, and a require sitting at
# the report would leave them raising NameError — which is the exact
# shape of the defect this file is being changed to fix.
require_relative '../../core/stage_failures'

module RjuiTools
  module CLI
    module Commands
      class BuildCommand
        def initialize(args)
          @args = args
          @config = Core::ConfigManager.load_config
          @validator = Core::AttributeValidator.new(:react)
          @binding_validator = Core::BindingValidator.new
          @all_warnings = []
          @binding_warnings = []
          @binding_errors = []
        end

        def execute
          Core::Logger.info('Building React components from JSON layouts...')

          # The app's own converter spellings, before anything reads a layout:
          # the validators and the data model classify a node by the type it
          # is drawn as, and a registered spelling is drawn as written
          # (shared/core/type_synonyms.rb, TypeSynonyms.app_types).
          JsonUIShared::TypeSynonyms.app_types = React::ReactGenerator.extension_types

          layouts_dir = @config['layouts_directory']

          unless Dir.exist?(layouts_dir)
            Core::Logger.error("Layouts directory not found: #{layouts_dir}")
            Core::Logger.info('Run "rjui init" first')
            exit 1
          end

          # Update StringManager from Strings directory
          begin
            update_string_manager
          rescue JsonUIShared::PluralValidator::ValidationError => e
            Core::Logger.error(e.message)
            exit 1
          end

          # Bindings first, for every layout: a layout whose bindings carry an
          # ERROR is not written by any writer below (Data, component,
          # ViewModel, hook) — its generated files stay as the last good build
          # left them (StageFailures.block_layout). Until jsonui-cli 1.9.8 the
          # bindings were checked inside the component loop, after the Data
          # models were written, so a failed build had already replaced them.
          prevalidate_bindings(layouts_dir)

          # Update Data models from JSON data sections
          update_data_models

          # Emit shared cellIdGenerator helper
          emit_cell_id_generator

          # Emit the screen-marker helper (screen identity / test support)
          emit_screen_marker_helper
          emit_interaction_stop_helper
          emit_partial_text_helper

          # Emit the Collection scroll-control helper (scrollTo /
          # defaultScrollAnchor / currentPage / onItemAppear)
          emit_collection_scroll_helper

          # Emit the relative-positioning helper (align*View / align*OfView)
          emit_relative_position_helper

          # Emit the autoShrink helper (autoShrink / minimumScaleFactor)
          emit_auto_shrink_helper

          # Emit the date-format helper (SelectBox dateStringFormat)
          emit_date_format_helper

          # Design U8: do the ids inside an include with an id carry the
          # include's prefix, as on iOS and Android? `jui build` decides it
          # (INCLUDE_ID_PREFIX_GATE_FROM) and hands the answer over.
          apply_include_id_prefix_decision

          # Resources (colors.json, strings.json, …) and Styles (reusable style
          # definitions) hold no layout — the one rule, ScreenIndex.layout_path?
          all_json_files = Dir.glob(File.join(layouts_dir, '**', '*.json')).select do |file|
            JsonUIShared::ScreenIndex.layout_path?(layouts_dir, file)
          end
          # Responsive variant files (home@regular.json) are generated
          # alongside their base screen, never standalone (06 track).
          json_files = all_json_files.reject do |file|
            JsonUIShared::LayoutVariant.variant?(file)
          end

          if json_files.empty?
            Core::Logger.warn('No JSON layout files found')
            # Nothing to build is not a failure — but what the stages before
            # this one could not do still is: it was recorded and then never
            # written, so the ledger came back empty (measured on 0f7140a3:
            # SwiftUI, colors.json unparseable, no layouts yet — exit 0, 0
            # entries). Ticket uikit-build-reports-success-after-a-binding-error.
            JsonUI::StageFailures.report!(Core::Logger)
            JsonUI::StageFailures.conclude(Core::Logger, nil) if JsonUI::StageFailures.any?
            return
          end

          # Extract hex colors from layout JSONs, auto-migrate legacy flat
          # colors.json to themed schema, and (re)generate ColorManager.{ts,js}
          # with dark/light/custom-mode support. Runs BEFORE the main generator
          # loop so hex→key rewrites land in the JSON before component JSX
          # emission.
          update_color_manager(all_json_files, layouts_dir)

          # First pass: build component name -> subdir mapping
          component_paths = {}
          json_files.each do |json_file|
            comp_name = to_pascal_case(File.basename(json_file, '.json'))
            relative_path = json_file.sub("#{layouts_dir}/", '')
            subdir = File.dirname(relative_path)
            subdir_parts = subdir.split('/')
            subdir_parts.shift if %w[pages components].include?(subdir_parts.first)
            nested_subdir = subdir_parts.join('/')
            component_paths[comp_name] = nested_subdir
          end

          # Pass component paths to generator for import resolution
          @config['_component_paths'] = component_paths

          # The layouts that take `jsonuiPath`, their root's position in the
          # include-expanded tree (React::IncludePaths): an included layout
          # holding a node that hands its handler a viewId without an id. The
          # include graph is the whole set of layouts, so it is read here,
          # before any of them is generated.
          @config['_path_stems'] = React::IncludePaths.stems_taking_path(
            json_files.each_with_object({}) do |json_file, trees|
              trees[File.basename(json_file, '.json')] =
                React::StyleLoader.load_and_merge(JSON.parse(File.read(json_file, encoding: 'UTF-8')))
            rescue JSON::ParserError
              next
            end
          ).to_a

          # Where an include call site reads the partial it hands data to.
          @config['_layouts_dir'] = File.expand_path(layouts_dir)

          generator = React::ReactGenerator.new(@config)
          generator.unknown_type_validator = @validator

          # Screen identity: only screens carry a marker (cells and partials
          # render inside a host and would each grow a false one). Built once
          # over the WHOLE layout tree — a layout's classification depends on
          # how OTHER layouts reference it, so it cannot be decided per file.
          screen_index = JsonUIShared::ScreenIndex.build(layouts_dir)
          screen_index.report_lines.each { |line| Core::Logger.info(line) }

          expected_component_paths = []
          json_files.each do |json_file|
            Core::Logger.info("Processing: #{json_file}")

            begin
              json_content = JSON.parse(File.read(json_file, encoding: 'UTF-8'))
              component_name = File.basename(json_file, '.json')
              component_name = to_pascal_case(component_name)

              # Apply styles before conversion
              json_content = React::StyleLoader.load_and_merge(json_content)

              # L1-normalized layouts (`$jui` marker from `jui build`)
              # take the canonical-only validation path; raw layouts keep
              # the alias-tolerant L0 path.
              @validator.normalized = Core::Normalization.canonicalized?(json_content)

              # Validate JSON attributes
              validate_component(json_content, json_file)

              # Bindings were validated before any writer ran
              # (prevalidate_bindings); a layout with an ERROR is not written.
              next if JsonUI::StageFailures.layout_blocked?(json_file)

              # Shared layout checks (autoChangeTrackingId without cellIdProperty, etc.)
              shared_warnings = JsonUIShared::LayoutValidator.validate_layout(
                json_content, source_path: File.basename(json_file),
                extension_definitions: Core::AttributeValidator.extension_definitions(:react)
              )
              JsonUIShared::LayoutValidator.print_warnings(shared_warnings) unless shared_warnings.empty?

              # An `:error` means the declaration was violated in a way the
              # converters cannot survive — they would receive a String where
              # the declaration promises a list and raise on `.each`. Refusing
              # the layout here reports the cause; converting it reports
              # whichever exception the first converter happened to hit.
              # Recorded, not raised: every other layout still generates, and
              # the ledger is what turns this into a non-zero exit.
              if JsonUIShared::LayoutValidator.blocking?(shared_warnings)
                reason = shared_warnings.select { |w| w[:level] == :error }
                                        .map { |w| w[:message] }.join('; ')
                JsonUI::StageFailures.record(
                  'layout', "#{json_file} was not generated: #{reason}"
                )
                next
              end

              # Preserve subdirectory structure from layouts
              # e.g., Layouts/components/home/activity_item.json -> generated/components/home/ActivityItem.tsx
              relative_path = json_file.sub("#{layouts_dir}/", '')
              subdir = File.dirname(relative_path)
              # Remove 'pages' or 'components' prefix if present, keep nested subdirs
              subdir_parts = subdir.split('/')
              subdir_parts.shift if %w[pages components].include?(subdir_parts.first)
              nested_subdir = subdir_parts.join('/')

              variants = JsonUIShared::LayoutVariant.variants_for(json_file)
              variant_comps = variants.keys.each_with_object({}) do |cls, map|
                map[cls] = "#{component_name}#{cls.capitalize}Variant"
              end

              layout_screen_id = JsonUIShared::ScreenIndex.screen_id_for_path(json_file)
              layout_screen_id = nil unless screen_index.screen?(layout_screen_id)

              output = generator.generate(component_name, json_content, subdir: nested_subdir,
                                          variants: variant_comps,
                                          # RAW file stem: the canonical
                                          # namespace_candidates keeps raw
                                          # spellings as trailing own
                                          # candidates, which the PascalCase
                                          # component-name round-trip loses.
                                          namespace_stem: File.basename(json_file, '.json'),
                                          screen_id: layout_screen_id)

              # Use .tsx for TypeScript, .jsx for JavaScript
              extension = @config['typescript'] ? '.tsx' : '.jsx'

              output_path = if nested_subdir.empty?
                              File.join(
                                @config['components_directory'],
                                "#{component_name}#{extension}"
                              )
                            else
                              File.join(
                                @config['components_directory'],
                                nested_subdir,
                                "#{component_name}#{extension}"
                              )
                            end

              FileUtils.mkdir_p(File.dirname(output_path))
              File.write(output_path, output)
              expected_component_paths << File.expand_path(output_path)

              Core::Logger.success("Generated: #{output_path}")

              # Generate one component per variant file. Variants keep the
              # base's Data type and string namespace — the media-query
              # dispatch in the base component selects the tree at runtime.
              base_namespace_stem = File.basename(json_file, '.json')
              variants.each do |cls, variant_file|
                v_json = JSON.parse(File.read(variant_file, encoding: 'UTF-8'))
                v_json = React::StyleLoader.load_and_merge(v_json)
                @validator.normalized = Core::Normalization.canonicalized?(v_json)
                validate_component(v_json, variant_file)
                next if JsonUI::StageFailures.layout_blocked?(variant_file)
                v_shared_warnings = JsonUIShared::LayoutValidator.validate_layout(
                  v_json, source_path: File.basename(variant_file),
                  extension_definitions: Core::AttributeValidator.extension_definitions(:react)
                )
                JsonUIShared::LayoutValidator.print_warnings(v_shared_warnings) unless v_shared_warnings.empty?

                # Same rule for a responsive variant: it is a layout too.
                if JsonUIShared::LayoutValidator.blocking?(v_shared_warnings)
                  v_reason = v_shared_warnings.select { |w| w[:level] == :error }
                                              .map { |w| w[:message] }.join('; ')
                  JsonUI::StageFailures.record(
                    'layout', "#{variant_file} was not generated: #{v_reason}"
                  )
                  next
                end

                v_name = variant_comps[cls]
                v_rel = variant_file.sub("#{layouts_dir}/", '')
                v_output = generator.generate(
                  v_name, v_json, subdir: nested_subdir,
                  data_type: component_name,
                  source_rel: "Layouts/#{v_rel}",
                  namespace_stem: base_namespace_stem
                )
                v_path = if nested_subdir.empty?
                           File.join(@config['components_directory'], "#{v_name}#{extension}")
                         else
                           File.join(@config['components_directory'], nested_subdir, "#{v_name}#{extension}")
                         end
                FileUtils.mkdir_p(File.dirname(v_path))
                File.write(v_path, v_output)
                expected_component_paths << File.expand_path(v_path)
                Core::Logger.success("Generated variant: #{v_path}")
              end
            rescue JSON::ParserError => e
              Core::Logger.error("Invalid JSON in #{json_file}: #{e.message}")
              JsonUI::StageFailures.record(
                'layout', "#{json_file} was not generated: #{e.message}"
              )
            rescue StandardError => e
              # Carrying on is right — one bad layout should not stop the
              # other seventeen — but the run then finished with `Build
              # completed!` and exit 0 while a component was missing. That
              # is why a defect in the colour path went four releases
              # unnoticed: the exception reached neither the exit code nor
              # the closing line, and the error scrolled past.
              Core::Logger.error("Error processing #{json_file}: #{e.message}")
              JsonUI::StageFailures.record(
                'layout', "#{json_file} was not generated: #{e.message}"
              )
            end
          end

          # Generate ViewModels if enabled
          generate_viewmodels if @config['generate_viewmodels'] != false

          # Generate hooks for ViewModels if enabled
          generate_hooks if @config['generate_hooks'] != false

          # Ensure built-in components (NetworkImage etc.) exist
          ensure_builtin_components

          # Prune orphan outputs (files under generated dirs whose source
          # JSON was moved or deleted). Without this, stale outputs linger
          # with out-of-date markers/content and `jui lint-generated` reports
          # them as missing markers.
          prune_orphan_components(expected_component_paths)
          prune_orphan_viewmodel_bases(json_files)
          prune_layout_orphans
          prune_other_language_copies
          prune_stale_helpers

          # Print all collected warnings at the end
          print_validation_summary
          print_binding_warnings
          print_binding_errors

          # Error-severity canonical binding rules (binding_semantics.json
          # validatorRules) always fail the build
          if @binding_errors.any?
            # Which layouts were not written (StageFailures.block_layout) —
            # said before the exit, which used to come before the ledger.
            JsonUI::StageFailures.report!(Core::Logger)
            Core::Logger.error("Build failed: #{@binding_errors.size} binding error(s)")
            exit 1
          end

          # Stages that failed while the build carried on. Prints nothing
          # when nothing failed, so a healthy run is unchanged.
          JsonUI::StageFailures.report!(Core::Logger)

          # And the closing line does not say completed when it did not.
          # "Build completed!" beside an error the reader has already
          # scrolled past is what let a broken layout look like a clean
          # run. The exit code is left alone deliberately: a partial build
          # is a legitimate outcome here, and stopping it would break the
          # window every consuming project builds in. What was missing is
          # that the last line stops claiming otherwise.
          JsonUI::StageFailures.conclude(Core::Logger, 'Build completed!')
        end

        def prune_orphan_components(expected_paths)
          components_dir = @config['components_directory']
          return unless components_dir && Dir.exist?(components_dir)

          expected_set = expected_paths.to_set
          extension_glob = @config['typescript'] ? '*.tsx' : '*.jsx'
          all_generated = Dir.glob(File.join(components_dir, '**', extension_glob))

          # A layout `jui build` refused (StageFailures.block_layout) produced
          # nothing this run; its component (and its variants') stay as the
          # last build left them, so they are not orphans.
          blocked = JsonUI::StageFailures.blocked_layouts.keys.map do |f|
            to_pascal_case(JsonUIShared::LayoutVariant.split(File.basename(f, '.json')).first)
          end

          removed = []
          all_generated.each do |path|
            abs = File.expand_path(path)
            next if expected_set.include?(abs)
            name = File.basename(path, File.extname(path))
            next if blocked.any? { |b| name == b || (name.start_with?(b) && name.end_with?('Variant')) }
            File.delete(path)
            removed << path
          end

          return if removed.empty?

          Core::Logger.info("Pruned #{removed.size} orphan component(s):")
          removed.each { |p| Core::Logger.info("  - #{p}") }

          cleanup_empty_dirs(components_dir)
        end

        def prune_orphan_viewmodel_bases(json_files)
          vm_base_dir = @config['generated_viewmodels_directory']
          return unless vm_base_dir && Dir.exist?(vm_base_dir)

          # Current viewmodel_generator writes Base files flat at the root
          # of generated_viewmodels_directory, keyed by PascalCase name.
          # Anything nested deeper is by definition an orphan from when the
          # Python web_generator used to emit subdir-aware paths.
          layouts_dir = @config['layouts_directory']
          expected_names = Dir.glob(File.join(layouts_dir, '**', '*.json'))
            .select { |f| JsonUIShared::ScreenIndex.layout_path?(layouts_dir, f) }
            .reject { |f| JsonUIShared::LayoutVariant.variant?(f) }
            .map { |f| to_pascal_case(File.basename(f, '.json')) }
            .to_set

          extension = @config['typescript'] ? '.ts' : '.js'
          all_bases = Dir.glob(File.join(vm_base_dir, '**', "*ViewModelBase#{extension}"))

          removed = []
          all_bases.each do |path|
            rel = path.sub("#{vm_base_dir}/", '')
            rel_parts = rel.split('/')
            basename = File.basename(rel_parts.last, extension).sub(/ViewModelBase$/, '')

            if rel_parts.length == 1 && expected_names.include?(basename)
              # Flat path with matching source → keep
              next
            end
            # Subdir path or no matching source → orphan
            File.delete(path)
            removed << path
          end

          return if removed.empty?

          Core::Logger.info("Pruned #{removed.size} orphan ViewModelBase file(s):")
          removed.each { |p| Core::Logger.info("  - #{p}") }

          cleanup_empty_dirs(vm_base_dir)
        end

        # A deleted layout's Data model and hook, by the rule the three faces
        # share (lib/core/generated_orphans.rb): deleted when the file carries
        # @generated, sits where the config puts that output, and no layout
        # has its name. A hand-written ViewModel of that name is named, not
        # deleted. The two prunes above predate it and keep their own rules.
        def prune_layout_orphans
          data = React::DataModelGenerator.new
          hooks = React::HookGenerator.new
          orphans = JsonUIShared::GeneratedOrphans
          kinds = [
            orphans::Kind.new(dir: data.data_dir, owner: :generator,
                              pattern: /\A(?<name>[A-Za-z0-9_]+)Data\.(?:ts|js)\z/),
            orphans::Kind.new(dir: hooks.hooks_dir, owner: :generator,
                              pattern: /\Ause(?<name>[A-Za-z0-9_]+)ViewModel\.(?:ts|js)\z/),
            orphans::Kind.new(dir: hooks.viewmodels_dir, owner: :user,
                              pattern: /\A(?<name>[A-Za-z0-9_]+)ViewModel\.(?:ts|js)\z/)
          ]
          result = orphans.sweep(layouts_dir: data.layouts_dir, kinds: kinds)
          orphans.report_lines(result, base: data.source_path).each do |level, line|
            level == :warn ? Core::Logger.warn(line) : Core::Logger.info(line)
          end
        end

        # The helpers the build writes at the top of generated_directory
        # (screenMarker, interactionStop, includeId, ...). A helper this build
        # did not write stays behind otherwise — one a later version dropped,
        # one an earlier (or later) version added, or includeId from a
        # `jui build` that turned the include prefix on, followed by a
        # standalone `rjui build` that does not (ticket
        # rjui-clean-keeps-a-helper-the-running-version-no-longer-emits). Every
        # build, not only `--clean`: the rule the layout-orphan sweep follows.
        #
        # Deleted: a file directly in generated_directory that `rjui build`
        # marked as its own — the @generated sentinel AND its `Generator: rjui
        # build` line — and that no emitter wrote this run. Named and kept: a
        # file there carrying @generated under another generator's name (not
        # provably ours). A file without the sentinel is the user's and is
        # left alone silently. Not candidates: the outputs other stages own
        # at the same level (ColorManager / theme.css — the colour stage, which
        # can fail and carry on without rewriting them; StringManager — the
        # strings stage), and everything below the top level (components,
        # data, hooks, view model bases have their own prunes). Skipped when
        # generated_directory is also one of those output directories.
        HELPER_OWNED_ELSEWHERE = %w[ColorManager StringManager theme].freeze
        HELPER_GENERATOR_LINE = /Generator:\s+rjui build\s*$/.freeze

        def prune_stale_helpers
          generated_dir = @config['generated_directory'] || 'src/generated'
          return unless Dir.exist?(generated_dir)

          root = File.expand_path(generated_dir)
          shared = [
            @config['components_directory'], @config['data_directory'], @config['hooks_directory'],
            @config['generated_viewmodels_directory'], @config['viewmodels_directory'],
            @config['extensions_directory'], @config['lib_directory']
          ].compact.map { |dir| File.expand_path(dir) }
          return if shared.include?(root)

          emitted = @emitted_helpers || Set.new
          removed = []
          kept = []
          Dir.children(generated_dir).sort.each do |name|
            path = File.join(generated_dir, name)
            next unless File.file?(path)
            next unless %w[.ts .js .tsx .jsx].include?(File.extname(name))
            next if HELPER_OWNED_ELSEWHERE.include?(File.basename(name, File.extname(name)))
            next if emitted.include?(File.expand_path(path))

            head = File.foreach(path).first(JsonUIShared::GeneratedOrphans::HEAD_LINES)
            next unless head.any? { |line| line.include?(JsonUIShared::GeneratedOrphans::SENTINEL) }

            if head.any? { |line| line.match?(HELPER_GENERATOR_LINE) }
              File.delete(path)
              removed << path
            else
              kept << path
            end
          end

          unless removed.empty?
            Core::Logger.info("Pruned #{removed.size} generated helper(s) this build no longer writes:")
            removed.each { |p| Core::Logger.info("  - #{p}") }
          end
          return if kept.empty?

          Core::Logger.warn("#{kept.size} file(s) in #{generated_dir} carry @generated but not `rjui build`'s mark " \
                            'and this build did not write them; they were kept:')
          kept.each { |p| Core::Logger.warn("  - #{p}: delete it by hand if nothing imports it") }
        end

        # A project that changed `typescript` keeps what earlier builds wrote
        # in the other language — `Home.tsx` beside the `Home.jsx` this build
        # wrote — and both answer `import Home from '.../Home'` (which one a
        # bundler takes is its extension order). The layout-orphan sweep does
        # not see them: their layouts are all there. So each file in an
        # output directory the config declares, in the OTHER language, whose
        # same-named file in this language exists, is replaced
        # (GeneratedOrphans.sweep_replaced): deleted when it is the
        # generator's by the test its own refresh uses — the @generated
        # sentinel; NetworkImage / LinkifyText the ReactJsonUI header the
        # built-in refresh reads; useColorMode its sentinel or its pre-banner
        # line — and named otherwise (Configuration is the user's once written;
        # any file the user wrote). A ViewModel the user wrote in the other
        # language is named too: its base and hook are written in its language
        # (viewmodel_generator follows the file). EmbedContainer is `rjui
        # init`'s and no build writes it, so nothing in this language replaced
        # it: when it is init's copy unchanged — the init mark, and the
        # template of its language byte for byte — this language's copy is
        # written and the old one deleted; otherwise it is named and kept
        # (4f ruling 2026-09-26, round 8). The mark alone is not the test here,
        # as it is for NetworkImage: build refreshes NetworkImage whenever it
        # differs, so its mark means the tool owns every byte; EmbedContainer
        # is never refreshed, and an edit below its header comment would be
        # the user's. Until jsonui-cli 1.9.0 all of them stayed, unnamed.
        OTHER_LANGUAGE = { '.ts' => '.js', '.tsx' => '.jsx', '.js' => '.ts', '.jsx' => '.tsx' }.freeze
        BUILTIN_OWNED = {
          'NetworkImage' => ->(text) { text.include?('Generated by ReactJsonUI') },
          'LinkifyText' => ->(text) { text.include?('Generated by ReactJsonUI') },
          'useColorMode' => lambda { |text|
            text.include?(Core::GeneratedMarker::SENTINEL) || text.include?(LEGACY_USE_COLOR_MODE_MARKER)
          },
          'Configuration' => ->(_text) { false },
          'EmbedContainer' => ->(text) { EMBED_CONTAINER_TEMPLATES.value?(text) }
        }.freeze
        # `rjui init`'s mark on the EmbedContainer it writes.
        EMBED_CONTAINER_MARK = 'Generated by rjui_tools `rjui init`'
        # The copy init writes, by the extension it takes.
        EMBED_CONTAINER_TEMPLATES = {
          '.tsx' => File.read(Core::Templates.path('EmbedContainer.tsx', 'typescript' => true)),
          '.jsx' => File.read(Core::Templates.path('EmbedContainer.tsx', 'typescript' => false))
        }.freeze

        def prune_other_language_copies
          typescript = @config['typescript'] ? true : false
          stale_exts = typescript ? %w[.js .jsx] : %w[.ts .tsx]
          dirs = [
            @config['generated_directory'] || 'src/generated',
            @config['components_directory'], @config['data_directory'], @config['hooks_directory'],
            @config['generated_viewmodels_directory'],
            @config['extensions_directory'] || 'src/components/extensions',
            @config['lib_directory'] || 'src/lib/jsonui'
          ].compact.uniq.select { |dir| Dir.exist?(dir) }
          pairs = dirs.flat_map do |dir|
            Dir.glob(File.join(dir, '**', '*')).select { |path| File.file?(path) && stale_exts.include?(File.extname(path)) }
          end.uniq.map do |old|
            ext = File.extname(old)
            [old, old.sub(/#{Regexp.escape(ext)}\z/, OTHER_LANGUAGE.fetch(ext))]
          end
          unreplaced = replace_embed_container(pairs)
          pairs -= unreplaced.map { |old, current, _| [old, current] }
          owned = lambda do |path|
            head = File.foreach(path).first(JsonUIShared::GeneratedOrphans::HEAD_LINES).join
            rule = BUILTIN_OWNED[File.basename(path, File.extname(path))]
            rule ? rule.call(File.read(path)) : head.include?(JsonUIShared::GeneratedOrphans::SENTINEL)
          end
          result = JsonUIShared::GeneratedOrphans.sweep_replaced(pairs, owned: owned)
          language = typescript ? 'TypeScript' : 'JavaScript'
          unless result.removed.empty?
            Core::Logger.info("Pruned #{result.removed.size} generated file(s) the #{language} output replaces:")
            result.removed.each { |old, current| Core::Logger.info("  - #{old} (now #{File.basename(current)})") }
          end
          unless result.kept.empty?
            Core::Logger.warn("#{result.kept.size} file(s) the #{language} output replaces were kept:")
            result.kept.each do |old, current|
              Core::Logger.warn("  - #{old}: #{File.basename(current)} replaces it, but it is not marked as the generator's, " \
                                'so it was not deleted — delete it (or move what you changed into the new one) by hand')
            end
          end
          unreplaced.each do |old, current, reason|
            if File.exist?(current)
              Core::Logger.warn("#{old} is in the other language and was kept: #{reason}. #{File.basename(current)} is beside " \
                                'it and answers the same import — delete it by hand (after moving what you changed into ' \
                                "#{File.basename(current)}) or keep it.")
            else
              Core::Logger.warn("#{old} is in the other language and was kept: #{reason}, so #{File.basename(current)} was not " \
                                "written in its place — the #{language} screens import it as it is. Replace it by hand " \
                                "(`rjui init` writes #{File.basename(current)} when it is absent) or keep it.")
            end
          end
          name_other_language_viewmodels(stale_exts, language)
        end

        # EmbedContainer in the other language: when it is init's copy
        # unchanged, this language's copy is written (as init writes it) when
        # there is none, so the sweep replaces the old one; when it is not, it
        # is returned — [old, this language's copy, why] — to be named and kept
        # (and taken out of the sweep), and nothing is written beside it (two
        # copies would answer one import).
        def replace_embed_container(pairs)
          # `map { }.compact`, not `filter_map` (Ruby 2.7): spec/react/
          # ruby_baseline_spec holds lib to 2.6.
          pairs.map do |old, current|
            next unless File.basename(old, File.extname(old)) == 'EmbedContainer'

            text = File.read(old)
            if BUILTIN_OWNED.fetch('EmbedContainer').call(text)
              File.write(current, File.read(Core::Templates.path('EmbedContainer.tsx', @config))) unless File.exist?(current)
              next
            end

            reason = if text.include?(EMBED_CONTAINER_MARK)
                       "it carries `rjui init`'s mark but is not the copy init writes (edited, or an older template)"
                     else
                       "it does not carry `rjui init`'s mark (the user's)"
                     end
            [old, current, reason]
          end.compact
        end

        def name_other_language_viewmodels(stale_exts, language)
          dir = @config['viewmodels_directory']
          return unless dir && Dir.exist?(dir)

          models = Dir.glob(File.join(dir, '**', '*ViewModel*')).select { |path| stale_exts.include?(File.extname(path)) }.sort
          return if models.empty?

          Core::Logger.warn("#{models.size} ViewModel(s) of this #{language} project are in the other language; " \
                            'their bases and hooks are written in their language, to match:')
          models.each { |path| Core::Logger.warn("  - #{path}") }
        end

        def cleanup_empty_dirs(root)
          Dir.glob(File.join(root, '**/*'))
             .select { |p| File.directory?(p) && (Dir.entries(p) - %w[. ..]).empty? }
             .sort_by { |p| -p.length }
             .each do |p|
            Dir.rmdir(p)
            Core::Logger.info("  Removed empty dir: #{p}")
          end
        end

        private

        # An emitter's record of the helper it wrote, for prune_stale_helpers.
        def note_emitted_helper(path)
          (@emitted_helpers ||= Set.new) << File.expand_path(path)
        end

        def to_pascal_case(string)
          string.split(/[-_]/).map(&:capitalize).join
        end

        def ensure_builtin_components
          extensions_dir = @config['extensions_directory'] || 'src/components/extensions'
          FileUtils.mkdir_p(extensions_dir)

          network_image_path = File.join(extensions_dir, Core::Templates.file_name('NetworkImage.tsx', @config))
          template_path = Core::Templates.path('network_image.tsx', @config)
          if File.exist?(template_path)
            template = Core::Frameworks.apply_directive(File.read(template_path), Core::Frameworks.for(@config))
            if !File.exist?(network_image_path)
              File.write(network_image_path, template)
              Core::Logger.success("Created built-in component: #{network_image_path}")
            else
              existing = File.read(network_image_path)
              # Refresh library-owned copies when the shipped template
              # changed (the converter emits against this contract, so a
              # stale copy breaks typecheck). A copy without the generated
              # header is treated as user-customized and left alone.
              if existing != template && existing.include?('Generated by ReactJsonUI')
                File.write(network_image_path, template)
                Core::Logger.success("Refreshed built-in component: #{network_image_path}")
              end
            end
          end

          ensure_linkify_text_component
          ensure_configuration_template
        end

        # Copy the LinkifyText built-in (Label `linkable` runtime) into the
        # consumer tree. Same ownership contract as NetworkImage: a copy still
        # carrying the generated header refreshes when the shipped template
        # changes; a copy without it is user-customized and left alone.
        def ensure_linkify_text_component
          extensions_dir = @config['extensions_directory'] || 'src/components/extensions'
          FileUtils.mkdir_p(extensions_dir)

          target_path = File.join(extensions_dir, Core::Templates.file_name('LinkifyText.tsx', @config))
          template_path = Core::Templates.path('linkify_text.tsx', @config)
          return unless File.exist?(template_path)

          template = Core::Frameworks.apply_directive(File.read(template_path), Core::Frameworks.for(@config))
          if !File.exist?(target_path)
            File.write(target_path, template)
            Core::Logger.success("Created built-in component: #{target_path}")
          else
            existing = File.read(target_path)
            if existing != template && existing.include?('Generated by ReactJsonUI')
              File.write(target_path, template)
              Core::Logger.success("Refreshed built-in component: #{target_path}")
            end
          end
        end

        # Copy the Configuration.ts template (FontSpec / Configuration.Font)
        # into the host app's @/lib/jsonui/ directory so generated components
        # can import { Configuration } and route font specs through the
        # host-supplied fontProvider. Idempotent — leaves an existing copy
        # alone (consumers may have customized the provider field).
        def ensure_configuration_template
          lib_dir = @config['lib_directory'] || 'src/lib/jsonui'
          FileUtils.mkdir_p(lib_dir)

          target_path = File.join(lib_dir, Core::Templates.file_name('Configuration.ts', @config))
          return if File.exist?(target_path)

          template_path = Core::Templates.path('Configuration.ts', @config)
          return unless File.exist?(template_path)

          File.write(target_path, File.read(template_path))
          Core::Logger.success("Created Configuration template: #{target_path}")
        end

        # Validate component and its children recursively
        # @param component [Hash] The component to validate
        # @param file_path [String] The file path for error messages
        # @param parent_orientation [String] The parent's orientation ('horizontal' or 'vertical')
        def validate_component(component, file_path, parent_orientation = nil)
          return unless component.is_a?(Hash)

          # Skip style-only entries and data declarations
          return if component.key?('style') && Core::NodeKeys.written(component).size == 1
          return if component.key?('data') && !component.key?('type')

          if component['type']
            warnings = @validator.validate(component, nil, parent_orientation)
            warnings.each do |warning|
              @all_warnings << { file: file_path, message: warning }
            end
          end

          # Get this component's orientation for children validation
          # View default orientation is 'vertical' (matches sjui/kjui behavior)
          # If not specified, use default for View types, otherwise inherit from parent
          # (the node as drawn: an HStack is a View with orientation
          # horizontal, and its children are laid out so — type_synonyms.rb)
          drawn = JsonUIShared::TypeSynonyms.drawn(component)
          current_orientation = drawn['orientation'] ||
            (drawn['type'] == 'View' ? 'vertical' : parent_orientation)

          # Validate children recursively
          if component['child']
            children = component['child'].is_a?(Array) ? component['child'] : [component['child']]
            children.each { |child| validate_component(child, file_path, current_orientation) }
          end
        end

        # Print validation summary at the end of build
        def print_validation_summary
          return if @all_warnings.empty?

          puts
          Core::Logger.warn("Validation warnings found: #{@all_warnings.size}")
          puts

          # Group warnings by file
          grouped = @all_warnings.group_by { |w| w[:file] }
          grouped.each do |file, warnings|
            puts "\e[33m  #{file}:\e[0m"
            warnings.each do |w|
              puts "\e[33m    ⚠️  #{w[:message]}\e[0m"
            end
          end
          puts
        end

        # Every layout's bindings (variants included), before anything is
        # written; a layout with an ERROR is blocked. A layout that cannot be
        # read is left to the stage that reads it, which reports it.
        def prevalidate_bindings(layouts_dir)
          Dir.glob(File.join(layouts_dir, '**', '*.json')).sort.each do |file|
            next unless JsonUIShared::ScreenIndex.layout_path?(layouts_dir, file)

            begin
              json = React::StyleLoader.load_and_merge(JSON.parse(File.read(file, encoding: 'UTF-8')))
            rescue StandardError
              next
            end
            before = @binding_errors.size
            validate_bindings(json, file)
            found = @binding_errors.size - before
            JsonUI::StageFailures.block_layout(file, "#{found} binding error(s)") if found.positive?
          end
        end

        # Validate binding expressions for business logic
        def validate_bindings(json_content, file_path)
          file_name = File.basename(file_path)
          @binding_validator.validate(json_content, file_name)
          # The validator resets its channels per validate() call — collect
          # both here so errors survive across files
          @binding_warnings.concat(@binding_validator.warnings)
          @binding_errors.concat(@binding_validator.errors)
        end

        # Print binding warnings at the end of build
        def print_binding_warnings
          return if @binding_warnings.empty?

          puts
          Core::Logger.warn("Binding warnings found: #{@binding_warnings.size}")
          puts "  Business logic detected in bindings. Move this logic to ViewModel."
          puts

          @binding_warnings.each do |warning|
            puts "\e[33m  ⚠️  #{warning}\e[0m"
          end
          puts
        end

        # Print error-severity canonical rule violations at the end of build
        def print_binding_errors
          return if @binding_errors.empty?

          puts
          Core::Logger.error("Binding errors found: #{@binding_errors.size}")
          puts "  Canonical binding rules (severity: error) were violated."
          puts

          @binding_errors.each do |error|
            puts "\e[31m  ✖  #{error}\e[0m"
          end
          puts
        end

        def update_data_models
          Core::Logger.info('Generating Data models...')
          data_generator = React::DataModelGenerator.new
          data_generator.update_data_models
        rescue StandardError => e
          Core::Logger.error("Error generating data models: #{e.message}")
          # The stage stops at the first layout it cannot read, so the ones
          # after it have no Data model either. Until 1.9.0 this ERROR
          # scrolled past "Build completed!" (ticket
          # uikit-build-reports-success-after-a-binding-error).
          JsonUI::StageFailures.record('data models', "the Data models were not generated: #{e.message}")
        end

        def generate_viewmodels
          Core::Logger.info('Generating ViewModels...')
          viewmodel_generator = React::ViewModelGenerator.new
          viewmodel_generator.generate_viewmodels
        rescue StandardError => e
          Core::Logger.error("Error generating viewmodels: #{e.message}")
          JsonUI::StageFailures.record('viewmodels', "the ViewModels were not generated: #{e.message}")
        end

        def generate_hooks
          viewmodels_dir = @config['viewmodels_directory'] || 'src/viewmodels'
          return unless Dir.exist?(viewmodels_dir)

          viewmodel_files = Dir.glob(File.join(viewmodels_dir, '*ViewModel.*'))
          return if viewmodel_files.empty?

          Core::Logger.info('Generating hooks for ViewModels...')
          hook_generator = React::HookGenerator.new
          hook_generator.generate_hooks
        rescue StandardError => e
          Core::Logger.error("Error generating hooks: #{e.message}")
          JsonUI::StageFailures.record('hooks', "the ViewModel hooks were not generated: #{e.message}")
        end

        def update_color_manager(json_files, layouts_dir)
          resources_dir = File.join(layouts_dir, 'Resources')
          FileUtils.mkdir_p(resources_dir)

          # The generator-emitted ColorManager lives alongside the other
          # @generated files (StringManager, cellIdGenerator). Use the same
          # directory so the import path `@/generated/ColorManager` resolves.
          config = @config.merge('source_path' => Dir.pwd)
          source_path = Dir.pwd

          manager = Core::Resources::ColorManager.new(config, source_path, resources_dir)
          manager.process_colors(json_files, json_files.size, 0, config)

          # Tell the Tailwind mapper which color names are theme-safe
          # (mode-complete in colors.json = mirrored in the web @theme) so an
          # off-palette name resolves back to its hex instead of emitting a
          # dead `bg-<name>` class (rjui-offpalette-hex-dead-tailwind-class).
          React::TailwindMapper.configure_palette(
            theme_safe: manager.mode_complete_keys,
            fallbacks: manager.fallback_hexes
          )

          ensure_use_color_mode_hook
        rescue StandardError => e
          Core::Logger.error("Error processing colors: #{e.message}")
          JsonUI::StageFailures.record(
            'colors', "colors were not processed: #{e.message}"
          )
        end

        # Copy the useColorMode React hook template to @/hooks/ so consumers
        # can subscribe to ColorManager mode changes. Library-owned copies
        # (still carrying the generated header) refresh when the shipped
        # template changes — same contract as ensure_builtin_components; a
        # copy without the header is treated as user-customized and left alone.
        #
        # Ownership is decided by the @generated sentinel, the same marker
        # `jui lint-generated` checks. Copies shipped before the template
        # carried the banner are recognized by their JSDoc line instead, so
        # they refresh once into the sentinel form
        # (rjui-usecolormode-template-lacks-generated-sentinel).
        LEGACY_USE_COLOR_MODE_MARKER = 'Generated by rjui build'

        def ensure_use_color_mode_hook
          hooks_dir = @config['hooks_directory'] || 'src/hooks'
          FileUtils.mkdir_p(hooks_dir)

          target_path = File.join(hooks_dir, Core::Templates.file_name('useColorMode.ts', @config))
          template_path = Core::Templates.path('use_color_mode.ts', @config)
          return unless File.exist?(template_path)

          template = Core::Frameworks.apply_directive(File.read(template_path), Core::Frameworks.for(@config))
          if !File.exist?(target_path)
            File.write(target_path, template)
            Core::Logger.success("Created hook: #{target_path}")
          else
            existing = File.read(target_path)
            library_owned = existing.include?(Core::GeneratedMarker::SENTINEL) ||
                            existing.include?(LEGACY_USE_COLOR_MODE_MARKER)
            if existing != template && library_owned
              File.write(target_path, template)
              Core::Logger.success("Refreshed hook: #{target_path}")
            end
          end
        end

        def update_string_manager
          strings_dir = @config['strings_directory'] || 'src/Strings'
          generated_dir = @config['generated_directory'] || 'src/generated'
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          string_manager_path = File.join(generated_dir, "StringManager.#{extension}")
          # If we flipped modes, delete the stale file from the other extension
          # so imports (`from '@/generated/StringManager'`) don't resolve twice.
          other_path = File.join(generated_dir, "StringManager.#{is_ts ? 'js' : 'ts'}")
          File.delete(other_path) if File.exist?(other_path)
          layouts_dir = @config['layouts_directory'] || 'Layouts'
          resources_strings_json = File.join(layouts_dir, 'Resources', 'strings.json')

          languages = @config['languages'] || ['en', 'ja']
          default_language = @config['default_language'] || 'en'

          # Read strings from both sources
          strings_data = {}
          plurals_data = {}
          languages.each do |lang|
            strings_data[lang] = {}
            plurals_data[lang] = {}
          end
          plural_errors = []

          # Source 1: Layouts/Resources/strings.json (sjui/kjui shared format)
          # Format: { "screen_name": { "key": { "en": "Hello", "ja": "こんにちは" } } }
          if File.exist?(resources_strings_json)
            shared_strings = JSON.parse(File.read(resources_strings_json, encoding: 'UTF-8'))

            # Plural entries (CLDR cardinal): schema check + layouts must not
            # reference plural keys directly (VM-only in v1 — converters
            # inline layout strings statically and cannot pass a count).
            plural_errors.concat(JsonUIShared::PluralValidator.validate_strings(shared_strings))
            layout_files = Dir.glob(File.join(layouts_dir, '**', '*.json')).select do |file|
              JsonUIShared::ScreenIndex.layout_path?(layouts_dir, file)
            end
            plural_errors.concat(
              JsonUIShared::PluralValidator.validate_layout_references(shared_strings, layout_files)
            )

            if plural_errors.empty?
              shared_strings.each do |file_prefix, keys|
                next unless keys.is_a?(Hash)

                keys.each do |key, value|
                  full_key = "#{file_prefix}_#{key}"
                  if JsonUIShared::PluralValidator.plural_value?(value)
                    languages.each do |lang|
                      forms = JsonUIShared::PluralValidator.plural_forms(value, lang, default_language)
                      plurals_data[lang][full_key] = forms if forms
                    end
                  elsif value.is_a?(Hash)
                    # Multi-language: { "en": "Hello", "ja": "こんにちは" }
                    languages.each do |lang|
                      resolved = value[lang] || value[default_language] || value.values.first || ''
                      strings_data[lang][full_key] = resolved
                    end
                  else
                    # Single string (default language only)
                    languages.each do |lang|
                      strings_data[lang][full_key] = value.to_s
                    end
                  end
                end
              end
              Core::Logger.info("Loaded strings from #{resources_strings_json}")
            end
          end

          # Source 2: src/Strings/en.json, ja.json (legacy per-language files)
          # These override shared strings if both exist
          if Dir.exist?(strings_dir)
            languages.each do |lang|
              lang_file = File.join(strings_dir, "#{lang}.json")
              if File.exist?(lang_file)
                lang_strings = JSON.parse(File.read(lang_file, encoding: 'UTF-8'))
                lang_strings.each_key do |key|
                  value = lang_strings[key]
                  next unless value.is_a?(Hash) && value.key?('plural')
                  plural_errors << "#{lang_file}: '#{key}' — plural entries are not supported in " \
                                   'legacy per-language files; move the key to ' \
                                   "#{resources_strings_json}"
                  lang_strings.delete(key)
                end
                strings_data[lang].merge!(lang_strings)
              end
            end
          end

          unless plural_errors.empty?
            plural_errors.each { |e| Core::Logger.error(e) }
            raise JsonUIShared::PluralValidator::ValidationError,
                  "strings.json plural validation failed (#{plural_errors.length} error(s))"
          end

          # Skip if no strings from any source
          return if strings_data.values.all?(&:empty?) && plurals_data.values.all?(&:empty?)

          # Generate StringManager content
          strings_json = JSON.pretty_generate(strings_data)
          marker_header = Core::GeneratedMarker.comment_header(
            source: "StringManager (strings from Strings/*.json)",
            generator: "rjui build"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = if is_ts
                      string_manager_typescript_content(strings_json, default_language, marker_header, marker_footer)
                    else
                      string_manager_javascript_content(strings_json, default_language, marker_header, marker_footer)
                    end

          # Plural support is injected only when plural keys exist, so
          # projects without plurals keep a byte-identical StringManager.
          content = augment_with_plurals(content, plurals_data, default_language, is_ts: is_ts)

          FileUtils.mkdir_p(generated_dir)
          File.write(string_manager_path, content)
          Core::Logger.success("Updated: #{string_manager_path}")
        end

        # camelCase spelling matching createCamelCaseProxy in the generated
        # StringManager (underscore collapses before [a-z0-9]).
        def plural_camel_key(snake_key)
          snake_key.gsub(/_([a-z0-9])/) { Regexp.last_match(1).upcase }
        end

        # Inject the plural runtime into the generated StringManager:
        # - `plurals` tables (lang -> key -> CLDR category -> body) resolved
        #   via Intl.PluralRules with `{count}` substitution
        # - loud failures for count-less access to plural keys (proxy
        #   properties + getString/getDefaultString), which would otherwise
        #   render as undefined/empty
        # Anchor-based insertion keeps the base templates byte-stable when no
        # plural key exists.
        def augment_with_plurals(content, plurals_data, default_language, is_ts:)
          return content if plurals_data.nil? || plurals_data.values.all?(&:empty?)

          canonical = {}
          plurals_data.each_value do |keys|
            keys.each_key do |full_key|
              canonical[full_key] = full_key
              camel = plural_camel_key(full_key)
              canonical[camel] = full_key unless camel == full_key
            end
          end

          plurals_json = JSON.pretty_generate(plurals_data)
          canonical_json = JSON.pretty_generate(canonical)

          plurals_decl = is_ts ? 'const plurals: PluralsRoot =' : 'const plurals ='
          canonical_decl = is_ts ? 'const PLURAL_KEY_CANONICAL: Record<string, string> =' : 'const PLURAL_KEY_CANONICAL ='
          tables = +''
          tables << "type PluralsRoot = Record<string, Record<string, StringMap>>;\n\n" if is_ts
          tables << <<~JS
            // Plural tables compiled from strings.json `plural` entries (CLDR
            // cardinal, `{count}` placeholder). Plural keys are VM-only — resolve
            // them with StringManager.plural(key, count) (or getDefaultPlural for
            // SSR-safe seed code); count-less access throws.
            #{plurals_decl} #{plurals_json};

            // Both snake_case and camelCase spellings of every plural key, mapped
            // to the canonical (snake_case) key.
            #{canonical_decl} #{canonical_json};

          JS
          content = content.sub("const LANGUAGE_STORAGE_KEY") { "#{tables}const LANGUAGE_STORAGE_KEY" }

          proxy_guard = <<-JS
  for (const pluralKey of Object.keys(PLURAL_KEY_CANONICAL)) {
    Object.defineProperty(camelCaseMap, pluralKey, {
      enumerable: false,
      configurable: true,
      get() {
        throw new Error(`'${pluralKey}' is a plural key - use StringManager.plural('${pluralKey}', count) from the ViewModel`);
      },
    });
  }
          JS
          content = content.sub("  return camelCaseMap;") { "#{proxy_guard}  return camelCaseMap;" }

          lookup_guard = <<-JS
    if (PLURAL_KEY_CANONICAL[key]) {
      throw new Error(`'${key}' is a plural key - use StringManager.plural('${key}', count) from the ViewModel`);
    }
          JS
          content = content.sub("    return this.currentLanguage[key] || key;") do
            "#{lookup_guard}    return this.currentLanguage[key] || key;"
          end
          content = content.sub("    return this._cache[defaultLang][key] || key;") do
            "#{lookup_guard}    return this._cache[defaultLang][key] || key;"
          end

          sig = is_ts ? '(key: string, count: number): string' : '(key, count)'
          resolve_sig = is_ts ? '(lang: string, key: string, count: number): string' : '(lang, key, count)'
          private_kw = is_ts ? 'private ' : ''
          category_decl = is_ts ? 'let category: string' : 'let category'
          methods = <<-JS

  // Resolve a plural key for the current language. `count` picks the CLDR
  // cardinal category via Intl.PluralRules and replaces `{count}`.
  plural#{sig} {
    return this._resolvePlural(this.language, key, count);
  }

  // SSR-safe plural pinned to the default language (see getDefaultString).
  getDefaultPlural#{sig} {
    return this._resolvePlural('#{default_language}', key, count);
  }

  #{private_kw}_resolvePlural#{resolve_sig} {
    const canonicalKey = PLURAL_KEY_CANONICAL[key];
    if (!canonicalKey) {
      throw new Error(`Unknown plural key '${key}' - register it in strings.json with a "plural" value`);
    }
    const defaultTables = plurals['#{default_language}'];
    const langTables = plurals[lang] || defaultTables;
    const table = (langTables && langTables[canonicalKey]) || (defaultTables && defaultTables[canonicalKey]);
    if (!table) {
      throw new Error(`Plural key '${canonicalKey}' has no forms for language '${lang}'`);
    }
    #{category_decl} = 'other';
    try {
      category = new Intl.PluralRules(lang).select(count);
    } catch (_e) {
      // Unknown locale tag: fall back to the required 'other' category
    }
    const body = table[category] !== undefined ? table[category] : table['other'];
    return body.replace(/\\{count\\}/g, String(count));
  }
          JS
          anchor = "}\n\nexport const StringManager = new StringManagerClass();"
          content = content.sub(anchor) { "#{methods}#{anchor}" }

          content
        end

        def string_manager_javascript_content(strings_json, default_language, marker_header, marker_footer)
          fw = Core::Frameworks.for(@config)
          <<~JS
            #{fw.use_client_prefix}#{marker_header}
            // Manages multi-language string resources.

            import { useSyncExternalStore } from 'react';

            const strings = #{strings_json};

            const LANGUAGE_STORAGE_KEY = 'jsonui-language';
            const LANGUAGE_EVENT = 'jsonui:languagechange';

            // Convert snake_case keys to camelCase for property access
            function createCamelCaseProxy(obj) {
              const camelCaseMap = {};
              for (const key in obj) {
                const camelKey = key.replace(/_([a-z0-9])/g, (_, letter) => letter.toUpperCase());
                camelCaseMap[camelKey] = obj[key];
                camelCaseMap[key] = obj[key]; // Also keep snake_case access
              }
              return camelCaseMap;
            }

            class StringManagerClass {
              constructor() {
                this._currentLanguage = '#{default_language}';
                if (typeof window !== 'undefined') {
                  const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
                  if (saved && strings[saved]) {
                    this._currentLanguage = saved;
                  }
                }
                this._cache = {};
              }

              get currentLanguage() {
                const lang = this._currentLanguage;
                if (!this._cache[lang]) {
                  this._cache[lang] = createCamelCaseProxy(strings[lang] || strings['#{default_language}']);
                }
                return this._cache[lang];
              }

              get language() {
                return this._currentLanguage;
              }

              setLanguage(lang) {
                if (!strings[lang]) {
                  console.warn(`Language '${lang}' not found. Available: ${Object.keys(strings).join(', ')}`);
                  return;
                }
                if (this._currentLanguage === lang) return;
                this._currentLanguage = lang;
                this._cache = {};
                if (typeof window !== 'undefined') {
                  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
                  window.dispatchEvent(new CustomEvent(LANGUAGE_EVENT, { detail: { language: lang } }));
                }
              }

              get availableLanguages() {
                return Object.keys(strings);
              }

              getString(key) {
                return this.currentLanguage[key] || key;
              }

              // SSR-safe lookup pinned to the default language. Use this from
              // ViewModel constructors / onAppear / any code path that runs
              // during SSR or before hydration; getString(key) reads
              // currentLanguage which may diverge between server and client
              // when the user has a persisted locale, causing hydration
              // mismatches. Re-seed with getString from a post-mount hook
              // (e.g. useEffect) once the client has hydrated.
              getDefaultString(key) {
                const defaultLang = '#{default_language}';
                if (!this._cache[defaultLang]) {
                  this._cache[defaultLang] = createCamelCaseProxy(strings[defaultLang]);
                }
                return this._cache[defaultLang][key] || key;
              }
            }

            export const StringManager = new StringManagerClass();
            export default StringManager;

            // Reactive hook — generated components consume this as `const $s = useStringManager()`.
            // Subscribes to `setLanguage` events so every call site re-renders on language change.
            function subscribeLanguage(callback) {
              if (typeof window === 'undefined') return () => {};
              window.addEventListener(LANGUAGE_EVENT, callback);
              return () => window.removeEventListener(LANGUAGE_EVENT, callback);
            }

            function getLanguageSnapshot() {
              return StringManager.currentLanguage;
            }

            // SSR + client first render must agree, otherwise React reports a
            // hydration mismatch when the persisted locale differs from the
            // default. Keep the server snapshot fixed to the default-language
            // proxy; the post-hydration subscribe pass swaps in the real
            // persisted locale via getLanguageSnapshot.
            let _serverSnapshot = null;
            function getServerSnapshot() {
              if (!_serverSnapshot) {
                _serverSnapshot = createCamelCaseProxy(strings['#{default_language}']);
              }
              return _serverSnapshot;
            }

            export function useStringManager() {
              return useSyncExternalStore(subscribeLanguage, getLanguageSnapshot, getServerSnapshot);
            }

            #{marker_footer}
          JS
        end

        def string_manager_typescript_content(strings_json, default_language, marker_header, marker_footer)
          fw = Core::Frameworks.for(@config)
          <<~TS
            #{fw.use_client_prefix}#{marker_header}
            // Manages multi-language string resources.

            import { useSyncExternalStore } from 'react';

            type StringMap = Record<string, string>;
            type StringsRoot = Record<string, StringMap>;

            const strings: StringsRoot = #{strings_json};

            const LANGUAGE_STORAGE_KEY = 'jsonui-language';
            const LANGUAGE_EVENT = 'jsonui:languagechange';

            // Convert snake_case keys to camelCase for property access
            function createCamelCaseProxy(obj: StringMap): StringMap {
              const camelCaseMap: StringMap = {};
              for (const key in obj) {
                const camelKey = key.replace(/_([a-z0-9])/g, (_, letter) => letter.toUpperCase());
                camelCaseMap[camelKey] = obj[key];
                camelCaseMap[key] = obj[key]; // Also keep snake_case access
              }
              return camelCaseMap;
            }

            class StringManagerClass {
              private _currentLanguage: string;
              private _cache: Record<string, StringMap>;

              constructor() {
                this._currentLanguage = '#{default_language}';
                if (typeof window !== 'undefined') {
                  const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
                  if (saved && strings[saved]) {
                    this._currentLanguage = saved;
                  }
                }
                this._cache = {};
              }

              get currentLanguage(): StringMap {
                const lang = this._currentLanguage;
                if (!this._cache[lang]) {
                  this._cache[lang] = createCamelCaseProxy(strings[lang] || strings['#{default_language}']);
                }
                return this._cache[lang];
              }

              get language(): string {
                return this._currentLanguage;
              }

              setLanguage(lang: string): void {
                if (!strings[lang]) {
                  console.warn(`Language '${lang}' not found. Available: ${Object.keys(strings).join(', ')}`);
                  return;
                }
                if (this._currentLanguage === lang) return;
                this._currentLanguage = lang;
                this._cache = {};
                if (typeof window !== 'undefined') {
                  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
                  window.dispatchEvent(new CustomEvent(LANGUAGE_EVENT, { detail: { language: lang } }));
                }
              }

              get availableLanguages(): string[] {
                return Object.keys(strings);
              }

              getString(key: string): string {
                return this.currentLanguage[key] || key;
              }

              // SSR-safe lookup pinned to the default language. Use this from
              // ViewModel constructors / onAppear / any code path that runs
              // during SSR or before hydration; getString(key) reads
              // currentLanguage which may diverge between server and client
              // when the user has a persisted locale, causing hydration
              // mismatches. Re-seed with getString from a post-mount hook
              // (e.g. useEffect) once the client has hydrated.
              getDefaultString(key: string): string {
                const defaultLang = '#{default_language}';
                if (!this._cache[defaultLang]) {
                  this._cache[defaultLang] = createCamelCaseProxy(strings[defaultLang]);
                }
                return this._cache[defaultLang][key] || key;
              }
            }

            export const StringManager = new StringManagerClass();
            export default StringManager;

            // Reactive hook — generated components consume this as `const $s = useStringManager()`.
            // Subscribes to `setLanguage` events so every call site re-renders on language change.
            function subscribeLanguage(callback: () => void): () => void {
              if (typeof window === 'undefined') return () => {};
              window.addEventListener(LANGUAGE_EVENT, callback);
              return () => window.removeEventListener(LANGUAGE_EVENT, callback);
            }

            function getLanguageSnapshot(): StringMap {
              return StringManager.currentLanguage;
            }

            // SSR + client first render must agree, otherwise React reports a
            // hydration mismatch when the persisted locale differs from the
            // default. Keep the server snapshot fixed to the default-language
            // proxy; the post-hydration subscribe pass swaps in the real
            // persisted locale via getLanguageSnapshot.
            let _serverSnapshot: StringMap | null = null;
            function getServerSnapshot(): StringMap {
              if (!_serverSnapshot) {
                _serverSnapshot = createCamelCaseProxy(strings['#{default_language}']);
              }
              return _serverSnapshot;
            }

            export function useStringManager(): StringMap {
              return useSyncExternalStore(subscribeLanguage, getLanguageSnapshot, getServerSnapshot);
            }

            #{marker_footer}
          TS
        end

        # The screen marker's production gate lives in ONE generated module
        # rather than inline in every screen, because the environment check
        # needs `process`, and a Vite project without @types/node fails to
        # typecheck a bare `process.env` reference (measured: TS2580). A
        # module-scoped `declare` satisfies the compiler without pulling in
        # Node types, and does not collide when @types/node IS present.
        #
        # The literal `process.env.NODE_ENV` form is deliberate: bundlers
        # statically replace exactly that expression, so a production build
        # constant-folds the branch away. A `globalThis.process` lookup would
        # typecheck too, but bundlers do NOT replace it — the marker would
        # then ship in production, which is the thing being prevented.
        #
        # ⚠️ 2026-09-10: from a2f06144 the paragraph above was true and the
        # code was not. The `| undefined` shape of the declaration forced a
        # `typeof` guard and an optional chain (`process?.env?.NODE_ENV`),
        # and neither is the literal expression a bundler replaces. Measured:
        # Next 16 (Turbopack) kept a runtime check against its `process`
        # polyfill — whose `env` is empty in a browser — and the marker
        # rendered in every web face's production build; esbuild folded the
        # `typeof` and kept the marker. The declaration now has the shape that
        # lets the plain member read type-check, and
        # spec/cli/commands/screen_marker_helper_spec.rb runs the emitted text
        # through a define, so the fold is measured rather than described.
        # The answer `jui build` hands over in JSONUI_INCLUDE_ID_PREFIX — rjui
        # reads no version literal of its own (design U8):
        #   on               prefix them; emit the helper
        #   announce:<rel>   not yet; one line naming the release
        #   off              not at all (withdrawn / undeclared); silent
        #   (absent)         run on its own: keep the unprefixed spelling, say so
        def apply_include_id_prefix_decision
          decision = ENV['JSONUI_INCLUDE_ID_PREFIX'].to_s
          if decision == 'on'
            @config['_include_id_prefix'] = true
            emit_include_id_helper
          elsif decision.start_with?('announce:')
            Core::Logger.info(
              "NOTICE [include-ids]: from jsonui-cli #{decision.split(':', 2)[1]}, the ids " \
              "inside an include with an id carry the include's prefix on web, as on iOS " \
              "and Android (`hero` + `type_badge` -> `heroTypeBadge`)"
            )
          elsif decision.empty?
            Core::Logger.info(
              "NOTICE [include-ids]: whether the ids inside an include with an id carry the " \
              "include's prefix on web (`hero` + `type_badge` -> `heroTypeBadge`, as on iOS " \
              "and Android) is decided by `jui build`; run on its own, this build keeps the " \
              "unprefixed spelling"
            )
          end
        end

        # The web side of an include's id prefix (design U8), the spelling the
        # SwiftUI and Compose builds give the same ids — codegen's
        # (sjui/kjui include_expander.rb, held to shared/core/
        # camel_case_vectors.json): `to_camel_case` splits on `_`, each part
        # after the first capitalized with the REST lower-cased (an empty part
        # adds nothing, so Ruby dropping trailing ones changes no answer);
        # `combine` upper-cases the name's first letter only when it is a-z. A
        # runtime function because one partial can sit under two include ids.
        def emit_include_id_helper
          generated_dir = @config['generated_directory'] || 'src/generated'
          FileUtils.mkdir_p(generated_dir)
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          path = File.join(generated_dir, "includeId.#{extension}")
          s = is_ts ? ': string' : ''
          opt = is_ts ? ': string | undefined' : ''

          marker_header = Core::GeneratedMarker.comment_header(
            source: "includeId (include id prefix helper)",
            generator: "rjui build"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = <<~JS
            #{marker_header}
            // The ids inside an include with an id carry the include's prefix,
            // spelled as the SwiftUI and Compose builds spell them:
            // `hero` + `type_badge` -> `heroTypeBadge`.
            export function jsonuiCamel(name#{s})#{s} {
              if (!name.includes('_')) {
                return name;
              }
              const parts = name.split('_');
              return parts[0] + parts.slice(1).map(
                (p) => (p ? p[0].toUpperCase() + p.slice(1).toLowerCase() : '')
              ).join('');
            }

            export function jsonuiIncludeId(prefix#{opt}, name#{s})#{s} {
              if (!prefix) {
                return name;
              }
              return prefix + jsonuiCamel(name).replace(/^[a-z]/, (c) => c.toUpperCase());
            }

            export function jsonuiIncludePrefix(outer#{opt}, includeId#{s})#{s} {
              return outer ? jsonuiIncludeId(outer, includeId) : jsonuiCamel(includeId);
            }

            #{marker_footer}
          JS

          File.write(path, content)
          note_emitted_helper(path)
          Core::Logger.info("Generated: #{path}")
        end

        # The helper a stopped element spreads (BaseConverter
        # #apply_interaction_inert): `inert` in the form the running React
        # takes — a boolean from React 19, a string before it — read from
        # React.version at run time, so the generated components are the same
        # under both. Measured in Chromium (18.3.1, 19.2.7): the spread stops
        # the pointer, the keyboard and the accessibility tree; `inert={true}`
        # does nothing under 18 and `inert=""` nothing under 19.
        def emit_interaction_stop_helper
          generated_dir = @config['generated_directory'] || 'src/generated'
          FileUtils.mkdir_p(generated_dir)
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          path = File.join(generated_dir, "interactionStop.#{extension}")
          stop_type = is_ts ? ': boolean' : ''
          ret_type = is_ts ? ': Record<string, unknown>' : ''

          marker_header = Core::GeneratedMarker.comment_header(
            source: "interactionStop (userInteractionEnabled helper)",
            generator: "rjui build"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = <<~JS
            #{marker_header}
            import React from 'react';

            // userInteractionEnabled false, or a binding while it is false: the
            // element and everything in it are inert — no pointer, no keyboard
            // focus, and out of the accessibility tree. React 19 takes `inert`
            // as a boolean and treats "" as false; React 18 writes an attribute
            // it does not know only as a string and drops `true`.
            const booleanInert = Number(React.version.split('.')[0]) >= 19;

            export function jsonuiInert(stop#{stop_type})#{ret_type} {
              if (!stop) {
                return {};
              }
              return booleanInert ? { inert: true } : { inert: '' };
            }

            #{marker_footer}
          JS

          File.write(path, content)
          note_emitted_helper(path)
          Core::Logger.info("Generated: #{path}")
        end

        def emit_screen_marker_helper
          generated_dir = @config['generated_directory'] || 'src/generated'
          FileUtils.mkdir_p(generated_dir)
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          path = File.join(generated_dir, "screenMarker.#{extension}")

          declare = is_ts ? "declare const process: { env: { NODE_ENV?: string } };\n\n" : ''
          id_type = is_ts ? ': string' : ''
          ret_type = is_ts ? ': Record<string, string>' : ''

          marker_header = Core::GeneratedMarker.comment_header(
            source: "screenMarker (screen identity helper)",
            generator: "rjui build"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = <<~JS
            #{marker_header}
            // Screen identity beacon for the test drivers: `data-screen` on a
            // generated screen's root element. Development builds only — the
            // marker is test scaffolding and has no place in a shipped app,
            // matching the DEBUG-only markers on iOS and Android.
            #{declare}export function screenMarker(screenId#{id_type})#{ret_type} {
              if (process.env.NODE_ENV === 'production') {
                return {};
              }
              return { 'data-screen': screenId };
            }

            #{marker_footer}
          JS

          File.write(path, content)
          note_emitted_helper(path)
          Core::Logger.info("Generated: #{path}")
        end

        # Runtime renderer for `partialAttributes`.
        #
        # Web used to slice the literal `text` at BUILD time, which made two
        # shapes impossible: a pattern range (the text is not known yet) and
        # a localized or bound `text` (the key was sliced instead of the
        # resolved string). iOS and Android both hand the partials to their
        # runtime, so this brings web to the same semantics rather than
        # inventing new ones — see the canon note on Label.partialAttributes.
        def emit_partial_text_helper
          generated_dir = @config['generated_directory'] || 'src/generated'
          FileUtils.mkdir_p(generated_dir)
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          path = File.join(generated_dir, "partialText.#{extension}")

          types = if is_ts
                    <<~TS.rstrip
                      import type { CSSProperties, ReactNode } from 'react';

                      export type PartialSpec = {
                        /** [start, end) character offsets, or a text pattern to find. */
                        range: [number, number] | string;
                        style?: CSSProperties;
                        className?: string;
                        onClick?: () => void;
                      };
                    TS
                  else
                    ''
                  end

          sig = if is_ts
                  'export function partialText(text: string, partials: PartialSpec[]): ReactNode'
                else
                  'export function partialText(text, partials)'
                end
          resolved_decl = is_ts ? 'const resolved: Array<{ start: number; end: number; spec: PartialSpec }> = [];' : 'const resolved = [];'
          nodes_decl = is_ts ? 'const nodes: ReactNode[] = [];' : 'const nodes = [];'
          style_decl = is_ts ? 'let style: CSSProperties = {};' : 'let style = {};'
          classes_decl = is_ts ? 'let classes: string[] = [];' : 'let classes = [];'
          click_decl = is_ts ? 'let onClick: (() => void) | undefined;' : 'let onClick;'

          marker_header = Core::GeneratedMarker.comment_header(
            source: 'partialText (partialAttributes runtime renderer)',
            generator: 'rjui build'
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = <<~JS
            #{marker_header}
            // Renders `partialAttributes` against the RESOLVED text, at runtime.
            //
            // Semantics are taken from the iOS and Android runtimes so the same
            // layout behaves identically on all three:
            //   * an array range is [start, end), end exclusive
            //   * a string range is the FIRST occurrence (indexOf); if the
            //     pattern is absent the partial is skipped, not an error
            //   * a range outside the text, or inverted, is skipped
            //   * partials apply in declaration order and MERGE where they
            //     overlap, later declarations winning per property — matching
            //     NSAttributedString / AnnotatedString rather than exclusive spans
            import { createElement } from 'react';
            #{types}

            #{sig} {
              if (!text || !partials || partials.length === 0) return text;

              #{resolved_decl}
              for (const spec of partials) {
                let start;
                let end;
                if (Array.isArray(spec.range)) {
                  start = spec.range[0];
                  end = spec.range[1];
                } else if (typeof spec.range === 'string') {
                  const found = text.indexOf(spec.range);
                  if (found < 0) continue;
                  start = found;
                  end = found + spec.range.length;
                } else {
                  continue;
                }
                if (!(start >= 0 && end <= text.length && start < end)) continue;
                resolved.push({ start, end, spec });
              }
              if (resolved.length === 0) return text;

              // Cut the string at every boundary, then merge whatever covers
              // each piece. This is what makes overlap behave like the mobile
              // runtimes instead of the last writer replacing the span.
              const cuts = Array.from(
                new Set([0, text.length].concat(resolved.map((r) => r.start), resolved.map((r) => r.end)))
              ).sort((a, b) => a - b);

              #{nodes_decl}
              for (let i = 0; i < cuts.length - 1; i += 1) {
                const from = cuts[i];
                const to = cuts[i + 1];
                if (from >= to) continue;
                const chunk = text.slice(from, to);
                const covering = resolved.filter((r) => r.start <= from && r.end >= to);
                if (covering.length === 0) {
                  nodes.push(chunk);
                  continue;
                }
                #{style_decl}
                #{classes_decl}
                #{click_decl}
                for (const c of covering) {
                  if (c.spec.style) style = { ...style, ...c.spec.style };
                  if (c.spec.className) classes.push(c.spec.className);
                  if (c.spec.onClick) onClick = c.spec.onClick;
                }
                nodes.push(
                  createElement(
                    'span',
                    {
                      key: `jui-partial-${from}-${to}`,
                      className: classes.length > 0 ? classes.join(' ') : undefined,
                      style: Object.keys(style).length > 0 ? style : undefined,
                      onClick,
                    },
                    chunk
                  )
                );
              }
              return nodes;
            }

            #{marker_footer}
          JS

          File.write(path, content)
          note_emitted_helper(path)
          Core::Logger.info("Generated: #{path}")
        end

        # dateStringFormat — the shape the ViewModel holds its date string in.
        #
        # A native date/time input only ever speaks ISO: `yyyy-MM-dd`, `HH:mm`,
        # or `yyyy-MM-ddTHH:mm`. iOS formats `selectedDate` with the declared
        # pattern, so without a conversion the web would silently hand the
        # ViewModel a string in a format it did not ask for — and reject the one
        # it stored. Hence a round trip on both edges of the input.
        def emit_date_format_helper
          generated_dir = @config['generated_directory'] || 'src/generated'
          FileUtils.mkdir_p(generated_dir)
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          path = File.join(generated_dir, "dateFormat.#{extension}")

          str = is_ts ? ': string' : ''
          str_or_null = is_ts ? ': string | null | undefined' : ''
          ret_str = is_ts ? ': string' : ''
          parts_type = is_ts ? ': Record<string, string>' : ''
          scan_ret = is_ts ? ': { order: string[]; regex: RegExp }' : ''

          marker_header = Core::GeneratedMarker.comment_header(
            source: "dateFormat (SelectBox dateStringFormat helper)",
            generator: "rjui build"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = <<~JS
            #{marker_header}
            // Converts between a declared `dateStringFormat` and the ISO value a
            // native date/time input requires. Supported tokens: yyyy MM dd HH mm
            // ss — the DateFormatter patterns JsonUI layouts actually use.

            const TOKENS = ['yyyy', 'MM', 'dd', 'HH', 'mm', 'ss'];

            function scanPattern(pattern#{str})#{scan_ret} {
              const order#{is_ts ? ': string[]' : ''} = [];
              let source = '';
              let i = 0;
              while (i < pattern.length) {
                const token = TOKENS.find((t) => pattern.startsWith(t, i));
                if (token) {
                  order.push(token);
                  source += token === 'yyyy' ? '(\\\\d{4})' : '(\\\\d{1,2})';
                  i += token.length;
                } else {
                  source += pattern[i].replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
                  i += 1;
                }
              }
              return { order, regex: new RegExp('^' + source + '$') };
            }

            function pad(value#{str}, width#{is_ts ? ': number' : ''}) {
              return value.length >= width ? value : '0'.repeat(width - value.length) + value;
            }

            // The three ISO shapes an <input type="date|time|datetime-local">
            // reports, in one pass.
            function isoParts(iso#{str})#{is_ts ? ': Record<string, string> | null' : ''} {
              const [datePart, timePart] = iso.split('T');
              const parts#{parts_type} = {};
              const date = (datePart ?? '').split('-');
              const time = (timePart ?? (iso.includes(':') && !iso.includes('-') ? iso : '')).split(':');
              if (date.length === 3) {
                parts.yyyy = date[0];
                parts.MM = date[1];
                parts.dd = date[2];
              }
              if (time.length >= 2) {
                parts.HH = time[0];
                parts.mm = time[1];
                parts.ss = time[2] ?? '00';
              }
              return Object.keys(parts).length > 0 ? parts : null;
            }

            /** ISO (what the input reports) -> the declared format. */
            export function formatDateValue(
              iso#{str_or_null},
              pattern#{str},
              _inputType#{str}
            )#{ret_str} {
              if (!iso) return '';
              const parts = isoParts(iso);
              if (!parts) return iso;
              return pattern.replace(/yyyy|MM|dd|HH|mm|ss/g, (token) => parts[token] ?? '');
            }

            /** The declared format (what the ViewModel holds) -> ISO. */
            export function toIsoDateValue(
              value#{str_or_null},
              pattern#{str},
              inputType#{str}
            )#{ret_str} {
              if (!value) return '';
              const { order, regex } = scanPattern(pattern);
              const match = regex.exec(value);
              if (!match) {
                // A ViewModel still holding ISO keeps working; anything else is
                // dropped rather than fed to the input as an invalid value,
                // which React would warn about on every render.
                return isoParts(value) ? value : '';
              }
              const parts#{parts_type} = {};
              order.forEach((token, index) => {
                parts[token] = match[index + 1];
              });
              const date = parts.yyyy && parts.MM && parts.dd
                ? pad(parts.yyyy, 4) + '-' + pad(parts.MM, 2) + '-' + pad(parts.dd, 2)
                : '';
              const time = parts.HH && parts.mm
                ? pad(parts.HH, 2) + ':' + pad(parts.mm, 2) +
                  (order.includes('ss') && parts.ss ? ':' + pad(parts.ss, 2) : '')
                : '';
              if (inputType === 'time') return time;
              if (inputType === 'datetime-local') return date && time ? date + 'T' + time : '';
              return date;
            }

            #{marker_footer}
          JS

          File.write(path, content)
          note_emitted_helper(path)
          Core::Logger.success("Updated: #{path}")
        end

        # align*OfView / align*View / alignCenter*View — positioning a child
        # against a SIBLING's box.
        #
        # CSS has no way to express this statically: `position: absolute` offsets
        # resolve against the containing block, never against another element.
        # (Anchor positioning would, but it is Chromium-only.) So the boxes are
        # measured and the offsets written, which is what AutoLayout does on iOS
        # and what RelativePositionContainer does in SwiftUI.
        #
        # Which edge is set matters: an absolutely positioned box applies its
        # margin OUTWARD from whichever offset is set, so anchoring the child's
        # bottom uses `bottom` and lets margin-bottom push it up — the same sign
        # UIKit gives it. Setting `top` and subtracting a margin would fight the
        # class-driven margin already on the element.
        def emit_relative_position_helper
          generated_dir = @config['generated_directory'] || 'src/generated'
          FileUtils.mkdir_p(generated_dir)
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          path = File.join(generated_dir, "relativePosition.#{extension}")

          spec_type = is_ts ? <<~TS : ''

            /** One child's constraints. Every value is the id of a sibling. */
            export interface RelativeConstraint {
              /** id of the element being positioned */
              id: string;
              /** alignTopOfView — this element's bottom sits at the anchor's top */
              above?: string;
              /** alignBottomOfView — this element's top sits at the anchor's bottom */
              below?: string;
              /** alignLeftOfView — this element's right sits at the anchor's left */
              leftOf?: string;
              /** alignRightOfView — this element's left sits at the anchor's right */
              rightOf?: string;
              /** alignTopView / alignBottomView / alignLeftView / alignRightView */
              alignTop?: string;
              alignBottom?: string;
              alignLeft?: string;
              alignRight?: string;
              /** alignCenterVerticalView / alignCenterHorizontalView */
              centerVertical?: string;
              centerHorizontal?: string;
            }
          TS
          container_param = is_ts ? ': HTMLElement | null | undefined' : ''
          spec_param = is_ts ? ': RelativeConstraint[]' : ''
          cleanup_ret = is_ts ? ': () => void' : ''
          el_type = is_ts ? ' as HTMLElement | null' : ''

          marker_header = Core::GeneratedMarker.comment_header(
            source: "relativePosition (align*View / align*OfView helper)",
            generator: "rjui build"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = <<~JS
            #{marker_header}
            // Positions children against sibling boxes. See RelativeConstraint
            // for which JsonUI attribute each field comes from.
            #{spec_type}
            function findChild(container#{container_param}, id#{is_ts ? ': string' : ''}) {
              if (!container) return null;
              return container.querySelector('[id="' + id + '"]')#{el_type};
            }

            // Writes one child's offsets. Returns true when anything moved, so the
            // caller can settle chains (A below B below C) without needing the
            // constraints in dependency order.
            function place(
              container#{container_param},
              spec#{is_ts ? ': RelativeConstraint' : ''}
            ) {
              const child = findChild(container, spec.id);
              if (!container || !child) return false;

              const box = container.getBoundingClientRect();
              const self = child.getBoundingClientRect();
              const anchorOf = (id#{is_ts ? ': string | undefined' : ''}) => {
                if (!id) return null;
                const el = findChild(container, id);
                return el ? el.getBoundingClientRect() : null;
              };

              let top#{is_ts ? ': number | null' : ''} = null;
              let bottom#{is_ts ? ': number | null' : ''} = null;
              let left#{is_ts ? ': number | null' : ''} = null;
              let right#{is_ts ? ': number | null' : ''} = null;

              const above = anchorOf(spec.above);
              if (above) bottom = box.bottom - above.top;
              const below = anchorOf(spec.below);
              if (below) top = below.bottom - box.top;
              const alignTop = anchorOf(spec.alignTop);
              if (alignTop) top = alignTop.top - box.top;
              const alignBottom = anchorOf(spec.alignBottom);
              if (alignBottom) bottom = box.bottom - alignBottom.bottom;
              const centerVertical = anchorOf(spec.centerVertical);
              if (centerVertical) {
                top = centerVertical.top + centerVertical.height / 2 - box.top - self.height / 2;
              }

              const leftOf = anchorOf(spec.leftOf);
              if (leftOf) right = box.right - leftOf.left;
              const rightOf = anchorOf(spec.rightOf);
              if (rightOf) left = rightOf.right - box.left;
              const alignLeft = anchorOf(spec.alignLeft);
              if (alignLeft) left = alignLeft.left - box.left;
              const alignRight = anchorOf(spec.alignRight);
              if (alignRight) right = box.right - alignRight.right;
              const centerHorizontal = anchorOf(spec.centerHorizontal);
              if (centerHorizontal) {
                left = centerHorizontal.left + centerHorizontal.width / 2 - box.left - self.width / 2;
              }

              let moved = false;
              const write = (
                prop#{is_ts ? ": 'top' | 'bottom' | 'left' | 'right'" : ''},
                value#{is_ts ? ': number | null' : ''}
              ) => {
                const next = value === null ? '' : Math.round(value) + 'px';
                if (child.style[prop] === next) return;
                child.style[prop] = next;
                moved = true;
              };
              // A vertical constraint clears the opposite edge, so re-running
              // after a layout change cannot leave both edges pinned and stretch
              // the element. An axis with no constraint is left alone.
              if (top !== null || bottom !== null) {
                write('top', top);
                write('bottom', bottom);
              }
              if (left !== null || right !== null) {
                write('left', left);
                write('right', right);
              }
              return moved;
            }

            export function applyRelativePositions(
              container#{container_param},
              spec#{spec_param}
            )#{cleanup_ret} {
              if (!container || spec.length === 0) return () => {};

              const settle = () => {
                // One pass per constraint is enough to settle any acyclic chain;
                // the loop exits as soon as nothing moves, so the common case is
                // two passes.
                for (let pass = 0; pass < spec.length + 1; pass++) {
                  let moved = false;
                  for (const one of spec) {
                    if (place(container, one)) moved = true;
                  }
                  if (!moved) return;
                }
              };

              settle();

              if (typeof ResizeObserver === 'undefined') return () => {};
              // Anchors move when their own content reflows, so the container
              // alone is not enough to observe.
              const observer = new ResizeObserver(() => settle());
              observer.observe(container);
              for (const one of spec) {
                const child = findChild(container, one.id);
                if (child) observer.observe(child);
                for (const anchorId of [
                  one.above, one.below, one.leftOf, one.rightOf,
                  one.alignTop, one.alignBottom, one.alignLeft, one.alignRight,
                  one.centerVertical, one.centerHorizontal
                ]) {
                  const anchor = anchorId ? findChild(container, anchorId) : null;
                  if (anchor) observer.observe(anchor);
                }
              }
              return () => observer.disconnect();
            }

            #{marker_footer}
          JS

          File.write(path, content)
          note_emitted_helper(path)
          Core::Logger.success("Updated: #{path}")
        end

        # autoShrink / minimumScaleFactor — shrink the text until it fits the
        # element's own box, never below `minimumScaleFactor` of the declared
        # size. Same contract as UILabel.adjustsFontSizeToFitWidth and Compose
        # autosizing.
        #
        # This has to measure: CSS can size text against the VIEWPORT
        # (`vw`, `clamp`) but never against the element's own content box, and
        # the two are unrelated. The converter used to emit
        # `min(<size>px, max(<size * factor>px, 1vw))`, which reads like a
        # shrink and is not one — on a 375px-wide viewport it renders a 16px
        # Label at 8px whether or not anything overflows, and on a wide one the
        # 1vw term outruns both floors so minimumScaleFactor changes nothing at
        # all (measured: fixture and control both computed 10.24px at 1024px,
        # 0 differing px — plan 51-A).
        def emit_auto_shrink_helper
          generated_dir = @config['generated_directory'] || 'src/generated'
          FileUtils.mkdir_p(generated_dir)
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          path = File.join(generated_dir, "autoShrink.#{extension}")

          options_type = is_ts ? <<~TS : ''

            export interface AutoShrinkOptions {
              /** The size the element is declared with, in px. The ceiling. */
              fontSize?: number;
              /** Floor as a fraction of fontSize (iOS minimumScaleFactor). */
              minimumScaleFactor?: number;
            }
          TS
          el_param = is_ts ? ': HTMLElement | null | undefined' : ''
          options_param = is_ts ? ': AutoShrinkOptions' : ''
          cleanup_ret = is_ts ? ': () => void' : ''

          marker_header = Core::GeneratedMarker.comment_header(
            source: 'autoShrink (autoShrink / minimumScaleFactor helper)',
            generator: 'rjui build'
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = <<~JS
            #{marker_header}
            // Shrinks an element's text until it fits its own box, down to
            // `minimumScaleFactor` of the declared size. Re-runs on resize.
            #{options_type}
            function overflows(el#{is_ts ? ': HTMLElement' : ''}) {
              // A box that grows with its content (height: fit-content, the
              // wrapContent default) never reports vertical overflow — the
              // honest answer there is "it fits", and nothing shrinks.
              return el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1;
            }

            export function applyAutoShrink(
              el#{el_param},
              options#{options_param}
            )#{cleanup_ret} {
              if (!el) return () => {};

              const declared = options.fontSize ?? parseFloat(getComputedStyle(el).fontSize) ?? 0;
              if (!declared) return () => {};
              // 0.5 when autoShrink is declared without a floor — the same
              // fallback sjui's SwiftUI label converter uses, so the three
              // platforms shrink to the same place. A factor at or above 1 is
              // "do not shrink": the floor is the ceiling.
              const factor = options.minimumScaleFactor ?? 0.5;
              const floor = Math.max(1, declared * Math.min(factor, 1));

              const fit = () => {
                el.style.fontSize = declared + 'px';
                if (floor >= declared || !overflows(el)) return;
                // Bisect rather than step: a 4px search space converges in
                // ~5 reflows instead of one per pixel.
                let lo = floor;
                let hi = declared;
                for (let i = 0; i < 8 && hi - lo > 0.5; i++) {
                  const mid = (lo + hi) / 2;
                  el.style.fontSize = mid + 'px';
                  if (overflows(el)) { hi = mid; } else { lo = mid; }
                }
                el.style.fontSize = lo + 'px';
              };

              fit();

              if (typeof ResizeObserver === 'undefined') return () => {};
              // Observing the element itself would feed its own writes back in;
              // the box that decides whether the text fits is the parent's.
              const parent = el.parentElement;
              if (!parent) return () => {};
              const observer = new ResizeObserver(() => fit());
              observer.observe(parent);
              return () => observer.disconnect();
            }

            #{marker_footer}
          JS

          File.write(path, content)
          note_emitted_helper(path)
          Core::Logger.success("Updated: #{path}")
        end

        # Collection scroll control — scrollTo / scrollAnchor / scrollAnimated /
        # defaultScrollAnchor / currentPage / onItemAppear.
        #
        # These live in a helper rather than inline in every generated component
        # because each one is a measurement, and measurement blobs repeated per
        # collection are where drift starts. `scrollIntoView` is deliberately
        # not used: it scrolls every scrollable ancestor, so scrolling a list to
        # its last row would also scroll the page.
        def emit_collection_scroll_helper
          generated_dir = @config['generated_directory'] || 'src/generated'
          FileUtils.mkdir_p(generated_dir)
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          path = File.join(generated_dir, "collectionScroll.#{extension}")

          anchor_type = is_ts ? "\n\nexport type CollectionScrollAnchor = 'top' | 'center' | 'bottom';" : ''
          el_param = is_ts ? ': HTMLElement | null | undefined' : ''
          index_param = is_ts ? ': number | undefined | null' : ''
          anchor_param = is_ts ? ': CollectionScrollAnchor | undefined' : ''
          horizontal_param = is_ts ? ': boolean' : ''
          animated_param = is_ts ? ': boolean' : ''
          page_ret = is_ts ? ': number' : ''
          # `behavior` must be ScrollBehavior, not string, or ScrollToOptions
          # rejects it under TS.
          behavior_type = is_ts ? ': ScrollBehavior' : ''
          appear_param = is_ts ? ': (index: number) => void' : ''
          cleanup_ret = is_ts ? ': () => void' : ''
          element_param = is_ts ? ': Element' : ''
          id_param = is_ts ? ': string' : ''
          key_prop_param = is_ts ? ': string | null' : ''
          target_param = is_ts ? ': unknown' : ''
          keys_param = is_ts ? ': unknown[] | null' : ''
          lists_param = is_ts ? ': unknown[][]' : ''
          keys_ret = is_ts ? ': unknown[]' : ''
          keys_decl = is_ts ? ': unknown[]' : ''
          record_cast = is_ts ? ' as Record<string, unknown>' : ''

          marker_header = Core::GeneratedMarker.comment_header(
            source: "collectionScroll (Collection scroll-control helper)",
            generator: "rjui build"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = <<~JS
            #{marker_header}
            // Scroll control for Collection components. Every function is a
            // no-op on a missing element so a generated effect never has to
            // guard the ref itself.#{anchor_type}

            function leadingEdge(box#{is_ts ? ': DOMRect' : ''}, horizontal#{horizontal_param}) {
              return horizontal ? box.left : box.top;
            }

            // currentPage: bring the child at `index` to `anchor` within the
            // collection's own scroll box — NOT the page's.
            export function scrollCollectionToItem(
              container#{el_param},
              index#{index_param},
              anchor#{anchor_param},
              animated#{animated_param},
              horizontal#{horizontal_param}
            ) {
              if (!container || index === undefined || index === null) return;
              const child = container.children[Number(index)];
              if (!child) return;
              scrollCollectionToElement(container, child, anchor, animated, horizontal);
            }

            // scrollTo names a CELL (4f ruling 2026-09-27; the SSoT's
            // Collection.scrollTo): a number is the cell's place among the
            // cells of every drawn section, in section order — a section's
            // header or footer, and a section's block, is not a cell; a
            // string is the first cell, in section order, whose key it is
            // (`keys`, the drawn cells' keys in that order: a cell's cellId,
            // else its cellIdProperty value). Anything else — a string no
            // cell has as its key included — scrolls nowhere; a string of
            // digits is a key like any other, not an index (only Kotlin reads
            // the legacy `<digits>` form). The cells are the elements
            // addressed `<collectionId>_item_<n>`, in document order; a
            // Collection whose cells carry no address falls back to its
            // children. Until jsonui-cli 1.9.0 this was the container's
            // child at the index, which counts a header, a footer and a
            // section's block; a string was read as a number, and — with no
            // cellIdProperty — a string of digits as an index while a cellId
            // was never matched.
            export function scrollCollectionToCell(
              container#{el_param},
              collectionId#{id_param},
              target#{target_param},
              keys#{keys_param},
              anchor#{anchor_param},
              animated#{animated_param},
              horizontal#{horizontal_param}
            ) {
              if (!container) return;
              let n = -1;
              if (typeof target === 'number') {
                n = target;
              } else if (typeof target === 'string' && target !== '' && keys) {
                n = keys.findIndex((key) => key !== null && key !== undefined && String(key) === target);
              }
              if (!Number.isInteger(n) || n < 0) return;
              const prefix = collectionId + '_item_';
              const cells = Array.from(container.querySelectorAll('[id]')).filter((el) =>
                el.id.startsWith(prefix) && /^[0-9]+$/.test(el.id.slice(prefix.length))
              );
              const cell = cells.length > 0 ? cells[n] : container.children[n];
              if (!cell) return;
              scrollCollectionToElement(container, cell, anchor, animated, horizontal);
            }

            // The keys of the drawn cells, in section order (`lists`, each drawn
            // section's cells): a cell's `cellId`, else — only when the
            // Collection has one — its cellIdProperty value, else null; a cell
            // with neither has no key.
            export function collectionCellKeys(lists#{lists_param}, cellIdProperty#{key_prop_param})#{keys_ret} {
              const keys#{keys_decl} = [];
              for (const cells of lists) {
                for (const cell of cells ?? []) {
                  const record = (cell ?? {})#{record_cast};
                  keys.push(record['cellId'] ?? (cellIdProperty ? record[cellIdProperty] : null) ?? null);
                }
              }
              return keys;
            }

            function scrollCollectionToElement(
              container#{is_ts ? ': HTMLElement' : ''},
              child#{element_param},
              anchor#{anchor_param},
              animated#{animated_param},
              horizontal#{horizontal_param}
            ) {
              const containerBox = container.getBoundingClientRect();
              const childBox = child.getBoundingClientRect();
              const scrolled = horizontal ? container.scrollLeft : container.scrollTop;
              const start =
                leadingEdge(childBox, horizontal) - leadingEdge(containerBox, horizontal) + scrolled;
              const childSize = horizontal ? childBox.width : childBox.height;
              const viewport = horizontal ? container.clientWidth : container.clientHeight;
              let offset = start;
              if (anchor === 'center') offset = start - (viewport - childSize) / 2;
              else if (anchor !== 'top') offset = start - (viewport - childSize);
              offset = Math.max(0, offset);
              const behavior#{behavior_type} = animated === false ? 'auto' : 'smooth';
              container.scrollTo(
                horizontal ? { left: offset, behavior } : { top: offset, behavior }
              );
            }

            // defaultScrollAnchor: where the collection starts. Runs once, so it
            // sets the scroll offset directly rather than animating to it.
            export function applyCollectionDefaultAnchor(
              container#{el_param},
              anchor#{anchor_param},
              horizontal#{horizontal_param}
            ) {
              if (!container) return;
              const max = horizontal
                ? container.scrollWidth - container.clientWidth
                : container.scrollHeight - container.clientHeight;
              if (max <= 0) return;
              const offset = anchor === 'bottom' ? max : anchor === 'center' ? max / 2 : 0;
              if (horizontal) container.scrollLeft = offset;
              else container.scrollTop = offset;
            }

            // currentPage read-back: the cell nearest the collection's leading
            // edge. Measured rather than divided by a page width, because cells
            // are not required to be uniformly sized.
            export function currentCollectionPage(
              container#{el_param},
              horizontal#{horizontal_param}
            )#{page_ret} {
              if (!container) return 0;
              const origin = leadingEdge(container.getBoundingClientRect(), horizontal);
              let nearest = 0;
              let best = Infinity;
              for (let i = 0; i < container.children.length; i++) {
                const box = container.children[i].getBoundingClientRect();
                const distance = Math.abs(leadingEdge(box, horizontal) - origin);
                if (distance < best) {
                  best = distance;
                  nearest = i;
                }
              }
              return nearest;
            }

            // onItemAppear: fires with the cell index each time a cell enters the
            // collection's viewport, matching SwiftUI's .onAppear and Compose's
            // LaunchedEffect per cell. Returns the observer teardown.
            export function observeCollectionItems(
              container#{el_param},
              onAppear#{appear_param}
            )#{cleanup_ret} {
              if (!container || typeof IntersectionObserver === 'undefined') {
                return () => {};
              }
              const observer = new IntersectionObserver(
                (entries) => {
                  for (const entry of entries) {
                    if (!entry.isIntersecting) continue;
                    const index = Array.prototype.indexOf.call(
                      container.children,
                      entry.target
                    );
                    if (index >= 0) onAppear(index);
                  }
                },
                { root: container }
              );
              for (let i = 0; i < container.children.length; i++) {
                observer.observe(container.children[i]);
              }
              return () => observer.disconnect();
            }

            #{marker_footer}
          JS

          File.write(path, content)
          note_emitted_helper(path)
          Core::Logger.success("Updated: #{path}")
        end

        def emit_cell_id_generator
          generated_dir = @config['generated_directory'] || 'src/generated'
          FileUtils.mkdir_p(generated_dir)
          is_ts = @config['typescript']
          extension = is_ts ? 'ts' : 'js'
          path = File.join(generated_dir, "cellIdGenerator.#{extension}")

          type_annotation = is_ts ? ': Record<string, unknown>' : ''
          key_type = is_ts ? ': string' : ''
          idx_type = is_ts ? ': number' : ''
          ret_type = is_ts ? ': string' : ''
          list_type = is_ts ? ': Array<Record<string, unknown>>' : ''
          str_array_type = is_ts ? ': string[]' : ''

          marker_header = Core::GeneratedMarker.comment_header(
            source: "cellIdGenerator (autoChangeTrackingId helper)",
            generator: "rjui build"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = <<~JS
            #{marker_header}
            // Stable cell identifier generator used by Collection components
            // when autoChangeTrackingId is enabled in the layout spec.
            // Format: `<primary>_<base36(fnv1a)>`. Hash excludes the primary key
            // and the reserved "cellId" entry so re-applying is idempotent.

            export function autoCellId(data#{type_annotation}, primaryKey#{key_type}, index#{idx_type})#{ret_type} {
              const primary = String(data[primaryKey] ?? index);
              let hash = 2166136261; // FNV-1a 32bit offset
              const keys = Object.keys(data)
                .filter((k) => k !== primaryKey && k !== 'cellId')
                .sort();
              for (const k of keys) {
                const v = data[k];
                if (typeof v === 'function') continue;
                const str =
                  k +
                  ':' +
                  (typeof v === 'object' && v !== null
                    ? JSON.stringify(v, Object.keys(v).sort())
                    : String(v));
                for (let i = 0; i < str.length; i++) {
                  hash ^= str.charCodeAt(i);
                  hash = Math.imul(hash, 16777619);
                }
              }
              return `${primary}_${(hash >>> 0).toString(36)}`;
            }

            export function enrichCellIds(data#{list_type}, primaryKey#{key_type}) {
              const seen = new Map();
              const duplicates#{str_array_type} = [];
              const result = data.map((item, index) => {
                const id = autoCellId(item, primaryKey, index);
                const count = (seen.get(id) || 0) + 1;
                seen.set(id, count);
                const resolved = count > 1 ? `${id}#${count}` : id;
                if (count > 1) duplicates.push(id);
                return { ...item, cellId: resolved };
              });
              if (duplicates.length > 0) {
                // eslint-disable-next-line no-console
                console.warn(
                  '[cellIdGenerator] Duplicate cellIds detected:',
                  duplicates,
                  '- add a unique field to cellIdProperty.'
                );
              }
              return result;
            }

            #{marker_footer}
          JS

          File.write(path, content)
          note_emitted_helper(path)
          Core::Logger.success("Updated: #{path}")
        end
      end
    end
  end
end
