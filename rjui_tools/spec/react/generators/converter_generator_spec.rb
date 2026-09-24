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

  # rjui-component-scaffold-logs-created-when-it-kept-the-file: until 1.8.113
  # "Created component file" followed the write call unconditionally, so a run
  # that kept the file printed "Skipped existing component" and then "Created"
  # for the same untouched file.
  describe 'ReactComponentGenerator#generate reports what it did to the component file' do
    def generate_in(tmp, options, stdin: '')
      gen = RjuiTools::React::Generators::ReactComponentGenerator.new('Card', { attributes: {} }.merge(options), {})
      original_stdin = $stdin
      $stdin = StringIO.new(stdin)
      out = nil
      begin
        out = capture_stdout { gen.generate }
      ensure
        $stdin = original_stdin
      end
      [out, File.read(File.join(tmp, 'src', 'components', 'extensions', 'Card.tsx'))]
    end

    def capture_stdout
      original = $stdout
      $stdout = StringIO.new
      yield
      $stdout.string
    ensure
      $stdout = original
    end

    around do |example|
      saved_env = ENV.delete('JUI_SKIP_EXISTING')
      Dir.mktmpdir do |tmp|
        Dir.chdir(tmp) do
          @tmp = tmp
          example.run
        end
      end
    ensure
      saved_env.nil? ? ENV.delete('JUI_SKIP_EXISTING') : ENV['JUI_SKIP_EXISTING'] = saved_env
    end

    def plant_user_file
      dir = File.join(@tmp, 'src', 'components', 'extensions')
      FileUtils.mkdir_p(dir)
      File.write(File.join(dir, 'Card.tsx'), "USER OWNED\n")
    end

    it 'says Created when there was no file' do
      out, body = generate_in(@tmp, {})
      expect(out).to include('Created component file')
      expect(body).not_to eq("USER OWNED\n")
    end

    it 'does not say Created when it kept the file' do
      [[{ skip_existing: true }, ''], [{}, "n\n"], [{}, '']].each do |options, answer|
        plant_user_file
        out, body = generate_in(@tmp, options, stdin: answer)
        expect(body).to eq("USER OWNED\n")
        expect(out).not_to include('Created component file'), [options, answer].inspect
      end
      plant_user_file
      ENV['JUI_SKIP_EXISTING'] = '1'
      out, = generate_in(@tmp, {})
      expect(out).to include('Skipped existing component')
      expect(out).not_to include('Created component file')
    end

    it 'says Created when it replaced the file' do
      [[{ force: true }, ''], [{}, "y\n"]].each do |options, answer|
        plant_user_file
        out, body = generate_in(@tmp, options, stdin: answer)
        expect(body).not_to eq("USER OWNED\n")
        expect(out).to include('Created component file'), [options, answer].inspect
      end
    end
  end

  # jui-g-converter-drops-spec-prop-descriptions: until 1.8.113 every
  # regeneration wrote "<key> attribute" over the spec's descriptions.
  describe "#generate_attribute_definition_file with the component spec's descriptions" do
    it 'writes the descriptions handed down by jui g converter --from / --all' do
      Dir.mktmpdir do |tmp|
        gen = described_class.new('DescribedCard', {
          attributes: { 'title' => 'String', '@value' => 'String', 'count' => 'Int' },
          attribute_descriptions: { 'title' => '見出し', 'value' => '入力値' }
        }, {})
        allow(gen).to receive(:attr_defs_dir).and_return(tmp)
        allow(RjuiTools::Core::Logger).to receive(:info)
        gen.send(:generate_attribute_definition_file)

        content = JSON.parse(File.read(File.join(tmp, 'DescribedCard.json'), encoding: 'UTF-8'))
        expect(content['DescribedCard']['title']['description']).to eq('見出し')
        expect(content['DescribedCard']['value']['description']).to eq('入力値')   # the spec names it without "@"
        expect(content['DescribedCard']['count']['description']).to eq('count attribute')
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
