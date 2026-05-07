# frozen_string_literal: true

require 'core/style_loader'

RSpec.describe StyleLoader do
  let(:temp_dir) { Dir.mktmpdir }
  let(:styles_dir) { File.join(temp_dir, 'src/main/assets/Styles') }
  let(:config) { { 'project_path' => temp_dir } }

  before do
    FileUtils.mkdir_p(styles_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'loads styles from Styles directory' do
      File.write(File.join(styles_dir, 'primary_button.json'), '{"background": "#6200EE"}')

      loader = described_class.new(config)
      styles = loader.instance_variable_get(:@styles)

      expect(styles).to have_key('primary_button')
      expect(styles['primary_button']['background']).to eq('#6200EE')
    end

    it 'handles missing Styles directory' do
      FileUtils.rm_rf(styles_dir)

      loader = described_class.new(config)
      styles = loader.instance_variable_get(:@styles)

      expect(styles).to eq({})
    end

    it 'handles invalid JSON in style file' do
      File.write(File.join(styles_dir, 'invalid.json'), 'not valid json')

      expect { described_class.new(config) }.to output(/Warning.*Failed to load style/).to_stdout
    end

    it 'loads multiple style files' do
      File.write(File.join(styles_dir, 'style1.json'), '{"color": "#FF0000"}')
      File.write(File.join(styles_dir, 'style2.json'), '{"color": "#00FF00"}')

      loader = described_class.new(config)
      styles = loader.instance_variable_get(:@styles)

      expect(styles).to have_key('style1')
      expect(styles).to have_key('style2')
    end

    it 'tries app/src/main/assets/Styles if src/main/assets/Styles not found' do
      FileUtils.rm_rf(styles_dir)
      app_styles_dir = File.join(temp_dir, 'app/src/main/assets/Styles')
      FileUtils.mkdir_p(app_styles_dir)
      File.write(File.join(app_styles_dir, 'app_style.json'), '{"fontSize": 16}')

      loader = described_class.new(config)
      styles = loader.instance_variable_get(:@styles)

      expect(styles).to have_key('app_style')
    end
  end

  describe '#apply_styles' do
    before do
      File.write(File.join(styles_dir, 'button.json'), '{"background": "#6200EE", "fontColor": "#FFFFFF"}')
      File.write(File.join(styles_dir, 'large_text.json'), '{"fontSize": 24}')
    end

    let(:loader) { described_class.new(config) }

    it 'applies style to element' do
      json_data = { 'type' => 'Button', 'style' => 'button', 'text' => 'Click' }

      result = loader.apply_styles(json_data)

      expect(result['background']).to eq('#6200EE')
      expect(result['fontColor']).to eq('#FFFFFF')
      expect(result['text']).to eq('Click')
    end

    it 'removes style attribute after applying' do
      json_data = { 'type' => 'Button', 'style' => 'button' }

      result = loader.apply_styles(json_data)

      expect(result).not_to have_key('style')
    end

    it 'does not override inline attributes' do
      json_data = { 'type' => 'Button', 'style' => 'button', 'background' => '#FF0000' }

      result = loader.apply_styles(json_data)

      expect(result['background']).to eq('#FF0000')
    end

    it 'applies multiple styles as array' do
      json_data = { 'type' => 'Button', 'style' => ['button', 'large_text'] }

      result = loader.apply_styles(json_data)

      expect(result['background']).to eq('#6200EE')
      expect(result['fontSize']).to eq(24)
    end

    it 'applies styles recursively to children array' do
      json_data = {
        'type' => 'View',
        'child' => [
          { 'type' => 'Button', 'style' => 'button' }
        ]
      }

      result = loader.apply_styles(json_data)

      expect(result['child'][0]['background']).to eq('#6200EE')
    end

    it 'applies styles recursively to single child' do
      json_data = {
        'type' => 'View',
        'child' => { 'type' => 'Button', 'style' => 'button' }
      }

      result = loader.apply_styles(json_data)

      expect(result['child']['background']).to eq('#6200EE')
    end

    it 'applies styles recursively to children key' do
      json_data = {
        'type' => 'View',
        'children' => [
          { 'type' => 'Button', 'style' => 'button' }
        ]
      }

      result = loader.apply_styles(json_data)

      expect(result['children'][0]['background']).to eq('#6200EE')
    end

    it 'handles element without style' do
      json_data = { 'type' => 'Text', 'text' => 'Hello' }

      result = loader.apply_styles(json_data)

      expect(result['text']).to eq('Hello')
    end

    it 'handles non-existent style' do
      json_data = { 'type' => 'Button', 'style' => 'nonexistent' }

      result = loader.apply_styles(json_data)

      expect(result).not_to have_key('style')
    end

    it 'handles non-hash element' do
      result = loader.apply_styles('not a hash')
      expect(result).to eq('not a hash')
    end
  end
end
