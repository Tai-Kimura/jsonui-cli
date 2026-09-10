# frozen_string_literal: true

require 'spec_helper'
require 'compose/components/button_component'

# Handler NAME references — canon: shared/core/binding_semantics.json
# → contexts.nameRef. The Compose half of the pin measured on 2026-09-10; see
# rjui_tools/spec/react/converters/handler_name_spelling_spec.rb for the
# history. camelCase event attributes take the binding form only.
RSpec.describe 'handler name spelling (compose)' do
  def on_click_line(value)
    imports = Set.new
    code = KjuiTools::Compose::Components::ButtonComponent.generate(
      { 'type' => 'Button', 'id' => 'b', 'text' => 'x', 'onClick' => value }, 0, imports
    )
    code.lines.grep(/onClick/).first.to_s
  end

  it 'onClick with the binding form invokes the named handler' do
    expect(on_click_line('@{handleTap}')).to include('data.handleTap?.invoke()')
  end

  it 'onClick with a bare name is not an invocation' do
    line = on_click_line('handleTap')
    expect(line).not_to include('invoke()')
    expect(line).to include('ERROR')
  end
end
