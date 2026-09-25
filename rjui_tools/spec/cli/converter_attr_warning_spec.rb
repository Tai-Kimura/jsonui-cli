# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# The warning `rjui g converter --attributes key:Type` prints for a type
# outside the attribute type vocabulary (JsonUIShared::AttributeTypes
# .outside_warning, the one sentence of all three tools) names the type the
# scaffold declares, and says "kept" when the run wrote no scaffold.
#
# Until 1.8.121 (measured on f16f3a11, 2026-09-26) `Row!!` — sjui's "not
# optional" mark — was named "Row? in Swift" on every tool while sjui's
# scaffold declared `Row`; and a run that kept the existing scaffold
# (--skip-existing) said "it is scaffolded as …" of files it had not
# touched, which still declared the type they were made with. Ticket
# converter-attr-types-warning-wording.
#
# End to end: the TypeScript the warning names is read back from the
# component written. The Swift it names for `Row!!` is sjui's rule (sjui's
# arm reads it back from the Swift written); rjui writes no Swift, so here it
# is held to that rule as a literal. The tool is COPIED (links dereferenced).
RSpec.describe 'the warning for an attribute type outside the vocabulary, through rjui g converter' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  # type => [what the component declares for it, what sjui's Swift scaffold
  # declares]. The Swift column is sjui's rule, pinned in sjui_tools
  # (swift_component_generator_spec, "respects !! suffix for non-optional").
  def self.declares
    { 'Row' => ['any', 'Row?'], 'Row?' => ['any', 'Row?'], 'Row!!' => ['any', 'Row'],
      '[Row]' => ['any[]', '[Row]'] }
  end

  before(:all) do
    @dir = Dir.mktmpdir('rjui_attr_warning')
    tool = File.join(@dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    # No rjui.config.json: rjui writes its defaults (components in
    # src/components/extensions), as leaf_children_build_spec.rb.
    FileUtils.mkdir_p(File.join(@dir, 'src', 'Layouts'))

    rjui = lambda do |component, type, flags|
      said, status = Open3.capture2e('ruby', File.join(tool, 'bin', 'rjui'), 'g', 'converter', component,
                                     '--attributes', "r:#{type}", *flags, chdir: @dir, stdin_data: '')
      [said.gsub(/\e\[[0-9;]*m/, ''), status]
    end
    # Per type: New (a fresh scaffold), Kept (made with Int, then the type
    # with --skip-existing: nothing written) and Forced (made with Int, then
    # the type with --force).
    @runs = {}
    self.class.declares.each_key.with_index do |type, i|
      @runs[[type, :new]] = rjui.call("New#{i}", type, ['--force'])
      rjui.call("Kept#{i}", 'Int', ['--force'])
      @runs[[type, :kept]] = rjui.call("Kept#{i}", type, ['--skip-existing'])
      rjui.call("Forced#{i}", 'Int', ['--force'])
      @runs[[type, :forced]] = rjui.call("Forced#{i}", type, ['--force'])
    end
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def component(type, run)
    "#{run.to_s.capitalize}#{self.class.declares.keys.index(type)}"
  end

  # The one warning line of a run, or a failure naming what it printed.
  def warning(type, run)
    said, status = @runs[[type, run]]
    expect(status.success?).to be(true), said
    lines = said.lines.select { |l| l.include?('not in the attribute type vocabulary') }
    expect(lines.size).to eq(1), said
    lines.first
  end

  # What the component declares for `r`.
  def declared(name)
    tsx = File.read(File.join(@dir, 'src', 'components', 'extensions', "#{name}.tsx"))
    tsx[/^\s*r\?: (.+);$/, 1]
  end

  declares.each do |type, (ts, swift)|
    context type do
      %i[new forced].each do |run|
        it "#{run}: names #{ts} in TypeScript — what the component declares — and #{swift} in Swift" do
          said = warning(type, run)
          expect(declared(component(type, run))).to eq(ts)
          expect(said[/ and (\S+) in TypeScript/, 1]).to eq(ts), said
          expect(said[/it is scaffolded as (\S+) in Swift,/, 1]).to eq(swift), said
        end
      end

      it 'kept (--skip-existing): says the scaffold was kept, not what it is scaffolded as' do
        said = warning(type, :kept)
        # Nothing was written: the kept component still declares its first type.
        expect(declared(component(type, :kept))).to eq('number')
        expect(said).not_to include('is scaffolded as')
        expect(said).to include('the existing scaffold was kept')
        expect(said[/ and (\S+) in TypeScript/, 1]).to eq(ts), said
        expect(said[/a new scaffold would declare (\S+) in Swift,/, 1]).to eq(swift), said
      end
    end
  end
end
