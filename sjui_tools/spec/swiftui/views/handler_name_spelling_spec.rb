# frozen_string_literal: true

require 'spec_helper'
require 'swiftui/views/button_converter'
require 'json'
require 'tmpdir'
require 'stringio'
require 'swiftui/json_to_swiftui_converter'

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

  # The lowercase onclick, on the build path (LayoutValidator.drop_bound_onclick!).
  def built(attr, value)
    Dir.mktmpdir('sjui_onclick') do |dir|
      path = File.join(dir, 'probe.json')
      File.write(path, JSON.generate('type' => 'View', 'id' => 'root', 'child' => [
                                       { 'data' => [{ 'name' => 'handleTap', 'class' => '(() -> Void)?' }] },
                                       { 'type' => 'Button', 'id' => 'b', 'text' => 'x', attr => value }
                                     ]))
      err = StringIO.new
      orig = $stderr
      $stderr = err
      begin
        swift = Array(SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path)).join("\n")
      ensure
        $stderr = orig
      end
      [swift, err.string]
    end
  end

  it 'lowercase onclick with the binding form is not a call, and says so once' do
    swift, err = built('onclick', '@{handleTap}')
    expect(swift).not_to include('handleTap')
    expect(err.scan("'onclick' takes a bare handler name, not a binding (@{handleTap}); write a binding as onClick. Ignored.").size).to eq(1)
  end

  it 'lowercase onclick with a bare name and onClick with a binding still call' do
    expect(built('onclick', 'handleTap').first).to include('data.handleTap?()')
    swift, err = built('onClick', '@{handleTap}')
    expect(swift).to include('data.handleTap?()')
    expect(err).not_to include("'onclick' takes")
  end
end
