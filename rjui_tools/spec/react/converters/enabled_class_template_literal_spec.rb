# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
Dir[File.expand_path('../../../lib/react/converters/*_converter.rb', __dir__)].sort.each { |f| require f }

# A bound `enabled` adds `${!data.enabled ? 'opacity-50 cursor-not-allowed' : ''}`
# to a component's class string; written as className="..." it reached the
# page as its own text and the disabled look never came (ticket
# rjui-checkbox-enabled-class-not-template-literal: CheckBox, Switch, Radio and
# Slider). A class string holding `${` is a template literal, everywhere.
RSpec.describe 'a class string holding ${ is a template literal' do
  let(:config) { { 'use_tailwind' => true } }
  converters = RjuiTools::React::Converters

  {
    'CheckBox' => converters::ToggleConverter, 'Switch' => converters::SwitchConverter,
    'Radio' => converters::RadioConverter, 'Slider' => converters::SliderConverter
  }.each do |type, klass|
    [{}, { 'label' => 'x', 'text' => 'x' }].each do |extra|
      it "#{type}#{extra.empty? ? '' : ' with a label'}: the disabled look is evaluated" do
        out = klass.new({ 'type' => type, 'enabled' => '@{enabled}' }.merge(extra), config).convert
        expect(out).to include("${!data.enabled ? 'opacity-50 cursor-not-allowed' : ''}")
        expect(out).to match(/className=\{`[^`]*\$\{!data\.enabled \? 'opacity-50 cursor-not-allowed' : ''\}[^`]*`\}/)
        expect(out).not_to match(/className="[^"]*\$\{/)
      end
    end
  end

  it 'the four, with and without a label, compile as TypeScript' do
    emits = {
      'CheckBox' => converters::ToggleConverter, 'Switch' => converters::SwitchConverter,
      'Radio' => converters::RadioConverter, 'Slider' => converters::SliderConverter
    }.flat_map do |type, klass|
      [{}, { 'label' => 'x', 'text' => 'x' }].map do |extra|
        klass.new({ 'type' => type, 'enabled' => '@{enabled}' }.merge(extra), config.merge('typescript' => true)).convert
      end
    end
    expect(TypeScriptCompiler.component(*emits)).to compile_as_typescript.with_ambient(<<~TS)
      declare const data: { enabled: boolean };
    TS
  end

  # The family: every converter, with each attribute a converter may turn into a class expression bound.
  it 'no converter writes a plain className holding ${' do
    plain = []
    converters.constants.map { |c| converters.const_get(c) }
              .select { |c| c.is_a?(Class) && c.name.end_with?('Converter') && c.instance_methods.include?(:convert) }
              .each do |klass|
      type = klass.name.split('::').last.sub(/Converter\z/, '')
      %w[enabled hidden visibility background fontColor cornerRadius alpha].each do |name|
        [{}, { 'label' => 'x', 'text' => 'x' }].each do |extra|
          out = begin
            klass.new({ 'type' => type, name => "@{#{name}}" }.merge(extra), config).convert
          rescue StandardError, NotImplementedError   # an abstract converter, or a shape it refuses
            next
          end
          out.to_s.scan(/className="[^"]*\$\{[^"]*"/).each { |m| plain << "#{type} #{name}: #{m[0, 80]}" }
        end
      end
    end
    expect(plain).to eq([])
  end
end
