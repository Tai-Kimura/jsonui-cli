# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'xcodeproj'
require 'core/stage_failures'
require 'core/xcode_project_manager'
require 'core/config_manager'

# An ERROR a build prints is a stage it did not complete: it is in the ledger
# (JUI_STAGE_FAILURES, which `jui build` turns into exit 1) and the build does
# not end in its success line. One arm per stage of `sjui build` that printed
# an error and carried on, each made to fail by a real input.
#
# Until 1.8.121 (measured on 32785ce8, 2026-09-26) each of these ended in
# "Build completed successfully!" / "SwiftUI build completed!" with nothing in
# the ledger — `jui build` exited 0 — and a healthy UIKit build printed
# "ERROR: Removing empty group" and "ERROR: Warning: Creating new group" for
# what the Xcode project manager did on purpose. Under `--mode all` the
# ledger took each entry twice. Ticket
# uikit-build-reports-success-after-a-binding-error.
RSpec.describe 'sjui build: a stage that printed an error is in the ledger' do
  REPO_STAGES = File.expand_path('../../../..', __dir__)
  NAME = 'Probe'

  # The tool is linked, not copied (lib/core/attribute_definitions.json is a
  # relative link into shared/core) — except where the arm is that file
  # missing, where the copy without -L is the input.
  def project(mode, dangling_definitions: false, source_group: true)
    dir = Dir.mktmpdir('sjui_stage')
    if dangling_definitions
      FileUtils.mkdir_p(File.join(dir, 'sjui_tools'))
      %w[bin lib].each { |d| system('cp', '-R', File.join(REPO_STAGES, 'sjui_tools', d), File.join(dir, 'sjui_tools')) || raise(d) }
    else
      FileUtils.ln_s(File.join(REPO_STAGES, 'sjui_tools'), File.join(dir, 'sjui_tools'))
    end
    File.write(File.join(dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => mode, 'project_name' => NAME, 'project_file_name' => NAME, 'source_directory' => NAME,
      'layouts_directory' => 'Layouts', 'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
      'view_directory' => 'View', 'data_directory' => 'Data', 'viewmodel_directory' => 'ViewModel',
      'bindings_directory' => 'Bindings', 'resource_manager_directory' => 'ResourceManager', 'use_network' => true
    ))
    if mode == 'swiftui'
      FileUtils.mkdir_p(File.join(dir, "#{NAME}.xcodeproj"))
    else
      x = Xcodeproj::Project.new(File.join(dir, "#{NAME}.xcodeproj"))
      x.new_target(:application, NAME, :ios, '15.0')
      x.new_group(NAME, NAME) if source_group
      x.save
    end
    %w[Layouts Styles View Bindings].each { |d| FileUtils.mkdir_p(File.join(dir, NAME, d)) }
    @dirs << dir
    dir
  end

  def layout(dir, name, extra = {})
    File.write(File.join(dir, NAME, 'Layouts', "#{name}.json"), JSON.pretty_generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical',
      'child' => [{ 'type' => 'Label', 'id' => 'title', 'text' => 'Hello', 'width' => 'wrapContent', 'height' => 'wrapContent' }.merge(extra)]
    ))
  end

  # [log without colour, exit status, ledger entries]
  def build(dir)
    ledger = File.join(dir, 'ledger.json')
    File.delete(ledger) if File.exist?(ledger)
    log, status = Open3.capture2e({ 'JUI_STAGE_FAILURES' => ledger }, 'ruby', File.join(dir, 'sjui_tools', 'bin', 'sjui'), 'build', chdir: dir)
    [log.gsub(/\e\[[0-9;]*m/, ''), status.exitstatus, File.exist?(ledger) ? JSON.parse(File.read(ledger)) : []]
  end

  # A mode that stops this process writing — unless it is root, for whom it
  # does not, and the arm would then be measuring nothing.
  def read_only(path, mode)
    FileUtils.chmod(mode, path)
    skip "#{path} is still writable (running as root?)" if File.writable?(path)
  end

  def expect_incomplete(log, exit_code, entries, stage, *words)
    expect(exit_code).to eq(0), log # the exit is `jui build`'s, from the ledger
    expect(entries.map { |e| e['stage'] }).to eq([stage]), "#{entries.inspect}\n#{log}"
    words.each { |w| expect(entries.first['message']).to include(w) }
    last = log.lines.map(&:strip).reject(&:empty?)
    expect(log).to include("Build finished with 1 stage(s) incomplete — see above"), log
    expect(last.grep(/completed successfully!|SwiftUI build completed!/)).to be_empty, log
  end

  before(:all) { @dirs = [] }
  after(:all) do
    @dirs.each do |d|
      system('chmod', '-R', 'u+w', d)
      FileUtils.rm_rf(d)
    end
  end

  describe 'UIKit' do
    it 'a binding file it could not write: in the ledger, and not "Build completed successfully!"' do
      dir = project('uikit')
      layout(dir, 'home')
      read_only(File.join(dir, NAME, 'Bindings'), 0o555)
      log, exit_code, entries = build(dir)
      expect(log).to include('Error generating binding file for home')
      expect_incomplete(log, exit_code, entries, 'layout', 'home.json', 'HomeBinding.swift')

      # The next run tries the layout again and says so again.
      log, exit_code, entries = build(dir)
      expect_incomplete(log, exit_code, entries, 'layout', 'home.json')
    end

    it 'says ERROR only for what failed: a project with an empty group and none for the source directory builds clean' do
      dir = project('uikit', source_group: false)
      x = Xcodeproj::Project.open(File.join(dir, "#{NAME}.xcodeproj"))
      x.main_group.new_group('Leftover')
      x.save
      layout(dir, 'home')
      log, exit_code, entries = build(dir)
      # The two it did say, at their level now.
      expect(log).to include('Removing empty group: Leftover').and include("Creating new group '#{NAME}'")
      expect(log.lines.grep(/ERROR/)).to be_empty, log
      expect([exit_code, entries]).to eq([0, []])
      expect(log).to include('Build completed successfully!')
    end

    it 'a binding file written but not added to the Xcode project is in the ledger' do
      JsonUI::StageFailures.clear!
      manager = SjuiTools::Core::XcodeProjectManager.allocate
      manager.instance_variable_set(:@project_path, '/x/Probe.xcodeproj')
      allow(manager).to receive(:add_file).and_return(:added, :failed)
      allow(manager).to receive(:cleanup_empty_groups)
      manager.add_binding_files(%w[/x/AOkBinding.swift /x/BLostBinding.swift], '/x')
      expect(JsonUI::StageFailures.entries).to eq(
        [{ stage: 'Xcode project', message: 'BLostBinding.swift was written but not added to Probe.xcodeproj' }]
      )
    ensure
      JsonUI::StageFailures.clear!
    end

    # The UIKit build loads the definitions twice (measured: two "not found"
    # lines) — the arm where "once" is a claim. kjui and rjui meet it once.
    it 'attribute_definitions.json missing (a copy that left its link dangling): in the ledger once' do
      dir = project('uikit', dangling_definitions: true)
      layout(dir, 'home')
      log, exit_code, entries = build(dir)
      expect(log.scan('attribute_definitions.json not found').size).to be >= 2 # the control: met more than once
      expect_incomplete(log, exit_code, entries, 'validation', 'attribute_definitions.json')
    end

    it 'under --mode all, one failure is one entry in the ledger (the UIKit and the SwiftUI stages each report)' do
      dir = project('uikit')
      File.write(File.join(dir, 'sjui.config.json'), File.read(File.join(dir, 'sjui.config.json')).sub('"uikit"', '"all"'))
      layout(dir, 'home')
      FileUtils.mkdir_p(File.join(dir, NAME, 'Layouts', 'Resources'))
      File.write(File.join(dir, NAME, 'Layouts', 'Resources', 'colors.json'), '{ "a": ')
      log, exit_code, entries = build(dir)
      expect(entries.map { |e| e['stage'] }).to eq(['colors']), "#{entries.inspect}\n#{log}"
      expect(exit_code).to eq(0)
    end
  end

  describe 'SwiftUI' do
    it 'a cached layout that no longer parses: refused, in the ledger' do
      dir = project('swiftui')
      layout(dir, 'home')
      expect(build(dir)[2]).to eq([])
      file = File.join(dir, NAME, 'Layouts', 'home.json')
      stamp = File.mtime(file) - 3600
      File.write(file, '{ "type": ')
      File.utime(stamp, stamp, file) # the cache still takes it as built
      log, exit_code, entries = build(dir)
      expect(log).to include('Invalid JSON in')
      expect_incomplete(log, exit_code, entries, 'layout', 'home.json', 'could not be read')
    end

    it 'a style that does not parse: in the ledger once, however many nodes use it' do
      dir = project('swiftui')
      File.write(File.join(dir, NAME, 'Layouts', 'home.json'), JSON.generate(
        'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
        'child' => %w[a b].map { |id| { 'type' => 'Label', 'id' => id, 'text' => id, 'style' => 'broken' } }
      ))
      File.write(File.join(dir, NAME, 'Styles', 'broken.json'), '{ "fontSize": ')
      log, exit_code, entries = build(dir)
      expect(log.scan('Error parsing style file').size).to be >= 2 # the control: met more than once
      expect_incomplete(log, exit_code, entries, 'styles', 'broken.json', 'drawn without it')
    end

    it 'a generated view it cannot update (no GeneratedView struct in it): in the ledger' do
      dir = project('swiftui')
      layout(dir, 'home')
      expect(build(dir)[2]).to eq([])
      view = Dir.glob(File.join(dir, '**', 'HomeGeneratedView.swift')).first
      File.write(view, "// emptied by hand\n")
      FileUtils.touch(File.join(dir, NAME, 'Layouts', 'home.json'))
      log, exit_code, entries = build(dir)
      expect(log).to include('Could not find struct definition')
      expect_incomplete(log, exit_code, entries, 'layout', 'HomeGeneratedView.swift', 'was not updated')
    end

    it 'a layout whose colours could not be written back: in the ledger' do
      dir = project('swiftui')
      layout(dir, 'home', 'fontColor' => '#123456')
      read_only(File.join(dir, NAME, 'Layouts', 'home.json'), 0o444)
      log, exit_code, entries = build(dir)
      expect_incomplete(log, exit_code, entries, 'colors', 'home.json', 'colour extraction failed')
    end

  end

  describe 'the stages every build reads' do
    before { JsonUI::StageFailures.clear! }
    after { JsonUI::StageFailures.clear! }

    it 'a config that does not parse: the build on the defaults is named, once however often it is loaded' do
      Dir.mktmpdir('sjui_cfg') do |dir|
        path = File.join(dir, 'sjui.config.json')
        File.write(path, '{ "mode": ')
        2.times { expect { SjuiTools::Core::ConfigManager.load_config(path) }.to output(/Failed to parse config file/).to_stdout }
        expect(JsonUI::StageFailures.entries.map { |e| e[:stage] }).to eq(['config'])
        expect(JsonUI::StageFailures.entries.first[:message]).to include('ran on the default configuration')
      end
    end

    it 'a layout whose strings could not be extracted: in the ledger (kjui says ERROR for it)' do
      require 'core/resources/string_manager'
      Dir.mktmpdir('sjui_str') do |dir|
        file = File.join(dir, 'home.json')
        File.write(file, JSON.generate('type' => 'Label', 'text' => 'hi'))
        manager = SjuiTools::Core::Resources::StringManager.allocate
        allow(manager).to receive(:ensure_tmp_directory)
        allow(manager).to receive(:load_extracted_strings).and_return('strings' => {})
        allow(manager).to receive(:save_extracted_strings)
        allow(manager).to receive(:extract_strings_from_json).and_raise(IOError, 'disk went away')
        %i[warn debug info].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
        manager.process_json_files([file])
        expect(JsonUI::StageFailures.entries.map { |e| e[:stage] }).to eq(['strings'])
        expect(JsonUI::StageFailures.entries.first[:message]).to include('home.json', 'disk went away')
      end
    end
  end
end
