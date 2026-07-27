# frozen_string_literal: true

require 'compose/compose_builder'

# Screen marker emission (screen-identity track, Phase 4).
#
# The static path has no conformance coverage on Android — the conformance
# host is Dynamic-mode only — so the generated string IS the regression test.
RSpec.describe KjuiTools::Compose::ComposeBuilder do
  let(:temp_dir) { Dir.mktmpdir('compose_builder_screen_marker_test') }
  let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }
  let(:view_dir) { File.join(temp_dir, 'src/main/kotlin/com/example/app/views') }

  let(:config) do
    {
      'source_directory' => 'src/main',
      'layouts_directory' => 'assets/Layouts',
      'view_directory' => 'kotlin/com/example/app/views',
      'package_name' => 'com.example.app',
      'project_path' => temp_dir
    }
  end

  before do
    FileUtils.mkdir_p(layouts_dir)
    FileUtils.mkdir_p(view_dir)

    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
    allow(Dir).to receive(:pwd).and_return(temp_dir)
  end

  after { FileUtils.rm_rf(temp_dir) }

  let(:builder) { described_class.new }

  def screen_layout(id = 'root')
    {
      'type' => 'View',
      'id' => id,
      'data' => [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => 'x' }],
      'child' => [{ 'type' => 'Label', 'id' => 'which', 'text' => '@{title}' }]
    }
  end

  def gen_path(dir, name)
    File.join(temp_dir, 'src/main/kotlin/com/example/app/views', dir, name)
  end

  def body_of(path)
    File.read(path)[/\/\/ >>> GENERATED_CODE_START.*?\/\/ >>> GENERATED_CODE_END/m]
  end

  context 'a screen layout' do
    before do
      File.write(File.join(layouts_dir, 'home.json'), JSON.generate(screen_layout))
      builder.build_file(File.join(layouts_dir, 'home.json'))
    end

    it 'wraps both rendering branches in a transparent Box carrying the marker' do
      body = body_of(gen_path('home', 'HomeGeneratedView.kt'))

      expect(body).to include('Box(propagateMinConstraints = true) {')
      expect(body).to include('ScreenMarker("home")')

      # Outside the mode switch: a mode-dependent marker would split test
      # results by rendering mode.
      expect(body.index('Box(propagateMinConstraints = true)'))
        .to be < body.index('if (DynamicModeManager.isActive())')
    end


    it 'passes the BARE screen id — the runtime layer owns the __screen_ prefix' do
      # Regression: codegen used to pass the already-prefixed marker while
      # the library prefixed again, producing __screen___screen_<id> on a
      # real device.
      expect(body_of(gen_path('home', 'HomeGeneratedView.kt')))
        .not_to include('ScreenMarker("__screen_')
    end

    it 'imports ScreenMarker and names the minimum library version' do
      content = File.read(gen_path('home', 'HomeGeneratedView.kt'))

      expect(content).to include('import com.kotlinjsonui.core.ScreenMarker')
      expect(content).to include(
        "// Requires KotlinJsonUI >= #{described_class::SCREEN_MARKER_MIN_LIBRARY_VERSION} (screen marker)"
      )
    end

    it 'is idempotent across rebuilds' do
      first = File.read(gen_path('home', 'HomeGeneratedView.kt'))
      builder.build_file(File.join(layouts_dir, 'home.json'))
      expect(File.read(gen_path('home', 'HomeGeneratedView.kt'))).to eq(first)
    end
  end

  context 'a layout referenced as a cell' do
    before do
      File.write(File.join(layouts_dir, 'item_cell.json'), JSON.generate(screen_layout('cell_root')))
      File.write(File.join(layouts_dir, 'list.json'), JSON.generate(
        'type' => 'View',
        'child' => [{ 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['item_cell'] }]
      ))
      builder.build_file(File.join(layouts_dir, 'item_cell.json'))
    end

    it 'emits no marker and no wrapper Box' do
      body = body_of(gen_path('item_cell', 'ItemCellGeneratedView.kt'))

      expect(body).not_to include('ScreenMarker')
      expect(body).not_to include('propagateMinConstraints')
      expect(File.read(gen_path('item_cell', 'ItemCellGeneratedView.kt')))
        .not_to include('import com.kotlinjsonui.core.ScreenMarker')
    end
  end

  context 'a layout declaring "role": "cell"' do
    before do
      layout = screen_layout.merge('role' => 'cell')
      File.write(File.join(layouts_dir, 'standalone.json'), JSON.generate(layout))
      builder.build_file(File.join(layouts_dir, 'standalone.json'))
    end

    it 'honours the explicit role over the derivation' do
      expect(body_of(gen_path('standalone', 'StandaloneGeneratedView.kt')))
        .not_to include('ScreenMarker')
    end
  end
end
