# frozen_string_literal: true

require 'set'
require 'compose/components/textfield_component'
require 'compose/components/textview_component'
require 'compose/helpers/resource_resolver'
require 'compose/helpers/import_manager'

# A bound field follows what the view model holds, also when the view model
# takes an edit back to the value it held (ticket kjui-textfield-corrected-
# value-not-written-back), and a key is not lost to an older value (ticket 2026-11-07-
# kjui-textfield-stale-value-overwrites-newer-key). The behaviour is measured on a
# device by KotlinJsonUI TextFieldCorrectedValueTest, on a paste of this text; here,
# the text.
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
    code.lines.find { |l| l.start_with?('LaunchedEffect(textFieldState_f)') && l.include?('updateData') }
  end

  { 'TextField' => :TextFieldComponent, 'TextView' => :TextViewComponent }.each do |type, name|
    describe type do
      let(:component) { components.const_get(name) }

      it 'does not write its own echo back, and takes a value it did not send' do
        code, = emit(component)
        expect(code).to include('val textFieldState_f_sent = remember { ArrayDeque<String>() }')
        expect(code).to include(
          'LaunchedEffect(data.age) { val held = viewModel.data.value.age; ' \
          'val echo = textFieldState_f_sent.indexOf(held); ' \
          'if (echo >= 0) repeat(echo + 1) { textFieldState_f_sent.removeFirst() } ' \
          'else if (textFieldState_f.text.toString() != held) textFieldState_f.edit { replace(0, length, held) } }'
        )
      end

      it 'waits on the value after sending, not on time, and compares with the view model, not composition' do
        code, = emit(component, 'onTextChange' => '@{onAgeChange}')
        expect(edit_effect(code)).to include(
          'snapshotFlow { textFieldState_f.text.toString() }.collectLatest { newValue -> ' \
          'val data = viewModel.data.value; ' \
          'if (newValue != data.age) { textFieldState_f_sent.addLast(newValue); ' \
          'viewModel.updateData(mapOf("age" to newValue)); data.onAgeChange?.invoke(newValue); ' \
          'val held = viewModel.data.first { it.age != newValue }.age; textFieldState_f_sent.clear(); ' \
          'textFieldState_f_sent.addLast(held); ' \
          'if (textFieldState_f.text.toString() == newValue) textFieldState_f.edit { replace(0, length, held) }'
        )
        expect(code).not_to include('withFrameNanos')
        expect(code).not_to match(/LaunchedEffect\(data\.age\) \{ if \(/)
      end

      it 'does so without a handler too: a view model updateData of its own can correct' do
        code, = emit(component)
        expect(edit_effect(code)).to include(
          'viewModel.updateData(mapOf("age" to newValue)); val held = viewModel.data.first'
        )
      end

      it 'calls a bare handler name as it calls the binding form' do
        code, = emit(component, 'onTextChange' => 'onAgeChange')
        expect(edit_effect(code)).to include('data.onAgeChange?.invoke(newValue); val held')
      end

      it 'asks for what it names' do
        _, imports = emit(component)
        map = KjuiTools::Compose::Helpers::ImportManager.get_imports_map
        expect(imports).to include(:remember, :flow_first, :snapshot_flow, :flow_collect_latest)
        expect(map[:flow_collect_latest]).to eq('import kotlinx.coroutines.flow.collectLatest')
        expect(map[:flow_first]).to eq('import kotlinx.coroutines.flow.first')
      end

      it 'writes Kotlin a compiler accepts' do
        code, = emit(component, 'onTextChange' => '@{onAgeChange}')
        expect(<<~KOTLIN).to compile_as_kotlin
          #{ComposeStubUniverse.common_stages(code)}
          class Data(val age: String = "", val fIsFocused: Boolean = false, val onAgeChange: ((String) -> Unit)? = null)
          class DataFlow { val value = Data(); suspend fun first(predicate: (Data) -> Boolean): Data = value }
          class ViewModel { val data = DataFlow(); fun updateData(values: Map<String, Any?>) {} }
          fun writeBack(data: Data, viewModel: ViewModel) {
          #{code}
          }
        KOTLIN
      end

      it 'leaves a field with no binding as it was: there is no value to follow' do
        code, imports = emit(component, 'text' => 'plain', 'onTextChange' => '@{onAgeChange}')
        expect(code).not_to include('_sent')
        expect(imports).not_to include(:flow_first)
      end
    end
  end
end
