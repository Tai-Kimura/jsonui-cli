# frozen_string_literal: true

require 'compose/style_loader'
require 'core/config_manager'
require 'core/project_finder'

RSpec.describe KjuiTools::Compose::StyleLoader do
  let(:temp_dir) { Dir.mktmpdir('style_loader_test') }
  let(:styles_dir) { File.join(temp_dir, 'src/main/assets/Styles') }

  let(:config) do
    {
      'source_directory' => 'src/main',
      'styles_directory' => 'assets/Styles',
      'project_path' => temp_dir
    }
  end

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    FileUtils.mkdir_p(styles_dir)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '.load_and_merge' do
    it 'returns json_data unchanged when no style' do
      json_data = { 'type' => 'Text', 'text' => 'Hello' }
      result = described_class.load_and_merge(json_data)
      expect(result).to eq(json_data)
    end

    it 'returns non-hash data unchanged' do
      result = described_class.load_and_merge('string')
      expect(result).to eq('string')
    end

    context 'with style file' do
      before do
        File.write(File.join(styles_dir, 'cardStyle.json'), JSON.generate({
          'background' => '#FFFFFF',
          'cornerRadius' => 12
        }))
      end

      it 'applies style from file' do
        json_data = { 'type' => 'View', 'style' => 'cardStyle' }
        result = described_class.load_and_merge(json_data)
        expect(result['background']).to eq('#FFFFFF')
        expect(result['cornerRadius']).to eq(12)
      end

      it 'component attributes override style' do
        json_data = { 'type' => 'View', 'style' => 'cardStyle', 'cornerRadius' => 20 }
        result = described_class.load_and_merge(json_data)
        expect(result['cornerRadius']).to eq(20)  # Component value takes precedence
      end

      it 'removes style key from result' do
        json_data = { 'type' => 'View', 'style' => 'cardStyle' }
        result = described_class.load_and_merge(json_data)
        expect(result).not_to have_key('style')
      end
    end

    it 'processes children recursively' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'type' => 'Text', 'text' => 'Hello' }
        ]
      }
      result = described_class.load_and_merge(json_data)
      expect(result['child'].first['type']).to eq('Text')
    end

    it 'processes single child' do
      json_data = {
        'type' => 'View',
        'child' => { 'type' => 'Text', 'text' => 'Hello' }
      }
      result = described_class.load_and_merge(json_data)
      expect(result['child']['type']).to eq('Text')
    end

    it 'handles include attribute' do
      json_data = { 'type' => 'View', 'include' => 'some_component' }
      result = described_class.load_and_merge(json_data)
      expect(result).to have_key('include')
    end

    context 'with invalid style file' do
      before do
        File.write(File.join(styles_dir, 'invalidStyle.json'), 'not valid json')
      end

      it 'returns data without style applied' do
        json_data = { 'type' => 'View', 'style' => 'invalidStyle' }
        expect { described_class.load_and_merge(json_data) }.to output(/Warning/).to_stdout
      end
    end
  end
end
