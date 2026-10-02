# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'core/kotlin_identifier'
require 'core/resources/color_manager'
require 'core/resources/string_manager'

# Names kjui writes from a key are valid Kotlin / Android whatever the key —
# the Android section of ticket sjui-resource-managers-emit-swift-that-does-
# not-compile (sjui: Core::SwiftIdentifier). Only a name that does not compile
# today changes: a leading digit takes `_`, a Kotlin hard keyword is
# back-quoted where declared; a soft keyword (`open`) and every other name are
# written as before. kotlinc rejected `val 4ecdc4`, `val object`, `val when`;
# aapt2 rejected a string resource named `1_screen_…` (measured 2026-10-03).
RSpec.describe 'resource names from keys (kjui)' do
  let(:dir) { Dir.mktmpdir('kjui_resource_identifiers') }
  let(:resources_dir) { File.join(dir, 'src/main/assets/Layouts/Resources') }
  let(:config) { { 'source_directory' => 'src/main', 'package_name' => 'com.example.app' } }

  before { FileUtils.mkdir_p(resources_dir) }
  after { FileUtils.rm_rf(dir) }

  def color_manager_kotlin(colors)
    File.write(File.join(resources_dir, 'colors.json'), JSON.generate(colors))
    manager = KjuiTools::Core::Resources::ColorManager.new(config, dir, resources_dir)
    allow(KjuiTools::Core::Logger).to receive(:info)
    manager.send(:generate_color_manager_kotlin)
    File.read(Dir.glob(File.join(dir, '**', 'ColorManager.kt')).first)
  end

  KRI_COLORS = { 'light' => { '4ecdc4' => '#4ECDC4', 'object' => '#111111', 'when' => '#222222',
                          'open' => '#333333', 'primary_text' => '#444444' } }.freeze

  it 'writes a digit-led key with `_`, a hard keyword back-quoted, and every other name as before' do
    kotlin = color_manager_kotlin(KRI_COLORS)

    expect(kotlin).to include('val _4ecdc4: Int?', 'val `object`: Int?', 'val `when`: Int?')
    expect(kotlin).to include('val open: Int?', 'val primaryText: Int?')
    expect(kotlin).not_to match(/val (4ecdc4|object|when):/)
    # The key read at run time is the key as written.
    expect(kotlin).to include('color("4ecdc4")', 'color("object")')
  end

  # The generated file, as kotlinc reads it: its Android / Compose imports are
  # stood in for by the members it uses.
  KRI_STUBS = <<~KOTLIN
    object Color { fun parseColor(value: String): Int = 0 }
    object Log { fun w(tag: String, message: String): Int = 0 }
    class MutableState<T>(var value: T)
    fun <T> mutableStateOf(value: T): MutableState<T> = MutableState(value)
    class ComposeColor(val argb: Int)
  KOTLIN

  it 'writes a ColorManager kotlinc accepts' do
    kotlin = color_manager_kotlin(KRI_COLORS)
    body = kotlin.lines.reject { |l| l.start_with?('package ', 'import ') }.join

    expect("#{KRI_STUBS}\n#{body}").to compile_as_kotlin
  end

  # A string resource is named after the layout that holds it, so it starts
  # with a digit only when the layout's path does.
  it 'names the strings of a layout whose path starts with a digit with `_`, and prunes the old name' do
    layouts = File.dirname(resources_dir)
    File.write(File.join(layouts, '1_screen.json'), JSON.generate('type' => 'Label', 'text' => 'Hello there'))
    values = File.join(dir, 'src/main/res/values')
    FileUtils.mkdir_p(values)
    File.write(File.join(values, 'strings.xml'),
               %(<resources>\n  <string name="1_screen_hello_there">Hello there</string>\n</resources>\n))
    manager = KjuiTools::Core::Resources::StringManager.new(config, dir, resources_dir)
    allow(KjuiTools::Core::Logger).to receive(:info)
    allow(KjuiTools::Core::Logger).to receive(:debug)
    manager.process_strings([File.join(layouts, '1_screen.json')], 1, 0)
    manager.apply_to_strings_files

    names = File.read(File.join(values, 'strings.xml')).scan(/name=['"]([^'"]+)/).flatten
    expect(names).to include('_1_screen_hello_there')
    expect(names).not_to include('1_screen_hello_there')
  end

  it 'leaves every name that compiles as it is' do
    expect(KjuiTools::Core::KotlinIdentifier.declaration('primaryText')).to eq('primaryText')
    expect(KjuiTools::Core::KotlinIdentifier.declaration('open')).to eq('open')
    expect(KjuiTools::Core::KotlinIdentifier.resource_name('home_title')).to eq('home_title')
  end
end
