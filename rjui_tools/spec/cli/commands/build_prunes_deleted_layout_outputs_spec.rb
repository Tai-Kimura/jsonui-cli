# frozen_string_literal: true

require 'cli/commands/build_command'
require 'fileutils'
require 'tmpdir'

# jui-build-leaves-native-generated-files-of-a-deleted-layout, Web face.
#
# The build already pruned a deleted layout's component and ViewModel base;
# its Data model and hook stayed. They are now cleared by the rule the three
# faces share (lib/core/generated_orphans.rb; the rule's own arms are in
# sjui_tools/spec/core/generated_orphans_spec.rb), and a hand-written
# ViewModel of the same name is named, not deleted.
RSpec.describe RjuiTools::CLI::Commands::BuildCommand do
  around do |example|
    Dir.mktmpdir('rjui-orphans') { |dir| @root = dir; example.run }
  end

  # Data and hooks away from their defaults, so an arm fails if the sweep
  # spelled a directory itself instead of asking the generator that writes it.
  let(:config) do
    {
      'source_path' => @root, 'layouts_directory' => 'src/Layouts',
      'data_directory' => 'src/gen/models', 'hooks_directory' => 'src/gen/use',
      'viewmodels_directory' => 'src/vm', 'typescript' => true
    }
  end

  let(:build) { described_class.new([]) }

  before do
    allow(RjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(RjuiTools::Core::Logger).to receive(:info)
    allow(RjuiTools::Core::Logger).to receive(:warn)
    write('src/Layouts/home.json', '{"type": "View"}')
  end

  def write(rel, content = '')
    path = File.join(@root, rel)
    FileUtils.mkdir_p(File.dirname(path))
    File.write(path, content)
    path
  end

  def generated(rel)
    write(rel, "// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT\n// ║  Source:    GoneData\n")
  end

  def prune
    build.send(:prune_layout_orphans)
  end

  it "deletes a deleted layout's Data model and hook, naming each" do
    data = generated('src/gen/models/GoneData.ts')
    hook = generated('src/gen/use/useGoneViewModel.ts')
    prune
    expect([data, hook].map { |f| File.exist?(f) }).to eq([false, false])
    expect(RjuiTools::Core::Logger).to have_received(:info).with('  - src/gen/models/GoneData.ts')
    expect(RjuiTools::Core::Logger).to have_received(:info).with('  - src/gen/use/useGoneViewModel.ts')
  end

  it 'keeps the hand-written ViewModel of that layout and names it' do
    generated('src/gen/models/GoneData.ts')
    viewmodel = write('src/vm/GoneViewModel.ts')
    prune
    expect(File.exist?(viewmodel)).to be(true)
    expect(RjuiTools::Core::Logger).to have_received(:warn).with(a_string_starting_with('  - src/vm/GoneViewModel.ts: '))
  end

  it 'leaves the support files beside them alone' do
    support = [generated('src/gen/models/CollectionDataSource.ts'), generated('src/gen/use/useColorMode.ts')]
    prune
    expect(support.map { |f| File.exist?(f) }).to eq([true, true])
  end

  describe 'boundaries — each one is kept' do
    it 'a file of that name with no @generated line' do
      unmarked = write('src/gen/models/GoneData.ts', "export interface GoneData {}\n")
      prune
      expect(File.exist?(unmarked)).to be(true)
    end

    it 'a @generated file outside the directory the config declares' do
      stray = generated('src/generated/data/GoneData.ts')
      prune
      expect(File.exist?(stray)).to be(true)
    end

    it 'the outputs of a layout that still exists' do
      live = [generated('src/gen/models/HomeData.ts'), generated('src/gen/use/useHomeViewModel.ts')]
      prune
      expect(live.map { |f| File.exist?(f) }).to eq([true, true])
      expect(RjuiTools::Core::Logger).not_to have_received(:info).with(/Pruned/)
    end
  end
end
