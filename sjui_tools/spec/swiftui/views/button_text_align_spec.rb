# frozen_string_literal: true

require 'swiftui/views/button_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A Button's text is placed across it by textAlign alone, default centre (the
# SSoT's Button.textAlign, 4f ruling 2026-09-27); its gravity positions its
# content vertically only. StateAwareButtonView(textAlignment:) (SwiftJsonUI
# 10.29.0) places the label in the button's frame; the environment
# `.multilineTextAlignment` sjui already emitted aligns only the lines of a
# multi-line label, so until jsonui-cli 1.9.0 Left and Right stood in the
# middle (measured on the ConformanceHost, 200 and matchParent wide).
#
# The drawn arm is ButtonTextAlignProbeUITests in SwiftJsonUI's ConformanceHost.
RSpec.describe SjuiTools::SwiftUI::Views::ButtonConverter do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(extra)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter({ 'type' => 'Button', 'text' => 'Go', 'width' => 200, 'height' => 44 }.merge(extra), 0, nil, factory).convert.to_s
  end

  it 'textAlign Left and Right place the label at the start and the end' do
    expect(emit('textAlign' => 'Left')).to include('textAlignment: .leading')
    expect(emit('textAlign' => 'Right')).to include('textAlignment: .trailing')
    expect(emit('textAlign' => 'left')).to include('textAlignment: .leading')
  end

  it 'control: Center, none and a gravity pass nothing (the centre is the default)' do
    [{ 'textAlign' => 'Center' }, {}, { 'gravity' => 'left' }].each do |extra|
      expect(emit(extra)).not_to include('textAlignment:'), extra.inspect
    end
  end

  it 'type-checks the argument against the library signature', :swift_compile do
    stub = <<~SWIFT
      struct StateAwareButtonView: View {
          init(text: String, action: @escaping () -> Void, isEnabled: Bool = true, width: CGFloat? = nil, height: CGFloat? = nil,
               image: String? = nil, imageTint: Color? = nil, textAlignment: HorizontalAlignment = .center) {}
          var body: some View { EmptyView() }
      }
    SWIFT
    codes = [emit('textAlign' => 'Left'), emit('textAlign' => 'Right')]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", stubs: stub)).to compile_as_swift
  end
end
