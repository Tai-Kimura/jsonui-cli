# frozen_string_literal: true

require 'set'
require 'compose/components/textfield_component'
require 'compose/components/textview_component'
require 'compose/helpers/resource_resolver'
require 'compose/helpers/import_manager'

# A bound field follows what the view model holds, also when the view model
# takes an edit back to the value it held (ticket kjui-textfield-corrected-
# value-not-written-back). The behaviour is measured on a device by KotlinJsonUI
# TextFieldCorrectedValueTest, on a paste of this text; here, the text.
RSpec.describe 'TextField / TextView: the field follows the held value (kjui)' do
  let(:resolver) { KjuiTools::Compose::Helpers::ResourceResolver }
  let(:components) { KjuiTools::Compose::Components }

  before do
    resolver.data_definitions = {
      'age' => { 'name' => 'age', 'class' => 'String' },
      'onAgeChange' => { 'name' => 'onAgeChange', 'class' => '((String) -> Void)?' }
    }
  end

  after { resolver.data_definitions = {} }

  def emit(component, extra = {})
    imports = Set.new
    code = component.generate({ 'type' => 'x', 'id' => 'f', 'text' => '@{age}' }.merge(extra), 0, imports)
    [code, imports]
  end

  # The effect that sends the edit out, on one line.
  def edit_effect(code)
    code.lines.find { |l| l.start_with?('LaunchedEffect(textFieldState_f.text)') && l.include?('updateData') }
  end

  { 'TextField' => :TextFieldComponent, 'TextView' => :TextViewComponent }.each do |type, name|
    describe type do
      let(:component) { components.const_get(name) }

      it 'reads the value again after the edit went out, two frames later, and writes it when it differs' do
        code, = emit(component, 'onTextChange' => '@{onAgeChange}')
        expect(code).to include('val textFieldState_f_held = rememberUpdatedState(data.age)')
        expect(edit_effect(code)).to include(
          'viewModel.updateData(mapOf("age" to newValue)); data.onAgeChange?.invoke(newValue); ' \
          'withFrameNanos { }; withFrameNanos { }; ' \
          'if (textFieldState_f.text.toString() == newValue && textFieldState_f_held.value != newValue) ' \
          'textFieldState_f.edit { replace(0, length, textFieldState_f_held.value) }'
        )
      end

      it 'does so without a handler too: a view model updateData of its own can correct' do
        code, = emit(component)
        expect(edit_effect(code)).to include(
          'viewModel.updateData(mapOf("age" to newValue)); withFrameNanos { }; withFrameNanos { }; if ('
        )
      end

      it 'calls a bare handler name as it calls the binding form' do
        code, = emit(component, 'onTextChange' => 'onAgeChange')
        expect(edit_effect(code)).to include('data.onAgeChange?.invoke(newValue); withFrameNanos')
      end

      it 'asks for what it names' do
        _, imports = emit(component)
        map = KjuiTools::Compose::Helpers::ImportManager.get_imports_map
        expect(imports).to include(:remember_updated_state, :with_frame_nanos)
        expect(map[:remember_updated_state]).to eq('import androidx.compose.runtime.rememberUpdatedState')
        expect(map[:with_frame_nanos]).to eq('import androidx.compose.runtime.withFrameNanos')
      end

      it 'writes Kotlin a compiler accepts' do
        code, = emit(component, 'onTextChange' => '@{onAgeChange}')
        expect(<<~KOTLIN).to compile_as_kotlin
          #{ComposeStubUniverse.common_stages(code)}
          class Data(val age: String = "", val fIsFocused: Boolean = false, val onAgeChange: ((String) -> Unit)? = null)
          class ViewModel { fun updateData(values: Map<String, Any?>) {} }
          fun writeBack(data: Data, viewModel: ViewModel) {
          #{code}
          }
        KOTLIN
      end

      it 'leaves a field with no binding as it was: there is no value to follow' do
        code, imports = emit(component, 'text' => 'plain', 'onTextChange' => '@{onAgeChange}')
        expect(code).not_to include('withFrameNanos')
        expect(imports).not_to include(:with_frame_nanos)
      end
    end
  end
end
