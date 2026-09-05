# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative 'helpers/tint_helper'
require_relative '../core/config_manager'
require_relative '../core/project_finder'
require_relative '../core/logger'
require_relative '../core/type_converter'
require_relative '../core/layout_validator'
require_relative '../core/normalization'
require_relative '../core/layout_variant'
require_relative '../core/screen_index'
require_relative 'style_loader'
require_relative 'include_expander'
require_relative 'data_model_updater'
require_relative 'helpers/import_manager'
require_relative 'helpers/binding_expression'
require_relative 'helpers/modifier_builder'
require_relative 'helpers/resource_resolver'
require_relative 'helpers/visibility_helper'
require_relative 'helpers/responsive_helper'
require_relative 'helpers/section_extractor'
require_relative 'components/text_component'
require_relative 'components/iconlabel_component'
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
      # Version-skew guard: generated code that carries a screen marker will
      # not compile against a library without ScreenMarker, which is the
      # point — a silent "static has a marker, dynamic doesn't" split is far
      # harder to diagnose than a build error.
      #
      # 2.15.1 is a floor for CORRECTNESS, not for compilation: 2.15.0 places
      # the marker at the window origin, where the status bar covers it and
      # UiAutomator's By.res cannot find it, so every screen-transition
      # assertion on Android fails against it. Generated code compiles fine
      # either way, which is exactly why the version is named here.
      SCREEN_MARKER_MIN_LIBRARY_VERSION = '2.15.1'

      # Layouts whose build raised. The exception is caught per file so one
      # bad layout does not abandon the sweep, but a caught exception still
      # means this layout HAS NO FRESH OUTPUT — `update_generated_file` never
      # ran, so the previous generation stays on disk and looks current. The
      # caller has to be able to see that (plan 49 lane C; the section
      # extractor's own note at section_extractor.rb:625 warned about exactly
      # this, for exactly this reason).
      attr_reader :failed_files

      def initialize
        @failed_files = []
        @config = Core::ConfigManager.load_config
        @source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
        source_directory = @config['source_directory'] || 'src/main'
        @layouts_dir = File.join(@source_path, source_directory, @config['layouts_directory'] || 'assets/Layouts')
        @view_dir = File.join(@source_path, source_directory, @config['view_directory'] || 'kotlin/views')
        @package_name = @config['package_name'] || Core::ProjectFinder.get_package_name || 'com.example.app'

        FileUtils.mkdir_p(@view_dir) unless File.exist?(@view_dir)
      end

      # Screen identity: only screens carry a marker (cells and partials
      # render inside a host and would each grow a false one). Built once
      # over the WHOLE layout tree — a layout's classification depends on
      # how OTHER layouts reference it, so it cannot be decided per file.
      def screen_index
        @screen_index ||= begin
          index = JsonUIShared::ScreenIndex.build(@layouts_dir)
          index.report_lines.each { |line| Core::Logger.info line }
          index
        end
      end

      # Canonical screen id for a layout, or nil when it is not a screen.
      # The bare ID is what travels: the `__screen_` prefix is the runtime
      # layer's business (the library's ScreenMarker forms the test tag), so
      # passing an already-prefixed marker would double it.
      def screen_id_for(json_file)
        screen_id = JsonUIShared::ScreenIndex.screen_id_for_path(json_file)
        screen_index.screen?(screen_id) ? screen_id : nil
      end

      def build(options = {})
        # Get all JSON files but exclude Resources folder
        json_files = Dir.glob(File.join(@layouts_dir, '**/*.json')).reject do |file|
          file.include?('/Resources/') ||
            JsonUIShared::LayoutVariant.variant?(file)
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
        # Variant files (home@regular.json) are emitted alongside their
        # base screen — never as standalone screens.
        return nil if JsonUIShared::LayoutVariant.variant?(json_file)

        base_name = File.basename(json_file, '.json')
        snake_case_name = to_snake_case(base_name)
        pascal_case_name = to_pascal_case(base_name)
        variants = JsonUIShared::LayoutVariant.variants_for(json_file)
        variant_structs = variants.keys.each_with_object({}) do |cls, map|
          map[cls] = "#{pascal_case_name}#{cls.capitalize}VariantGeneratedView"
        end

        begin
          json_content = File.read(json_file)
          json_data = JSON.parse(json_content)

          # Skip partial files (they are included in other views, not standalone)
          if json_data['partial'] == true
            return nil
          end

          # Per-file normalization state: an L1-normalized layout (`$jui`
          # marker from `jui build`) takes the canonical-only attribute
          # lookup path in the component emitters; raw (L0) layouts keep
          # the alias fallbacks. The marker itself is build metadata, not
          # a renderable attribute — drop it before generation.
          Core::Normalization.layout_canonicalized = Core::Normalization.canonicalized?(json_data)
          json_data.delete(Core::Normalization::MARKER_KEY)

          json_data = StyleLoader.load_and_merge(json_data)

          shared_warnings = JsonUIShared::LayoutValidator.validate_layout(
            json_data, source_path: File.basename(json_file)
          )
          JsonUIShared::LayoutValidator.print_warnings(shared_warnings) unless shared_warnings.empty?

          # A declaration violation the converters cannot survive: kjui calls
          # `sections.any?` on what the declaration promises is a list, so a
          # binding string raises before anything is emitted. Refuse the
          # layout by name; recorded, not raised, so the other layouts still
          # generate and the ledger produces the non-zero exit.
          if JsonUIShared::LayoutValidator.blocking?(shared_warnings)
            reason = shared_warnings.select { |w| w[:level] == :error }
                                    .map { |w| w[:message] }.join('; ')
            begin
              require_relative '../core/stage_failures'
              JsonUI::StageFailures.record(
                'layout', "#{json_file} was not generated: #{reason}"
              )
            rescue LoadError
              nil
            end
            # `return`, not `next`: this is the body of `build_file`, a
            # method, not a block. `next` parses here and raises
            # LocalJumpError at run time.
            return
          end

          # Process includes - expand inline with ID prefix support (like SwiftJsonUI)
          json_data = IncludeExpander.process_includes(json_data, File.dirname(json_file))

          @required_imports = Set.new
          @included_views = Set.new
          @custom_components = Set.new
          @responsive_functions = []
          @responsive_counter = 0

          # Reset the per-class resolved_* local-name counters so each layout
          # generates the same bytes regardless of what was built before it in
          # the same process — regeneration must be idempotent (a rebuild over
          # an existing file has to equal a clean generation).
          Components::TextComponent.reset_counter!
          Components::TextFieldComponent.reset_counter!
          Components::TextViewComponent.reset_counter!
          Components::ButtonComponent.reset_counter!
          Components::ConstraintLayoutComponent.reset_counter!

          # Collect data definitions for ResourceResolver to check optional/non-optional
          data_properties = extract_data_properties(json_data)
          data_definitions = {}
          data_properties.each do |prop|
            data_definitions[prop['name']] = prop
          end
          Helpers::ResourceResolver.data_definitions = data_definitions

          # Find the GeneratedView file - preserve subdirectory structure from layouts
          relative_path = json_file.sub(@layouts_dir + '/', '')

          # Which strings.json sections this layout owns — string
          # resolution prefers them over a section that merely holds the
          # same text (same per-layout channel as data_definitions).
          Helpers::ResourceResolver.begin_layout(relative_path)
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
            update_generated_file(generated_view_file, json_data, dynamic_layout_name,
                                  variant_structs: variant_structs,
                                  screen_id: screen_id_for(json_file))
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

          # Emit one GeneratedView per variant file. Variants share the base
          # screen's Data/ViewModel types — the size-class dispatch in the
          # base GeneratedView selects the tree at runtime (06a-design D5).
          variants.each do |cls, variant_file|
            build_variant_file(
              variant_file, json_file, pascal_case_name, view_subdir,
              variant_structs[cls]
            )
          end

        rescue JSON::ParserError => e
          Core::Logger.error "Failed to parse #{json_file}: #{e.message}"
          @failed_files << json_file
        rescue => e
          Core::Logger.error "Failed to process #{json_file}: #{e.message}"
          @failed_files << json_file
        end
      end

      private

      def generate_component(json_data, depth = 0, parent_type = nil, is_root: false)
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
          code = generate_embed_responsive_inline(json_data, depth, parent_type)
          # The inline path returns early, BEFORE the top-level
          # wrap_with_visibility at the bottom of this method. Embed does not
          # self-wrap (it relies on that bottom wrap for the non-responsive
          # path), so without this the `visibility: "@{...}"` binding on a
          # responsive Embed is silently dropped. Wrap the whole if/else
          # chain in one VisibilityWrapper, mirroring sjui's single wrapper.
          return Helpers::VisibilityHelper.wrap_with_visibility(json_data, Helpers::TintHelper.wrap_with_tint(json_data, code, depth, @required_imports), depth, @required_imports, parent_type)
        end

        # Collection + responsive: same inline treatment as Embed. The
        # Collection body emits cell bindings like `data.<prop>.sections...`
        # and per-cell `viewModel(key = "..._${viewModel.hashCode()}")` —
        # both of these resolve against the enclosing GeneratedView's
        # `data` / `viewModel` parameters. A file-scope private helper has
        # neither in scope, so we inline the if/else at the call site.
        # Mirrors sjui's collection_converter.rb Group { if/else } shape.
        if json_data['type'] == 'Collection' && Helpers::ResponsiveHelper.responsive?(json_data)
          code = generate_collection_responsive_inline(json_data, depth, parent_type)
          # Same early-return-before-visibility-wrap bug as the Embed path
          # above. Collection does not self-wrap, so a responsive Collection
          # carrying `visibility: "@{...}"` (e.g. a grid/list display toggle)
          # would otherwise render unconditionally on Android while iOS
          # honors it. Wrap the inline if/else chain in one VisibilityWrapper.
          return Helpers::VisibilityHelper.wrap_with_visibility(json_data, Helpers::TintHelper.wrap_with_tint(json_data, code, depth, @required_imports), depth, @required_imports, parent_type)
        end

        # Check for responsive component — delegate to responsive generation
        if Helpers::ResponsiveHelper.responsive?(json_data)
          return generate_responsive_component(json_data, depth, parent_type, is_root: is_root)
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
          result = Components::ScrollViewComponent.generate(json_data, depth, @required_imports, parent_type, is_root: is_root)
          handle_container_result(result, depth, parent_type)
        when 'SafeAreaView'
          generate_safe_area_view(json_data, depth, is_root: is_root)
        when 'View'
          result = Components::ContainerComponent.generate(json_data, depth, @required_imports, parent_type, is_root: is_root)
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
        when 'IconLabel'
          Components::IconLabelComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Collection'
          Components::CollectionComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Table'
          Components::TableComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Web'
          Components::WebComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'WebView'
          Components::WebviewComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'GradientView'
          result = Components::GradientviewComponent.generate(json_data, depth, @required_imports, parent_type, is_root: is_root)
          handle_container_result(result, depth, parent_type)
        when 'Blur', 'BlurView'
          # 'Blur' is the canonical SSoT type; 'BlurView' is its alias. Only
          # the alias was dispatched, so canonical (L1-normalized) layouts
          # rendered nothing (parity family kjui-codegen-blur-missing).
          result = Components::BlurviewComponent.generate(json_data, depth, @required_imports, parent_type, is_root: is_root)
          handle_container_result(result, depth, parent_type)
        when 'TabView'
          result = Components::TabviewComponent.generate(json_data, depth, @required_imports, parent_type, is_root: is_root)
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
        # Container types already handle this in handle_container_result, so skip them.
        # `Embed` is NOT actually a container (EmbedComponent.generate returns a
        # plain String, not a Hash) so handle_container_result falls through
        # without wrapping — exclude it from the skip list so this fallback
        # path applies and `visibility: "@{...}"` on an Embed node actually
        # gates rendering.
        unless %w[View ScrollView Scroll GradientView Blur BlurView TabView].include?(component_type)
          code = Helpers::VisibilityHelper.wrap_with_visibility(json_data, Helpers::TintHelper.wrap_with_tint(json_data, code, depth, @required_imports), depth, @required_imports, parent_type) if code.is_a?(String) && !code.empty?
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
        @required_imports&.add(:local_window_info)

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

      # Collection + responsive: emit an inline if/else chain that calls
      # CollectionComponent.generate per branch with the merged attrs. No
      # private composable is extracted — the cell body resolves
      # `data.<prop>...` and the per-cell `viewModel(...)` call against the
      # enclosing GeneratedView scope. File-scope helper extraction would
      # break both. Width conditions share the embed-inline table
      # (INLINE_WIDTH_CONDITIONS / INLINE_LANDSCAPE_CONDITION) so the
      # generated condition shape is identical across Collection / Embed.
      def generate_collection_responsive_inline(json_data, depth, parent_type)
        branches = JsonUIShared::ResponsiveResolver.build_branches(json_data)
        @required_imports&.add(:local_window_info)

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
            lines << Components::CollectionComponent.generate(attrs, depth, @required_imports, parent_type)
            return lines.join("\n")
          else
            lines << indent("} else {", depth)
          end

          lines << Components::CollectionComponent.generate(attrs, depth + 1, @required_imports, parent_type)
        end

        lines << indent("}", depth)
        lines.join("\n")
      end

      # Window width in dp from LocalWindowInfo.containerSize (pixels →
      # LocalDensity conversion, truncated to Int so `in 600..839` stays an
      # Int range check). Replaces the deprecated
      # `LocalConfiguration.current.screenWidthDp`. Kept as a self-contained
      # expression (no hoisted `val`) so sibling responsive chains emitted
      # into the same block can't produce conflicting declarations.
      INLINE_WIDTH_DP_EXPR =
        'with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp().value.toInt() }'
      INLINE_WIDTH_CONDITIONS = {
        'compact' => "#{INLINE_WIDTH_DP_EXPR} < 600",
        'medium'  => "#{INLINE_WIDTH_DP_EXPR} in 600..839",
        'regular' => "#{INLINE_WIDTH_DP_EXPR} >= 840"
      }.freeze
      # Landscape = window wider than tall, from the same containerSize.
      # Replaces the deprecated `LocalConfiguration.current.orientation` read
      # (and drops the full-qualified android Configuration reference that was
      # previously needed to avoid clashing with kjui's core Configuration).
      INLINE_LANDSCAPE_CONDITION = 'LocalWindowInfo.current.containerSize.let { it.width > it.height }'

      # Build a standalone Kotlin boolean expression for a size class key,
      # using only LocalWindowInfo/LocalDensity so the call site doesn't need
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
      #
      # Emits an inline `if/else` chain at the call site instead of
      # extracting a file-scope `private fun Responsive<T><N>(...)`. Two
      # bugs make extraction structurally wrong:
      #
      # 1. Scope leak in the helper body. The extracted helper sits at file
      #    scope, so its body has no surrounding `data` / `viewModel` from
      #    the enclosing GeneratedView. Any modifier that closes over those
      #    parameters (`onClick = data.onX`, `alpha = data.x.toFloat()`,
      #    `visibility = data.flag`) emits an unresolved reference. Bug
      #    report: `kjui-view-responsive-helper-data-closure-scope-leak`.
      #
      # 2. Scope leak at the call site. The helper wrapped children in a
      #    `Box(...) { content() }` regardless of the original orientation,
      #    so a child `Modifier.weight(1f)` whose parent was a
      #    `SafeAreaView vertical → Column` got reparented to BoxScope and
      #    failed to resolve. The `weight` identifier fell back to
      #    module-level lookup and matched an unrelated `Float`, producing
      #    the confusing `Expression 'weight' of type 'Float' cannot be
      #    invoked as a function` error. Bug report:
      #    `kjui-responsive-helper-wraps-with-box-loses-row-column-scope`.
      #
      # Inlining at the call site fixes both: the branch container sits
      # directly in the caller's RowScope / ColumnScope / BoxScope, and
      # references inside the modifier chain resolve against the
      # GeneratedView's `data` / `viewModel` parameters. This mirrors the
      # existing Embed / Collection inline paths above.
      def generate_responsive_component(json_data, depth, parent_type, is_root: false)
        @responsive_counter += 1
        generate_view_responsive_inline(json_data, depth, parent_type, is_root: is_root)
      end

      # Emit an inline `if/else` chain that renders the View per branch
      # with merged attrs. No file-scope helper is registered.
      def generate_view_responsive_inline(json_data, depth, parent_type, is_root: false)
        branches = JsonUIShared::ResponsiveResolver.build_branches(json_data)
        @required_imports&.add(:local_window_info)

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
            # Only a default branch — emit the body directly with no
            # surrounding conditional.
            return generate_non_responsive_component(attrs, depth, parent_type, is_root: is_root)
          else
            lines << indent("} else {", depth)
          end

          # Each branch's body is itself a root composable for the
          # caller's `modifier` — long-press / gesture / layout modifier
          # must reach whichever branch renders. Propagate `is_root` into
          # every branch so the per-branch root container starts from
          # `modifier = modifier` (caller) rather than a fresh `Modifier`.
          lines << generate_non_responsive_component(attrs, depth + 1, parent_type, is_root: is_root)
        end

        lines << indent("}", depth)
        lines.join("\n")
      end

      # Generate a component without responsive handling (to avoid infinite recursion)
      def generate_non_responsive_component(json_data, depth, parent_type, is_root: false)
        component_type = json_data['type'] || 'View'

        code = case component_type
        when 'Text', 'Label'
          Components::TextComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Button'
          Components::ButtonComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'Image'
          Components::ImageComponent.generate(json_data, depth, @required_imports, parent_type)
        when 'View'
          result = Components::ContainerComponent.generate(json_data, depth, @required_imports, parent_type, is_root: is_root)
          handle_container_result(result, depth, parent_type)
        else
          # Fall through to normal generation for other types (responsive already stripped)
          generate_component(json_data, depth, parent_type, is_root: is_root)
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

          # Optional per-child wrapper: a container that must place EACH
          # child in its own scope (ScrollView paging wraps every child in
          # `item { }` so the snap fling has item bounds to snap to).
          # Optional per-child decorator: a container that must REWRITE each
          # generated child (ConstraintLayout injects `.constrainAs(ref)` into
          # the child's modifier chain — the child itself is produced by the
          # real dispatch above, so it keeps testTag/size/background/children).
          wrapper = result[:child_wrapper]
          decorator = result[:child_decorator]
          children.each_with_index do |child, child_index|
            child_depth = wrapper ? depth + 2 : depth + 1
            child_code = generate_component(child, child_depth, layout_type)
            next if child_code.empty?
            child_code = decorator.call(child, child_code, child_depth, child_index) if decorator

            if wrapper
              code += "\n" + ('    ' * (depth + 1)) + wrapper[:open]
              code += "\n" + child_code
              code += "\n" + ('    ' * (depth + 1)) + wrapper[:close]
            else
              code += "\n" + child_code
            end
          end

          code += result[:closing] if result[:closing]

          # Wrap with VisibilityWrapper if visibility binding is specified
          if json_data
            code = Helpers::VisibilityHelper.wrap_with_visibility(json_data, Helpers::TintHelper.wrap_with_tint(json_data, code, depth, @required_imports), depth, @required_imports, parent_type)
          end

          code
        else
          result
        end
      end

      def generate_safe_area_view(json_data, depth, is_root: false)
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
          return generate_safe_area_view_with_constraints(json_data, children, edges, depth, is_root: is_root)
        end

        # Parse orientation for child layout
        orientation = json_data['orientation']

        # `direction` reverses the children along the orientation axis — the
        # same two values container_component honours (bottomToTop on a
        # vertical stack, rightToLeft on a horizontal one; everything else is
        # the natural order). This inline helper bypasses container_component,
        # so SafeAreaView.direction was inert on this face
        # (codegen_effect SafeAreaView.direction android).
        case json_data['direction']
        when 'bottomToTop'
          children = children.reverse if orientation == 'vertical'
        when 'rightToLeft'
          children = children.reverse if orientation == 'horizontal'
        end

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

        # `spacing` is declared on SafeAreaView (51-E) and this inline helper
        # never read it, so a spaced safe-area column packed its children.
        # Same emit the container converter uses for a plain View, including
        # the bound face — `spacing` is `["number", "binding"]` and a raw
        # interpolation would put `@{v}.dp` in code position. A Box has no
        # arrangement to name, so orientation gates it exactly as it does there.
        if json_data['spacing'] && %w[Row Column].include?(container)
          @required_imports&.add(:arrangement)
          spacing_dp = Helpers::BoundValue.dp(json_data['spacing'])
          arrangement = container == 'Column' ? 'verticalArrangement' : 'horizontalArrangement'
          code += "\n" + indent("#{arrangement} = Arrangement.spacedBy(#{spacing_dp}),", depth + 1)
        end

        # Build modifiers
        # Background must come BEFORE systemBarsPadding so it extends to screen edges
        #
        # testTag + declared size first, exactly like the dynamic component
        # (DynamicSafeAreaViewComponent: applyTestTag → applySize with the
        # declared dimensions winning and fillMaxWidth only as the default).
        # This inline helper used to open with a FIXED `.fillMaxWidth()`, no
        # size builder and no tag — a declared `width: 200 / height: 200` was
        # never read, and the node was invisible to the test driver. The known
        # trap: kwargs threaded through components/ miss compose_builder.rb's
        # inline helpers (plan 49 lane C, D's measurement).
        modifiers = ["Modifier"]
        modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, @required_imports))
        size_modifiers = Helpers::ModifierBuilder.build_size(json_data, nil, @required_imports)
        size_modifiers << ".fillMaxWidth()" unless json_data['width']
        modifiers.concat(size_modifiers)
        modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, @required_imports))
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

        # `is_root` flows from generate_component when SafeAreaView is the
        # *GeneratedView's root composable. ModifierBuilder.format then
        # opens the chain from the caller's `modifier` parameter so
        # external gestures / layout modifiers wrap the safe-area /
        # background chain emitted inside.
        code += Helpers::ModifierBuilder.format(modifiers, depth, is_root: is_root)
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

      def generate_safe_area_view_with_constraints(json_data, children, edges, depth, is_root: false)
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

        # Build modifiers — same repair as generate_safe_area_view: testTag +
        # declared size first (this one opened with a fixed `.fillMaxSize()`),
        # the full-size default only when the dimension is undeclared.
        modifiers = ["Modifier"]
        modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, @required_imports))
        size_modifiers = Helpers::ModifierBuilder.build_size(json_data, nil, @required_imports)
        size_modifiers << ".fillMaxWidth()" unless json_data['width']
        size_modifiers << ".fillMaxHeight()" unless json_data['height']
        modifiers.concat(size_modifiers)
        modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, @required_imports))
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

        # See `generate_safe_area_view` — `is_root` opens the chain from
        # caller's `modifier` so SafeAreaView roots wrapping a
        # ConstraintLayout still forward external modifiers.
        code += Helpers::ModifierBuilder.format(modifiers, depth, is_root: is_root)
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

        modifiers.concat(Helpers::ModifierBuilder.build_size(child_data, nil, @required_imports))
        modifiers.concat(Helpers::ModifierBuilder.build_offset(child_data, @required_imports))

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

        modifiers.concat(Helpers::ModifierBuilder.build_size(child_data, nil, @required_imports))
        modifiers.concat(Helpers::ModifierBuilder.build_offset(child_data, @required_imports))
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

      def update_generated_file(file_path, json_data, dynamic_layout_name = nil, fun_stem: nil, types_stem: nil, variant_structs: {}, screen_id: nil)
        existing_content = File.read(file_path)

        if existing_content.include?('// >>> GENERATED_CODE_START') &&
           existing_content.include?('// >>> GENERATED_CODE_END')

          # Use the provided dynamic layout name or extract from file path
          # as fallback. Variant views pass fun_stem/types_stem explicitly:
          # their composable name (HomeRegularVariant) does not round-trip
          # from the file stem (home@regular), and their Data/ViewModel
          # types stay base-canonical (Home).
          layout_name = dynamic_layout_name || File.basename(File.dirname(file_path))
          view_name = fun_stem || to_pascal_case(File.basename(layout_name))
          types_name = types_stem || view_name

          # Generate both static and dynamic versions
          # is_root: true on the static content threads the caller's
          # `modifier` parameter into the root composable's modifier chain
          # so callers can apply gesture / layout modifiers (e.g.
          # combinedClickable for long-press) from outside the GeneratedView.
          static_content = generate_component(json_data, 1, nil, is_root: true)
          dynamic_content = generate_dynamic_view_content(layout_name, json_data, 1)

          # Lift oversized container children into file-scope @Composable
          # private fun SectionN(data, viewModel) helpers so no single
          # lambda crosses the JVM 65,536 byte / method bytecode limit.
          # Mirrors sjui's view_updater section extraction. Helpers join
          # the same RESPONSIVE_HELPERS marker block below.
          static_content, section_functions, section_waivers = Helpers::SectionExtractor.extract(
            static_content,
            view_name: view_name,
            data_type: "#{types_name}Data",
            viewmodel_type: "#{types_name}ViewModel",
            # The emitted wrapper (marker Box + Dynamic-mode if/else) adds
            # two brace levels around this body inside the main function.
            enclosing_depth: 2
          )
          @responsive_functions.concat(section_functions) if section_functions.any?
          # Waivers (functions the extractor could not bound without an
          # unsafe cut) are computed and surfaced by `jui lint-generated` —
          # NOT printed as build warnings on Android. The depth/line bound is
          # calibrated to iOS's failure mechanism (SwiftUI composes one
          # generic type and the device decodes its metadata on a 1MB
          # stack); Compose folds nothing into types, and the constraint
          # that does exist here — the dex 65,535 code-unit method limit —
          # is a HARD compile error, so a passing build already proves it.
          # Measured on the shipped waivers: worst 12.6% of the dex limit
          # and 4,369 ART instructions (huge-method line is 10,000), smaller
          # than hand-written ViewModels that warn about nothing. A warning
          # that is permanently present destroys the zero-warning gate it
          # was meant to serve (kjui-android-size-warning-uses-ios-
          # calibrated-bound, 2026-07-28). Set KJUI_SECTION_WAIVER_WARNINGS=1
          # to print them while debugging the extractor itself.
          if ENV['KJUI_SECTION_WAIVER_WARNINGS'] == '1'
            Array(section_waivers).each do |w|
              puts "warning: [section-extractor] #{view_name}: #{w.function} " \
                   "depth #{w.depth} / #{w.lines} lines exceeds the bound and has no safe cut."
            end
          end

          # Variant-file dispatch: replace the static tree with a window
          # width `when` that selects the matching variant composable.
          # Whole-tree replacement — the same data/viewModel/modifier feed
          # every branch (06a-design D4/D5).
          if variant_structs.any?
            static_content = wrap_static_with_variants(static_content, variant_structs)
            @required_imports.add(:local_window_info)
          end

          # Create content that switches based on DynamicModeManager
          composable_content = generate_mode_aware_content(layout_name, static_content, dynamic_content, 1, screen_id: screen_id)

          # Block form: a STRING replacement would interpret backslash
          # sequences (\&, \', \`, \0-\9) inside the generated Kotlin and
          # could splice stale file content into the output.
          updated_content = existing_content.gsub(
            /\/\/ >>> GENERATED_CODE_START.*?\/\/ >>> GENERATED_CODE_END/m
          ) { "// >>> GENERATED_CODE_START\n#{composable_content}    // >>> GENERATED_CODE_END" }

          # Responsive helper composables MUST sit at file scope, not inside
          # the parent GeneratedView fun. Local @Composable functions can't
          # carry the `private` modifier in Kotlin, and emitting them inside
          # the parent leaks the parent scope (data / viewModel / etc.) which
          # collides with the helper's own clean signature. We park them
          # between a separate RESPONSIVE_HELPERS marker pair appended after
          # the parent fun's closing brace; subsequent builds rewrite the
          # block atomically.
          helpers_marker_regex = /\n*\/\/ >>> RESPONSIVE_HELPERS_START.*?\/\/ >>> RESPONSIVE_HELPERS_END\n?/m
          if @responsive_functions && @responsive_functions.any?
            helpers_block = @responsive_functions.join("\n\n")
            helpers_section = "\n\n// >>> RESPONSIVE_HELPERS_START\n#{helpers_block}\n// >>> RESPONSIVE_HELPERS_END\n"
            if updated_content =~ helpers_marker_regex
              updated_content = updated_content.sub(helpers_marker_regex) { helpers_section }
            else
              updated_content = updated_content.rstrip + helpers_section
            end
          else
            # No responsive helpers this build — drop any stale block left
            # over from a previous build to keep the file deterministic.
            updated_content = updated_content.sub(helpers_marker_regex, "\n")
          end

          # Update function signature to include viewModel and modifier parameters
          # Match initial template (data only)
          updated_content = updated_content.gsub(
            /fun #{view_name}GeneratedView\(\s*\n\s*data: #{types_name}Data\s*\n\s*\)/m,
            "fun #{view_name}GeneratedView(\n    data: #{types_name}Data,\n    viewModel: #{types_name}ViewModel,\n    modifier: Modifier = Modifier\n)"
          )
          # Match previously updated template (data + viewModel, no modifier)
          updated_content = updated_content.gsub(
            /fun #{view_name}GeneratedView\(\s*\n\s*data: #{types_name}Data,\s*\n\s*viewModel: #{types_name}ViewModel\s*\n\s*\)/m,
            "fun #{view_name}GeneratedView(\n    data: #{types_name}Data,\n    viewModel: #{types_name}ViewModel,\n    modifier: Modifier = Modifier\n)"
          )

          # Add ViewModel import if not present
          viewmodel_import = "import #{@package_name}.viewmodels.#{types_name}ViewModel"
          unless updated_content.include?(viewmodel_import)
            # Add after Data import
            data_import = "import #{@package_name}.data.#{types_name}Data"
            updated_content = updated_content.gsub(data_import, "#{data_import}\n#{viewmodel_import}")
          end

          updated_content = update_imports(updated_content, view_name)
          File.write(file_path, updated_content)
          Core::Logger.success "Updated: #{file_path}"
        else
          Core::Logger.warn "Generated code markers not found in #{file_path}"
        end
      end

      # Wrap the base static tree in a window-width `when` that dispatches
      # to variant composables (regular ≥ 840dp, medium 600..839, compact
      # < 600 — same thresholds as inline `responsive`). The base tree is
      # emitted at most once: in the `else` arm when some size class still
      # resolves to it, or not at all when every class has a variant.
      def wrap_static_with_variants(static_content, variant_structs)
        call = lambda do |struct|
          "#{struct}(data = data, viewModel = viewModel, modifier = modifier)"
        end

        lines = ["    when {"]
        all_covered = %w[compact medium regular].all? { |c| variant_structs.key?(c) }

        %w[regular medium].each do |cls|
          next unless variant_structs[cls]
          lines << "        #{INLINE_WIDTH_CONDITIONS[cls]} -> #{call.call(variant_structs[cls])}"
        end

        if all_covered
          lines << "        else -> #{call.call(variant_structs['compact'])}"
        else
          if variant_structs['compact']
            lines << "        #{INLINE_WIDTH_CONDITIONS['compact']} -> #{call.call(variant_structs['compact'])}"
          end
          indented_base = static_content.split("\n").map { |l| l.empty? ? l : "        #{l}" }.join("\n")
          lines << "        else -> {"
          lines << indented_base
          lines << "        }"
        end

        lines << "    }"
        lines.join("\n") + "\n"
      end

      # Build one variant file (home@regular.json) into
      # <Base><Class>VariantGeneratedView.kt next to the base GeneratedView.
      # Data definitions come from the BASE layout — the variant contract is
      # base-canonical (`jui build` gate rule V3/V4).
      def build_variant_file(variant_file, base_json_file, base_pascal, view_subdir, variant_struct)
        json_content = File.read(variant_file)
        json_data = JSON.parse(json_content)

        Core::Normalization.layout_canonicalized = Core::Normalization.canonicalized?(json_data)
        json_data.delete(Core::Normalization::MARKER_KEY)
        json_data = StyleLoader.load_and_merge(json_data)

        shared_warnings = JsonUIShared::LayoutValidator.validate_layout(
          json_data, source_path: File.basename(variant_file)
        )
        JsonUIShared::LayoutValidator.print_warnings(shared_warnings) unless shared_warnings.empty?

        # A responsive variant is a layout too: same refusal, same ledger.
        # `return`, not `next` — this is a method body, not a block.
        if JsonUIShared::LayoutValidator.blocking?(shared_warnings)
          reason = shared_warnings.select { |w| w[:level] == :error }
                                  .map { |w| w[:message] }.join('; ')
          begin
            require_relative '../core/stage_failures'
            JsonUI::StageFailures.record(
              'layout', "#{variant_file} was not generated: #{reason}"
            )
          rescue LoadError
            nil
          end
          return
        end

        json_data = IncludeExpander.process_includes(json_data, File.dirname(variant_file))

        @required_imports = Set.new
        @included_views = Set.new
        @custom_components = Set.new
        @responsive_functions = []
        @responsive_counter = 0
        Components::TextComponent.reset_counter!
        Components::TextFieldComponent.reset_counter!
        Components::TextViewComponent.reset_counter!
        Components::ButtonComponent.reset_counter!
        Components::ConstraintLayoutComponent.reset_counter!

        # Optionality checks resolve against the BASE data section
        base_json = JSON.parse(File.read(base_json_file))
        base_json = StyleLoader.load_and_merge(base_json)
        base_json = IncludeExpander.process_includes(base_json, File.dirname(base_json_file))
        data_definitions = {}
        extract_data_properties(base_json).each do |prop|
          data_definitions[prop['name']] = prop
        end
        Helpers::ResourceResolver.data_definitions = data_definitions

        variant_view_file = File.join(@view_dir, view_subdir, "#{variant_struct}.kt")
        base_view_file = File.join(@view_dir, view_subdir, "#{base_pascal}GeneratedView.kt")
        ensure_variant_scaffold(variant_view_file, base_view_file, variant_struct, base_pascal)

        relative_path = variant_file.sub(@layouts_dir + '/', '')
        # A variant folds into the base screen's sections (see
        # namespace_candidates) — same screen, same strings.
        Helpers::ResourceResolver.begin_layout(relative_path)
        dynamic_layout_name = relative_path.sub(/\.json$/, '')
        fun_stem = variant_struct.sub(/GeneratedView\z/, '')
        update_generated_file(variant_view_file, json_data, dynamic_layout_name,
                              fun_stem: fun_stem, types_stem: base_pascal)
      rescue JSON::ParserError => e
        Core::Logger.error "Failed to parse #{variant_file}: #{e.message}"
      rescue => e
        Core::Logger.error "Failed to process #{variant_file}: #{e.message}"
      end

      # Create the variant GeneratedView file when missing. Reuses the base
      # GeneratedView's package line (same directory → same package).
      def ensure_variant_scaffold(variant_view_file, base_view_file, variant_struct, base_pascal)
        return if File.exist?(variant_view_file)

        package_line = if File.exist?(base_view_file)
                         File.read(base_view_file)[/^package .+$/] || "package #{@package_name}.views"
                       else
                         "package #{@package_name}.views"
                       end
        fun_stem = variant_struct.sub(/GeneratedView\z/, '')

        FileUtils.mkdir_p(File.dirname(variant_view_file))
        File.write(variant_view_file, <<~KOTLIN)
          #{package_line}

          import androidx.compose.runtime.Composable
          import androidx.compose.ui.Modifier
          import #{@package_name}.data.#{base_pascal}Data
          import #{@package_name}.viewmodels.#{base_pascal}ViewModel

          @Composable
          fun #{fun_stem}GeneratedView(
              data: #{base_pascal}Data,
              viewModel: #{base_pascal}ViewModel,
              modifier: Modifier = Modifier
          ) {
              // >>> GENERATED_CODE_START
              // >>> GENERATED_CODE_END
          }
        KOTLIN
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
        # Block form — see update_generated_file for the backreference rationale.
        updated_content = existing_content.gsub(
          /\/\/ >>> GENERATED_CODE_START.*?\/\/ >>> GENERATED_CODE_END/m
        ) { "// >>> GENERATED_CODE_START\n#{update_data_content}    // >>> GENERATED_CODE_END" }

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

          # Synthesized <id>IsFocused — keep in sync with
          # DataModelUpdater#extract_data_properties: the generated view emits
          # viewModel.updateData(mapOf("<id>IsFocused" to it.isFocused)) focus
          # writebacks, so updateData's when-block must carry a matching branch
          # or the key silently falls through to `else -> updated`.
          if %w[TextField EditText Input TextView].include?(json_data['type']) && json_data['id']
            focus_prop_name = to_camel_case(json_data['id']) + 'IsFocused'
            unless properties.any? { |p| p['name'] == focus_prop_name }
              properties << { 'name' => focus_prop_name, 'class' => 'Boolean', 'defaultValue' => false }
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

        # Add @Suppress("UNCHECKED_CAST") when any property needs an
        # erasure-unchecked cast: callbacks AND generic List/Map types.
        has_unchecked_cast = data_properties.any? { |prop|
          class_type = prop['class'].to_s
          class_type.include?('-> Unit') || class_type.include?('-> Void') ||
            class_type.match?(/^(List|Map)<.*>$/)
        }
        code += "    private var _lastUpdateData: Map<String, Any>? = null\n"
        if has_unchecked_cast
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
          # String tokens/hex are legal at runtime (token-string defaults are
          # the declared vocabulary); ColorManager.compose.colorOrHex resolves
          # them without a Context, so updateData stops silently dropping the
          # value the dynamic path renders.
          "(value as? Color) ?: (value as? ULong)?.let { Color(it) } ?: (value as? String)?.let { com.kotlinjsonui.generated.ColorManager.compose.colorOrHex(it) } ?: updated.#{name}"
        when 'CollectionDataSource'
          # Fully qualified like the Data-class emission (data_model_updater):
          # the generated ViewModel imports nothing from com.kotlinjsonui.data,
          # so a bare cast is an unresolved reference on a fresh generation.
          "value as? com.kotlinjsonui.data.CollectionDataSource ?: updated.#{name}"
        else
          "value as? #{kotlin_type} ?: updated.#{name}"
        end
      end

      def generate_mode_aware_content(layout_name, static_content, dynamic_content, depth, screen_id: nil)
        indent_str = "    " * depth

        # Screen marker: a sibling node placed inside a TRANSPARENT Box that
        # wraps both rendering branches.
        #
        # The Box is not decoration. Measured on API 35: a zero-size node is
        # absent from the accessibility tree, and so is a sized child placed
        # outside a zero-size parent — the marker has to occupy real space to
        # be findable. Emitted as a bare sibling it would cost 1.dp of layout
        # in the (dominant) Column-shaped callers and shift every screenshot;
        # inside a Box it overlays the content and costs nothing, because a
        # Box sizes to its largest child.
        #
        # The Box deliberately takes NO modifier: the caller's `modifier`
        # keeps flowing into the inner root exactly as before, so the content
        # this wraps is byte-identical to the unmarked output.
        # propagateMinConstraints keeps a non-filling root sized as it was.
        if screen_id
          body = generate_mode_aware_body(layout_name, static_content, dynamic_content, depth)
          inner = body.lines.map { |line| line.strip.empty? ? line : "    #{line}" }.join
          @required_imports.add(:box)
          @required_imports.add(:screen_marker)
          code = "#{indent_str}Box(propagateMinConstraints = true) {\n"
          code += inner
          code += "#{indent_str}    // Requires KotlinJsonUI >= #{SCREEN_MARKER_MIN_LIBRARY_VERSION} (screen marker)\n"
          code += "#{indent_str}    ScreenMarker(\"#{screen_id}\")\n"
          code += "#{indent_str}}\n"
          return code
        end

        generate_mode_aware_body(layout_name, static_content, dynamic_content, depth)
      end

      def generate_mode_aware_body(layout_name, static_content, dynamic_content, depth)
        indent_str = "    " * depth

        code = ""
        # Embed init-params child-side wiring: unconditionally drive any
        # pending init params from an enclosing EmbedContainer into this
        # screen's ViewModel. No-op when the screen is not embedded.
        code += "#{indent_str}// Requires KotlinJsonUI >= 2.13.0 (embed init-params)\n"
        code += "#{indent_str}DriveEmbedInitParams(viewModel)\n"
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
        # DriveEmbedInitParams lives in the main library module
        # (com.kotlinjsonui.embed) — new in KotlinJsonUI 2.13.0.
        @required_imports.add(:drive_embed_init_params)
        # SafeDynamicView import is already added in generate_dynamic_view

        code
      end

      def generate_dynamic_view_content(layout_name, json_data, depth)
        indent_str = "    " * depth

        code = ""
        code += "#{indent_str}    SafeDynamicView(\n"
        code += "#{indent_str}        layoutName = \"#{layout_name}\",\n"
        # Forward the caller's `modifier` parameter so external gestures /
        # layout modifiers reach the dynamic-mode rendering too. The
        # library `SafeDynamicView` already accepts `modifier: Modifier =
        # Modifier`; without this line, dynamic mode silently dropped
        # caller modifiers (matching the static-mode root bug).
        code += "#{indent_str}        modifier = modifier,\n"
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

        if (inner = Helpers::BindingExpression.extract_inner(text))
          # Canonical text-context emit (shared with ResourceResolver):
          # nullable access gets the authored `??` default (or `?: ""`),
          # non-null access is plain — see BindingExpression.
          Helpers::BindingExpression.interpolated_access(inner)
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

      # Case-preserving: snake/kebab-case parts get their first letter
      # upcased WITHOUT downcasing the rest, so an already-PascalCase input
      # ("BasicCell") survives instead of degrading to "Basiccell". Matches
      # CollectionComponent.to_pascal_case — the two must agree or cell
      # import and class names diverge.
      def to_pascal_case(str)
        return str if str.nil? || str.empty?

        str.split(/[_\-]/).map { |x| x.empty? ? x : x[0].upcase + x[1..].to_s }.join
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
