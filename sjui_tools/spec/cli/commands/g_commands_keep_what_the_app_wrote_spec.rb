# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'digest'

# `sjui g view / partial / collection / adapter` (SwiftUI, and UIKit on a real
# empty Xcode project) against the disk: each command runs on a new project,
# every file it made is then EDITED (a layout re-serialised, any other file
# given an extra line), and the command runs again over those edits — with a
# closed stdin, answering "n", answering "y", with --skip-existing (stdin
# ready to say "y") and with --force (stdin ready to say "n"). The authority
# is the md5 of each file on disk, not anything the generator says or
# records.
#
# The one rule (ticket generate-commands-overwrite-edited-files-and-ignore-their-flags):
# a file that is there is the app's — a closed stdin, "n" and --skip-existing
# keep it, --force and "y" replace it; both flags are accepted by every
# command; a rollback deletes only what the run created.
#
# Until 1.8.121 (measured on 32785ce8, 2026-09-26): SwiftUI `g collection`
# overwrote all five files on every run (closed stdin and --skip-existing
# too); UIKit `g view` overwrote the ViewController and the layout; `g view`
# refused both flags ("invalid option", exit 1); `g partial`, `g collection`
# and `g adapter` ignored them (partial and UIKit collection kept the file
# under --force, adapter still asked); UIKit `g view` / `g collection`
# deleted every listed file when the Xcode step raised — a ViewModel they had
# kept too; `g binding` wrote nothing, said nothing and exited 0.
RSpec.describe 'sjui g view / partial / collection / adapter keep the files the app wrote' do
  TOOL_ROOT_KEEP = File.expand_path('../../..', __dir__)

  # [label, mode, generate arguments]
  COMMANDS_KEEP = [
    ['swiftui view', 'swiftui', %w[view home]],
    ['swiftui partial', 'swiftui', %w[partial header]],
    ['swiftui collection', 'swiftui', %w[collection item_cell]],
    ['swiftui adapter', 'swiftui', %w[adapter Card]],
    ['uikit view', 'uikit', %w[view home]],
    ['uikit partial', 'uikit', %w[partial header]],
    ['uikit collection', 'uikit', %w[collection Item/Cell]]
  ].freeze

  # [path, extra arguments, stdin]
  PATHS_KEEP = {
    closed: [[], ''],
    answered_n: [[], "n\n" * 8],
    answered_y: [[], "y\n" * 8],
    skip_existing: [['--skip-existing'], "y\n" * 8],
    force: [['--force'], "n\n" * 8]
  }.freeze

  # Files a command patches or creates once and shares with other
  # components; --force is about the command's own scaffold files.
  SHARED_KEEP = /CustomComponentRegistration\.swift\z/.freeze

  def self.make_project(dir, mode)
    tool = File.join(dir, 'sjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(TOOL_ROOT_KEEP, d), tool)
    end
    File.write(File.join(dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => mode, 'project_name' => 'P', 'project_file_name' => 'P', 'source_directory' => 'P',
      'layouts_directory' => 'Layouts', 'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
      'view_directory' => 'View', 'data_directory' => 'Data', 'viewmodel_directory' => 'ViewModel',
      'bindings_directory' => 'Bindings', 'resource_manager_directory' => 'ResourceManager',
      'string_files' => ['P/Localizable.strings'], 'use_network' => true, 'adapter_directory' => 'Extensions/Adapters'
    ))
    FileUtils.mkdir_p(File.join(dir, 'P', 'Layouts'))
    FileUtils.mkdir_p(File.join(dir, 'P', 'Bindings'))
    script = "require 'xcodeproj'; pr = Xcodeproj::Project.new(ARGV[0]); pr.new_target(:application, 'P', :ios); " \
             "pr.main_group.new_group('P', 'P'); pr.save"
    raise 'could not make an Xcode project' unless system('ruby', '-e', script, File.join(dir, 'P.xcodeproj'))
  end

  # md5 of every file the app could own: not the tool copy, its cache, the
  # Xcode project or the binding files `sjui build` rewrites.
  def self.disk_files(dir)
    Dir.glob(File.join(dir, '**', '*'), File::FNM_DOTMATCH).select { |f| File.file?(f) }
       .map { |f| f.sub("#{dir}/", '') }
       .reject { |f| f.start_with?('sjui_tools/', '.sjui_cache/', 'P.xcodeproj/', 'P/Bindings/') || f == 'sjui.config.json' }
       .to_h { |f| [f, Digest::MD5.file(File.join(dir, f)).hexdigest] }
  end

  def self.edit_file(path)
    if path.end_with?('.json')
      File.write(path, JSON.generate(JSON.parse(File.read(path))))
    else
      File.write(path, "#{File.read(path)}\n// edited by the app\n")
    end
  end

  def self.run_g(dir, args, stdin:, env: {})
    out, status = Open3.capture2e(env, 'ruby', File.join(dir, 'sjui_tools', 'bin', 'sjui'), 'g', *args,
                                  chdir: dir, stdin_data: stdin)
    [out.gsub(/\e\[[0-9;]*m/, ''), status.exitstatus]
  end

  # Every XcodeProjectManager#add_file raises: the step the UIKit generators
  # roll back on. (add_file rescues its own errors, so the raise is injected.)
  def self.fault_file(root)
    path = File.join(root, 'fault_add_file.rb')
    File.write(path, <<~RUBY)
      module FaultAddFile
        def add_file(*) = raise('injected: add_file failed')
      end
      module SjuiTools; module Core; class XcodeProjectManager; prepend FaultAddFile; end; end; end
    RUBY
    path
  end

  before(:all) do
    @roots = []
    @runs = COMMANDS_KEEP.to_h do |label, mode, args|
      root = Dir.mktmpdir('sjui_g_keep')
      @roots << root
      base = File.join(root, 'base')
      self.class.make_project(base, mode)
      before = self.class.disk_files(base)
      new_out, new_rc = self.class.run_g(base, args, stdin: '')
      made = (self.class.disk_files(base).keys - before.keys).sort
      made.each { |f| self.class.edit_file(File.join(base, f)) }
      edited = self.class.disk_files(base).slice(*made)

      paths = PATHS_KEEP.to_h do |key, (flags, stdin)|
        dir = File.join(root, key.to_s)
        FileUtils.cp_r(base, dir)
        out, rc = self.class.run_g(dir, args + flags, stdin: stdin)
        [key, { out: out, rc: rc, disk: self.class.disk_files(dir) }]
      end
      if mode == 'uikit'
        fault = { 'RUBYOPT' => "-r#{self.class.fault_file(root)}" }
        dir = File.join(root, 'fault_again')
        FileUtils.cp_r(base, dir)
        out, rc = self.class.run_g(dir, args, stdin: '', env: fault)
        paths[:fault_again] = { out: out, rc: rc, disk: self.class.disk_files(dir) }
        dir = File.join(root, 'fault_new')
        self.class.make_project(dir, mode)
        out, rc = self.class.run_g(dir, args, stdin: '', env: fault)
        paths[:fault_new] = { out: out, rc: rc, disk: self.class.disk_files(dir) }
      end
      [label, { new_out: new_out, new_rc: new_rc, made: made, edited: edited, paths: paths }]
    end
  end

  after(:all) { @roots.each { |root| FileUtils.rm_rf(root) } }

  def changed(run, path)
    run[:made].reject { |f| run[:paths][path][:disk][f] == run[:edited][f] }
  end

  def scaffold(run)
    run[:made].grep_v(SHARED_KEEP)
  end

  COMMANDS_KEEP.each do |label, _mode, _args|
    it "#{label}: the first run makes files (the precondition)" do
      run = @runs[label]
      expect(run[:new_rc]).to eq(0), run[:new_out]
      expect(run[:made]).not_to be_empty, run[:new_out]
    end

    it "#{label}: a closed stdin or \"n\" keeps every file the app edited" do
      run = @runs[label]
      aggregate_failures do
        %i[closed answered_n].each do |path|
          expect(changed(run, path)).to eq([]), "#{path}: #{run[:paths][path][:out]}"
          expect(run[:paths][path][:rc]).to eq(0), "#{path}: #{run[:paths][path][:out]}"
        end
      end
    end

    it "#{label}: --skip-existing keeps them without asking" do
      path = @runs[label][:paths][:skip_existing]
      expect(changed(@runs[label], :skip_existing)).to eq([]), path[:out]
      expect(path[:rc]).to eq(0), path[:out]
      expect(path[:out]).not_to include('Overwrite? (y/n)')
    end

    it "#{label}: --force replaces the scaffold files without asking" do
      run = @runs[label]
      path = run[:paths][:force]
      expect(changed(run, :force).sort).to eq(scaffold(run)), path[:out]
      expect(path[:rc]).to eq(0), path[:out]
      expect(path[:out]).not_to include('Overwrite? (y/n)')
    end

    it "#{label}: \"y\" at the prompt replaces them" do
      run = @runs[label]
      expect(changed(run, :answered_y).sort).to eq(scaffold(run)), run[:paths][:answered_y][:out]
    end

    it "#{label}: takes --force and --skip-existing without an error or a stack trace" do
      aggregate_failures do
        %i[skip_existing force].each do |path|
          said = @runs[label][:paths][path][:out]
          expect(said).not_to match(/invalid option|Traceback|\.rb:\d+:in /), "#{path}: #{said}"
        end
      end
    end
  end

  COMMANDS_KEEP.select { |_, mode, _| mode == 'uikit' }.each do |label, _mode, _args|
    it "#{label}: a failed Xcode step deletes no file that was there before the run" do
      run = @runs[label]
      path = run[:paths][:fault_again]
      expect(path[:rc]).not_to eq(0), path[:out]
      expect(path[:out]).to include('injected: add_file failed')
      expect(run[:made].reject { |f| path[:disk][f] == run[:edited][f] }).to eq([]), path[:out]
    end

    next if label == 'uikit partial' # no rollback: it keeps what it wrote

    it "#{label}: a failed Xcode step deletes the files the run created" do
      path = @runs[label][:paths][:fault_new]
      expect(path[:rc]).not_to eq(0), path[:out]
      expect(path[:out]).to include('injected: add_file failed')
      created_before_the_step = path[:out].scan(/^Created (?:ViewController|collection cell): (\S+)$/).flatten
      expect(created_before_the_step).not_to be_empty, path[:out]
      expect(created_before_the_step.select { |f| File.exist?(f) }).to eq([]), path[:out]
    end
  end

  # SwiftUI `g collection` writes where `g view` does under the same config
  # (the directories `sjui build` reads). Until 1.8.121 it wrote View/,
  # Layouts/, Data/, ViewModel/ whatever the config said.
  describe 'g collection under a config that names its own directories' do
    it 'writes into the directories g view writes into' do
      Dir.mktmpdir('sjui_g_dirs') do |dir|
        self.class.make_project(dir, 'swiftui')
        config = JSON.parse(File.read(File.join(dir, 'sjui.config.json')))
        File.write(File.join(dir, 'sjui.config.json'), JSON.pretty_generate(config.merge(
          'layouts_directory' => 'Screens', 'view_directory' => 'Views', 'data_directory' => 'Models',
          'viewmodel_directory' => 'ViewModels'
        )))
        FileUtils.mkdir_p(File.join(dir, 'P', 'Screens'))
        before = self.class.disk_files(dir).keys
        said, rc = self.class.run_g(dir, %w[view home], stdin: '')
        expect(rc).to eq(0), said
        view_dirs = (self.class.disk_files(dir).keys - before).map { |f| f.split('/')[1] }.uniq.sort
        before = self.class.disk_files(dir).keys
        said, rc = self.class.run_g(dir, %w[collection item_cell], stdin: '')
        expect(rc).to eq(0), said
        cell_dirs = (self.class.disk_files(dir).keys - before).map { |f| f.split('/')[1] }.uniq.sort
        expect(view_dirs).to eq(%w[Models Screens ViewModels Views])
        expect(cell_dirs).to eq(view_dirs), said
      end
    end
  end

  describe 'g binding' do
    it 'says it wrote nothing and does not exit 0 (UIKit)' do
      Dir.mktmpdir('sjui_g_binding') do |dir|
        self.class.make_project(dir, 'uikit')
        before = self.class.disk_files(dir)
        said, rc = self.class.run_g(dir, %w[binding HomeBinding], stdin: '')
        expect(rc).not_to eq(0), said
        expect(said).to include('nothing written')
        expect(self.class.disk_files(dir)).to eq(before)
      end
    end
  end
end
