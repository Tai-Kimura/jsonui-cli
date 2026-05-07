# frozen_string_literal: true

require 'core/resources/color_manager'
require 'json'
require 'tempfile'
require 'fileutils'

RSpec.describe KjuiTools::Core::Resources::ColorManager do
  let(:temp_dir) { Dir.mktmpdir }
  let(:resources_dir) { File.join(temp_dir, 'Resources') }
  let(:source_path) { temp_dir }
  let(:config) { { 'source_directory' => 'src/main' } }
  let(:manager) { described_class.new(config, source_path, resources_dir) }

  before do
    FileUtils.mkdir_p(resources_dir)
    allow(KjuiTools::Core::Logger).to receive(:info)
    allow(KjuiTools::Core::Logger).to receive(:debug)
    allow(KjuiTools::Core::Logger).to receive(:warn)
    allow(KjuiTools::Core::Logger).to receive(:error)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates manager with config' do
      expect(manager).to be_a(described_class)
    end

    it 'loads existing colors.json' do
      colors = { 'primary' => '#007AFF' }
      File.write(File.join(resources_dir, 'colors.json'), JSON.generate(colors))

      new_manager = described_class.new(config, source_path, resources_dir)
      expect(new_manager).to be_a(described_class)
    end

    it 'handles invalid colors.json' do
      File.write(File.join(resources_dir, 'colors.json'), 'invalid json')

      expect { described_class.new(config, source_path, resources_dir) }.not_to raise_error
    end

    it 'loads existing defined_colors.json' do
      colors = { 'custom_color' => nil }
      File.write(File.join(resources_dir, 'defined_colors.json'), JSON.generate(colors))

      new_manager = described_class.new(config, source_path, resources_dir)
      expect(new_manager).to be_a(described_class)
    end

    it 'handles invalid defined_colors.json' do
      File.write(File.join(resources_dir, 'defined_colors.json'), 'invalid json')

      expect { described_class.new(config, source_path, resources_dir) }.not_to raise_error
    end
  end

  describe '#process_colors' do
    it 'returns early for empty processed files' do
      manager.process_colors([], 0, 0, config)
      expect(File.exist?(File.join(resources_dir, 'colors.json'))).to be false
    end

    it 'extracts colors from JSON files' do
      json_file = File.join(temp_dir, 'test.json')
      File.write(json_file, JSON.generate({ 'background' => '#FF0000' }))

      manager.process_colors([json_file], 1, 0, config)

      expect(File.exist?(File.join(resources_dir, 'colors.json'))).to be true
    end

    it 'skips binding expressions' do
      json_file = File.join(temp_dir, 'test.json')
      File.write(json_file, JSON.generate({ 'background' => '@{viewModel.backgroundColor}' }))

      manager.process_colors([json_file], 1, 0, config)

      content = File.read(json_file)
      data = JSON.parse(content)
      expect(data['background']).to eq('@{viewModel.backgroundColor}')
    end

    it 'generates ColorManager.kt when resource_manager_directory is configured' do
      config_with_manager = config.merge('resource_manager_directory' => 'generated')
      manager_with_config = described_class.new(config_with_manager, source_path, resources_dir)

      colors = { 'primary' => '#007AFF' }
      File.write(File.join(resources_dir, 'colors.json'), JSON.generate(colors))
      manager_with_config.instance_variable_set(:@colors_data, colors)

      json_file = File.join(temp_dir, 'test.json')
      File.write(json_file, JSON.generate({ 'background' => '#FF0000' }))

      manager_with_config.process_colors([json_file], 1, 0, config_with_manager)

      output_file = File.join(temp_dir, 'generated', 'ColorManager.kt')
      expect(File.exist?(output_file)).to be true
    end
  end

  describe '#apply_to_color_assets' do
    it 'creates colors.xml if it does not exist' do
      colors = { 'primary' => '#007AFF' }
      File.write(File.join(resources_dir, 'colors.json'), JSON.generate(colors))

      new_manager = described_class.new(config, source_path, resources_dir)
      new_manager.apply_to_color_assets

      colors_xml_path = File.join(temp_dir, 'src/main/res/values/colors.xml')
      expect(File.exist?(colors_xml_path)).to be true
    end

    it 'updates existing colors.xml' do
      colors_dir = File.join(temp_dir, 'src/main/res/values')
      FileUtils.mkdir_p(colors_dir)

      File.write(File.join(colors_dir, 'colors.xml'), <<~XML)
        <?xml version="1.0" encoding="utf-8"?>
        <resources>
          <color name="existing">#FFFFFF</color>
        </resources>
      XML

      colors = { 'primary' => '#007AFF' }
      File.write(File.join(resources_dir, 'colors.json'), JSON.generate(colors))

      new_manager = described_class.new(config, source_path, resources_dir)
      new_manager.apply_to_color_assets

      content = File.read(File.join(colors_dir, 'colors.xml'))
      expect(content).to include('primary')
    end

    it 'does not overwrite colors.json values with nil from defined_colors.json' do
      colors_dir = File.join(temp_dir, 'src/main/res/values')
      FileUtils.mkdir_p(colors_dir)

      File.write(File.join(colors_dir, 'colors.xml'), <<~XML)
        <?xml version="1.0" encoding="utf-8"?>
        <resources>
        </resources>
      XML

      # colors.json has proper color values
      colors = { 'amber' => '#D4A574', 'charcoal' => '#1a1a1a' }
      File.write(File.join(resources_dir, 'colors.json'), JSON.generate(colors))

      # defined_colors.json has nil values for the same keys (legacy behavior)
      defined_colors = { 'amber' => nil, 'charcoal' => nil }
      File.write(File.join(resources_dir, 'defined_colors.json'), JSON.generate(defined_colors))

      new_manager = described_class.new(config, source_path, resources_dir)
      new_manager.apply_to_color_assets

      content = File.read(File.join(colors_dir, 'colors.xml'))
      # Should include colors from colors.json, not be skipped due to nil values
      expect(content).to include('amber')
      expect(content).to include('#FFD4A574')
      expect(content).to include('charcoal')
      expect(content).to include('#FF1A1A1A')
    end

    it 'adds defined_colors only when colors.json does not have the key' do
      colors_dir = File.join(temp_dir, 'src/main/res/values')
      FileUtils.mkdir_p(colors_dir)

      File.write(File.join(colors_dir, 'colors.xml'), <<~XML)
        <?xml version="1.0" encoding="utf-8"?>
        <resources>
        </resources>
      XML

      # colors.json has one color
      colors = { 'primary' => '#007AFF' }
      File.write(File.join(resources_dir, 'colors.json'), JSON.generate(colors))

      # defined_colors.json has additional colors with values
      defined_colors = { 'secondary' => '#FF6B6B' }
      File.write(File.join(resources_dir, 'defined_colors.json'), JSON.generate(defined_colors))

      new_manager = described_class.new(config, source_path, resources_dir)
      new_manager.apply_to_color_assets

      content = File.read(File.join(colors_dir, 'colors.xml'))
      expect(content).to include('primary')
      expect(content).to include('secondary')
    end
  end

  describe '#is_color_property?' do
    it 'identifies background properties' do
      expect(manager.send(:is_color_property?, 'background')).to be true
      expect(manager.send(:is_color_property?, 'backgroundColor')).to be true
    end

    it 'identifies text color properties' do
      expect(manager.send(:is_color_property?, 'fontColor')).to be true
      expect(manager.send(:is_color_property?, 'textColor')).to be true
      expect(manager.send(:is_color_property?, 'color')).to be true
    end

    it 'identifies state background properties' do
      expect(manager.send(:is_color_property?, 'disabledBackground')).to be true
      expect(manager.send(:is_color_property?, 'tapBackground')).to be true
      expect(manager.send(:is_color_property?, 'pressedBackground')).to be true
      expect(manager.send(:is_color_property?, 'selectedBackground')).to be true
    end

    it 'identifies gradient color properties' do
      expect(manager.send(:is_color_property?, 'gradientStartColor')).to be true
      expect(manager.send(:is_color_property?, 'gradientEndColor')).to be true
      expect(manager.send(:is_color_property?, 'startColor')).to be true
    end

    it 'rejects non-color properties' do
      expect(manager.send(:is_color_property?, 'width')).to be false
      expect(manager.send(:is_color_property?, 'text')).to be false
      expect(manager.send(:is_color_property?, 'type')).to be false
    end
  end

  describe '#is_hex_color?' do
    it 'identifies 6-character hex colors' do
      expect(manager.send(:is_hex_color?, '#FF0000')).to be true
      expect(manager.send(:is_hex_color?, 'FF0000')).to be true
    end

    it 'identifies 3-character hex colors' do
      expect(manager.send(:is_hex_color?, '#F00')).to be true
      expect(manager.send(:is_hex_color?, 'F00')).to be true
    end

    it 'identifies 8-character ARGB hex colors' do
      expect(manager.send(:is_hex_color?, '#80FF0000')).to be true
    end

    it 'rejects non-hex strings' do
      expect(manager.send(:is_hex_color?, 'red')).to be false
      expect(manager.send(:is_hex_color?, 'primaryColor')).to be false
    end

    it 'rejects binding expressions' do
      expect(manager.send(:is_hex_color?, '@{viewModel.color}')).to be false
    end

    it 'rejects non-string values' do
      expect(manager.send(:is_hex_color?, 123)).to be false
      expect(manager.send(:is_hex_color?, nil)).to be false
    end
  end

  describe '#normalize_hex_color' do
    it 'adds # prefix if missing' do
      expect(manager.send(:normalize_hex_color, 'FF0000')).to eq('#FF0000')
    end

    it 'converts to uppercase' do
      expect(manager.send(:normalize_hex_color, '#ff0000')).to eq('#FF0000')
    end

    it 'expands 3-character hex' do
      expect(manager.send(:normalize_hex_color, '#F00')).to eq('#FF0000')
    end

    it 'preserves 8-character ARGB hex' do
      expect(manager.send(:normalize_hex_color, '#80FF0000')).to eq('#80FF0000')
    end
  end

  describe '#parse_hex_to_rgb' do
    it 'parses 6-character hex' do
      expect(manager.send(:parse_hex_to_rgb, '#FF0000')).to eq([255, 0, 0])
      expect(manager.send(:parse_hex_to_rgb, '#00FF00')).to eq([0, 255, 0])
      expect(manager.send(:parse_hex_to_rgb, '#0000FF')).to eq([0, 0, 255])
    end

    it 'parses 3-character hex' do
      expect(manager.send(:parse_hex_to_rgb, '#F00')).to eq([255, 0, 0])
    end

    it 'parses 8-character ARGB hex' do
      expect(manager.send(:parse_hex_to_rgb, '#80FF0000')).to eq([255, 0, 0])
    end

    it 'returns nil for invalid hex' do
      expect(manager.send(:parse_hex_to_rgb, 'invalid')).to be_nil
    end
  end

  describe '#generate_color_key' do
    it 'generates white for bright colors' do
      key = manager.send(:generate_color_key, '#FFFFFF')
      expect(key).to eq('white')
    end

    it 'generates black for dark colors' do
      key = manager.send(:generate_color_key, '#000000')
      expect(key).to eq('black')
    end

    it 'generates key with color suffix for colored values' do
      key = manager.send(:generate_color_key, '#FF0000')
      expect(key).to include('red')
    end

    it 'generates key with gray suffix for grayscale' do
      key = manager.send(:generate_color_key, '#808080')
      expect(key).to include('gray')
    end

    it 'adds counter suffix for duplicates' do
      # First key
      key1 = manager.send(:generate_color_key, '#000000')
      expect(key1).to eq('black')

      # Themed: @extracted_colors is { mode => { key => hex } }. Seed the
      # default extract mode ('light') so the duplicate check finds it.
      manager.instance_variable_get(:@extracted_colors)['light']['black'] = '#000000'

      # Second key should be incremented
      key2 = manager.send(:generate_color_key, '#010101')
      expect(key2).to eq('black_2')
    end
  end

  describe '#process_and_replace_color' do
    it 'skips data binding expressions' do
      result = manager.send(:process_and_replace_color, '@{data.color}')
      expect(result).to eq('@{data.color}')
    end

    it 'skips binding expressions with complex expressions' do
      result = manager.send(:process_and_replace_color, '@{viewModel.backgroundColor}')
      expect(result).to eq('@{viewModel.backgroundColor}')
    end

    it 'replaces hex colors with keys' do
      result = manager.send(:process_and_replace_color, '#FF0000')
      expect(result).not_to eq('#FF0000')
    end

    it 'returns existing key for known colors' do
      # Themed: seed the light palette directly (no more @colors_data flat map).
      manager.instance_variable_get(:@palettes)['light']['primary'] = '#007AFF'
      result = manager.send(:process_and_replace_color, '#007AFF')
      expect(result).to eq('primary')
    end

    it 'tracks undefined color keys' do
      manager.send(:process_and_replace_color, 'undefinedColor')
      expect(manager.instance_variable_get(:@undefined_colors)).to include('undefinedColor')
    end
  end

  describe '#replace_colors_recursive' do
    it 'replaces colors in hash' do
      data = { 'background' => '#FF0000' }
      manager.send(:replace_colors_recursive, data)
      expect(data['background']).not_to eq('#FF0000')
    end

    it 'handles nested hashes' do
      data = { 'view' => { 'background' => '#FF0000' } }
      manager.send(:replace_colors_recursive, data)
      expect(data['view']['background']).not_to eq('#FF0000')
    end

    it 'handles arrays' do
      data = [{ 'background' => '#FF0000' }]
      manager.send(:replace_colors_recursive, data)
      expect(data[0]['background']).not_to eq('#FF0000')
    end

    it 'ignores non-color properties' do
      data = { 'text' => 'Hello' }
      modified = manager.send(:replace_colors_recursive, data)
      expect(modified).to be false
      expect(data['text']).to eq('Hello')
    end

    it 'skips binding expressions in recursive replacement' do
      data = { 'background' => '@{viewModel.backgroundColor}' }
      modified = manager.send(:replace_colors_recursive, data)
      expect(modified).to be false
      expect(data['background']).to eq('@{viewModel.backgroundColor}')
    end

    context 'with data Color defaultValue' do
      before do
        # Themed schema: pre-seed the light palette so the recursive replacer
        # can find #D4A574 → 'light_pink' on lookup.
        manager.instance_variable_get(:@palettes)['light']['light_pink'] = '#D4A574'
      end

      it 'replaces hex defaultValue with color key' do
        data = {
          'data' => [
            { 'name' => 'selectedTabColor', 'class' => 'Color', 'defaultValue' => '#D4A574' }
          ]
        }
        manager.send(:replace_colors_recursive, data)
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
        manager.send(:replace_colors_recursive, data)
        expect(data['children'][0]['data'][0]['defaultValue']).to eq('light_pink')
      end
    end
  end

  describe '#snake_to_camel' do
    it 'converts snake_case to camelCase' do
      expect(manager.send(:snake_to_camel, 'primary_blue')).to eq('primaryBlue')
      expect(manager.send(:snake_to_camel, 'dark_gray')).to eq('darkGray')
    end

    it 'handles single word' do
      expect(manager.send(:snake_to_camel, 'primary')).to eq('primary')
    end

    it 'handles numbers' do
      expect(manager.send(:snake_to_camel, 'white_2')).to eq('white2')
    end
  end

  describe '#generate_kotlin_code (themed)' do
    let(:colors_file) { File.join(resources_dir, 'colors.json') }

    def build_manager(palette_json)
      File.write(colors_file, JSON.pretty_generate(palette_json))
      described_class.new(config, source_path, resources_dir)
    end

    context 'with valid colors (single light mode)' do
      it 'generates ColorManager object with views + compose sub-objects' do
        m = build_manager('modes' => ['light'], 'light' => { 'primary' => '#007AFF' })
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to include('object ColorManager')
        expect(code).to include('object views')
        expect(code).to include('object compose')
      end

      it 'includes snake_case → camelCase color accessors' do
        m = build_manager('modes' => ['light'], 'light' => { 'primary_blue' => '#007AFF' })
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))
        expect(code).to include('primaryBlue')
      end

      it 'views.color and compose.color return nullable types' do
        m = build_manager('modes' => ['light'], 'light' => { 'primary' => '#007AFF' })
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to include('fun color(key: String): Int?')
        expect(code).to include('fun color(key: String): ComposeColor?')
      end

      it 'handles binding expressions by returning null' do
        m = build_manager('modes' => ['light'], 'light' => { 'primary' => '#007AFF' })
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to include('if (key.startsWith("@{") && key.endsWith("}")) return null')
      end

      it 'uses Log.w for runtime warnings (never println)' do
        m = build_manager('modes' => ['light'], 'light' => { 'primary' => '#007AFF' })
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to include('import android.util.Log')
        expect(code).to include('Log.w(TAG,')
        expect(code).not_to include('println(')
      end
    end
  end

  describe 'themed schema support' do
    let(:colors_file) { File.join(resources_dir, 'colors.json') }

    describe 'schema migration (flat → themed)' do
      it 'auto-migrates flat colors.json on apply_to_color_assets' do
        File.write(colors_file, JSON.pretty_generate({
          'primary' => '#FF0000',
          'secondary' => '#00FF00'
        }))

        m = described_class.new(config, source_path, resources_dir)
        m.apply_to_color_assets

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

        m = described_class.new(config, source_path, resources_dir)
        expect(m.modes).to eq(%w[day night high_contrast])
        expect(m.fallback_mode).to eq('day')
      end
    end

    describe 'ColorManager.kt themed API' do
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
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to include('enum class ColorMode')
        expect(code).to include('LIGHT("light")')
        expect(code).to include('DARK("dark")')
      end

      it 'emits per-mode palette sub-objects (light / dark) inside views and compose' do
        m = described_class.new(config, source_path, resources_dir)
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to match(/object light \{[\s\S]*?primary/m)
        expect(code).to match(/object dark \{[\s\S]*?primary/m)
      end

      it 'emits mutableStateOf-backed currentMode for Compose recomposition' do
        m = described_class.new(config, source_path, resources_dir)
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to include('mutableStateOf(fallbackMode)')
        expect(code).to include('val currentMode: ColorMode get() = _currentMode.value')
      end

      it 'emits setMode + subscribe + applySystemMode APIs' do
        m = described_class.new(config, source_path, resources_dir)
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to include('fun setMode(mode: ColorMode)')
        expect(code).to include('fun subscribe(key: Any, callback: () -> Unit)')
        expect(code).to include('fun applySystemMode(osMode: String)')
      end

      it 'emits fallback lookup chain in views.color' do
        m = described_class.new(config, source_path, resources_dir)
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to include('palettes[mode]?.get(key) ?: palettes[fallbackMode]?.get(key)')
      end

      it 'emits systemModeMapping table' do
        m = described_class.new(config, source_path, resources_dir)
        code = m.send(:generate_kotlin_code, m.send(:deep_clone_palettes))

        expect(code).to include('systemModeMapping: Map<String, ColorMode>')
      end
    end

    describe 'colors.xml emission (Android resource qualifiers)' do
      it 'writes fallback palette to res/values/colors.xml and dark to res/values-night/' do
        File.write(colors_file, JSON.pretty_generate({
          'modes' => %w[light dark],
          'fallback_mode' => 'light',
          'light' => { 'primary' => '#FFFFFF' },
          'dark' => { 'primary' => '#000000' }
        }))

        xml_config = config.merge('source_directory' => 'src/main')
        m = described_class.new(xml_config, source_path, resources_dir)
        m.apply_to_color_assets

        day_xml = File.join(source_path, 'src/main/res/values/colors.xml')
        night_xml = File.join(source_path, 'src/main/res/values-night/colors.xml')

        expect(File.exist?(day_xml)).to be true
        expect(File.exist?(night_xml)).to be true
        expect(File.read(day_xml)).to include('#FFFFFFFF')  # padded to ARGB
        expect(File.read(night_xml)).to include('#FF000000')
      end
    end
  end
end
