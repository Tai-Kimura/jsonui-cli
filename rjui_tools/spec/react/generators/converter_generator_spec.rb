# frozen_string_literal: true

require_relative '../../spec_helper'
require 'fileutils'
require 'stringio'
require 'tmpdir'
require 'react/generators/converter_generator'

RSpec.describe RjuiTools::React::Generators::ConverterGenerator do
  let(:generator) { described_class.new('Card', { attributes: {} }, {}) }

  describe '#normalize_type' do
    it 'treats canonical lowercase names as non-optional base types' do
      expect(generator.send(:normalize_type, 'string')).to eq(base: 'string', array: false, optional: false)
      expect(generator.send(:normalize_type, 'int')).to eq(base: 'int', array: false, optional: false)
      expect(generator.send(:normalize_type, 'bool')).to eq(base: 'bool', array: false, optional: false)
    end

    it 'strips a trailing `?` and marks the type optional' do
      expect(generator.send(:normalize_type, 'String?')).to eq(base: 'string', array: false, optional: true)
      expect(generator.send(:normalize_type, 'Int?')).to eq(base: 'int', array: false, optional: true)
    end

    it 'unwraps `[X]?` into an optional array of X' do
      expect(generator.send(:normalize_type, '[Int]?')).to eq(base: 'int', array: true, optional: true)
    end

    it 'unwraps `[X]` into a required array of X' do
      expect(generator.send(:normalize_type, '[String]')).to eq(base: 'string', array: true, optional: false)
    end

    it 'preserves custom Swift-ish type names (lower-cased)' do
      expect(generator.send(:normalize_type, 'MyModel?')).to eq(base: 'mymodel', array: false, optional: true)
    end
  end

  describe '#map_type_to_json_type' do
    it 'maps optional String? to [string, binding]' do
      expect(generator.send(:map_type_to_json_type, 'String?')).to eq(['string', 'binding'])
    end

    it 'maps optional Int? to [number, binding]' do
      expect(generator.send(:map_type_to_json_type, 'Int?')).to eq(['number', 'binding'])
    end

    it 'maps optional Bool to [boolean, binding]' do
      expect(generator.send(:map_type_to_json_type, 'Bool')).to eq(['boolean', 'binding'])
    end

    it 'maps array-of-int to [array, binding]' do
      expect(generator.send(:map_type_to_json_type, '[Int]?')).to eq(['array', 'binding'])
    end

    it 'maps Color to [string, binding] (semantic color name or @{binding})' do
      expect(generator.send(:map_type_to_json_type, 'Color')).to eq(['string', 'binding'])
    end

    it 'maps optional Color? to [string, binding]' do
      expect(generator.send(:map_type_to_json_type, 'Color?')).to eq(['string', 'binding'])
    end

    it 'falls through to binding-only for truly custom types' do
      expect(generator.send(:map_type_to_json_type, 'MyCustomType?')).to eq('binding')
    end

    it 'maps Callback (exposedEvents) to binding-only' do
      expect(generator.send(:map_type_to_json_type, 'Callback')).to eq('binding')
    end
  end

  describe 'ReactComponentGenerator scaffold id contract (regression: rjui-converter-scaffold-component-props-missing-id)' do
    let(:component_generator) do
      RjuiTools::React::Generators::ReactComponentGenerator.new('GanttChart', { attributes: {} }, {})
    end

    it 'includes id in the props interface, destructure and root element' do
      template = component_generator.send(:component_template)
      expect(template).to include('id?: string;')
      expect(template).to match(/\{ id, children, className \}/)
      expect(template).to include('<div id={id} className="gantt-chart">')
    end
  end

  describe 'overwrite prompt non-interactive behavior (regression: rjui-generator-overwrite-prompt-crashes-on-eof)' do
    it 'treats stdin EOF as "n" instead of crashing on nil (converter file)' do
      Dir.mktmpdir do |tmp|
        Dir.chdir(tmp) do
          FileUtils.mkdir_p(File.join(tmp, 'rjui_tools'))
          ext_dir = File.join(tmp, 'rjui_tools', 'lib', 'react', 'converters', 'extensions')
          FileUtils.mkdir_p(ext_dir)
          existing_file = File.join(ext_dir, 'card_converter.rb')
          File.write(existing_file, "ORIGINAL\n")

          original_stdin = $stdin
          $stdin = StringIO.new('') # immediate EOF -> gets returns nil
          begin
            expect { generator.send(:create_converter_file) }.not_to raise_error
          ensure
            $stdin = original_stdin
          end
          expect(File.read(existing_file)).to eq("ORIGINAL\n")
        end
      end
    end

    it 'overwrites without prompting when options[:force] is set' do
      Dir.mktmpdir do |tmp|
        Dir.chdir(tmp) do
          FileUtils.mkdir_p(File.join(tmp, 'rjui_tools'))
          ext_dir = File.join(tmp, 'rjui_tools', 'lib', 'react', 'converters', 'extensions')
          FileUtils.mkdir_p(ext_dir)
          existing_file = File.join(ext_dir, 'card_converter.rb')
          File.write(existing_file, "ORIGINAL\n")

          forced = described_class.new('Card', { attributes: {}, force: true }, {})
          original_stdin = $stdin
          $stdin = StringIO.new('') # would crash/deny if the prompt were reached
          begin
            forced.send(:create_converter_file)
          ensure
            $stdin = original_stdin
          end
          expect(File.read(existing_file)).not_to eq("ORIGINAL\n")
        end
      end
    end

    it 'skips the existing component file with options[:skip_existing]' do
      Dir.mktmpdir do |tmp|
        Dir.chdir(tmp) do
          comp_dir = File.join(tmp, 'src', 'components', 'extensions')
          FileUtils.mkdir_p(comp_dir)
          existing_file = File.join(comp_dir, 'Card.tsx')
          File.write(existing_file, "USER OWNED\n")

          gen = RjuiTools::React::Generators::ReactComponentGenerator.new(
            'Card', { attributes: {}, skip_existing: true }, {}
          )
          gen.send(:create_component_file)
          expect(File.read(existing_file)).to eq("USER OWNED\n")
        end
      end
    end
  end

  describe 'ReactComponentGenerator#ruby_type_to_typescript' do
    let(:component_generator) do
      RjuiTools::React::Generators::ReactComponentGenerator.new('Card', { attributes: {} }, {})
    end

    it 'maps Callback (exposedEvents) to a void function type' do
      expect(component_generator.send(:ruby_type_to_typescript, 'Callback'))
        .to eq('(...args: any[]) => void')
    end

    it 'emits the function type into the props interface' do
      gen = RjuiTools::React::Generators::ReactComponentGenerator.new(
        'Card', { attributes: { 'onDateSelected' => 'Callback' }, is_container: false }, {}
      )
      interface = gen.send(:generate_props_interface)
      expect(interface).to include('onDateSelected?: (...args: any[]) => void;')
    end
  end

  describe '#generate_props_lines binding branch (regression: rjui-converter-scaffold-binding-props-missing-data-prefix)' do
    it 'resolves @{} bindings through add_viewmodel_data_prefix like built-in converters' do
      gen = described_class.new('Card', { attributes: { 'selectionMode' => 'String?' } }, {})
      out = gen.send(:generate_props_lines).join("\n")
      expect(out).to include('add_viewmodel_data_prefix(selectionMode_value[2..-2])')
      expect(out).not_to include('prop_name = selectionMode_value[2..-2]')
    end
  end

  describe '#emit_literal_branch' do
    def lines_for(type_str)
      t = generator.send(:normalize_type, type_str)
      generator.send(:emit_literal_branch, 'filename', t).join("\n")
    end

    it 'emits a template-literal escape path for String?, not .inspect' do
      out = lines_for('String?')
      expect(out).to include('escaped = filename_value.to_s.gsub')
      expect(out).to include('filename={`')
      expect(out).not_to include('.inspect')
    end

    it 'routes snake_case string literals through StringManager for localization' do
      # Matches the standard Label `text` pass: `"title": "toc_title"` in
      # layout → `title={StringManager.currentLanguage.xxx}` in generated
      # JSX. Hand-written English like `"title": "On this page"` still
      # falls through the template-literal path.
      out = lines_for('String?')
      # convert_string_key returns nil on strings.json miss — the scaffold
      # captures the result with assignment-in-conditional and falls back
      # to the template-literal path when nil.
      expect(out).to include('(resolved = convert_string_key(filename_value))')
      # Template-literal fallback present for literals and unregistered
      # identifiers (e.g. "bash", "yaml").
      expect(out).to include('filename={`')
    end

    it 'emits a numeric embed for Int?' do
      out = lines_for('Int?')
      expect(out).to include('filename={#{filename_value}}')
      expect(out).not_to include('.inspect')
    end

    it 'emits a boolean embed for Bool' do
      out = lines_for('Bool')
      expect(out).to include("filename_value ? 'true' : 'false'")
      expect(out).not_to include('.inspect')
    end

    it 'emits JSON.generate for arrays instead of .inspect' do
      out = lines_for('[Int]?')
      expect(out).to include('JSON.generate(filename_value)')
      expect(out).not_to include('.inspect')
    end

    it 'routes array JSON output through rewrite_json_string_values for in-element localization' do
      # Array-of-objects props (TableOfContents.items, Breadcrumb.items) need
      # element-level StringManager rewriting: `label: "toc_row_x"` in layout
      # must become `label: StringManager.currentLanguage.xxx` in the emitted
      # JSX, while non-resolving identifier fields stay literal.
      out = lines_for('[String]?')
      expect(out).to include('rewrite_json_string_values')
      expect(out).to include('JSON.generate(filename_value)')
    end

    it 'emits JSON.generate for custom types instead of .inspect' do
      out = lines_for('MyModel?')
      expect(out).to include('JSON.generate(filename_value)')
      expect(out).not_to include('.inspect')
    end
  end

  describe '#create_converter_file with JUI_SKIP_EXISTING=1' do
    # `jui build` calls each platform's `g converter` non-interactively.
    # Without the env-var bypass the Ruby generator would fall into
    # `print "Overwrite? (y/n)"` + `gets.chomp` — that crashes on a closed
    # stdin and blocks the build either way. The env var short-circuits.
    it 'leaves an existing converter file untouched without prompting' do
      Dir.mktmpdir do |tmp|
        Dir.chdir(tmp) do
          # Force `extensions_dir` into the tmpdir by creating rjui_tools/
          FileUtils.mkdir_p(File.join(tmp, 'rjui_tools'))
          ext_dir = File.join(tmp, 'rjui_tools', 'lib', 'react', 'converters', 'extensions')
          FileUtils.mkdir_p(ext_dir)
          existing_file = File.join(ext_dir, 'card_converter.rb')
          File.write(existing_file, "ORIGINAL\n")

          original_env = ENV['JUI_SKIP_EXISTING']
          ENV['JUI_SKIP_EXISTING'] = '1'
          begin
            # `$stdin.gets` would blow up if reached — test passes only if
            # the env-var branch returned first.
            original_stdin = $stdin
            $stdin = StringIO.new('')
            begin
              generator.send(:create_converter_file)
            ensure
              $stdin = original_stdin
            end
          ensure
            if original_env.nil?
              ENV.delete('JUI_SKIP_EXISTING')
            else
              ENV['JUI_SKIP_EXISTING'] = original_env
            end
          end

          expect(File.read(existing_file)).to eq("ORIGINAL\n")
        end
      end
    end
  end
end
