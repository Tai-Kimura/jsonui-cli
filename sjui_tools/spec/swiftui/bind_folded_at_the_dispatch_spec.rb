# frozen_string_literal: true

require 'json'
require 'swiftui/converter_factory'

# `bind` is folded into the attribute it stands for on the node a built-in
# converter draws — its style merged (StyleLoader, before conversion) — at
# ConverterFactory#create_converter, after the app's own converters were asked
# (JsonUIShared::BindFold). No converter reads `bind` itself. The layout
# normalizer leaves a node with a style or responsive overrides for this fold.
RSpec.describe 'sjui: bind folded at the dispatch' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  convert = ->(node) { SjuiTools::SwiftUI::ConverterFactory.new.create_converter(JSON.parse(JSON.generate(node))).convert }
  vectors = File.expand_path('../../../shared/core/bind_fold_vectors.json', __dir__)

  it 'draws each style case as the table says (the style merged, then folded)' do
    skip 'shared vectors not present in this layout' unless File.exist?(vectors)

    date, switch = JSON.parse(File.read(vectors))['style_cases']
    merged = ->(c) { c['styles'].fetch(c['node']['style']).merge(c['node']).reject { |k, _| k == 'style' } }
    # a style's lone bind on a Date box: the picker reads and writes the binding
    expect(convert.call(merged.call(date))).to include('selectedDate: data.day.toDate(', 'data.day = newValue')
    # a style's isOn beside a layout bind: the static value, no binding
    code = convert.call(merged.call(switch))
    expect(code).not_to include('data.on')
  end

  [
    { 'type' => 'Switch' }, { 'type' => 'Toggle' }, { 'type' => 'CheckBox' }, { 'type' => 'Check' },
    { 'type' => 'Slider' }, { 'type' => 'Segment', 'items' => %w[x y] }, { 'type' => 'Progress' },
    { 'type' => 'SelectBox', 'items' => %w[x y] }, { 'type' => 'SelectBox', 'selectItemType' => 'Date' },
    { 'type' => 'Radio', 'items' => %w[x y] }, { 'type' => 'TextField' }, { 'type' => 'TextView' }
  ].each do |node|
    it "binds a lone bind on #{node.values_at('type', 'selectItemType').compact.join(' ')}" do
      expect(convert.call(node.merge('id' => 'i', 'bind' => '@{b}'))).to include('data.b')
    end
  end

  it 'drops bind beside a static own value' do
    expect(convert.call('type' => 'CheckBox', 'id' => 'i', 'isOn' => true, 'bind' => '@{b}')).not_to include('data.b')
    expect(convert.call('type' => 'Slider', 'id' => 'i', 'value' => 0.5, 'bind' => '@{b}')).not_to include('data.b')
  end

  # No converter reads `bind`. Code only — a comment naming it does not count.
  it 'is read by no converter' do
    token = /\['bind'\]|\["bind"\]/
    hits = lambda do |text, name|
      text.lines.each_with_index.filter_map do |line, i|
        next if line.strip.start_with?('#')

        "#{name}:#{i + 1}" if line.sub(/#.*/, '') =~ token
      end
    end
    expect(hits.call("          if @component['bind'] && x\n", 'read').size).to eq(1)
    expect(hits.call("          # @component['bind'] was read here\n", 'comment').size).to eq(0)

    lib = File.expand_path('../../lib/swiftui', __dir__)
    files = Dir.glob(File.join(lib, '**', '*.rb'))
    expect(files.size).to be > 40
    expect(files.flat_map { |f| hits.call(File.read(f), f.delete_prefix("#{lib}/")) }).to eq([])
  end
end
