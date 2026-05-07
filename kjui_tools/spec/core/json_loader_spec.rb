# frozen_string_literal: true

require 'core/json_loader'

RSpec.describe JsonLoader do
  let(:temp_dir) { Dir.mktmpdir('json_loader_test') }
  let(:config) { { 'project_path' => temp_dir } }
  let(:loader) { described_class.new(config) }

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#load_layout' do
    context 'when layout file exists' do
      before do
        layouts_dir = File.join(temp_dir, 'src', 'main', 'assets', 'Layouts')
        FileUtils.mkdir_p(layouts_dir)
        File.write(File.join(layouts_dir, 'TestLayout.json'), '{"type": "View"}')
      end

      it 'loads layout with .json extension' do
        content = loader.load_layout('TestLayout.json')
        expect(content).to eq('{"type": "View"}')
      end

      it 'loads layout without .json extension' do
        content = loader.load_layout('TestLayout')
        expect(content).to eq('{"type": "View"}')
      end
    end

    context 'when layout is in app/src/main/assets/Layouts' do
      before do
        layouts_dir = File.join(temp_dir, 'app', 'src', 'main', 'assets', 'Layouts')
        FileUtils.mkdir_p(layouts_dir)
        File.write(File.join(layouts_dir, 'AppLayout.json'), '{"type": "Text"}')
      end

      it 'finds layout in app directory' do
        content = loader.load_layout('AppLayout')
        expect(content).to eq('{"type": "Text"}')
      end
    end

    context 'when layout is in Layouts directory' do
      before do
        layouts_dir = File.join(temp_dir, 'Layouts')
        FileUtils.mkdir_p(layouts_dir)
        File.write(File.join(layouts_dir, 'SimpleLayout.json'), '{"type": "Button"}')
      end

      it 'finds layout in root Layouts directory' do
        content = loader.load_layout('SimpleLayout')
        expect(content).to eq('{"type": "Button"}')
      end
    end

    context 'when layout is in project root' do
      before do
        File.write(File.join(temp_dir, 'RootLayout.json'), '{"type": "Image"}')
      end

      it 'finds layout in project root' do
        content = loader.load_layout('RootLayout')
        expect(content).to eq('{"type": "Image"}')
      end
    end

    context 'when layout file does not exist' do
      it 'returns nil' do
        content = loader.load_layout('NonExistent')
        expect(content).to be_nil
      end
    end
  end

  describe '#load_json' do
    context 'when file exists' do
      before do
        File.write(File.join(temp_dir, 'test.json'), '{"key": "value"}')
      end

      it 'loads and returns file content' do
        content = loader.load_json(File.join(temp_dir, 'test.json'))
        expect(content).to eq('{"key": "value"}')
      end
    end

    context 'when file does not exist' do
      it 'returns nil' do
        content = loader.load_json(File.join(temp_dir, 'nonexistent.json'))
        expect(content).to be_nil
      end
    end
  end
end
