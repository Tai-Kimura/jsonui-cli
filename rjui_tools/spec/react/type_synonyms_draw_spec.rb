# frozen_string_literal: true

require 'json'
require_relative '../../lib/react/react_generator'
require_relative '../../lib/core/type_synonyms'

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
    'Web' => { 'url' => 'https://example.invalid/' }
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
