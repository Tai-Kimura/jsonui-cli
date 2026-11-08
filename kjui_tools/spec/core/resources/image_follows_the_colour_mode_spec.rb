# frozen_string_literal: true

require 'json'
require 'set'
require 'tmpdir'
require 'fileutils'
require 'core/resources/color_manager'
require 'compose/compose_builder'
require_relative '../../support/kotlin_compiler'

# An image could not follow the colour mode: jui build wrote one drawable from
# <name>.svg and nothing chose another (ticket jui-images-no-per-color-mode-
# variants). Now <name>.<mode>.svg is the drawable <name>__<mode>, jui build
# writes the table image_modes.json beside colors.json, and the screen asks
# ColorManager for the current mode's picture: a written name through
# compose.drawable(R.drawable.<name>, "<mode>" to R.drawable.<name>__<mode>),
# a bound name through compose.drawableName. ColorManager also hands every mode
# to the library's label (Configuration.setThemeMode), which Dynamic reads.
# Without a mode's picture, nothing new is written.
RSpec.describe 'an image follows the colour mode (Android)' do
  let(:dir) { Dir.mktmpdir('kjui_image_modes') }
  let(:resources_dir) { File.join(dir, 'src/main/assets/Layouts/Resources') }
  let(:config) { { 'source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts', 'package_name' => 'com.example.app' } }
  let(:table) { { 'version' => 1, 'images' => { 'ic_probe' => { 'dark' => 'ic_probe__dark', 'sepia' => 'ic_probe__sepia' } } } }

  before do
    FileUtils.mkdir_p(resources_dir)
    File.write(File.join(resources_dir, 'colors.json'), JSON.generate(
      'light' => { 'surface' => '#FFFFFF' }, 'dark' => { 'surface' => '#202020' }, 'sepia' => { 'surface' => '#F3E7D3' }
    ))
    allow(KjuiTools::Core::Logger).to receive(:info)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
  end
  after { FileUtils.rm_rf(dir) }

  def with_table
    File.write(File.join(resources_dir, 'image_modes.json'), JSON.generate(table))
  end

  def color_manager_kt
    KjuiTools::Core::Resources::ColorManager.new(config, dir, resources_dir).send(:generate_color_manager_kotlin)
    File.read(Dir.glob(File.join(dir, '**', 'ColorManager.kt')).first)
  end

  def image(attrs)
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, { 'type' => 'Image', 'id' => 'p', 'width' => 24, 'height' => 24 }.merge(attrs), 0).to_s
  end

  describe 'what is written' do
    it 'writes nothing new for a project without a mode picture, and the library label in every project' do
      kt = color_manager_kt
      expect(kt).not_to include('fun drawable(')
      expect(kt).not_to include('imageModes')
      expect(kt).to include('com.kotlinjsonui.core.Configuration.setThemeMode(mode.raw)')
      expect(image('srcName' => 'ic_probe')).to include('painterResource(id = R.drawable.ic_probe)')
    end

    it "asks ColorManager for a written name with a mode's picture, naming each picture as an R reference" do
      with_table
      expect(color_manager_kt).to include('fun drawable(base: Int, vararg byMode: Pair<String, Int>): Int')
      expect(image('srcName' => 'ic_probe')).to include(
        'painterResource(id = com.kotlinjsonui.generated.ColorManager.compose.drawable(R.drawable.ic_probe, ' \
        '"dark" to R.drawable.ic_probe__dark, "sepia" to R.drawable.ic_probe__sepia))'
      )
      expect(image('srcName' => 'ic_plain')).to include('painterResource(id = R.drawable.ic_plain)')
    end

    it 'looks a bound name up through ColorManager once the project has a mode picture' do
      expect(image('srcName' => '@{icon}')).to include('getIdentifier(data.icon, "drawable"')
      with_table
      expect(image('srcName' => '@{icon}')).to include('getIdentifier(com.kotlinjsonui.generated.ColorManager.compose.drawableName(data.icon), "drawable"')
    end
  end

  describe 'run on the JVM', :kotlin_compile do
    IMAGE_MODE_CONFIGURATION = <<~KOTLIN
      package com.kotlinjsonui.core
      object Configuration {
          var currentThemeMode: String = "light"
          fun setThemeMode(mode: String) { currentThemeMode = mode }
      }
    KOTLIN

    def stubs
      <<~KOTLIN
        object Color { fun parseColor(value: String): Int = if (value.startsWith("#")) value.substring(1).toLong(16).toInt() else throw IllegalArgumentException(value) }
        object Log { fun w(tag: String, message: String): Int = 0 }
        class MutableState<T>(var value: T)
        fun <T> mutableStateOf(value: T): MutableState<T> = MutableState(value)
        class ComposeColor(val argb: Int)
        annotation class Composable
        interface SharedPreferences {
            fun getString(key: String, defValue: String?): String?
            fun edit(): Editor
            interface Editor { fun putString(key: String, value: String?): Editor; fun apply() }
        }
        val store = mutableMapOf<String, String>()
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
        // R.drawable as ids; one recomposition of a screen with a written and a bound image.
        object R { object drawable { const val ic_probe = 1; const val ic_probe__dark = 2; const val ic_probe__sepia = 3 } }
        fun frame(label: String) {
            ColorManager.compose.FollowSystem()
            val written = ColorManager.compose.drawable(R.drawable.ic_probe, "dark" to R.drawable.ic_probe__dark, "sepia" to R.drawable.ic_probe__sepia)
            val bound = ColorManager.compose.drawableName("ic_probe")
            println("$label|$written|$bound|${com.kotlinjsonui.core.Configuration.currentThemeMode}")
        }
      KOTLIN
    end

    it "draws the current mode's picture, the base where the mode has none, and hands the mode to the library" do
      with_table
      body = color_manager_kt.lines.reject { |l| l.start_with?('package ', 'import ') }.join
      result = KotlinCompiler.run("#{stubs}\n#{body}\nfun main() {\n#{<<~KOTLIN}\n}\n", files: { 'Configuration.kt' => IMAGE_MODE_CONFIGURATION })
        frame("1 first launch, light OS")
        osDark = true; frame("2 the OS turns dark")
        ColorManager.setMode(ColorManager.ColorMode.SEPIA); frame("3 setMode(sepia)")
        osDark = false; frame("4 the OS turns light under the choice")
        ColorManager.setMode(ColorManager.ColorMode.LIGHT); frame("5 setMode(light)")
        ColorManager.setFollowSystemMode(true); osDark = true; frame("6 back to the OS, dark")
      KOTLIN
      raise "did not run: #{result.errors.join("\n")}" unless result.success?

      expect(result.output.lines.map { |l| l.strip.split('|')[1..] }).to eq([
        %w[1 ic_probe light], %w[2 ic_probe__dark dark], %w[3 ic_probe__sepia sepia],
        %w[3 ic_probe__sepia sepia], %w[1 ic_probe light], %w[2 ic_probe__dark dark]
      ])
    end
  end
end
