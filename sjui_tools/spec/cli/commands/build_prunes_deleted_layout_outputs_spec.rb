# frozen_string_literal: true

require 'cli/commands/build'
require 'swiftui/data_model_updater'
require 'fileutils'
require 'tmpdir'

# jui-build-leaves-native-generated-files-of-a-deleted-layout, iOS face.
#
# Deleting a layout used to leave its Data model and GeneratedView in the
# tree, both @generated, both still compiled. The SwiftUI build now clears
# them by the rule the three faces share (lib/core/generated_orphans.rb; the
# rule's own arms are in spec/core/generated_orphans_spec.rb). These arms hold
# the wiring: which directories, which names, what is named instead.
RSpec.describe SjuiTools::CLI::Commands::Build do
  let(:build) { described_class.new }

  around do |example|
    Dir.mktmpdir('sjui-orphans') { |dir| @root = dir; example.run }
  end

  # A data directory away from the default, so an arm fails if the sweep
  # spelled the directory itself instead of asking the Data writer.
  let(:config) do
    {
      'layouts_directory' => 'Layouts', 'view_directory' => 'View',
      'viewmodel_directory' => 'ViewModel', 'data_directory' => 'Models/Data'
    }
  end

  before do
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(@root)
    allow(SjuiTools::Core::Logger).to receive(:info)
    allow(SjuiTools::Core::Logger).to receive(:warn)
    write('Layouts/home.json', '{"type": "View"}')
  end

  def write(rel, content = '')
    path = File.join(@root, rel)
    FileUtils.mkdir_p(File.dirname(path))
    File.write(path, content)
    path
  end

  def generated(rel)
    write(rel, "// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT\n// ║  Source:    Layouts/x.json\n")
  end

  def prune
    build.send(:prune_layout_orphans, @root, config,
               File.join(@root, 'Layouts'), File.join(@root, 'View'))
  end

  it "deletes a deleted layout's Data model and GeneratedView, naming each" do
    data = generated('Models/Data/GoneData.swift')
    view = generated('View/Gone/GoneGeneratedView.swift')
    prune
    expect([data, view].map { |f| File.exist?(f) }).to eq([false, false])
    expect(SjuiTools::Core::Logger).to have_received(:info).with('  - Models/Data/GoneData.swift')
    expect(SjuiTools::Core::Logger).to have_received(:info).with('  - View/Gone/GoneGeneratedView.swift')
  end

  it "keeps the hand-written View and ViewModel of that layout and names them" do
    generated('Models/Data/GoneData.swift')
    view = write('View/Gone/GoneView.swift')
    viewmodel = write('ViewModel/GoneViewModel.swift')
    prune
    expect(File.exist?(view) && File.exist?(viewmodel)).to be(true)
    expect(SjuiTools::Core::Logger).to have_received(:warn).with(a_string_starting_with('  - View/Gone/GoneView.swift: '))
    expect(SjuiTools::Core::Logger).to have_received(:warn).with(a_string_starting_with('  - ViewModel/GoneViewModel.swift: '))
  end

  describe 'boundaries — each one is kept' do
    it 'a file of that name with no @generated line' do
      unmarked = write('Models/Data/GoneData.swift', "import Foundation\nstruct GoneData {}\n")
      prune
      expect(File.exist?(unmarked)).to be(true)
    end

    it 'a @generated file outside the directory the config declares' do
      stray = generated('Data/GoneData.swift')
      prune
      expect(File.exist?(stray)).to be(true)
    end

    it 'the outputs of a layout that still exists' do
      live = [generated('Models/Data/HomeData.swift'), generated('View/Home/HomeGeneratedView.swift')]
      prune
      expect(live.map { |f| File.exist?(f) }).to eq([true, true])
      expect(SjuiTools::Core::Logger).not_to have_received(:info).with(/Pruned/)
    end
  end
end
