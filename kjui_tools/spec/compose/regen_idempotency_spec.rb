# frozen_string_literal: true

require 'compose/compose_builder'

# Regression spec for kjui-incremental-build-stale-section-merge:
# rebuilding a layout ON TOP of an existing generated file after the layout's
# section structure changed must produce the same bytes as a clean generation
# (rm generated file, scaffold, build). The observed field failure was calls
# to SectionN helpers whose definitions came from the previous generation
# (unresolved references at best, silently wrong UI at worst).
RSpec.describe 'generated-view regeneration idempotency' do
  let(:temp_dir) { Dir.mktmpdir('compose_regen_test') }
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

  # A section-heavy layout: enough sibling containers with enough content to
  # push the generated body over SectionExtractor's line threshold so helper
  # functions are emitted.
  def section_heavy_layout(section_count:, labels_per_section: 8)
    {
      'type' => 'SafeAreaView',
      'child' => [
        {
          'type' => 'ScrollView',
          'id' => 'root_scroll',
          'orientation' => 'vertical',
          'child' => [
            {
              'type' => 'View',
              'id' => 'content_root',
              'orientation' => 'vertical',
              'width' => 'matchParent',
              'child' => (0...section_count).map do |s|
                {
                  'type' => 'View',
                  'id' => "block_#{s}",
                  'orientation' => 'vertical',
                  'width' => 'matchParent',
                  'child' => (0...labels_per_section).map do |i|
                    {
                      'type' => 'Label',
                      'id' => "block_#{s}_label_#{i}",
                      'text' => "Section #{s} row #{i}",
                      'fontSize' => 14,
                      'fontColor' => '#333333'
                    }
                  end
                }
              end
            }
          ]
        }
      ],
      'data' => [
        { 'name' => 'title', 'class' => 'String', 'defaultValue' => "'Regen'" }
      ]
    }
  end

  def generated_file
    File.join(view_dir, 'regen_screen', 'RegenScreenGeneratedView.kt')
  end

  def write_layout(json)
    File.write(File.join(layouts_dir, 'regen_screen.json'), JSON.pretty_generate(json))
  end

  def build!
    builder = KjuiTools::Compose::ComposeBuilder.new
    # Quiet the logger output; we only care about the emitted file.
    expect { builder.build_file(File.join(layouts_dir, 'regen_screen.json')) }.to output(/./).to_stdout
  end

  def section_calls(content)
    content.scan(/^\s*(Section\d+(?:_\d+)*)\(data, viewModel\)\s*$/).flatten.uniq.sort
  end

  def section_defs(content)
    content.scan(/private fun (Section\d+(?:_\d+)*)\(/).flatten.uniq.sort
  end

  it 'regenerating over an existing file after a structure change matches clean generation' do
    # Build v1 (clean scaffold + build)
    write_layout(section_heavy_layout(section_count: 10))
    build!
    expect(File.exist?(generated_file)).to be true
    v1 = File.read(generated_file)
    expect(section_defs(v1)).not_to be_empty

    # Change the section structure (drop several blocks) and rebuild ON TOP
    write_layout(section_heavy_layout(section_count: 6))
    build!
    incremental = File.read(generated_file)

    # Clean generation of the same v2 layout in a pristine location
    FileUtils.rm_rf(File.dirname(generated_file))
    build!
    clean = File.read(generated_file)

    # Every call must have a matching definition, in both outputs
    expect(section_calls(incremental) - section_defs(incremental)).to eq([])
    expect(section_calls(clean) - section_defs(clean)).to eq([])

    # And the incremental regeneration must be byte-identical to clean output
    expect(incremental).to eq(clean)
  end

  it 'repeated rebuilds of the same layout are byte-stable' do
    write_layout(section_heavy_layout(section_count: 8))
    build!
    first = File.read(generated_file)
    build!
    second = File.read(generated_file)
    expect(second).to eq(first)
  end
end
