# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# The warning `sjui g converter --attributes key:Type` prints for a type
# outside the attribute type vocabulary (JsonUIShared::AttributeTypes
# .outside_warning, the one sentence of all three tools) names the type the
# scaffold declares, and says "kept" when the run wrote no scaffold.
#
# Until 1.8.121 (measured on f16f3a11, 2026-09-26) `Row!!` — sjui's "not
# optional" mark — was named "Row? in Swift" while the component and the
# adapter declared `Row`; and a run that kept the existing scaffold
# (--skip-existing) said "it is scaffolded as …" of files it had not
# touched, which still declared the type they were made with. Ticket
# converter-attr-types-warning-wording.
#
# End to end: what the warning says and what the scaffold declares come from
# two places (the shared table and the Swift generators), and the scaffold's
# type is read back from the files written. The tool is COPIED (links
# dereferenced): `g converter` writes into the tool's own views/extensions.
RSpec.describe 'the warning for an attribute type outside the vocabulary, through sjui g converter' do
  def tool_root
    File.expand_path('../../..', __dir__)
  end

  # type => what the Swift scaffold declares for it. `Row!!` => `Row` is
  # sjui's own rule, pinned where the component is made
  # (swift_component_generator_spec, "respects !! suffix for non-optional"):
  # the authority the warning is held to, not the warning's own table.
  def self.swift_declares
    { 'Row' => 'Row?', 'Row?' => 'Row?', 'Row!!' => 'Row', '[Row]' => '[Row]' }
  end

  before(:all) do
    @dir = Dir.mktmpdir('sjui_attr_warning')
    tool = File.join(@dir, 'sjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    name = 'WarnProbe'
    File.write(File.join(@dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => 'swiftui', 'project_name' => name, 'project_file_name' => name,
      'source_directory' => name, 'layouts_directory' => 'Layouts',
      'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
      'view_directory' => 'View', 'data_directory' => 'Data',
      'viewmodel_directory' => 'ViewModel',
      'resource_manager_directory' => 'ResourceManager',
      'string_files' => ["#{name}/Localizable.strings"], 'use_network' => true,
      'adapter_directory' => 'Extensions/Adapters'
    ))
    FileUtils.mkdir_p(File.join(@dir, "#{name}.xcodeproj"))
    FileUtils.mkdir_p(File.join(@dir, name, 'Layouts'))

    sjui = lambda do |component, type, flags|
      said, status = Open3.capture2e('ruby', File.join(tool, 'bin', 'sjui'), 'g', 'converter', component,
                                     '--attributes', "r:#{type}", *flags, chdir: @dir, stdin_data: '')
      [said.gsub(/\e\[[0-9;]*m/, ''), status]
    end
    # Per type: New (a fresh scaffold), Kept (made with Int, then the type
    # with --skip-existing: nothing written) and Forced (made with Int, then
    # the type with --force).
    @runs = {}
    self.class.swift_declares.each_key.with_index do |type, i|
      @runs[[type, :new]] = sjui.call("New#{i}", type, ['--force'])
      sjui.call("Kept#{i}", 'Int', ['--force'])
      @runs[[type, :kept]] = sjui.call("Kept#{i}", type, ['--skip-existing'])
      sjui.call("Forced#{i}", 'Int', ['--force'])
      @runs[[type, :forced]] = sjui.call("Forced#{i}", type, ['--force'])
    end
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def component(type, run)
    "#{run.to_s.capitalize}#{self.class.swift_declares.keys.index(type)}"
  end

  # The one warning line of a run, or a failure naming what it printed.
  def warning(type, run)
    said, status = @runs[[type, run]]
    expect(status.success?).to be(true), said
    lines = said.lines.select { |l| l.include?('not in the attribute type vocabulary') }
    expect(lines.size).to eq(1), said
    lines.first
  end

  # What the component and the adapter declare for `r`.
  def declared(name)
    swift = File.read(File.join(@dir, 'WarnProbe', 'Extensions', "#{name}.swift"))
    adapter = File.read(File.join(@dir, 'WarnProbe', 'Extensions', 'Adapters', "#{name}Adapter.swift"))
    [swift[/^\s*let r: (.+)$/, 1], adapter[/^\s*let r: (\S+)/, 1]]
  end

  swift_declares.each do |type, swift|
    context type do
      %i[new forced].each do |run|
        it "#{run}: names #{swift} in Swift — what the component and the adapter declare" do
          said = warning(type, run)
          expect(declared(component(type, run))).to eq([swift, swift])
          expect(said[/it is scaffolded as (\S+) in Swift,/, 1]).to eq(swift), said
        end
      end

      it 'kept (--skip-existing): says the scaffold was kept, not what it is scaffolded as' do
        said = warning(type, :kept)
        # Nothing was written: the kept scaffold still declares its first type.
        expect(declared(component(type, :kept))).to eq(%w[Int Int])
        expect(said).not_to include('is scaffolded as')
        expect(said).to include('the existing scaffold was kept')
        expect(said[/a new scaffold would declare (\S+) in Swift,/, 1]).to eq(swift), said
      end
    end
  end
end
