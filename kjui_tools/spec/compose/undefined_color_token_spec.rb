# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# `android.graphics.Color.parseColor` takes hex and its own 23 names and
# throws IllegalArgumentException on everything else. A colour name absent
# from colors.json was handed to it verbatim, so an authoring mistake became
# a crash at the moment the composable was composed — and on the consumer the
# colour styled an error label behind a `visibility` binding, so it crashed
# only once the error it was meant to display finally appeared.
#
# The build knew. `find_color_key` had already returned nil; nothing said so.
#
# What must NOT change is the defined name: it emits `colorResource(R.color.x)`
# and always did. The population this fix is for is "names in no palette".
RSpec.describe 'an undefined colour token on Compose' do
  REPO_ROOT = File.expand_path('../../..', __dir__)

  # `Color.Unspecified` and `Color(android.graphics.Color.parseColor(...))`
  # need the SAME import — `androidx.compose.ui.graphics.Color` — because the
  # outer `Color(...)` in the old form is that class. So the swap cannot
  # produce a dangling reference, and the generated-view base import list
  # carries it unconditionally.
  def project
    dir = Dir.mktmpdir('kjui_color')
    File.write(File.join(dir, 'jui.config.json'), JSON.pretty_generate(
      'project_name' => 'CProbe', 'spec_directory' => 'docs/screens/json',
      'component_spec_directory' => 'docs/components/json', 'strings_file' => '',
      'type_map_file' => '.jsonui-type-map.json',
      'platforms' => { 'android' => { 'root' => '.', 'layoutsDir' => 'app/src/main/assets/Layouts', 'mode' => 'compose' } }
    ))
    File.write(File.join(dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => 'CProbe',
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
    File.write(File.join(dir, '.jsonui-type-map.json'), '{}')
    layouts = File.join(dir, 'app', 'src', 'main', 'assets', 'Layouts')
    FileUtils.mkdir_p(File.join(layouts, 'Resources'))
    FileUtils.mkdir_p(File.join(dir, 'app', 'src', 'main', 'assets', 'Styles'))
    File.write(File.join(layouts, 'Resources', 'colors.json'),
               JSON.pretty_generate('deep_slate' => '#221C10'))
    File.write(File.join(layouts, 'panel.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => [
        label('a', 'deep_slate'), label('b', 'alert_crimson'),
        label('c', '#EF4444'), label('d', 'red')
      ]
    ))
    # A second layout naming the same missing colour: one mistake, one line.
    File.write(File.join(layouts, 'other.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => [label('e', 'alert_crimson')]
    ))
    FileUtils.ln_s(File.join(REPO_ROOT, 'kjui_tools'), File.join(dir, 'kjui_tools'))
    dir
  end

  def label(id, color)
    { 'type' => 'Label', 'id' => id, 'width' => 'wrapContent', 'height' => 'wrapContent',
      'text' => id, 'fontColor' => color }
  end

  def build(dir)
    Open3.capture2e('ruby', File.join(dir, 'kjui_tools', 'bin', 'kjui'), 'build', chdir: dir)
  end

  def emitted(dir)
    Dir.glob(File.join(dir, '**', '*GeneratedView.kt')).map { |f| File.read(f) }.join("\n")
  end

  it 'names the undefined colour and emits one that composes' do
    dir = project
    log, = build(dir)
    kotlin = emitted(dir)
    expect(kotlin).not_to be_empty, "build generated nothing, so this asserts nothing\n#{log}"

    expect(log).to include("Color 'alert_crimson' is not defined in colors.json"), log
    expect(kotlin).to include('color = Color.Unspecified')
    expect(kotlin).not_to include('parseColor("alert_crimson")')
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  # The arm that keeps the fix off the healthy population.
  #
  # A hex literal never reaches this branch at all: the colour extractor runs
  # first and rewrites it to a generated palette key, so what codegen sees is
  # already `colorResource(...)`. Measured — the first cut of this example
  # asserted `parseColor("#EF4444")` and failed on the real build.
  it 'leaves a defined name and an Android colour name alone' do
    dir = project
    log, = build(dir)
    kotlin = emitted(dir)

    expect(kotlin).to include('colorResource(R.color.deep_slate)')
    expect(kotlin).to include('parseColor("red")')
    expect(kotlin).not_to include('parseColor("#')
    expect(log).not_to include("Color 'deep_slate'"), log
    expect(log).not_to include("Color 'red'"), log
    expect(log).not_to match(/Color '#/), log
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  it 'warns once for a name used in two layouts' do
    dir = project
    log, = build(dir)

    expect(log.scan("Color 'alert_crimson' is not defined").size).to eq(1), log
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  # A string assert is not a compile. The expressions are taken from the
  # generated file rather than retyped, so the arm tracks the emitter.
  #
  # ⚠️ LIMIT: without the Compose compiler plugin this checks TYPES against
  # stubs — @Composable call context and stability inference are not checked.
  describe 'the emitted colour expressions compile', :kotlin_compile do
    it 'accepts every shape this emitter produces' do
      dir = project
      build(dir)
      kotlin = emitted(dir)
      exprs = kotlin.scan(/color = (Color\.Unspecified|colorResource\([^)]*\)|Color\(android\.graphics\.Color\.parseColor\("[^"]*"\)\))/)
                    .flatten.uniq
      expect(exprs.size).to be >= 3, "expected the fixture's colour shapes, got #{exprs.inspect}"

      # The extractor invents key names for hex literals, so the stub's R
      # members are read off the emitted code rather than listed by hand.
      keys = exprs.grep(/colorResource/).map { |e| e[/R\.color\.(\w+)/, 1] }.compact.uniq
      body = exprs.each_with_index.map { |e, i| "    val c#{i}: Color = #{e}" }.join("\n")
      expect(<<~KOTLIN).to compile_as_kotlin
        package emitted

        class Color(val argb: Long) {
            companion object { val Unspecified = Color(0L) }
        }
        object android {
            object graphics {
                object Color {
                    fun parseColor(s: String): Long = 0L
                }
            }
        }
        object R { object color {
        #{keys.map { |k| "    const val #{k}: Int = 1" }.join("\n")}
        } }
        fun colorResource(id: Int): Color = Color(0L)

        fun emitted() {
        #{body}
        }
      KOTLIN
    ensure
      FileUtils.rm_rf(dir) if dir
    end
  end
end
