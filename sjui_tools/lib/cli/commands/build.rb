# frozen_string_literal: true

require 'optparse'
require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'
require_relative '../../core/resources_manager'
require_relative '../../core/plural_validator'
require_relative '../../core/attribute_validator'
require_relative '../../core/normalization'
require_relative '../../core/binding_validator'
require_relative '../../core/layout_variant'
require_relative '../../core/screen_index'

module SjuiTools
  module CLI
    module Commands
      class Build
        def run(args)
          options = parse_options(args)

          # Detect mode
          mode = options[:mode] || Core::ConfigManager.detect_mode

          # Store validation results
          @validation_warnings = []
          @validation_errors = 0
          @binding_errors = []

          # Process all JSON files for string extraction
          begin
            process_strings_extraction
          rescue JsonUIShared::PluralValidator::ValidationError => e
            Core::Logger.error e.message
            exit 1
          end

          case mode
          when 'uikit', 'all'
            build_uikit(options)
          end

          if mode == 'swiftui' || mode == 'all'
            build_swiftui(options)
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
            opts.banner = "Usage: sjui build [options]"

            opts.on('--mode MODE', ['all', 'uikit', 'swiftui'],
                    'Build mode (all, uikit, swiftui)') do |mode|
              options[:mode] = mode
            end

            opts.on('--clean', 'Clean cache before building') do
              options[:clean] = true
            end

            opts.on('--no-validate', 'Skip JSON attribute validation') do
              options[:validate] = false
            end

            opts.on('--strict',
                    'Fail build on validation findings (attribute and binding warnings; ' \
                    'canonical binding errors fail with or without it)') do
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
        # @param file_name [String] The file name for error messages
        # @param parent_orientation [String, nil] The parent's orientation ('horizontal' or 'vertical')
        # @param hierarchy [String, nil] The hierarchy path (e.g., "child[0].child[1]")
        def validate_json(json_data, validator, file_name, parent_orientation = nil, hierarchy = nil)
          return [] unless json_data.is_a?(Hash)

          # Skip data definition objects (they have 'data' array but no 'type')
          return [] if json_data.key?('data') && !json_data.key?('type')

          warnings = validator.validate(json_data, nil, parent_orientation,
                                         file_name: file_name,
                                         view_id: json_data['id'],
                                         hierarchy: hierarchy)

          # Warn if Collection has items binding but no sections defined
          if json_data['type']&.downcase == 'collection' && json_data['items'] && (!json_data['sections'] || json_data['sections'].empty?)
            loc = hierarchy || 'root'
            warnings << "⚠️  [#{loc}] Collection has 'items' binding but no 'sections' defined. In SwiftUI mode, collections with 'items' should define 'sections' for proper cell rendering."
          end

          # Warn if include directive is missing id in SwiftUI mode
          if json_data.key?('include') && !json_data.key?('id')
            loc = hierarchy || 'root'
            warnings << "⚠️  [#{loc}] Include '#{json_data['include']}' is missing 'id'. In SwiftUI mode, included data properties need an id prefix to avoid name collisions."
          end

          # Warn if ScrollView has multiple child views (should wrap in a single View container)
          if json_data['type']&.downcase&.match?(/^(scrollview|scroll)$/)
            child_data = json_data['child'] || json_data['children'] || []
            child_data = [child_data] unless child_data.is_a?(Array)
            ui_children = child_data.select { |c| c.is_a?(Hash) && (c['type'] || c['include']) }
            if ui_children.length > 1
              loc = hierarchy || 'root'
              warnings << "⚠️  [#{loc}] ScrollView has #{ui_children.length} child views. Wrap them in a single View container."
            end
          end

          # Determine current orientation for passing to children
          current_orientation = json_data['orientation'] || parent_orientation

          # Validate children recursively
          children = json_data['child'] || json_data['children'] || []
          children = [children] unless children.is_a?(Array)

          children.each_with_index do |child, index|
            next unless child.is_a?(Hash)
            child_hierarchy = hierarchy ? "#{hierarchy}.child[#{index}]" : "child[#{index}]"
            warnings.concat(validate_json(child, validator, file_name, current_orientation, child_hierarchy))
          end

          # Validate sections (for Collection/Table)
          if json_data['sections'].is_a?(Array)
            json_data['sections'].each_with_index do |section, section_index|
              if section.is_a?(Hash)
                ['header', 'footer', 'cell'].each do |key|
                  next unless section[key].is_a?(Hash)
                  section_hierarchy = hierarchy ? "#{hierarchy}.sections[#{section_index}].#{key}" : "sections[#{section_index}].#{key}"
                  warnings.concat(validate_json(section[key], validator, file_name, current_orientation, section_hierarchy))
                end
              end
            end
          end

          warnings
        end

        # Canonical screen id for a layout, or nil when it is not a
        # screen. Returning nil is the whole gate: cells, partials and
        # variant structs must emit nothing.
        #
        # The bare ID is what travels: the `__screen_` prefix is the runtime
        # layer's business (SwiftJsonUI's modifier forms the identifier), so
        # passing an already-prefixed marker would double it.
        def screen_id_for(screen_index, json_file)
          return nil unless screen_index

          screen_id = JsonUIShared::ScreenIndex.screen_id_for_path(json_file)
          screen_index.screen?(screen_id) ? screen_id : nil
        end

        def build_uikit(options = {})
          Core::Logger.info "Building UIKit files..."

          # Setup project paths
          unless Core::ProjectFinder.setup_paths
            Core::Logger.error "Could not find project file (.xcodeproj or Package.swift)"
            exit 1
          end

          # Load custom view types from config
          config = Core::ConfigManager.load_config
          custom_view_types = config['custom_view_types'] || {}

          # Setup custom view types
          if custom_view_types.any?
            require_relative '../../uikit/json_loader'
            require_relative '../../uikit/import_module_manager'

            view_type_mappings = {}
            import_mappings = {}

            custom_view_types.each do |view_type, type_config|
              if type_config['class_name']
                view_type_mappings[view_type.to_sym] = type_config['class_name']
              end
              if type_config['import_module']
                import_mappings[view_type] = type_config['import_module']
              end
            end

            # Extend view type set
            UIKit::JsonLoader.view_type_set.merge!(view_type_mappings) unless view_type_mappings.empty?

            # Add import mappings
            import_mappings.each do |type, module_name|
              UIKit::ImportModuleManager.add_type_import_mapping(type, module_name)
            end
          end

          # Run JsonLoader
          require_relative '../../uikit/json_loader'
          loader = UIKit::JsonLoader.new
          loader.start_analyze
          # Error-severity canonical binding violations found during load
          # (||= keeps direct build_uikit calls, e.g. from specs, working)
          (@binding_errors ||= []).concat(loader.binding_errors)
        end

        def build_swiftui(options = {})
          Core::Logger.info "Building SwiftUI files..."

          # Setup project paths
          unless Core::ProjectFinder.setup_paths
            Core::Logger.error "Could not find project file (.xcodeproj or Package.swift)"
            exit 1
          end

          require_relative '../../swiftui/json_to_swiftui_converter'
          require_relative '../../swiftui/view_updater'
          require_relative '../../swiftui/data_model_updater'
          require_relative '../../swiftui/build_cache_manager'

          config = Core::ConfigManager.load_config
          source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
          layouts_dir = File.join(source_path, config['layouts_directory'] || 'Layouts')
          view_dir = File.join(source_path, config['view_directory'] || 'View')

          # Initialize cache manager
          cache_manager = SjuiTools::SwiftUI::BuildCacheManager.new(source_path)

          # Clean cache if --clean option is specified
          if options[:clean]
            Core::Logger.info "Cleaning build cache..."
            cache_manager.clean_cache
          end
          last_updated = cache_manager.load_last_updated
          last_including_files = cache_manager.load_last_including_files
          style_dependencies = cache_manager.load_style_dependencies

          # Process all JSON files in Layouts directory
          json_files = Dir.glob(File.join(layouts_dir, '**/*.json')).reject do |file|
            # Skip Resources folder
            next true if file.include?(File.join(layouts_dir, 'Resources'))
            # Skip responsive variant files (home@regular.json) — they are
            # converted alongside their base screen, never as standalone
            # screens (jui build's variant gate enforces the contract)
            next true if JsonUIShared::LayoutVariant.variant?(file)
            # Skip files with "mode": "uikit" (only process swiftui or unspecified)
            begin
              json_content = JSON.parse(File.read(file))
              # Skip partials (cell layouts included via Collection)
              next true if json_content['partial'] == true
              file_mode = json_content['mode']
              file_mode && file_mode.downcase == 'uikit'
            rescue JSON::ParserError
              false
            end
          end

          # Map base screen → { size_class => variant file }
          variants_by_base = json_files.each_with_object({}) do |file, map|
            found = JsonUIShared::LayoutVariant.variants_for(file)
            map[file] = found if found.any?
          end

          if json_files.empty?
            Core::Logger.warn "No JSON files found in #{layouts_dir}"
            return
          end

          # Track new includes and style dependencies
          new_including_files = {}
          new_style_dependencies = {}

          # Filter files that need update
          files_to_update = []
          json_files.each do |json_file|
            # Use relative path as cache key to avoid collision for same-named files in different directories
            rel = Pathname.new(json_file).relative_path_from(Pathname.new(layouts_dir)).to_s
            cache_key = rel.sub(/\.json$/, '')

            # Check if file needs update. A dirty variant file re-converts
            # its base screen (the dispatch + variant view live there).
            variant_dirty = (variants_by_base[json_file] || {}).values.any? do |vf|
              vrel = Pathname.new(vf).relative_path_from(Pathname.new(layouts_dir)).to_s
              cache_manager.needs_update?(vf, last_updated, layouts_dir, last_including_files, style_dependencies, vrel.sub(/\.json$/, ''))
            end
            if variant_dirty || cache_manager.needs_update?(json_file, last_updated, layouts_dir, last_including_files, style_dependencies, cache_key)
              files_to_update << json_file
            else
              # Keep existing includes and style dependencies for unchanged files
              new_including_files[cache_key] = last_including_files[cache_key] if last_including_files[cache_key]
              new_style_dependencies[cache_key] = style_dependencies[cache_key] if style_dependencies[cache_key]
            end
          end

          # Update Data models if any files need updating
          if files_to_update.any?
            Core::Logger.info "Updating #{files_to_update.length} of #{json_files.length} files..."
            data_updater = SjuiTools::SwiftUI::DataModelUpdater.new
            data_updater.update_data_models
          else
            Core::Logger.info "No files need updating (all cached)"
            return
          end

          # Initialize validators if validation is enabled
          styles_dir = File.join(source_path, config['styles_directory'] || 'Styles')
          validator = options[:validate] ? Core::AttributeValidator.new(:swiftui, styles_dir) : nil
          binding_validator = options[:validate] ? Core::BindingValidator.new : nil

          converter = SjuiTools::SwiftUI::JsonToSwiftUIConverter.new
          # Which layouts are cells / headers / footers of a vertically
          # scrolling Collection — decided over the WHOLE tree, like the
          # screen index below, so a wrapping flow inside such a cell lets
          # the host scroll (the in-tree mark cannot see across files).
          converter.scrolling_cell_ids = SjuiTools::SwiftUI::ScrollingCellIndex.build(layouts_dir)
          converter.collection_cell_ids = SjuiTools::SwiftUI::CollectionCellIndex.build(layouts_dir)
          updater = SjuiTools::SwiftUI::ViewUpdater.new

          # Screen identity: only screens carry a marker (cells and partials
          # render inside a host and would each grow a false one). Built once
          # over the WHOLE layout tree — classification depends on how other
          # layouts reference this one, so it cannot be decided per file.
          screen_index = JsonUIShared::ScreenIndex.build(
            layouts_dir,
            app_owned_screens: (config.dig('test', 'appOwnedScreens') rescue nil)
          )
          screen_index.report_lines.each { |line| Core::Logger.info line }

          files_to_update.each do |json_file|
            # Get relative path from layouts directory
            relative_path = Pathname.new(json_file).relative_path_from(Pathname.new(layouts_dir)).to_s
            base_name = File.basename(relative_path, '.json')
            file_name = File.basename(json_file, '.json')
            dir_path = File.dirname(relative_path)
            cache_key = relative_path.sub(/\.json$/, '')

            # Read and parse JSON to extract includes and styles
            begin
              json_content = File.read(json_file)
              json_data = JSON.parse(json_content)

              # Validate attributes if enabled
              if validator
                # L1-normalized layouts (`$jui` marker) take the
                # canonical-only validation path
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
                  # --strict gates on these too. The flag says "validation
                  # errors" and a binding warning is a validation finding, but
                  # only attribute warnings were counted: measured 2026-09-04,
                  # a tree reporting four findings still exited 0 under
                  # --strict because all four came from the binding validator.
                  @validation_errors += binding_warnings.length
                  Core::Logger.warn "  #{binding_warnings.length} binding warning(s) in #{relative_path}"
                end
              end

              # Extract includes and styles for cache tracking
              includes = cache_manager.extract_includes(json_data)
              styles = cache_manager.extract_styles(json_data)

              new_including_files[cache_key] = includes if includes.any?
              new_style_dependencies[cache_key] = styles if styles.any?
            rescue => ex
              Core::Logger.warn "Failed to parse #{json_file}: #{ex.message}"
            end

            # Convert to PascalCase for Swift file
            view_name = base_name.split(/[_\-]/).map(&:capitalize).join

            # Determine Swift file path - now targeting GeneratedView in view folder
            # Convert directory segments to PascalCase to match View folder naming convention
            swift_file = if dir_path == '.'
              File.join(view_dir, view_name, "#{view_name}GeneratedView.swift")
            else
              pascal_dir = dir_path.split('/').map { |s| s.split(/[_\-]/).map(&:capitalize).join }.join('/')
              File.join(view_dir, pascal_dir, view_name, "#{view_name}GeneratedView.swift")
            end

            # Responsive variant files attached to this base screen
            # (home@regular.json → HomeRegularVariantGeneratedView + a size
            # class dispatch in the base GeneratedView)
            variants = variants_by_base[json_file] || {}
            variant_structs = variants.keys.each_with_object({}) do |cls, map|
              map[cls] = "#{view_name}#{cls.capitalize}VariantGeneratedView"
            end
            variant_kwargs = variants.any? ? { variant_dispatch: variant_structs, force_typed_view_model: true } : {}

            if File.exist?(swift_file)
              Core::Logger.info "Processing: #{relative_path}"

              # Convert JSON to SwiftUI code
              swiftui_code, _, state_variables, root_children, responsive_functions = converter.convert_json_to_view(json_file)

              # Update the existing Swift file's generatedBody
              updater.update_generated_body(swift_file, swiftui_code, state_variables: state_variables || [], root_children: root_children, responsive_functions: responsive_functions || [], screen_id: screen_id_for(screen_index, json_file), **variant_kwargs)

              Core::Logger.info "  Updated: #{swift_file}"
            else
              # Auto-generate GeneratedView.swift for new layout
              Core::Logger.info "  Generating view for new layout: #{relative_path}"

              # Create directory
              swift_dir = File.dirname(swift_file)
              FileUtils.mkdir_p(swift_dir)

              # Determine json reference for DynamicView
              json_reference = dir_path == '.' ? base_name : "#{dir_path}/#{base_name}"

              # Create minimal GeneratedView.swift stub
              stub_content = <<~SWIFT
                import SwiftUI
                import SwiftJsonUI
                import Combine

                struct #{view_name}GeneratedView: View {
                    @SwiftUI.Binding var data: #{view_name}Data

                    var body: some View {
                        if ViewSwitcher.isDynamicMode {
                            DynamicView(jsonName: "#{json_reference}", viewId: "#{base_name}_view", data: data.toDictionary())
                        } else {
                            // >>> GENERATED_CODE_START
                            Text("Placeholder")
                            // >>> GENERATED_CODE_END
                        }
                    }
                }
              SWIFT

              File.write(swift_file, stub_content)

              # Now process the newly created file
              swiftui_code, _, state_variables, root_children, responsive_functions = converter.convert_json_to_view(json_file)
              updater.update_generated_body(swift_file, swiftui_code, state_variables: state_variables || [], root_children: root_children, responsive_functions: responsive_functions || [], screen_id: screen_id_for(screen_index, json_file), **variant_kwargs)
              Core::Logger.info "  Created and updated: #{swift_file}"
            end

            # Emit one GeneratedView per variant file. Variants share the
            # base screen's Data type and ViewModel — the dispatch in the
            # base GeneratedView selects the tree, the wrapper's single VM
            # instance survives the swap (06a-design.md D4/D5).
            variants.each do |cls, variant_file|
              variant_rel = Pathname.new(variant_file).relative_path_from(Pathname.new(layouts_dir)).to_s
              variant_struct = variant_structs[cls]
              variant_swift_file = File.join(File.dirname(swift_file), "#{variant_struct}.swift")
              variant_source = variant_rel.sub(/\.json$/, '')

              begin
                variant_json = JSON.parse(File.read(variant_file))
                if validator
                  validator.normalized = Core::Normalization.canonicalized?(variant_json)
                  warnings = validate_json(variant_json, validator, File.basename(variant_file, '.json'))
                  if warnings.any?
                    @validation_warnings.concat(warnings.map { |w| "[#{variant_rel}] #{w}" })
                    @validation_errors += warnings.length
                    Core::Logger.warn "  #{warnings.length} attribute warning(s) in #{variant_rel}"
                  end
                end
                if binding_validator
                  binding_warnings = binding_validator.validate(variant_json, variant_rel)
                  @binding_errors.concat(binding_validator.errors)
                  if binding_warnings.any?
                    @validation_warnings.concat(binding_warnings)
                    # Same as the primary path: --strict counts binding findings.
                    @validation_errors += binding_warnings.length
                    Core::Logger.warn "  #{binding_warnings.length} binding warning(s) in #{variant_rel}"
                  end
                end
              rescue => ex
                Core::Logger.warn "Failed to parse #{variant_file}: #{ex.message}"
              end

              unless File.exist?(variant_swift_file)
                FileUtils.mkdir_p(File.dirname(variant_swift_file))
                stub_content = <<~SWIFT
                  import SwiftUI
                  import SwiftJsonUI
                  import Combine

                  struct #{variant_struct}: View {
                      @SwiftUI.Binding var data: #{view_name}Data

                      var body: some View {
                          // >>> GENERATED_CODE_START
                          Text("Placeholder")
                          // >>> GENERATED_CODE_END
                      }
                  }
                SWIFT
                File.write(variant_swift_file, stub_content)
              end

              v_code, _, v_state, v_children, v_responsive = converter.convert_json_to_view(variant_file)
              updater.update_generated_body(variant_swift_file, v_code, state_variables: v_state || [], root_children: v_children, responsive_functions: v_responsive || [], force_typed_view_model: true, view_model_type: "#{view_name}ViewModel", source_name: variant_source)
              Core::Logger.info "  Updated variant: #{variant_swift_file}"
            end
          end

          # Save cache for next build
          cache_manager.save_cache(new_including_files, new_style_dependencies)

          Core::Logger.success "SwiftUI build completed!"
        end

        def process_strings_extraction
          # Setup project paths
          unless Core::ProjectFinder.setup_paths
            Core::Logger.error "Could not find project file"
            return
          end

          config = Core::ConfigManager.load_config
          source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
          layouts_dir = File.join(source_path, config['layouts_directory'] || 'Layouts')

          # Load cache to check for modified files
          cache_dir = File.join(source_path, '.sjui_cache')

          # For SwiftUI mode, use swiftui_last_updated.txt
          if config['mode'] == 'swiftui'
            last_updated_file = File.join(cache_dir, 'swiftui_last_updated.txt')
            last_updated = {}

            if File.exist?(last_updated_file)
              File.readlines(last_updated_file).each do |line|
                parts = line.strip.split(':', 2)
                if parts.length == 2
                  last_updated[parts[0]] = parts[1].to_i
                end
              end
            end
          else
            # For UIKit mode, use last_updated.json
            last_updated_file = File.join(cache_dir, 'last_updated.json')
            last_updated = {}

            if File.exist?(last_updated_file)
              begin
                last_updated = JSON.parse(File.read(last_updated_file))
              rescue JSON::ParserError
                Core::Logger.warn "Failed to parse cache file, processing all files"
              end
            end
          end

          # Process all resources through ResourcesManager
          resources_manager = Core::ResourcesManager.new
          resources_manager.process_resources(layouts_dir, last_updated)
        end
      end
    end
  end
end
