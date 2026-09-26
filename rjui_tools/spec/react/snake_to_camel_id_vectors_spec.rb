# frozen_string_literal: true

require 'json'
require 'react/converters/base_converter'
require 'react/data_model_generator'
require 'react/react_generator'
require_relative '../support/typescript_compiler'

# The lowerCamel stem of an id (refs, focus fields) is written in three
# places that must stay in sync (base_converter.rb says so); all three answer
# the `camel` column of shared/core/camel_case_vectors.json, the spelling
# sjui/kjui give an id, so a web id and a native one are the same word.
RSpec.describe 'id stems in camelCase — shared vectors (rjui)' do
  vectors = JSON.parse(File.read(File.expand_path('../../../shared/core/camel_case_vectors.json', __dir__)))
  owners = [RjuiTools::React::Converters::BaseConverter,
            RjuiTools::React::DataModelGenerator,
            RjuiTools::React::ReactGenerator]

  vectors['cases'].each do |c|
    it "spells #{c['input'].inspect} as the table does, in all three" do
      got = owners.map { |k| k.allocate.send(:snake_to_camel_id, c['input']) }
      expect(got).to eq([c['camel']] * owners.size)
    end
  end

  # The stem is code: react_generator declares `const <stem>Ref` and
  # `<stem>ShrinkRef`, a converter writes `ref={…}` with it, the data model
  # declares `<stem>IsFocused` and its handler. A screen whose ids are every
  # row, and its data model from DataModelGenerator's own writer, compiled
  # together under --strict: each stem is an identifier, and the owners that
  # write it name the same one. React's hooks and the build's helpers are
  # declared as the file uses them.
  it 'writes stems a screen compiles with, declared and used by different owners', :typescript_compile do
    kids = vectors['cases'].each_with_index.flat_map do |c, i|
      [{ 'type' => 'TextField', 'id' => c['input'], 'text' => "@{t#{i}}" },
       { 'type' => 'Label', 'id' => "#{c['input']}_shrink", 'text' => 'x', 'autoShrink' => true }]
    end
    layout = { 'type' => 'View', 'id' => 'root', 'child' => kids }
    screen = RjuiTools::React::ReactGenerator.new({ 'typescript' => true }).generate('Home', layout, screen_id: 'home')
    model_writer = RjuiTools::React::DataModelGenerator.allocate
    model_writer.instance_variable_set(:@use_typescript, true)
    model = model_writer.send(:generate_typescript_content, 'Home', [], [],
                              model_writer.send(:extract_text_field_bindings, layout), {},
                              model_writer.send(:extract_value_bindings, layout))
    expect(screen).to include('const emailVerifyViewRef = useRef')
    source = [model, screen].map { |file| file.lines.reject { |l| l.start_with?('import ') }.join }.join("\n")
    expect(source).to compile_as_typescript.with_ambient(<<~TS)
      declare function useRef<T>(initial: T): { current: T };
      declare function useEffect(effect: () => void, deps?: unknown[]): void;
      declare function useStringManager(): Record<string, string>;
      declare function screenMarker(screenId: string): Record<string, string>;
      declare function applyAutoShrink(element: HTMLElement | null, options: object): void;
      declare namespace JSX {
        interface IntrinsicElements {
          input: { [attr: string]: unknown; onChange?: (e: { target: HTMLInputElement }) => void };
        }
      }
    TS
  end
end
