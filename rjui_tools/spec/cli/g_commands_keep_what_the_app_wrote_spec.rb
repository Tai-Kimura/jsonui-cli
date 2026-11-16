# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'digest'
require 'pty'
require 'rbconfig'

# `rjui g view / component / collection` against the disk: each command runs
# on a new project, every file it made is then EDITED (a layout re-serialised,
# any other file given an extra line), and the command runs again over those
# edits — with a closed stdin, with a pipe held open and never written (what
# an MCP server's child and an agent's shell get), answering "n" and "y" on a
# pseudo-terminal, with --skip-existing (the terminal ready to say "y") and
# with --force (ready to say "n"). The authority is the md5 of each file on
# disk. Every run is killed after run_limit seconds and fails its example as
# "timeout" instead of hanging the suite.
#
# The one rule (ticket generate-commands-overwrite-edited-files-and-ignore-their-flags):
# a file that is there is the app's — --force and a "y" typed on a terminal
# replace it; "n", --skip-existing and a stdin that is not a terminal keep it,
# and a stdin that is not a terminal is never read (one line names the file and
# --force); both flags are accepted by every command; an option a command does
# not declare, and a missing name, are one line and exit 1.
#
# Until 1.9.0 (measured on 32785ce8, 2026-09-26): `g view` and `g component`
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

  # A normal run takes well under a second; a run waiting on stdin is killed
  # here.
  def self.run_limit
    30
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

  # stdin: a String (written, then closed), :open_pipe (held open and never
  # written), or [:terminal, typed] (a pseudo-terminal). Returns [output, rc],
  # rc :timeout when the run was killed after run_limit seconds.
  def self.run_rjui(dir, args, stdin: '')
    # RbConfig.ruby, not `ruby`: the rjui under test runs on the interpreter
    # running this spec. `ruby` from PATH is rbenv's choice — RBENV_VERSION,
    # else the .ruby-version above the child's cwd (a tmpdir: none), else the
    # global — so the 2.6 leg ran the tool on 3.2.2 or on 2.6 depending on the
    # shell it was launched from (measured 2026-09-26 on sjui's spec of this
    # name: with RBENV_VERSION set its children ran 3.2.2 and its 2.6-only
    # failures vanished; unset, they ran 2.6 and failed on the 3.2.2 leg too).
    cmd = [RbConfig.ruby, File.join(dir, 'rjui_tools', 'bin', 'rjui'), *args]
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

    it "#{label}: a stdin that is not a terminal is not read — closed, or a pipe held open and never written" do
      run = @runs[label]
      aggregate_failures do
        %i[closed open_pipe].each do |path|
          said = run[:paths][path][:out]
          expect(run[:paths][path][:rc]).to eq(0), "#{path} (rc #{run[:paths][path][:rc]}): #{said}"
          expect(changed(run, path)).to eq([]), "#{path}: #{said}"
          expect(said).not_to include('Overwrite? (y/n)'), path.to_s
          run[:made].each do |f|
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
