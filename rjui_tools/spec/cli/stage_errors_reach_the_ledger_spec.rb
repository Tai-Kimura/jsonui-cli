# frozen_string_literal: true

require 'open3'
require 'rbconfig'
require 'tmpdir'
require 'json'
require 'fileutils'
require_relative '../../lib/core/stage_failures'

# An ERROR a build prints is a stage it did not complete: it is in the ledger
# (JUI_STAGE_FAILURES, which `jui build` turns into exit 1) and the build does
# not end in "Build completed!". One arm per stage of `rjui build` that
# printed an error and carried on, each made to fail by a real input where
# one reaches it.
#
# Until 1.8.121 (measured on 32785ce8, 2026-09-26) each of these ended in
# "[SUCCESS] Build completed!" with nothing in the ledger; a style that did
# not parse said "Error parsing style file" on one path and nothing at all on
# the converters' own. Ticket uikit-build-reports-success-after-a-binding-error.
RSpec.describe 'rjui build: a stage that printed an error is in the ledger' do
  RJUI_ROOT = File.expand_path('../..', __dir__)

  def project(dangling_definitions: false)
    dir = Dir.mktmpdir('rjui_stage')
    if dangling_definitions
      FileUtils.mkdir_p(File.join(dir, 'rjui_tools'))
      %w[bin lib].each { |d| system('cp', '-R', File.join(RJUI_ROOT, d), File.join(dir, 'rjui_tools')) || raise(d) }
    else
      FileUtils.ln_s(RJUI_ROOT, File.join(dir, 'rjui_tools'))
    end
    FileUtils.mkdir_p(File.join(dir, 'src/Layouts'))
    FileUtils.mkdir_p(File.join(dir, 'src/Styles'))
    @dirs << dir
    dir
  end

  def layout(dir, name, extra = {})
    File.write(File.join(dir, 'src/Layouts', "#{name}.json"), JSON.pretty_generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical',
      'child' => [{ 'type' => 'Label', 'id' => 'title', 'text' => 'Hello', 'width' => 'wrapContent', 'height' => 'wrapContent' }.merge(extra)]
    ))
  end

  def build(dir)
    ledger = File.join(dir, 'ledger.json')
    log, status = Open3.capture2e({ 'JUI_STAGE_FAILURES' => ledger }, RbConfig.ruby, File.join(dir, 'rjui_tools', 'bin', 'rjui'), 'build', chdir: dir)
    [log.gsub(/\e\[[0-9;]*m/, ''), status.exitstatus, File.exist?(ledger) ? JSON.parse(File.read(ledger)) : []]
  end

  def expect_incomplete(log, exit_code, entries, stages, *words)
    expect(exit_code).to eq(0), log # the exit is `jui build`'s, from the ledger
    expect(entries.map { |e| e['stage'] }).to eq(Array(stages)), "#{entries.inspect}\n#{log}"
    words.each { |w| expect(entries.map { |e| e['message'] }.join("\n")).to include(w) }
    expect(log).to include("Build finished with #{Array(stages).size} stage(s) incomplete — see above"), log
    expect(log).not_to include('Build completed!')
  end

  before(:all) { @dirs = [] }
  after(:all) do
    @dirs.each do |d|
      system('chmod', '-R', 'u+w', d)
      FileUtils.rm_rf(d)
    end
  end

  it 'a healthy build still ends "Build completed!" with an empty ledger (the control)' do
    dir = project
    layout(dir, 'home')
    log, exit_code, entries = build(dir)
    expect([exit_code, entries]).to eq([0, []]), log
    expect(log).to include('Build completed!')
  end

  it 'the ViewModels it could not generate: in the ledger' do
    dir = project
    layout(dir, 'home')
    File.write(File.join(dir, 'src/viewmodels'), 'a file where the directory goes')
    log, exit_code, entries = build(dir)
    expect(log).to include('Error generating viewmodels')
    expect_incomplete(log, exit_code, entries, 'viewmodels', 'the ViewModels were not generated')
  end

  it 'the Data models, which stop at the first layout they cannot read: in the ledger beside that layout' do
    dir = project
    layout(dir, 'home')
    File.write(File.join(dir, 'src/Layouts/bad.json'), '{ "type": ')
    log, exit_code, entries = build(dir)
    expect(log).to include('Error generating data models')
    expect_incomplete(log, exit_code, entries, ['data models', 'layout'], 'the Data models were not generated', 'bad.json')
  end

  it 'a style that does not parse: in the ledger once' do
    dir = project
    layout(dir, 'home', 'style' => 'broken')
    File.write(File.join(dir, 'src/Styles/broken.json'), '{ "fontSize": ')
    log, exit_code, entries = build(dir)
    expect(log).to include('Error parsing style file')
    # The file is there: it is not "not found" (it was, after its parse error, until 1.8.121).
    expect(log).not_to include("Style file 'broken' not found")
    expect_incomplete(log, exit_code, entries, 'styles', 'broken.json', 'drawn without it')
  end

  it 'a style that is not there is still said to be not found (the other side of the line above)' do
    dir = project
    layout(dir, 'home', 'style' => 'absent')
    log, exit_code, entries = build(dir)
    expect(log).to include("Style file 'absent' not found")
    expect([exit_code, entries]).to eq([0, []])
  end

  it 'no layouts yet: not a failure, but what an earlier stage could not do still reaches the ledger' do
    dir = project
    log, exit_code, entries = build(dir)
    expect(log).to include('No JSON layout files found')
    expect([exit_code, entries]).to eq([0, []]) # the control: an empty project is not a failure

    # The Data-model stage runs before the layouts are counted.
    FileUtils.rm_rf(File.join(dir, 'src/generated/data'))
    File.write(File.join(dir, 'src/generated/data'), 'a file where the directory goes')
    log, exit_code, entries = build(dir)
    expect(log).to include('No JSON layout files found')
    expect_incomplete(log, exit_code, entries, 'data models', 'the Data models were not generated')
  end

  it 'a layout whose colours could not be written back: in the ledger' do
    dir = project
    layout(dir, 'home', 'fontColor' => '#123456')
    file = File.join(dir, 'src/Layouts/home.json')
    FileUtils.chmod(0o444, file)
    skip "#{file} is still writable (running as root?)" if File.writable?(file)
    log, exit_code, entries = build(dir)
    expect_incomplete(log, exit_code, entries, 'colors', 'home.json', 'colour extraction failed')
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
    expect(log).not_to include('Build completed!')
  end

  describe 'stages driven directly' do
    before { JsonUI::StageFailures.clear! }
    after { JsonUI::StageFailures.clear! }

    it 'the ViewModel hooks it could not generate: in the ledger' do
      require_relative '../../lib/cli/commands/build_command'
      Dir.mktmpdir('rjui_hooks') do |dir|
        Dir.chdir(dir) do
          FileUtils.mkdir_p('src/viewmodels')
          File.write('src/viewmodels/HomeViewModel.ts', '')
          command = RjuiTools::CLI::Commands::BuildCommand.new([])
          allow_any_instance_of(RjuiTools::React::HookGenerator).to receive(:generate_hooks).and_raise(IOError, 'disk went away')
          %i[info error].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
          command.send(:generate_hooks)
        end
      end
      expect(JsonUI::StageFailures.entries.map { |e| e[:stage] }).to eq(['hooks'])
      expect(JsonUI::StageFailures.entries.first[:message]).to include('disk went away')
    end

    # The two loaders spell the path differently (the build's is absolute,
    # the converters' relative to the project); a style both of them meet is
    # one failure.
    it 'one style, met by both loaders under their two spellings of its path, is one entry' do
      Dir.mktmpdir('rjui_two') do |dir|
        Dir.chdir(dir) do
          FileUtils.mkdir_p('src/Styles')
          error = JSON::ParserError.new('unexpected end of input')
          require_relative '../../lib/react/style_loader'
          RjuiTools::React::StyleLoader.unparsed_style('src/Styles/broken.json', error)
          RjuiTools::React::StyleLoader.unparsed_style(File.join(Dir.pwd, 'src/Styles/broken.json'), error)
        end
      end
      expect(JsonUI::StageFailures.entries.size).to eq(1), JsonUI::StageFailures.entries.inspect
    end

    # The converters load a node's style themselves (BaseConverter#load_style);
    # until 1.8.121 that path returned nil for a style that did not parse and
    # printed nothing.
    it "the converters' own style loader names a style that does not parse" do
      require_relative '../../lib/react/converters/base_converter'
      Dir.mktmpdir('rjui_style') do |dir|
        File.write(File.join(dir, 'broken.json'), '{ "fontSize": ')
        converter = RjuiTools::React::Converters::BaseConverter.new({ 'type' => 'Label' }, { 'styles_directory' => dir })
        expect(converter.send(:load_style, 'broken')).to be_nil
        expect(JsonUI::StageFailures.entries.map { |e| e[:stage] }).to eq(['styles'])
        expect(JsonUI::StageFailures.entries.first[:message]).to include(File.join(File.realpath(dir), 'broken.json')).or include(File.join(dir, 'broken.json'))
      end
    end
  end
end
