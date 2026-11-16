# frozen_string_literal: true

require 'swiftui/views/textview_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A TextView's `padding` is its container inset, as SwiftJsonUI Dynamic
# reads it (TextViewConverter → DynamicHelpers.getPadding). codegen read
# only containerInset / edgeInset / paddings and applied no outer padding,
# so `padding: 8` was dropped: the text sat at the editor's default inset
# while Dynamic inset it by 8 (ticket ios-a-textviews-id-box-shrinks-by-its-
# container-inset).
RSpec.describe 'sjui codegen: a TextView reads `padding` as its container inset' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(attrs)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    node = { 'type' => 'TextView', 'id' => 't', 'hint' => 'Text', 'width' => 100, 'height' => 40 }.merge(attrs)
    factory.create_converter(node, 1, nil, factory).convert.to_s
  end

  TEXTVIEW_PADDING_INSET = 'containerInset: EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8)'

  it 'padding 8: the inset, and no outer padding' do
    code = emit('padding' => 8)
    expect(code).to include(TEXTVIEW_PADDING_INSET)
    expect(code).not_to include('.padding(')
  end

  it 'paddings wins over padding (control: the existing order)' do
    expect(emit('padding' => 8, 'paddings' => [2])).to include('containerInset: EdgeInsets(top: 2, leading: 2, bottom: 2, trailing: 2)')
  end

  it 'no padding: no inset argument (control: the default)' do
    expect(emit({})).not_to include('containerInset:')
  end

  # TextViewWithPlaceholder's init, transcribed for the arguments the
  # converter writes here — a transcription, not a compile against it.
  it 'compiles as emitted' do
    code = emit('padding' => 8)
    swift = <<~SWIFT
      import SwiftUI
      struct TextViewWithPlaceholder: View {
          init(text: Binding<String>, hint: String? = nil,
               containerInset: EdgeInsets = EdgeInsets(top: 8, leading: 5, bottom: 8, trailing: 5),
               isFocused: Binding<Bool>? = nil, accessibilityIdentifier: String? = nil) {}
          var body: some View { EmptyView() }
      }
      struct TextViewHostData { var tIsFocused = false }
      struct TextViewHost: View {
          @State var tText = ""
          @State var data = TextViewHostData()
          var body: some View {
      #{code}
          }
      }
    SWIFT
    expect(swift).to compile_as_swift
  end
end
