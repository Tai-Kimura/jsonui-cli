# frozen_string_literal: true

require 'optparse'
require 'json'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'
require_relative '../../core/attribute_validator'
require_relative '../../core/binding_validator'

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

          case mode
          when 'xml', 'all'
            build_xml(options)
          end

          if mode == 'compose' || mode == 'all'
            build_compose(options)
          end

          # Print validation summary if there were warnings
          print_validation_summary if options[:validate] != false && @validation_warnings.any?

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
          json_files = Dir.glob(File.join(layouts_dir, '**/*.json')).reject do |file|
            file.include?('/Resources/')
          end

          if json_files.empty?
            Core::Logger.warn "No JSON files found in #{layouts_dir}"
            return
          end

          # Extract resources before processing layouts
          require_relative '../../core/resources_manager'
          resources_manager = Core::ResourcesManager.new(config, source_path)
          resources_manager.extract_resources(json_files)
          Core::Logger.info "-" * 60

          # Track new includes and style dependencies
          new_including_files = {}
          new_style_dependencies = {}

          # Filter files that need update
          files_to_update = []
          json_files.each do |json_file|
            file_name = File.basename(json_file, '.json')

            # Check if file needs update
            if cache_manager.needs_update?(json_file, last_updated, layouts_dir, last_including_files, style_dependencies)
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
                if binding_warnings.any?
                  @validation_warnings.concat(binding_warnings)
                  Core::Logger.warn "  #{binding_warnings.length} binding warning(s) in #{relative_path}"
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
            rescue => e
              Core::Logger.error "Failed to process #{json_file}: #{e.message}"
            end
          end

          # Save cache for next build
          cache_manager.save_cache(new_including_files, new_style_dependencies)

          Core::Logger.success "Compose build completed!"
        end
      end
    end
  end
end
