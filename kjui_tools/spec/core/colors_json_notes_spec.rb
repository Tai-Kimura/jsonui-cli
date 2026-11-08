# frozen_string_literal: true

require 'core/resources/color_manager'
require 'core/type_converter_core'
require 'json'
require 'tmpdir'
require 'fileutils'

# A `_` key in colors.json (`_comment`) is a note, not a colour or a mode.
#
# Until 2.5.14 it was a colour inside a palette and at the top of a flat file
# (which migrates into one): every face emitted a `Comment` accessor for its
# text, and the web's THEME_KEYS listed it, so cssColor('_comment') was
# `var(--color-_comment)`. At the top of a THEMED file it was the first content
# key, the file read as flat, every palette was dropped and colors.json was
# written back holding the note alone; the name lookups answered every palette
# name "not defined". Notes are kept where they were when the file is written.
#
# ColorManagerCore and TypeConverterCore are byte-identical across the three
# tools (shared/core mirror); this spec is too, but for the generated file.
RSpec.describe KjuiTools::Core::Resources::ColorManager do
  let(:temp_dir) { Dir.mktmpdir('colors_json_notes') }
  let(:resources_dir) { File.join(temp_dir, 'Resources') }
  let(:colors_path) { File.join(resources_dir, 'colors.json') }
  let(:config) { { 'resource_manager_directory' => 'gen', 'source_directory' => 'src/main' } }

  before { FileUtils.mkdir_p(resources_dir) }
  after { FileUtils.rm_rf(temp_dir) }

  def write_colors(body)
    File.write(colors_path, JSON.pretty_generate(body))
  end

  def manager
    described_class.new(config, temp_dir, resources_dir)
  end

  def generated(manager)
    manager.apply_to_color_assets
    manager.send(:generate_color_manager_kotlin)
    File.read(File.join(temp_dir, 'gen', 'ColorManager.kt'))
  end

  # The generated file, as kotlinc reads it: its Android / Compose imports are
  # stood in for by the members it uses (as resource_identifiers_spec does).
  NOTES_STUBS = <<~KOTLIN
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

  FLAT = { '_comment' => 'tokens.css, 1:1', 'ink' => '#112233' }.freeze
  IN_PALETTES = {
    'light' => { '_comment' => 'light note', 'ink' => '#112233' },
    'dark' => { '_comment' => 'dark note', 'ink' => '#000000' }
  }.freeze
  ON_TOP = { '_comment' => 'file note', 'light' => { 'ink' => '#112233' }, 'dark' => { 'ink' => '#000000' } }.freeze

  it 'a flat file: the note is no colour, and stays at the top when migrated' do
    write_colors(FLAT)
    m = manager
    m.apply_to_color_assets
    expect(m.palettes).to eq('light' => { 'ink' => '#112233' })
    written = JSON.parse(File.read(colors_path))
    expect(written['_comment']).to eq('tokens.css, 1:1')
    expect(written['light']).to eq('ink' => '#112233')
  end

  # jui build copies the source over the platform copy each build, and the
  # tool migrates it again: the note is written where the source has it (the
  # top of a flat file), and the second build leaves it there.
  it 'a flat file: the note stays on top across two builds' do
    2.times do
      write_colors(FLAT)
      manager.apply_to_color_assets
      written = JSON.parse(File.read(colors_path))
      expect(written['_comment']).to eq('tokens.css, 1:1')
      expect(written.values.grep(Hash).flat_map(&:keys)).not_to include('_comment')
    end
  end

  it 'a themed file: a note inside a palette is no colour, and is written back in that palette' do
    write_colors(IN_PALETTES)
    m = manager
    expect(m.palettes).to eq('light' => { 'ink' => '#112233' }, 'dark' => { 'ink' => '#000000' })
    expect(m.mode_complete_keys).to eq(['ink'])
    m.send(:save_colors_json)
    written = JSON.parse(File.read(colors_path))
    expect(written['light']).to eq('_comment' => 'light note', 'ink' => '#112233')
    expect(written['dark']).to eq('_comment' => 'dark note', 'ink' => '#000000')
  end

  it 'a themed file with a note on top reads as themed and is left as written' do
    write_colors(ON_TOP)
    before = File.read(colors_path)
    m = manager
    m.apply_to_color_assets
    expect(m.modes).to eq(%w[light dark])
    expect(m.palettes).to eq('light' => { 'ink' => '#112233' }, 'dark' => { 'ink' => '#000000' })
    expect(File.read(colors_path)).to eq(before)
  end

  [['flat', FLAT], ['in palettes', IN_PALETTES], ['on top', ON_TOP]].each do |label, body|
    it "the generated file names no note (#{label})" do
      write_colors(body)
      out = generated(manager)
      expect(out).not_to match(/_comment|\bComment\b/)
      expect(out).to include('ink')
    end

    it "the generated file compiles (#{label})" do
      write_colors(body)
      kotlin = generated(manager).lines.reject { |l| l.start_with?('package ', 'import ') }.join
      # The library's mode label, which ColorManager hands every mode to
      # (as resource_identifiers_spec stands it in).
      configuration = "package com.kotlinjsonui.core\nobject Configuration { fun setThemeMode(mode: String) {} }\n"
      expect("#{NOTES_STUBS}\n#{kotlin}").to compile_as_kotlin.alongside('Configuration.kt' => configuration)
    end
    it "the name lookup answers ink and not the note (#{label})" do
      names = JsonUIShared::TypeConverterCore.flatten_colors_for_lookup(JSON.parse(JSON.generate(body)))
      expect(names.keys).to eq(['ink'])
    end
  end
end
