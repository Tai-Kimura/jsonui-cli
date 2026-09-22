# frozen_string_literal: true

require 'compose/components/scrollview_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::ScrollViewComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates vertical LazyColumn by default' do
      json_data = { 'type' => 'ScrollView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('LazyColumn(')
      expect(required_imports).to include(:lazy_column)
    end

    it 'generates horizontal LazyRow when horizontalScroll is true' do
      json_data = { 'type' => 'ScrollView', 'horizontalScroll' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('LazyRow(')
      expect(required_imports).to include(:lazy_row)
    end

    it 'generates horizontal LazyRow when orientation is horizontal' do
      json_data = { 'type' => 'ScrollView', 'orientation' => 'horizontal' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('LazyRow(')
    end

    it 'returns children for parent to process' do
      json_data = { 
        'type' => 'ScrollView', 
        'child' => [{ 'type' => 'Text', 'text' => 'Hello' }] 
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:children]).to be_an(Array)
      expect(result[:children].first['type']).to eq('Text')
    end

    it 'returns closing braces' do
      json_data = { 'type' => 'ScrollView' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:closing]).to include('}')
    end

    # Regression: kjui-responsive-inline-align-not-available-in-lazyitemscope
    # Children render inside the emitted `item { ... }` lambda whose receiver
    # is LazyItemScope, not Column/RowScope. handle_container_result reads
    # `:layout_type` to know what scope its children sit in; without an
    # override it falls back to the outer parent_type (e.g. 'Column' when a
    # vertical SafeAreaView wraps the ScrollView), and a child responsive
    # View that emits `Modifier.align(Alignment.CenterHorizontally)` fails
    # to resolve at compile time. ScopeFree routes alignment through the
    # scope-independent `wrapContentWidth/Height` modifiers.
    it 'returns layout_type: ScopeFree so children inside item { } avoid scope-bound .align' do
      json_data = { 'type' => 'ScrollView', 'child' => [{ 'type' => 'Text', 'text' => 'Hello' }] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:layout_type]).to eq('ScopeFree')
    end

    it 'handles single child as array' do
      json_data = { 
        'type' => 'ScrollView', 
        'child' => { 'type' => 'Text', 'text' => 'Single' } 
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:children]).to be_an(Array)
    end

    it 'detects horizontal from child View orientation' do
      json_data = {
        'type' => 'ScrollView',
        'child' => [{ 'type' => 'View', 'orientation' => 'horizontal' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result[:code]).to include('LazyRow(')
    end

    context 'keyboardAvoidance' do
      it 'adds imePadding by default' do
        json_data = { 'type' => 'ScrollView' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).to include('.imePadding()')
        expect(required_imports).to include(:ime_padding)
      end

      it 'adds imePadding when keyboardAvoidance is true' do
        json_data = { 'type' => 'ScrollView', 'keyboardAvoidance' => true }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).to include('.imePadding()')
        expect(required_imports).to include(:ime_padding)
      end

      it 'does not add imePadding when keyboardAvoidance is false' do
        json_data = { 'type' => 'ScrollView', 'keyboardAvoidance' => false }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).not_to include('imePadding()')
        expect(required_imports).not_to include(:ime_padding)
      end

      it 'works with horizontal scroll and keyboardAvoidance disabled' do
        json_data = {
          'type' => 'ScrollView',
          'horizontalScroll' => true,
          'keyboardAvoidance' => false
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).to include('LazyRow(')
        expect(result[:code]).not_to include('imePadding()')
      end
    end
  end

  # ---------------------------------------------------------------- 1.8.108
  #
  # `keyboardAvoidancePadding` (SSoT: ScrollView, number, default 20): while
  # the IME is up the LazyColumn's viewport ends that far above it, after
  # imePadding and on the scrollable itself, so bringIntoView leaves the
  # clearance. Absent → 20, the SSoT default, so both platforms agree
  # whether or not the attribute is written.
  describe 'keyboardAvoidancePadding (1.8.108)' do
    let(:imports) { Set.new }

    # generate returns a hash whose :code is the emitted LazyColumn.
    def code_for(extra)
      described_class.generate({ 'type' => 'ScrollView' }.merge(extra), 0, imports)[:code]
    end

    it 'pads the scrollable by the declared value only while the IME is up, after imePadding' do
      code = code_for('keyboardAvoidancePadding' => 32)
      expect(code).to include('.imePadding()')
      expect(code).to include('.padding(bottom = if (WindowInsets.ime.getBottom(LocalDensity.current) > 0) 32.dp else 0.dp)')
      expect(code.index('.imePadding()')).to be < code.index('WindowInsets.ime.getBottom')
      expect(imports).to include(:window_insets_ime)
    end

    it 'applies the SSoT default of 20 when the layout does not declare it' do
      expect(code_for({})).to include(') 20.dp else 0.dp)')
    end

    it 'emits neither imePadding nor the clearance when keyboardAvoidance is false' do
      code = code_for('keyboardAvoidance' => false, 'keyboardAvoidancePadding' => 32)
      expect(code).not_to include('imePadding')
      expect(code).not_to include('WindowInsets.ime')
    end

    it 'emits no clearance for a non-numeric value (the validator reports the type)' do
      expect(code_for('keyboardAvoidancePadding' => 'big')).not_to include('WindowInsets.ime')
    end

    # The clearance emit is well-typed against a stub universe of the
    # Compose symbols it names (spec/support/kotlin_compiler.rb): the
    # `WindowInsets.ime.getBottom(LocalDensity.current)` read, the `Dp`
    # arithmetic and the conditional padding. Types against stubs only —
    # not the Compose compiler's rules.
    it 'emits a scrollable whose clearance compiles' do
      result = described_class.generate(
        { 'type' => 'ScrollView', 'id' => 'form_scroll', 'keyboardAvoidancePadding' => 32, 'child' => [] },
        1, imports
      )
      expect(<<~KOTLIN).to compile_as_kotlin
        annotation class Composable
        class SemanticsScope { var testTagsAsResourceId: Boolean = false }
        class Dp(val value: Float)
        val Int.dp: Dp get() = Dp(this.toFloat())
        class Density
        object LocalDensity { val current: Density = Density() }
        class Insets { fun getBottom(density: Density): Int = 0 }
        object WindowInsets { val ime: Insets = Insets() }
        object Modifier {
            fun testTag(tag: String): Modifier = this
            fun semantics(block: SemanticsScope.() -> Unit): Modifier = this
            fun imePadding(): Modifier = this
            fun padding(bottom: Dp): Modifier = this
        }
        class LazyListScope { fun item(content: () -> Unit) { content() } }
        @Composable
        fun LazyColumn(modifier: Modifier = Modifier, content: LazyListScope.() -> Unit) { LazyListScope().content() }
        @Composable
        fun Host() {
        #{result[:code]}#{result[:closing]}
        }
      KOTLIN
    end
  end

end
