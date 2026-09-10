# frozen_string_literal: true

require 'spec_helper'
require 'swiftui/views/button_converter'

# Handler NAME references — canon: shared/core/binding_semantics.json
# → contexts.nameRef. The SwiftUI half of the pin measured on 2026-09-10; see
# rjui_tools/spec/react/converters/handler_name_spelling_spec.rb for the
# history. camelCase event attributes take the binding form only; a bare
# name is never promoted to a call.
RSpec.describe 'handler name spelling (swiftui)' do
  def button_code(value)
    code = SjuiTools::SwiftUI::Views::ButtonConverter.new(
      { 'type' => 'Button', 'id' => 'b', 'text' => 'x', 'onClick' => value }
    ).convert
    code.is_a?(Array) ? code.join("\n") : code
  end

  it 'onClick with the binding form calls the named handler' do
    expect(button_code('@{handleTap}')).to include('data.handleTap?()')
  end

  it 'onClick with a bare name is not a call' do
    expect(button_code('handleTap')).not_to include('handleTap')
  end
end
