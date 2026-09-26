# frozen_string_literal: true

require 'compose/components/progress_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::ProgressComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  describe '.generate' do
    context 'indeterminate progress' do
      it 'generates linear indeterminate progress by default' do
        json_data = { 'type' => 'Progress' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('LinearProgressIndicator(')
      end

      # `style` is the style file's name (common.style), not a shape:
      # Progress declares none, so whatever the style is called it is a bar.
      it 'draws a bar whatever style file the node names' do
        %w[circular large linear bar_primary].each do |style|
          result = described_class.generate({ 'type' => 'Progress', 'style' => style }, 0, required_imports)
          expect(result).to include('LinearProgressIndicator('), style
          expect(result).not_to include('CircularProgressIndicator('), style
        end
      end
    end

    context 'determinate progress' do
      it 'generates progress with value' do
        json_data = { 'type' => 'Progress', 'value' => '0.5' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('LinearProgressIndicator(')
        expect(result).to include('progress = {')
      end

      it 'generates progress with bind attribute' do
        json_data = { 'type' => 'Progress', 'bind' => '@{progressValue}' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('progress = { data.progressValue.toFloat() }')
      end

      it 'generates progress with value data binding' do
        json_data = { 'type' => 'Progress', 'value' => '@{downloadProgress}' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('progress = { data.downloadProgress.toFloat() }')
      end
    end

    context 'with colors' do
      it 'generates progress with progressTintColor' do
        json_data = { 'type' => 'Progress', 'progressTintColor' => '#007AFF' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('color =')
      end

      it 'generates progress with trackTintColor' do
        json_data = { 'type' => 'Progress', 'trackTintColor' => '#CCCCCC' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('trackColor =')
      end

      it 'generates progress with both colors' do
        json_data = {
          'type' => 'Progress',
          'progressTintColor' => '#007AFF',
          'trackTintColor' => '#CCCCCC'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('color =')
        expect(result).to include('trackColor =')
      end
    end

    context 'with modifiers' do
      it 'generates progress with width' do
        json_data = { 'type' => 'Progress', 'width' => 200 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.requiredWidth(200.dp)')
      end

      it 'generates progress with height' do
        json_data = { 'type' => 'Progress', 'height' => 50 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.requiredHeight(50.dp)')
      end

      it 'generates progress with padding' do
        json_data = { 'type' => 'Progress', 'padding' => 16 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('modifier = Modifier')
      end

      it 'generates progress with margins' do
        json_data = { 'type' => 'Progress', 'margins' => [10, 20] }
        result = described_class.generate(json_data, 0, required_imports)
        # Progress with margins still generates
        expect(result).to include('ProgressIndicator(')
      end
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      result = described_class.send(:indent, 'text', 0)
      expect(result).to eq('text')
    end

    it 'adds indentation for level 1' do
      result = described_class.send(:indent, 'text', 1)
      expect(result).to eq('    text')
    end

    it 'handles multi-line text' do
      result = described_class.send(:indent, "line1\nline2", 1)
      expect(result).to eq("    line1\n    line2")
    end

    it 'preserves empty lines' do
      result = described_class.send(:indent, "line1\n\nline2", 1)
      expect(result).to eq("    line1\n\n    line2")
    end
  end
end
