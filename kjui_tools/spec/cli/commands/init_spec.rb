# frozen_string_literal: true

require 'cli/commands/init'
require 'core/config_manager'
require 'core/project_finder'
require 'fileutils'

RSpec.describe KjuiTools::CLI::Commands::Init do
  let(:temp_dir) { Dir.mktmpdir('init_test') }

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    allow(KjuiTools::Core::ProjectFinder).to receive(:setup_paths)
    allow(KjuiTools::Core::ProjectFinder).to receive(:package_name).and_return('com.example.app')
    allow(KjuiTools::Core::ProjectFinder).to receive(:find_source_directory).and_return('src/main')
    allow(KjuiTools::Core::ConfigManager).to receive(:detect_mode).and_return('compose')
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      'source_directory' => 'src/main',
      'layouts_directory' => 'assets/Layouts',
      'styles_directory' => 'assets/Styles'
    })
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '#run' do
    context 'in compose mode' do
      it 'creates config file' do
        init = described_class.new
        expect { init.run(['--mode', 'compose']) }.to output(/Initializing KotlinJsonUI/).to_stdout
        expect(File.exist?('kjui.config.json')).to be true
      end

      it 'shows initialization complete message' do
        init = described_class.new
        expect { init.run(['--mode', 'compose']) }.to output(/Initialization complete/).to_stdout
      end

      it 'shows next steps with setup instruction' do
        init = described_class.new
        expect { init.run(['--mode', 'compose']) }.to output(/Run 'kjui setup'/).to_stdout
      end
    end

    context 'in xml mode' do
      it 'creates config file' do
        init = described_class.new
        expect { init.run(['--mode', 'xml']) }.to output(/Initializing KotlinJsonUI/).to_stdout
        expect(File.exist?('kjui.config.json')).to be true
      end

      it 'shows initialization complete' do
        init = described_class.new
        expect { init.run(['--mode', 'xml']) }.to output(/Initialization complete/).to_stdout
      end

      it 'shows next steps message' do
        init = described_class.new
        expect { init.run(['--mode', 'xml']) }.to output(/Next steps/).to_stdout
      end
    end

    context 'when config already exists' do
      before do
        File.write('kjui.config.json', JSON.generate({
          'mode' => 'compose',
          'source_directory' => 'src/main'
        }))
      end

      it 'detects existing config' do
        init = described_class.new
        expect { init.run(['--mode', 'compose']) }.to output(/Config file already exists/).to_stdout
      end
    end

    context 'mode detection' do
      it 'uses compose mode by default' do
        init = described_class.new
        expect { init.run([]) }.to output(/compose mode/).to_stdout
      end
    end
  end

  # `kjui init --mode compose` in a fresh process (2026-09-03): the compose
  # branch reads ColorManager::DEFAULT_RESOURCE_MANAGER_SUFFIX, and init.rb
  # did not load it. This file's own examples could not see that — run with
  # the rest of the suite, spec/core/resources/color_manager_spec.rb had
  # already loaded the constant, and only an isolated run
  # (`rspec spec/cli/commands/init_spec.rb`) went red. So the check below
  # runs in a child interpreter that loads init.rb and nothing else: what a
  # consumer's `kjui init` actually starts from.
  describe 'require chain (fresh interpreter, no sibling spec loaded)' do
    let(:lib_dir) { File.expand_path('../../../lib', __dir__) }

    it 'resolves the ColorManager constant the compose default reads' do
      script = "require 'cli/commands/init'; " \
               "puts KjuiTools::Core::Resources::ColorManager::DEFAULT_RESOURCE_MANAGER_SUFFIX"
      out = IO.popen([RbConfig.ruby, '-I', lib_dir, '-e', script], err: %i[child out], &:read)
      expect($?.success?).to be(true), "init.rb alone must load the constant it reads:\n#{out}"
      expect(out.strip).to eq(File.join('kotlin', 'com', 'kotlinjsonui', 'generated'))
    end

    it 'writes the compose config with the generated ColorManager path' do
      init = described_class.new
      expect { init.run(['--mode', 'compose']) }.to output(/Initialization complete/).to_stdout
      config = JSON.parse(File.read('kjui.config.json'))
      expect(config['resource_manager_directory']).to eq('src/main/kotlin/com/kotlinjsonui/generated')
    end
  end

  describe 'option parsing' do
    it 'accepts --mode option' do
      init = described_class.new
      expect { init.run(['--mode', 'compose']) }.to output(/Initialization complete/).to_stdout
    end

    it 'shows help with --help' do
      init = described_class.new
      expect { init.run(['--help']) }.to raise_error(SystemExit)
    end
  end
end
