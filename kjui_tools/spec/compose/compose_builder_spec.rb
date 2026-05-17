# frozen_string_literal: true

require 'compose/compose_builder'

RSpec.describe KjuiTools::Compose::ComposeBuilder do
  let(:temp_dir) { Dir.mktmpdir('compose_builder_test') }
  let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }
  let(:view_dir) { File.join(temp_dir, 'src/main/kotlin/com/example/app/views') }

  let(:config) do
    {
      'source_directory' => 'src/main',
      'layouts_directory' => 'assets/Layouts',
      'view_directory' => 'kotlin/com/example/app/views',
      'package_name' => 'com.example.app',
      'project_path' => temp_dir
    }
  end

  before do
    FileUtils.mkdir_p(layouts_dir)
    FileUtils.mkdir_p(view_dir)

    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
    allow(Dir).to receive(:pwd).and_return(temp_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'sets up directories correctly' do
      builder = described_class.new
      expect(builder.instance_variable_get(:@layouts_dir)).to include('assets/Layouts')
      expect(builder.instance_variable_get(:@view_dir)).to include('kotlin/com/example/app/views')
    end

    it 'creates view directory if not exists' do
      FileUtils.rm_rf(view_dir)
      described_class.new
      expect(Dir.exist?(view_dir)).to be true
    end
  end

  describe '#build' do
    context 'when no JSON files found' do
      it 'logs warning' do
        builder = described_class.new
        expect { builder.build }.to output(/No JSON files found/).to_stdout
      end
    end

    context 'when JSON files exist in Resources folder' do
      before do
        resources_dir = File.join(layouts_dir, 'Resources')
        FileUtils.mkdir_p(resources_dir)
        File.write(File.join(resources_dir, 'strings.json'), '{}')
      end

      it 'excludes Resources folder from build' do
        builder = described_class.new
        expect { builder.build }.to output(/No JSON files found/).to_stdout
      end
    end
  end

  describe '#build_file' do
    let(:builder) { described_class.new }

    context 'with invalid JSON' do
      before do
        File.write(File.join(layouts_dir, 'invalid.json'), 'not valid json')
      end

      it 'logs error for invalid JSON' do
        expect { builder.build_file(File.join(layouts_dir, 'invalid.json')) }.to output(/Failed to parse/).to_stdout
      end
    end

    context 'when GeneratedView/ViewModel are missing on disk' do
      before do
        File.write(File.join(layouts_dir, 'test_view.json'), '{"type": "View"}')
      end

      it 'scaffolds the missing Kotlin files from the view template' do
        builder.build_file(File.join(layouts_dir, 'test_view.json'))

        view_root = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/test_view')
        expect(File.exist?(File.join(view_root, 'TestViewView.kt'))).to be true
        expect(File.exist?(File.join(view_root, 'TestViewGeneratedView.kt'))).to be true

        viewmodel_file = File.join(
          temp_dir, 'src/main/kotlin/com/example/kotlinjsonui/sample/viewmodels/TestViewViewModel.kt'
        )
        expect(File.exist?(viewmodel_file)).to be true
      end
    end

    # Regression: kjui-view-responsive-helper-data-closure-scope-leak +
    # kjui-responsive-helper-wraps-with-box-loses-row-column-scope.
    # View+responsive must inline the if/else at the call site (like Embed
    # and Collection). Extracting to a file-scope `private fun Responsive...`
    # strips both the enclosing `data` / `viewModel` closure refs and the
    # parent RowScope/ColumnScope, so any child `Modifier.weight(...)` or
    # modifier closure (`onClick = data.onX`) becomes unresolved.
    context 'when JSON has a non-Embed responsive View' do
      before do
        File.write(File.join(layouts_dir, 'responsive_view.json'), <<~JSON)
          {
            "type": "View",
            "orientation": "vertical",
            "responsive": {
              "regular": { "centerHorizontal": true, "maxWidth": 720 },
              "regular-landscape": { "maxWidth": 960 }
            },
            "child": [
              { "type": "Text", "text": "Hello" }
            ]
          }
        JSON
      end

      it 'inlines the if/else at the call site and emits no file-scope helper' do
        builder.build_file(File.join(layouts_dir, 'responsive_view.json'))
        gen_path = File.join(
          temp_dir,
          'src/main/kotlin/com/example/app/views/responsive_view/ResponsiveViewGeneratedView.kt'
        )
        content = File.read(gen_path)

        # No private fun helper, no RESPONSIVE_HELPERS marker block.
        expect(content).not_to include('// >>> RESPONSIVE_HELPERS_START')
        expect(content).not_to match(/private fun Responsive\w+\(/)

        # Inline if/else lands inside the static-mode branch.
        expect(content).to include('LocalConfiguration.current.screenWidthDp >= 840')

        # No windowSizeClass plumbing anywhere — the inline path doesn't
        # need a `windowSizeClass: WindowSizeClass` parameter.
        expect(content).not_to include('windowSizeClass: WindowSizeClass')
        expect(content).not_to include('windowSizeClass = windowSizeClass')

        # The landscape branch references the full-qualified Configuration
        # constant directly (no `import android.content.res.Configuration`).
        expect(content).not_to include("\nimport android.content.res.Configuration\n")
        expect(content).to include('android.content.res.Configuration.ORIENTATION_LANDSCAPE')

        # No leftover material3-window-size-class import either.
        expect(content).not_to include('androidx.compose.material3.windowsizeclass')
      end
    end

    # Regression: kjui-auto-extract-sections-like-sjui.
    # End-to-end check that the section extractor runs as part of the build
    # and parks helpers in the RESPONSIVE_HELPERS marker block. Large layouts
    # are required to cross the line-threshold, so we fabricate one with many
    # text children under a single root container.
    context 'when JSON has enough top-level children to cross the section threshold' do
      before do
        # Each panel is a plain `View` (Column) wrapping a single Spacer.
        # Spacer-only panels emit no `val resolved_text...` sibling — that
        # would trip the val/var-sibling guard and block section extraction.
        # 60 panels easily clear the 100-line threshold once the parent
        # Column accumulates their bodies.
        panel_count = 60
        children = Array.new(panel_count) do |i|
          {
            'type' => 'View',
            'id' => "panel_#{i}",
            'orientation' => 'vertical',
            'child' => [
              { 'type' => 'Spacer', 'height' => 8 }
            ]
          }
        end
        layout = {
          'type' => 'View',
          'orientation' => 'vertical',
          'child' => children
        }
        File.write(File.join(layouts_dir, 'big_view.json'), JSON.generate(layout))
      end

      it 'lifts oversized children into file-scope @Composable private fun Section* helpers' do
        builder.build_file(File.join(layouts_dir, 'big_view.json'))
        gen_path = File.join(
          temp_dir,
          'src/main/kotlin/com/example/app/views/big_view/BigViewGeneratedView.kt'
        )
        content = File.read(gen_path)

        # Helpers block appears with at least one Section helper.
        expect(content).to include('// >>> RESPONSIVE_HELPERS_START')
        expect(content).to include('// >>> RESPONSIVE_HELPERS_END')
        expect(content).to match(/@Composable\s+private fun Section\d+/)

        # Section helpers carry the (data, viewModel) signature so the
        # call sites in the parent body resolve. Generated views always
        # carry these signatures; we check they appear at least twice (once
        # for the GeneratedView entry-point, plus at least one Section).
        expect(content.scan(/data:\s+BigViewData/).size).to be >= 2
        expect(content.scan(/viewModel:\s+BigViewViewModel/).size).to be >= 2

        # At least one section call appears inside the body marker block.
        body_block = content[/\/\/ >>> GENERATED_CODE_START.*?\/\/ >>> GENERATED_CODE_END/m]
        expect(body_block).to match(/Section\d+\(data, viewModel\)/)
      end
    end
  end

  # Regression: kjui-embed-visibility-attribute-ignored.
  # `Embed` was in the exclusion list for the fallback VisibilityWrapper
  # path. `EmbedComponent.generate` returns a plain String (not a Hash),
  # so `handle_container_result` falls through without wrapping — and the
  # fallback wrap was being explicitly skipped for `Embed`. Result:
  # `visibility: "@{prop}"` on an Embed node was silently dropped, so
  # tablet master-detail couldn't hide the right pane on initial state.
  describe '#generate_component (Embed visibility regression)' do
    let(:builder) do
      b = described_class.new
      b.instance_variable_set(:@required_imports, Set.new)
      b.instance_variable_set(:@included_views, Set.new)
      b.instance_variable_set(:@custom_components, Set.new)
      b.instance_variable_set(:@responsive_functions, [])
      b.instance_variable_set(:@responsive_counter, 0)
      b
    end

    it 'wraps Embed with VisibilityWrapper when visibility binding is set' do
      json = {
        'type' => 'Embed',
        'id' => 'detail_pane',
        'screen' => 'product_detail',
        'visibility' => '@{detailPaneVisibility}'
      }
      result = builder.send(:generate_component, json, 0, nil)
      expect(result).to include('VisibilityWrapper(')
      expect(result).to include('visibility = data.detailPaneVisibility')
      expect(result).to include('EmbedContainer(')
    end

    it 'guards weight + visibility with `if (... != "gone")` for Row-scope Embeds' do
      # Without the guard, Compose still reserves slot space for a gone
      # weighted child, breaking the 2-pane split rebalance.
      json = {
        'type' => 'Embed',
        'id' => 'detail_pane',
        'screen' => 'product_detail',
        'weight' => 1,
        'visibility' => '@{detailPaneVisibility}'
      }
      result = builder.send(:generate_component, json, 0, 'Row')
      expect(result).to include('if (data.detailPaneVisibility.lowercase() != "gone")')
      expect(result).to include('VisibilityWrapper(')
    end

    it 'emits Embed unchanged when no visibility attribute is set (back-compat)' do
      json = {
        'type' => 'Embed',
        'id' => 'detail_pane',
        'screen' => 'product_detail'
      }
      result = builder.send(:generate_component, json, 0, nil)
      expect(result).not_to include('VisibilityWrapper')
      expect(result).to include('EmbedContainer(')
    end
  end

  describe 'private helper methods' do
    let(:builder) { described_class.new }

    describe '#to_pascal_case' do
      it 'converts snake_case to PascalCase' do
        expect(builder.send(:to_pascal_case, 'test_view_name')).to eq('TestViewName')
      end

      it 'converts kebab-case to PascalCase' do
        expect(builder.send(:to_pascal_case, 'test-view-name')).to eq('TestViewName')
      end
    end

    describe '#to_camel_case' do
      it 'converts to camelCase' do
        expect(builder.send(:to_camel_case, 'test_view')).to eq('testView')
      end
    end

    describe '#to_snake_case' do
      it 'converts PascalCase to snake_case' do
        expect(builder.send(:to_snake_case, 'TestViewName')).to eq('test_view_name')
      end
    end

    describe '#indent' do
      it 'adds correct indentation' do
        result = builder.send(:indent, 'text', 2)
        expect(result).to eq('        text')
      end

      it 'returns text unchanged for level 0' do
        result = builder.send(:indent, 'text', 0)
        expect(result).to eq('text')
      end
    end

    describe '#quote' do
      it 'escapes quotes' do
        result = builder.send(:quote, 'text with "quotes"')
        expect(result).to eq('"text with \\"quotes\\""')
      end

      it 'escapes newlines' do
        result = builder.send(:quote, "line1\nline2")
        expect(result).to eq('"line1\\nline2"')
      end

      it 'escapes tabs' do
        result = builder.send(:quote, "text\twith\ttabs")
        expect(result).to eq('"text\\twith\\ttabs"')
      end
    end

    describe '#process_data_binding' do
      it 'processes simple binding' do
        result = builder.send(:process_data_binding, '@{userName}')
        expect(result).to eq('"${data.userName}"')
      end

      it 'processes binding with null coalescing' do
        result = builder.send(:process_data_binding, '@{userName ?? "Guest"}')
        expect(result).to eq('"${data.userName}"')
      end

      it 'quotes non-binding text' do
        result = builder.send(:process_data_binding, 'plain text')
        expect(result).to eq('"plain text"')
      end
    end

    describe '#format_value_for_kotlin' do
      it 'formats string values' do
        expect(builder.send(:format_value_for_kotlin, 'test')).to eq('"test"')
      end

      it 'formats integer values' do
        expect(builder.send(:format_value_for_kotlin, 42)).to eq('42')
      end

      it 'formats float values' do
        expect(builder.send(:format_value_for_kotlin, 3.14)).to eq('3.14f')
      end

      it 'formats boolean true' do
        expect(builder.send(:format_value_for_kotlin, true)).to eq('true')
      end

      it 'formats boolean false' do
        expect(builder.send(:format_value_for_kotlin, false)).to eq('false')
      end

      it 'formats nil' do
        expect(builder.send(:format_value_for_kotlin, nil)).to eq('null')
      end

      it 'formats arrays as strings' do
        expect(builder.send(:format_value_for_kotlin, [1, 2, 3])).to eq('"[1, 2, 3]"')
      end
    end

    describe '#generate_component' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
      end

      it 'returns empty string for non-hash data' do
        expect(builder.send(:generate_component, 'not a hash')).to eq('')
        expect(builder.send(:generate_component, nil)).to eq('')
      end

      it 'generates Text component' do
        result = builder.send(:generate_component, { 'type' => 'Text', 'text' => 'Hello' })
        expect(result).to include('Text(')
      end

      it 'generates Label as Text component' do
        result = builder.send(:generate_component, { 'type' => 'Label', 'text' => 'Hello' })
        expect(result).to include('Text(')
      end

      it 'generates Button component' do
        result = builder.send(:generate_component, { 'type' => 'Button', 'text' => 'Click' })
        expect(result).to include('Button(')
      end

      it 'generates Image component' do
        result = builder.send(:generate_component, { 'type' => 'Image', 'src' => 'icon' })
        expect(result).to include('Image(')
      end

      it 'generates TextField component' do
        result = builder.send(:generate_component, { 'type' => 'TextField' })
        expect(result).not_to be_empty
      end

      it 'generates Switch component' do
        result = builder.send(:generate_component, { 'type' => 'Switch' })
        expect(result).to include('Switch')
      end

      it 'generates Toggle as Switch component' do
        result = builder.send(:generate_component, { 'type' => 'Toggle' })
        expect(result).to include('Switch')
      end

      it 'generates Slider component' do
        result = builder.send(:generate_component, { 'type' => 'Slider' })
        expect(result).to include('Slider')
      end

      it 'generates Progress component' do
        result = builder.send(:generate_component, { 'type' => 'Progress' })
        expect(result).to include('ProgressIndicator')
      end

      it 'generates SelectBox component' do
        result = builder.send(:generate_component, { 'type' => 'SelectBox' })
        expect(result).not_to be_empty
      end

      it 'generates Check/Checkbox component' do
        result = builder.send(:generate_component, { 'type' => 'Check' })
        expect(result).not_to be_empty
      end

      it 'generates Checkbox component' do
        result = builder.send(:generate_component, { 'type' => 'Checkbox' })
        expect(result).not_to be_empty
      end

      it 'generates Radio component' do
        result = builder.send(:generate_component, { 'type' => 'Radio' })
        expect(result).not_to be_empty
      end

      it 'generates Segment component' do
        result = builder.send(:generate_component, { 'type' => 'Segment' })
        expect(result).not_to be_empty
      end

      it 'generates NetworkImage component' do
        result = builder.send(:generate_component, { 'type' => 'NetworkImage', 'url' => 'https://example.com/img.png' })
        expect(result).not_to be_empty
      end

      it 'generates CircleImage component' do
        result = builder.send(:generate_component, { 'type' => 'CircleImage' })
        expect(result).not_to be_empty
      end

      it 'generates Indicator component' do
        result = builder.send(:generate_component, { 'type' => 'Indicator' })
        expect(result).not_to be_empty
      end

      it 'generates TextView component' do
        result = builder.send(:generate_component, { 'type' => 'TextView' })
        expect(result).not_to be_empty
      end

      it 'generates Collection component' do
        result = builder.send(:generate_component, { 'type' => 'Collection', 'sections' => [{ 'cell' => 'ProductCell' }] })
        expect(result).not_to be_empty
        # Cell imports are now handled via required_imports with "cell:" prefix
        expect(builder.instance_variable_get(:@required_imports)).to include('cell:ProductCell')
      end

      it 'generates Table component' do
        result = builder.send(:generate_component, { 'type' => 'Table' })
        expect(result).not_to be_empty
      end

      it 'generates Web component' do
        result = builder.send(:generate_component, { 'type' => 'Web', 'url' => 'https://example.com' })
        expect(result).not_to be_empty
      end

      it 'generates GradientView component' do
        result = builder.send(:generate_component, { 'type' => 'GradientView' })
        expect(result).not_to be_empty
      end

      it 'generates BlurView component' do
        result = builder.send(:generate_component, { 'type' => 'BlurView' })
        expect(result).not_to be_empty
      end

      it 'generates Spacer component' do
        result = builder.send(:generate_component, { 'type' => 'Spacer', 'height' => 16 })
        expect(result).to include('Spacer')
        expect(result).to include('16.dp')
      end

      it 'generates Spacer with default height' do
        result = builder.send(:generate_component, { 'type' => 'Spacer' })
        expect(result).to include('8.dp')
      end

      it 'generates TODO for unknown component' do
        result = builder.send(:generate_component, { 'type' => 'UnknownWidget' })
        expect(result).to include('TODO')
      end

      it 'generates View as container' do
        result = builder.send(:generate_component, { 'type' => 'View' })
        expect(result).not_to be_empty
      end

      it 'generates ScrollView' do
        result = builder.send(:generate_component, { 'type' => 'ScrollView' })
        expect(result).not_to be_empty
      end

      it 'generates Scroll as ScrollView' do
        result = builder.send(:generate_component, { 'type' => 'Scroll' })
        expect(result).not_to be_empty
      end
    end

    describe '#generate_safe_area_view' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
      end

      it 'generates Box with systemBarsPadding' do
        result = builder.send(:generate_safe_area_view, {}, 0)
        expect(result).to include('Box(')
        expect(result).to include('.systemBarsPadding()')
      end

      it 'generates with child components' do
        data = { 'child' => { 'type' => 'Text', 'text' => 'Hello' } }
        result = builder.send(:generate_safe_area_view, data, 0)
        expect(result).to include('Text(')
      end

      it 'handles child array' do
        data = { 'child' => [{ 'type' => 'Text', 'text' => 'Hello' }] }
        result = builder.send(:generate_safe_area_view, data, 0)
        expect(result).to include('Text(')
      end

      context 'with relative positioning in children' do
        it 'uses ConstraintLayout when child has alignBottomOfView' do
          data = {
            'child' => [
              { 'type' => 'View', 'id' => 'headerContainer', 'orientation' => 'vertical' },
              { 'type' => 'ScrollView', 'id' => 'scrollContent', 'alignBottomOfView' => 'headerContainer' }
            ]
          }
          result = builder.send(:generate_safe_area_view, data, 0)
          expect(result).to include('ConstraintLayout(')
          expect(result).to include('val headerContainer = createRef()')
          expect(result).to include('.constrainAs(')
          expect(result).to include('top.linkTo(headerContainer.bottom')
        end

        it 'uses ConstraintLayout when child has alignTopOfView' do
          data = {
            'child' => [
              { 'type' => 'View', 'id' => 'footer', 'orientation' => 'vertical' },
              { 'type' => 'View', 'alignTopOfView' => 'footer' }
            ]
          }
          result = builder.send(:generate_safe_area_view, data, 0)
          expect(result).to include('ConstraintLayout(')
        end

        it 'uses ConstraintLayout when child has alignLeftOfView' do
          data = {
            'child' => [
              { 'type' => 'View', 'id' => 'sidebar' },
              { 'type' => 'View', 'alignLeftOfView' => 'sidebar' }
            ]
          }
          result = builder.send(:generate_safe_area_view, data, 0)
          expect(result).to include('ConstraintLayout(')
        end

        it 'uses ConstraintLayout when child has alignRightOfView' do
          data = {
            'child' => [
              { 'type' => 'View', 'id' => 'sidebar' },
              { 'type' => 'View', 'alignRightOfView' => 'sidebar' }
            ]
          }
          result = builder.send(:generate_safe_area_view, data, 0)
          expect(result).to include('ConstraintLayout(')
        end

        it 'generates LazyColumn for ScrollView with constraints' do
          data = {
            'child' => [
              { 'type' => 'View', 'id' => 'header', 'orientation' => 'vertical' },
              { 'type' => 'ScrollView', 'id' => 'content', 'alignBottomOfView' => 'header', 'child' => { 'type' => 'Text', 'text' => 'Content' } }
            ]
          }
          result = builder.send(:generate_safe_area_view, data, 0)
          expect(result).to include('LazyColumn(')
          expect(result).to include('item {')
        end

        it 'does not use ConstraintLayout without relative positioning' do
          data = {
            'child' => [
              { 'type' => 'View', 'id' => 'header' },
              { 'type' => 'View', 'id' => 'content' }
            ]
          }
          result = builder.send(:generate_safe_area_view, data, 0)
          expect(result).to include('Box(')
          expect(result).not_to include('ConstraintLayout(')
        end

        it 'adds constraint_layout to required imports when using ConstraintLayout' do
          data = {
            'child' => [
              { 'type' => 'View', 'id' => 'header' },
              { 'type' => 'ScrollView', 'alignBottomOfView' => 'header' }
            ]
          }
          builder.send(:generate_safe_area_view, data, 0)
          expect(builder.instance_variable_get(:@required_imports)).to include(:constraint_layout)
        end
      end
    end

    describe '#has_relative_positioning_in_children?' do
      it 'returns true when child has alignBottomOfView' do
        children = [{ 'type' => 'View', 'alignBottomOfView' => 'other' }]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be true
      end

      it 'returns true when child has alignTopOfView' do
        children = [{ 'type' => 'View', 'alignTopOfView' => 'other' }]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be true
      end

      it 'returns true when child has alignLeftOfView' do
        children = [{ 'type' => 'View', 'alignLeftOfView' => 'other' }]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be true
      end

      it 'returns true when child has alignRightOfView' do
        children = [{ 'type' => 'View', 'alignRightOfView' => 'other' }]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be true
      end

      it 'returns true when child has alignTopView' do
        children = [{ 'type' => 'View', 'alignTopView' => 'other' }]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be true
      end

      it 'returns true when child has alignBottomView' do
        children = [{ 'type' => 'View', 'alignBottomView' => 'other' }]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be true
      end

      it 'returns true when child has alignCenterVerticalView' do
        children = [{ 'type' => 'View', 'alignCenterVerticalView' => 'other' }]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be true
      end

      it 'returns true when child has alignCenterHorizontalView' do
        children = [{ 'type' => 'View', 'alignCenterHorizontalView' => 'other' }]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be true
      end

      it 'returns false when no children have relative positioning' do
        children = [
          { 'type' => 'View', 'id' => 'header' },
          { 'type' => 'View', 'id' => 'content' }
        ]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be false
      end

      it 'returns false for empty children' do
        expect(builder.send(:has_relative_positioning_in_children?, [])).to be false
      end

      it 'returns false for non-hash children' do
        children = ['not a hash', 123, nil]
        expect(builder.send(:has_relative_positioning_in_children?, children)).to be false
      end
    end

    describe 'include handling (expanded by IncludeExpander)' do
      # Includes are now expanded inline by IncludeExpander before ComposeBuilder
      # runs, so there is no longer a generate_include method. These tests verify
      # that expectation.

      it 'does not expose a generate_include method' do
        expect(builder.private_methods).not_to include(:generate_include)
      end

      it 'raises when an unexpanded include reaches generate_component' do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
        expect {
          builder.send(:generate_component, { 'include' => 'product_cell' })
        }.to raise_error(/Include should have been expanded/)
      end
    end

    describe 'data-only child filtering (regression: kjui-embed-with-responsive-codegen-malformed issue 5)' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
      end

      it 'returns empty string for data-only entries (no type, has data)' do
        result = builder.send(:generate_component, { 'data' => [{ 'name' => 'foo' }] })
        expect(result).to eq('')
      end

      it 'returns empty string for shared_data entries (no type)' do
        result = builder.send(:generate_component, { 'shared_data' => [] })
        expect(result).to eq('')
      end

      it 'returns empty string for variables entries (no type)' do
        result = builder.send(:generate_component, { 'variables' => [] })
        expect(result).to eq('')
      end

      it 'does not emit Box for plain data spec child' do
        result = builder.send(:generate_component, { 'data' => [{ 'name' => 'captureFlow' }] })
        expect(result).not_to include('Box')
      end

      it 'still generates components when type is present' do
        result = builder.send(:generate_component, { 'type' => 'Text', 'text' => 'OK' })
        expect(result).to include('Text(')
      end
    end

    describe 'Embed responsive inline (regression: kjui-embed-with-responsive-codegen-malformed issues 1+2+4)' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
        builder.instance_variable_set(:@responsive_functions, [])
      end

      let(:embed_json) do
        {
          'type' => 'Embed',
          'id' => 'capturePane',
          'screen' => 'photo_registration',
          'width' => 420,
          'responsive' => {
            'regular' => { 'width' => 360 },
            'regular-landscape' => { 'width' => 420 }
          }
        }
      end

      it 'emits inline if/else (not a private composable)' do
        result = builder.send(:generate_component, embed_json, 0, nil)
        expect(result).to include('if (')
        expect(result).not_to include('private fun Responsive')
      end

      it 'uses standalone LocalConfiguration condition (regression: jui-embed-responsive-block-codegen-broken)' do
        # The inline path runs in the GeneratedView body where `windowSizeClass`
        # is not declared. We must use LocalConfiguration directly instead.
        result = builder.send(:generate_component, embed_json, 0, nil)
        expect(result).to include('LocalConfiguration.current.screenWidthDp >= 840')
        expect(result).not_to include('windowSizeClass.widthSizeClass')
        expect(result).not_to include('WindowWidthSizeClass.Expanded')
      end

      it 'does not pull in the window_size_class import for the inline path' do
        builder.send(:generate_component, embed_json, 0, nil)
        imports = builder.instance_variable_get(:@required_imports)
        expect(imports).not_to include(:window_size_class)
        expect(imports).to include(:local_configuration)
      end

      it 'does not register a responsive helper function' do
        builder.send(:generate_component, embed_json, 0, nil)
        responsive_funcs = builder.instance_variable_get(:@responsive_functions)
        expect(responsive_funcs).to be_empty
      end

      it 'inlines an EmbedContainer per branch' do
        result = builder.send(:generate_component, embed_json, 0, nil)
        expect(result.scan('EmbedContainer(').length).to be >= 2
      end
    end

    # Regression: kjui-collection-responsive-helper-data-viewmodel-scope-leak
    # Collection bodies reference enclosing `data.<prop>` for the cell data
    # source and a per-cell `viewModel(key = "..._${viewModel.hashCode()}")`
    # invocation. Hoisting the body into a file-scope private composable
    # leaves both unresolved. Collection + responsive must inline like Embed.
    describe 'Collection responsive inline (regression: kjui-collection-responsive-helper-data-viewmodel-scope-leak)' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
        builder.instance_variable_set(:@responsive_functions, [])
        builder.instance_variable_set(:@responsive_counter, 0)
      end

      let(:collection_json) do
        {
          'type' => 'Collection',
          'id' => 'items_grid',
          'width' => 'matchParent',
          'height' => 'matchParent',
          'columns' => 2,
          'responsive' => {
            'regular' => { 'columns' => 5 }
          },
          'sections' => [
            {
              'cellsBinding' => '@{gridItems.sections[0].cells}',
              'cell' => 'shop_item_list_item'
            }
          ]
        }
      end

      it 'emits inline if/else for the Collection (not a private composable)' do
        result = builder.send(:generate_component, collection_json, 0, nil)
        expect(result).to include('if (LocalConfiguration.current.screenWidthDp >= 840)')
        # No file-scope helper registered for the Collection.
        funcs = builder.instance_variable_get(:@responsive_functions)
        expect(funcs).to be_empty
        # No `ResponsiveCollection<N>()` call either.
        expect(result).not_to match(/ResponsiveCollection\d+\(\)/)
      end

      it 'pulls in local_configuration but not window_size_class' do
        builder.send(:generate_component, collection_json, 0, nil)
        imports = builder.instance_variable_get(:@required_imports)
        expect(imports).to include(:local_configuration)
        expect(imports).not_to include(:window_size_class)
      end

      it 'emits both branches with their respective column counts' do
        result = builder.send(:generate_component, collection_json, 0, nil)
        # regular branch: 5 columns
        expect(result).to match(/GridCells\.Fixed\(5\)/)
        # default branch: 2 columns
        expect(result).to match(/GridCells\.Fixed\(2\)/)
      end
    end

    # Regression: kjui-view-responsive-helper-data-closure-scope-leak +
    # kjui-responsive-helper-wraps-with-box-loses-row-column-scope.
    # The extracted-private-composable path leaked the enclosing
    # GeneratedView scope: modifier closures referencing `data.<prop>` and
    # child `Modifier.weight(...)` calls both broke. The fix is to inline
    # the if/else chain at the call site (same shape as Embed / Collection).
    describe 'View responsive inline (regression: kjui-view-responsive-helper-data-closure-scope-leak + kjui-responsive-helper-wraps-with-box-loses-row-column-scope)' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
        builder.instance_variable_set(:@responsive_functions, [])
        builder.instance_variable_set(:@responsive_counter, 0)
      end

      let(:view_json) do
        {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'centerHorizontal' => true, 'maxWidth' => 720 }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'Hello' }]
        }
      end

      it 'emits inline if/else (not a private composable)' do
        call_code = builder.send(:generate_component, view_json, 0, nil)
        expect(call_code).to include('if (LocalConfiguration.current.screenWidthDp >= 840)')
        expect(call_code).not_to match(/Responsive\w+\s*\{/)
        expect(call_code).not_to include('windowSizeClass = windowSizeClass')
      end

      it 'does not register a file-scope helper function' do
        builder.send(:generate_component, view_json, 0, nil)
        funcs = builder.instance_variable_get(:@responsive_functions)
        expect(funcs).to be_empty
      end

      it 'uses LocalConfiguration.current.screenWidthDp not WindowWidthSizeClass' do
        call_code = builder.send(:generate_component, view_json, 0, nil)
        expect(call_code).to include('LocalConfiguration.current.screenWidthDp')
        expect(call_code).not_to include('WindowWidthSizeClass')
      end

      it 'pulls in local_configuration but not window_size_class' do
        builder.send(:generate_component, view_json, 0, nil)
        imports = builder.instance_variable_get(:@required_imports)
        expect(imports).not_to include(:window_size_class)
        expect(imports).to include(:local_configuration)
      end

      it 'fully qualifies android.content.res.Configuration when a landscape branch is present' do
        # Regression: bare `Configuration.ORIENTATION_LANDSCAPE` would clash
        # with kjui's `com.kotlinjsonui.core.Configuration` whenever a
        # component on the same screen also needs the kjui Configuration
        # class (e.g. Button / TextField / font helper).
        landscape_json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'maxWidth' => 720 },
            'regular-landscape' => { 'maxWidth' => 960 }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'Hello' }]
        }
        call_code = builder.send(:generate_component, landscape_json, 0, nil)
        expect(call_code).to include('android.content.res.Configuration.ORIENTATION_LANDSCAPE')
      end

      it 'preserves the caller parent scope so child Modifier.weight resolves' do
        # The original bug: the extracted helper wrapped children in a Box,
        # so a child weight(1f) lost its ColumnScope receiver. Inline
        # rendering puts the branch container directly in the caller's
        # ColumnScope, preserving weight resolution.
        weight_json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'maxWidth' => 640, 'centerHorizontal' => true }
          },
          'child' => [
            { 'type' => 'View', 'orientation' => 'horizontal', 'weight' => 1,
              'child' => [{ 'type' => 'Text', 'text' => 'A' }] }
          ]
        }
        call_code = builder.send(:generate_component, weight_json, 0, 'Column')
        # Each branch emits a Column (the responsive View itself is
        # vertical) and the child renders inside that Column scope so its
        # own modifiers see ColumnScope. No `private fun` wrapper.
        expect(call_code).to include('Column(')
        expect(call_code).not_to match(/private fun Responsive/)
      end

      it 'modifier closures keep their data/viewModel references at the call site' do
        # The original bug: extracting the helper to file scope dropped
        # `data` / `viewModel` from the body's scope, so onClick / alpha
        # bindings emitted unresolved references. Inline preserves them.
        closure_json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'onclick' => '@{onProductCardTap}',
          'responsive' => {
            'regular' => { 'maxWidth' => 480, 'centerHorizontal' => true }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'Card' }]
        }
        call_code = builder.send(:generate_component, closure_json, 0, 'Column')
        # The `data.onProductCardTap?.invoke()` (or similar) lives directly
        # inside the inline if/else, where `data` is the GeneratedView's
        # parameter and resolves correctly.
        expect(call_code).to include('data.onProductCardTap')
        # No helper extraction.
        funcs = builder.instance_variable_get(:@responsive_functions)
        expect(funcs).to be_empty
      end
    end

    # Regression: sjui-kjui-responsive-non-frame-attrs-dropped
    # The bug reporter flagged this as iOS-confirmed and Android-suspect
    # ("kjui は理論上は non-frame attrs を branch ごとに適用できるはず").
    # kjui IS correct here because each branch re-runs
    # Components::ContainerComponent.generate(attrs, ...) with the
    # base-merged-with-override attrs, and ContainerComponent already
    # delegates margin / padding / background / etc. to ModifierBuilder.
    # These tests lock in that behavior.
    describe 'View responsive non-frame attrs reach the branch (regression: sjui-kjui-responsive-non-frame-attrs-dropped)' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
        builder.instance_variable_set(:@responsive_functions, [])
        builder.instance_variable_set(:@responsive_counter, 0)
      end

      it 'override-only topMargin emits .padding(top = 80.dp) in the regular branch' do
        json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'topMargin' => 80 }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'Hi' }]
        }
        result = builder.send(:generate_component, json, 0, nil)
        expect(result).to include('80.dp')
        # The regular branch is the only one with the override; default
        # branch should NOT carry the 80 padding.
        expect(result.scan(/80\.dp/).length).to eq(1)
      end

      it 'base + override leftPadding emits 32 in regular branch and 16 in default' do
        json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'leftPadding' => 16,
          'responsive' => {
            'regular' => { 'leftPadding' => 32 }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'Hi' }]
        }
        result = builder.send(:generate_component, json, 0, nil)
        # Regular and default branches each emit their respective values.
        expect(result).to include('32.dp')
        expect(result).to include('16.dp')
      end
    end

    # Regression lock-in: sjui-kjui-responsive-honor-weight-and-width.
    # kjui inline path already merges `weight` / `width` / `height` from
    # the responsive branch into `attrs` and re-runs
    # ContainerComponent.generate with the merged set. build_size and
    # build_weight then emit the right modifiers per branch. The bug
    # filer's expectation ("scope outside") was incorrect for Android —
    # only iOS sjui has structural limitations (WeightedHStack refactor
    # needed). These tests prove Android honors the override and stop
    # future regressions.
    describe 'View responsive width/height/weight reach the branch (regression: sjui-kjui-responsive-honor-weight-and-width)' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
        builder.instance_variable_set(:@responsive_functions, [])
        builder.instance_variable_set(:@responsive_counter, 0)
      end

      it 'override-only weight emits .weight(1f) inside the regular branch when parent is Row' do
        json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'width' => 'matchParent',
          'responsive' => {
            'regular' => { 'width' => 0, 'weight' => 1 }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'A' }]
        }
        result = builder.send(:generate_component, json, 0, 'Row')
        # Regular branch carries `.weight(1f)`; default branch keeps
        # `.fillMaxWidth()` from base `width: matchParent`.
        expect(result).to include('.weight(1f)')
        expect(result).to include('.fillMaxWidth()')
        # The regular branch's `width: 0` is suppressed (build_size skips
        # numeric width when weight is set with width == 0). So no
        # `.width(0.dp)` should appear.
        expect(result).not_to include('.width(0.dp)')
      end

      it 'orientation switch with per-branch weight on children compiles to Row/Column with correct emit' do
        # Full repro of the bug report's unify use case: vertical
        # (compact) ↔ horizontal (regular) outer + child weights only
        # active in regular.
        json = {
          'type' => 'View',
          'id' => 'mypage_root',
          'width' => 'matchParent',
          'height' => 'matchParent',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'orientation' => 'horizontal' }
          },
          'child' => [
            {
              'type' => 'View',
              'id' => 'left_panel',
              'orientation' => 'vertical',
              'width' => 'matchParent',
              'responsive' => {
                'regular' => { 'width' => 0, 'weight' => 1 }
              },
              'child' => [{ 'type' => 'Text', 'text' => 'L' }]
            },
            {
              'type' => 'View',
              'id' => 'right_panel',
              'orientation' => 'vertical',
              'width' => 'matchParent',
              'responsive' => {
                'regular' => { 'width' => 0, 'weight' => 1 }
              },
              'child' => [{ 'type' => 'Text', 'text' => 'R' }]
            }
          ]
        }
        result = builder.send(:generate_component, json, 0, nil)
        # Outer responsive: Row in regular branch, Column in default.
        expect(result).to include('Row(')
        expect(result).to include('Column(')
        # Each child has an inline responsive — its regular branch
        # carries `.weight(1f)`, default branch keeps `.fillMaxWidth()`.
        expect(result.scan('.weight(1f)').length).to be >= 2
      end

      it 'override-only height: matchParent emits .fillMaxHeight() in the regular branch' do
        json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'height' => 'wrapContent',
          'responsive' => {
            'regular' => { 'height' => 'matchParent' }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'A' }]
        }
        result = builder.send(:generate_component, json, 0, nil)
        expect(result).to include('.fillMaxHeight()')
      end

      it 'override-only width: 240 emits .width(240.dp) in the regular branch' do
        json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'width' => 'matchParent',
          'responsive' => {
            'regular' => { 'width' => 240 }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'A' }]
        }
        result = builder.send(:generate_component, json, 0, nil)
        expect(result).to include('.width(240.dp)')
        expect(result).to include('.fillMaxWidth()') # default branch
      end

      it 'override-only gravity reaches the Column branch and emits horizontalAlignment' do
        json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'gravity' => 'centerHorizontal' }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'A' }]
        }
        result = builder.send(:generate_component, json, 0, nil)
        # gravity → Column's `horizontalAlignment` parameter.
        expect(result).to include('horizontalAlignment = Alignment.CenterHorizontally')
      end
    end

    # Regression: kjui-responsive-helper-align-scope-leak (now obsolete
    # under the inline path, but the tests stay as a lock — alignment for
    # a responsive View must reach the call site in a form that resolves
    # against the caller's actual scope receiver). Because inline emits
    # the branch container *inside* the caller's RowScope / ColumnScope /
    # BoxScope, `Modifier.align(...)` is valid again — no need for the
    # ScopeFree `wrapContentWidth/Height` workaround.
    describe 'responsive inline emits scope-correct alignment (regression: kjui-responsive-helper-align-scope-leak)' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
        builder.instance_variable_set(:@responsive_functions, [])
        builder.instance_variable_set(:@responsive_counter, 0)
      end

      it 'centerHorizontal in responsive override emits .align inside ColumnScope' do
        json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'maxWidth' => 720, 'centerHorizontal' => true }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'Hello' }]
        }
        result = builder.send(:generate_component, json, 0, 'Column')
        # Inside ColumnScope, `.align(Alignment.CenterHorizontally)` is a
        # valid scope-bound extension — no need for `wrapContentWidth`.
        expect(result).to include('.align(Alignment.CenterHorizontally)')
        # No file-scope helper emitted.
        expect(builder.instance_variable_get(:@responsive_functions)).to be_empty
      end

      it 'centerVertical in responsive override emits .align inside RowScope' do
        json = {
          'type' => 'View',
          'orientation' => 'horizontal',
          'responsive' => {
            'regular' => { 'maxHeight' => 480, 'centerVertical' => true }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'Hi' }]
        }
        result = builder.send(:generate_component, json, 0, 'Row')
        expect(result).to include('.align(Alignment.CenterVertically)')
        expect(builder.instance_variable_get(:@responsive_functions)).to be_empty
      end

      it 'centerInParent in responsive override emits .align(Alignment.Center) inside BoxScope' do
        json = {
          'type' => 'View',
          'orientation' => 'vertical',
          'responsive' => {
            'regular' => { 'centerInParent' => true }
          },
          'child' => [{ 'type' => 'Text', 'text' => 'Hi' }]
        }
        result = builder.send(:generate_component, json, 0, 'Box')
        # BoxScope honours `Modifier.align(Alignment.Center)` for full
        # centering, which is what build_alignment emits when centerInParent
        # is set without conflicting alignment hints.
        expect(result).to include('.align(Alignment.Center)')
        expect(builder.instance_variable_get(:@responsive_functions)).to be_empty
      end
    end

    # Regression: kjui-responsive-inline-align-not-available-in-lazyitemscope
    # ScrollView emits `LazyColumn { item { ... } }` and its children render
    # inside the `item` lambda whose receiver is `LazyItemScope`. With the
    # earlier inline-responsive fix, a responsive View child was inheriting
    # the OUTER parent_type (e.g. 'Column' when SafeAreaView vertical wraps
    # the ScrollView), and `Modifier.align(Alignment.CenterHorizontally)` was
    # emitted inside the item lambda — unresolved against LazyItemScope.
    #
    # ScrollViewComponent now returns `layout_type: 'ScopeFree'`, so
    # handle_container_result passes ScopeFree to children. That routes
    # alignment through `wrapContentWidth/Height(...)`, which resolves in
    # any scope including LazyItemScope.
    describe 'responsive View inside ScrollView (regression: kjui-responsive-inline-align-not-available-in-lazyitemscope)' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
        builder.instance_variable_set(:@responsive_functions, [])
        builder.instance_variable_set(:@responsive_counter, 0)
      end

      it 'routes the inline branch through ScopeFree even when the outer wrapper is Column' do
        json = {
          'type' => 'ScrollView',
          'child' => [{
            'type' => 'View',
            'orientation' => 'vertical',
            'responsive' => {
              'regular' => { 'maxWidth' => 960, 'centerHorizontal' => true }
            },
            'child' => [{ 'type' => 'Text', 'text' => 'Hi' }]
          }]
        }
        # parent_type='Column' mimics a vertical SafeAreaView wrapping the
        # ScrollView at screen root. The responsive child must NOT emit
        # `Modifier.align(Alignment.CenterHorizontally)` because the actual
        # receiver scope at the call site is LazyItemScope.
        result = builder.send(:generate_component, json, 0, 'Column')
        expect(result).to include('item {')
        expect(result).not_to include('.align(Alignment.CenterHorizontally)')
        # Scope-independent centering is still emitted.
        expect(result).to include('.wrapContentWidth(Alignment.CenterHorizontally)')
      end
    end

    # Regression: same bug — verify build_alignment 'ScopeFree' branch.
    describe 'ModifierBuilder.build_alignment(parent_type: ScopeFree)' do
      it 'returns wrapContentWidth for centerHorizontal in ScopeFree' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'centerHorizontal' => true }, nil, 'ScopeFree'
        )
        expect(mods).to eq(['.wrapContentWidth(Alignment.CenterHorizontally)'])
      end

      it 'returns wrapContentHeight for centerVertical in ScopeFree' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'centerVertical' => true }, nil, 'ScopeFree'
        )
        expect(mods).to eq(['.wrapContentHeight(Alignment.CenterVertically)'])
      end

      it 'returns both for centerInParent in ScopeFree' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'centerInParent' => true }, nil, 'ScopeFree'
        )
        expect(mods).to include('.wrapContentWidth(Alignment.CenterHorizontally)')
        expect(mods).to include('.wrapContentHeight(Alignment.CenterVertically)')
      end

      # Regression: sjui-kjui-responsive-align-left-right-not-honored.
      # alignLeft / alignRight / alignTop / alignBottom now map to scope-
      # independent `wrapContentWidth/Height(Alignment.Start/End/Top/Bottom)`
      # in ScopeFree contexts (responsive emit inside a LazyItemScope, etc.).
      it 'returns wrapContentWidth(Alignment.Start) for alignLeft in ScopeFree' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'alignLeft' => true }, nil, 'ScopeFree'
        )
        expect(mods).to eq(['.wrapContentWidth(Alignment.Start)'])
      end

      it 'returns wrapContentWidth(Alignment.End) for alignRight in ScopeFree' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'alignRight' => true }, nil, 'ScopeFree'
        )
        expect(mods).to eq(['.wrapContentWidth(Alignment.End)'])
      end

      it 'returns wrapContentHeight(Alignment.Top) for alignTop in ScopeFree' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'alignTop' => true }, nil, 'ScopeFree'
        )
        expect(mods).to eq(['.wrapContentHeight(Alignment.Top)'])
      end

      it 'returns wrapContentHeight(Alignment.Bottom) for alignBottom in ScopeFree' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'alignBottom' => true }, nil, 'ScopeFree'
        )
        expect(mods).to eq(['.wrapContentHeight(Alignment.Bottom)'])
      end

      it 'combines alignBottom + alignRight into two scope-free modifiers' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'alignBottom' => true, 'alignRight' => true }, nil, 'ScopeFree'
        )
        expect(mods).to include('.wrapContentWidth(Alignment.End)')
        expect(mods).to include('.wrapContentHeight(Alignment.Bottom)')
      end

      it 'collapses alignLeft + alignRight to CenterHorizontally in ScopeFree' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'alignLeft' => true, 'alignRight' => true }, nil, 'ScopeFree'
        )
        expect(mods).to eq(['.wrapContentWidth(Alignment.CenterHorizontally)'])
      end

      it 'centerHorizontal beats alignLeft in ScopeFree' do
        mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_alignment(
          { 'centerHorizontal' => true, 'alignLeft' => true }, nil, 'ScopeFree'
        )
        expect(mods).to eq(['.wrapContentWidth(Alignment.CenterHorizontally)'])
      end
    end

    describe '#handle_container_result' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new)
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
      end

      it 'returns string result as-is' do
        expect(builder.send(:handle_container_result, 'simple', 0)).to eq('simple')
      end

      it 'processes hash result with code and children' do
        result = builder.send(:handle_container_result, {
          code: 'Box(',
          children: [{ 'type' => 'Text', 'text' => 'Hello' }],
          closing: ')'
        }, 0)
        expect(result).to include('Box(')
        expect(result).to include(')')
      end
    end

    describe '#update_imports' do
      before do
        builder.instance_variable_set(:@required_imports, Set.new([:text]))
        builder.instance_variable_set(:@included_views, Set.new)
        builder.instance_variable_set(:@cell_views, Set.new)
        builder.instance_variable_set(:@custom_components, Set.new)
      end

      it 'adds imports to content' do
        content = "package com.example.app\n\nimport android.app.Activity\n\nclass Test {}"
        result = builder.send(:update_imports, content)
        expect(result).to include('import')
      end

      it 'preserves the current view\'s own Data/ViewModel imports' do
        content = <<~KT
          package com.example.app

          import android.app.Activity
          import com.example.app.data.ChatData
          import com.example.app.viewmodels.ChatViewModel

          class Test {}
        KT
        result = builder.send(:update_imports, content, 'Chat')
        expect(result).to include('import com.example.app.data.ChatData')
        expect(result).to include('import com.example.app.viewmodels.ChatViewModel')
      end

      it 'drops stale Data/ViewModel imports for unused names' do
        content = <<~KT
          package com.example.app

          import android.app.Activity
          import com.example.app.data.ChatData
          import com.example.app.viewmodels.ChatViewModel
          import com.example.app.data.AssistantMessageBubbleData
          import com.example.app.viewmodels.AssistantMessageBubbleViewModel

          class Test {}
        KT
        result = builder.send(:update_imports, content, 'Chat')
        expect(result).not_to include('AssistantMessageBubble')
        expect(result).to include('import com.example.app.data.ChatData')
      end

      it 'preserves Data/ViewModel imports for cell:* entries' do
        builder.instance_variable_set(
          :@required_imports,
          Set.new(['cell:chat/message_cell'])
        )
        content = <<~KT
          package com.example.app

          import com.example.app.data.ChatData
          import com.example.app.viewmodels.ChatViewModel
          import com.example.app.data.MessageCellData
          import com.example.app.viewmodels.MessageCellViewModel

          class Test {}
        KT
        result = builder.send(:update_imports, content, 'Chat')
        expect(result).to include('import com.example.app.data.MessageCellData')
        expect(result).to include('import com.example.app.viewmodels.MessageCellViewModel')
      end
    end
  end
end
