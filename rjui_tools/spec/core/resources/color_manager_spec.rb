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

  # Regression: rjui-web-theme-css-not-generated-from-colors-json —
  # generated components emit `bg-<token>` classes that only resolve when a
  # Tailwind v4 @theme registers `--color-<token>`. rjui build now emits that
  # @theme as a @generated theme.css.
  describe 'theme.css generation' do
    let(:theme_file) { File.join(source_path, 'src', 'generated', 'theme.css') }

    def write_colors(hash)
      File.write(File.join(resources_dir, 'colors.json'), JSON.pretty_generate(hash))
    end

    # process_colors returns early on an empty file list, so drive it with a
    # colorless layout file — the pass still regenerates ColorManager + theme.
    def run_process(cfg = config)
      dummy = File.join(temp_dir, 'dummy_layout.json')
      File.write(dummy, JSON.pretty_generate('type' => 'View'))
      described_class.new(cfg, source_path, resources_dir).process_colors([dummy], 1, 0, cfg)
    end

    it 'emits an @theme block with --color-<token> for each mode-complete token' do
      write_colors('ink' => '#1C1C1A', 'surface' => '#FFFFFF', 'primary' => '#0E5A46')
      run_process

      expect(File.exist?(theme_file)).to be true
      css = File.read(theme_file)
      expect(css).to include('@theme {')
      expect(css).to include('--color-ink: #1C1C1A;')
      expect(css).to include('--color-surface: #FFFFFF;')
      expect(css).to include('--color-primary: #0E5A46;')
      expect(css).to include('@generated')
    end

    # Regression: rjui-scrollbar-hide-class-has-no-css — converters emit
    # `scrollbar-hide` (tailwind-scrollbar-hide plugin vocabulary, not
    # Tailwind core), so a plugin-less consumer got an inert class. The one
    # generated stylesheet consumers import now supplies it, as @utility so
    # variant forms (`md:scrollbar-hide`) resolve too.
    it 'supplies the scrollbar-hide utility the converters emit' do
      write_colors('ink' => '#1C1C1A')
      run_process

      css = File.read(theme_file)
      expect(css).to include('@utility scrollbar-hide {')
      expect(css).to include('scrollbar-width: none;')
      expect(css).to include('&::-webkit-scrollbar {')
    end

    it 'converts JsonUI alpha-first 8-digit hex to rgba()' do
      write_colors('backdrop' => '#731C1C1A')
      run_process

      css = File.read(theme_file)
      # #731C1C1A => A=0x73(115)=0.451, R=0x1C(28), G=0x1C(28), B=0x1A(26)
      expect(css).to include('--color-backdrop: rgba(28, 28, 26, 0.451);')
    end

    it 'renders fully-opaque 8-digit alpha as integer 1' do
      write_colors('solid' => '#FF102030')
      run_process

      expect(File.read(theme_file)).to include('--color-solid: rgba(16, 32, 48, 1);')
    end

    it 'emits per-mode overrides under :root[data-theme=...] for extra modes' do
      write_colors(
        'modes' => %w[light dark],
        'fallback_mode' => 'light',
        'light' => { 'surface' => '#FFFFFF', 'ink' => '#1C1C1A' },
        'dark' => { 'surface' => '#101010', 'ink' => '#F5F5F5' }
      )
      run_process

      css = File.read(theme_file)
      expect(css).to include('@theme {')
      expect(css).to include('--color-surface: #FFFFFF;')
      expect(css).to include(':root[data-theme="dark"] {')
      expect(css).to include('--color-surface: #101010;')
    end

    it 'skips tokens that are not mode-complete (would emit a dead class)' do
      write_colors(
        'modes' => %w[light dark],
        'light' => { 'surface' => '#FFFFFF', 'lightOnly' => '#ABCDEF' },
        'dark' => { 'surface' => '#101010' }
      )
      run_process

      css = File.read(theme_file)
      expect(css).to include('--color-surface')
      expect(css).not_to include('--color-lightOnly')
    end

    it 'still writes theme.css (utilities only, no @theme block) when there are no colors' do
      write_colors({})
      run_process

      expect(File.exist?(theme_file)).to be true
      css = File.read(theme_file)
      expect(css).not_to include('@theme {')
      expect(css).to include('@utility scrollbar-hide {')
    end
  end

  describe '#css_color_value' do
    it 'keeps 6-digit hex as-is' do
      expect(manager.send(:css_color_value, '#0E5A46')).to eq('#0E5A46')
    end

    it 'expands nothing for 3-digit hex but keeps it valid CSS' do
      expect(manager.send(:css_color_value, '#abc')).to eq('#abc')
    end

    it 'converts 8-digit alpha-first hex to rgba' do
      expect(manager.send(:css_color_value, '#731C1C1A')).to eq('rgba(28, 28, 26, 0.451)')
    end

    it 'returns nil for non-hex values' do
      expect(manager.send(:css_color_value, 'not_a_color')).to be_nil
      expect(manager.send(:css_color_value, nil)).to be_nil
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

      # rjui-offpalette-hex-dead-tailwind-class: hue-carrying pales must not
      # collapse to bare `white`/`black` (Tailwind builtins, hue discarded).
      it 'keeps the hue for a near-white tinted color instead of bare white' do
        key = manager.send(:generate_color_key, '#DBEAFE') # pale blue-ish
        expect(key).not_to match(/^white(_\d+)?$/)
        expect(key).to start_with('pale_') # hue suffix preserved
      end

      it 'keeps the hue for a near-black tinted color instead of bare black' do
        key = manager.send(:generate_color_key, '#0A1030') # very dark blue
        expect(key).not_to match(/^black(_\d+)?$/)
      end

      it 'still names true neutrals white/black' do
        expect(manager.send(:generate_color_key, '#FFFFFF')).to eq('white')
        expect(manager.send(:generate_color_key, '#FDFDFC')).to eq('white')
        expect(manager.send(:generate_color_key, '#000000')).to eq('black')
      end
    end

    describe '#mode_complete_keys / #fallback_hexes' do
      it 'returns only names defined in every mode' do
        colors_file = File.join(resources_dir, 'colors.json')
        File.write(colors_file, JSON.pretty_generate(
          'modes' => %w[light dark],
          'fallback_mode' => 'light',
          'light' => { 'surface' => '#FFFFFF', 'white_2' => '#FFFBEB' },
          'dark' => { 'surface' => '#0B1220' }
        ))
        m = described_class.new(config, source_path, resources_dir)
        expect(m.mode_complete_keys).to eq(['surface'])
        expect(m.fallback_hexes).to include('white_2' => '#FFFBEB')
      end

      it 'treats every key as complete in a single-mode project' do
        colors_file = File.join(resources_dir, 'colors.json')
        File.write(colors_file, JSON.pretty_generate('light' => { 'a' => '#111111', 'b' => '#222222' }))
        m = described_class.new(config, source_path, resources_dir)
        expect(m.mode_complete_keys.sort).to eq(%w[a b])
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

      # rjui-dynamic-color-binding-emits-raw-token: a color attribute that
      # lands in an inline style has to resolve its colors.json key at
      # runtime, the way iOS and Android already do.
      it 'emits resolveColor: palette lookup with quiet pass-through' do
        m = described_class.new(config, source_path, resources_dir)
        m.send(:generate_color_manager)

        content = File.read(File.join(source_path, 'src', 'generated', 'ColorManager.js'))
        expect(content).to include('resolveColor(value)')
        # token -> current mode, then the fallback mode
        expect(content).to include('if (p && p[value] !== undefined) return p[value];')
        expect(content).to include('if (fb && fb[value] !== undefined) return fb[value];')
        # anything else is handed back untouched, and without a warning:
        # a caller cannot tell a typo from a valid CSS color name
        expect(content).to include('    return value;')
        resolve_body = content[/resolveColor\(value\).*?\n  \}/m]
        expect(resolve_body).not_to include('console.warn')
      end

      it 'types resolveColor for TS' do
        ts_config = config.merge('typescript' => true)
        m = described_class.new(ts_config, source_path, resources_dir)
        m.send(:generate_color_manager)

        content = File.read(File.join(source_path, 'src', 'generated', 'ColorManager.ts'))
        expect(content).to include('resolveColor(value: unknown): string | undefined')
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

  describe '#generate_ts_code SYSTEM_MODE_MAPPING type (regression: rjui-colormanager-single-mode-system-mapping-ts-error)' do
    # With a light-only colors.json, `Object.freeze({ light: 'light' })`
    # infers a single-key literal type, so `SYSTEM_MODE_MAPPING[osMode]`
    # (osMode: 'light' | 'dark') fails strict tsc with TS7053. The emitted
    # const needs an explicit loose readonly record annotation.
    let(:single_mode_manager) do
      File.write(File.join(resources_dir, 'colors.json'), JSON.generate({
        'modes' => ['light'],
        'fallback_mode' => 'light',
        'systemModeMapping' => { 'light' => 'light' },
        'light' => { 'primary' => '#336699' }
      }))
      described_class.new(config, source_path, resources_dir)
    end

    it 'annotates SYSTEM_MODE_MAPPING as a loose readonly record in TS output' do
      code = single_mode_manager.send(
        :generate_ts_code, single_mode_manager.send(:deep_clone_palettes), true
      )
      expect(code).to include(
        'const SYSTEM_MODE_MAPPING: Readonly<Record<string, string | undefined>> = Object.freeze({'
      )
    end

    it 'leaves the JS output unannotated' do
      code = single_mode_manager.send(
        :generate_ts_code, single_mode_manager.send(:deep_clone_palettes), false
      )
      expect(code).to include('const SYSTEM_MODE_MAPPING = Object.freeze({')
    end
  end
end
