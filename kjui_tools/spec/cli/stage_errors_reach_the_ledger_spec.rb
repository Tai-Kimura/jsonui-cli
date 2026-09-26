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

  def project(dangling_definitions: false, synonyms: nil)
    dir = Dir.mktmpdir('kjui_stage')
    if dangling_definitions
      FileUtils.mkdir_p(File.join(dir, 'kjui_tools'))
      %w[bin lib].each { |d| system('cp', '-R', File.join(KJUI_ROOT, d), File.join(dir, 'kjui_tools')) || raise(d) }
    elsif synonyms
      # The tool copied with its links followed, and type_synonyms.json
      # replaced by `synonyms` — that one table unusable and nothing else.
      FileUtils.mkdir_p(File.join(dir, 'kjui_tools'))
      %w[bin lib].each { |d| system('cp', '-RL', File.join(KJUI_ROOT, d), File.join(dir, 'kjui_tools')) || raise(d) }
      table = File.join(dir, 'kjui_tools', 'lib', 'core', 'type_synonyms.json')
      File.delete(table)
      File.write(table, synonyms)
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

  def expect_incomplete(log, exit_code, entries, stage, *words)
    expect(exit_code).to eq(0), log # the exit is `jui build`'s, from the ledger
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
    log, exit_code, entries = build(dir)
    expect([exit_code, entries]).to eq([0, []]), log
    expect(log).to include('Compose build completed!')
  end

  it 'colors.json that does not parse: already in the ledger, and now the last line says so' do
    dir = project
    layout(dir, 'home')
    FileUtils.mkdir_p(File.join(dir, SRC, 'assets/Layouts/Resources'))
    File.write(File.join(dir, SRC, 'assets/Layouts/Resources/colors.json'), '{ "a": ')
    log, exit_code, entries = build(dir)
    expect_incomplete(log, exit_code, entries, 'colors', 'colors.json could not be parsed')
  end

  it 'a style that does not parse: in the ledger once' do
    dir = project
    File.write(File.join(dir, SRC, 'assets/Layouts/home.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => %w[a b].map { |id| { 'type' => 'Label', 'id' => id, 'text' => id, 'style' => 'broken' } }
    ))
    File.write(File.join(dir, SRC, 'assets/Styles/broken.json'), '{ "fontSize": ')
    log, exit_code, entries = build(dir)
    expect(log).to include('Failed to parse style file')
    expect_incomplete(log, exit_code, entries, 'styles', 'broken.json', 'drawn without it')
  end

  it 'colors.xml with no root element: in the ledger' do
    dir = project
    layout(dir, 'home', 'fontColor' => '#123456')
    FileUtils.mkdir_p(File.join(dir, SRC, 'res/values'))
    File.write(File.join(dir, SRC, 'res/values/colors.xml'), '')
    log, exit_code, entries = build(dir)
    expect(log).to include('Invalid colors.xml structure')
    expect_incomplete(log, exit_code, entries, 'colors', 'colors.xml', 'no root element')
  end

  it 'a layout whose colours could not be written back: in the ledger' do
    dir = project
    layout(dir, 'home', 'fontColor' => '#123456')
    file = File.join(dir, SRC, 'assets/Layouts/home.json')
    FileUtils.chmod(0o444, file)
    skip "#{file} is still writable (running as root?)" if File.writable?(file)
    log, exit_code, entries = build(dir)
    expect_incomplete(log, exit_code, entries, 'colors', 'home.json', 'colour extraction failed')
  end

  it 'kjui.config.json that does not parse: the build on the defaults is named, once for every load' do
    dir = project
    layout(dir, 'home')
    File.write(File.join(dir, 'kjui.config.json'), '{ "mode": ')
    log, exit_code, entries = build(dir)
    expect(log.scan('Error parsing config file').size).to be > 1 # the control: loaded more than once
    expect_incomplete(log, exit_code, entries, 'config', 'kjui.config.json', 'default configuration')
  end

  it 'a Layouts directory that is not there: a named failure, and not created' do
    dir = project
    layouts = File.join(dir, SRC, 'assets/Layouts')
    FileUtils.rm_rf(layouts)
    log, exit_code, = build(dir)
    expect(exit_code).to eq(1), log
    expect(log).to include("Layouts directory not found: #{File.join(File.realpath(dir), SRC, 'assets/Layouts')}")
    expect(Dir.exist?(layouts)).to be(false)
    expect(log).not_to include('No JSON files found')
  end

  it 'no layouts yet: not a failure, but what an earlier stage could not do still reaches the ledger' do
    dir = project
    log, exit_code, entries = build(dir)
    expect(log).to include('No JSON files found')
    expect([exit_code, entries]).to eq([0, []]) # the control: an empty project is not a failure

    # The config fails to parse: the build runs on the defaults, whose Layouts
    # directory is there and empty.
    FileUtils.mkdir_p(File.join(dir, 'src/main/assets/Layouts'))
    File.write(File.join(dir, 'kjui.config.json'), '{ "mode": ')
    log, exit_code, entries = build(dir)
    expect(log).to include('No JSON files found')
    expect(exit_code).to eq(0), log
    expect(entries.map { |e| e['stage'] }).to eq(['config']), "#{entries.inspect}\n#{log}"
    expect(log).to include('Build finished with 1 stage(s) incomplete — see above')
  end

  # Ruled after counting the faces: 2167 style references, 0 to no file —
  # so a missing one is a stage that did not complete. Until 1.8.121 kjui
  # drew the node without it and printed nothing.
  it 'a style that is not there: said, and in the ledger once' do
    dir = project
    File.write(File.join(dir, SRC, 'assets/Layouts/home.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => %w[a b].map { |id| { 'type' => 'Label', 'id' => id, 'text' => id, 'style' => 'absent' } }
    ))
    log, exit_code, entries = build(dir)
    expect(log).to include("Style file 'absent' not found: ")
    expect_incomplete(log, exit_code, entries, 'styles', 'absent.json', 'was not found')
  end

  # A plain `cp -R` of the tool leaves every link into shared/core dangling:
  # attribute_definitions.json and, since 753acb06, type_synonyms.json. Each
  # is a validation stage that did not complete — named where it is met, in
  # the ledger once however often it is met, and the build carries on without
  # it (the exit is `jui build`'s, from the ledger). This build meets each
  # file once even over two layouts (measured), so "once" is not what this
  # arm tests; sjui's UIKit arm, which meets each more than once, is.
  it 'a copy that left its links dangling: attribute_definitions.json and type_synonyms.json in the ledger, each once' do
    dir = project(dangling_definitions: true)
    layout(dir, 'home')
    layout(dir, 'other')
    log, exit_code, entries = build(dir)
    expect(log).to include('attribute_definitions.json not found').and include('type_synonyms.json not found')
    expect(exit_code).to eq(0), log
    expect(entries.map { |e| e['stage'] }).to eq(%w[validation validation]), "#{entries.inspect}\n#{log}"
    messages = entries.map { |e| e['message'] }
    expect(messages.count { |m| m.include?('attribute_definitions.json') }).to eq(1), messages.inspect
    expect(messages.count { |m| m.include?('type_synonyms.json') }).to eq(1), messages.inspect
    expect(log).to include('Build finished with 2 stage(s) incomplete — see above'), log
    expect(log).not_to include('Compose build completed!')
  end

  # A type_synonyms.json that is there but cannot be used — not JSON, or not
  # the declared shape — is the same stage failure as a missing one: named,
  # in the ledger once over two layouts, the build carrying on without it.
  # Until 1.8.121 it raised: the tools said nothing, blamed the layout, or
  # failed every layout (attribute_validator_core.rb#type_synonyms).
  {
    'not JSON' => ['{ "synonyms": ', 'does not parse'],
    'not the declared shape' => ['{ "synonyms": { "Table": "Collection" } }', 'is not the declared shape']
  }.each do |form, (content, says)|
    it "a type_synonyms.json that is #{form}: named, in the ledger once" do
      dir = project(synonyms: content)
      layout(dir, 'home')
      layout(dir, 'other')
      log, exit_code, entries = build(dir)
      expect(exit_code).to eq(0), log
      expect(entries.map { |e| e['stage'] }).to eq(['validation']), "#{entries.inspect}\n#{log}"
      expect(entries.first['message']).to include('type_synonyms.json').and include(says)
      expect(log).to match(/Error\] \S*type_synonyms\.json/), log
      expect(log).to include('Build finished with 1 stage(s) incomplete — see above'), log
      expect(log).not_to include('Compose build completed!')
    end
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
