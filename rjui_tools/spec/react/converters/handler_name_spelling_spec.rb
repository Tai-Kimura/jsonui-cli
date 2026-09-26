# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
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

  def screen(attr, value)
    layout = { 'type' => 'View', 'id' => 'root_view',
               'child' => [{ 'type' => 'Button', 'id' => 'b', 'text' => 'x', attr => value }] }
    generator.generate('Home', layout, screen_id: 'home')
  end

  def button_line(attr, value)
    screen(attr, value).lines.grep(/<button/).first.to_s
  end

  it 'onClick with the binding form calls the named handler' do
    expect(button_line('onClick', '@{handleTap}')).to include('onClick={() => data.handleTap?.()}')
  end

  it 'onClick with a bare name is not a call' do
    line = button_line('onClick', 'handleTap')
    expect(line).not_to include('onClick={')
    expect(line).to include('ERROR: onClick requires binding format')
  end

  it 'lowercase onclick with a bare name calls the named handler (selector legacy)' do
    expect(button_line('onclick', 'handleTap')).to include('onClick={() => data.handleTap?.()}')
  end

  it 'lowercase onclick with the binding form is not a call' do
    line = button_line('onclick', '@{handleTap}')
    expect(line).not_to include('onClick={')
    expect(line).to include('ERROR: onclick requires selector format')
  end

  # The whole generated file, imports cut, under --strict — each spelling,
  # the calls and the refusals: a refusal is written as a comment where the
  # handler would go, and the file around it still has to compile. The
  # imports are declared as the build writes them (screenMarker.ts,
  # StringManager.ts) and HomeData as the data model declares a handler.
  it 'writes a file that compiles for every spelling', :typescript_compile do
    [['onClick', '@{handleTap}'], ['onClick', 'handleTap'], ['onclick', 'handleTap'], ['onclick', '@{handleTap}']]
      .each do |attr, value|
        body = screen(attr, value).lines.reject { |l| l.start_with?('import ') }.join
        expect(body).to compile_as_typescript.with_ambient(<<~TS), "#{attr}: #{value}"
          interface HomeData { handleTap?: () => void }
          declare function createHomeData(): HomeData;
          declare function useStringManager(): Record<string, string>;
          declare function screenMarker(screenId: string): Record<string, string>;
        TS
      end
  end
end
