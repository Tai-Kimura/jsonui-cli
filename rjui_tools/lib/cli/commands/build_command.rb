# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative '../../core/config_manager'
require_relative '../../core/generated_marker'
require_relative '../../core/logger'
require_relative '../../core/attribute_validator'
require_relative '../../core/normalization'
require_relative '../../core/binding_validator'
require_relative '../../core/resources/color_manager'
require_relative '../../react/react_generator'
require_relative '../../react/style_loader'
require_relative '../../core/layout_validator'
require_relative '../../core/plural_validator'
require_relative '../../react/data_model_generator'
require_relative '../../react/viewmodel_generator'
require_relative '../../react/hook_generator'
require_relative '../../core/layout_variant'
require_relative '../../core/screen_index'

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

          # Update Data models from JSON data sections
          update_data_models

          # Emit shared cellIdGenerator helper
          emit_cell_id_generator

          all_json_files = Dir.glob(File.join(layouts_dir, '**', '*.json')).reject do |file|
            # Skip Resources folder (colors.json, strings.json, etc.)
            # Skip Styles folder (reusable style definitions, not components)
            file.include?(File.join(layouts_dir, 'Resources')) ||
              file.include?(File.join(layouts_dir, 'Styles'))
          end
          # Responsive variant files (home@regular.json) are generated
          # alongside their base screen, never standalone (06 track).
          json_files = all_json_files.reject do |file|
            JsonUIShared::LayoutVariant.variant?(file)
          end

          if json_files.empty?
            Core::Logger.warn('No JSON layout files found')
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

          generator = React::ReactGenerator.new(@config)

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

              # Validate binding expressions for business logic
              validate_bindings(json_content, json_file)

              # Shared layout checks (autoChangeTrackingId without cellIdProperty, etc.)
              shared_warnings = JsonUIShared::LayoutValidator.validate_layout(
                json_content, source_path: File.basename(json_file)
              )
              JsonUIShared::LayoutValidator.print_warnings(shared_warnings) unless shared_warnings.empty?

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
                validate_bindings(v_json, variant_file)
                v_shared_warnings = JsonUIShared::LayoutValidator.validate_layout(
                  v_json, source_path: File.basename(variant_file)
                )
                JsonUIShared::LayoutValidator.print_warnings(v_shared_warnings) unless v_shared_warnings.empty?

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
            rescue StandardError => e
              Core::Logger.error("Error processing #{json_file}: #{e.message}")
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

          # Print all collected warnings at the end
          print_validation_summary
          print_binding_warnings
          print_binding_errors

          # Error-severity canonical binding rules (binding_semantics.json
          # validatorRules) always fail the build
          if @binding_errors.any?
            Core::Logger.error("Build failed: #{@binding_errors.size} binding error(s)")
            exit 1
          end

          Core::Logger.success('Build completed!')
        end

        def prune_orphan_components(expected_paths)
          components_dir = @config['components_directory']
          return unless components_dir && Dir.exist?(components_dir)

          expected_set = expected_paths.to_set
          extension_glob = @config['typescript'] ? '*.tsx' : '*.jsx'
          all_generated = Dir.glob(File.join(components_dir, '**', extension_glob))

          removed = []
          all_generated.each do |path|
            abs = File.expand_path(path)
            next if expected_set.include?(abs)
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
            .reject { |f| f.include?('/Resources/') || f.include?('/Styles/') }
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

        def to_pascal_case(string)
          string.split(/[-_]/).map(&:capitalize).join
        end

        def ensure_builtin_components
          extensions_dir = @config['extensions_directory'] || 'src/components/extensions'
          FileUtils.mkdir_p(extensions_dir)

          network_image_path = File.join(extensions_dir, 'NetworkImage.tsx')
          template_path = File.join(File.dirname(__FILE__), '../../react/templates/network_image.tsx')
          if File.exist?(template_path)
            template = File.read(template_path)
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

          ensure_configuration_template
        end

        # Copy the Configuration.ts template (FontSpec / Configuration.Font)
        # into the host app's @/lib/jsonui/ directory so generated components
        # can import { Configuration } and route font specs through the
        # host-supplied fontProvider. Idempotent — leaves an existing copy
        # alone (consumers may have customized the provider field).
        def ensure_configuration_template
          lib_dir = @config['lib_directory'] || 'src/lib/jsonui'
          FileUtils.mkdir_p(lib_dir)

          target_path = File.join(lib_dir, 'Configuration.ts')
          return if File.exist?(target_path)

          template_path = File.join(File.dirname(__FILE__), '../../react/templates/Configuration.ts')
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
          return if component.key?('style') && component.keys.size == 1
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
          current_orientation = component['orientation'] ||
            (component['type'] == 'View' ? 'vertical' : parent_orientation)

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
        end

        def generate_viewmodels
          Core::Logger.info('Generating ViewModels...')
          viewmodel_generator = React::ViewModelGenerator.new
          viewmodel_generator.generate_viewmodels
        rescue StandardError => e
          Core::Logger.error("Error generating viewmodels: #{e.message}")
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
        end

        # Copy the useColorMode React hook template to @/hooks/ so consumers
        # can subscribe to ColorManager mode changes. Library-owned copies
        # (still carrying the generated header) refresh when the shipped
        # template changes — same contract as ensure_builtin_components; a
        # copy without the header is treated as user-customized and left alone.
        def ensure_use_color_mode_hook
          hooks_dir = @config['hooks_directory'] || 'src/hooks'
          FileUtils.mkdir_p(hooks_dir)

          target_path = File.join(hooks_dir, 'useColorMode.ts')
          template_path = File.join(File.dirname(__FILE__), '../../react/templates/use_color_mode.ts')
          return unless File.exist?(template_path)

          template = File.read(template_path)
          if !File.exist?(target_path)
            File.write(target_path, template)
            Core::Logger.success("Created hook: #{target_path}")
          else
            existing = File.read(target_path)
            if existing != template && existing.include?('Generated by rjui build')
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
            layout_files = Dir.glob(File.join(layouts_dir, '**', '*.json')).reject do |file|
              file.include?(File.join(layouts_dir, 'Resources'))
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
          <<~JS
            "use client";

            #{marker_header}
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
          <<~TS
            "use client";

            #{marker_header}
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
          Core::Logger.success("Updated: #{path}")
        end
      end
    end
  end
end
