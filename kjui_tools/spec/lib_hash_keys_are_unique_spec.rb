# frozen_string_literal: true

require 'open3'
require 'rbconfig'
require 'tmpdir'

# A hash literal that names one key twice keeps the last value, and Ruby says
# so only under -w: no spec, no build and no run of the tool fails on it.
# jsonui-cli 1.9.23 added a second :scroll_by to ImportManager's map for the
# Collection's anchored scrollTo; it overwrote the ScrollView anchor's, and
# every ScrollView with defaultScrollAnchor gained an animateScrollBy import it
# never called (kjui-import-manager-duplicate-scroll-by-key).
#
# Every file under lib/ is compiled — not run — in one Ruby with warnings on,
# and none may report a duplicated key. Other -w warnings are not this check's
# (lib has some, unused variables among them).
module LibHashKeysAreUnique
  module_function

  DUPLICATE = /: warning: key .* is duplicated and overwritten/

  # [warning lines naming a duplicated key, everything the compile printed]
  def duplicate_keys(paths)
    script = 'ARGV.each { |f| RubyVM::InstructionSequence.compile_file(f) }'
    out, status = Open3.capture2e(RbConfig.ruby, '-w', '-e', script, *paths)
    raise "the compile did not finish (#{status}):\n#{out}" unless status.success?

    [out.lines.map(&:chomp).grep(DUPLICATE), out]
  end
end

RSpec.describe 'the lib files of this tool' do
  it 'name no key twice in one hash literal' do
    lib = File.expand_path('../lib', __dir__)
    paths = Dir.glob(File.join(lib, '**', '*.rb')).sort
    expect(paths.size).to be > 100
    expect(paths).to include(File.join(lib, 'compose', 'helpers', 'import_manager.rb'))
    found, = LibHashKeysAreUnique.duplicate_keys(paths)
    expect(found).to eq([])
  end

  describe 'the detector' do
    around { |example| Dir.mktmpdir { |dir| @dir = dir; example.run } }

    def write(name, source)
      File.join(@dir, name).tap { |path| File.write(path, source) }
    end

    it 'finds a key named twice, and names the file' do
      path = write('twice.rb', "MAP = {\n  scroll_by: 'a',\n  other: 'b',\n  scroll_by: 'c'\n}\n")
      found, = LibHashKeysAreUnique.duplicate_keys([path])
      expect(found.size).to eq(1)
      expect(found.first).to start_with("#{path}:2:").and include(':scroll_by')
    end

    it 'leaves distinct keys, and a warning of another kind' do
      distinct = write('distinct.rb', "MAP = { scroll_by: 'a', anchored_scroll_by: 'b' }\n")
      unused = write('unused.rb', "def m\n  x = 1\nend\n")
      found, printed = LibHashKeysAreUnique.duplicate_keys([distinct, unused])
      expect(found).to eq([])
      expect(printed).to include('assigned but unused variable - x')
    end
  end
end
