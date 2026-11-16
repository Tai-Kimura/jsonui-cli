# frozen_string_literal: true

require 'open3'
require 'rbconfig'
require 'tmpdir'
require 'json'
require 'fileutils'

# An attribute the build leaves out as another mode's or platform's — a web
# drag handler on sjui / kjui, and an iOS / Android one on rjui, written legitimately by a shared layout — was kept as an
# INFO that no build printed: `validate` resets its INFOs on every node and
# nothing called print_infos (ticket jui-build-mode-outside-infos-are-
# collected-and-never-printed). Ruling: named in a verbose build only, DEBUG
# in the environment (`DEBUG=1 jui build`); a default build prints what it did.
#
# The tool is COPIED (links dereferenced), as the other build specs do.
RSpec.describe 'mode / platform outside INFOs, through rjui build' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  def build(*args, debug: false)
    env = { 'DEBUG' => (debug ? '1' : nil) }
    out, status = Open3.capture2e(env, RbConfig.ruby, File.join(@dir, 'rjui_tools', 'bin', 'rjui'), 'build', *args, chdir: @dir)
    [out.gsub(/\e\[[0-9;]*m/, ''), status]
  end

  before(:all) do
    @dir = Dir.mktmpdir('rjui_outside_infos')
    tool = File.join(@dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    # The SSoT declares `bindingInfo` for swift only (Image / NetworkImage
    # contentMode); an extension definition declares one for this face, so
    # this build has a bound value to name.
    shipped = JSON.parse(File.read(File.join(tool, 'lib', 'core', 'attribute_definitions.json')))
    ext = File.join(tool, 'lib', 'react', 'converters', 'extensions', 'attribute_definitions')
    FileUtils.mkdir_p(ext)
    File.write(File.join(ext, 'bound_probe.json'), JSON.generate(
      'Image' => { 'contentMode' => shipped['Image']['contentMode'].merge(
        'bindingInfo' => { 'platform' => ['react'], 'note' => 'a probe limitation declared for this face.' }
      ) }
    ))
    # No rjui.config.json: rjui writes its defaults (layouts in src/Layouts).
    layouts = File.join(@dir, 'src', 'Layouts')
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

  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def info_lines(log)
    log.lines.grep(/\[RJUI Info\] /).map(&:chomp)
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
    expect(info_lines(@cached).grep(/Attribute '/)).to eq(["ℹ️  [RJUI Info] [src/Layouts/drag.json] [id=holder] Attribute 'onLongPress' in 'View' is for Swift/Kotlin platform (current: React)"]), @cached
    expect(@cached).to include('Not built here (another mode or platform): 1 attribute(s)')
  end

  # The bound values with a limitation declared on this face (`bindingInfo`)
  # were the same INFO, printed by no build (ticket
  # jui-build-binding-infos-are-collected-and-never-printed).
  it 'names a bound value with a declared limitation in a verbose build' do
    expect(info_lines(@cached).grep(/is bound: /)).to eq(["ℹ️  [RJUI Info] [src/Layouts/drag.json] [id=photo] 'contentMode' on Image is bound: a probe limitation declared for this face."]), @cached
    expect(@cached).to include('Bound with a limitation on this platform: 1 attribute(s)')
  end
end
