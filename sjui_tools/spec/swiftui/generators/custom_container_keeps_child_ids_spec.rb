# frozen_string_literal: true

require 'swiftui/generators/converter_generator'
require 'swiftui/views/base_view_converter'
require 'swiftui/views/responsive_helper'
require 'swiftui/converter_factory'
require 'swiftui/generators/swift_component_generator'

# A project's own container (a converter `sjui g converter` scaffolds) with an
# id keeps its children's identifiers: it is made an explicit accessibility
# container before its own identifier, as the built-in containers are.
#
# Until 1.8.121 only the built-in types were (ACCESSIBILITY_CONTAINER_TYPES),
# so a custom container's id went on bare and SwiftUI pushed it down onto its
# children — measured in the codegen host (XCUITest, iOS 26.5, 2026-09-25):
# with one child, the container's id found on the child and the child's own
# 0 times; with two, the container's id twice. Ticket
# sjui-custom-container-takes-its-childrens-identifiers; the measurement is
# SwiftJsonUI ConformanceHost's CustomContainerIdUITests.
RSpec.describe 'a scaffolded custom container and its children\'s identifiers' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  before do
    %i[info debug warn success].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
  end

  let(:factory) { SjuiTools::SwiftUI::ConverterFactory.new }

  def scaffold_class(name, **options)
    source = SjuiTools::SwiftUI::Generators::ConverterGenerator.new(name, **options).send(:converter_template)
    eval(source.gsub(/^\s*require_relative .*$/, ''), TOPLEVEL_BINDING, "#{name}_converter.rb") # rubocop:disable Security/Eval
    SjuiTools::SwiftUI::Views::Extensions.const_get("#{name}Converter")
  end

  def kid(id)
    { 'type' => 'Label', 'id' => id, 'text' => id }
  end

  # The lines after the component's closing brace: its own modifiers.
  def own_modifiers(code)
    code.lines.drop_while { |l| l !~ /^\}/ }.map(&:strip)
  end

  it 'makes a custom container with children a container before its identifier' do
    klass = scaffold_class('KeepIdsA')
    code = klass.new({ 'type' => 'KeepIdsA', 'id' => 'box', 'child' => [kid('a'), kid('b')] }, 0, nil, factory, nil).convert
    mods = own_modifiers(code)
    contain = mods.index('.accessibilityElement(children: .contain)')
    id = mods.index('.accessibilityIdentifier("box")')
    expect(contain).not_to be_nil, code
    expect(id).to be > contain
  end

  it 'anchors a single child against the merge, as the built-in containers do' do
    klass = scaffold_class('KeepIdsB', is_container: true)
    code = klass.new({ 'type' => 'KeepIdsB', 'id' => 'box', 'child' => [kid('only')] }, 0, nil, factory, nil).convert
    expect(own_modifiers(code)).to include('.accessibilityElement(children: .ignore)', '.accessibilityElement(children: .contain)')
  end

  it 'leaves a custom component with no children as it was: its identifier alone' do
    klass = scaffold_class('KeepIdsC')
    code = klass.new({ 'type' => 'KeepIdsC', 'id' => 'box' }, 0, nil, factory, nil).convert
    expect(code).not_to include('.accessibilityElement(')
    expect(code).to include('.accessibilityIdentifier("box")')
  end

  it 'is the extension converters only — a built-in leaf with the same shape is unchanged' do
    label = SjuiTools::SwiftUI::Views::LabelConverter.new({ 'type' => 'Label', 'id' => 'l', 'text' => 'x' }, 0, nil)
    expect(label.send(:custom_container?)).to be(false)
  end

  # What the call site compiles to, with the component the same run scaffolds.
  it 'emits Swift that compiles against the scaffolded component' do
    klass = scaffold_class('KeepIdsE', is_container: true)
    code = klass.new({ 'type' => 'KeepIdsE', 'id' => 'box', 'child' => [kid('a'), kid('b')] }, 0, nil, factory, nil).convert
    component = SjuiTools::SwiftUI::Generators::SwiftComponentGenerator
                .new('KeepIdsE', is_container: true, command: 'spec')
                .send(:swift_template)
                .sub(/\A(\/\/.*\n)+/, '').sub(/^import SwiftUI\n/, '').sub(/^#if DEBUG.*?#endif\n?/m, '')
    expect(compilable_view(code, stubs: component)).to compile_as_swift
  end
end
