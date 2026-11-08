# frozen_string_literal: true

require 'tmpdir'
require 'json'
require 'fileutils'
require_relative '../../../lib/core/resources/color_manager'
require_relative '../../../lib/core/logger'
require_relative '../../../lib/core/type_converter'

# The browser's own parts (form controls, scrollbars) did not follow the colour
# mode: neither theme.css nor a chosen mode's <style> said color-scheme, so they
# were light in every mode, dark included (measured in Chromium, WebKit and
# Firefox — ticket 2026-11-08-web-colour-mode-has-no-color-scheme). Now each
# mode's color-scheme rides with its colours: the OS appearance
# systemModeMapping maps to it, or what colors.json's colorSchemes says, or
# light (said once by the build). colorSchemes is a setting like
# systemModeMapping: neither a colour nor a mode.
RSpec.describe "the browser's own parts follow the colour mode (web)" do
  let(:temp_dir) { Dir.mktmpdir('color_scheme') }
  let(:resources_dir) { File.join(temp_dir, 'Resources') }
  let(:generated) { File.join(temp_dir, 'src', 'generated') }
  let(:config) { { 'generated_directory' => 'src/generated' } }
  let(:base) do
    { 'modes' => %w[light dark sepia midnight], 'fallback_mode' => 'light',
      'systemModeMapping' => { 'light' => 'light', 'dark' => 'dark' },
      'light' => { 'surface' => '#FFFFFF' }, 'dark' => { 'surface' => '#202020' },
      'sepia' => { 'surface' => '#F3E7D3' }, 'midnight' => { 'surface' => '#000010' } }
  end
  let(:warned) { [] }

  before do
    FileUtils.mkdir_p(resources_dir)
    allow(RjuiTools::Core::Logger).to receive(:info)
    allow(RjuiTools::Core::Logger).to receive(:warn) { |m| warned << m }
  end
  after { FileUtils.rm_rf(temp_dir) }

  def manager(colors)
    File.write(File.join(resources_dir, 'colors.json'), JSON.generate(colors))
    dummy = File.join(temp_dir, 'dummy.json')
    File.write(dummy, JSON.generate('type' => 'View'))
    RjuiTools::Core::Resources::ColorManager.new(config, temp_dir, resources_dir).tap { |m| m.process_colors([dummy], 1, 0, config) }
  end

  def theme_css
    File.read(File.join(generated, 'theme.css'))
  end

  it 'takes a mode from the OS appearance mapped to it, from colorSchemes, or light' do
    m = manager(base.merge('colorSchemes' => { 'midnight' => 'dark' }))
    expect(%w[light dark sepia midnight].map { |mode| m.color_scheme(mode) }).to eq(%w[light dark light dark])
    expect(manager(base.merge('colorSchemes' => { 'dark' => 'light' })).color_scheme('dark')).to eq('light')
    expect(manager(base.merge('colorSchemes' => { 'sepia' => 'purple' })).color_scheme('sepia')).to eq('light')
  end

  it "writes each mode's color-scheme with the colours' selectors, and in a chosen mode's rule" do
    m = manager(base.merge('colorSchemes' => { 'midnight' => 'dark' }))
    css = theme_css
    expect(css).to include(':root { color-scheme: light; }',
                           ':root[data-theme="dark"] { color-scheme: dark; }',
                           ':root[data-theme="sepia"] { color-scheme: light; }',
                           ':root[data-theme="midnight"] { color-scheme: dark; }')
    expect(css).to match(/@media \(prefers-color-scheme: dark\) \{\n  :root:not\(\[data-theme\]\) \{ color-scheme: dark; \}\n\}/)
    expect(m.mode_css('midnight')).to end_with('color-scheme:dark}')
    expect(m.mode_css('sepia')).to end_with('color-scheme:light}')
  end

  it 'says once which modes are light only because nothing says otherwise' do
    manager(base)
    said = warned.select { |w| w.include?('color-scheme') || w.include?("browser's own parts") }
    expect(said.size).to eq(1)
    expect(said.first).to include("'sepia'", "'midnight'", '"colorSchemes"')
    warned.clear
    manager(base.merge('colorSchemes' => { 'sepia' => 'light', 'midnight' => 'dark' }))
    expect(warned.grep(/own parts/)).to eq([])
  end

  it 'a light-only project draws them light, and is told nothing' do
    manager('light' => { 'surface' => '#FFFFFF' })
    expect(theme_css).to include(':root { color-scheme: light; }')
    expect(theme_css).not_to include('data-theme')
    expect(warned.grep(/own parts/)).to eq([])
  end

  it 'colorSchemes is neither a mode nor a colour, first in the file or beside a note, and survives the write-back' do
    colors = { 'colorSchemes' => { 'sepia' => 'dark' }, '_comment' => 'a note' }.merge(base)
    m = manager(colors)
    expect(m.modes).to eq(%w[light dark sepia midnight])
    expect(m.color_scheme('sepia')).to eq('dark')
    expect(File.read(File.join(generated, 'ColorManager.js'))).not_to include('colorSchemes')
    written = JSON.parse(File.read(File.join(resources_dir, 'colors.json')))
    expect(written['colorSchemes']).to eq('sepia' => 'dark')
    expect(written['_comment']).to eq('a note')
    flat = JsonUIShared::TypeConverterCore.send(:flatten_colors_for_lookup, colors)
    expect(flat.keys).to eq(['surface'])
    # a flat file too: first, it did not make the file read as themed, nor its modes as colour names
    flat_file = { 'colorSchemes' => { 'sepia' => 'dark' }, 'ink' => '#000000', 'paper' => '#FFFFFF' }
    expect(JsonUIShared::TypeConverterCore.send(:flatten_colors_for_lookup, flat_file).keys).to eq(%w[ink paper])
  end
end
