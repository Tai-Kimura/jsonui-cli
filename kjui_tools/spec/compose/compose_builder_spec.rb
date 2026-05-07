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
