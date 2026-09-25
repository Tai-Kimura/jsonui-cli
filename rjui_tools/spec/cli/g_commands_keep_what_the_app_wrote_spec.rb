# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'digest'

# `rjui g view / component / collection` against the disk: each command runs
# on a new project, every file it made is then EDITED (a layout re-serialised,
# any other file given an extra line), and the command runs again over those
# edits — with a closed stdin, answering "n", answering "y", with
# --skip-existing (stdin ready to say "y") and with --force (stdin ready to
# say "n"). The authority is the md5 of each file on disk.
#
# The one rule (ticket generate-commands-overwrite-edited-files-and-ignore-their-flags):
# a file that is there is the app's — a closed stdin, "n" and --skip-existing
# keep it, --force and "y" replace it; both flags are accepted by every
# command; an option a command does not declare, and a missing name, are one
# line and exit 1.
#
# Until 1.8.121 (measured on 32785ce8, 2026-09-26): `g view` and `g component`
# ended in an OptionParser::InvalidOption stack trace on --force and on
# --skip-existing; `g collection` ignored both; a missing name said so and
# exited 0.
RSpec.describe 'rjui g view / component / collection keep the files the app wrote' do
  def self.tool_root
    File.expand_path('../..', __dir__)
  end

  # [label, generate arguments]
  def self.commands
    [
      ['view', %w[view home]],
      ['component', %w[component Card]],
      ['collection', %w[collection item_cell]]
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

  # No rjui.config.json: rjui writes its defaults, as the other CLI specs.
  def self.make_project(dir)
    tool = File.join(dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    FileUtils.mkdir_p(File.join(dir, 'src', 'Layouts'))
  end

  def self.disk_files(dir)
    Dir.glob(File.join(dir, '**', '*'), File::FNM_DOTMATCH).select { |f| File.file?(f) }
       .map { |f| f.sub("#{dir}/", '') }
       .reject { |f| f.start_with?('rjui_tools/') || f == 'rjui.config.json' }
       .to_h { |f| [f, Digest::MD5.file(File.join(dir, f)).hexdigest] }
  end

  def self.edit_file(path)
    if path.end_with?('.json')
      File.write(path, JSON.generate(JSON.parse(File.read(path))))
    else
      File.write(path, "#{File.read(path)}\n// edited by the app\n")
    end
  end

  def self.run_rjui(dir, args, stdin: '')
    out, status = Open3.capture2e('ruby', File.join(dir, 'rjui_tools', 'bin', 'rjui'), *args,
                                  chdir: dir, stdin_data: stdin)
    [out.gsub(/\e\[[0-9;]*m/, ''), status.exitstatus]
  end

  before(:all) do
    @roots = []
    @runs = self.class.commands.to_h do |label, args|
      root = Dir.mktmpdir('rjui_g_keep')
      @roots << root
      base = File.join(root, 'base')
      self.class.make_project(base)
      before = self.class.disk_files(base)
      new_out, new_rc = self.class.run_rjui(base, ['g', *args])
      made = (self.class.disk_files(base).keys - before.keys).sort
      made.each { |f| self.class.edit_file(File.join(base, f)) }
      edited = self.class.disk_files(base).slice(*made)

      paths = self.class.paths.to_h do |key, (flags, stdin)|
        dir = File.join(root, key.to_s)
        FileUtils.cp_r(base, dir)
        out, rc = self.class.run_rjui(dir, ['g', *args, *flags], stdin: stdin)
        [key, { out: out, rc: rc, disk: self.class.disk_files(dir) }]
      end
      [label, { new_out: new_out, new_rc: new_rc, made: made, edited: edited, paths: paths }]
    end
  end

  after(:all) { @roots.each { |root| FileUtils.rm_rf(root) } }

  def changed(run, path)
    run[:made].reject { |f| run[:paths][path][:disk][f] == run[:edited][f] }
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

    it "#{label}: --force replaces them without asking" do
      run = @runs[label]
      path = run[:paths][:force]
      expect(changed(run, :force).sort).to eq(run[:made]), path[:out]
      expect(path[:rc]).to eq(0), path[:out]
      expect(path[:out]).not_to include('Overwrite? (y/n)')
    end

    it "#{label}: \"y\" at the prompt replaces them" do
      run = @runs[label]
      expect(changed(run, :answered_y).sort).to eq(run[:made]), run[:paths][:answered_y][:out]
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

  describe 'what a run that cannot do its job says' do
    it 'an option the command does not declare: one line, exit 1, no stack trace' do
      Dir.mktmpdir('rjui_g_opts') do |dir|
        self.class.make_project(dir)
        said, rc = self.class.run_rjui(dir, %w[g view home --bogus])
        expect(rc).to eq(1), said
        expect(said).to include('invalid option: --bogus')
        expect(said).not_to match(/\.rb:\d+:in /)
        expect(self.class.disk_files(dir)).to be_empty
      end
    end

    it 'a missing name: exit 1' do
      Dir.mktmpdir('rjui_g_opts') do |dir|
        self.class.make_project(dir)
        %w[view component collection].each do |type|
          said, rc = self.class.run_rjui(dir, ['g', type])
          expect(rc).to eq(1), "#{type}: #{said}"
          expect(said).to include('Name is required')
        end
      end
    end
  end
end
