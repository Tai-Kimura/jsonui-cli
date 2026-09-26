# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'digest'
require 'pty'

# `sjui g view / partial / collection / adapter` (SwiftUI, and UIKit on a real
# empty Xcode project) against the disk: each command runs on a new project,
# every file it made is then EDITED (a layout re-serialised, any other file
# given an extra line), and the command runs again over those edits — with a
# closed stdin, with a pipe held open and never written (what an MCP server's
# child and an agent's shell get), answering "n" and "y" on a pseudo-terminal,
# with --skip-existing (the terminal ready to say "y") and with --force (ready
# to say "n"). The authority is the md5 of each file on disk, not anything the
# generator says or records. Every run is killed after RUN_LIMIT_KEEP seconds
# and fails its example as "timeout" instead of hanging the suite.
#
# The one rule (ticket generate-commands-overwrite-edited-files-and-ignore-their-flags):
# a file that is there is the app's — --force and a "y" typed on a terminal
# replace it; "n", --skip-existing and a stdin that is not a terminal keep it,
# and a stdin that is not a terminal is never read (one line names the file and
# --force); both flags are accepted by every command; a UIKit run whose Xcode
# step fails (a raise, or add_file answering :failed) leaves the tree as it was
# and exits non-zero.
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

  # Answers typed on the pseudo-terminal, then end-of-file (^D) for any
  # prompt beyond them.
  def self.typed(answer)
    [:terminal, "#{answer}\n" * 8 + "\x04" * 4]
  end

  # [path, extra arguments, stdin]
  PATHS_KEEP = {
    closed: [[], ''],
    open_pipe: [[], :open_pipe],
    answered_n: [[], typed('n')],
    answered_y: [[], typed('y')],
    skip_existing: [['--skip-existing'], typed('y')],
    force: [['--force'], typed('n')]
  }.freeze

  # A normal run takes a few seconds (UIKit runs the build); a run waiting on
  # stdin is killed here.
  RUN_LIMIT_KEEP = 30

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

  # stdin: a String (written, then closed), :open_pipe (held open and never
  # written), or [:terminal, typed] (a pseudo-terminal). Returns [output, rc],
  # rc :timeout when the run was killed after RUN_LIMIT_KEEP seconds.
  def self.run_g(dir, args, stdin:, env: {})
    cmd = ['ruby', File.join(dir, 'sjui_tools', 'bin', 'sjui'), 'g', *args]
    out = +''
    rc = nil
    if stdin.is_a?(Array)
      PTY.spawn(env, *cmd, chdir: dir) do |r, w, pid|
        w.write(stdin[1])
        rc = drain(r, pid, out) { Process.wait2(pid)[1] }
      end
    else
      Open3.popen2e(env, *cmd, chdir: dir) do |i, o, t|
        unless stdin == :open_pipe
          i.write(stdin)
          i.close
        end
        rc = drain(o, t.pid, out) { t.value }
      end
    end
    [out.force_encoding(Encoding::UTF_8).delete("\r").gsub(/\e\[[0-9;]*m/, ''), rc]
  end

  def self.drain(io, pid, out)
    deadline = Time.now + RUN_LIMIT_KEEP
    loop do
      left = deadline - Time.now
      unless left.positive? && IO.select([io], nil, nil, left)
        Process.kill('KILL', pid)
        yield
        return :timeout
      end
      out << io.readpartial(4096)
    rescue EOFError, Errno::EIO
      break
    end
    yield.exitstatus
  end

  # The whole tree the app owns, for "as it was": every file's md5 (the Xcode
  # project and the binding files included) and every directory.
  def self.tree(dir)
    all = Dir.glob(File.join(dir, '**', '*'), File::FNM_DOTMATCH)
             .reject { |f| f.end_with?('/.', '/..') }.map { |f| f.sub("#{dir}/", '') }
             .reject { |f| f.start_with?('sjui_tools/') || f == 'sjui_tools' }
    { files: all.select { |f| File.file?(File.join(dir, f)) }
                .to_h { |f| [f, Digest::MD5.file(File.join(dir, f)).hexdigest] },
      dirs: all.select { |f| File.directory?(File.join(dir, f)) }.sort }
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

  # The FIRST add_file adds its file (and saves project.pbxproj), the second
  # raises: a failure after the run has changed the project.
  def self.second_fault_file(root)
    path = File.join(root, 'fault_second_add_file.rb')
    File.write(path, <<~RUBY)
      module FaultSecondAddFile
        def add_file(*args)
          $add_file_calls = ($add_file_calls || 0) + 1
          raise('injected: the second add_file failed') if $add_file_calls == 2

          super
        end
      end
      module SjuiTools; module Core; class XcodeProjectManager; prepend FaultSecondAddFile; end; end; end
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
        was = self.class.tree(dir)
        out, rc = self.class.run_g(dir, args, stdin: '', env: fault)
        paths[:fault_again] = { out: out, rc: rc, disk: self.class.disk_files(dir), was: was, is: self.class.tree(dir) }
        dir = File.join(root, 'fault_new')
        self.class.make_project(dir, mode)
        was = self.class.tree(dir)
        out, rc = self.class.run_g(dir, args, stdin: '', env: fault)
        paths[:fault_new] = { out: out, rc: rc, disk: self.class.disk_files(dir), was: was, is: self.class.tree(dir) }
        dir = File.join(root, 'fault_second')
        self.class.make_project(dir, mode)
        was = self.class.tree(dir)
        out, rc = self.class.run_g(dir, args, stdin: '', env: { 'RUBYOPT' => "-r#{self.class.second_fault_file(root)}" })
        paths[:fault_second] = { out: out, rc: rc, was: was, is: self.class.tree(dir) }
        # Not injected: the .xcodeproj directory read-only, so Xcodeproj
        # cannot rename its temp file over project.pbxproj and add_file
        # answers :failed (it rescues its own error).
        dir = File.join(root, 'readonly_project')
        self.class.make_project(dir, mode)
        was = self.class.tree(dir)
        File.chmod(0o555, File.join(dir, 'P.xcodeproj'))
        out, rc = self.class.run_g(dir, args, stdin: '')
        File.chmod(0o755, File.join(dir, 'P.xcodeproj'))
        paths[:readonly_project] = { out: out, rc: rc, disk: self.class.disk_files(dir), was: was, is: self.class.tree(dir) }
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

    it "#{label}: a stdin that is not a terminal is not read — closed, or a pipe held open and never written" do
      run = @runs[label]
      aggregate_failures do
        %i[closed open_pipe].each do |path|
          said = run[:paths][path][:out]
          expect(run[:paths][path][:rc]).to eq(0), "#{path} (rc #{run[:paths][path][:rc]}): #{said}"
          expect(changed(run, path)).to eq([]), "#{path}: #{said}"
          expect(said).not_to include('Overwrite? (y/n)'), path.to_s
          scaffold(run).each do |f|
            expect(said).to match(/Kept existing .*#{Regexp.escape(File.basename(f))} \(stdin is not a terminal; --force replaces it\)/),
                            "#{path}: no line keeps #{f}: #{said}"
          end
        end
      end
    end

    it "#{label}: on a terminal it asks" do
      expect(@runs[label][:paths][:answered_n][:out]).to include('Overwrite? (y/n)')
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
      expect(path[:is]).to eq(path[:was]), path[:out]
    end

    it "#{label}: a raising Xcode step on a new project leaves the tree as it was, exit non-zero" do
      path = @runs[label][:paths][:fault_new]
      expect(path[:rc]).not_to eq(0), path[:out]
      expect(path[:out]).to include('injected: add_file failed')
      expect(path[:out]).to match(/^Created /), path[:out] # the run wrote before the step (the precondition)
      expect(path[:is]).to eq(path[:was]), path[:out]
    end

    unless label == 'uikit partial' # one add_file: no second step to fail
      it "#{label}: a step failing after the project was saved leaves the tree as it was — project.pbxproj too" do
        path = @runs[label][:paths][:fault_second]
        expect(path[:out]).to include('Added to Xcode project'), path[:out] # the first add saved (the precondition)
        expect(path[:rc]).not_to eq(0), path[:out]
        expect(path[:out]).to include('injected: the second add_file failed')
        expect(path[:is]).to eq(path[:was]), path[:out]
      end
    end

    it "#{label}: add_file answering :failed (a read-only .xcodeproj) leaves the tree as it was, exit non-zero" do
      path = @runs[label][:paths][:readonly_project]
      expect(path[:out]).to include('ERROR: Error adding file to Xcode project'), path[:out] # the precondition
      expect(path[:rc]).not_to eq(0), path[:out]
      expect(path[:out]).to include('to the Xcode project'), path[:out]
      expect(path[:is]).to eq(path[:was]), path[:out]
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

  # The Dynamic-mode layout name a nested cell's scaffold carries is the one
  # `sjui build` writes when it rewrites the GeneratedView — the bare name,
  # which SwiftJsonUI finds in the layouts' subdirectories (measured
  # 2026-09-26; ticket dynamic-layout-name-drops-the-subdirectory-of-a-nested-cell).
  describe 'g collection home/item_cell: the Dynamic layout name' do
    it 'is the one sjui build writes' do
      Dir.mktmpdir('sjui_g_dynamic_name') do |dir|
        self.class.make_project(dir, 'swiftui')
        said, rc = self.class.run_g(dir, %w[collection home/item_cell], stdin: '')
        expect(rc).to eq(0), said
        view = File.join(dir, 'P', 'View', 'Home', 'ItemCell', 'ItemCellGeneratedView.swift')
        hook = ->{ File.read(view)[/DynamicView\(jsonName: "([^"]*)"/, 1] }
        scaffolded = hook.call
        built, = Open3.capture2e('ruby', File.join(dir, 'sjui_tools', 'bin', 'sjui'), 'build', chdir: dir, stdin_data: '')
        expect(File.read(view)).to include('Generator: sjui build'), built # the build rewrote it (the precondition)
        expect(scaffolded).to eq(hook.call)
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
