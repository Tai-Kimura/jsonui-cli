# frozen_string_literal: true

require 'compose/compose_builder'

# Responsive variant-file mechanism (home@regular.json → size-class
# dispatch in the base GeneratedView + <Base><Class>VariantGeneratedView),
# 06 variant-file track / 06a-design.md D5-D6.
RSpec.describe KjuiTools::Compose::ComposeBuilder do
  let(:temp_dir) { Dir.mktmpdir('compose_builder_variant_test') }
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

  after do
    FileUtils.rm_rf(temp_dir)
  end

  let(:builder) { described_class.new }
  let(:base_layout) do
    {
      'type' => 'View',
      'id' => 'root',
      'data' => [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => 'base' }],
      'child' => [{ 'type' => 'Label', 'id' => 'which', 'text' => '@{title}' }]
    }
  end
  let(:variant_layout) do
    {
      'type' => 'View',
      'id' => 'root',
      'child' => [{ 'type' => 'Label', 'id' => 'which', 'text' => 'regular tree' }]
    }
  end

  def gen_path(name)
    File.join(temp_dir, 'src/main/kotlin/com/example/app/views/home', name)
  end

  context 'with a @regular variant next to the base screen' do
    before do
      File.write(File.join(layouts_dir, 'home.json'), JSON.generate(base_layout))
      File.write(File.join(layouts_dir, 'home@regular.json'), JSON.generate(variant_layout))
      builder.build_file(File.join(layouts_dir, 'home.json'))
    end

    it 'emits a window-width dispatch in the base GeneratedView static branch' do
      content = File.read(gen_path('HomeGeneratedView.kt'))
      body = content[/\/\/ >>> GENERATED_CODE_START.*?\/\/ >>> GENERATED_CODE_END/m]

      expect(body).to include('when {')
      expect(body).to include('>= 840')
      expect(body).to include('HomeRegularVariantGeneratedView(data = data, viewModel = viewModel, modifier = modifier)')
      # base tree stays reachable in the else arm
      expect(body).to include('else -> {')
      expect(content).to include('import androidx.compose.ui.platform.LocalWindowInfo')
      expect(content).to include('import androidx.compose.ui.platform.LocalDensity')
    end

    it 'creates the variant GeneratedView with base-canonical Data/ViewModel types' do
      path = gen_path('HomeRegularVariantGeneratedView.kt')
      expect(File.exist?(path)).to be true
      content = File.read(path)

      expect(content).to include('fun HomeRegularVariantGeneratedView(')
      expect(content).to include('data: HomeData')
      expect(content).to include('viewModel: HomeViewModel')
      expect(content).to include('modifier: Modifier = Modifier')
      expect(content).to include('regular tree')
      expect(content).not_to include('HomeRegularVariantData')
      expect(content).not_to include('HomeRegularVariantViewModel')
    end

    it 'is idempotent across rebuilds' do
      first_base = File.read(gen_path('HomeGeneratedView.kt'))
      first_variant = File.read(gen_path('HomeRegularVariantGeneratedView.kt'))
      builder.build_file(File.join(layouts_dir, 'home.json'))
      expect(File.read(gen_path('HomeGeneratedView.kt'))).to eq(first_base)
      expect(File.read(gen_path('HomeRegularVariantGeneratedView.kt'))).to eq(first_variant)
    end
  end

  context 'with all three variants present' do
    before do
      File.write(File.join(layouts_dir, 'home.json'), JSON.generate(base_layout))
      %w[compact medium regular].each do |cls|
        File.write(File.join(layouts_dir, "home@#{cls}.json"), JSON.generate(variant_layout))
      end
      builder.build_file(File.join(layouts_dir, 'home.json'))
    end

    it 'drops the base tree and dispatches compact in the else arm' do
      body = File.read(gen_path('HomeGeneratedView.kt'))[/\/\/ >>> GENERATED_CODE_START.*?\/\/ >>> GENERATED_CODE_END/m]

      expect(body).to include('else -> HomeCompactVariantGeneratedView(')
      expect(body).to include('in 600..839')
      expect(body).to include('HomeMediumVariantGeneratedView(')
      expect(body).not_to include('@{title}'.sub('@{', 'data.'))
      expect(body).not_to include('else -> {')
    end
  end

  context 'variant exclusion' do
    before do
      File.write(File.join(layouts_dir, 'home.json'), JSON.generate(base_layout))
      File.write(File.join(layouts_dir, 'home@regular.json'), JSON.generate(variant_layout))
    end

    it 'build_file on a variant file is a no-op' do
      expect(builder.build_file(File.join(layouts_dir, 'home@regular.json'))).to be_nil
      expect(Dir.glob(File.join(view_dir, '**/*.kt'))).to be_empty
    end

    it 'build never scaffolds a standalone screen for the variant' do
      builder.build
      kt_files = Dir.glob(File.join(view_dir, '**/*.kt')).map { |f| File.basename(f) }
      expect(kt_files).to include('HomeGeneratedView.kt', 'HomeRegularVariantGeneratedView.kt')
      expect(kt_files.grep(/@/)).to be_empty
      expect(kt_files).not_to include('Home@regularView.kt')
    end

    it 'does not generate a Data model for the variant' do
      builder.build
      data_files = Dir.glob(File.join(temp_dir, 'src/main/kotlin/**/data/*.kt')).map { |f| File.basename(f) }
      expect(data_files.grep(/@|Variant/)).to be_empty
    end
  end

  context 'without variants' do
    it 'generates byte-identical output to the pre-variant pipeline' do
      File.write(File.join(layouts_dir, 'home.json'), JSON.generate(base_layout))
      builder.build_file(File.join(layouts_dir, 'home.json'))
      content = File.read(gen_path('HomeGeneratedView.kt'))
      expect(content).not_to include('when {')
      expect(content).not_to include('Variant')
    end
  end
end
