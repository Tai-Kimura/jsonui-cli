# frozen_string_literal: true

require 'json'
require 'swiftui/converter_factory'
require_relative '../support/emitted_swift'

# `bind` is folded into the attribute it stands for on the node a built-in
# converter draws — its style merged (StyleLoader, before conversion) — at
# ConverterFactory#create_converter, after the app's own converters were asked
# (JsonUIShared::BindFold). No converter reads `bind` itself. The layout
# normalizer leaves a node with a style or responsive overrides for this fold.
#
# What is measured is the node create_converter hands the converter (its
# @component): what each converter then draws from its own value attribute is
# its own specs'.
RSpec.describe 'sjui: bind folded at the dispatch' do
  include EmittedSwift
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  handed = lambda do |node|
    converter = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(JSON.parse(JSON.generate(node)))
    converter.instance_variable_get(:@component)
  end
  vectors = File.expand_path('../../../shared/core/bind_fold_vectors.json', __dir__)

  it 'hands each style case to its converter as the table draws it (the style merged, then folded)' do
    skip 'shared vectors not present in this layout' unless File.exist?(vectors)

    cases = JSON.parse(File.read(vectors))['style_cases']
    expect(cases.size).to be >= 2
    cases.each do |c|
      merged = c['styles'].fetch(c['node']['style']).merge(c['node']).reject { |k, _| k == 'style' }
      expect(handed.call(merged)).to eq(c['drawn']), c['name']
    end
  end

  it 'hands every case of the table to its converter folded' do
    skip 'shared vectors not present in this layout' unless File.exist?(vectors)

    cases = JSON.parse(File.read(vectors))['cases']
    expect(cases.size).to be >= 18
    got = cases.map { |c| [c['name'], handed.call(c['node'])] }
    expect(got).to eq(cases.map { |c| [c['name'], c['expect']] })
  end

  # The folded node reaches the Swift a compiler reads: a lone bind on a
  # Progress is its value (a one-way read, so the fragment compiles against a
  # plain data struct); `bind` itself names nothing in the Swift.
  it 'draws a lone bind as the value it folds to, in Swift that compiles' do
    code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter({ 'type' => 'Progress', 'id' => 'p', 'bind' => '@{level}' }).convert
    expect(code).to include('ProgressView(value: data.level)')
    expect(compilable_view(code, data: ['var level: Double = 0.5'])).to compile_as_swift
  end

  # An app's converter (the registry's CONVERTER_MAPPINGS) gets its node as
  # written; one that cannot load falls through to the built-in, which draws
  # it folded.
  it 'hands an app converter its node as written' do
    probe = Class.new do
      attr_reader :component

      def initialize(component, *_rest)
        @component = component
      end
    end
    stub_const('SjuiTools::SwiftUI::Views::Extensions::ProbeSwitchConverter', probe)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.instance_variable_set(:@custom_converters, { 'Switch' => 'ProbeSwitchConverter' })
    allow(factory).to receive(:require_relative).and_return(true)
    expect(factory.create_converter({ 'type' => 'Switch', 'bind' => '@{b}' }).component)
      .to eq('type' => 'Switch', 'bind' => '@{b}')

    unloadable = SjuiTools::SwiftUI::ConverterFactory.new
    unloadable.instance_variable_set(:@custom_converters, { 'Switch' => 'NoSuchConverter' })
    expect(unloadable.create_converter({ 'type' => 'Switch', 'bind' => '@{b}' }).instance_variable_get(:@component))
      .to eq('type' => 'Switch', 'isOn' => '@{b}')
  end

  # No converter reads `bind`. Code only — a comment naming it does not count.
  it 'is read by no converter' do
    token = /\['bind'\]|\["bind"\]/
    hits = lambda do |text, name|
      # map + compact, not filter_map: Ruby 2.6 (the consumer floor and a
      # CI leg until jsonui-cli 1.9.0; 3.2 since) has no filter_map
      text.lines.each_with_index.map do |line, i|
        next if line.strip.start_with?('#')

        "#{name}:#{i + 1}" if line.sub(/#.*/, '') =~ token
      end.compact
    end
    expect(hits.call("          if @component['bind'] && x\n", 'read').size).to eq(1)
    expect(hits.call("          # @component['bind'] was read here\n", 'comment').size).to eq(0)

    lib = File.expand_path('../../lib/swiftui', __dir__)
    files = Dir.glob(File.join(lib, '**', '*.rb'))
    expect(files.size).to be > 40
    expect(files.flat_map { |f| hits.call(File.read(f), f.delete_prefix("#{lib}/")) }).to eq([])
  end
end
