# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative '../core/config_manager'
require_relative '../core/project_finder'
require_relative '../core/logger'
require_relative '../core/type_converter'
require_relative '../core/layout_validator'
require_relative 'style_loader'
require_relative 'include_expander'
require_relative 'data_model_updater'
require_relative 'helpers/import_manager'
require_relative 'helpers/modifier_builder'
require_relative 'helpers/resource_resolver'
require_relative 'helpers/visibility_helper'
require_relative 'helpers/responsive_helper'
require_relative 'components/text_component'
require_relative 'components/button_component'
require_relative 'components/textfield_component'
require_relative 'components/container_component'
require_relative 'components/image_component'
require_relative 'components/scrollview_component'
require_relative 'components/switch_component'
require_relative 'components/slider_component'
require_relative 'components/progress_component'
require_relative 'components/selectbox_component'
require_relative 'components/checkbox_component'
require_relative 'components/radio_component'
require_relative 'components/segment_component'
require_relative 'components/networkimage_component'
require_relative 'components/circleimage_component'
require_relative 'components/indicator_component'
require_relative 'components/textview_component'
require_relative 'components/collection_component'
require_relative 'components/table_component'
require_relative 'components/web_component'
require_relative 'components/webview_component'
require_relative 'components/gradientview_component'
require_relative 'components/blurview_component'
require_relative 'components/tabview_component'
require_relative 'components/embed_component'
require_relative 'generators/view_generator'

