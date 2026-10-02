# frozen_string_literal: true

require 'set'
require 'compose/components/textfield_component'
require 'compose/helpers/resource_resolver'

# A TextField's onFocus / onBlur / onBeginEditing / onEndEditing name a
# handler — in the binding form (`@{h}`) or bare (`h`) — and the generated
# code calls it as the data declares it (ModifierBuilder.
# get_event_handler_invocation: no value; the viewId when the handler takes
# one). Until jsonui-cli 1.9.6 the value was written as it stood, so the
# binding form put `data.@{h}?.invoke()` in the file, which does not parse
# (ticket kjui-textfield-focus-events-write-the-binding-braces).
RSpec.describe 'TextField focus events (kjui)' do
  let(:resolver) { KjuiTools::Compose::Helpers::ResourceResolver }

  before do
    resolver.data_definitions = {
      'h' => { 'name' => 'h', 'class' => '(() -> Void)?' },
      'g' => { 'name' => 'g', 'class' => '((String) -> Void)?' }
    }
  end

  after { resolver.data_definitions = {} }

  def emit(extra)
    KjuiTools::Compose::Components::TextFieldComponent.generate(
      { 'type' => 'TextField', 'id' => 'f', 'text' => '@{t}' }.merge(extra), 0, Set.new
    )
  end

  %w[onFocus onBlur onBeginEditing onEndEditing].each do |event|
    it "#{event}: the binding form and the bare name call the same handler" do
      expect(emit(event => '@{h}')).to include("#{event} = { data.h?.invoke() }")
      expect(emit(event => 'h')).to include("#{event} = { data.h?.invoke() }")
      expect(emit(event => '@{h}')).not_to include('@{')
    end
  end

  it "hands the viewId to a handler that takes one" do
    expect(emit('onBeginEditing' => '@{g}')).to include('onBeginEditing = { data.g?.invoke("f") }')
  end

  it 'writes no call for a blank handler' do
    code = emit('onFocus' => '@{}', 'onBlur' => '   ')
    expect(code).not_to include('onFocus =')
    expect(code).not_to include('onBlur =')
  end

  it 'writes Kotlin a compiler accepts' do
    code = emit('onFocus' => '@{h}', 'onBlur' => 'h', 'onBeginEditing' => '@{g}', 'onEndEditing' => '@{h}')
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(code)}
      class Data(val t: String = "", val fIsFocused: Boolean = false,
                 val h: (() -> Unit)? = null, val g: ((String) -> Unit)? = null)
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      fun focusEvents(data: Data, viewModel: ViewModel) {
      #{code}
      }
    KOTLIN
  end
end
