# frozen_string_literal: true

require 'swiftui/views/progress_converter'
require_relative '../../support/emitted_swift'

# `style` on a Progress is the style file's name (common.style), not a shape:
# Progress declares none, and a determinate ProgressView is a bar. sjui read
# the key as the shape, so a Progress naming any style file but `linear` was
# drawn as a spinner (CircularProgressViewStyle) — kjui and rjui drew a bar.
RSpec.describe 'sjui: a Progress with a style file stays a bar' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  it 'sets no progressViewStyle, whatever the style is called' do
    %w[bar_primary circular linear].each do |style|
      code = SjuiTools::SwiftUI::Views::ProgressConverter.new('type' => 'Progress', 'progress' => 0.4, 'style' => style).convert
      expect(code).to include('ProgressView(value:'), style
      expect(code).not_to include('progressViewStyle'), style
    end
  end

  it 'compiles as it is emitted' do
    code = SjuiTools::SwiftUI::Views::ProgressConverter.new('type' => 'Progress', 'id' => 'p', 'progress' => 0.4, 'style' => 'bar_primary').convert
    body = code.to_s.lines.map { |l| "        #{l}" }.join
    swift = "struct EmittedHost: View {\n    @State var pValue: Double = 0.4\n    var body: some View {\n#{body}\n    }\n}\n"
    expect(swift).to compile_as_swift.with_imports('SwiftUI')
  end
end
