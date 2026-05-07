# frozen_string_literal: true

require 'tmpdir'
require_relative '../../../lib/core/resources/color_manager'
require_relative '../../../lib/core/logger'

RSpec.describe RjuiTools::Core::Resources::ColorManager do
  let(:temp_dir) { Dir.mktmpdir('color_manager_test') }
  let(:source_path) { temp_dir }
  let(:resources_dir) { File.join(temp_dir, 'Resources') }
  let(:config) { { 'generated_directory' => 'src/generated' } }
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
      FileUtils.mkdir_p(File.join(source_path, 'src', 'generated'))
    end

    context 'with no processed files' do
      it 'returns early without processing' do
        expect { manager.process_colors([], 0, 0, config) }.not_to output.to_stdout
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

      it 'parses 8-digit hex (ignoring alpha)' do
        expect(manager.send(:parse_hex_to_rgb, '#FF0000AA')).to eq([255, 0, 0])
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
            'type' => 'View',
            'child' => [
              { 'type' => 'Label', 'fontColor' => '#FF0000' }
            ]
          }))
        end

        it 'processes nested color properties' do
          content = JSON.parse(File.read(json_file))
          manager.send(:replace_colors_recursive, content)
          expect(content['child'][0]['fontColor']).not_to eq('#FF0000')
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

    describe '#generate_color_manager_js' do
      before do
        FileUtils.mkdir_p(File.join(source_path, 'src', 'generated'))
        # Add some colors to test
        colors_file = File.join(resources_dir, 'colors.json')
        File.write(colors_file, '{"primary": "#FF0000", "secondary": "#00FF00"}')
      end

      it 'generates ColorManager.js file' do
        new_manager = described_class.new(config, source_path, resources_dir)
        new_manager.send(:generate_color_manager_js)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        expect(File.exist?(output_file)).to be true
      end

      it 'includes color definitions in generated file' do
        new_manager = described_class.new(config, source_path, resources_dir)
        new_manager.send(:generate_color_manager_js)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        expect(content).to include('primary')
        expect(content).to include('secondary')
        expect(content).to include('#FF0000')
        expect(content).to include('#00FF00')
      end

      it 'generates color() method with binding expression handling' do
        new_manager = described_class.new(config, source_path, resources_dir)
        new_manager.send(:generate_color_manager_js)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        expect(content).to include('color(key)')
        # Themed emission uses single-quoted literals for the binding sentinel.
        expect(content).to include("startsWith('@{')")
        expect(content).to include("endsWith('}')")
        expect(content).to include('return undefined')
      end

      it 'generates camelCase property accessors' do
        # Test with snake_case color name
        colors_file = File.join(resources_dir, 'colors.json')
        File.write(colors_file, '{"primary_blue": "#0000FF"}')

        new_manager = described_class.new(config, source_path, resources_dir)
        new_manager.send(:generate_color_manager_js)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        expect(content).to include('get primaryBlue()')
      end
    end
  end

  describe 'themed schema support' do
    describe 'schema migration (flat → themed)' do
      let(:colors_file) { File.join(resources_dir, 'colors.json') }

      it 'auto-migrates a flat colors.json on process_colors' do
        File.write(colors_file, JSON.pretty_generate({
          'primary' => '#FF0000',
          'secondary' => '#00FF00'
        }))

        # A no-op process_colors (empty processed_files skips entirely), so
        # force migration via apply_to_color_assets.
        new_manager = described_class.new(config, source_path, resources_dir)
        new_manager.apply_to_color_assets

        migrated = JSON.parse(File.read(colors_file))
        expect(migrated['light']).to eq('primary' => '#FF0000', 'secondary' => '#00FF00')
        expect(migrated['modes']).to eq(['light'])
        expect(migrated['fallback_mode']).to eq('light')
      end

      it 'keeps already-themed colors.json unchanged across reads (idempotent)' do
        themed = {
          'modes' => %w[light dark],
          'fallback_mode' => 'light',
          'systemModeMapping' => { 'light' => 'light', 'dark' => 'dark' },
          'light' => { 'primary' => '#FFFFFF' },
          'dark' => { 'primary' => '#000000' }
        }
        File.write(colors_file, JSON.pretty_generate(themed))

        new_manager = described_class.new(config, source_path, resources_dir)
        new_manager.apply_to_color_assets

        after = JSON.parse(File.read(colors_file))
        expect(after['light']).to eq('primary' => '#FFFFFF')
        expect(after['dark']).to eq('primary' => '#000000')
        expect(after['modes']).to eq(%w[light dark])
      end

      it 'supports arbitrary mode names (not just light/dark)' do
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
        FileUtils.mkdir_p(File.join(source_path, 'src', 'generated'))
        File.write(json_file, JSON.pretty_generate({
          'type' => 'View', 'background' => '#123456'
        }))
      end

      it 'writes extracted hex into the default light palette when no mode is configured' do
        manager.process_colors([json_file], 1, 0, config)

        colors_file = File.join(resources_dir, 'colors.json')
        colors_data = JSON.parse(File.read(colors_file))
        expect(colors_data['light'].values).to include('#123456')
        # dark palette shouldn't be fabricated until the user creates it.
        expect(colors_data).not_to have_key('dark')
      end

      it 'routes extraction into the configured mode via extract_into_mode config' do
        config_with_mode = config.merge('extract_into_mode' => 'dark')
        targeted = described_class.new(config_with_mode, source_path, resources_dir)
        targeted.process_colors([json_file], 1, 0, config_with_mode)

        colors_file = File.join(resources_dir, 'colors.json')
        colors_data = JSON.parse(File.read(colors_file))
        expect(colors_data['dark']).to be_a(Hash)
        expect(colors_data['dark'].values).to include('#123456')
      end
    end

    describe 'generated ColorManager emits themed API' do
      before do
        FileUtils.mkdir_p(File.join(source_path, 'src', 'generated'))
        File.write(File.join(resources_dir, 'colors.json'), JSON.pretty_generate({
          'modes' => %w[light dark],
          'fallback_mode' => 'light',
          'light' => { 'primary' => '#FFFFFF' },
          'dark' => { 'primary' => '#000000' }
        }))
      end

      it 'emits a ColorMode object literal including every mode' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        expect(content).to include("LIGHT: 'light'")
        expect(content).to include("DARK: 'dark'")
      end

      it 'emits per-mode palette accessors (light / dark getters)' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        expect(content).to include('get light()')
        expect(content).to include('get dark()')
      end

      it 'emits a per-mode palette object literal with the color values' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        expect(content).to include('_lightPalette')
        expect(content).to include('_darkPalette')
        expect(content).to match(/_lightPalette.*?primary: '#FFFFFF'/m)
        expect(content).to match(/_darkPalette.*?primary: '#000000'/m)
      end

      it 'emits current-mode dynamic accessor that calls color(key)' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        # Dynamic accessor at the top level routes through color() → current mode.
        expect(content).to match(/get primary\(\) \{ return this\.color\('primary'\); \}/)
      end

      it 'emits setMode / followSystemMode and system mode listener bootstrap' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        expect(content).to include('setMode(mode)')
        expect(content).to include('followSystemMode')
        expect(content).to include("matchMedia('(prefers-color-scheme: dark)')")
      end

      it 'emits .ts when the typescript config is true' do
        ts_config = config.merge('typescript' => true)
        m = described_class.new(ts_config, source_path, resources_dir)
        m.send(:generate_color_manager)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.ts')
        expect(File.exist?(output_file)).to be true
        content = File.read(output_file)
        # ColorMode as `as const` literal object → derived type alias.
        expect(content).to include('as const')
        expect(content).to include('export type ColorMode')
      end

      it 'annotates _rawPalettes with a loose index type under TS (strict-mode safe)' do
        # Without the explicit type, `Object.freeze({literal})` infers a
        # tight readonly type with no string index signature, so
        # `_rawPalettes[m][key]` where `key: string` errors with TS7053 /
        # TS2536 under tsconfig strict: true (Next.js default). The fix is
        # to declare Record<string, Readonly<Record<string, string |
        # undefined>>> on the outer const so string-keyed lookups stay
        # legal while the literal hex values remain inlined at runtime.
        ts_config = config.merge('typescript' => true)
        m = described_class.new(ts_config, source_path, resources_dir)
        m.send(:generate_color_manager)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.ts')
        content = File.read(output_file)
        expect(content).to include('const _rawPalettes: Record<string, Readonly<Record<string, string | undefined>>>')
      end

      it 'does NOT add the Record type annotation in .js output' do
        # The annotation is TS-only syntax. JS output must stay as a plain
        # `const _rawPalettes = Object.freeze({...})`.
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        expect(content).to include('const _rawPalettes = Object.freeze({')
        expect(content).not_to include('Record<string')
      end
    end

    describe 'lenient fallback' do
      before do
        FileUtils.mkdir_p(File.join(source_path, 'src', 'generated'))
        File.write(File.join(resources_dir, 'colors.json'), JSON.pretty_generate({
          'modes' => %w[light dark],
          'fallback_mode' => 'light',
          'light' => { 'only_in_light' => '#ABCDEF', 'primary' => '#FFFFFF' },
          'dark' => { 'primary' => '#000000' }
        }))
      end

      it 'emits color() that falls back to FALLBACK_MODE when the current-mode palette misses the key' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager)

        output_file = File.join(source_path, 'src', 'generated', 'ColorManager.js')
        content = File.read(output_file)
        # The fallback branch is the literal `const fb = _rawPalettes[FALLBACK_MODE];`
        # — proves that miss-in-current-mode → try-fallback is wired.
        expect(content).to include('_rawPalettes[FALLBACK_MODE]')
        expect(content).to include("FALLBACK_MODE = 'light'")
      end
    end
  end

  describe 'integration tests' do
    context 'with multiple color formats in one file' do
      let(:json_file) { File.join(temp_dir, 'multi.json') }

      before do
        FileUtils.mkdir_p(File.join(source_path, 'src', 'generated'))
        File.write(json_file, JSON.pretty_generate({
          'type' => 'View',
          'background' => '#FF0000',
          'child' => [
            {
              'type' => 'Label',
              'fontColor' => '@{vm.textColor}',
              'text' => 'Test'
            },
            {
              'type' => 'Button',
              'background' => 'custom_color',
              'text' => 'Click'
            }
          ]
        }))
      end

      it 'handles hex colors, bindings, and custom keys correctly' do
        manager.process_colors([json_file], 1, 0, config)

        content = JSON.parse(File.read(json_file))

        # Hex color should be replaced with key
        expect(content['background']).not_to eq('#FF0000')
        expect(content['background']).to be_a(String)

        # Binding should remain unchanged
        expect(content['child'][0]['fontColor']).to eq('@{vm.textColor}')

        # Custom color key should remain unchanged
        expect(content['child'][1]['background']).to eq('custom_color')

        # colors.json should have the hex color. With themed schema the file
        # shape is {modes, fallback_mode, systemModeMapping, light: {key: hex}, …}
        # — navigate into the 'light' palette (the default extract target).
        colors_file = File.join(resources_dir, 'colors.json')
        colors_data = JSON.parse(File.read(colors_file))
        expect(colors_data['light']).to be_a(Hash)
        expect(colors_data['light'].values).to include('#FF0000')

        # defined_colors.json should have the custom key
        defined_colors_file = File.join(resources_dir, 'defined_colors.json')
        defined_colors_data = JSON.parse(File.read(defined_colors_file))
        expect(defined_colors_data.keys).to include('custom_color')
      end
    end
  end
end
