# frozen_string_literal: true

require 'cli/commands/init'

RSpec.describe SjuiTools::CLI::Commands::Init do
  let(:command) { described_class.new }
  let(:temp_dir) { Dir.mktmpdir('init_test') }

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '#run' do
    before do
      allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
      allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(nil)
      allow(SjuiTools::Core::ProjectFinder).to receive(:find_source_directory).and_return('Sources')
      allow(SjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('swiftui')
    end

    context 'with --help flag' do
      it 'shows help and exits' do
        expect { command.run(['--help']) }.to raise_error(SystemExit)
      end
    end

    context 'with --mode option' do
      it 'creates config file with specified mode' do
        expect { command.run(['--mode', 'swiftui']) }.to output(/Initializing SwiftJsonUI project in swiftui mode/).to_stdout

        expect(File.exist?('sjui.config.json')).to be true
        config = JSON.parse(File.read('sjui.config.json'))
        expect(config['mode']).to eq('swiftui')
      end

      it 'creates config file for uikit mode' do
        expect { command.run(['--mode', 'uikit']) }.to output(/Initializing SwiftJsonUI project in uikit mode/).to_stdout

        config = JSON.parse(File.read('sjui.config.json'))
        expect(config['mode']).to eq('uikit')
        expect(config['bindings_directory']).to eq('Bindings')
      end

      it 'creates config file for all mode' do
        expect { command.run(['--mode', 'all']) }.to output(/Initializing SwiftJsonUI project in all mode/).to_stdout

        config = JSON.parse(File.read('sjui.config.json'))
        expect(config['mode']).to eq('all')
      end
    end

    context 'when config file already exists' do
      before do
        File.write('sjui.config.json', JSON.pretty_generate({
          'mode' => 'swiftui',
          'source_directory' => ''
        }))
        FileUtils.mkdir_p('Sources')
      end

      it 'does not overwrite existing config' do
        expect { command.run([]) }.to output(/Config file already exists/).to_stdout
      end

      it 'updates source_directory if empty' do
        allow(SjuiTools::Core::ProjectFinder).to receive(:project_dir).and_return(temp_dir)

        expect { command.run([]) }.to output(/Updated source_directory/).to_stdout

        config = JSON.parse(File.read('sjui.config.json'))
        expect(config['source_directory']).to eq('Sources')
      end
    end

    context 'with detected mode from installer' do
      let(:mode_file) { File.join(File.dirname(__FILE__), '../../../../MODE') }

      it 'uses detected mode when no option specified' do
        expect { command.run([]) }.to output(/Initializing SwiftJsonUI project in swiftui mode/).to_stdout
      end
    end

    context 'swiftui config' do
      it 'includes swiftui-specific directories' do
        command.run(['--mode', 'swiftui'])

        config = JSON.parse(File.read('sjui.config.json'))
        expect(config['layouts_directory']).to eq('Layouts')
        expect(config['styles_directory']).to eq('Styles')
        expect(config['view_directory']).to eq('View')
        expect(config['data_directory']).to eq('Data')
        expect(config['viewmodel_directory']).to eq('ViewModel')
        expect(config['resource_manager_directory']).to eq('ResourceManager')
      end

    end

    context 'uikit config' do
      it 'includes uikit-specific directories' do
        command.run(['--mode', 'uikit'])

        config = JSON.parse(File.read('sjui.config.json'))
        expect(config['bindings_directory']).to eq('Bindings')
        expect(config['hot_loader_directory']).to be_a(String)
      end
    end

    context 'output messages' do
      it 'shows completion message for swiftui mode' do
        expect { command.run(['--mode', 'swiftui']) }.to output(/SwiftUI mode initialized/).to_stdout
      end

      it 'shows next steps for uikit mode' do
        expect { command.run(['--mode', 'uikit']) }.to output(/Next steps:/).to_stdout
      end
    end
  end
end
