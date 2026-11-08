# frozen_string_literal: true

require 'spec_helper'
require 'json'
require 'tmpdir'
require 'fileutils'
require_relative '../../../lib/core/resources/color_manager'
require_relative '../../../lib/swiftui/views/color_palette'

# colors.json's colorSchemes ({"sepia": "dark"}: the color-scheme the web
# draws the browser's own parts with) is a setting like systemModeMapping:
# neither a mode nor a colour on iOS, first in the file or beside a note
# (ticket 2026-11-08-web-colour-mode-has-no-color-scheme).
RSpec.describe 'colorSchemes is a setting, not a mode (iOS)' do
  let(:colors) do
    { 'colorSchemes' => { 'sepia' => 'dark' }, '_comment' => 'a note',
      'light' => { 'surface' => '#FFFFFF' }, 'sepia' => { 'surface' => '#F3E7D3' } }
  end

  it 'is not a ColorMode and names no colour' do
    Dir.mktmpdir do |dir|
      resources = File.join(dir, 'Resources')
      FileUtils.mkdir_p(resources)
      File.write(File.join(resources, 'colors.json'), JSON.generate(colors))
      allow(SjuiTools::Core::Logger).to receive(:info)
      manager = SjuiTools::Core::Resources::ColorManager.new({ 'resource_manager_directory' => 'RM' }, dir, resources)
      expect(manager.modes).to eq(%w[light sepia])
      manager.apply_to_color_assets
      swift = File.read(File.join(dir, 'RM', 'ColorManager.swift'))
      expect(swift.scan(/^        case (\w+)/).flatten).to eq(%w[light sepia])
      expect(swift).not_to include('colorSchemes')
    end
  end

  it "is not counted among the palette's names" do
    expect(SjuiTools::SwiftUI::Views::ColorPalette.send(:union_of_modes, colors)).to eq(['surface'])
  end
end
