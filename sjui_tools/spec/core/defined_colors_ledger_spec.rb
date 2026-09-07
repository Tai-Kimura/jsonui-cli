# frozen_string_literal: true

require 'core/resources/color_manager'
require 'json'
require 'tmpdir'
require 'open3'
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
RSpec.describe SjuiTools::Core::Resources::ColorManager do
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

  # Removing the caller's gate made this run on every build, which on a face
  # that never carried a ledger would have created an empty `{}` — a new
  # untracked file arriving in a consumer that had deliberately never had
  # one. Measured on a real face: `defined_colors.json` absent, tracked 0.
  it 'does not create a ledger on a face that has none and nothing undefined' do
    write_palette('brand_primary' => '#221C10')
    expect(File.exist?(ledger_path)).to be false

    manager = described_class.new(config, temp_dir, resources_dir)
    # Silence too: a face whose gate diffs build output verbatim would see a
    # line about a file it does not have.
    expect { manager.apply_to_color_assets }
      .not_to output(/Updated defined_colors\.json/).to_stdout

    expect(File.exist?(ledger_path)).to be false
  end

  # ...but a face with something undefined still gets one. The guard is
  # about empty, not about absent.
  it 'creates a ledger on a face that has none once something is undefined' do
    write_palette('brand_primary' => '#221C10')
    json = File.join(temp_dir, 'panel.json')
    File.write(json, JSON.pretty_generate('type' => 'View', 'background' => 'never_declared'))

    manager = described_class.new(config, temp_dir, resources_dir)
    manager.process_colors([json], 1, 0, config)
    manager.apply_to_color_assets

    expect(File.exist?(ledger_path)).to be true
    expect(JSON.parse(File.read(ledger_path))).to have_key('never_declared')
  end

  it 'writes an empty ledger rather than deleting the file' do
    write_palette('brand_primary' => '#221C10')
    File.write(ledger_path, JSON.pretty_generate('brand_primary' => nil))
    ledger_after_save

    expect(File.exist?(ledger_path)).to be true
  end

  # The three states in one real build. The examples above construct the
  # manager directly; this one runs `sjui build`, which is where the gate
  # that kept the save from happening actually lived.
  describe 'through a real build' do
    LEDGER_REPO_ROOT = File.expand_path('../../..', __dir__)

    def build_project(layout_color:, ledger:, palette:)
      dir = Dir.mktmpdir('ledger_build')
      name = 'LedgerProbe'
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
        'viewmodel_directory' => 'ViewModel', 'resource_manager_directory' => 'ResourceManager',
        'string_files' => ["#{name}/Localizable.strings"], 'use_network' => true
      ))
      File.write(File.join(dir, '.jsonui-type-map.json'), '{}')
      FileUtils.mkdir_p(File.join(dir, "#{name}.xcodeproj"))
      res = File.join(dir, name, 'Layouts', 'Resources')
      FileUtils.mkdir_p(res)
      File.write(File.join(res, 'colors.json'), JSON.pretty_generate(palette))
      # The ledger as an older build left it.
      File.write(File.join(res, 'defined_colors.json'), JSON.pretty_generate(ledger))
      File.write(File.join(dir, name, 'Layouts', 'panel.json'), JSON.generate(
        'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
        'child' => [{ 'type' => 'Label', 'id' => 'a', 'width' => 'wrapContent',
                      'height' => 'wrapContent', 'text' => 'x', 'fontColor' => layout_color }]
      ))
      FileUtils.ln_s(File.join(LEDGER_REPO_ROOT, 'sjui_tools'), File.join(dir, 'sjui_tools'))
      log, = Open3.capture2e('ruby', File.join(dir, 'sjui_tools', 'bin', 'sjui'), 'build', chdir: dir)
      [dir, JSON.parse(File.read(File.join(res, 'defined_colors.json'))), log]
    end

    it 'drops the newly defined name, keeps the still-missing one, adds the new one' do
      dir, ledger, log = build_project(
        layout_color: 'freshly_missing',
        ledger: { 'was_missing_now_defined' => nil, 'still_missing' => nil },
        palette: { 'was_missing_now_defined' => '#221C10' }
      )

      expect(ledger).not_to have_key('was_missing_now_defined'), "#{ledger.inspect}\n#{log}"
      expect(ledger).to have_key('still_missing'), "#{ledger.inspect}\n#{log}"
      expect(ledger).to have_key('freshly_missing'), "#{ledger.inspect}\n#{log}"
    ensure
      FileUtils.rm_rf(dir) if dir
    end

    # THE ONE THAT MATTERS. Every colour this build sees is defined, so
    # `@undefined_colors` is empty — which is precisely when the old
    # `save_defined_colors_json if @undefined_colors.any?` skipped the save
    # entirely. A project that has finished defining its colours is exactly
    # the project whose ledger needs cleaning, and it was the one the clean
    # could never reach. Measured on a consumer: both faces' ledgers frozen
    # since April while colors.json moved on.
    it 'cleans the ledger on a build with no new undefined colour' do
      dir, ledger, log = build_project(
        layout_color: 'was_missing_now_defined',
        ledger: { 'was_missing_now_defined' => nil, 'still_missing' => nil },
        palette: { 'was_missing_now_defined' => '#221C10' }
      )

      expect(ledger).not_to have_key('was_missing_now_defined'), "#{ledger.inspect}\n#{log}"
      expect(ledger).to have_key('still_missing'), "#{ledger.inspect}\n#{log}"
    ensure
      FileUtils.rm_rf(dir) if dir
    end

    # The content check that keeps the now-ungated save off a tracked file's
    # mtime on every build.
    it 'does not rewrite the file when nothing changed' do
      dir, = build_project(
        layout_color: 'was_missing_now_defined',
        ledger: { 'still_missing' => nil },
        palette: { 'was_missing_now_defined' => '#221C10' }
      )
      path = File.join(dir, 'LedgerProbe', 'Layouts', 'Resources', 'defined_colors.json')
      before = File.mtime(path)

      sleep 1.1
      Open3.capture2e('ruby', File.join(dir, 'sjui_tools', 'bin', 'sjui'), 'build', chdir: dir)

      expect(File.mtime(path)).to eq(before)
    ensure
      FileUtils.rm_rf(dir) if dir
    end
  end
end
