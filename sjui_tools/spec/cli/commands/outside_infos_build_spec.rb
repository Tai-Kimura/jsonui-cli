# frozen_string_literal: true

require 'open3'
require 'rbconfig'
require 'tmpdir'
require 'json'
require 'fileutils'

# An attribute the build leaves out as another mode's or platform's — a web
# drag handler on sjui / kjui, written legitimately by a shared layout — was kept as an
# INFO that no build printed: `validate` resets its INFOs on every node and
# nothing called print_infos (ticket jui-build-mode-outside-infos-are-
# collected-and-never-printed). Ruling: named in a verbose build only, DEBUG
# in the environment (`DEBUG=1 jui build`, or sjui's own --verbose); a default build prints what it did.
#
# The tool is COPIED (links dereferenced), as the other build specs do.
RSpec.describe 'mode / platform outside INFOs, through sjui build' do
  def tool_root
    File.expand_path('../../..', __dir__)
  end

  def build(*args, debug: false)
    env = { 'DEBUG' => (debug ? '1' : nil) }
    out, status = Open3.capture2e(env, RbConfig.ruby, File.join(@dir, 'sjui_tools', 'bin', 'sjui'), 'build', *args, chdir: @dir)
    [out.gsub(/\e\[[0-9;]*m/, ''), status]
  end

  before(:all) do
    @dir = Dir.mktmpdir('sjui_outside_infos')
    tool = File.join(@dir, 'sjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    name = 'OutsideProbe'
    File.write(File.join(@dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => 'swiftui', 'project_name' => name, 'project_file_name' => name,
      'source_directory' => name, 'layouts_directory' => 'Layouts',
      'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
      'view_directory' => 'View', 'data_directory' => 'Data',
      'viewmodel_directory' => 'ViewModel',
      'resource_manager_directory' => 'ResourceManager',
      'string_files' => ["#{name}/Localizable.strings"], 'use_network' => true
    ))
    FileUtils.mkdir_p(File.join(@dir, "#{name}.xcodeproj"))
    layouts = File.join(@dir, name, 'Layouts')
    FileUtils.mkdir_p(layouts)
    node = ->(type, id, extra = {}) { { 'type' => type, 'id' => id, 'width' => 'matchParent', 'height' => 'wrapContent' }.merge(extra) }
    File.write(File.join(layouts, 'drag.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical',
      'child' => [
        { 'data' => [{ 'name' => 'onDragStart', 'class' => '(() -> Void)?' }, { 'name' => 'onHold', 'class' => '(() -> Void)?' }, { 'name' => 'mode', 'class' => 'String' }] },
        node.call('View', 'dropzone', 'onDragStart' => '@{onDragStart}'),
        node.call('View', 'holder', 'onLongPress' => '@{onHold}'),
        node.call('Image', 'photo', 'srcName' => 'icon', 'contentMode' => '@{mode}'),
        node.call('Label', 'title', 'text' => 'hello')
      ]
    ))
    @default, @default_status = build
    @cached, @cached_status = build(debug: true)
    @fresh, @fresh_status = build('--clean', debug: true)
    @flag, @flag_status = build('--verbose')
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def info_lines(log)
    log.lines.grep(/\[SJUI Info\] /).map(&:chomp)
  end

  it 'builds' do
    expect(@default_status).to be_success, @default[-3000..]
    expect(@cached_status).to be_success, @cached[-3000..]
  end

  it 'prints no INFO in a default build' do
    expect(info_lines(@default)).to be_empty, @default
    expect(@default).not_to include('Not built here')
    expect(@default).not_to include('Bound with a limitation')
  end

  it 'names the attribute, component and platform in a verbose build (cached layout)' do
    expect(info_lines(@cached).grep(/Attribute '/)).to eq(["ℹ️  [SJUI Info] [drag.json] [drag id=dropzone] Attribute 'onDragStart' in 'View' is for React platform (current: Swift)"]), @cached
    expect(@cached).to include('Not built here (another mode or platform): 1 attribute(s)')
  end

  # The bound values with a limitation declared on this face (`bindingInfo`)
  # were the same INFO, printed by no build (ticket
  # jui-build-binding-infos-are-collected-and-never-printed).
  it 'names a bound value with a declared limitation in a verbose build' do
    bound = info_lines(@cached).grep(/is bound: /)
    expect(bound.size).to eq(1), @cached
    expect(bound.first).to start_with("ℹ️  [SJUI Info] [drag.json] [drag id=photo] 'contentMode' on Image is bound: a contentMode bound to a value that is AspectFill")
    expect(@cached).to include('Bound with a limitation on this platform: 1 attribute(s)')
  end

  it 'names it in a fresh verbose build, and under sjui --verbose' do
    expect(@fresh_status).to be_success, @fresh[-3000..]
    expect(info_lines(@fresh)).to eq(info_lines(@cached)), @fresh
    expect(@flag_status).to be_success, @flag[-3000..]
    expect(info_lines(@flag)).to eq(info_lines(@cached)), @flag
  end
end
