# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# The build cache reads what the generated code is made from besides the
# layouts: this tool's own code, the project's extension components (their
# attribute definitions and converters) and the config. It read the layouts
# alone, so a component regenerated or edited, or the tool replaced
# (`jui sync_tool`), was followed by a build that kept every generated view
# until `--clean` (measured 2026-09-26 on f16f3a11: a converter, a definition
# and a built-in converter edited — each build "all cached", 0 views
# rewritten). Ticket build-cache-ignores-a-changed-component-definition-or-
# converter.
#
# One project, builds in a row; before each, every layout goes back to ONE
# fixed moment an hour before the first build, so each answer is the cache's
# and not the second a build started in.
RSpec.describe 'the sjui build cache reads the tool and the components' do
  def tool_root
    File.expand_path('../../..', __dir__)
  end

  def run(*args)
    out, = Open3.capture2e('ruby', File.join(@dir, 'sjui_tools', 'bin', 'sjui'), *args, chdir: @dir)
    out.gsub(/\e\[[0-9;]*m/, '')
  end

  def age_layouts
    @past ||= Time.at(Time.now.to_i - 3600)
    Dir.glob(File.join(@layouts, '*.json')).each { |f| File.utime(@past, @past, f) }
  end

  def build
    age_layouts
    run('build')
  end

  def extensions
    Dir.glob(File.join(@dir, 'sjui_tools', 'lib', '**', 'extensions'))
       .find { |d| File.directory?(File.join(d, 'attribute_definitions')) }
  end

  before(:all) do
    @dir = Dir.mktmpdir('sjui_cache_inputs')
    tool = File.join(@dir, 'sjui_tools')
    FileUtils.mkdir_p(tool)
    # `-L`: lib/core's files are relative links into shared/core.
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    File.write(File.join(@dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => 'swiftui', 'project_name' => 'CacheInputs', 'project_file_name' => 'CacheInputs',
      'source_directory' => 'CacheInputs', 'layouts_directory' => 'Layouts',
      'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
      'view_directory' => 'View', 'data_directory' => 'Data',
      'viewmodel_directory' => 'ViewModel',
      'resource_manager_directory' => 'ResourceManager',
      'string_files' => ['CacheInputs/Localizable.strings'], 'use_network' => true
    ))
    FileUtils.mkdir_p(File.join(@dir, 'CacheInputs.xcodeproj'))
    @layouts = File.join(@dir, 'CacheInputs', 'Layouts')
    FileUtils.mkdir_p(@layouts)
    run('g', 'converter', 'Box', '--attributes', 'title:String', '--container', '--force')
    File.write(File.join(@layouts, 'screen.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => [{ 'type' => 'Box', 'id' => 'box', 'title' => 't', 'width' => 'matchParent', 'height' => 'wrapContent',
                    'child' => [{ 'type' => 'Label', 'id' => 'kid', 'text' => 'kid', 'width' => 'wrapContent', 'height' => 'wrapContent' }] }]
    ))
    @first = build
    @unchanged = build # D0

    converter = Dir.glob(File.join(extensions, '**', '*box*.rb')).first
    File.write(converter, "#{File.read(converter)}\n# edited by hand\n")
    @converter_edited = build # D2

    definition = File.join(extensions, 'attribute_definitions', 'Box.json')
    json = JSON.parse(File.read(definition))
    json['Box']['subtitle'] = { 'type' => 'string' }
    File.write(definition, JSON.pretty_generate(json))
    @definition_edited = build # D3

    builtin = File.join(@dir, 'sjui_tools', 'lib', 'swiftui', 'views', 'label_converter.rb')
    File.write(builtin, "#{File.read(builtin)}\n# edited: a replaced tool\n")
    @tool_edited = build # D4
    @again = build # and settled again
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  it 'builds, then caches an untouched project (the control)' do
    expect(@first).to include('Updating 1 of 1 files'), @first
    expect(@unchanged).to include('No files need updating (all cached)'), @unchanged
  end

  {
    converter_edited: "an extension component's converter edited",
    definition_edited: "an extension component's attribute definition edited",
    tool_edited: 'a built-in converter of the tool edited (a replaced tool)'
  }.each do |log, change|
    it "converts every layout again after #{change}, the layouts untouched" do
      text = instance_variable_get("@#{log}")
      expect(text).to include('every layout is converted'), text
      expect(text).to include('Updating 1 of 1 files'), text
    end
  end

  it 'caches again once the change is built' do
    expect(@again).to include('No files need updating (all cached)'), @again
  end
end
