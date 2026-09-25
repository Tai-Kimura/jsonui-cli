# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'digest'

# `kjui g view / partial / collection / adapter` (Compose mode; the XML mode is
# frozen) against the disk: each command runs on a new project, every file it
# made is then EDITED (a layout re-serialised, any other file given an extra
# line), and the command runs again over those edits — with a closed stdin,
# answering "n", answering "y", with --skip-existing (stdin ready to say "y")
# and with --force (stdin ready to say "n"). The authority is the md5 of each
# file on disk.
#
# The one rule (ticket generate-commands-overwrite-edited-files-and-ignore-their-flags):
# a file that is there is the app's — a closed stdin, "n" and --skip-existing
# keep it, --force and "y" replace it; both flags are accepted by every
# command; the files `g collection` writes are the ones `kjui build` looks for.
#
# Until 1.8.121 (measured on 32785ce8, 2026-09-26): `g view` parsed --force
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

  # {path => [extra arguments, stdin]}
  def self.paths
    {
      closed: [[], ''],
      answered_n: [[], "n\n" * 8],
      answered_y: [[], "y\n" * 8],
      skip_existing: [['--skip-existing'], "y\n" * 8],
      force: [['--force'], "n\n" * 8]
    }
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

  def self.run_kjui(dir, args, stdin: '')
    out, status = Open3.capture2e('ruby', File.join(dir, 'kjui_tools', 'bin', 'kjui'), *args,
                                  chdir: dir, stdin_data: stdin)
    [out.gsub(/\e\[[0-9;]*m/, ''), status.exitstatus]
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
  end
end
