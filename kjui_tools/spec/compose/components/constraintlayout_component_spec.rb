# frozen_string_literal: true

require 'compose/components/constraintlayout_component'
require 'compose/components/container_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::ConstraintLayoutComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  describe '.generate' do
    it 'adds constraint_layout to imports' do
      json_data = { 'type' => 'ConstraintLayout' }
      described_class.generate(json_data, 0, required_imports)
      expect(required_imports).to include(:constraint_layout)
    end

    it 'falls back to container for children without constraints' do
      json_data = {
        'type' => 'ConstraintLayout',
        'child' => [{ 'type' => 'Text', 'text' => 'Hello' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      # Should fall back to ContainerComponent
      expect(result).not_to be_empty
    end

    it 'generates ConstraintLayout when children have constraints' do
      json_data = {
        'type' => 'ConstraintLayout',
        'child' => [{
          'type' => 'Text',
          'text' => 'Hello',
          'alignTop' => true,
          'alignLeft' => true
        }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ConstraintLayout(')
      expect(result).to include('createRef()')
    end

    it 'handles single child as hash' do
      json_data = {
        'type' => 'ConstraintLayout',
        'child' => {
          'type' => 'Text',
          'text' => 'Single',
          'centerInParent' => true
        }
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('ConstraintLayout(')
    end

    it 'uses id for constraint reference' do
      json_data = {
        'type' => 'ConstraintLayout',
        'child' => [{
          'id' => 'myButton',
          'type' => 'Button',
          'text' => 'Click',
          'alignTop' => true
        }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('myButton')
      expect(result).to include('createRef()')
    end

    it 'generates constraint reference without id' do
      json_data = {
        'type' => 'ConstraintLayout',
        'child' => [{
          'type' => 'Text',
          'text' => 'Test',
          'alignTop' => true
        }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('view_0')
    end
  end

  describe '.has_relative_positioning?' do
    it 'returns true for alignTop' do
      expect(described_class.send(:has_relative_positioning?, { 'alignTop' => true })).to be true
    end

    it 'returns true for alignBottom' do
      expect(described_class.send(:has_relative_positioning?, { 'alignBottom' => true })).to be true
    end

    it 'returns true for alignLeft' do
      expect(described_class.send(:has_relative_positioning?, { 'alignLeft' => true })).to be true
    end

    it 'returns true for alignRight' do
      expect(described_class.send(:has_relative_positioning?, { 'alignRight' => true })).to be true
    end

    it 'returns true for centerHorizontal' do
      expect(described_class.send(:has_relative_positioning?, { 'centerHorizontal' => true })).to be true
    end

    it 'returns true for centerVertical' do
      expect(described_class.send(:has_relative_positioning?, { 'centerVertical' => true })).to be true
    end

    it 'returns true for centerInParent' do
      expect(described_class.send(:has_relative_positioning?, { 'centerInParent' => true })).to be true
    end

    it 'returns true for alignTopOfView' do
      expect(described_class.send(:has_relative_positioning?, { 'alignTopOfView' => 'other' })).to be true
    end

    it 'returns false for non-hash' do
      expect(described_class.send(:has_relative_positioning?, 'not a hash')).to be false
      expect(described_class.send(:has_relative_positioning?, nil)).to be false
    end

    it 'returns false for hash without positioning attrs' do
      expect(described_class.send(:has_relative_positioning?, { 'text' => 'Hello' })).to be false
    end
  end

  describe '.has_positioning_constraints?' do
    it 'returns true for alignTopOfView' do
      expect(described_class.send(:has_positioning_constraints?, { 'alignTopOfView' => 'other' })).to be true
    end

    it 'returns true for alignTop' do
      expect(described_class.send(:has_positioning_constraints?, { 'alignTop' => true })).to be true
    end

    it 'returns false for centerInParent' do
      expect(described_class.send(:has_positioning_constraints?, { 'centerInParent' => true })).to be false
    end

    it 'returns false for non-hash' do
      expect(described_class.send(:has_positioning_constraints?, nil)).to be false
    end
  end

  describe '.should_apply_margins_as_padding?' do
    it 'returns true when no positioning constraints' do
      expect(described_class.send(:should_apply_margins_as_padding?, { 'text' => 'Hello' })).to be true
    end

    it 'returns false when has positioning constraints' do
      expect(described_class.send(:should_apply_margins_as_padding?, { 'alignTop' => true })).to be false
    end

    it 'returns false for non-hash' do
      expect(described_class.send(:should_apply_margins_as_padding?, nil)).to be false
    end
  end

  describe '.generate_text_component' do
    it 'generates basic Text' do
      result = described_class.send(:generate_text_component, { 'text' => 'Hello' }, 0, required_imports)
      expect(result).to include('Text(')
      expect(result).to include('"Hello"')
    end

    it 'generates Text with data binding' do
      result = described_class.send(:generate_text_component, { 'text' => '@{userName}' }, 0, required_imports)
      expect(result).to include('${data.userName}')
    end

    it 'generates Text with fontSize routed through FontSpec resolve' do
      result = described_class.send(:generate_text_component, { 'text' => 'Test', 'fontSize' => 18 }, 0, required_imports)
      expect(result).to include('Configuration.Font.resolve(FontSpec(')
      expect(result).to include('size = 18.sp')
      expect(result).to match(/fontSize = resolved_constraint_text\d+\.size \?: TextUnit\.Unspecified/)
    end

    it 'generates Text with fontColor' do
      result = described_class.send(:generate_text_component, { 'text' => 'Test', 'fontColor' => '#FF0000' }, 0, required_imports)
      expect(result).to include('color =')
    end

    it 'generates Text with color attribute' do
      result = described_class.send(:generate_text_component, { 'text' => 'Test', 'color' => '#FF0000' }, 0, required_imports)
      expect(result).to include('color =')
    end

    it 'generates Text with font bold routed through FontSpec resolve' do
      result = described_class.send(:generate_text_component, { 'text' => 'Test', 'font' => 'bold' }, 0, required_imports)
      expect(result).to include('Configuration.Font.resolve(FontSpec(')
      expect(result).to include('weight = FontWeight.Bold')
      expect(result).to match(/fontWeight = resolved_constraint_text\d+\.weight/)
    end

    it 'generates Text with fontWeight bold routed through FontSpec resolve' do
      result = described_class.send(:generate_text_component, { 'text' => 'Test', 'fontWeight' => 'bold' }, 0, required_imports)
      expect(result).to include('Configuration.Font.resolve(FontSpec(')
      expect(result).to include('weight = FontWeight.Bold')
      expect(result).to match(/fontWeight = resolved_constraint_text\d+\.weight/)
    end

    it 'generates Text with textAlign center' do
      result = described_class.send(:generate_text_component, { 'text' => 'Test', 'textAlign' => 'center' }, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.Center')
    end

    it 'generates Text with textAlign left' do
      result = described_class.send(:generate_text_component, { 'text' => 'Test', 'textAlign' => 'left' }, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.Left')
    end

    it 'generates Text with textAlign right' do
      result = described_class.send(:generate_text_component, { 'text' => 'Test', 'textAlign' => 'right' }, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.Right')
    end
  end

  describe '.generate_button_component' do
    it 'generates basic Button' do
      result = described_class.send(:generate_button_component, { 'text' => 'Click' }, 0, required_imports)
      expect(result).to include('Button(')
      expect(result).to include('Text("Click")')
    end

    it 'generates Button with onclick' do
      result = described_class.send(:generate_button_component, { 'text' => 'Click', 'onclick' => 'handleClick' }, 0, required_imports)
      expect(result).to include('onClick = { data.handleClick?.invoke() }')
    end

    it 'generates Button with empty onClick when no handler' do
      result = described_class.send(:generate_button_component, { 'text' => 'Click' }, 0, required_imports)
      expect(result).to include('onClick = { }')
    end

    it 'uses default text when none provided' do
      result = described_class.send(:generate_button_component, {}, 0, required_imports)
      expect(result).to include('Text("Button")')
    end
  end

  describe '.generate_image_component' do
    it 'generates basic Image' do
      result = described_class.send(:generate_image_component, { 'src' => 'icon' }, 0, required_imports)
      expect(result).to include('Image(')
      expect(result).to include('R.drawable.icon')
    end

    it 'removes file extension' do
      result = described_class.send(:generate_image_component, { 'src' => 'icon.png' }, 0, required_imports)
      expect(result).to include('R.drawable.icon')
      expect(result).not_to include('.png')
    end

    it 'uses source attribute' do
      result = described_class.send(:generate_image_component, { 'source' => 'avatar' }, 0, required_imports)
      expect(result).to include('R.drawable.avatar')
    end

    it 'uses placeholder when no source' do
      result = described_class.send(:generate_image_component, {}, 0, required_imports)
      expect(result).to include('R.drawable.placeholder')
    end
  end

  describe '.generate_box_component' do
    it 'generates Box with empty content' do
      result = described_class.send(:generate_box_component, {}, 0, required_imports)
      expect(result).to include('Box(')
      expect(result).to include('// Content')
    end
  end

  describe '.quote' do
    it 'quotes text' do
      expect(described_class.send(:quote, 'hello')).to eq('"hello"')
    end

    it 'escapes quotes' do
      expect(described_class.send(:quote, 'hello "world"')).to eq('"hello \\"world\\""')
    end

    it 'escapes newlines' do
      expect(described_class.send(:quote, "hello\nworld")).to eq('"hello\\nworld"')
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      expect(described_class.send(:indent, 'text', 0)).to eq('text')
    end

    it 'adds indentation for level 1' do
      expect(described_class.send(:indent, 'text', 1)).to eq('    text')
    end

    it 'preserves empty lines' do
      result = described_class.send(:indent, "line1\n\nline2", 1)
      expect(result).to eq("    line1\n\n    line2")
    end
  end
end