module KjuiTools
  module Compose
    # Refactored ComposeBuilder - under 300 lines
    class ComposeBuilder
      def initialize
        @config = Core::ConfigManager.load_config
        @source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
        source_directory = @config['source_directory'] || 'src/main'
        @layouts_dir = File.join(@source_path, source_directory, @config['layouts_directory'] || 'assets/Layouts')
        @view_dir = File.join(@source_path, source_directory, @config['view_directory'] || 'kotlin/views')
        @package_name = @config['package_name'] || Core::ProjectFinder.get_package_name || 'com.example.app'

        FileUtils.mkdir_p(@view_dir) unless File.exist?(@view_dir)
      end

      def build(options = {})
        # Get all JSON files but exclude Resources folder
        json_files = Dir.glob(File.join(@layouts_dir, '**/*.json')).reject do |file|
          file.include?('/Resources/')
        end

        if json_files.empty?
          Core::Logger.warn "No JSON files found in #{@layouts_dir}"
          return
        end

        # Update data models first
        data_updater = DataModelUpdater.new
        data_updater.update_data_models

        # Build each JSON file
        json_files.each { |file| build_file(file) }
      end

      def build_file(json_file)
        base_name = File.basename(json_file, '.json')
        snake_case_name = to_snake_case(base_name)
        pascal_case_name = to_pascal_case(base_name)

        begin
          json_content = File.read(json_file)
          json_data = JSON.parse(json_content)

          # Skip partial files (they are included in other views, not standalone)
          if json_data['partial'] == true
            return nil
          end

          json_data = StyleLoader.load_and_merge(json_data)

          shared_warnings = JsonUIShared::LayoutValidator.validate_layout(
            json_data, source_path: File.basename(json_file)
          )
          JsonUIShared::LayoutValidator.print_warnings(shared_warnings) unless shared_warnings.empty?

          # Process includes - expand inline with ID prefix support (like SwiftJsonUI)
          json_data = IncludeExpander.process_includes(json_data, File.dirname(json_file))

          @required_imports = Set.new
          @included_views = Set.new
          @custom_components = Set.new
          @responsive_functions = []
          @responsive_counter = 0

          # Collect data definitions for ResourceResolver to check optional/non-optional
          data_properties = extract_data_properties(json_data)
          data_definitions = {}
          data_properties.each do |prop|
            data_definitions[prop['name']] = prop
          end
          Helpers::ResourceResolver.data_definitions = data_definitions

          # Find the GeneratedView file - preserve subdirectory structure from layouts
          relative_path = json_file.sub(@layouts_dir + '/', '')
          relative_dir = File.dirname(relative_path)
          if relative_dir == '.'
            view_subdir = snake_case_name
          else
            view_subdir = File.join(relative_dir, snake_case_name)
          end
          generated_view_file = File.join(@view_dir, view_subdir, "#{pascal_case_name}GeneratedView.kt")

          # Update ViewModel's updateData function
          source_directory = @config['source_directory'] || 'src/main'
          viewmodel_dir = File.join(@source_path, source_directory, @config['viewmodel_directory'] || 'kotlin/viewmodels')
          viewmodel_file = File.join(viewmodel_dir, "#{pascal_case_name}ViewModel.kt")

          # If MainView / GeneratedView / ViewModel haven't been scaffolded yet
          # (e.g., the layout JSON was added by hand), fall back to the same
          # template the `kjui g view` generator uses. Each underlying
          # `create_*_template` is a no-op when the file already exists, so
          # this stays idempotent on subsequent builds.
          unless File.exist?(generated_view_file) && File.exist?(viewmodel_file)
            scaffold_name = relative_path.sub(/\.json$/, '')
            begin
              Generators::ViewGenerator.new(scaffold_name).ensure_kotlin_files_exist(base_path: @source_path)
            rescue => e
              Core::Logger.warn "Could not scaffold Kotlin files for #{scaffold_name}: #{e.message}"
            end
          end

          if File.exist?(generated_view_file)
            # Calculate the layout name for dynamic mode (relative path without .json)
            dynamic_layout_name = relative_path.sub(/\.json$/, '')
            update_generated_file(generated_view_file, json_data, dynamic_layout_name)
          else
            Core::Logger.warn "GeneratedView file not found: #{generated_view_file}"
          end

          if File.exist?(viewmodel_file)
            update_viewmodel_file(viewmodel_file, json_data, pascal_case_name)
          else
            # Check for cell ViewModels in subdirectories (e.g., viewmodels/Home/ItemCardViewModel.kt)
            cell_viewmodel_files = Dir.glob(File.join(viewmodel_dir, '**', "#{pascal_case_name}ViewModel.kt"))
            cell_viewmodel_files.each do |cell_vm_file|
              update_viewmodel_file(cell_vm_file, json_data, pascal_case_name)
            end
          end

        rescue JSON::ParserError => e
          Core::Logger.error "Failed to parse #{json_file}: #{e.message}"
        rescue => e
          Core::Logger.error "Failed to process #{json_file}: #{e.message}"
        end
      end

      private

      def generate_component(json_data, depth = 0, parent_type = nil)
        return "" unless json_data.is_a?(Hash)

        # Skip data-spec / shared_data / variables entries that may appear
        # inline in a `child:` array (no `type` key, no `include`). Without
        # this, generate_component falls through to type=View → emits a
        # spurious empty Box. Mirrors sjui's view_converter child filter.
        if !json_data.key?('type') && !json_data.key?('include') &&
           (json_data.key?('data') || json_data.key?('shared_data') || json_data.key?('variables'))
          return ""
        end

        # Embed + responsive: inline the if/else chain at the call site
        # instead of extracting to a private composable. Extraction would
        # leak the parent scope's `data` / `viewModel` / `windowSizeClass`
        # references out of the function signature, AND would inject the
        # private function INSIDE the GENERATED_CODE_START..END marker pair
        # (see update_generated_file responsive_functions append). Inline
        # avoids both.
        if json_data['type'] == 'Embed' && Helpers::ResponsiveHelper.responsive?(json_data)
          return generate_embed_responsive_inline(json_data, depth, parent_type)
        end

        # Check for responsive component — delegate to responsive generation
        if Helpers::ResponsiveHelper.responsive?(json_data)
          return generate_responsive_component(json_data, depth, parent_type)
        end

        component_type = json_data['type'] || 'View'

        # Includes should have been expanded by IncludeExpander.process_includes
        # If we still see an include here, it's a bug
        if json_data['include']
          raise "Include should have been expanded by IncludeExpander.process_includes. This is a bug."
        end

        # Generate component based on type
        code = case component_type
        when 'ScrollView', 'Scroll'
          result = Components::ScrollViewComponent.generate(json_data, depth, @required_imports, parent_type)
          handle_container_result(result, depth, parent_type)
        when 'SafeAreaView'
          generate_safe_area_view(json_data, depth)
        when 'View'
          result = Components::ContainerComponent.generate(json_data, depth, @required_imports, parent_type)
          handle_container_result(result, depth, parent_type)
        when 'Text', 'Label'
          Components::TextComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Button'
          Components::ButtonComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Image'
          Components::ImageComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'TextField'
          Components::TextFieldComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Switch', 'Toggle'
          Components::SwitchComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Slider'
          Components::SliderComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Progress'
          Components::ProgressComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'SelectBox'
          Components::SelectBoxComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Check', 'Checkbox', 'CheckBox'
          Components::CheckboxComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Radio'
          Components::RadioComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Segment'
          Components::SegmentComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'NetworkImage'
          Components::NetworkImageComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'CircleImage'
          Components::CircleImageComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Indicator'
          Components::IndicatorComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'TextView'
          Components::TextViewComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Collection'
          Components::CollectionComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Table'
          Components::TableComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Web'
          Components::WebComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'WebView'
          Components::WebviewComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'GradientView'
          result = Components::GradientviewComponent.generate(json_data, depth, @required_imports, parent_type)
          handle_container_result(result, depth, parent_type)
        when 'BlurView'
          result = Components::BlurviewComponent.generate(json_data, depth, @required_imports, parent_type)
          handle_container_result(result, depth, parent_type)
        when 'TabView'
          result = Components::TabviewComponent.generate(json_data, depth, @required_imports, parent_type)
          handle_container_result(result, depth, parent_type)
        when 'Embed'
          result = Components::EmbedComponent.generate(json_data, depth, @required_imports, parent_type)
          handle_container_result(result, depth, parent_type)
        when 'Spacer'
          "Spacer(modifier = Modifier.height(#{json_data['height'] || 8}.dp))"
        else
          # Check for custom components
          check_custom_component(component_type, json_data, depth, parent_type)
        end

        # Wrap with VisibilityWrapper for all components
        # Container types already handle this in handle_container_result, so skip them
        unless %w[View ScrollView Scroll GradientView BlurView TabView Embed].include?(component_type)
          code = Helpers::VisibilityHelper.wrap_with_visibility(json_data, code, depth, @required_imports, parent_type) if code.is_a?(String) && !code.empty?
        end

        code
      end

      # Embed + responsive: emit an inline if/else chain that calls
      # EmbedComponent.generate per branch with merged attrs. No private
      # composable is extracted, so data/viewModel references inside the
      # EmbedContainer body resolve against the enclosing GeneratedView scope.
      #
      # Condition expressions are emitted in their *standalone* form (e.g.
      # `LocalConfiguration.current.screenWidthDp >= 840`) rather than the
      # `windowSizeClass.widthSizeClass == WindowWidthSizeClass.Expanded`
      # form used by the extracted private-composable path. The GeneratedView
      # signature only carries `(data, viewModel, modifier)`, so it has no
      # `windowSizeClass` variable in scope; using LocalConfiguration directly
      # avoids needing to thread one in. Thresholds match Material3's
      # WindowWidthSizeClass definitions: compact <600dp, medium 600..839dp,
      # expanded >=840dp.
      def generate_embed_responsive_inline(json_data, depth, parent_type)
        branches = JsonUIShared::ResponsiveResolver.build_branches(json_data)
        @required_imports&.add(:local_configuration)

        lines = []
        first = true
        branches.each do |branch|
          condition = build_embed_inline_condition(branch[:size_class])
          attrs = branch[:attrs].dup
          attrs.delete('responsive')

          if condition
            keyword = first ? 'if' : '} else if'
            lines << indent("#{keyword} (#{condition}) {", depth)
            first = false
          elsif first
            # Only a default branch — no conditional at all.
            lines << Components::EmbedComponent.generate(attrs, depth, @required_imports, parent_type)
            return lines.join("\n")
          else
            lines << indent("} else {", depth)
          end

          lines << Components::EmbedComponent.generate(attrs, depth + 1, @required_imports, parent_type)
        end

        lines << indent("}", depth)
        lines.join("\n")
      end

      INLINE_WIDTH_CONDITIONS = {
        'compact' => 'LocalConfiguration.current.screenWidthDp < 600',
        'medium'  => 'LocalConfiguration.current.screenWidthDp in 600..839',
        'regular' => 'LocalConfiguration.current.screenWidthDp >= 840'
      }.freeze
      INLINE_LANDSCAPE_CONDITION = 'LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE'

      # Build a standalone Kotlin boolean expression for a size class key,
      # using only LocalConfiguration so the call site doesn't need to have
      # a `windowSizeClass` variable in scope. Returns nil for the default
      # (else) branch.
      def build_embed_inline_condition(size_class)
        return nil if size_class.nil?

        parsed = JsonUIShared::ResponsiveResolver.parse_size_class(size_class)
        conditions = []
        conditions << INLINE_WIDTH_CONDITIONS[parsed[:width]] if INLINE_WIDTH_CONDITIONS.key?(parsed[:width])
        conditions << INLINE_LANDSCAPE_CONDITION if parsed[:landscape]
        return nil if conditions.empty?
        conditions.join(' && ')
      end

      # Generate code for a component that has a `responsive` block.
      # Produces:
      #   - A private @Composable function (accumulated in @responsive_functions)
      #   - An inline call to that function at the current depth
      def generate_responsive_component(json_data, depth, parent_type)
        component_type = json_data['type'] || 'View'
        has_children = has_component_children?(json_data)

        # Generate a unique function name
        @responsive_counter += 1
        func_name = "Responsive#{component_type.gsub(/[^A-Za-z0-9]/, '')}#{@responsive_counter}"

        if has_children
          generate_responsive_container(json_data, depth, parent_type, func_name)
        else
          generate_responsive_leaf(json_data, depth, parent_type, func_name)
        end
      end

      # Generate responsive container: extracts wrapper function, renders children inline
      def generate_responsive_container(json_data, depth, parent_type, func_name)
        children = json_data['child'] || []
        children = [children] unless children.is_a?(Array)

        # Build the wrapper function that switches container per branch
        result = Helpers::ResponsiveHelper.generate_container_wrapper(
          func_name, json_data, 0, @required_imports
        ) do |attrs, branch_depth, imports|
          # Generate the container opening code for this branch's attributes
          branch_result = Components::ContainerComponent.generate(attrs, branch_depth, imports, parent_type)
          if branch_result.is_a?(Hash)
            # Container opening + "content()" call + closing
            code = branch_result[:code]
            code += "\n" + indent("content()", branch_depth + 1)
            code += branch_result[:closing] if branch_result[:closing]
            code
          else
            branch_result
          end
        end

        # Accumulate the function definition
        @responsive_functions << result[:function_code]

        # Generate the call site: wrapper function wrapping children
        call_code = indent("#{func_name}(windowSizeClass = windowSizeClass) {", depth)

        # Determine the layout type for children from the default branch
        # Use vertical as a safe default for child layout context
        default_attrs = json_data.dup
        default_attrs.delete('responsive')
        layout_type = determine_child_layout_type(default_attrs)

        children.each do |child|
          child_code = generate_component(child, depth + 1, layout_type)
          call_code += "\n" + child_code unless child_code.empty?
        end
        call_code += "\n" + indent("}", depth)

        call_code
      end

      # Generate responsive leaf: extracts function, returns call
      def generate_responsive_leaf(json_data, depth, parent_type, func_name)
        result = Helpers::ResponsiveHelper.generate_leaf_wrapper(
          func_name, json_data, 0, @required_imports
        ) do |attrs, branch_depth, imports|
          # Generate the full component for this branch
          generate_non_responsive_component(attrs, branch_depth, parent_type)
        end

        @responsive_functions << result[:function_code]

        # Return the call site
        indent("#{func_name}(windowSizeClass = windowSizeClass)", depth)
      end

      # Generate a component without responsive handling (to avoid infinite recursion)
      def generate_non_responsive_component(json_data, depth, parent_type)
        component_type = json_data['type'] || 'View'

        code = case component_type
        when 'Text', 'Label'
          Components::TextComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Button'
          Components::ButtonComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Image'
          Components::ImageComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'View'
          result = Components::ContainerComponent.generate(json_data, depth, @required_imports, parent_type)
          handle_container_result(result, depth, parent_type)
        else
          # Fall through to normal generation for other types (responsive already stripped)
          generate_component(json_data, depth, parent_type)
        end

        code
      end

      def has_component_children?(json_data)
        children = json_data['child']
        return false unless children
        return true if children.is_a?(Array) && !children.empty?
        return true if children.is_a?(Hash)
        false
      end

      def determine_child_layout_type(attrs)
        orientation = attrs['orientation']
        case orientation
        when 'horizontal' then 'Row'
        when 'vertical' then 'Column'
        else 'Box'
        end
      end

      def check_custom_component(component_type, json_data, depth, parent_type)
        # Try to load custom component mappings if they exist
        mappings_file = File.join(File.dirname(__FILE__), 'components', 'extensions', 'component_mappings.rb')

        if File.exist?(mappings_file)
          require_relative 'components/extensions/component_mappings'

          if defined?(Components::Extensions::COMPONENT_MAPPINGS)
            component_class = Components::Extensions::COMPONENT_MAPPINGS[component_type]

            if component_class
              # Load the custom component file
              snake_case_name = component_type.gsub(/([A-Z]+)([A-Z][a-z])/,'\1_\2')
                                            .gsub(/([a-z\d])([A-Z])/,'\1_\2')
                                            .downcase
              component_file = File.join(File.dirname(__FILE__), 'components', 'extensions', "#{snake_case_name}_component.rb")

              if File.exist?(component_file)
                require_relative "components/extensions/#{snake_case_name}_component"

                # Add import for the custom component
                @custom_components&.add(component_type)

                result = component_class.generate(json_data, depth, @required_imports, parent_type)

                # Handle container components that return metadata
                if result.is_a?(Hash) && result[:children]
                  return handle_container_result(result, depth, parent_type)
                else
                  return result
                end
              end
            end
          end
        end

        "// TODO: Implement component type: #{component_type}"
      end

      def handle_container_result(result, depth, parent_type = nil)
        if result.is_a?(Hash)
          code = result[:code]
          children = result[:children] || []
          layout_type = result[:layout_type] || parent_type
          json_data = result[:json_data]

          # Add lifecycle effects at the start of container content
          if json_data && Helpers::ModifierBuilder.has_lifecycle_events?(json_data)
            lifecycle = Helpers::ModifierBuilder.build_lifecycle_effects(json_data, depth + 1, @required_imports)
            code += "\n" + lifecycle[:before] unless lifecycle[:before].empty?
          end

          children.each do |child|
            child_code = generate_component(child, depth + 1, layout_type)
            code += "\n" + child_code unless child_code.empty?
          end

          code += result[:closing] if result[:closing]

          # Wrap with VisibilityWrapper if visibility binding is specified
          if json_data
            code = Helpers::VisibilityHelper.wrap_with_visibility(json_data, code, depth, @required_imports, parent_type)
          end

          code
        else
          result
        end
      end

      def generate_safe_area_view(json_data, depth)
        # Add import for SafeAreaConfig
        @required_imports&.add(:safe_area_config)

        # Parse edges - support both 'edges' and 'safeAreaInsetPositions' (alias)
        edges_array = json_data['edges'] || json_data['safeAreaInsetPositions'] || ['all']
        edges = edges_array.is_a?(Array) ? edges_array : [edges_array]

        # Get children - support both 'child' and 'children'
        children = json_data['children'] || json_data['child'] || []
        children = [children] unless children.is_a?(Array)

        # Check if any child has relative positioning - if so, use ConstraintLayout
        if has_relative_positioning_in_children?(children)
          return generate_safe_area_view_with_constraints(json_data, children, edges, depth)
        end

        # Parse orientation for child layout
        orientation = json_data['orientation']

        # Determine container type based on orientation
        # No orientation = Box (like ZStack in SwiftUI)
        container = case orientation
                    when 'horizontal' then 'Row'
                    when 'vertical' then 'Column'
                    else 'Box'
                    end

        # Get parent SafeAreaConfig and filter edges
        code = indent("val safeAreaConfig = LocalSafeAreaConfig.current", depth)
        code += "\n" + indent("val edges = mutableListOf(#{edges.map { |e| "\"#{e}\"" }.join(', ')}).apply {", depth)
        code += "\n" + indent("if (safeAreaConfig.ignoreBottom) {", depth + 1)
        code += "\n" + indent("remove(\"bottom\")", depth + 2)
        code += "\n" + indent("if (contains(\"all\")) { remove(\"all\"); addAll(listOf(\"top\", \"start\", \"end\")) }", depth + 2)
        code += "\n" + indent("}", depth + 1)
        code += "\n" + indent("if (safeAreaConfig.ignoreTop) {", depth + 1)
        code += "\n" + indent("remove(\"top\")", depth + 2)
        code += "\n" + indent("if (contains(\"all\")) { remove(\"all\"); addAll(listOf(\"bottom\", \"start\", \"end\")) }", depth + 2)
        code += "\n" + indent("}", depth + 1)
        code += "\n" + indent("}.distinct()", depth)

        code += "\n\n" + indent("#{container}(", depth)

        # Build modifiers
        # Background must come BEFORE systemBarsPadding so it extends to screen edges
        modifiers = ["Modifier"]
        modifiers << ".fillMaxWidth()"
        modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, @required_imports))

        # Apply safe area padding based on edges (after background)
        # Use conditional modifiers based on runtime edges
        modifiers << ".then(if (edges.contains(\"all\")) Modifier.systemBarsPadding() else Modifier)"
        modifiers << ".then(if (!edges.contains(\"all\") && edges.contains(\"top\")) Modifier.statusBarsPadding() else Modifier)"
        modifiers << ".then(if (!edges.contains(\"all\") && edges.contains(\"bottom\")) Modifier.navigationBarsPadding() else Modifier)"

        # Check if keyboard padding should be applied
        ignore_keyboard = json_data['ignoreKeyboard'] == true
        modifiers << ".imePadding()" unless ignore_keyboard

        modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
        modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

        code += Helpers::ModifierBuilder.format(modifiers, depth)
        code += "\n" + indent(") {", depth)

        children.each do |child|
          child_code = generate_component(child, depth + 1, container)
          code += "\n" + child_code unless child_code.empty?
        end

        code += "\n" + indent("}", depth)
        code
      end

      def has_relative_positioning_in_children?(children)
        relative_attrs = [
          'alignTopOfView', 'alignBottomOfView', 'alignLeftOfView', 'alignRightOfView',
          'alignTopView', 'alignBottomView', 'alignLeftView', 'alignRightView',
          'alignCenterVerticalView', 'alignCenterHorizontalView'
        ]

        children.any? do |child|
          next false unless child.is_a?(Hash)
          relative_attrs.any? { |attr| child[attr] }
        end
      end

      def generate_safe_area_view_with_constraints(json_data, children, edges, depth)
        @required_imports&.add(:constraint_layout)

        # Get parent SafeAreaConfig and filter edges
        code = indent("val safeAreaConfig = LocalSafeAreaConfig.current", depth)
        code += "\n" + indent("val edges = mutableListOf(#{edges.map { |e| "\"#{e}\"" }.join(', ')}).apply {", depth)
        code += "\n" + indent("if (safeAreaConfig.ignoreBottom) {", depth + 1)
        code += "\n" + indent("remove(\"bottom\")", depth + 2)
        code += "\n" + indent("if (contains(\"all\")) { remove(\"all\"); addAll(listOf(\"top\", \"start\", \"end\")) }", depth + 2)
        code += "\n" + indent("}", depth + 1)
        code += "\n" + indent("if (safeAreaConfig.ignoreTop) {", depth + 1)
        code += "\n" + indent("remove(\"top\")", depth + 2)
        code += "\n" + indent("if (contains(\"all\")) { remove(\"all\"); addAll(listOf(\"bottom\", \"start\", \"end\")) }", depth + 2)
        code += "\n" + indent("}", depth + 1)
        code += "\n" + indent("}.distinct()", depth)

        code += "\n\n" + indent("ConstraintLayout(", depth)

        # Build modifiers
        modifiers = ["Modifier"]
        modifiers << ".fillMaxSize()"
        modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, @required_imports))

        # Apply safe area padding based on edges (after background)
        modifiers << ".then(if (edges.contains(\"all\")) Modifier.systemBarsPadding() else Modifier)"
        modifiers << ".then(if (!edges.contains(\"all\") && edges.contains(\"top\")) Modifier.statusBarsPadding() else Modifier)"
        modifiers << ".then(if (!edges.contains(\"all\") && edges.contains(\"bottom\")) Modifier.navigationBarsPadding() else Modifier)"

        # Check if keyboard padding should be applied
        ignore_keyboard = json_data['ignoreKeyboard'] == true
        modifiers << ".imePadding()" unless ignore_keyboard

        modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
        modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))

        code += Helpers::ModifierBuilder.format(modifiers, depth)
        code += "\n" + indent(") {", depth)

        # Create constraint references for children with IDs
        children.each do |child|
          next unless child.is_a?(Hash) && child['id']
          ref_name = child['id']
          code += "\n" + indent("val #{ref_name} = createRef()", depth + 1)
        end
        code += "\n"

        # Generate children with constraints
        children.each do |child|
          next unless child.is_a?(Hash)
          child_code = generate_safe_area_child_with_constraints(child, depth + 1)
          code += "\n" + child_code unless child_code.empty?
        end

        code += "\n" + indent("}", depth)
        code
      end

      def generate_safe_area_child_with_constraints(child_data, depth)
        ref_name = child_data['id']
        component_type = child_data['type'] || 'View'

        # Build constraints for this child
        constraints = Helpers::ModifierBuilder.build_relative_positioning(child_data)

        # Generate the component based on type
        case component_type
        when 'ScrollView', 'Scroll'
          generate_scroll_with_constraints(child_data, ref_name, constraints, depth)
        when 'View'
          generate_view_with_constraints(child_data, ref_name, constraints, depth)
        else
          # For other types, generate normally but wrap with constraint modifier
          generate_component_with_constraints(child_data, ref_name, constraints, depth)
        end
      end

      def generate_scroll_with_constraints(child_data, ref_name, constraints, depth)
        # Generate LazyColumn with constrainAs modifier
        code = indent("LazyColumn(", depth)

        modifiers = ["Modifier"]

        # Add constrainAs if we have a ref_name
        if ref_name
          constraint_block = constraints.any? ? constraints.join("\n" + "    " * (depth + 2)) : ""
          modifiers << ".constrainAs(#{ref_name}) {\n" + indent(constraint_block, depth + 2) + "\n" + indent("}", depth + 1)
        end

        modifiers.concat(Helpers::ModifierBuilder.build_size(child_data))

        # Check if keyboard padding should be applied
        ignore_keyboard = child_data['ignoreKeyboard'] == true
        modifiers << ".imePadding()" unless ignore_keyboard

        code += Helpers::ModifierBuilder.format(modifiers, depth)
        code += "\n" + indent(") {", depth)

        # Process scroll content
        scroll_children = child_data['child'] || child_data['children'] || []
        scroll_children = [scroll_children] unless scroll_children.is_a?(Array)

        code += "\n" + indent("item {", depth + 1)
        scroll_children.each do |scroll_child|
          child_code = generate_component(scroll_child, depth + 2)
          code += "\n" + child_code unless child_code.empty?
        end
        code += "\n" + indent("}", depth + 1)

        code += "\n" + indent("}", depth)
        code
      end

      def generate_view_with_constraints(child_data, ref_name, constraints, depth)
        # Determine layout type based on orientation
        orientation = child_data['orientation']
        container = case orientation
                    when 'horizontal' then 'Row'
                    when 'vertical' then 'Column'
                    else 'Box'
                    end

        code = indent("#{container}(", depth)

        modifiers = ["Modifier"]

        # Add constrainAs if we have a ref_name
        if ref_name
          constraint_block = constraints.any? ? constraints.join("\n" + "    " * (depth + 2)) : ""
          modifiers << ".constrainAs(#{ref_name}) {\n" + indent(constraint_block, depth + 2) + "\n" + indent("}", depth + 1)
        end

        modifiers.concat(Helpers::ModifierBuilder.build_size(child_data))
        modifiers.concat(Helpers::ModifierBuilder.build_margins(child_data))
        modifiers.concat(Helpers::ModifierBuilder.build_background(child_data, @required_imports))
        modifiers.concat(Helpers::ModifierBuilder.build_padding(child_data))

        code += Helpers::ModifierBuilder.format(modifiers, depth)
        code += "\n" + indent(") {", depth)

        # Process children
        view_children = child_data['child'] || child_data['children'] || []
        view_children = [view_children] unless view_children.is_a?(Array)

        view_children.each do |view_child|
          child_code = generate_component(view_child, depth + 1, container)
          code += "\n" + child_code unless child_code.empty?
        end

        code += "\n" + indent("}", depth)
        code
      end

      def generate_component_with_constraints(child_data, ref_name, constraints, depth)
        # Generate the component normally and then add constrainAs modifier
        result = generate_component(child_data, depth)

        # If we have constraints, we need to inject them
        if ref_name && constraints.any? && result.include?("modifier = Modifier")
          constraint_block = constraints.join("\n" + "    " * (depth + 2))
          constraint_modifier = ".constrainAs(#{ref_name}) {\n" + indent(constraint_block, depth + 2) + "\n" + indent("}", depth + 1)

          # Insert after "modifier = Modifier"
          result = result.sub(/modifier = Modifier/, "modifier = Modifier#{constraint_modifier}")
        end

        result
      end

      def update_generated_file(file_path, json_data, dynamic_layout_name = nil)
        existing_content = File.read(file_path)

        if existing_content.include?('// >>> GENERATED_CODE_START') &&
           existing_content.include?('// >>> GENERATED_CODE_END')

          # Use the provided dynamic layout name or extract from file path as fallback
          layout_name = dynamic_layout_name || File.basename(File.dirname(file_path))
          view_name = to_pascal_case(File.basename(layout_name))

          # Generate both static and dynamic versions
          static_content = generate_component(json_data, 1)
          dynamic_content = generate_dynamic_view_content(layout_name, json_data, 1)

          # Create content that switches based on DynamicModeManager
          composable_content = generate_mode_aware_content(layout_name, static_content, dynamic_content, 1)

          # Append responsive helper functions if any were generated
          if @responsive_functions && @responsive_functions.any?
            composable_content += "\n"
            @responsive_functions.each do |func_code|
              composable_content += "\n#{func_code}\n"
            end
          end

          updated_content = existing_content.gsub(
            /\/\/ >>> GENERATED_CODE_START.*?\/\/ >>> GENERATED_CODE_END/m,
            "// >>> GENERATED_CODE_START\n#{composable_content}    // >>> GENERATED_CODE_END"
          )

          # Update function signature to include viewModel and modifier parameters
          # Match initial template (data only)
          updated_content = updated_content.gsub(
            /fun #{view_name}GeneratedView\(\s*\n\s*data: #{view_name}Data\s*\n\s*\)/m,
            "fun #{view_name}GeneratedView(\n    data: #{view_name}Data,\n    viewModel: #{view_name}ViewModel,\n    modifier: Modifier = Modifier\n)"
          )
          # Match previously updated template (data + viewModel, no modifier)
          updated_content = updated_content.gsub(
            /fun #{view_name}GeneratedView\(\s*\n\s*data: #{view_name}Data,\s*\n\s*viewModel: #{view_name}ViewModel\s*\n\s*\)/m,
            "fun #{view_name}GeneratedView(\n    data: #{view_name}Data,\n    viewModel: #{view_name}ViewModel,\n    modifier: Modifier = Modifier\n)"
          )

          # Add ViewModel import if not present
          viewmodel_import = "import #{@package_name}.viewmodels.#{view_name}ViewModel"
          unless updated_content.include?(viewmodel_import)
            # Add after Data import
            data_import = "import #{@package_name}.data.#{view_name}Data"
            updated_content = updated_content.gsub(data_import, "#{data_import}\n#{viewmodel_import}")
          end

          updated_content = update_imports(updated_content, view_name)
          File.write(file_path, updated_content)
          Core::Logger.success "Updated: #{file_path}"
        else
          Core::Logger.warn "Generated code markers not found in #{file_path}"
        end
      end

      def update_viewmodel_file(file_path, json_data, view_name)
        existing_content = File.read(file_path)

        # Check if the file has generated code markers
        unless existing_content.include?('// >>> GENERATED_CODE_START') &&
               existing_content.include?('// >>> GENERATED_CODE_END')
          return # Skip files without markers
        end

        # Extract data properties from JSON
        data_properties = extract_data_properties(json_data)

        # Generate the updateData function content
        update_data_content = generate_update_data_function(data_properties, view_name)

        # Replace the generated section
        updated_content = existing_content.gsub(
          /\/\/ >>> GENERATED_CODE_START.*?\/\/ >>> GENERATED_CODE_END/m,
          "// >>> GENERATED_CODE_START\n#{update_data_content}    // >>> GENERATED_CODE_END"
        )

        # Add kotlinx.coroutines.flow.update import if not present
        update_import = "import kotlinx.coroutines.flow.update"
        unless updated_content.include?(update_import)
          # Add after asStateFlow import
          as_state_flow_import = "import kotlinx.coroutines.flow.asStateFlow"
          if updated_content.include?(as_state_flow_import)
            updated_content = updated_content.gsub(as_state_flow_import, "#{as_state_flow_import}\n#{update_import}")
          end
        end

        # Add Painter import if any property uses Image type
        if data_properties.any? { |prop| prop['class'] == 'Image' || prop['class'] == 'Painter' }
          painter_import = "import androidx.compose.ui.graphics.painter.Painter"
          unless updated_content.include?(painter_import)
            # Add after package line
            updated_content = updated_content.sub(/^(package .+\n)/, "\\1\n#{painter_import}\n")
          end
        end

        # Add Color import if any property uses Color type
        if data_properties.any? { |prop| prop['class'] == 'Color' }
          color_import = "import androidx.compose.ui.graphics.Color"
          unless updated_content.include?(color_import)
            # Add after package line
            updated_content = updated_content.sub(/^(package .+\n)/, "\\1\n#{color_import}\n")
          end
        end

        File.write(file_path, updated_content)
        Core::Logger.success "Updated ViewModel: #{file_path}"
      end

      def extract_data_properties(json_data, properties = [])
        if json_data.is_a?(Hash)
          # Note: includes are now expanded inline by IncludeExpander, so we should
          # not see 'include' keys here. All data definitions (including those from
          # expanded includes with ID prefixes) should be collected.

          # Check for data section at any level and collect ALL data definitions
          if json_data['data']
            if json_data['data'].is_a?(Array)
              json_data['data'].each do |data_item|
                if data_item.is_a?(Hash) && data_item['name']
                  # Platform/mode filter: skip if not matching
                  next if data_item['platform'] && data_item['platform'] != 'kotlin'
                  next if data_item['mode'] && !['compose', 'xml'].include?(data_item['mode'])
                  unless properties.any? { |p| p['name'] == data_item['name'] }
                    # Normalize platform-specific class/defaultValue
                    normalized = Core::TypeConverter.normalize_data_property(data_item, @mode)
                    properties << normalized
                  end
                end
              end
            end
          end

          # Continue searching in children (collect all data, not just the first)
          if json_data['child']
            if json_data['child'].is_a?(Array)
              json_data['child'].each do |child|
                extract_data_properties(child, properties)
              end
            else
              extract_data_properties(json_data['child'], properties)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_data_properties(item, properties)
          end
        end

        properties
      end

      def generate_update_data_function(data_properties, view_name)
        code = "    // Auto-generated updateData function - updated by 'kjui build'\n"

        # Add @Suppress("UNCHECKED_CAST") if there are callback properties
        has_callback_properties = data_properties.any? { |prop|
          class_type = prop['class'].to_s
          class_type.include?('-> Unit') || class_type.include?('-> Void')
        }
        code += "    private var _lastUpdateData: Map<String, Any>? = null\n"
        if has_callback_properties
          code += "    @Suppress(\"UNCHECKED_CAST\")\n"
        end
        code += "    fun updateData(updates: Map<String, Any>) {\n"
        code += "        if (updates == _lastUpdateData) return\n"
        code += "        _lastUpdateData = updates\n"
        code += "        _data.update { current ->\n"
        code += "            var updated = current\n"
        code += "            updates.forEach { (key, value) ->\n"
        code += "                updated = when (key) {\n"

        if data_properties.empty?
          code += "                    else -> updated\n"
        else
          data_properties.each do |prop|
            name = prop['name']
            class_type = prop['class'] || 'String'
            # Handle platform-specific class objects that weren't normalized
            class_type = Core::TypeConverter.extract_platform_value(class_type, @mode) if class_type.is_a?(Hash)
            class_type = class_type.to_s
            kotlin_cast = get_kotlin_cast(class_type, name)
            code += "                    \"#{name}\" -> updated.copy(#{name} = #{kotlin_cast})\n"
          end
          code += "                    else -> updated\n"
        end

        code += "                }\n"
        code += "            }\n"
        code += "            updated\n"
        code += "        }\n"
        code += "    }\n"
        code
      end

      def get_kotlin_cast(class_type, name)
        # Convert Swift types to Kotlin types using TypeConverter
        kotlin_type = Core::TypeConverter.to_kotlin_type(class_type, @mode)

        case class_type
        when 'String'
          "value as? String ?: updated.#{name}"
        when 'Int'
          "(value as? Number)?.toInt() ?: updated.#{name}"
        when 'Double'
          "(value as? Number)?.toDouble() ?: updated.#{name}"
        when 'Float', 'CGFloat'
          "(value as? Number)?.toFloat() ?: updated.#{name}"
        when 'Bool', 'Boolean'
          "value as? Boolean ?: updated.#{name}"
        when 'Image', 'Painter'
          "value as? Painter ?: updated.#{name}"
        when 'Color'
          "(value as? Color) ?: (value as? ULong)?.let { Color(it) } ?: updated.#{name}"
        else
          "value as? #{kotlin_type} ?: updated.#{name}"
        end
      end

      def generate_mode_aware_content(layout_name, static_content, dynamic_content, depth)
        indent_str = "    " * depth

        code = ""
        code += "#{indent_str}// Check if Dynamic Mode is active\n"
        code += "#{indent_str}if (DynamicModeManager.isActive()) {\n"
        code += "#{indent_str}    // Dynamic Mode - use SafeDynamicView for real-time updates\n"
        code += dynamic_content
        code += "#{indent_str}} else {\n"
        code += "#{indent_str}    // Static Mode - use generated code\n"
        code += "    #{static_content}"
        code += "#{indent_str}}\n"

        # Add required imports for DynamicModeManager
        @required_imports.add(:dynamic_mode_manager)
        # SafeDynamicView import is already added in generate_dynamic_view

        code
      end

      def generate_dynamic_view_content(layout_name, json_data, depth)
        indent_str = "    " * depth

        code = ""
        code += "#{indent_str}    SafeDynamicView(\n"
        code += "#{indent_str}        layoutName = \"#{layout_name}\",\n"
        code += "#{indent_str}        data = data.toMap(),\n"
        code += "#{indent_str}        fallback = {\n"
        code += "#{indent_str}            // Show error or loading state when dynamic view is not available\n"
        code += "#{indent_str}            Box(\n"
        code += "#{indent_str}                modifier = Modifier.fillMaxSize(),\n"
        code += "#{indent_str}                contentAlignment = Alignment.Center\n"
        code += "#{indent_str}            ) {\n"
        code += "#{indent_str}                Text(\n"
        code += "#{indent_str}                    text = \"Dynamic view not available\",\n"
        code += "#{indent_str}                    color = Color.Gray\n"
        code += "#{indent_str}                )\n"
        code += "#{indent_str}            }\n"
        code += "#{indent_str}        },\n"
        code += "#{indent_str}        onError = { error ->\n"
        code += "#{indent_str}            // Log error or show error UI\n"
        code += "#{indent_str}            android.util.Log.e(\"DynamicView\", \"Error loading #{layout_name}: \\$error\")\n"
        code += "#{indent_str}        },\n"
        code += "#{indent_str}        onLoading = {\n"
        code += "#{indent_str}            // Show loading indicator\n"
        code += "#{indent_str}            Box(\n"
        code += "#{indent_str}                modifier = Modifier.fillMaxSize(),\n"
        code += "#{indent_str}                contentAlignment = Alignment.Center\n"
        code += "#{indent_str}            ) {\n"
        code += "#{indent_str}                CircularProgressIndicator()\n"
        code += "#{indent_str}            }\n"
        code += "#{indent_str}        }\n"
        code += "#{indent_str}    ) { jsonContent ->\n"
        code += "#{indent_str}        // Parse and render the dynamic JSON content\n"
        code += "#{indent_str}        // This will be handled by the DynamicView implementation\n"
        code += "#{indent_str}    }\n"

        # Add required imports
        @required_imports.add(:safe_dynamic_view)
        @required_imports.add(:circular_progress_indicator)
        @required_imports.add(:box)

        code
      end

      def update_imports(content, current_view_name = nil)
        imports_map = Helpers::ImportManager.get_imports_map(@package_name)

        # Collect all required imports
        imports_to_add = []
        @required_imports.each do |import_type|
          import_lines = imports_map[import_type]
          if import_lines
            if import_lines.is_a?(Array)
              imports_to_add.concat(import_lines)
            else
              imports_to_add << import_lines
            end
          end
        end

        # Add imports for included views
        if @included_views && @included_views.any?
          # Add necessary imports for creating ViewModels
          imports_to_add << "import android.app.Application" unless imports_to_add.include?("import android.app.Application")
          imports_to_add << "import androidx.compose.ui.platform.LocalContext" unless imports_to_add.include?("import androidx.compose.ui.platform.LocalContext")

          @included_views.each do |view_name|
            pascal_name = to_pascal_case(view_name)
            view_import = "import #{@package_name}.views.#{view_name}.#{pascal_name}View"
            data_import = "import #{@package_name}.data.#{pascal_name}Data"
            viewmodel_import = "import #{@package_name}.viewmodels.#{pascal_name}ViewModel"

            imports_to_add << view_import unless imports_to_add.include?(view_import)
            imports_to_add << data_import unless imports_to_add.include?(data_import)
            imports_to_add << viewmodel_import unless imports_to_add.include?(viewmodel_import)
          end
        end

        # Add imports for custom components
        if @custom_components && @custom_components.any?
          @custom_components.each do |component_name|
            component_import = "import #{@package_name}.extensions.#{component_name}"
            imports_to_add << component_import unless imports_to_add.include?(component_import)
          end
        end

        # Add imports for cell views (from sections in Collection components)
        # Process "cell:CellName" entries from required_imports
        cell_imports = @required_imports.select { |imp| imp.to_s.start_with?('cell:') }
        if cell_imports.any?
          # Add necessary imports for creating ViewModels in collections
          imports_to_add << "import androidx.lifecycle.viewmodel.compose.viewModel" unless imports_to_add.include?("import androidx.lifecycle.viewmodel.compose.viewModel")

          cell_imports.each do |cell_import|
            # Extract cell path from "cell:CellName" (may contain subdirectory like "chat/message_cell")
            cell_path = cell_import.to_s.sub('cell:', '')

            # Handle subdirectory paths: "chat/message_cell" -> basename "message_cell", subdir from path
            if cell_path.include?('/')
              path_parts = cell_path.split('/')
              cell_basename = path_parts.last
              # The subdirectory is embedded in the cell path
              embedded_subdir = path_parts[0..-2].map { |p| to_snake_case(p) }.join('.')
            else
              cell_basename = cell_path
              embedded_subdir = nil
            end

            cell_class = to_pascal_case(cell_basename)
            snake_name = to_snake_case(cell_basename)

            # Find the cell's subdirectory by locating its JSON file
            cell_subdir = embedded_subdir || find_cell_subdirectory(snake_name)

            # Build the view import path with subdirectory if found
            if cell_subdir
              view_import = "import #{@package_name}.views.#{cell_subdir}.#{snake_name}.#{cell_class}View"
            else
              view_import = "import #{@package_name}.views.#{snake_name}.#{cell_class}View"
            end
            data_import = "import #{@package_name}.data.#{cell_class}Data"
            viewmodel_import = "import #{@package_name}.viewmodels.#{cell_class}ViewModel"

            imports_to_add << view_import unless imports_to_add.include?(view_import)
            imports_to_add << data_import unless imports_to_add.include?(data_import)
            imports_to_add << viewmodel_import unless imports_to_add.include?(viewmodel_import)
          end
        end

        # Add imports for TabView tab views
        # Process "tabview:ViewName" entries from required_imports
        tabview_imports = @required_imports.select { |imp| imp.to_s.start_with?('tabview:') }
        if tabview_imports.any?
          tabview_imports.each do |tabview_import|
            # Extract view class name from "tabview:ViewName"
            view_class = tabview_import.to_s.sub('tabview:', '')
            snake_name = to_snake_case(view_class)

            # Find the view's subdirectory by locating its JSON file
            view_subdir = find_cell_subdirectory(snake_name)

            # Build the view import path with subdirectory if found
            if view_subdir
              view_import = "import #{@package_name}.views.#{view_subdir}.#{snake_name}.#{view_class}View"
            else
              view_import = "import #{@package_name}.views.#{snake_name}.#{view_class}View"
            end

            imports_to_add << view_import unless imports_to_add.include?(view_import)
          end
        end

        # Rebuild imports section completely (remove unused imports)
        lines = content.split("\n")
        package_index = lines.find_index { |line| line.start_with?("package ") }

        if package_index
          # Find the range of import statements
          first_import_index = nil
          last_import_index = nil

          lines.each_with_index do |line, i|
            next if i <= package_index
            if line.start_with?("import ")
              first_import_index ||= i
              last_import_index = i
            elsif first_import_index && !line.strip.empty? && !line.start_with?("import ")
              # Stop when we hit non-import, non-empty line after imports started
              break
            end
          end

          if first_import_index && last_import_index
            # Build the blessed Pascal-case name set:
            #   - the current view's own Data/ViewModel
            #   - cell:* basenames pulled in via Collection cellClasses
            #   - tabview:* names pulled in via TabView
            #   - included_views (legacy include-based composition)
            # Anything else under `<pkg>.data.` / `<pkg>.viewmodels.` is treated
            # as stale (left over from earlier builds when cellClasses listed
            # different cells, or written by a now-removed code path) and
            # discarded. Without this filter every previously-emitted
            # ViewModel/Data import survives forever.
            blessed_names = Set.new
            blessed_names.add(current_view_name) if current_view_name

            cell_imports = @required_imports.select { |imp| imp.to_s.start_with?('cell:') }
            cell_imports.each do |ci|
              cell_path = ci.to_s.sub('cell:', '')
              cell_basename = cell_path.include?('/') ? cell_path.split('/').last : cell_path
              blessed_names.add(to_pascal_case(cell_basename))
            end

            tabview_imports = @required_imports.select { |imp| imp.to_s.start_with?('tabview:') }
            tabview_imports.each do |ti|
              blessed_names.add(ti.to_s.sub('tabview:', ''))
            end

            if @included_views
              @included_views.each { |v| blessed_names.add(to_pascal_case(v)) }
            end

            data_re = /\Aimport #{Regexp.escape(@package_name)}\.data\.(\w+)Data\s*\z/
            vm_re = /\Aimport #{Regexp.escape(@package_name)}\.viewmodels\.(\w+)ViewModel\s*\z/
            existing_project_imports = lines[first_import_index..last_import_index].select do |line|
              next false if line.include?('/')
              if (md = line.match(data_re))
                blessed_names.include?(md[1])
              elsif (md = line.match(vm_re))
                blessed_names.include?(md[1])
              else
                false
              end
            end

            # Build the base imports that are always needed
            base_imports = [
              "import androidx.compose.foundation.background",
              "import androidx.compose.foundation.layout.*",
              "import androidx.compose.foundation.lazy.LazyColumn",
              "import androidx.compose.foundation.lazy.LazyRow",
              "import androidx.compose.material3.*",
              "import androidx.compose.runtime.Composable",
              "import androidx.compose.ui.Alignment",
              "import androidx.compose.ui.Modifier",
              "import androidx.compose.ui.graphics.Color",
              "import androidx.compose.ui.text.font.FontWeight",
              "import androidx.compose.ui.text.style.TextAlign",
              "import androidx.compose.ui.unit.dp",
              "import androidx.compose.ui.unit.sp"
            ]

            # Combine: base imports + project imports + dynamically required imports
            all_imports = (base_imports + existing_project_imports + imports_to_add).uniq.sort

            # Replace the import section
            # Strip leading blank lines from the remaining content to avoid accumulating empty lines
            remaining_lines = lines[(last_import_index + 1)..-1]
            remaining_lines.shift while remaining_lines.first&.strip&.empty?
            new_lines = lines[0..package_index] + [""] + all_imports + [""] + remaining_lines
            content = new_lines.join("\n")
          end
        end

        content
      end

      def process_data_binding(text)
        return quote(text) unless text.is_a?(String)

        if text.match(/@\{([^}]+)\}/)
          variable = $1
          if variable.include?(' ?? ')
            var_name = variable.split(' ?? ')[0].strip
            "\"\${data.#{var_name}}\""
          else
            "\"\${data.#{variable}}\""
          end
        else
          quote(text)
        end
      end

      def quote(text)
        # Escape special characters properly
        escaped = text.gsub('\\', '\\\\\\\\')  # Escape backslashes first
                     .gsub('"', '\\"')           # Escape quotes
                     .gsub("\n", '\\n')           # Escape newlines
                     .gsub("\r", '\\r')           # Escape carriage returns
                     .gsub("\t", '\\t')           # Escape tabs
        "\"#{escaped}\""
      end

      def indent(text, level)
        return text if level == 0
        spaces = '    ' * level
        text.split("\n").map { |line|
          line.empty? ? line : spaces + line
        }.join("\n")
      end

      def to_pascal_case(str)
        str.split(/[_\-]/).map(&:capitalize).join
      end

      # Formats a plain Ruby value as a Kotlin literal suitable for use in
      # generated source code. Strings are quoted, floats get an "f" suffix,
      # nil becomes "null", and arrays/hashes are serialised as quoted strings.
      def format_value_for_kotlin(value)
        case value
        when nil
          'null'
        when true, false
          value.to_s
        when Integer
          value.to_s
        when Float
          "#{value}f"
        when String
          "\"#{value}\""
        else
          "\"#{value}\""
        end
      end

      def to_camel_case(str)
        pascal = to_pascal_case(str)
        pascal[0].downcase + pascal[1..-1]
      end

      def to_snake_case(str)
        str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
           .gsub(/([a-z\d])([A-Z])/, '\1_\2')
           .downcase
      end

      # Find the subdirectory where a cell's JSON file is located
      # Returns the subdirectory path in dot notation (e.g., "home" for home/item_card.json)
      # Returns nil if the cell is in the root Layouts directory
      def find_cell_subdirectory(cell_snake_name)
        # Search for the cell's JSON file in the layouts directory
        json_files = Dir.glob(File.join(@layouts_dir, '**', "#{cell_snake_name}.json"))

        return nil if json_files.empty?

        # Get the first match and extract its relative path
        json_file = json_files.first
        relative_path = json_file.sub(@layouts_dir + '/', '')
        dir_path = File.dirname(relative_path)

        return nil if dir_path == '.'

        # Convert directory path to dot notation and ensure snake_case
        dir_path.split('/').map { |p| to_snake_case(p) }.join('.')
      end
    end
  end
end
