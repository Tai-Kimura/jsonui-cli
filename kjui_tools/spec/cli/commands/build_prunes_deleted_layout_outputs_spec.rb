# frozen_string_literal: true

require 'cli/commands/build'
require 'compose/compose_builder'
require 'compose/data_model_updater'
require 'compose/generators/view_generator'
require 'fileutils'
require 'tmpdir'

# jui-build-leaves-native-generated-files-of-a-deleted-layout, Android face.
#
# The Compose build now clears what a deleted layout left by the rule the
# three faces share (lib/core/generated_orphans.rb; the rule's own arms are in
# sjui_tools/spec/core/generated_orphans_spec.rb). Here the Data model is
# @generated and is deleted. The GeneratedView carries no @generated line (the
# generator rewrites its GENERATED_CODE block and leaves the rest as the
# scaffold wrote it), and is deleted all the same: it is a generated file, not
# a place for hand-written code, and left behind it names the deleted ViewModel
# so the app stops compiling (ticket jui-build-leaves-orphan-protocol-and-kjui-
# view-after-screen-removal, ruling 2026-11-13). One that held lines its
# scaffold does not have is deleted too, and named in a warning.
RSpec.describe KjuiTools::CLI::Commands::Build do
  let(:build) { described_class.new }

  around do |example|
    Dir.mktmpdir('kjui-orphans') { |dir| @root = dir; example.run }
  end

  # A data directory away from the default, so an arm fails if the sweep
  # spelled the directory itself instead of asking the Data writer.
  let(:config) do
    {
      'source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts',
      'view_directory' => 'kotlin/views', 'viewmodel_directory' => 'kotlin/viewmodels',
      'data_directory' => 'kotlin/app/models', 'package_name' => 'com.example.probe'
    }
  end

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(@root)
    allow(KjuiTools::Core::Logger).to receive(:info)
    allow(KjuiTools::Core::Logger).to receive(:warn)
    write('src/main/assets/Layouts/home.json', '{"type": "View"}')
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

  # What the generator writes for a new screen, as a build has rewritten it:
  # the scaffold with its block filled and the helpers block appended.
  def generated_view(rel, name = File.basename(rel, 'GeneratedView.kt'))
    scaffold = KjuiTools::Compose::Generators::ViewGenerator.allocate
                                                           .send(:generated_view_content, name, 'gone', nil, 'com.example.probe')
    built = scaffold.sub(/(GENERATED_CODE_START\n).*?(\s*\/\/ >>> GENERATED_CODE_END)/m, "\\1        Text(\"built\")\\2")
    write(rel, "#{built}\n// >>> RESPONSIVE_HELPERS_START\n@Composable\nprivate fun Section1() {}\n// >>> RESPONSIVE_HELPERS_END\n")
  end

  def altered_line(rel)
    "#{rel} #{JsonUIShared::GeneratedOrphans::ALTERED_WARNING}"
  end

  def prune
    build.send(:prune_layout_orphans, KjuiTools::Compose::ComposeBuilder.new)
  end

  it "deletes a deleted layout's Data model and names it" do
    data = generated('src/main/kotlin/app/models/GoneData.kt')
    prune
    expect(File.exist?(data)).to be(false)
    expect(KjuiTools::Core::Logger).to have_received(:info).with('  - src/main/kotlin/app/models/GoneData.kt')
  end

  it 'deletes its GeneratedView, which holds only what the generator wrote, without a warning' do
    view = generated_view('src/main/kotlin/views/gone/GoneGeneratedView.kt')
    prune
    expect(File.exist?(view)).to be(false)
    expect(KjuiTools::Core::Logger).to have_received(:info).with('  - src/main/kotlin/views/gone/GoneGeneratedView.kt')
    expect(KjuiTools::Core::Logger).not_to have_received(:warn).with(a_string_including('GoneGeneratedView'))
  end

  it 'deletes a GeneratedView whose scaffold differs only in whitespace and line breaks, without a warning' do
    view = generated_view('src/main/kotlin/views/gone/GoneGeneratedView.kt')
    File.write(view, File.read(view).gsub("\n", "\n\n").gsub('    ', "\t").sub('fun GoneGeneratedView(', 'fun  GoneGeneratedView ('))
    prune
    expect(File.exist?(view)).to be(false)
    expect(KjuiTools::Core::Logger).not_to have_received(:warn).with(a_string_including('GoneGeneratedView'))
  end

  # The heavier mistake would be deleting hand-written code in silence: one
  # line outside the blocks is still deleted (a GeneratedView is not a place
  # for it), and the run says so, in one line, with the way back.
  it 'deletes a GeneratedView that held a hand-written line outside its blocks, and warns' do
    view = generated_view('src/main/kotlin/views/gone/GoneGeneratedView.kt')
    File.write(view, File.read(view).sub('@Composable', "private val handWritten = 1\n\n@Composable"))
    prune
    expect(File.exist?(view)).to be(false)
    expect(KjuiTools::Core::Logger).to have_received(:warn).with(altered_line('src/main/kotlin/views/gone/GoneGeneratedView.kt'))
  end

  it 'keeps the hand-written View and ViewModel of that layout and names them' do
    generated('src/main/kotlin/app/models/GoneData.kt')
    view = write('src/main/kotlin/views/gone/GoneView.kt')
    viewmodel = write('src/main/kotlin/viewmodels/GoneViewModel.kt')
    prune
    expect(File.exist?(view) && File.exist?(viewmodel)).to be(true)
    expect(KjuiTools::Core::Logger).to have_received(:warn).with(a_string_starting_with('  - src/main/kotlin/views/gone/GoneView.kt: '))
    expect(KjuiTools::Core::Logger).to have_received(:warn).with(a_string_starting_with('  - src/main/kotlin/viewmodels/GoneViewModel.kt: '))
  end

  # The older marker this generator wrote before @generated: not the claim
  # the rule deletes on, so the file is named instead.
  it 'keeps a Data model that carries only the older marker, and names it' do
    old = write('src/main/kotlin/app/models/GoneStyleData.kt', "// Generated by kjui_tools - DO NOT EDIT\npackage x\n")
    prune
    expect(File.exist?(old)).to be(true)
    expect(KjuiTools::Core::Logger).to have_received(:warn)
      .with("  - src/main/kotlin/app/models/GoneStyleData.kt: #{JsonUIShared::GeneratedOrphans::WARNINGS[:unmarked]}")
  end

  # A moved layout gets a new GeneratedView and View in its new package; the
  # app still imports the old View, which draws the old GeneratedView — no
  # longer updated. The old GeneratedView is deleted and the old View named;
  # the path comes from generated_view_dir, the one the build writes by.
  it 'deletes the GeneratedView a moved layout left behind, names its View, and leaves the new ones alone' do
    write('src/main/assets/Layouts/section/moved_card.json', '{"type": "View"}')
    stale = generated_view('src/main/kotlin/views/moved_card/MovedCardGeneratedView.kt')
    old_view = write('src/main/kotlin/views/moved_card/MovedCardView.kt')
    generated_view('src/main/kotlin/views/section/moved_card/MovedCardGeneratedView.kt')
    write('src/main/kotlin/views/section/moved_card/MovedCardView.kt')
    prune
    expect(File.exist?(stale)).to be(false)
    expect(File.exist?(File.join(@root, 'src/main/kotlin/views/section/moved_card/MovedCardGeneratedView.kt'))).to be(true)
    orphans = JsonUIShared::GeneratedOrphans
    expect(KjuiTools::Core::Logger).to have_received(:info).with('  - src/main/kotlin/views/moved_card/MovedCardGeneratedView.kt')
    expect(KjuiTools::Core::Logger).to have_received(:warn)
      .with("  - src/main/kotlin/views/moved_card/MovedCardView.kt: #{orphans.moved_warning(:user, 'section/moved_card')}")
    expect(KjuiTools::Core::Logger).not_to have_received(:warn).with(a_string_including('views/section/moved_card/'))
  end

  describe 'a living layout\'s GeneratedView' do
    it 'is named when it holds a hand-written line outside its blocks, and kept' do
      live = generated_view('src/main/kotlin/views/home/HomeGeneratedView.kt')
      File.write(live, File.read(live).sub('@Composable', "private val handWritten = 1\n\n@Composable"))
      prune
      expect(File.exist?(live)).to be(true)
      expect(KjuiTools::Core::Logger).to have_received(:warn)
        .with("src/main/kotlin/views/home/HomeGeneratedView.kt #{described_class::HAND_WRITTEN_GENERATED_VIEW}")
    end

    it 'is not named when it holds only what the generator wrote' do
      live = generated_view('src/main/kotlin/views/home/HomeGeneratedView.kt')
      prune
      expect(File.exist?(live)).to be(true)
      expect(KjuiTools::Core::Logger).not_to have_received(:warn)
    end
  end

  describe 'boundaries — each one is kept' do
    it 'a @generated file outside the directory the config declares' do
      stray = generated('src/main/kotlin/app/data/GoneData.kt')
      prune
      expect(File.exist?(stray)).to be(true)
    end

    it 'the outputs of a layout that still exists' do
      live = generated('src/main/kotlin/app/models/HomeData.kt')
      live_view = generated_view('src/main/kotlin/views/home/HomeGeneratedView.kt')
      File.write(live_view, File.read(live_view).sub('@Composable', "private val handWritten = 1\n\n@Composable"))
      prune
      expect(File.exist?(live) && File.exist?(live_view)).to be(true)
      expect(KjuiTools::Core::Logger).not_to have_received(:info).with(/Pruned/)
    end
  end
end
