# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require 'swiftui/views/selectbox_converter'
require 'swiftui/views/textview_converter'
require_relative '../../support/emitted_swift'

# A four-value `paddings` is [top, right, bottom, left] (the SSoT's
# common.paddings), as SwiftJsonUI Dynamic (edgeInsetsFromArray, getPadding)
# and both Compose paths read it. Until jsonui-cli 1.9.14, sjui read it as
# [top, left, bottom, right] in three places: spacing_helper (every view),
# SelectBox and TextView. Different left and right values were then padded
# the other way round from Dynamic (ticket
# sjui-four-value-paddings-read-as-top-left-bottom-right). The relative
# container already read it right.
#
# The drawn arm is PaddingsOrderProbeUITests in SwiftJsonUI's
# ConformanceHost. It measures where the child sits, which a width cannot
# tell.
RSpec.describe 'sjui: a four-value paddings is [top, right, bottom, left]' do
  include EmittedSwift

  def view(extra)
    SjuiTools::SwiftUI::Views::ViewConverter.new({ 'type' => 'View', 'child' => [] }.merge(extra)).convert.to_s
  end

  it 'a view: leading is the fourth value, trailing the second' do
    code = view('paddings' => [1, 30, 3, 4])
    expect(code).to include('.padding(.leading, 4)').and include('.padding(.trailing, 30)')
    expect(code).not_to include('.padding(.leading, 30)')
  end

  it 'equal sides emit what they did (the consumer faces\' four-value paddings)' do
    code = view('paddings' => [16, 8, 16, 8])
    expect(code.lines.map(&:strip).grep(/\A\.padding\(/))
      .to eq(['.padding(.top, 16)', '.padding(.leading, 8)', '.padding(.bottom, 16)', '.padding(.trailing, 8)'])
  end

  it 'a SelectBox' do
    code = SjuiTools::SwiftUI::Views::SelectBoxConverter.new({ 'type' => 'SelectBox', 'paddings' => [1, 30, 3, 4] }).convert.to_s
    expect(code).to include('padding: EdgeInsets(top: 1, leading: 4, bottom: 3, trailing: 30)')
  end

  it 'a TextView\'s paddings; its containerInset keeps [top, left, bottom, right], as Dynamic reads it (control)' do
    tv = ->(extra) { SjuiTools::SwiftUI::Views::TextViewConverter.new({ 'type' => 'TextView' }.merge(extra)).convert.to_s }
    expect(tv.('paddings' => [1, 30, 3, 4])).to include('containerInset: EdgeInsets(top: 1, leading: 4, bottom: 3, trailing: 30)')
    expect(tv.('containerInset' => [1, 30, 3, 4])).to include('containerInset: EdgeInsets(top: 1, leading: 30, bottom: 3, trailing: 4)')
  end

  it 'the view\'s padding type-checks', :swift_compile do
    expect(compilable_view(view('paddings' => [1, 30, 3, 4]))).to compile_as_swift
  end
end
