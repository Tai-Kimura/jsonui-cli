# frozen_string_literal: true

require 'set'
require 'compose/components/button_component'
require 'compose/components/textfield_component'
require_relative '../../support/kotlin_compiler'
require_relative '../../support/compose_stub_universe'

# A control the layout writes no cornerRadius on (the requester's ruling 2026-11-15, ticket
# jui-button-default-corner-radius-differs): a Button is square, as on iOS and the web, and its
# shadow is cast in the same square outline; a TextField / TextView's shadow follows
# CustomTextField's square default. Both were Configuration's 8. A declared cornerRadius is
# drawn as declared.
RSpec.describe 'kjui: the corner a control draws with no cornerRadius' do
  let(:button) { KjuiTools::Compose::Components::ButtonComponent }

  it 'draws a Button square, without reading a Configuration corner' do
    code = button.generate({ 'type' => 'Button', 'text' => 'Go' }, 0, Set.new)
    expect(code).to include('shape = RoundedCornerShape(0.dp)')
    expect(code).not_to include('defaultCornerRadius')
  end

  it "casts a Button's shadow in the same square outline" do
    code = button.generate({ 'type' => 'Button', 'text' => 'Go', 'shadow' => '#000000|0|2|0.3|4' }, 0, Set.new)
    expect(code).to include('.dropShadow(shape = RoundedCornerShape(0.dp), ')
  end

  it 'draws a declared cornerRadius as declared' do
    code = button.generate({ 'type' => 'Button', 'text' => 'Go', 'cornerRadius' => 12 }, 0, Set.new)
    expect(code).to include('shape = RoundedCornerShape(12.dp)')
  end

  it 'the square, the shadowed and the declared Buttons compile' do
    nodes = [{}, { 'shadow' => '#000000|0|2|0.3|4' }, { 'cornerRadius' => 12 }]
    emitted = nodes.map.with_index do |node, i|
      code = button.generate({ 'type' => 'Button', 'text' => 'Go' }.merge(node), 0, Set.new)
      "fun emitted#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}"
    end.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end

  it "casts a TextField's shadow in CustomTextField's square default" do
    outline = KjuiTools::Compose::Components::TextFieldComponent.shadow_outline({ 'type' => 'TextField' }, Set.new)
    expect(outline).to eq('RoundedCornerShape(0.dp)')
  end
end
