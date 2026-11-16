# frozen_string_literal: true

require_relative '../../lib/core/binding_validator'

# binding-bare-event (shared/core/binding_validator_core.rb): a bare name
# given to an event attribute the SSoT declares binding-only (type
# "binding", no "string") is reported; it was dropped by the generators with
# no report (ticket bare-event-handler-is-dropped-without-a-warning). An
# attribute declared with "string" takes a bare name as a declared form, an
# app's own component uses camelCase keys as props, and a non-event key that
# begins with "on" is not an event: none of those is reported.
RSpec.describe RjuiTools::Core::BindingValidator do
  def bare_event_warnings(node)
    layout = { 'type' => 'View', 'id' => 'root', 'child' => [
      { 'data' => [{ 'name' => 'h', 'class' => 'Function' }, { 'name' => 'rows', 'class' => 'CollectionDataSource' }] }, node
    ] }
    described_class.new.validate(layout, 'probe.json').grep(/binding-bare-event/)
  end

  it 'reports a bare name on a binding-only event, on a declared type and through an alias' do
    { { 'type' => 'Button', 'id' => 'b', 'text' => 'x', 'onClick' => 'h' } => "'Button.onClick'",
      { 'type' => 'Switch', 'id' => 's', 'onValueChange' => 'h' } => "'Switch.onValueChange'",
      { 'type' => 'Slider', 'id' => 'sl', 'value' => '@{v}', 'onValueChange' => 'h' } => "'Slider.onValueChange'",
      { 'type' => 'SelectBox', 'id' => 'sb', 'items' => %w[a], 'onValueChanged' => 'h' } => "'SelectBox.onValueChanged'" }.each do |node, named|
      warnings = bare_event_warnings(node)
      expect(warnings.size).to eq(1), "#{named}: #{warnings.inspect}"
      expect(warnings.first).to include(named, "write '@{h}'")
    end
  end

  it 'control: the binding form, a string-declared event, an app component, a colour and an alias of a non-event are not reported' do
    [{ 'type' => 'Button', 'id' => 'b', 'text' => 'x', 'onClick' => '@{h}' },
     { 'type' => 'Collection', 'id' => 'c', 'items' => '@{rows}', 'onPageChanged' => 'h' },
     { 'type' => 'View', 'id' => 'v', 'onAppear' => 'h' },
     { 'type' => 'TextField', 'id' => 't', 'onSubmit' => 'h', 'onTextChange' => 'h', 'onShouldReturn' => 'h' },
     { 'type' => 'MyCard', 'id' => 'm', 'onClick' => 'h' },
     { 'type' => 'Switch', 'id' => 's', 'onTintColor' => 'red' },
     { 'type' => 'CheckBox', 'id' => 'k', 'onSrc' => 'icon_on' }].each do |node|
      expect(bare_event_warnings(node)).to eq([]), node.inspect
    end
  end
end
