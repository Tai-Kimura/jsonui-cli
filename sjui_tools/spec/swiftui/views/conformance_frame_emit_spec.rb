# frozen_string_literal: true

require 'swiftui/converter_factory'
require 'core/config_manager'

# `.jsonUIConformanceFrame(id)` is for the conformance host only.
#
# It hands a view's layout box up to the host's `frame:<id>` measuring
# element, which the frames gate reads. An app has no use for it, and a line
# per id in every app's generated code would be a diff in every consumer and
# would not compile against a SwiftJsonUI without jsonUIConformanceFrame. So
# it is emitted only when the sjui config says `"conformance_frames": true`,
# which only the host's codegen (ConformanceHost/scripts/
# generate_codegen_host.rb) writes.
RSpec.describe 'conformance frame emit' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all)  { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(component)
    out = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert
    out.is_a?(Array) ? out.join("\n") : out.to_s
  end

  def with_config(config)
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
  end

  def line_of(code, needle)
    code.each_line.find_index { |l| l.include?(needle) }
  end

  # A View (apply_common_decorations), a Label and a TextField (its own
  # chain), each with a margin so the slot can be checked against it.
  let(:shapes) do
    {
      'View' => { 'type' => 'View', 'id' => 'target', 'width' => 200, 'height' => 200, 'topMargin' => 10 },
      'Label' => { 'type' => 'Label', 'id' => 'target', 'text' => 'Sample', 'topMargin' => 10 },
      'TextField' => { 'type' => 'TextField', 'id' => 'target', 'width' => 200, 'topMargin' => 10 }
    }
  end

  it 'emits nothing without the flag, as an app builds' do
    with_config({})
    shapes.each do |type, component|
      expect(emit(component)).not_to include('jsonUIConformanceFrame'), type
    end
  end

  it 'emits nothing when the flag is anything but true' do
    with_config({ 'conformance_frames' => 'true' })
    expect(emit(shapes['View'])).not_to include('jsonUIConformanceFrame')
  end

  it 'emits it with the flag, inside the margins: before the margin padding' do
    with_config({ 'conformance_frames' => true })
    shapes.each do |type, component|
      code = emit(component)
      frame = line_of(code, '.jsonUIConformanceFrame("target")')
      margin = line_of(code, '.padding(.top, 10)')
      expect(frame).not_to be_nil, "#{type}: no measuring modifier:\n#{code}"
      expect(margin).not_to be_nil, "#{type}: no top margin:\n#{code}"
      expect(frame).to be < margin, "#{type}: the measuring modifier is outside the margin:\n#{code}"
    end
  end

  # Inside the offset as well: `.offset` moves the drawing, not the layout
  # bounds, so a modifier after it reported an offsetY 8 view at y = 0
  # (ConformanceHost, 2026-10-05) where Android's testTag and web read 8.
  it 'emits it inside the offset' do
    with_config({ 'conformance_frames' => true })
    code = emit(shapes['View'].merge('offsetY' => 8))
    frame = line_of(code, '.jsonUIConformanceFrame("target")')
    offset = line_of(code, '.offset(')
    expect(offset).not_to be_nil, "no offset:\n#{code}"
    expect(frame).to be < offset, "the measuring modifier is outside the offset:\n#{code}"
  end

  # The stub is the library's signature (SwiftJsonUI
  # JsonUIConformanceFrame.swift), so an emit that passed it anything else
  # would not type-check here either.
  it 'type-checks with the flag', :swift_compile do
    with_config({ 'conformance_frames' => true })
    view = %w[View Label].map { |type| emit(shapes[type]) }.join("\n")
    stub = 'extension View { func jsonUIConformanceFrame(_ id: String?) -> some View { self } }'
    expect(compilable_view("VStack {\n#{view}\n}", stubs: stub)).to compile_as_swift
  end

  it 'skips an id that is not drawn, with the flag' do
    with_config({ 'conformance_frames' => true })
    hidden = shapes['View'].merge('visibility' => 'invisible')
    expect(emit(hidden)).not_to include('jsonUIConformanceFrame')
  end
end
