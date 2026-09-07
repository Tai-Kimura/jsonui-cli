# frozen_string_literal: true

require 'core/resources/color_manager'
require 'json'
require 'tmpdir'
require 'fileutils'

# defined_colors.json is a picture of what is STILL undefined.
#
# `save_defined_colors_json` only ever merged, so once a name was written it
# stayed written — including after somebody added the colour. The file exists
# to answer "which names does no palette define?" and it answered that
# question wrongly, more wrongly the longer a project lived. Measured on a
# consumer: both platform faces' ledgers, untouched since April, still listed
# 7 and 8 names that colors.json now defines.
#
# Byte-identical across the three tools (shared/core mirror), so the ledger
# means the same thing on every face.
RSpec.describe KjuiTools::Core::Resources::ColorManager do
  let(:temp_dir) { Dir.mktmpdir('defined_colors_ledger') }
  let(:resources_dir) { File.join(temp_dir, 'Resources') }
  let(:config) { { 'resource_manager_directory' => 'ResourceManager' } }
  let(:ledger_path) { File.join(resources_dir, 'defined_colors.json') }

  before { FileUtils.mkdir_p(resources_dir) }
  after { FileUtils.rm_rf(temp_dir) }

  def write_palette(palette)
    File.write(File.join(resources_dir, 'colors.json'), JSON.pretty_generate(palette))
  end

  # The PUBLIC entry, deliberately. `save_defined_colors_json` used to be
  # reached only through `... if @undefined_colors.any?`, so a unit call to
  # the method itself would have passed while the real build never ran it —
  # which is exactly how a consumer's ledger stayed frozen for five months.
  def ledger_after_save
    manager = described_class.new(config, temp_dir, resources_dir)
    manager.apply_to_color_assets
    JSON.parse(File.read(ledger_path))
  end

  it 'drops a name the palette now defines' do
    write_palette('brand_primary' => '#221C10')
    File.write(ledger_path, JSON.pretty_generate('brand_primary' => nil))

    expect(ledger_after_save).to eq({})
  end

  it 'keeps a name no palette defines' do
    write_palette('brand_primary' => '#221C10')
    File.write(ledger_path, JSON.pretty_generate('never_declared' => nil))

    expect(ledger_after_save).to eq('never_declared' => nil)
  end

  # Resolution is mode-agnostic from the layout side — a layout names a key,
  # not a mode — so a colour carried by one mode only is defined, and a
  # ledger that kept it would report a working colour as missing.
  it 'drops a name carried by one mode only' do
    write_palette(
      'modes' => %w[light dark], 'fallback_mode' => 'light',
      'light' => { 'brand_primary' => '#221C10' },
      'dark' => { 'dusk_only' => '#101010' }
    )
    File.write(ledger_path, JSON.pretty_generate('dusk_only' => nil, 'never_declared' => nil))

    expect(ledger_after_save).to eq('never_declared' => nil)
  end

  it 'writes an empty ledger rather than deleting the file' do
    write_palette('brand_primary' => '#221C10')
    File.write(ledger_path, JSON.pretty_generate('brand_primary' => nil))
    ledger_after_save

    expect(File.exist?(ledger_path)).to be true
  end
end
