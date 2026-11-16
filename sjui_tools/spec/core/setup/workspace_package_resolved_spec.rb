# frozen_string_literal: true

require 'fileutils'
require 'json'
require 'tmpdir'
require 'core/setup/workspace_package_resolved'
require 'core/setup/common_setup'
require 'core/setup/library_setup'

# The workspace `Package.resolved` (filed 2026-09-10,
# sjui-setup-writes-an-empty-package-resolved-…). setup wrote
# `{"object":{"pins":[]},"version":1}` — 52 bytes, byte-identical on two
# faces — behind an `unless File.exist?`, so `xcodebuild -project` baked the
# project copy's 20 pins while opening the .xcworkspace resolved from zero.
# Both builds succeed and nothing prints a version, so the split has no
# instrument of its own.
#
# ⚠️ Two halves, and the second is the one that can go silently green.
# "Stop creating it" is visible on a fresh tree. "Reclaim the one already
# there" is invisible on a tree that has none — which is every fixture that
# does not deliberately place one. So the arms below count the SIDE EFFECT
# (`filled` / `removed`) rather than asking whether the file looks right
# afterwards: a run that deleted the shell and wrote a new empty one leaves
# exactly the state a final-state check accepts.
RSpec.describe SjuiTools::Core::Setup::WorkspacePackageResolved do
  subject(:mod) { described_class }

  around do |example|
    Dir.mktmpdir do |dir|
      @root = dir
      @project = File.join(dir, 'App.xcodeproj')
      @workspace = File.join(dir, 'App.xcworkspace')
      FileUtils.mkdir_p(File.join(@workspace, 'xcshareddata', 'swiftpm'))
      example.run
    end
  end

  def shell_path
    File.join(@workspace, 'xcshareddata', 'swiftpm', 'Package.resolved')
  end

  def project_path
    File.join(@project, 'project.xcworkspace', 'xcshareddata', 'swiftpm', 'Package.resolved')
  end

  def write_shell(content)
    File.write(shell_path, content)
  end

  def write_project_copy(pins)
    FileUtils.mkdir_p(File.dirname(project_path))
    File.write(project_path, JSON.pretty_generate(
      'pins' => Array.new(pins) { |i| { 'identity' => "dep#{i}" } }, 'version' => 3))
  end

  # The exact bytes the faces have — a LITERAL, not a re-generation.
  # `JSON.pretty_generate` renders an empty array differently across the
  # json gem versions these suites run on: 52 bytes under Ruby 3.2, 58 under
  # the 2.6 leg (`"pins": [\n\n    ]`). A specimen built by calling the
  # generator is a specimen of THIS ruby, and pinning its size passed six
  # green examples on 3.2 and went red on 2.6.
  #
  # ⚠️ Which also says something about the product: a shell written by a
  # setup run under 2.6 is not byte-identical to one written under 3.2, so
  # the filer's md5 identifies a shell AND the ruby that wrote it. Detection
  # here is by parsed pin count, which covers both forms — see the arm that
  # feeds it each of them.
  EMPTY_V1 = %({\n  "object": {\n    "pins": []\n  },\n  "version": 1\n})
  EMPTY_V1_RUBY26 = %({\n  "object": {\n    "pins": [\n\n    ]\n  },\n  "version": 1\n})

  describe '.pin_count' do
    it 'reads version 1, where the pins hang under "object"' do
      write_shell(JSON.pretty_generate('object' => { 'pins' => [{ 'a' => 1 }] }, 'version' => 1))
      expect(mod.pin_count(shell_path)).to eq(1)
    end

    it 'reads version 3, where the pins are at the top level' do
      write_shell(JSON.pretty_generate('pins' => [{ 'a' => 1 }, { 'b' => 2 }], 'version' => 3))
      expect(mod.pin_count(shell_path)).to eq(2)
    end

    it 'counts the faces\' shell as empty, in both bytes it comes in' do
      write_shell(EMPTY_V1)
      expect(mod.pin_count(shell_path)).to eq(0)
      expect(File.size(shell_path)).to eq(52)

      write_shell(EMPTY_V1_RUBY26)
      expect(mod.pin_count(shell_path)).to eq(0)
      expect(File.size(shell_path)).to eq(58)
    end

    it 'answers nil, not 0, when the file is absent or unreadable' do
      expect(mod.pin_count(shell_path)).to be_nil
      write_shell('not json at all')
      expect(mod.pin_count(shell_path)).to be_nil
    end
  end

  describe '.reclaim' do
    it 'fills an empty shell from the project copy and says how many' do
      write_shell(EMPTY_V1)
      write_project_copy(20)
      outcome = mod.reclaim(@workspace, @project)
      expect([outcome.filled, outcome.removed, outcome.kept]).to eq([1, 0, 0])
      expect(outcome.pins).to eq(20)
      expect(File.read(shell_path)).to eq(File.read(project_path))
    end

    it 'removes an empty shell when there is no project copy to fill it from' do
      write_shell(EMPTY_V1)
      outcome = mod.reclaim(@workspace, @project)
      expect([outcome.filled, outcome.removed, outcome.kept]).to eq([0, 1, 0])
      expect(File.exist?(shell_path)).to be false
    end

    it 'removes an empty shell when the project copy is empty too' do
      write_shell(EMPTY_V1)
      write_project_copy(0)
      outcome = mod.reclaim(@workspace, @project)
      expect(outcome.removed).to eq(1)
      expect(File.exist?(shell_path)).to be false
    end

    # The negative control: a file with real pins is somebody's work.
    it 'leaves a file that has pins exactly as it found it' do
      real = JSON.pretty_generate('pins' => [{ 'identity' => 'firebase' }], 'version' => 3)
      write_shell(real)
      write_project_copy(20)
      outcome = mod.reclaim(@workspace, @project)
      expect([outcome.filled, outcome.removed, outcome.kept]).to eq([0, 0, 1])
      expect(File.read(shell_path)).to eq(real)
    end

    it 'leaves a file it cannot parse, rather than deleting what it cannot judge' do
      write_shell('{ this is not json')
      outcome = mod.reclaim(@workspace, @project)
      expect([outcome.removed, outcome.kept]).to eq([0, 1])
      expect(File.exist?(shell_path)).to be true
    end

    it 'reports absence as absence, and creates nothing' do
      outcome = mod.reclaim(@workspace, @project)
      expect([outcome.absent, outcome.filled, outcome.removed, outcome.kept]).to eq([1, 0, 0, 0])
      expect(File.exist?(shell_path)).to be false
    end

    it 'is idempotent: the second run has nothing left to reclaim' do
      write_shell(EMPTY_V1)
      write_project_copy(20)
      expect(mod.reclaim(@workspace, @project).acted?).to be true
      second = mod.reclaim(@workspace, @project)
      expect(second.acted?).to be false
      expect(second.kept).to eq(1)
    end
  end

  describe '.report' do
    # Silence is what let the empty file survive from 2026-03 to 2026-09:
    # "this tree was repaired" and "this version repairs nothing" printed
    # the same thing. Every branch says something.
    %w[filled removed kept absent].each do |branch|
      it "prints a line in the #{branch} branch" do
        case branch
        when 'filled' then (write_shell(EMPTY_V1); write_project_copy(3))
        when 'removed' then write_shell(EMPTY_V1)
        when 'kept' then write_shell(JSON.pretty_generate('pins' => [{ 'a' => 1 }], 'version' => 3))
        end
        expect { mod.report(mod.reclaim(@workspace, @project)) }
          .to output(/Package.resolved/).to_stdout
      end
    end
  end


  # Two entry points reach the same rule and a rule can be wired into one of
  # them: `common_setup.ensure_workspace_exists` (from the SwiftUI setup and
  # the UIKit setup) and `library_setup.ensure_workspace_structure` (from
  # `setup_libraries`). The ticket counted two CREATION SITES; there are
  # three ways in. Arms per call site, not per rule.
  describe 'LibrarySetup#ensure_workspace_structure' do
    def run_library_setup
      setup = SjuiTools::Core::Setup::LibrarySetup.allocate
      setup.instance_variable_set(:@project, double(path: @project))
      # private: the entry point is `setup_libraries`, which needs a real
      # Xcodeproj. The rule under test is the same object either way.
      setup.send(:ensure_workspace_structure)
    end

    it 'no longer writes an empty Package.resolved on a fresh tree' do
      FileUtils.rm_rf(@workspace)
      expect { run_library_setup }.to output.to_stdout
      expect(File.exist?(shell_path)).to be false
    end

    it 'reclaims a shell an older version of itself left behind' do
      write_shell(EMPTY_V1)
      write_project_copy(20)
      expect { run_library_setup }.to output(/Reclaimed/).to_stdout
      expect(mod.pin_count(shell_path)).to eq(20)
    end
  end

  describe 'CommonSetup#ensure_workspace_exists' do
    def run_setup
      setup = SjuiTools::Core::Setup::CommonSetup.allocate
      setup.instance_variable_set(:@project_file_path, @project)
      setup.ensure_workspace_exists
    end

    it 'no longer writes an empty Package.resolved on a fresh tree' do
      FileUtils.rm_rf(@workspace)
      expect { run_setup }.to output.to_stdout
      expect(File.exist?(shell_path)).to be false
    end

    it 'reclaims a shell an older version of itself left behind' do
      write_shell(EMPTY_V1)
      write_project_copy(20)
      expect { run_setup }.to output(/Reclaimed/).to_stdout
      expect(mod.pin_count(shell_path)).to eq(20)
    end
  end
end
