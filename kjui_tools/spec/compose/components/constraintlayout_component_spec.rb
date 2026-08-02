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
      # Container contract: the header code + children + a decorator that
      # injects constrainAs — children render via the REAL dispatch in
      # compose_builder (the old local mini-generators are gone).
      expect(result).to be_a(Hash)
      expect(result[:code]).to include('ConstraintLayout(')
      expect(result[:code]).to include('createRef()')
      expect(result[:layout_type]).to eq('ConstraintLayout')
      expect(result[:children].length).to eq(1)
      expect(result[:child_decorator]).to respond_to(:call)
    end

    it 'decorator injects constrainAs with linkTo margins from the ORIGINAL child' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'type' => 'View', 'id' => 'positioned', 'alignTop' => true, 'topMargin' => 12 }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      # The dispatched copy is margin-stripped (linkTo owns the offset)…
      expect(result[:children].first).not_to have_key('topMargin')
      # …but the injected constraint block still reads the original margins.
      decorated = result[:child_decorator].call(
        result[:children].first,
        "Box(\n    modifier = Modifier\n        .testTag(\"positioned\")\n) {\n}",
        1, 0
      )
      expect(decorated).to include('constrainAs(positioned)')
      expect(decorated).to include('top.linkTo(parent.top')
      expect(decorated).to include('12')
      expect(decorated).to include('.testTag("positioned")')
    end

    it 'keeps the id → testTag contract on the ConstraintLayout path' do
      # Regression: this branch used to drop the root testTag, so any layout
      # whose root has a relative-positioned child (align*View) could not be
      # found by the test driver — the conformance align* fixtures were
      # uncapturable until the tag was restored.
      json_data = {
        'type' => 'View',
        'id' => 'root',
        'child' => [
          { 'type' => 'View', 'id' => 'anchor', 'width' => 50, 'height' => 50 },
          { 'type' => 'View', 'id' => 'target', 'alignBottomOfView' => 'anchor' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('ConstraintLayout(')
      expect(result[:code]).to include('.testTag("root")')
      expect(result[:code]).to include('.semantics { testTagsAsResourceId = true }')
      expect(required_imports).to include(:test_tag)
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
      expect(result[:code]).to include('ConstraintLayout(')
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
      expect(result[:code]).to include('myButton')
      expect(result[:code]).to include('createRef()')
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
      expect(result[:code]).to include('view_0')
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
