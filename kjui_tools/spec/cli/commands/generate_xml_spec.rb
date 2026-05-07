# frozen_string_literal: true

require 'cli/commands/generate_xml'
require 'core/config_manager'

RSpec.describe CLI::Commands::GenerateXml do
  let(:temp_dir) { Dir.mktmpdir }
  let(:config) do
    {
      'project_path' => temp_dir,
      'mode' => 'xml'
    }
  end

  # Use stub_const to make ConfigManager available in the CLI module scope
  before do
    stub_const('ConfigManager', KjuiTools::Core::ConfigManager)
    allow(ConfigManager).to receive(:load_config).and_return(config)
    # Create directory structure
    layouts_dir = File.join(temp_dir, 'app', 'src', 'main', 'assets', 'Layouts')
    FileUtils.mkdir_p(layouts_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '.run' do
    it 'returns error when config is nil' do
      allow(ConfigManager).to receive(:load_config).and_return(nil)
      expect { described_class.run([]) }.to output(/config.json not found/).to_stdout
    end

    it 'returns error when mode is not xml' do
      allow(ConfigManager).to receive(:load_config).and_return({ 'mode' => 'compose', 'project_path' => temp_dir })
      expect { described_class.run([]) }.to output(/not XML/).to_stdout
    end

    it 'shows help with -h flag' do
      expect { described_class.run(['-h']) }.to output(/Usage: kjui generate-xml/).to_stdout
    end

    it 'shows help with --help flag' do
      expect { described_class.run(['--help']) }.to output(/Usage: kjui generate-xml/).to_stdout
    end

    context 'when generating layouts' do
      before do
        layouts_dir = File.join(temp_dir, 'app', 'src', 'main', 'assets', 'Layouts')
        # No JSON files
      end

      it 'reports no JSON files found when directory is empty' do
        expect { described_class.run([]) }.to output(/No JSON layout files found/).to_stdout
      end
    end
  end

  describe '.show_help' do
    it 'outputs usage information' do
      expect { described_class.send(:show_help) }.to output(/Usage: kjui generate-xml/).to_stdout
    end

    it 'includes argument descriptions' do
      expect { described_class.send(:show_help) }.to output(/layout_name/).to_stdout
    end

    it 'includes option descriptions' do
      expect { described_class.send(:show_help) }.to output(/--force/).to_stdout
      expect { described_class.send(:show_help) }.to output(/--layout/).to_stdout
      expect { described_class.send(:show_help) }.to output(/--help/).to_stdout
    end

    it 'includes examples' do
      expect { described_class.send(:show_help) }.to output(/Examples:/).to_stdout
    end
  end

  describe '.should_generate?' do
    let(:layouts_dir) { File.join(temp_dir, 'app', 'src', 'main', 'assets', 'Layouts') }
    let(:res_layout_dir) { File.join(temp_dir, 'app', 'src', 'main', 'res', 'layout') }
    let(:layout_name) { 'test_view' }

    before do
      FileUtils.mkdir_p(res_layout_dir)
    end

    it 'returns true when force is true' do
      result = described_class.send(:should_generate?, layout_name, config, true)
      expect(result).to be true
    end

    it 'returns true when xml file does not exist' do
      File.write(File.join(layouts_dir, "#{layout_name}.json"), '{}')
      result = described_class.send(:should_generate?, layout_name, config, false)
      expect(result).to be true
    end

    it 'returns true when json file does not exist' do
      result = described_class.send(:should_generate?, layout_name, config, false)
      expect(result).to be true
    end

    it 'returns true when json is newer than xml' do
      json_file = File.join(layouts_dir, "#{layout_name}.json")
      xml_file = File.join(res_layout_dir, "#{layout_name}.xml")

      File.write(xml_file, '')
      sleep 0.1
      File.write(json_file, '{}')

      result = described_class.send(:should_generate?, layout_name, config, false)
      expect(result).to be true
    end

    it 'returns false when xml is newer than json' do
      json_file = File.join(layouts_dir, "#{layout_name}.json")
      xml_file = File.join(res_layout_dir, "#{layout_name}.xml")

      File.write(json_file, '{}')
      sleep 0.1
      File.write(xml_file, '')

      result = described_class.send(:should_generate?, layout_name, config, false)
      expect(result).to be false
    end
  end
end
