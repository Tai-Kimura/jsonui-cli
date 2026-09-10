# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/react_generator'

# Handler NAME references — canon: shared/core/binding_semantics.json
# → contexts.nameRef.
#
# Until 2026-09-10 the canon said `'@{name}'` and the bare name were
# equivalent spellings. Measured on all three code generators that day: they
# are not, and the three agree with each other. The camelCase event
# attributes (`onClick`, …) take the binding form only; the lowercase
# `onclick` — the UIKit selector legacy — takes the bare name only. The
# canon now says what the generators do, and this file is the web half of
# the pin (kjui_tools and sjui_tools carry the same four arms).
RSpec.describe 'handler name spelling (web)' do
  let(:generator) { RjuiTools::React::ReactGenerator.new({ 'typescript' => true }) }

  def button_line(attr, value)
    layout = { 'type' => 'View', 'id' => 'root_view',
               'child' => [{ 'type' => 'Button', 'id' => 'b', 'text' => 'x', attr => value }] }
    generator.generate('Home', layout, screen_id: 'home').lines.grep(/<button/).first.to_s
  end

  it 'onClick with the binding form calls the named handler' do
    expect(button_line('onClick', '@{handleTap}')).to include('onClick={data.handleTap}')
  end

  it 'onClick with a bare name is not a call' do
    line = button_line('onClick', 'handleTap')
    expect(line).not_to include('onClick={')
    expect(line).to include('ERROR: onClick requires binding format')
  end

  it 'lowercase onclick with a bare name calls the named handler (selector legacy)' do
    expect(button_line('onclick', 'handleTap')).to include('onClick={data.handleTap}')
  end

  it 'lowercase onclick with the binding form is not a call' do
    line = button_line('onclick', '@{handleTap}')
    expect(line).not_to include('onClick={')
    expect(line).to include('ERROR: onclick requires selector format')
  end
end
