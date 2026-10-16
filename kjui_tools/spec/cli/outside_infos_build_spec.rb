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
# in the environment (`DEBUG=1 jui build`); a default build prints what it did.
#
# The tool is COPIED (links dereferenced), as the other build specs do.
RSpec.describe 'mode / platform outside INFOs, through kjui build' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  def build(*args, debug: false)
    env = { 'DEBUG' => (debug ? '1' : nil) }
    out, status = Open3.capture2e(env, RbConfig.ruby, File.join(@dir, 'kjui_tools', 'bin', 'kjui'), 'build', *args, chdir: @dir)
    [out.gsub(/\e\[[0-9;]*m/, ''), status]
  end

  before(:all) do
    @dir = Dir.mktmpdir('kjui_outside_infos')
    tool = File.join(@dir, 'kjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    File.write(File.join(@dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => 'OutsideProbe',
      'source_directory' => 'app/src/main', 'layouts_directory' => 'assets/Layouts',
      'styles_directory' => 'assets/Styles',
      'data_directory' => 'kotlin/com/example/app/data',
      'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'view_directory' => 'kotlin/com/example/app/views',
      'extension_directory' => 'kotlin/com/example/app/extensions',
      'adapter_directory' => 'kotlin/com/example/app/adapters',
      'resource_manager_directory' => 'app/src/main/kotlin/com/kotlinjsonui/generated',
      'package_name' => 'com.example.app',
      'string_files' => ['res/values/strings.xml'], 'use_network' => true
    ))
    layouts = File.join(@dir, 'app', 'src', 'main', 'assets', 'Layouts')
    FileUtils.mkdir_p(File.join(@dir, 'app', 'src', 'main', 'assets', 'Styles'))
    FileUtils.mkdir_p(layouts)
    node = ->(type, id, extra = {}) { { 'type' => type, 'id' => id, 'width' => 'matchParent', 'height' => 'wrapContent' }.merge(extra) }
    File.write(File.join(layouts, 'drag.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical',
      'child' => [
        { 'data' => [{ 'name' => 'onDragStart', 'class' => '(() -> Void)?' }, { 'name' => 'onHold', 'class' => '(() -> Void)?' }] },
        node.call('View', 'dropzone', 'onDragStart' => '@{onDragStart}'),
        node.call('View', 'holder', 'onLongPress' => '@{onHold}'),
        node.call('Label', 'title', 'text' => 'hello')
      ]
    ))
    @default, @default_status = build
    @cached, @cached_status = build(debug: true)
    @fresh, @fresh_status = build('--clean', debug: true)
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def info_lines(log)
    log.lines.grep(/\[KJUI Info\] /).map(&:chomp)
  end

  it 'builds' do
    expect(@default_status).to be_success, @default[-3000..]
    expect(@cached_status).to be_success, @cached[-3000..]
  end

  it 'prints no INFO in a default build' do
    expect(info_lines(@default)).to be_empty, @default
    expect(@default).not_to include('Not built here')
  end

  it 'names the attribute, component and platform in a verbose build (cached layout)' do
    expect(info_lines(@cached)).to eq(["ℹ️  [KJUI Info] [drag.json] [id=dropzone] Attribute 'onDragStart' in 'View' is for React platform (current: Kotlin)"]), @cached
    expect(@cached).to include('Not built here (another mode or platform): 1 attribute(s)')
  end

  it 'names it in a fresh verbose build' do
    expect(@fresh_status).to be_success, @fresh[-3000..]
    expect(info_lines(@fresh)).to eq(info_lines(@cached)), @fresh
  end
end
