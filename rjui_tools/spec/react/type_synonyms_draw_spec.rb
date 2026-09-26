# frozen_string_literal: true

require 'json'
require_relative '../../lib/react/react_generator'
require_relative '../../lib/core/type_synonyms'
require_relative '../support/typescript_compiler'

# An app's converter registered under a synonym's name (HStack), standing in
# for one in the app's extensions directory.
class ProbeHStackReactConverter
  def initialize(json, _config)
    @json = json
  end

  def convert_node(_indent = 0)
    "<ProbeHStack type=\"#{@json['type']}\" orientation=\"#{@json['orientation'].inspect}\" />"
  end
end

# A type-synonym spelling emits exactly what the type the table says it is
# drawn as emits (shared/core/type_synonyms.json), with the attributes its
# spelling means — at the root (ReactGenerator) and as a child
# (BaseConverter) — and an app's converter registered under a synonym's name
# is the app's.
#
# Measured before the change: the two converter maps held Text, Scroll,
# Table, Checkbox and CircleImage of their own, and drew the table's other
# spellings (WebView, HStack, Img, ProgressBar, …) as a plain View with an
# "Unknown component type" warning.
RSpec.describe 'type synonyms in the rjui converters' do
  # What each drawn-as type needs to draw.
  RJUI_SYNONYM_EXTRA = {
    'Label' => { 'text' => 't' },
    'TextView' => { 'text' => 't' },
    'Image' => { 'srcName' => 'probe' },
    'CircleImage' => { 'srcName' => 'probe' },
    'NetworkImage' => { 'url' => 'https://example.invalid/x.png' },
    'SelectBox' => { 'items' => %w[a b] },
    'CheckBox' => {},
    'Radio' => { 'text' => 'r' },
    'Segment' => { 'items' => %w[a b] },
    'Slider' => {},
    'Progress' => {},
    'Indicator' => {},
    'View' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'ScrollView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'Collection' => { 'items' => [] },
    'GradientView' => { 'gradient' => ['#FF0000', '#0000FF'] },
    'Blur' => {},
    'Web' => { 'url' => 'https://example.invalid/' },
    'TextField' => { 'text' => 't' },
    'Switch' => {}
  }.freeze

  # The table, read as data here — the converters read it through
  # JsonUIShared::TypeSynonyms.
  RJUI_SYNONYM_TABLE = JSON.parse(File.read(JsonUIShared::TypeSynonyms::DEFAULT_PATH))['synonyms']

  def generator
    RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true })
  end

  def emit(node)
    generator.send(:convert_component, JSON.parse(JSON.generate(node)))
  end

  def emit_as_child(node)
    emit({ 'type' => 'View', 'id' => 'p', 'child' => [JSON.parse(JSON.generate(node))] })
  end

  it 'reads the table' do
    expect(RJUI_SYNONYM_TABLE.size).to be >= 40
  end

  it 'tells a declared type from an unknown one (control)' do
    view = { 'type' => 'View', 'id' => 'n' }.merge(RJUI_SYNONYM_EXTRA['View'])
    expect(emit({ 'type' => 'Label', 'id' => 'n', 'text' => 't' })).not_to eq(emit(view))
  end

  RJUI_SYNONYM_TABLE.each do |spelling, entry|
    target = entry['render_as'] || entry['canonical']
    implied = entry.reject { |key, _| %w[canonical render_as].include?(key) }

    it "emits #{spelling} as #{target}#{implied.empty? ? '' : " with #{implied}"}, at the root and as a child" do
      extra = RJUI_SYNONYM_EXTRA.fetch(target)
      as_target = { 'type' => target, 'id' => 'n' }.merge(extra).merge(implied)
      as_spelling = { 'type' => spelling, 'id' => 'n' }.merge(extra)
      expect(emit(as_target)).to eq(emit(as_target)), "#{target} emits differently each time"
      # An unknown type draws a plain View — for a spelling of View that is
      # the same code, so the warning is what tells the two apart.
      allow(RjuiTools::Core::Logger).to receive(:warn).and_call_original
      expect(emit(as_spelling)).to eq(emit(as_target))
      expect(emit_as_child(as_spelling)).to eq(emit_as_child(as_target))
      expect(RjuiTools::Core::Logger).not_to have_received(:warn).with(/Unknown component type/)
    end
  end

  # The declared alias sections (`_alias_of`), read from the definitions as
  # data here — the converters read them through JsonUIShared::ComponentAliases.
  RJUI_ALIAS_SECTIONS = JSON.parse(File.read(JsonUIShared::ComponentAliases::DEFAULT_DEFINITIONS))
                            .select { |_, section| section.is_a?(Hash) && section['_alias_of'].is_a?(String) }
                            .transform_values { |section| section['_alias_of'] }

  it 'reads the declared alias sections' do
    expect(RJUI_ALIAS_SECTIONS.size).to be >= 4
  end

  RJUI_ALIAS_SECTIONS.each do |alias_name, canonical|
    it "emits the alias section #{alias_name} as #{canonical}, at the root and as a child" do
      extra = RJUI_SYNONYM_EXTRA.fetch(canonical)
      as_canonical = { 'type' => canonical, 'id' => 'n' }.merge(extra)
      as_alias = { 'type' => alias_name, 'id' => 'n' }.merge(extra)
      expect(emit(as_alias)).to eq(emit(as_canonical))
      expect(emit_as_child(as_alias)).to eq(emit_as_child(as_canonical))
    end
  end

  # What the table and the alias sections draw is TypeScript that compiles
  # under --strict: every spelling once, in one component. The examples
  # above compare a spelling's emission with its drawn type's; this one puts
  # the emissions in front of a compiler. What the screen file and its data
  # model declare around the markup (the seeded-state helper, the text
  # inputs' ref, their focus handler) is declared as they write it.
  it 'compiles what every spelling and alias section emits' do
    nodes = RJUI_SYNONYM_TABLE.map { |spelling, entry| [spelling, entry['render_as'] || entry['canonical']] } +
            RJUI_ALIAS_SECTIONS.to_a
    emitted = nodes.map { |spelling, target| emit({ 'type' => spelling, 'id' => 'n' }.merge(RJUI_SYNONYM_EXTRA.fetch(target))) }
    expect(emitted.size).to eq(RJUI_SYNONYM_TABLE.size + RJUI_ALIAS_SECTIONS.size)
    # A root NetworkImage (a synonym's target too) is the NetworkImage
    # built-in, as a nested one is: one converter table (45014517); it was a
    # plain <img> at the root. Declared as the built-in declares its props.
    expect(TypeScriptCompiler.component(*emitted)).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
      #{TypeScriptCompiler.template_declarations('network_image.tsx', 'NetworkImageProps')}
      declare const NetworkImage: (props: NetworkImageProps) => JSX.Element;
      declare const data: { onNIsFocusedChange?: (value: boolean) => void };
      declare const nRef: { current: HTMLInputElement | HTMLTextAreaElement | null };
      declare const JsonUISeeded: <T>(props: { seed: T; children: (value: T, set: (value: T) => void) => JSX.Element }) => JSX.Element;
    TS
  end

  it "draws a node's own orientation, not the one its spelling means" do
    node = { 'type' => 'HStack', 'id' => 'n', 'orientation' => 'vertical' }.merge(RJUI_SYNONYM_EXTRA['View'])
    expect(emit(node)).to eq(emit(node.merge('type' => 'View')))
  end

  describe 'an app converter registered under a synonym name' do
    it 'is given the node as written, before any synonym is resolved — at the root and as a child' do
      gen = generator
      gen.instance_variable_get(:@extension_converters)['HStack'] = ProbeHStackReactConverter
      root = gen.send(:convert_component, { 'type' => 'HStack', 'child' => [] })
      expect(root).to eq('<ProbeHStack type="HStack" orientation="nil" />')
      nested = gen.send(:convert_component, { 'type' => 'View', 'child' => [{ 'type' => 'HStack', 'child' => [] }] })
      expect(nested).to include('<ProbeHStack type="HStack" orientation="nil" />')
    end
  end
end
