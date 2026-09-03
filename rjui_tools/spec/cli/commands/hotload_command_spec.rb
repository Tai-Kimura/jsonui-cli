# frozen_string_literal: true

require 'fileutils'
require 'tmpdir'
require 'cli/commands/hotload_command'

# `hotload stop` used to follow its PID-file kill with a name-matching sweep:
#
#     system("pkill -f 'rjui.*hotload.*listen' 2>/dev/null")
#     system("pkill -f 'rjui.*watch' 2>/dev/null")
#
# `pkill -f` matches the whole command line, so the second pattern signals
# ANY process whose command line contains both "rjui" and "watch" — another
# lane's script, an editor task, a tool invoked with that string as an
# argument. It cannot tell whether it owns what it kills.
#
# It read as harmless because it matched nothing: measured on the
# maintainer's machine, both patterns matched 0 processes — while a control
# pattern matched 64. The zero was that day's process list, not a property
# of the patterns. On the same machine and the same day, an outside SIGTERM
# arriving mid-run turned a consumer's E2E suite red three times, and this
# tool ships to every consumer through `jui sync_tool`.
#
# The PID file is the only ownership record this command has: `hotload
# listen` watches directories and binds no port, so there is no listener to
# look up either. No PID file means the owner is unknown, and an unknown
# owner is not something to kill.
RSpec.describe RjuiTools::CLI::Commands::HotloadCommand do
  let(:tmp) { File.realpath(Dir.mktmpdir('rjui_hotload_spec')) }
  let(:pid_file) { described_class::PID_FILE }

  before do
    allow(RjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    %i[info success error warn debug].each do |level|
      allow(RjuiTools::Core::Logger).to receive(level) if RjuiTools::Core::Logger.respond_to?(level)
    end
    @cwd = Dir.pwd
    Dir.chdir(tmp) # PID_FILE is relative to the working directory
  end

  after do
    Dir.chdir(@cwd)
    FileUtils.rm_rf(tmp)
  end

  def stop_command
    described_class.new(['stop'])
  end

  describe 'stop' do
    it 'signals the pid the file names, and removes the file' do
      File.write(pid_file, "4242\n")
      cmd = stop_command
      expect(Process).to receive(:kill).with('TERM', 4242)
      cmd.execute
      expect(File.exist?(pid_file)).to be false
    end

    it 'kills nothing at all when there is no pid file' do
      # The owner is unknown. That is the end of it — the old sweep is what
      # turned "I do not know who owns this" into "kill whatever matches".
      expect(Process).not_to receive(:kill)
      cmd = stop_command
      expect(cmd).not_to receive(:system)
      cmd.execute
    end

    it 'never shells out to a name-matching kill, pid file or not' do
      # The assertion is on the CALL, not on the file's text: a sweep
      # spelled with backticks or spawn would pass a text search of the
      # source while doing exactly what this forbids.
      [nil, "4242\n"].each do |contents|
        File.write(pid_file, contents) if contents
        cmd = stop_command
        allow(Process).to receive(:kill)
        expect(cmd).not_to receive(:system)
        expect(cmd).not_to receive(:spawn)
        expect(cmd).not_to receive(:`)
        cmd.execute
      end
    end

    it 'survives a stale pid file (the process is already gone)' do
      File.write(pid_file, "4242\n")
      allow(Process).to receive(:kill).with('TERM', 4242).and_raise(Errno::ESRCH)
      expect { stop_command.execute }.not_to raise_error
      expect(File.exist?(pid_file)).to be false
    end

    it 'does not treat a garbage pid file as a pid' do
      File.write(pid_file, "not-a-pid\n")
      expect(Process).not_to receive(:kill)
      stop_command.execute
      expect(File.exist?(pid_file)).to be false
    end
  end
end
