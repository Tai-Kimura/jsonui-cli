# frozen_string_literal: true

require 'optparse'
require 'json'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'
require_relative '../../core/attribute_validator'
require_relative '../../core/binding_validator'
require_relative '../../core/normalization'
require_relative '../../core/layout_variant'

module KjuiTools
  module CLI
    module Commands
      class Build
        def run(args)
          options = parse_options(args)

          # Detect mode
          mode = options[:mode] || Core::ConfigManager.get('mode') || 'compose'

          # Store validation results
          @validation_warnings = []
          @validation_errors = 0
          @binding_errors = []

          case mode
          when 'xml', 'all'
            build_xml(options)
          end

          if mode == 'compose' || mode == 'all'
            build_compose(options)
          end

          # Print validation summary if there were warnings
          print_validation_summary if options[:validate] != false && @validation_warnings.any?

          # Error-severity canonical binding rules (binding_semantics.json
          # validatorRules) always fail the build, strict or not
          if @binding_errors.any?
            Core::Logger.error "Build failed: #{@binding_errors.size} binding error(s) (canonical severity: error)"
            exit 1
          end

          # Exit with error code if strict mode and there were validation errors
          if options[:strict] && @validation_errors > 0
            Core::Logger.error "Build failed: #{@validation_errors} validation error(s)"
            exit 1
          end
        end

        private

        def parse_options(args)
          options = {}

          OptionParser.new do |opts|
            opts.banner = "Usage: kjui build [options]"

            opts.on('--mode MODE', ['all', 'xml', 'compose'],
                    'Build mode (all, xml, compose)') do |mode|
              options[:mode] = mode
            end

            opts.on('--clean', 'Clean cache before building') do
              options[:clean] = true
            end

            opts.on('--no-validate', 'Skip JSON attribute validation') do
              options[:validate] = false
            end

            opts.on('--strict', 'Fail build on validation errors') do
              options[:strict] = true
            end

            opts.on('-h', '--help', 'Show this help message') do
              puts opts
              exit
            end
          end.parse!(args)

          # Validation is enabled by default
          options[:validate] = true if options[:validate].nil?

          options
        end

        def print_validation_summary
          Core::Logger.info "-" * 60
          Core::Logger.warn "Validation Summary: #{@validation_warnings.length} warning(s) found"
          @validation_warnings.each do |warning|
            puts "  \e[33m#{warning}\e[0m"
          end
        end

        # Validate a JSON component and all its children recursively
        # @param json_data [Hash] The JSON component to validate
        # @param validator [AttributeValidator] The validator instance
        # @param file_name [String] The name of the file being validated
        # @param parent_orientation [String, nil] The orientation of the parent component
        def validate_json(json_data, validator, file_name, parent_orientation = nil)
          return [] unless json_data.is_a?(Hash)

          warnings = validator.validate(json_data, nil, parent_orientation)

          # Get this component's orientation for passing to children
          current_orientation = json_data['orientation']

          # Validate children recursively
          children = json_data['child'] || json_data['children'] || []
          children = [children] unless children.is_a?(Array)

          children.each do |child|
            warnings.concat(validate_json(child, validator, file_name, current_orientation)) if child.is_a?(Hash)
          end

          # Validate sections (for Collection/Table)
          # Section headers, footers, and cells are top-level components, so parent_orientation is nil
          if json_data['sections'].is_a?(Array)
            json_data['sections'].each do |section|
              if section.is_a?(Hash)
                ['header', 'footer', 'cell'].each do |key|
                  warnings.concat(validate_json(section[key], validator, file_name, nil)) if section[key].is_a?(Hash)
                end
              end
            end
          end

          warnings
        end

        def build_xml(options = {})
          Core::Logger.info "Building XML View files..."

          # Setup project paths
          Core::ProjectFinder.setup_paths

          require_relative '../../xml/xml_builder'
          builder = Xml::XmlBuilder.new

          # Pass validation options to builder
          builder.validation_enabled = options[:validate]
          builder.validation_callback = ->(file, warnings) {
            if warnings.any?
              @validation_warnings.concat(warnings.map { |w| "[#{file}] #{w}" })
              @validation_errors += warnings.length
            end
          } if options[:validate]

          builder.build(options)

          Core::Logger.success "XML build completed!"
        end

        def build_compose(options = {})
          Core::Logger.info "Building Compose files..."

          # Setup project paths
          Core::ProjectFinder.setup_paths

          require_relative '../../compose/compose_builder'
          require_relative '../../compose/build_cache_manager'

          config = Core::ConfigManager.load_config
          source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
          source_directory = config['source_directory'] || 'src/main'
          layouts_dir = File.join(source_path, source_directory, config['layouts_directory'] || 'assets/Layouts')

          # Initialize cache manager
          cache_manager = Compose::BuildCacheManager.new(source_path)

          # Clean cache if --clean option is specified
          if options[:clean]
            Core::Logger.info "Cleaning build cache..."
            cache_manager.clean_cache
          end

          last_updated = cache_manager.load_last_updated
          last_including_files = cache_manager.load_last_including_files
          style_dependencies = cache_manager.load_style_dependencies

          # Process all JSON files in Layouts directory (excluding Resources folder)
          all_json_files = Dir.glob(File.join(layouts_dir, '**/*.json')).reject do |file|
            file.include?('/Resources/')
          end
          # Responsive variant files (home@regular.json) are built alongside
          # their base screen, never standalone — but they stay in the
          # resources scan (their strings localize like any layout).
          json_files = all_json_files.reject do |file|
            JsonUIShared::LayoutVariant.variant?(file)
          end

          if json_files.empty?
            Core::Logger.warn "No JSON files found in #{layouts_dir}"
            return
          end

          # Extract resources before processing layouts
          require_relative '../../core/resources_manager'
          require_relative '../../core/plural_validator'
          resources_manager = Core::ResourcesManager.new(config, source_path)
          begin
            resources_manager.extract_resources(all_json_files)
          rescue JsonUIShared::PluralValidator::ValidationError => e
            Core::Logger.error e.message
            exit 1
          end
          Core::Logger.info "-" * 60

          # Track new includes and style dependencies
          new_including_files = {}
          new_style_dependencies = {}
          failed_files = []

          # Filter files that need update
          files_to_update = []
          json_files.each do |json_file|
            file_name = File.basename(json_file, '.json')

            # Check if file needs update. A dirty variant file re-builds its
            # base screen (the dispatch + variant view live there).
            variant_dirty = JsonUIShared::LayoutVariant.variants_for(json_file).values.any? do |vf|
              cache_manager.needs_update?(vf, last_updated, layouts_dir, last_including_files, style_dependencies)
            end
            if variant_dirty || cache_manager.needs_update?(json_file, last_updated, layouts_dir, last_including_files, style_dependencies)
              files_to_update << json_file
            else
              # Keep existing includes and style dependencies for unchanged files
              new_including_files[file_name] = last_including_files[file_name] if last_including_files[file_name]
              new_style_dependencies[file_name] = style_dependencies[file_name] if style_dependencies[file_name]
            end
          end

          # Update data models first (always run to ensure data models are in sync)
          require_relative '../../compose/data_model_updater'
          data_updater = Compose::DataModelUpdater.new
          data_updater.update_data_models(files_to_update)

          if files_to_update.empty?
            Core::Logger.info "No files need updating (all cached)"
            return
          end

          Core::Logger.info "Updating #{files_to_update.length} of #{json_files.length} files..."

          # Initialize validators if validation is enabled
          validator = options[:validate] ? Core::AttributeValidator.new(:compose) : nil
          binding_validator = options[:validate] ? Core::BindingValidator.new : nil

          builder = Compose::ComposeBuilder.new

          files_to_update.each do |json_file|
            relative_path = Pathname.new(json_file).relative_path_from(Pathname.new(layouts_dir)).to_s
            file_name = File.basename(json_file, '.json')

            begin
              # Read and parse JSON
              json_content = File.read(json_file)
              json_data = JSON.parse(json_content)

              # Validate attributes if enabled
              if validator
                # L1-normalized layouts (`$jui` marker from `jui build`)
                # take the canonical-only validation path; raw layouts
                # keep the alias-tolerant L0 path.
                validator.normalized = Core::Normalization.canonicalized?(json_data)
                warnings = validate_json(json_data, validator, file_name)
                if warnings.any?
                  @validation_warnings.concat(warnings.map { |w| "[#{relative_path}] #{w}" })
                  @validation_errors += warnings.length
                  Core::Logger.warn "  #{warnings.length} attribute warning(s) in #{relative_path}"
                end
              end

              # Validate bindings for business logic
              if binding_validator
                binding_warnings = binding_validator.validate(json_data, relative_path)
                # The validator resets per validate() call — collect
                # error-severity canonical violations for build failure
                @binding_errors.concat(binding_validator.errors)
                if binding_warnings.any?
                  @validation_warnings.concat(binding_warnings)
                  Core::Logger.warn "  #{binding_warnings.length} binding warning(s) in #{relative_path}"
                end
              end

              # Validate variant files with the same validators (they are
              # not in json_files — the builder emits them with the base)
              JsonUIShared::LayoutVariant.variants_for(json_file).each_value do |variant_file|
                next unless validator || binding_validator
                variant_rel = Pathname.new(variant_file).relative_path_from(Pathname.new(layouts_dir)).to_s
                begin
                  variant_data = JSON.parse(File.read(variant_file))
                rescue JSON::ParserError
                  next
                end
                if validator
                  validator.normalized = Core::Normalization.canonicalized?(variant_data)
                  v_warnings = validate_json(variant_data, validator, File.basename(variant_file, '.json'))
                  if v_warnings.any?
                    @validation_warnings.concat(v_warnings.map { |w| "[#{variant_rel}] #{w}" })
                    @validation_errors += v_warnings.length
                    Core::Logger.warn "  #{v_warnings.length} attribute warning(s) in #{variant_rel}"
                  end
                end
                if binding_validator
                  v_binding_warnings = binding_validator.validate(variant_data, variant_rel)
                  @binding_errors.concat(binding_validator.errors)
                  if v_binding_warnings.any?
                    @validation_warnings.concat(v_binding_warnings)
                    Core::Logger.warn "  #{v_binding_warnings.length} binding warning(s) in #{variant_rel}"
                  end
                end
              end

              # Extract includes and styles for cache tracking
              includes = cache_manager.extract_includes(json_data)
              styles = cache_manager.extract_styles(json_data)

              new_including_files[file_name] = includes if includes.any?
              new_style_dependencies[file_name] = styles if styles.any?

              # Build Compose file
              Core::Logger.info "Processing: #{relative_path}"
              builder.build_file(json_file)

            rescue JSON::ParserError => e
              Core::Logger.error "Failed to parse #{json_file}: #{e.message}"
              failed_files << relative_path
            rescue => e
              Core::Logger.error "Failed to process #{json_file}: #{e.message}"
              failed_files << relative_path
            end
          end

          # Save cache for next build
          cache_manager.save_cache(new_including_files, new_style_dependencies)

          # A per-file failure used to be logged and stepped over, and the
          # build still ended with "completed!". The layout keeps whatever the
          # scaffold left behind — `build_file` creates the placeholder view
          # BEFORE it can raise — so the run produces a tree that is missing
          # generated code for those layouts while reporting success.
          #
          # That was survivable only because the placeholder used to name a
          # data property and the Kotlin compiler caught it. Making the
          # placeholder data-independent (so it compiles anywhere) removed the
          # last thing that noticed, which is exactly how a partial build
          # turned into a silent one. The build has to say so itself.
          # Plan 49 lane C, G's finding.
          # ComposeBuilder catches per-file exceptions itself, so most
          # failures never reach the rescue above — they arrive here.
          failed_files.concat(builder.failed_files.map { |f| f.sub("#{layouts_dir}/", '') })
          failed_files.uniq!

          unless failed_files.empty?
            Core::Logger.error "#{failed_files.length} layout(s) failed to build:"
            failed_files.each { |f| Core::Logger.error "  #{f}" }
            exit 1
          end

          # Belt and braces for the same failure mode arriving another way:
          # whatever the reason, a view still carrying the scaffold
          # placeholder has no generated code in it.
          stranded = stranded_placeholder_views(source_path, config)
          unless stranded.empty?
            Core::Logger.error "#{stranded.length} view(s) still contain the scaffold placeholder — " \
                               "their generated code was never written:"
            stranded.first(20).each { |f| Core::Logger.error "  #{f}" }
            Core::Logger.error "  … #{stranded.length - 20} more" if stranded.length > 20
            exit 1
          end

          Core::Logger.success "Compose build completed!"
        end

        # Views whose GENERATED_CODE block still holds the scaffold
        # placeholder. Compiling is not evidence that a view was generated —
        # the placeholder compiles fine and draws a plausible screen.
        def stranded_placeholder_views(source_path, config)
          require_relative '../../compose/generators/view_generator'
          view_dir = File.join(source_path, config['source_directory'] || 'src/main',
                               config['view_directory'] || 'kotlin/views')
          return [] unless Dir.exist?(view_dir)

          Dir.glob(File.join(view_dir, '**', '*GeneratedView.kt')).select do |f|
            File.read(f).include?(Compose::Generators::ViewGenerator::SCAFFOLD_PLACEHOLDER)
          end.map { |f| f.sub("#{source_path}/", '') }
        end
      end
    end
  end
end
