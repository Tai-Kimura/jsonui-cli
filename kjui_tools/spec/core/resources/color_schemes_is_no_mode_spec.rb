# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'core/resources/color_manager'
require_relative '../../support/kotlin_compiler'

# colors.json's colorSchemes ({"sepia": "dark"}: the color-scheme the web
# draws the browser's own parts with) is a setting like systemModeMapping:
# neither a mode nor a colour on Android, first in the file or beside a note,
# and the write-back keeps it (ticket 2026-11-08-web-colour-mode-has-no-color-scheme).
RSpec.describe 'colorSchemes is a setting, not a mode (Android)' do
  let(:dir) { Dir.mktmpdir('kjui_color_schemes') }
  let(:resources_dir) { File.join(dir, 'src/main/assets/Layouts/Resources') }
  let(:config) { { 'source_directory' => 'src/main', 'package_name' => 'com.example.app' } }

  before { FileUtils.mkdir_p(resources_dir) }
  after { FileUtils.rm_rf(dir) }

  it 'is not a ColorMode, names no colour, and is written back' do
    File.write(File.join(resources_dir, 'colors.json'), JSON.generate(
      'colorSchemes' => { 'sepia' => 'dark' }, '_comment' => 'a note',
      'light' => { 'surface' => '#FFFFFF' }, 'sepia' => { 'surface' => '#F3E7D3' }
    ))
    allow(KjuiTools::Core::Logger).to receive(:info)
    manager = KjuiTools::Core::Resources::ColorManager.new(config, dir, resources_dir)
    expect(manager.modes).to eq(%w[light sepia])
    expect(manager.color_scheme('sepia')).to eq('dark')
    manager.send(:generate_color_manager_kotlin)
    kt = File.read(Dir.glob(File.join(dir, '**', 'ColorManager.kt')).first)
    expect(kt.scan(/^        ([A-Z_]+)\("/).flatten).to eq(%w[LIGHT SEPIA])
    expect(kt).not_to include('colorSchemes')
    # and the file is Kotlin kotlinc takes (the names Android and Compose give, stood in for)
    stubs = <<~KOTLIN
      object Color { fun parseColor(value: String): Int = 0 }
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
      abstract class Context {
          abstract val applicationContext: Context
          abstract fun getSharedPreferences(name: String, mode: Int): SharedPreferences
          companion object { const val MODE_PRIVATE = 0 }
      }
      object LocalContext { val current: Context get() = throw IllegalStateException() }
      fun isSystemInDarkTheme(): Boolean = false
      fun <T> remember(key1: Any?, key2: Any?, calculation: () -> T): T = calculation()
    KOTLIN
    configuration = "package com.kotlinjsonui.core\nobject Configuration { fun setThemeMode(mode: String) {} }\n"
    body = kt.lines.reject { |l| l.start_with?('package ', 'import ') }.join
    expect("#{stubs}\n#{body}").to compile_as_kotlin.alongside('Configuration.kt' => configuration)
    manager.send(:save_colors_json)
    expect(JSON.parse(File.read(File.join(resources_dir, 'colors.json')))['colorSchemes']).to eq('sepia' => 'dark')
  end
end
