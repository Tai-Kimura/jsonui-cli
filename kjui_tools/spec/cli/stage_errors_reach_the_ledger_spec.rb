# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'pathname'
require_relative '../../lib/core/stage_failures'

# An ERROR a build prints is a stage it did not complete: it is in the ledger
# (JUI_STAGE_FAILURES, which `jui build` turns into exit 1) and the build does
# not end in "Compose build completed!". One arm per stage of `kjui build`
# that printed an error (or, for a style, the warning sjui and rjui print as
# an error) and carried on, each made to fail by a real input where one
# reaches it.
#
# Until 1.8.121 (measured on 32785ce8, 2026-09-26) each of these ended in
# "✅ Compose build completed!" with nothing in the ledger — and where the
# ledger did hold an entry (colors.json unparseable), the success line came
# directly under the list of what had not completed. Ticket
# uikit-build-reports-success-after-a-binding-error.
RSpec.describe 'kjui build: a stage that printed an error is in the ledger' do
  KJUI_ROOT = File.expand_path('../..', __dir__)
  SRC = 'app/src/main'

  def project(dangling_definitions: false)
    dir = Dir.mktmpdir('kjui_stage')
    if dangling_definitions
      FileUtils.mkdir_p(File.join(dir, 'kjui_tools'))
      %w[bin lib].each { |d| system('cp', '-R', File.join(KJUI_ROOT, d), File.join(dir, 'kjui_tools')) || raise(d) }
    else
      FileUtils.ln_s(KJUI_ROOT, File.join(dir, 'kjui_tools'))
    end
    File.write(File.join(dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => 'Probe', 'source_directory' => SRC,
      'layouts_directory' => 'assets/Layouts', 'styles_directory' => 'assets/Styles',
      'data_directory' => 'kotlin/com/example/app/data', 'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'view_directory' => 'kotlin/com/example/app/views', 'package_name' => 'com.example.app',
      'string_files' => ['res/values/strings.xml'], 'use_network' => true
    ))
    FileUtils.mkdir_p(File.join(dir, SRC, 'assets/Layouts'))
    FileUtils.mkdir_p(File.join(dir, SRC, 'assets/Styles'))
    @dirs << dir
    dir
  end

  def layout(dir, name, extra = {})
    File.write(File.join(dir, SRC, 'assets/Layouts', "#{name}.json"), JSON.pretty_generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical',
      'child' => [{ 'type' => 'Label', 'id' => 'title', 'text' => 'Hello', 'width' => 'wrapContent', 'height' => 'wrapContent' }.merge(extra)]
    ))
  end

  def build(dir)
    ledger = File.join(dir, 'ledger.json')
    log, status = Open3.capture2e({ 'JUI_STAGE_FAILURES' => ledger }, 'ruby', File.join(dir, 'kjui_tools', 'bin', 'kjui'), 'build', chdir: dir)
    [log.gsub(/\e\[[0-9;]*m/, ''), status.exitstatus, File.exist?(ledger) ? JSON.parse(File.read(ledger)) : []]
  end

  def expect_incomplete(log, code, entries, stage, *words)
    expect(code).to eq(0), log # the exit is `jui build`'s, from the ledger
    expect(entries.map { |e| e['stage'] }).to eq([stage]), "#{entries.inspect}\n#{log}"
    words.each { |w| expect(entries.first['message']).to include(w) }
    expect(log).to include('Build finished with 1 stage(s) incomplete — see above'), log
    expect(log).not_to include('Compose build completed!')
  end

  before(:all) { @dirs = [] }
  after(:all) do
    @dirs.each do |d|
      system('chmod', '-R', 'u+w', d)
      FileUtils.rm_rf(d)
    end
  end

  it 'a healthy build still ends "Compose build completed!" with an empty ledger (the control)' do
    dir = project
    layout(dir, 'home')
    log, code, entries = build(dir)
    expect([code, entries]).to eq([0, []]), log
    expect(log).to include('Compose build completed!')
  end

  it 'colors.json that does not parse: already in the ledger, and now the last line says so' do
    dir = project
    layout(dir, 'home')
    FileUtils.mkdir_p(File.join(dir, SRC, 'assets/Layouts/Resources'))
    File.write(File.join(dir, SRC, 'assets/Layouts/Resources/colors.json'), '{ "a": ')
    log, code, entries = build(dir)
    expect_incomplete(log, code, entries, 'colors', 'colors.json could not be parsed')
  end

  it 'a style that does not parse: in the ledger once' do
    dir = project
    File.write(File.join(dir, SRC, 'assets/Layouts/home.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => %w[a b].map { |id| { 'type' => 'Label', 'id' => id, 'text' => id, 'style' => 'broken' } }
    ))
    File.write(File.join(dir, SRC, 'assets/Styles/broken.json'), '{ "fontSize": ')
    log, code, entries = build(dir)
    expect(log).to include('Failed to parse style file')
    expect_incomplete(log, code, entries, 'styles', 'broken.json', 'drawn without it')
  end

  it 'colors.xml with no root element: in the ledger' do
    dir = project
    layout(dir, 'home', 'fontColor' => '#123456')
    FileUtils.mkdir_p(File.join(dir, SRC, 'res/values'))
    File.write(File.join(dir, SRC, 'res/values/colors.xml'), '')
    log, code, entries = build(dir)
    expect(log).to include('Invalid colors.xml structure')
    expect_incomplete(log, code, entries, 'colors', 'colors.xml', 'no root element')
  end

  it 'a layout whose colours could not be written back: in the ledger' do
    dir = project
    layout(dir, 'home', 'fontColor' => '#123456')
    file = File.join(dir, SRC, 'assets/Layouts/home.json')
    FileUtils.chmod(0o444, file)
    skip "#{file} is still writable (running as root?)" if File.writable?(file)
    log, code, entries = build(dir)
    expect_incomplete(log, code, entries, 'colors', 'home.json', 'colour extraction failed')
  end

  it 'kjui.config.json that does not parse: the build on the defaults is named, once for every load' do
    dir = project
    layout(dir, 'home')
    File.write(File.join(dir, 'kjui.config.json'), '{ "mode": ')
    log, code, entries = build(dir)
    expect(log.scan('Error parsing config file').size).to be > 1 # the control: loaded more than once
    expect_incomplete(log, code, entries, 'config', 'kjui.config.json', 'default configuration')
  end

  it 'attribute_definitions.json missing (a copy that left its link dangling): in the ledger once' do
    dir = project(dangling_definitions: true)
    layout(dir, 'home')
    log, code, entries = build(dir)
    expect(log).to include('attribute_definitions.json not found')
    expect(code).to eq(0)
    expect(entries.map { |e| e['stage'] }).to eq(['validation']), "#{entries.inspect}\n#{log}"
    expect(log).not_to include('Compose build completed!')
  end

  describe 'stages no real input reached here' do
    before { JsonUI::StageFailures.clear! }
    after { JsonUI::StageFailures.clear! }

    # A cached layout that stops parsing is met first by the data-model stage,
    # which raises (exit 1, measured) — so this is driven directly.
    it 'a cached layout that does not parse: refused and in the ledger' do
      require_relative '../../lib/cli/commands/build'
      Dir.mktmpdir('kjui_cached') do |dir|
        file = File.join(dir, 'home.json')
        File.write(file, '{ "type": ')
        build = KjuiTools::CLI::Commands::Build.new
        allow(KjuiTools::Core::Logger).to receive(:error)
        build.send(:validate_cached_layout, file, file, dir, nil, nil)
        expect(build.instance_variable_get(:@refused_layouts)).to eq([file])
        expect(JsonUI::StageFailures.entries.map { |e| e[:stage] }).to eq(['layout'])
        expect(JsonUI::StageFailures.entries.first[:message]).to include('home.json could not be read')
      end
    end

    it 'a layout whose strings could not be extracted: in the ledger' do
      require_relative '../../lib/core/resources/string_manager'
      Dir.mktmpdir('kjui_str') do |dir|
        layouts = File.join(dir, SRC, 'assets/Layouts')
        FileUtils.mkdir_p(layouts)
        file = File.join(layouts, 'home.json')
        File.write(file, JSON.generate('type' => 'Label', 'text' => 'hi'))
        manager = KjuiTools::Core::Resources::StringManager.new({ 'source_directory' => SRC }, dir, File.join(layouts, 'Resources'))
        allow(manager).to receive(:extract_strings_from_json).and_raise(IOError, 'disk went away')
        %i[error debug info].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
        manager.send(:extract_strings, [file])
        expect(JsonUI::StageFailures.entries.map { |e| e[:stage] }).to eq(['strings'])
        expect(JsonUI::StageFailures.entries.first[:message]).to include('home.json', 'disk went away')
      end
    end
  end
end
