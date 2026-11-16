# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'stringio'
require 'core/data_class_conflict'
require 'compose/data_model_updater'
require 'core/config_manager'
require 'core/project_finder'

# One data name declared twice with two types, in the Data type kjui builds
# for a screen — its includes expanded inline, so a prefix-less partial and
# the screen meet here. The first declaration in document order is kept and
# the rest dropped; until jsonui-cli 1.9.6 the drop was silent (ruling
# 2026-10-02: a warning on every face, not an error; data_class_conflict.rb).
# The same arms are on sjui (spec/swiftui/data_class_conflict_spec.rb); rjui
# builds a Data type per layout file and has its own.
RSpec.describe 'a data name declared twice with two types (kjui)' do
  let(:dir) { Dir.mktmpdir('data_class_conflict') }

  before do
    %w[Layouts/parts Data Styles].each { |d| FileUtils.mkdir_p(File.join(dir, d)) }
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
      'source_directory' => '', 'layouts_directory' => 'Layouts', 'data_directory' => 'Data',
      'styles_directory' => 'Styles', 'package_name' => 'com.example.app', 'mode' => 'compose'
    )
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
  end

  # The Data walk loads the project's type map (none here) into the
  # TypeConverter; put back what was there.
  around do |example|
    converter = KjuiTools::Core::TypeConverter
    had = converter.instance_variable_defined?(:@project_type_map)
    saved = converter.instance_variable_get(:@project_type_map) if had
    example.run
  ensure
    if had
      converter.instance_variable_set(:@project_type_map, saved)
    elsif converter.instance_variable_defined?(:@project_type_map)
      converter.remove_instance_variable(:@project_type_map)
    end
  end

  after { FileUtils.rm_rf(dir) }

  def layout(name, tree)
    File.write(File.join(dir, 'Layouts', "#{name}.json"), JSON.generate(tree))
  end

  def item(klass, default)
    { 'name' => 'title', 'class' => klass, 'defaultValue' => default }
  end

  # The screen declares first (its own data node, then the include), the
  # partial second.
  def screen(screen_item, partial_item, includes: 1)
    layout('parts/panel', 'type' => 'View', 'id' => 'panel_root', 'partial' => true,
                          'child' => [{ 'data' => [partial_item] }])
    layout('screen', 'type' => 'View', 'id' => 'root',
                     'child' => [{ 'data' => [screen_item] }] + [{ 'include' => 'parts/panel' }] * includes)
  end

  # [printed, ScreenData.kt]
  def build
    out = StringIO.new
    $stdout = out
    updater = KjuiTools::Compose::DataModelUpdater.new
    updater.send(:process_json_file, File.join(dir, 'Layouts', 'screen.json'))
    [out.string.gsub(/\e\[[0-9;]*m/, ''), File.read(File.join(dir, 'Data', 'ScreenData.kt'))]
  ensure
    $stdout = STDOUT
  end

  def warnings(printed)
    printed.lines.map(&:strip).grep(/\AWARNING: .*data property 'title' is declared as/)
  end

  it "warns once, names both types, and keeps the screen's" do
    screen(item('String', 'a'), item('Int', 7))

    printed, data = build

    expect(warnings(printed)).to eq([JsonUIShared::DataClassConflict.message('screen.json', 'title', 'String', 'Int')])
    expect(data.scan(/^\s*var title: /).size).to eq(1)
    expect(data).to include('var title: String = ')
  end

  it 'says it once for a partial included twice' do
    screen(item('String', 'a'), item('Int', 7), includes: 2)

    expect(warnings(build.first).size).to eq(1)
  end

  # The controls: what is not a conflict says nothing.
  it 'says nothing for the same type declared twice' do
    screen(item('String', 'a'), item('String', 'b'))

    printed, data = build

    expect(warnings(printed)).to be_empty
    expect(data.scan(/^\s*var title: /).size).to eq(1)
  end

  it 'compares the type it writes, not the spelling' do
    screen(item('Int', 1), item('Integer', 2))

    printed, data = build

    expect(warnings(printed)).to be_empty
    expect(data).to include('var title: Int = 1')
  end

  it 'does not compare default values' do
    screen(item('String', 'a'), item('String', 'something else'))

    expect(warnings(build.first)).to be_empty
  end

  it 'writes a Data type a compiler accepts' do
    screen(item('String', 'a'), item('Int', 7))

    expect(build.last).to compile_as_kotlin
  end
end
