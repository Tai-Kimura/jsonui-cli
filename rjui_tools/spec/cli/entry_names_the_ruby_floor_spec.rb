# frozen_string_literal: true

require 'open3'
require 'rbconfig'
require 'tmpdir'

# jsonui-cli 1.9.0 drops Ruby 2.6 (ruling 2026-09-26): bin/rjui needs Ruby 3.2
# or later and says so in the first code it runs — one ERROR line naming the
# ruby that ran, instead of a NoMethodError from inside a build. The block is
# the same in bin/sjui, bin/kjui and bin/rjui (jui_tools holds the three to
# one text). Both sides of the boundary, on the real entry:
#
# * this ruby — 3.2 or later on every leg that runs this suite — runs the
#   command and loads the tool;
# * a RUBY_VERSION below 3.2, replaced through RUBYOPT before the entry runs
#   (so this runs on any ruby), stops with the one line and loads nothing of
#   the tool; 3.2.0 and 3.10.0 run — 3.10 is where a string comparison of
#   versions would get it wrong;
# * the real /usr/bin/ruby, where it is below 3.2 (2.6.10 on macOS), stops the
#   same way — which is also what shows the entry still PARSES on a ruby it
#   refuses. Pending where /usr/bin/ruby is absent or 3.2 or later (CI's
#   ubuntu images), and the pending says so.
RSpec.describe 'bin/rjui and the Ruby floor (3.2)' do
  let(:tool) { 'rjui' }
  let(:command) { %w[help] }
  let(:bin) { File.expand_path("../../bin/#{tool}", __dir__) }

  # Runs the entry under *ruby* in an empty directory. The probe prints, at
  # exit, whether the tool's lib (cli/main.rb) was loaded, and — when
  # *fake_version* is given — replaces RUBY_VERSION before the entry runs.
  # Returns [stdout, stderr, status, the directory the entry ran in].
  def run_entry(ruby, fake_version: nil, env: {}, keep_rubyopt: true)
    Dir.mktmpdir("#{tool}_ruby_floor") do |dir|
      probe = File.join(dir, 'floor_probe.rb')
      lines = []
      if fake_version
        lines << 'Object.send(:remove_const, :RUBY_VERSION)'
        lines << "Object.const_set(:RUBY_VERSION, #{fake_version.inspect}.dup.freeze)"
      end
      lines << "at_exit { $stderr.puts \"LOADED_LIB=\#{$LOADED_FEATURES.any? { |f| f.end_with?('/cli/main.rb') }}\" }"
      File.write(probe, lines.join("\n") + "\n")
      rubyopt = [keep_rubyopt ? ENV['RUBYOPT'] : nil, "-r#{probe}"].compact.join(' ')
      child_env = { 'RBENV_VERSION' => nil }.merge(env).merge('RUBYOPT' => rubyopt)
      stdout, stderr, status = Open3.capture3(child_env, ruby, bin, *command, chdir: dir, stdin_data: '')
      return [stdout, stderr, status, File.realpath(dir)]
    end
  end

  def floor_lines(stderr)
    stderr.lines.map(&:chomp).select { |l| l.include?('needs Ruby 3.2 or later') }
  end

  def expect_stopped(stdout, stderr, status, version:, at:, dir:)
    expect(status.exitstatus).to eq(1), stderr
    expect(stdout).to eq('')
    said = floor_lines(stderr)
    expect(said.size).to eq(1), stderr
    expect(said.first).to start_with(
      "ERROR: #{tool} needs Ruby 3.2 or later (jsonui-cli 1.9.0), and this is Ruby #{version} at #{at}"
    )
    expect(said.first).to include("Put a .ruby-version naming Ruby 3.2 or later in #{dir} ")
    expect(stderr).to include('LOADED_LIB=false')
    said.first
  end

  it 'runs the command on this ruby (3.2 or later) and loads the tool' do
    expect(Gem::Version.new(RUBY_VERSION)).to be >= Gem::Version.new('3.2')
    stdout, stderr, status, = run_entry(RbConfig.ruby)
    expect(status.exitstatus).to eq(0), stdout + stderr
    expect(floor_lines(stderr)).to be_empty
    expect(stderr).to include('LOADED_LIB=true')
  end

  %w[2.6.10 3.1.9].each do |version|
    it "stops Ruby #{version} with one line naming it, before loading the tool" do
      stdout, stderr, status, dir = run_entry(RbConfig.ruby, fake_version: version)
      expect_stopped(stdout, stderr, status, version: version, at: RbConfig.ruby, dir: dir)
    end
  end

  %w[3.2.0 3.10.0].each do |version|
    it "runs Ruby #{version}" do
      stdout, stderr, status, = run_entry(RbConfig.ruby, fake_version: version)
      expect(status.exitstatus).to eq(0), stdout + stderr
      expect(floor_lines(stderr)).to be_empty
      expect(stderr).to include('LOADED_LIB=true')
    end
  end

  # What RBENV_VERSION says beside it: a version rbenv chose, or a pin rbenv
  # did not act on (jui passes the tool's .ruby-version as RBENV_VERSION; with
  # no rbenv in front of PATH the ruby that runs is PATH's).
  {
    'system' => ' (rbenv chose system)',
    '2.6.10' => ' (rbenv chose 2.6.10)',
    '3.2.2' => ' (RBENV_VERSION=3.2.2, but rbenv did not start this ruby)'
  }.each do |rbenv_version, note|
    it "says what RBENV_VERSION=#{rbenv_version} means for the ruby that ran" do
      stdout, stderr, status, dir = run_entry(RbConfig.ruby, fake_version: '2.6.10',
                                                             env: { 'RBENV_VERSION' => rbenv_version })
      line = expect_stopped(stdout, stderr, status, version: '2.6.10', at: RbConfig.ruby, dir: dir)
      expect(line).to include("at #{RbConfig.ruby}#{note}. Put")
    end
  end

  it 'stops the real /usr/bin/ruby when it is below 3.2' do
    system_ruby = '/usr/bin/ruby'
    skip "#{system_ruby} is absent here" unless File.executable?(system_ruby)
    clean = { 'RUBYOPT' => nil, 'RUBYLIB' => nil, 'BUNDLE_GEMFILE' => nil, 'BUNDLE_BIN_PATH' => nil,
              'GEM_HOME' => nil, 'GEM_PATH' => nil, 'RBENV_VERSION' => nil }
    # Asked from an empty directory, as the entry is run. On CI's ubuntu-24.04
    # (2026-09-27) the question asked from the tool's directory made the system
    # ruby (3.2.3) load Bundler for the tool's Gemfile, fail on the gems it
    # does not have and print nothing, while the entry run from an empty
    # directory with the same environment did not. An answer that is not a
    # version is a failed question, not a ruby below 3.2 — Gem::Version.new(nil)
    # is 0, which ran the stop on a 3.2 ruby and failed there.
    facts, said, asked = Dir.mktmpdir("#{tool}_ruby_version") do |dir|
      Open3.capture3(clean, system_ruby, '-rrbconfig', '-e', 'print RUBY_VERSION, " ", RbConfig.ruby', chdir: dir)
    end
    version, real_path = facts.split(' ', 2)
    unless asked.success? && version.to_s.match?(/\A\d+\.\d+/)
      raise "#{system_ruby} did not say its version (exit #{asked.exitstatus}, stdout #{facts.inspect}): #{said}"
    end
    skip "#{system_ruby} is Ruby #{version}, not below 3.2" if Gem::Version.new(version) >= Gem::Version.new('3.2')

    stdout, stderr, status, dir = run_entry(system_ruby, env: clean, keep_rubyopt: false)
    expect_stopped(stdout, stderr, status, version: version, at: real_path, dir: dir)
  end
end
