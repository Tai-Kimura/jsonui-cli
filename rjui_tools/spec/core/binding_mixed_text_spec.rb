# frozen_string_literal: true

require 'core/binding_validator'

# binding-mixed-text (warning; ruling 2026-10-02): a value that holds a binding
# and is not one binding. Composing a string is logic, and a layout holds
# none; and a string composed in the layout cannot be localized as one text —
# the ViewModel composes it and the layout binds it as one value. Until
# jsonui-cli 1.9.6 the SSoT declared it as text interpolation and nothing said
# a word. The rule's own cases are the shared vectors (binding_vectors.json,
# expectWarning); these arms are its boundary.
#
# Only an attribute the SSoT declares for the component: an extension
# component's own attribute is read as that component reads it. JsonUIDocument's
# CodeBlock shows code, `@{greeting}` and all, verbatim — its declaration says
# "Rendered verbatim; no interpolation is performed" — and its 31 such values
# (docs/screens/layouts, measured 2026-10-02) are not this rule's.
RSpec.describe 'binding-mixed-text (rjui)' do
  def messages(node)
    layout = { 'type' => 'View', 'id' => 'root',
               'data' => [{ 'name' => 'x', 'class' => 'String' }, { 'name' => 'id', 'class' => 'String' }],
               'child' => [node.merge('id' => 'target')] }
    RjuiTools::Core::BindingValidator.new.validate(layout, 'a.json').grep(/\[binding-mixed-text\]/)
  end

  it 'warns on literal text around a binding, naming both reasons' do
    found = messages('type' => 'Label', 'text' => 'Title: @{x}')
    expect(found.size).to eq(1)
    expect(found.first).to include('Compose the string in the ViewModel', 'localizable', 'a layout holds no logic')
  end

  it 'warns on a value position too (a url)' do
    expect(messages('type' => 'NetworkImage', 'src' => 'https://cdn/@{id}.png').size).to eq(1)
  end

  it 'says nothing for one binding, or for a literal' do
    expect(messages('type' => 'Label', 'text' => '@{x}')).to be_empty
    expect(messages('type' => 'Label', 'text' => 'Title')).to be_empty
  end

  it "says nothing for an attribute the SSoT does not declare for the component (CodeBlock's code)" do
    expect(messages('type' => 'CodeBlock', 'code' => '{ "type": "Label", "text": "@{greeting}" }')).to be_empty
  end
end
