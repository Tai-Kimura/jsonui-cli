# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'core/config_manager'
require 'core/resources/color_manager'
require 'react/helpers/string_manager_helper'
require 'react/react_generator'

# Ticket sjui-resource-managers-emit-swift-that-does-not-compile, the web
# section. ColorManager.ts names a getter after every colour and after every
# mode, and two kinds of key gave a file tsc rejects: a key that starts with a
# digit (`get 4ecdc4()`, `4ecdc4: '…'`) and a colour named like a mode (two
# `get light()`, TS2300). A reserved word is a legal property and getter name
# here, so it is left alone. Only those names change, as sjui names them: a
# leading digit gets `_`, and the mode's getter is `<mode>Palette` when a
# colour has its name.
#
# The StringManager declares no members — the generated views read
# `StringManager.currentLanguage.<accessor>` off a string map — so the only
# shape that breaks is an accessor a dot cannot take (`-` or a space in a
# key); that one is written with brackets.
RSpec.describe 'generated TypeScript names from resource keys' do
  describe 'ColorManager' do
    def generate(colors)
      Dir.mktmpdir do |dir|
        resources = File.join(dir, 'Resources')
        FileUtils.mkdir_p(resources)
        File.write(File.join(resources, 'colors.json'), JSON.generate(colors))
        allow(RjuiTools::Core::Logger).to receive(:info)
        manager = RjuiTools::Core::Resources::ColorManager.new(
          { 'generated_directory' => 'gen', 'typescript' => true }, dir, resources
        )
        manager.send(:generate_color_manager)
        File.read(File.join(dir, 'gen', 'ColorManager.ts'))
      end
    end

    # The flat colors.json form: its colours are the `light` palette.
    let(:clashing) { { 'light' => '#FFFFFF', 'ink' => '#111111', '4ecdc4' => '#4ECDC4', 'default' => '#000000' } }

    it 'names the palette getter `lightPalette` when a colour is named `light`, and prefixes a digit-led colour' do
      ts = generate(clashing)
      expect(ts).to include('  get lightPalette() { return _lightPalette; }', "  get light() { return this.color('light'); }",
                            "  get _4ecdc4() { return this.color('4ecdc4'); }", "  _4ecdc4: '#4ECDC4',",
                            "  get default() { return this.color('default'); }")
      expect(ts.scan(/^  get light\(\)/).size).to eq(1)
    end

    it 'control: with no colour of a mode name the mode getters keep their names' do
      ts = generate({ 'modes' => %w[light dark], 'light' => { 'ink' => '#111111' }, 'dark' => { 'ink' => '#EEEEEE' } })
      expect(ts).to include('  get light() { return _lightPalette; }', '  get dark() { return _darkPalette; }')
      expect(ts).not_to include('Palette() {')
    end

    it 'type-checks, with the getters a consumer reads' do
      ts = generate(clashing)
      expect("#{ts}\nconst _uses = [ColorManager.lightPalette.ink, ColorManager.light, ColorManager._4ecdc4, " \
             "ColorManager.default];\n").to compile_as_typescript
    end
  end

  describe 'StringManager references' do
    let(:host) do
      Class.new do
        include RjuiTools::React::Helpers::StringManagerHelper

        def initialize(config)
          @config = config
        end
      end.new({ '_current_json_name' => 'catalog' })
    end

    around do |example|
      Dir.mktmpdir do |dir|
        layouts = File.join(dir, 'Layouts')
        FileUtils.mkdir_p(File.join(layouts, 'Resources'))
        File.write(File.join(dir, 'rjui.config.json'), JSON.generate('layouts_directory' => layouts))
        File.write(File.join(layouts, 'Resources', 'strings.json'),
                   JSON.generate('catalog' => { 'icon-label_description' => 'Icon label', 'title' => 'Title',
                                                '15_minutes' => '15 minutes' }))
        Dir.chdir(dir) { example.run }
      end
    end

    it 'writes brackets only for an accessor a dot cannot take' do
      expect(host.convert_string_key('icon-label_description')).to eq('{StringManager.currentLanguage["catalogIcon-labelDescription"]}')
      expect(host.convert_string_key('title')).to eq('{StringManager.currentLanguage.catalogTitle}')
      expect(host.convert_string_key('15_minutes')).to eq('{StringManager.currentLanguage.catalog15Minutes}')
    end

    it 'type-checks, as written and as the generated view rewrites it to `$s`' do
      refs = %w[icon-label_description title 15_minutes].map { |k| host.convert_string_key(k)[1..-2] }
      # Every reference reads the snapshot; one left on StringManager would
      # still type-check but not re-render on setLanguage.
      expect(RjuiTools::React::ReactGenerator.read_strings_from_snapshot(refs.join(', '))).not_to include('StringManager')
      source = "declare const StringManager: { currentLanguage: Record<string, string> };\n" \
               "declare const $s: Record<string, string>;\n" \
               "const _a: string[] = [#{refs.join(', ')}];\n" \
               "const _b: string[] = [#{RjuiTools::React::ReactGenerator.read_strings_from_snapshot(refs.join(', '))}];\n"
      expect(source).to compile_as_typescript
    end
  end
end
