# frozen_string_literal: true

require 'swiftui/views/button_converter'
require 'swiftui/views/label_converter'
require 'swiftui/views/textview_converter'
require 'swiftui/views/selectbox_converter'
require_relative '../../support/emitted_swift'

# opacity (alpha), shadow, clipToBounds, offsetX / offsetY and hidden are
# common attributes every node draws (BaseViewConverter#apply_common_decorations).
# The converters that assemble their own chain did not call it: a Button drew
# none of the five — `opacity: 0.4` on a Button was fully opaque — and a
# Label, a TextView and a SelectBox drew no shadow, no clip and no offset.
RSpec.describe 'sjui: the common decorations on the converters that build their own chain' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  DECORATIONS = {
    'opacity' => [0.4, '.opacity(0.4)'],
    'shadow' => ['#000000|2|2|4|0.3', '.shadow('],
    'clipToBounds' => [true, '.clipped()'],
    'offsetX' => [9, '.offset(x: 9, y: 0)'],
    'hidden' => [true, '.opacity(0).accessibilityHidden(true)']
  }.freeze

  {
    SjuiTools::SwiftUI::Views::ButtonConverter => { 'type' => 'Button', 'text' => 'b' },
    SjuiTools::SwiftUI::Views::LabelConverter => { 'type' => 'Label', 'text' => 'l' },
    SjuiTools::SwiftUI::Views::TextViewConverter => { 'type' => 'TextView', 'text' => 't' },
    SjuiTools::SwiftUI::Views::SelectBoxConverter => { 'type' => 'SelectBox', 'items' => %w[a] }
  }.each do |klass, node|
    DECORATIONS.each do |attr, (value, line)|
      it "#{node['type']}: #{attr} is drawn" do
        code = klass.new(node.merge(attr => value)).convert
        expect(code).to include(line)
        expect(klass.new(node).convert).not_to include(line)
      end
    end
  end

  it 'a Button with all five compiles as emitted' do
    stub = <<~SWIFT
      struct StateAwareButtonView: View {
          init(text: String, action: @escaping () -> Void, isEnabled: Bool = true) {}
          var body: some View { EmptyView() }
      }
    SWIFT
    node = { 'type' => 'Button', 'text' => 'b' }.merge(DECORATIONS.transform_values(&:first))
    code = SjuiTools::SwiftUI::Views::ButtonConverter.new(node).convert
    expect(compilable_view(code, stubs: stub)).to compile_as_swift
  end
end
