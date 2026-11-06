# frozen_string_literal: true

require 'tmpdir'
require 'fileutils'
require 'json'
require 'cli/commands/init'
require 'core/resources/string_manager'

# Ticket 2026-11-06-sjui-init-string-files-entry-is-not-found: string_files are
# read from source_directory, and `init` wrote a SwiftUI project's entry with
# source_directory in it, so the first build warned and wrote nothing.
RSpec.describe 'the string_files entry `init` writes' do
  let(:root) { File.realpath(Dir.mktmpdir('init_strings')) }

  around do |example|
    Dir.chdir(root) { example.run }
  ensure
    FileUtils.rm_rf(root)
  end

  before do
    allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
    allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return("#{root}/MyApp.xcodeproj")
    allow(SjuiTools::Core::ProjectFinder).to receive(:find_source_directory).and_return('')
  end

  # init's own config, then what a build reads: the real file where Xcode has it.
  def init_and_apply(mode, real_file)
    allow($stdout).to receive(:write)
    SjuiTools::CLI::Commands::Init.new.run(['--mode', mode])
    config = JSON.parse(File.read('sjui.config.json'))
    source = File.join(root, config['source_directory'].to_s)
    FileUtils.mkdir_p(File.dirname(File.join(root, real_file)))
    File.write(File.join(root, real_file), '')
    FileUtils.mkdir_p(File.join(source, 'Layouts/Resources'))
    File.write(File.join(source, 'Layouts/Resources/strings.json'),
               JSON.generate({ 'home' => { 'hello' => { 'en' => 'EN', 'ja' => 'JA' } } }))
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(source)
    SjuiTools::Core::Resources::StringManager.new.apply_to_strings_files
    [config, File.read(File.join(root, real_file))]
  end

  it 'is found and written on a SwiftUI project' do
    config, written = init_and_apply('swiftui', 'MyApp/Localizable.strings')
    expect(config['source_directory']).to eq('MyApp')
    expect(config['string_files']).to eq(['Localizable.strings'])
    expect(written).to include('"home_hello" = "EN";')
  end

  it 'stays found and written where source_directory is empty (UIKit)' do
    config, written = init_and_apply('uikit', 'MyApp/Localizable.strings')
    expect(config['source_directory']).to eq('')
    expect(config['string_files']).to eq(['MyApp/Localizable.strings'])
    expect(written).to include('"home_hello" = "EN";')
  end
end

RSpec.describe SjuiTools::Core::Resources::StringManager, 'a string_files entry that is not there' do
  let(:root) { File.realpath(Dir.mktmpdir('init_strings')) }
  let(:source) { File.join(root, 'MyApp') }
  let(:config) { { 'source_directory' => 'MyApp', 'string_files' => string_files } }

  before do
    FileUtils.mkdir_p(File.join(source, 'Layouts/Resources'))
    File.write(File.join(source, 'Layouts/Resources/strings.json'), JSON.generate({ 'home' => { 'k' => { 'en' => 'E' } } }))
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(source)
    allow(SjuiTools::Core::Logger).to receive(:info)
    allow(SjuiTools::Core::Logger).to receive(:success)
    allow(SjuiTools::Core::Logger).to receive(:warn) { |line| warnings << line }
  end

  after { FileUtils.rm_rf(root) }

  let(:warnings) { [] }

  context 'when it names source_directory again (what init wrote through 2.5.5)' do
    let(:string_files) { ['MyApp/Localizable.strings'] }

    it 'says what the entry would be, on both the apply and the cache' do
      manager = described_class.new
      manager.apply_to_strings_files
      manager.cache_strings_files(string_files)
      expect(warnings.grep(/not found/).length).to eq(2)
      expect(warnings.grep(/not found/)).to all(include("this one would be 'Localizable.strings'"))
    end

    it 'still reads it as written: a directory of that name is a directory of that name' do
      FileUtils.mkdir_p(File.join(source, 'MyApp'))
      nested = File.join(source, 'MyApp/Localizable.strings')
      File.write(nested, '')
      described_class.new.apply_to_strings_files
      expect(File.read(nested)).to include('"home_k" = "E";')
      expect(warnings.grep(/not found/)).to be_empty
    end
  end

  context 'when it does not' do
    let(:string_files) { ['ja.lproj/Localizable.strings'] }

    it 'has no hint to give' do
      described_class.new.apply_to_strings_files
      expect(warnings.grep(/not found/).first).not_to include('would be')
    end
  end
end
