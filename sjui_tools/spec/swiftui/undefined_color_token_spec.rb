# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'swiftui/views/color_helper'
require 'swiftui/views/color_palette'

# A colour name that is in no palette must be said out loud at build time.
#
# `getColor(for:)` answers from the palette copied out of colors.json, and
# `Color(hex:)` behind it returns nil for anything that is not 3/6/8 hex
# digits — so an undefined name reached `?? Color.black` and rendered black.
# On the consumer that was an error label on a dark background: the message
# was there, sized, laid out, and unreadable. Nothing in the build said so;
# the only trace was a `null` line in defined_colors.json.
#
# The fallback swap is deliberately NOT applied to defined names. For a name
# in colors.json getColor never returns nil, so `?? Color.black` there is a
# dead branch — rewriting it would have churned 1307 sites across 102 files
# on a healthy consumer and changed no pixel. The population this fix is for
# is "names in no palette", and that is the population it reaches.
RSpec.describe 'an undefined colour token' do
  let(:helper) { Class.new { extend SjuiTools::SwiftUI::Views::ColorHelper } }

  before do
    SjuiTools::SwiftUI::Views::ColorPalette.reset!
    allow(SjuiTools::SwiftUI::Views::ColorPalette).to receive(:names).and_return(%w[deep_slate paper])
  end

  after { SjuiTools::SwiftUI::Views::ColorPalette.reset! }

  it 'warns once and falls back to clear' do
    expect(SjuiTools::Core::Logger).to receive(:warn).once.with(/alert_crimson/)

    emitted = helper.get_swiftui_color('alert_crimson')

    expect(emitted).to eq('SwiftJsonUIConfiguration.shared.getColor(for: "alert_crimson") ?? Color.clear')
  end

  # Forty layouts naming the same missing colour is one authoring mistake.
  it 'warns once per name, not once per use' do
    expect(SjuiTools::Core::Logger).to receive(:warn).once

    3.times { helper.get_swiftui_color('alert_crimson') }
  end

  # The arm that keeps the fix off the healthy population. If this text ever
  # changes, every generated iOS file on every consumer changes with it.
  it 'leaves a defined name byte-identical' do
    expect(SjuiTools::Core::Logger).not_to receive(:warn)

    expect(helper.get_swiftui_color('deep_slate'))
      .to eq('SwiftJsonUIConfiguration.shared.getColor(for: "deep_slate") ?? Color.black')
  end

  # Hex is resolved by getColor itself, so it is defined even though it is in
  # no palette. Treating it as undefined would warn about every literal colour
  # in the project.
  it 'says nothing about a hex literal' do
    expect(SjuiTools::Core::Logger).not_to receive(:warn)

    expect(helper.get_swiftui_color('#EF4444'))
      .to eq('SwiftJsonUIConfiguration.shared.getColor(for: "#EF4444") ?? Color.black')
  end

  # An unreadable or absent colors.json is not an empty one. Guessing
  # "undefined" there would warn about every colour in the project and
  # rewrite every fallback.
  it 'says nothing when the palette could not be read' do
    allow(SjuiTools::SwiftUI::Views::ColorPalette).to receive(:names).and_return(nil)
    expect(SjuiTools::Core::Logger).not_to receive(:warn)

    expect(helper.get_swiftui_color('alert_crimson'))
      .to eq('SwiftJsonUIConfiguration.shared.getColor(for: "alert_crimson") ?? Color.black')
  end

  # A string assert is not a compile. `Color.clear` is the emitted token, and
  # only swiftc can say the argument list and the `??` still type-check.
  it 'emits Swift a compiler accepts' do
    allow(SjuiTools::Core::Logger).to receive(:warn)
    fragment = "Text(\"x\").foregroundColor(#{helper.get_swiftui_color('alert_crimson')})"

    expect(compilable_view(fragment)).to compile_as_swift
  end

  # The examples above stub the palette, so none of them reads colors.json
  # from disk — the path resolution, the themed schema and the mode union are
  # all unexercised there. This one runs the real build.
  describe 'reading the real colors.json' do
    REPO_ROOT = File.expand_path('../../..', __dir__)

    def project
      dir = Dir.mktmpdir('color_token')
      name = 'ColorProbe'
      File.write(File.join(dir, 'jui.config.json'), JSON.pretty_generate(
        'project_name' => name, 'spec_directory' => 'docs/screens/json',
        'component_spec_directory' => 'docs/components/json', 'strings_file' => '',
        'type_map_file' => '.jsonui-type-map.json',
        'platforms' => { 'ios' => { 'root' => '.', 'layoutsDir' => "#{name}/Layouts", 'mode' => 'swiftui' } }
      ))
      File.write(File.join(dir, 'sjui.config.json'), JSON.pretty_generate(
        'mode' => 'swiftui', 'project_name' => name, 'project_file_name' => name,
        'source_directory' => name, 'layouts_directory' => 'Layouts',
        'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
        'view_directory' => 'View', 'data_directory' => 'Data',
        'viewmodel_directory' => 'ViewModel',
        'resource_manager_directory' => 'ResourceManager',
        'string_files' => ["#{name}/Localizable.strings"], 'use_network' => true
      ))
      File.write(File.join(dir, '.jsonui-type-map.json'), '{}')
      FileUtils.mkdir_p(File.join(dir, "#{name}.xcodeproj"))
      resources = File.join(dir, name, 'Layouts', 'Resources')
      FileUtils.mkdir_p(resources)
      # Themed schema with the key in ONE mode only: the runtime resolves it
      # whenever that mode is active, so a mode-flattening predicate would
      # call `dusk_only` undefined and warn about a colour that works.
      File.write(File.join(resources, 'colors.json'), JSON.pretty_generate(
        'modes' => %w[light dark], 'fallback_mode' => 'light',
        'light' => { 'deep_slate' => '#221C10' },
        'dark' => { 'dusk_only' => '#101010' }
      ))
      File.write(File.join(dir, name, 'Layouts', 'panel.json'), JSON.generate(
        'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
        'child' => [
          { 'type' => 'Label', 'id' => 'a', 'width' => 'wrapContent', 'height' => 'wrapContent',
            'text' => 'ok', 'fontColor' => 'deep_slate' },
          { 'type' => 'Label', 'id' => 'b', 'width' => 'wrapContent', 'height' => 'wrapContent',
            'text' => 'dusk', 'fontColor' => 'dusk_only' },
          { 'type' => 'Label', 'id' => 'c', 'width' => 'wrapContent', 'height' => 'wrapContent',
            'text' => 'ng', 'fontColor' => 'alert_crimson' }
        ]
      ))
      FileUtils.ln_s(File.join(REPO_ROOT, 'sjui_tools'), File.join(dir, 'sjui_tools'))
      dir
    end

    it 'warns only for the name no mode defines' do
      dir = project
      log, = Open3.capture2e('ruby', File.join(dir, 'sjui_tools', 'bin', 'sjui'), 'build', chdir: dir)

      generated = Dir.glob(File.join(dir, '**', '*GeneratedView.swift'))
      expect(generated).not_to be_empty, "build generated nothing, so this asserts nothing\n#{log}"
      swift = generated.map { |f| File.read(f) }.join("\n")

      expect(log).to include("Color 'alert_crimson' is not defined in colors.json"), log
      expect(log).not_to include("Color 'deep_slate'"), log
      expect(log).not_to include("Color 'dusk_only'"), log

      expect(swift).to include('getColor(for: "alert_crimson") ?? Color.clear')
      expect(swift).to include('getColor(for: "deep_slate") ?? Color.black')
      expect(swift).to include('getColor(for: "dusk_only") ?? Color.black')
    ensure
      FileUtils.rm_rf(dir) if dir
    end
  end
end
