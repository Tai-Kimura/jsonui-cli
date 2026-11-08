# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'core/resources/color_manager'
require_relative '../../support/kotlin_compiler'

# A colors.json with a dark mode did not reach an Android screen. A written
# colour was colorResource(R.color.x) and followed values-night only, never
# setMode; nothing kept a choice; and the OS reached ColorManager only if the
# app called applySystemMode itself (ticket rjui-color-mode-never-sets-data-
# theme; measured on an emulator). Now every generated screen calls
# compose.FollowSystem(), a written colour asks ColorManager first, setMode is
# a kept choice the OS does not override, and setFollowSystemMode(true) goes
# back to the OS. Measured here on the generated ColorManager run on the JVM,
# with Android's Context / SharedPreferences and Compose's four names stood in
# for; the next launch is a second run that starts from the first's prefs.
RSpec.describe 'the colour mode follows the OS and a kept choice (Android)', :kotlin_compile do
  let(:dir) { Dir.mktmpdir('kjui_colour_mode') }
  let(:resources_dir) { File.join(dir, 'src/main/assets/Layouts/Resources') }
  let(:config) { { 'source_directory' => 'src/main', 'package_name' => 'com.example.app' } }

  before { FileUtils.mkdir_p(resources_dir) }
  after { FileUtils.rm_rf(dir) }

  def color_manager_body
    File.write(File.join(resources_dir, 'colors.json'), JSON.generate(
      'light' => { 'surface' => '#FFFFFF' }, 'dark' => { 'surface' => '#202020' }
    ))
    manager = KjuiTools::Core::Resources::ColorManager.new(config, dir, resources_dir)
    allow(KjuiTools::Core::Logger).to receive(:info)
    manager.send(:generate_color_manager_kotlin)
    File.read(Dir.glob(File.join(dir, '**', 'ColorManager.kt')).first)
        .lines.reject { |l| l.start_with?('package ', 'import ') }.join
  end

  # Working stand-ins: prefs in a map (seeded with the last run's), the OS in a
  # var, `remember` keyed on its two keys as Compose keys it.
  def stubs(kept)
    <<~KOTLIN
      object Color { fun parseColor(value: String): Int = if (value.startsWith("#")) value.substring(1).toLong(16).toInt() else throw IllegalArgumentException(value) }
      object Log { fun w(tag: String, message: String): Int = 0 }
      class MutableState<T>(var value: T)
      fun <T> mutableStateOf(value: T): MutableState<T> = MutableState(value)
      class ComposeColor(val argb: Int)
      annotation class Composable
      val store = mutableMapOf<String, String>(#{kept ? "\"mode\" to \"#{kept}\"" : ''})
      interface SharedPreferences {
          fun getString(key: String, defValue: String?): String?
          fun edit(): Editor
          interface Editor { fun putString(key: String, value: String?): Editor; fun apply() }
      }
      object Prefs : SharedPreferences {
          override fun getString(key: String, defValue: String?) = store[key] ?: defValue
          override fun edit() = object : SharedPreferences.Editor {
              override fun putString(key: String, value: String?): SharedPreferences.Editor { store[key] = value!!; return this }
              override fun apply() {}
          }
      }
      open class Context {
          open val applicationContext: Context get() = this
          fun getSharedPreferences(name: String, mode: Int): SharedPreferences = Prefs
          companion object { const val MODE_PRIVATE = 0 }
      }
      object LocalContext { val current: Context = Context() }
      var osDark = false
      fun isSystemInDarkTheme(): Boolean = osDark
      var remembered: Pair<Any?, Any?>? = null
      fun <T> remember(key1: Any?, key2: Any?, calculation: () -> T): T? =
          if (remembered == (key1 to key2)) null else { remembered = key1 to key2; calculation() }
      // One recomposition of a generated screen: FollowSystem, then a written colour as kjui writes it.
      fun frame(label: String) {
          ColorManager.compose.FollowSystem()
          val surface = ColorManager.compose.color("surface")?.argb?.let { String.format("#%06X", it and 0xFFFFFF) }
          println("$label|${ColorManager.currentMode}|${ColorManager.isFollowingSystemMode()}|$surface|${store["mode"]}")
      }
    KOTLIN
  end

  def run(kept, steps)
    result = KotlinCompiler.run("#{stubs(kept)}\n#{color_manager_body}\nfun main() {\n#{steps}\n}\n")
    raise "did not run: #{result.errors.join("\n")}" unless result.success?

    result.output.lines.map { |l| l.strip.split('|') }
  end

  it 'takes the OS at first, keeps a choice over the OS, and goes back to the OS on setFollowSystemMode(true)' do
    out = run(nil, <<~KOTLIN)
      frame("1 first launch, light OS")
      osDark = true; frame("2 the OS turns dark")
      osDark = false; frame("3 and light again")
      ColorManager.setMode(ColorManager.ColorMode.DARK); frame("4 setMode(dark)")
      osDark = true; frame("5a the OS moves"); osDark = false; frame("5b the OS moves")
      ColorManager.setFollowSystemMode(true); frame("6 setFollowSystemMode(true), light OS")
      osDark = true; frame("7 the OS turns dark")
    KOTLIN
    expect(out.map { |o| o[1..] }).to eq([
      %w[LIGHT true #FFFFFF null], %w[DARK true #202020 null], %w[LIGHT true #FFFFFF null],
      %w[DARK false #202020 dark], %w[DARK false #202020 dark], %w[DARK false #202020 dark],
      %w[LIGHT true #FFFFFF system], %w[DARK true #202020 system]
    ])
  end

  it 'a kept choice wins over the OS at the next launch, and "system" is the OS again' do
    out = run('dark', 'frame("next launch, light OS, dark kept")')
    expect(out.first[1..3]).to eq(%w[DARK false #202020])
    out = run('system', 'osDark = true; frame("next launch, dark OS, system kept")')
    expect(out.first[1..3]).to eq(%w[DARK true #202020])
    out = run('system', 'frame("next launch, light OS, system kept")')
    expect(out.first[1..3]).to eq(%w[LIGHT true #FFFFFF])
  end
end
