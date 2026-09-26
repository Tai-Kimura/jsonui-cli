# frozen_string_literal: true

require 'json'
require 'swiftui/converter_factory'
require 'core/type_synonyms'
require_relative '../support/emitted_swift'
require_relative '../support/swift_compiler'

# An app's converter registered under a synonym's name (HStack), standing in
# for one in the app's extensions directory.
module SjuiTools
  module SwiftUI
    module Views
      module Extensions
        class ProbeHStackConverter
          # (component, indent_level, action_manager, factory, registry,
          # binding_registry): what the factory passes an app's converter
          def initialize(component, *_rest)
            @component = component
          end

          def convert
            "ProbeHStack(#{@component['type']}, orientation: #{@component['orientation'].inspect})"
          end
        end
      end
    end
  end
end

# A type-synonym spelling emits exactly what the type the table says it is
# drawn as emits (shared/core/type_synonyms.json), with the attributes its
# spelling means — and an app's converter registered under a synonym's name
# is the app's.
#
# Measured before the change (this spec against the factory's own cases):
# the factory held seven synonym spellings of its own (Text, Scroll,
# Checkbox, Table, WebView, BlurView, CircleImage) and drew the table's
# other spellings (HStack, Row, Img, ProgressBar, Spinner, …) with the
# default converter.
RSpec.describe 'type synonyms in the sjui SwiftUI converters' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  # What each drawn-as type needs to draw.
  TYPE_SYNONYM_EXTRA = {
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

  # The table, read as data here — the factory reads it through
  # JsonUIShared::TypeSynonyms.
  TYPE_SYNONYM_TABLE = JSON.parse(File.read(JsonUIShared::TypeSynonyms::DEFAULT_PATH))['synonyms']

  def emit(node)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(JSON.parse(JSON.generate(node)), 0, nil, factory, nil).convert.to_s
  end

  it 'reads the table' do
    expect(TYPE_SYNONYM_TABLE.size).to be >= 40
  end

  it 'tells a declared type from the default converter (control)' do
    expect(emit({ 'type' => 'ProbeUndeclaredType', 'id' => 'n' })).not_to eq(emit({ 'type' => 'View', 'id' => 'n' }.merge(TYPE_SYNONYM_EXTRA['View'])))
  end

  TYPE_SYNONYM_TABLE.each do |spelling, entry|
    target = entry['render_as'] || entry['canonical']
    implied = entry.reject { |key, _| %w[canonical render_as].include?(key) }

    it "emits #{spelling} as #{target}#{implied.empty? ? '' : " with #{implied}"}" do
      extra = TYPE_SYNONYM_EXTRA.fetch(target)
      as_target = { 'type' => target, 'id' => 'n' }.merge(extra).merge(implied)
      expected = emit(as_target)
      expect(emit(as_target)).to eq(expected), "#{target} emits differently each time"
      expect(emit({ 'type' => spelling, 'id' => 'n' }.merge(extra))).to eq(expected)
    end
  end

  it "draws a node's own orientation, not the one its spelling means" do
    node = { 'type' => 'HStack', 'id' => 'n', 'orientation' => 'vertical' }.merge(TYPE_SYNONYM_EXTRA['View'])
    expect(emit(node)).to eq(emit(node.merge('type' => 'View')))
  end

  describe 'what a synonym emits' do
    include EmittedSwift

    it 'compiles: an HStack becomes a View with orientation horizontal' do
      swift = emit({ 'type' => 'HStack', 'child' => [{ 'type' => 'Label', 'text' => 'c' }] })
      expect(compilable_view(swift)).to compile_as_swift
    end
  end

  describe 'an app converter registered under a synonym name' do
    it 'is given the node as written, before any synonym is resolved' do
      factory = SjuiTools::SwiftUI::ConverterFactory.new
      factory.instance_variable_set(:@custom_converters, { 'HStack' => 'ProbeHStackConverter' })
      # The factory requires the app's converter file from its extensions
      # directory; the class above stands in for it.
      allow(factory).to receive(:require_relative).and_return(true)
      converter = factory.create_converter({ 'type' => 'HStack', 'child' => [] }, 0, nil, factory, nil)
      expect(converter).to be_a(SjuiTools::SwiftUI::Views::Extensions::ProbeHStackConverter)
      expect(converter.convert).to eq('ProbeHStack(HStack, orientation: nil)')
    end
  end
end
