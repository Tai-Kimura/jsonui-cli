# frozen_string_literal: true

require 'core/resources/color_manager'
require 'core/logger'

RSpec.describe SjuiTools::Core::Resources::ColorManager do
  let(:temp_dir) { Dir.mktmpdir('color_manager_test') }
  let(:source_path) { temp_dir }
  let(:resources_dir) { File.join(temp_dir, 'Resources') }
  let(:config) { { 'resource_manager_directory' => 'ResourceManager' } }
  let(:manager) { described_class.new(config, source_path, resources_dir) }

  before do
    FileUtils.mkdir_p(resources_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates instance with config, source_path, and resources_dir' do
      expect(manager).to be_a(described_class)
    end

    it 'loads existing colors.json if present' do
      colors_file = File.join(resources_dir, 'colors.json')
      File.write(colors_file, '{"primary": "#FF0000"}')

      new_manager = described_class.new(config, source_path, resources_dir)
      expect(new_manager).to be_a(described_class)
    end

    it 'handles invalid colors.json gracefully' do
      colors_file = File.join(resources_dir, 'colors.json')
      File.write(colors_file, 'invalid json')

      expect { described_class.new(config, source_path, resources_dir) }.not_to raise_error
    end

    # An unreadable file used to become the same state as an empty one and
    # as a missing one: the parse error produced `nil`, and `nil` answers
    # :empty, so all three seeded the default palette. Two things followed
    # — a ColorManager emitted with every colour `undefined`, which builds
    # and type-checks and only fails at runtime, and a write-back that
    # replaced the author's file with a valid-looking one holding only the
    # colours that run had extracted. Measured on a real build: a file
    # defining `brand_primary` came back holding `dark_cyan` and
    # `pale_cyan`, exit 0, and the next build parses the replacement
    # without complaint.
    it 'tells an unreadable colors.json apart from an empty one' do
      colors_file = File.join(resources_dir, 'colors.json')

      File.write(colors_file, '{ this is not valid json')
      expect(described_class.new(config, source_path, resources_dir)).to be_load_failed

      File.write(colors_file, '{}')
      expect(described_class.new(config, source_path, resources_dir)).not_to be_load_failed
    end

    it 'does not call a missing colors.json a failure' do
      # A project that has not defined colours yet is an ordinary state and
      # must not be reported as a broken one.
      expect(described_class.new(config, source_path, resources_dir))
        .not_to be_load_failed
    end

    it 'leaves an unreadable colors.json exactly as it found it' do
      colors_file = File.join(resources_dir, 'colors.json')
      original = '{ this is not valid json'
      File.write(colors_file, original)

      manager = described_class.new(config, source_path, resources_dir)
      manager.send(:save_colors_json)

      expect(File.read(colors_file)).to eq(original)
    end

    it 'says what it did not write, since the build carries on' do
      colors_file = File.join(resources_dir, 'colors.json')
      File.write(colors_file, '{ this is not valid json')
      manager = described_class.new(config, source_path, resources_dir)

      expect(SjuiTools::Core::Logger).to receive(:error)
        .with(/colors\.json was not written/)
      manager.send(:save_colors_json)
    end

    it 'loads existing defined_colors.json if present' do
      defined_colors_file = File.join(resources_dir, 'defined_colors.json')
      File.write(defined_colors_file, '{"myColor": null}')

      new_manager = described_class.new(config, source_path, resources_dir)
      expect(new_manager).to be_a(described_class)
    end
  end

  describe '#process_colors' do
    let(:json_file) { File.join(temp_dir, 'test.json') }

    before do
      FileUtils.mkdir_p(File.join(source_path, 'ResourceManager'))
    end

    context 'with no processed files' do
      # This spec's config sets `resource_manager_directory`, so
      # ColorManager.swift is still generated and still logs — "early" here means
      # no extraction happens, not no output. Asserting on ALL of stdout made the
      # example depend on `Core::Logger.level`, a class-level global that other
      # specs lower and do not restore: it passed or failed on rspec's seed.
      it 'does not extract colors' do
        previous_level = SjuiTools::Core::Logger.level
        SjuiTools::Core::Logger.level = :info
        expect { manager.process_colors([], 0, 0, config) }
          .not_to output(/Extracting colors/).to_stdout
      ensure
        SjuiTools::Core::Logger.level = previous_level
      end
    end

    context 'with json files containing hex colors' do
      before do
        File.write(json_file, JSON.pretty_generate({
          'type' => 'View',
          'background' => '#FF0000'
        }))
      end

      it 'extracts and replaces hex colors' do
        manager.process_colors([json_file], 1, 0, config)

        # Check that colors.json was created
        colors_file = File.join(resources_dir, 'colors.json')
        expect(File.exist?(colors_file)).to be true
      end

      it 'updates json file with color key' do
        manager.process_colors([json_file], 1, 0, config)

        content = JSON.parse(File.read(json_file))
        # The hex color should be replaced with a key
        expect(content['background']).not_to eq('#FF0000')
      end
    end

    context 'with json files containing undefined color keys' do
      before do
        File.write(json_file, JSON.pretty_generate({
          'type' => 'View',
          'background' => 'my_custom_color'
        }))
      end

      it 'adds undefined colors to defined_colors.json' do
        manager.process_colors([json_file], 1, 0, config)

        defined_colors_file = File.join(resources_dir, 'defined_colors.json')
        expect(File.exist?(defined_colors_file)).to be true
      end
    end

    context 'with binding expressions' do
      before do
        File.write(json_file, JSON.pretty_generate({
          'type' => 'View',
          'background' => '@{viewModel.backgroundColor}'
        }))
      end

      it 'skips binding expressions' do
        manager.process_colors([json_file], 1, 0, config)

        content = JSON.parse(File.read(json_file))
        expect(content['background']).to eq('@{viewModel.backgroundColor}')
      end
    end

    context 'with fully transparent color (alpha = 00)' do
      before do
        File.write(json_file, JSON.pretty_generate({
          'type' => 'View',
          'background' => '#00000000'
        }))
      end

      it 'replaces transparent color with transparent key' do
        manager.process_colors([json_file], 1, 0, config)

        content = JSON.parse(File.read(json_file))
        expect(content['background']).to eq('transparent')
      end

      it 'adds transparent to colors.json' do
        manager.process_colors([json_file], 1, 0, config)

        colors_file = File.join(resources_dir, 'colors.json')
        colors_content = JSON.parse(File.read(colors_file))
        # Themed schema: transparent lands in the default extract mode ('light').
        expect(colors_content['light']['transparent']).to eq('#00000000')
      end
    end

    context 'with white transparent color' do
      before do
        # W3-2: JsonUI 8-digit hex is alpha-FIRST (#AARRGGBB) — the
        # convention kjui/rjui already used; sjui read the trailing byte.
        File.write(json_file, JSON.pretty_generate({
          'type' => 'View',
          'background' => '#00FFFFFF'
        }))
      end

      it 'replaces white transparent color with transparent key' do
        manager.process_colors([json_file], 1, 0, config)

        content = JSON.parse(File.read(json_file))
        expect(content['background']).to eq('transparent')
      end

      it 'adds transparent to colors.json' do
        manager.process_colors([json_file], 1, 0, config)

        colors_file = File.join(resources_dir, 'colors.json')
        colors_content = JSON.parse(File.read(colors_file))
        # Themed schema: transparent lands in the default extract mode ('light').
        expect(colors_content['light']['transparent']).to eq('#00000000')
      end
    end
  end

  describe '#apply_to_color_assets' do
    it 'saves pending colors' do
      manager.apply_to_color_assets
      # Should not raise error
    end
  end

  describe 'private methods' do
    describe '#is_color_property?' do
      it 'returns true for background' do
        expect(manager.send(:is_color_property?, 'background')).to be true
      end

      it 'returns true for fontColor' do
        expect(manager.send(:is_color_property?, 'fontColor')).to be true
      end

      it 'returns true for textColor' do
        expect(manager.send(:is_color_property?, 'textColor')).to be true
      end

      it 'returns true for borderColor' do
        expect(manager.send(:is_color_property?, 'borderColor')).to be true
      end

      it 'returns true for tintColor' do
        expect(manager.send(:is_color_property?, 'tintColor')).to be true
      end

      it 'returns false for non-color properties' do
        expect(manager.send(:is_color_property?, 'type')).to be false
      end
    end

    describe '#is_hex_color?' do
      it 'returns true for 6-digit hex with hash' do
        expect(manager.send(:is_hex_color?, '#FF0000')).to be true
      end

      it 'returns true for 6-digit hex without hash' do
        expect(manager.send(:is_hex_color?, 'FF0000')).to be true
      end

      it 'returns true for 3-digit hex' do
        expect(manager.send(:is_hex_color?, '#F00')).to be true
      end

      it 'returns true for 8-digit hex (with alpha)' do
        expect(manager.send(:is_hex_color?, '#FF0000FF')).to be true
      end

      it 'returns false for non-hex strings' do
        expect(manager.send(:is_hex_color?, 'red')).to be false
      end

      it 'returns false for non-string values' do
        expect(manager.send(:is_hex_color?, 123)).to be false
      end
    end

    describe '#is_transparent_color?' do
      it 'returns true for fully transparent color (alpha = 00) in RRGGBBAA format' do
        expect(manager.send(:is_transparent_color?, '#00000000')).to be true
      end

      # W3-2: alpha is the LEADING byte (#AARRGGBB).
      it 'returns true for any color with zero alpha' do
        expect(manager.send(:is_transparent_color?, '#00000000')).to be true
      end

      it 'returns true for white with zero alpha' do
        expect(manager.send(:is_transparent_color?, '#00FFFFFF')).to be true
      end

      it 'returns false for fully opaque color' do
        expect(manager.send(:is_transparent_color?, '#FF000000')).to be false
      end

      it 'returns false for 6-digit hex (no alpha)' do
        expect(manager.send(:is_transparent_color?, '#000000')).to be false
      end

      it 'returns false for 3-digit hex' do
        expect(manager.send(:is_transparent_color?, '#F00')).to be false
      end

      it 'returns false for non-string values' do
        expect(manager.send(:is_transparent_color?, 123)).to be false
      end

      it 'handles lowercase hex' do
        expect(manager.send(:is_transparent_color?, '#00ff0000')).to be true
      end
    end

    describe '#normalize_hex_color' do
      it 'adds hash if missing' do
        expect(manager.send(:normalize_hex_color, 'FF0000')).to eq('#FF0000')
      end

      it 'converts to uppercase' do
        expect(manager.send(:normalize_hex_color, '#ff0000')).to eq('#FF0000')
      end

      it 'expands 3-digit to 6-digit' do
        expect(manager.send(:normalize_hex_color, '#F00')).to eq('#FF0000')
      end

      it 'keeps 8-digit hex as is' do
        expect(manager.send(:normalize_hex_color, '#FF0000AA')).to eq('#FF0000AA')
      end
    end

    describe '#parse_hex_to_rgb' do
      it 'parses 6-digit hex' do
        expect(manager.send(:parse_hex_to_rgb, '#FF0000')).to eq([255, 0, 0])
      end

      it 'parses 3-digit hex' do
        expect(manager.send(:parse_hex_to_rgb, '#F00')).to eq([255, 0, 0])
      end

      it 'parses 8-digit hex (alpha-first: leading byte is stripped)' do
        expect(manager.send(:parse_hex_to_rgb, '#AAFF0000')).to eq([255, 0, 0])
      end

      it 'returns nil for invalid length hex' do
        expect(manager.send(:parse_hex_to_rgb, '#FF00')).to be_nil
      end
    end

    describe '#generate_color_key' do
      it 'generates key for red colors' do
        key = manager.send(:generate_color_key, '#FF0000')
        expect(key).to include('red')
      end

      it 'generates key for green colors' do
        key = manager.send(:generate_color_key, '#00FF00')
        expect(key).to include('green')
      end

      it 'generates key for blue colors' do
        key = manager.send(:generate_color_key, '#0000FF')
        expect(key).to include('blue')
      end

      it 'generates key for white' do
        key = manager.send(:generate_color_key, '#FFFFFF')
        expect(key).to eq('white')
      end

      it 'generates key for black' do
        key = manager.send(:generate_color_key, '#000000')
        expect(key).to eq('black')
      end

      it 'generates key for gray' do
        key = manager.send(:generate_color_key, '#808080')
        expect(key).to include('gray')
      end
    end

    describe '#snake_to_camel' do
      it 'converts snake_case to camelCase' do
        expect(manager.send(:snake_to_camel, 'primary_blue')).to eq('primaryBlue')
      end

      it 'handles single word' do
        expect(manager.send(:snake_to_camel, 'primary')).to eq('primary')
      end

      it 'handles numbers' do
        expect(manager.send(:snake_to_camel, 'white_2')).to eq('white2')
      end
    end

    describe '#replace_colors_recursive' do
      context 'with nested hash' do
        let(:json_file) { File.join(temp_dir, 'nested.json') }

        before do
          File.write(json_file, JSON.pretty_generate({
            'type' => 'VStack',
            'children' => [
              { 'type' => 'Text', 'fontColor' => '#FF0000' }
            ]
          }))
        end

        it 'processes nested color properties' do
          content = JSON.parse(File.read(json_file))
          manager.send(:replace_colors_recursive, content)
          expect(content['children'][0]['fontColor']).not_to eq('#FF0000')
        end
      end

      context 'with array' do
        it 'processes items in arrays' do
          data = [
            { 'background' => '#00FF00' },
            { 'background' => '#0000FF' }
          ]
          manager.send(:replace_colors_recursive, data)
          expect(data[0]['background']).not_to eq('#00FF00')
          expect(data[1]['background']).not_to eq('#0000FF')
        end
      end

      context 'with data Color defaultValue' do
        before do
          colors_file = File.join(resources_dir, 'colors.json')
          File.write(colors_file, '{"light_pink": "#D4A574"}')
        end

        it 'replaces hex defaultValue with color key' do
          new_manager = described_class.new(config, source_path, resources_dir)
          data = {
            'data' => [
              { 'name' => 'selectedTabColor', 'class' => 'Color', 'defaultValue' => '#D4A574' }
            ]
          }
          new_manager.send(:replace_colors_recursive, data)
          expect(data['data'][0]['defaultValue']).to eq('light_pink')
        end

        it 'skips binding expressions in defaultValue' do
          data = {
            'data' => [
              { 'name' => 'backgroundColor', 'class' => 'Color', 'defaultValue' => '@{viewModel.themeColor}' }
            ]
          }
          manager.send(:replace_colors_recursive, data)
          expect(data['data'][0]['defaultValue']).to eq('@{viewModel.themeColor}')
        end

        it 'does not modify defaultValue when class is not Color' do
          data = {
            'data' => [
              { 'name' => 'hexValue', 'class' => 'String', 'defaultValue' => '#D4A574' }
            ]
          }
          manager.send(:replace_colors_recursive, data)
          expect(data['data'][0]['defaultValue']).to eq('#D4A574')
        end

        it 'processes data Color in nested structures' do
          new_manager = described_class.new(config, source_path, resources_dir)
          data = {
            'type' => 'View',
            'children' => [
              {
                'type' => 'TabView',
                'data' => [
                  { 'name' => 'tabColor', 'class' => 'Color', 'defaultValue' => '#D4A574' }
                ]
              }
            ]
          }
          new_manager.send(:replace_colors_recursive, data)
          expect(data['children'][0]['data'][0]['defaultValue']).to eq('light_pink')
        end
      end
    end

    describe '#generate_color_manager_swift' do
      before do
        FileUtils.mkdir_p(File.join(source_path, 'ResourceManager'))
        # Add some colors to test
        colors_file = File.join(resources_dir, 'colors.json')
        File.write(colors_file, '{"primary": "#FF0000", "secondary": "#00FF00"}')
      end

      it 'generates ColorManager.swift file' do
        new_manager = described_class.new(config, source_path, resources_dir)
        new_manager.send(:generate_color_manager_swift)

        output_file = File.join(source_path, 'ResourceManager', 'ColorManager.swift')
        expect(File.exist?(output_file)).to be true
      end

      it 'includes color definitions in generated file' do
        new_manager = described_class.new(config, source_path, resources_dir)
        new_manager.send(:generate_color_manager_swift)

        output_file = File.join(source_path, 'ResourceManager', 'ColorManager.swift')
        content = File.read(output_file)
        expect(content).to include('primary')
        expect(content).to include('secondary')
      end
    end
  end

  describe 'themed schema support' do
    let(:colors_file) { File.join(resources_dir, 'colors.json') }

    before do
      FileUtils.mkdir_p(File.join(source_path, 'ResourceManager'))
    end

    describe 'schema migration (flat → themed)' do
      it 'auto-migrates a flat colors.json to themed on apply_to_color_assets' do
        File.write(colors_file, JSON.pretty_generate({
          'primary' => '#FF0000',
          'secondary' => '#00FF00'
        }))

        new_manager = described_class.new(config, source_path, resources_dir)
        new_manager.apply_to_color_assets

        migrated = JSON.parse(File.read(colors_file))
        expect(migrated['light']).to eq('primary' => '#FF0000', 'secondary' => '#00FF00')
        expect(migrated['modes']).to eq(['light'])
        expect(migrated['fallback_mode']).to eq('light')
      end

      it 'supports arbitrary mode names' do
        File.write(colors_file, JSON.pretty_generate({
          'modes' => %w[day night high_contrast],
          'fallback_mode' => 'day',
          'day' => { 'bg' => '#FFFFFF' },
          'night' => { 'bg' => '#222222' },
          'high_contrast' => { 'bg' => '#000000' }
        }))

        new_manager = described_class.new(config, source_path, resources_dir)
        expect(new_manager.modes).to eq(%w[day night high_contrast])
        expect(new_manager.fallback_mode).to eq('day')
      end
    end

    describe 'hex extraction routing' do
      let(:json_file) { File.join(temp_dir, 'layout.json') }

      before do
        File.write(json_file, JSON.pretty_generate({
          'type' => 'View', 'background' => '#123456'
        }))
      end

      it 'writes extracted hex into the default light palette' do
        manager.process_colors([json_file], 1, 0, config)

        colors_data = JSON.parse(File.read(colors_file))
        expect(colors_data['light'].values).to include('#123456')
        expect(colors_data).not_to have_key('dark')
      end

      it 'routes extraction into the configured mode via extract_into_mode' do
        targeted_config = config.merge('extract_into_mode' => 'dark')
        targeted = described_class.new(targeted_config, source_path, resources_dir)
        targeted.process_colors([json_file], 1, 0, targeted_config)

        colors_data = JSON.parse(File.read(colors_file))
        expect(colors_data['dark']).to be_a(Hash)
        expect(colors_data['dark'].values).to include('#123456')
      end
    end

    describe 'generated ColorManager.swift emits themed API' do
      before do
        File.write(colors_file, JSON.pretty_generate({
          'modes' => %w[light dark],
          'fallback_mode' => 'light',
          'light' => { 'primary' => '#FFFFFF' },
          'dark' => { 'primary' => '#000000' }
        }))
      end

      it 'emits ColorMode enum with every mode' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager_swift)

        output = File.read(File.join(source_path, 'ResourceManager', 'ColorManager.swift'))
        expect(output).to include('public enum ColorMode')
        expect(output).to match(/case\s+light/)
        expect(output).to match(/case\s+dark/)
      end

      it 'emits per-mode palette structs inside uikit and swiftui namespaces' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager_swift)

        output = File.read(File.join(source_path, 'ResourceManager', 'ColorManager.swift'))
        # `public struct light {` / `public struct dark {` appear inside both
        # `uikit` and `swiftui` namespaces, and each is followed by a `primary`
        # getter. Use a non-greedy any-char match so inner empty braces from
        # `private init() {}` don't short-circuit the match.
        expect(output).to match(/public struct light \{[\s\S]*?primary/m)
        expect(output).to match(/public struct dark \{[\s\S]*?primary/m)
      end

      it 'emits setMode + subscribe + Observable ObservableObject for mode switching' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager_swift)

        output = File.read(File.join(source_path, 'ResourceManager', 'ColorManager.swift'))
        expect(output).to include('public static func setMode(_ mode: ColorMode)')
        expect(output).to include('public static func subscribe')
        expect(output).to include('public final class Observable: ObservableObject')
        expect(output).to include('@Published public private(set) var currentMode: ColorMode')
      end

      it 'emits color(for:) with lenient fallback to fallbackMode' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager_swift)

        output = File.read(File.join(source_path, 'ResourceManager', 'ColorManager.swift'))
        # The fallback branch is the `?? ColorManager.palettes[ColorManager.fallbackMode]?[key]` chain.
        expect(output).to include('ColorManager.palettes[ColorManager.fallbackMode]')
      end

      it 'emits systemModeMapping table for OS appearance → project mode translation' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager_swift)

        output = File.read(File.join(source_path, 'ResourceManager', 'ColorManager.swift'))
        expect(output).to include('systemModeMapping: [UIUserInterfaceStyle: ColorMode]')
      end

      it 'emits `import Combine` so @Published + ObservableObject compile on all toolchains' do
        # Under Xcode iOS SDK 26 (and some older toolchains) SwiftUI does not
        # reliably re-export Combine, so `@Published` / `ObservableObject`
        # used by ColorManager.Observable fail to compile with a
        # "<unknown>:0: error: initializer 'init(wrappedValue:)' is not
        # available due to missing import of defining module 'Combine'"
        # at archive time. The fix emits `import Combine` unconditionally
        # — harmless when already in scope via SwiftUI re-export.
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager_swift)

        output = File.read(File.join(source_path, 'ResourceManager', 'ColorManager.swift'))
        expect(output).to include('import Combine')
      end
    end
  end
end
