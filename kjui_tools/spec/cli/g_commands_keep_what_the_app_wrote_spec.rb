# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'digest'
require 'pty'
require 'rbconfig'

# `kjui g view / partial / collection / adapter` (Compose mode; the XML mode is
# frozen) against the disk: each command runs on a new project, every file it
# made is then EDITED (a layout re-serialised, any other file given an extra
# line), and the command runs again over those edits — with a closed stdin,
# with a pipe held open and never written (what an MCP server's child and an
# agent's shell get), answering "n" and "y" on a pseudo-terminal, with
# --skip-existing (the terminal ready to say "y") and with --force (ready to
# say "n"). The authority is the md5 of each file on disk. Every run is killed
# after run_limit seconds and fails its example as "timeout" instead of
# hanging the suite.
#
# The one rule (ticket generate-commands-overwrite-edited-files-and-ignore-their-flags):
# a file that is there is the app's — --force and a "y" typed on a terminal
# replace it; "n", --skip-existing and a stdin that is not a terminal keep it,
# and a stdin that is not a terminal is never read (one line names the file and
# --force); both flags are accepted by every command; the files and the
# Dynamic layout name `g collection` writes are the ones `kjui build` uses.
#
# Until 1.9.0 (measured on 32785ce8, 2026-09-26): `g view` parsed --force
# and did not read it, and refused --skip-existing ("invalid option", exit 1);
# `g partial`, `g collection` and `g adapter` parsed neither (the files were
# kept under --force, the adapter still asked under --skip-existing); `g
# collection item_cell` wrote item_cellView.kt / item_cellViewModel.kt — and
# `g collection MyProducts/ProductCell` wrote under views/MyProducts/ — where
# `kjui build` did not look: it scaffolded a second set beside them.
RSpec.describe 'kjui g view / partial / collection / adapter keep the files the app wrote' do
  def self.tool_root
    File.expand_path('../..', __dir__)
  end

  # [label, generate arguments]
  def self.commands
    [
      ['view', %w[view home]],
      ['partial', %w[partial header]],
      ['collection', %w[collection item_cell]],
      ['adapter', %w[adapter Card]]
    ]
  end

  # Answers typed on the pseudo-terminal, then end-of-file (^D).
  def self.typed(answer)
    [:terminal, "#{answer}\n" * 8 + "\x04" * 4]
  end

  # {path => [extra arguments, stdin]}
  def self.paths
    {
      closed: [[], ''],
      open_pipe: [[], :open_pipe],
      answered_n: [[], typed('n')],
      answered_y: [[], typed('y')],
      skip_existing: [['--skip-existing'], typed('y')],
      force: [['--force'], typed('n')]
    }
  end

  # A normal run takes about a second; a run waiting on stdin is killed here.
  def self.run_limit
    30
  end

  # Files a command patches, or creates once and shares with other
  # components; --force is about the command's own scaffold files.
  SHARED_FILES_KJUI_KEEP = /(DynamicComponentRegistry|DynamicComponentInitializer)\.kt\z/.freeze

  def self.make_project(dir)
    tool = File.join(dir, 'kjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    File.write(File.join(dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => 'P', 'source_directory' => 'app/src/main',
      'layouts_directory' => 'assets/Layouts', 'styles_directory' => 'assets/Styles',
      'data_directory' => 'kotlin/com/example/app/data', 'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'view_directory' => 'kotlin/com/example/app/views', 'extension_directory' => 'kotlin/com/example/app/extensions',
      'adapter_directory' => 'kotlin/com/example/app/adapters',
      'resource_manager_directory' => 'app/src/main/kotlin/com/kotlinjsonui/generated',
      'package_name' => 'com.example.app', 'string_files' => ['res/values/strings.xml'], 'use_network' => true
    ))
    FileUtils.mkdir_p(File.join(dir, 'app/src/main/assets/Layouts'))
    FileUtils.mkdir_p(File.join(dir, 'app/src/main/assets/Styles'))
  end

  def self.disk_files(dir)
    Dir.glob(File.join(dir, '**', '*'), File::FNM_DOTMATCH).select { |f| File.file?(f) }
       .map { |f| f.sub("#{dir}/", '') }
       .reject { |f| f.start_with?('kjui_tools/', '.kjui_cache/') || f == 'kjui.config.json' }
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
  # rc :timeout when the run was killed after run_limit seconds.
  def self.run_kjui(dir, args, stdin: '')
    # RbConfig.ruby, not `ruby`: the kjui under test runs on the interpreter
    # running this spec. `ruby` from PATH is rbenv's choice — RBENV_VERSION,
    # else the .ruby-version above the child's cwd (a tmpdir: none), else the
    # global — so the 2.6 leg ran the tool on 3.2.2 or on 2.6 depending on the
    # shell it was launched from (measured 2026-09-26 on sjui's spec of this
    # name: with RBENV_VERSION set its children ran 3.2.2 and its 2.6-only
    # failures vanished; unset, they ran 2.6 and failed on the 3.2.2 leg too).
    cmd = [RbConfig.ruby, File.join(dir, 'kjui_tools', 'bin', 'kjui'), *args]
    out = +''
    rc = nil
    if stdin.is_a?(Array)
      PTY.spawn(*cmd, chdir: dir) do |r, w, pid|
        w.write(stdin[1])
        rc = drain(r, pid, out) { Process.wait2(pid)[1] }
      end
    else
      Open3.popen2e(*cmd, chdir: dir) do |i, o, t|
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
    deadline = Time.now + run_limit
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

  before(:all) do
    @roots = []
    @runs = self.class.commands.to_h do |label, args|
      root = Dir.mktmpdir('kjui_g_keep')
      @roots << root
      base = File.join(root, 'base')
      self.class.make_project(base)
      before = self.class.disk_files(base)
      new_out, new_rc = self.class.run_kjui(base, ['g', *args])
      made = (self.class.disk_files(base).keys - before.keys).sort
      made.each { |f| self.class.edit_file(File.join(base, f)) }
      edited = self.class.disk_files(base).slice(*made)

      paths = self.class.paths.to_h do |key, (flags, stdin)|
        dir = File.join(root, key.to_s)
        FileUtils.cp_r(base, dir)
        out, rc = self.class.run_kjui(dir, ['g', *args, *flags], stdin: stdin)
        [key, { out: out, rc: rc, disk: self.class.disk_files(dir) }]
      end
      [label, { new_out: new_out, new_rc: new_rc, made: made, edited: edited, paths: paths }]
    end
  end

  after(:all) { @roots.each { |root| FileUtils.rm_rf(root) } }

  def changed(run, path)
    run[:made].reject { |f| run[:paths][path][:disk][f] == run[:edited][f] }
  end

  def scaffold(run)
    run[:made].grep_v(SHARED_FILES_KJUI_KEEP)
  end

  commands.each do |label, _args|
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

  # The names are the build's: after `g collection`, `kjui build` finds the
  # cell's Kotlin files where the command wrote them, and writes no second
  # set (disk before and after the build; the build is the authority on the
  # names, as it is the one that updates the files).
  describe 'g collection names its files as kjui build does' do
    [['item_cell', 'views/item_cell/ItemCellView.kt'],
     ['MyProducts/ProductCell', 'views/my_products/product_cell/ProductCellView.kt']].each do |name, view|
      it "g collection #{name}: kjui build scaffolds no other Kotlin file for it" do
        Dir.mktmpdir('kjui_g_cell_names') do |dir|
          self.class.make_project(dir)
          said, rc = self.class.run_kjui(dir, ['g', 'collection', name])
          expect(rc).to eq(0), said
          expect(File).to exist(File.join(dir, 'app/src/main/kotlin/com/example/app', view)), said
          before = self.class.disk_files(dir).keys.grep(/\.kt\z/)
          built, = self.class.run_kjui(dir, ['build'])
          added = self.class.disk_files(dir).keys.grep(/\.kt\z/) - before
          expect(added.grep(%r{/(views|viewmodels|data)/})).to eq([]), built
          expect(built).not_to include('its layout moved')
        end
      end
    end

    # The Dynamic-mode layout name: the GeneratedView's `layoutName` is the
    # one `kjui build` writes when it rewrites the file (the path under
    # Layouts/), and the ViewModel's jsonFileName is the same path, as `g
    # view` writes it. Until 1.9.0 the scaffold said "product_cell" (ticket
    # dynamic-layout-name-drops-the-subdirectory-of-a-nested-cell).
    it 'g collection my_products/product_cell: the Dynamic layout name is the one kjui build writes' do
      Dir.mktmpdir('kjui_g_cell_dynamic') do |dir|
        self.class.make_project(dir)
        said, rc = self.class.run_kjui(dir, %w[g collection my_products/product_cell])
        expect(rc).to eq(0), said
        base = File.join(dir, 'app/src/main/kotlin/com/example/app')
        view = File.join(base, 'views/my_products/product_cell/ProductCellGeneratedView.kt')
        name = ->{ File.read(view)[/layoutName = "([^"]*)"/, 1] }
        scaffolded = name.call
        view_model = File.read(File.join(base, 'viewmodels/ProductCellViewModel.kt'))[/jsonFileName = "([^"]*)"/, 1]
        before = File.read(view)
        built, = self.class.run_kjui(dir, ['build'])
        expect(File.read(view)).not_to eq(before), built # the build rewrote it (the precondition)
        expect(scaffolded).to eq(name.call)
        expect(view_model).to eq(name.call)
      end
    end
  end
end
