# frozen_string_literal: true

require 'ripper'
require 'tmpdir'
require_relative 'spec_helper'

# Every spec file of this tool loads into one process, and a constant defined
# where the lexical scope is the top level — at the top of a file, or inside
# `RSpec.describe … do`, since a block opens no constant scope — is Object's:
# two files that define the same name share one constant, and which value an
# example sees depends on the order the files load (4f round 9). It happened:
# two Collection specs each defined SECTIONS, and the second's values ran the
# first's examples. A value a spec needs is scoped — a `let`, a local of the
# describe block, or a constant inside a module named for the file.
#
# The detector reads each file as UTF-8 and refuses one it cannot parse,
# rather than reading nothing in it: read with the locale's encoding, a file
# with a multibyte comment does not parse, and a skipped file is a file whose
# constants no one counted.
module SpecConstantsAreScoped
  module_function

  # The names `source` defines at the top level: constants assigned, and
  # modules and classes opened, outside any module or class body.
  def top_level_constants(source, path)
    tree = Ripper.sexp(source) or raise "did not parse: #{path}"
    found = []
    walk(tree, false, found)
    found.uniq
  end

  def walk(node, scoped, found)
    return unless node.is_a?(Array)

    case node[0]
    when :module, :class
      name = node[1]
      found << name[1][1] if !scoped && name.is_a?(Array) && name[0] == :const_ref
      node[2..].each { |child| walk(child, true, found) }
      return
    when :sclass
      node[1..].each { |child| walk(child, true, found) }
      return
    when :assign, :opassign
      target = node[1]
      if !scoped && target.is_a?(Array) && target[0] == :var_field && target[1].is_a?(Array) && target[1][0] == :@const
        found << target[1][1]
      end
    end
    node.each { |child| walk(child, scoped, found) if child.is_a?(Array) }
  end

  # A spec file's text, as UTF-8 whatever the locale says.
  def read(path)
    File.read(path, encoding: 'UTF-8')
  end

  # { name => [path, …] } for every name more than one source defines.
  def shared(sources)
    by_name = Hash.new { |h, k| h[k] = [] }
    sources.each { |path, source| top_level_constants(source, path).each { |name| by_name[name] << path } }
    by_name.select { |_, paths| paths.size > 1 }
  end
end

RSpec.describe 'the spec files of this tool' do
  it 'define no top-level constant another spec file defines' do
    root = __dir__
    sources = Dir.glob(File.join(root, '**', '*.rb')).sort.to_h { |f| [f.sub("#{root}/", ''), SpecConstantsAreScoped.read(f)] }
    expect(sources.size).to be > 50
    expect(SpecConstantsAreScoped.shared(sources)).to eq({})
  end

  describe 'the detector' do
    it 'finds a name defined at the top of one file and inside a describe block of another' do
      sources = { 'a_spec.rb' => "X = 1\n", 'b_spec.rb' => "RSpec.describe 'b' do\n  X = 2\nend\n",
                  'c_spec.rb' => "module X\nend\n" }
      expect(SpecConstantsAreScoped.shared(sources)).to eq('X' => %w[a_spec.rb b_spec.rb c_spec.rb])
    end

    it 'leaves a name inside a module or a class body, a let and a local' do
      sources = { 'a_spec.rb' => "X = 1\n", 'b_spec.rb' => "module B\n  X = 2\nend\n", 'c_spec.rb' => "class C\n  X = 3\nend\n",
                  'd_spec.rb' => "RSpec.describe 'd' do\n  let(:x) { 4 }\n  x = 5\nend\n" }
      expect(SpecConstantsAreScoped.shared(sources)).to eq({})
    end

    it 'reads a file as UTF-8 whatever the locale says' do
      saved = Encoding.default_external
      verbose = $VERBOSE
      Dir.mktmpdir('spec_constants') do |dir|
        path = File.join(dir, 'multibyte_spec.rb')
        File.write(path, "X = '\u2014'\n", encoding: 'UTF-8')
        $VERBOSE = nil
        Encoding.default_external = Encoding::US_ASCII
        expect(SpecConstantsAreScoped.top_level_constants(SpecConstantsAreScoped.read(path), path)).to eq(['X'])
      end
    ensure
      Encoding.default_external = saved
      $VERBOSE = verbose
    end

    it 'refuses a file it cannot parse' do
      expect { SpecConstantsAreScoped.top_level_constants("X = (\n", 'bad_spec.rb') }.to raise_error(/did not parse: bad_spec.rb/)
    end
  end
end
