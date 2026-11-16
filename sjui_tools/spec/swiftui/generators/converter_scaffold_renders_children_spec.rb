# frozen_string_literal: true

require 'swiftui/generators/converter_generator'
require 'swiftui/views/base_view_converter'
require 'swiftui/views/responsive_helper'
require 'swiftui/converter_factory'
require 'swiftui/generators/swift_component_generator'

# A converter scaffolded by `jui g converter` renders its container's children.
#
# From 1.8.107 through 1.8.111 it rendered none: the scaffold's `initialize`
# stored the factory as `@factory` / `@registry`, and `process_children` went
# through BaseViewConverter#render_child_honoring_visibility, which read
# `@converter_factory` and returned nil when it was absent. The block came
# out `{\n}`, the build reported 0 warnings, and a custom container's content
# was missing on iOS only. Reported 2026-09-24
# (sjui-converter-scaffold-container-drops-children).
#
# The specs that existed read the TEMPLATE AS TEXT, so a template whose
# generated code does nothing was green. These evaluate the generated class
# and convert a component with it — the only way to see what a scaffold does.
RSpec.describe 'a scaffolded container converter' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  before do
    allow(SjuiTools::Core::Logger).to receive(:info)
    allow(SjuiTools::Core::Logger).to receive(:debug)
    allow(SjuiTools::Core::Logger).to receive(:warn)
    allow(SjuiTools::Core::Logger).to receive(:success)
  end

  let(:factory) { SjuiTools::SwiftUI::ConverterFactory.new }

  # Evaluates the scaffold's source as it would be written, minus the two
  # require_relative lines (the file is not on disk here; both are loaded
  # above). A fresh class name per example keeps the definitions apart.
  def scaffold_class(name, **options)
    source = SjuiTools::SwiftUI::Generators::ConverterGenerator.new(name, **options)
                                                               .send(:converter_template)
    source = source.gsub(/^\s*require_relative .*$/, '')
    eval(source, TOPLEVEL_BINDING, "#{name}_converter.rb") # rubocop:disable Security/Eval
    SjuiTools::SwiftUI::Views::Extensions.const_get("#{name}Converter")
  end

  def component(type)
    { 'type' => type, 'id' => 'probe',
      'child' => [
        { 'type' => 'Label', 'id' => 'first', 'text' => 'First' },
        { 'type' => 'Label', 'id' => 'second', 'text' => 'Second', 'visibility' => '@{secondVisible}' }
      ] }
  end

  it 'renders every child, honoring visibility' do
    klass = scaffold_class('ScaffoldProbeA', is_container: true)
    code = klass.new(component('ScaffoldProbeA'), 0, nil, factory, nil).convert
    expect(code).to include('"First"')
    expect(code).to include('"Second"')
    expect(code).to include('VisibilityWrapper(data.secondVisible)')
    expect(code).not_to match(/ScaffoldProbeA \{\n\s*\}/)
  end

  it 'sets the names the base converter reads' do
    klass = scaffold_class('ScaffoldProbeB', is_container: true)
    converter = klass.new(component('ScaffoldProbeB'), 0, nil, factory, nil)
    expect(converter.instance_variable_get(:@converter_factory)).to be(factory)
  end

  # The converters already written by 1.8.107–1.8.111 set only the scaffold's
  # names, and `jui sync_tool` never rewrites views/extensions/. The base
  # converter reads those names too, so the next sync fixes them in place.
  it 'still renders the children of a scaffold that set only @factory / @registry' do
    klass = scaffold_class('ScaffoldProbeC', is_container: true)
    converter = klass.new(component('ScaffoldProbeC'), 0, nil, factory, nil)
    converter.instance_variable_set(:@converter_factory, nil)
    converter.instance_variable_set(:@view_registry, nil)
    code = converter.convert
    expect(code).to include('"First"')
    expect(code).to include('VisibilityWrapper(data.secondVisible)')
  end

  # The text above says the children are there; a compiler says the call
  # site is Swift that builds. The container is the Swift component the same
  # `g converter` run scaffolds (its own output, minus the header and the
  # preview), and VisibilityWrapper is mirrored from the library
  # (SwiftJsonUI Classes/SwiftUI/VisibilityWrapper.swift: both initializers).
  it 'emits Swift that compiles against the scaffolded component and the library wrapper' do
    klass = scaffold_class('ScaffoldProbeE', is_container: true)
    code = klass.new(component('ScaffoldProbeE'), 0, nil, factory, nil).convert
    swift_component = SjuiTools::SwiftUI::Generators::SwiftComponentGenerator
                      .new('ScaffoldProbeE', is_container: true, command: 'spec')
                      .send(:swift_template)
                      .sub(/\A(\/\/.*\n)+/, '')
                      .sub(/^import SwiftUI\n/, '')
                      .sub(/^#if DEBUG.*?#endif\n?/m, '')
    wrapper = <<~SWIFT
      enum Visibility: String {
          case visible, invisible, gone
          init(from string: String?) { self = Visibility(rawValue: string ?? "") ?? .visible }
      }
      struct VisibilityWrapper<Content: View>: View {
          let content: Content
          init(_ visibility: Visibility = .visible, @ViewBuilder content: () -> Content) { self.content = content() }
          init(_ visibilityString: String?, @ViewBuilder content: () -> Content) { self.content = content() }
          var body: some View { content }
      }
    SWIFT
    expect(compilable_view(code, data: ['var secondVisible: String? = "visible"'],
                                 stubs: swift_component + wrapper)).to compile_as_swift
  end

  it 'renders nothing, rather than raising, when no factory was handed in at all' do
    klass = scaffold_class('ScaffoldProbeD', is_container: true)
    code = klass.new(component('ScaffoldProbeD'), 0, nil, nil, nil).convert
    expect(code).not_to include('"First"')
  end
end
