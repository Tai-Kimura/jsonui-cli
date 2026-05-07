# frozen_string_literal: true

require 'cli/commands/validate'

RSpec.describe SjuiTools::CLI::Commands::Validate do
  let(:command) { described_class.new }
  let(:temp_dir) { File.realpath(Dir.mktmpdir('validate_test')) }

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#run' do
    context 'when project does not exist' do
      before do
        allow(command).to receive(:project_exists?).and_return(false)
      end

      it 'exits with error' do
        expect { command.run([]) }.to raise_error(SystemExit)
      end
    end

    context 'with --help flag' do
      it 'shows help and returns' do
        expect { command.run(['--help']) }.to output(/Usage: sjui validate/).to_stdout
      end
    end

    context 'with valid JSON files' do
      before do
        allow(command).to receive(:project_exists?).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'layouts_directory' => 'Layouts'
        })

        layouts_dir = File.join(temp_dir, 'Layouts')
        FileUtils.mkdir_p(layouts_dir)
        File.write(File.join(layouts_dir, 'valid.json'), '{"type": "View"}')
      end

      it 'reports valid files' do
        expect { begin; command.run([]); rescue SystemExit; end }.to output(/All 1 file\(s\) are valid JSON/).to_stdout
      end
    end

    context 'with invalid JSON files' do
      before do
        allow(command).to receive(:project_exists?).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'layouts_directory' => 'Layouts'
        })

        layouts_dir = File.join(temp_dir, 'Layouts')
        FileUtils.mkdir_p(layouts_dir)
        File.write(File.join(layouts_dir, 'invalid.json'), 'not valid json')
      end

      it 'reports errors' do
        expect { begin; command.run([]); rescue SystemExit; end }.to output(/Invalid:/).to_stdout
      end
    end

    context 'with --verbose flag' do
      before do
        allow(command).to receive(:project_exists?).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'layouts_directory' => 'Layouts'
        })

        layouts_dir = File.join(temp_dir, 'Layouts')
        FileUtils.mkdir_p(layouts_dir)
        File.write(File.join(layouts_dir, 'valid.json'), '{"type": "View"}')
      end

      it 'shows detailed output' do
        expect { begin; command.run(['--verbose']); rescue SystemExit; end }.to output(/Valid:/).to_stdout
      end
    end

    context 'with specific file' do
      let(:json_file) { File.join(temp_dir, 'test.json') }

      before do
        allow(command).to receive(:project_exists?).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
        allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
        File.write(json_file, '{"valid": true}')
      end

      it 'validates specific file' do
        expect { begin; command.run([json_file]); rescue SystemExit; end }.to output(/All 1 file\(s\) are valid JSON/).to_stdout
      end
    end
  end
end
