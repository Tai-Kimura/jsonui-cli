# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'core/resources/color_manager'

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
    manager.send(:save_colors_json)
    expect(JSON.parse(File.read(File.join(resources_dir, 'colors.json')))['colorSchemes']).to eq('sepia' => 'dark')
  end
end
