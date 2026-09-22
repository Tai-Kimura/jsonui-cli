# frozen_string_literal: true

require 'json'
require 'core/layout_validator'
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
      it 'calls the library modifier by default' do
        json_data = { 'type' => 'ScrollView' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).to include('.keyboardAvoidance(')
        expect(required_imports).to include(:keyboard_avoidance)
      end

      it 'calls the library modifier when keyboardAvoidance is true' do
        json_data = { 'type' => 'ScrollView', 'keyboardAvoidance' => true }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).to include('.keyboardAvoidance(')
      end

      it 'emits nothing for the keyboard when keyboardAvoidance is false' do
        json_data = { 'type' => 'ScrollView', 'keyboardAvoidance' => false }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).not_to include('keyboardAvoidance(')
        expect(result[:code]).not_to include('imePadding()')
        expect(required_imports).not_to include(:keyboard_avoidance)
      end

      it 'works with horizontal scroll and keyboardAvoidance disabled' do
        json_data = {
          'type' => 'ScrollView',
          'horizontalScroll' => true,
          'keyboardAvoidance' => false
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result[:code]).to include('LazyRow(')
        expect(result[:code]).not_to include('keyboardAvoidance(')
      end
    end
  end

  # ------------------------------------------------------- 1.8.108 / 1.8.110
  #
  # `keyboardAvoidancePadding` (SSoT: ScrollView, number, default 20): while
  # the IME is up the LazyColumn's viewport ends that far above it. From
  # 1.8.110 the emit is the library's `Modifier.keyboardAvoidance(listState,
  # clearanceDp)` — viewport half AND the follow that scrolls the focused
  # field up once the IME is up — shared with the dynamic ScrollView, so the
  # behaviour has one implementation (user's ruling 2026-09-22: change the
  # library's scroll, not two renders). Until 1.8.109 this spelled
  # `.imePadding().padding(bottom = if (WindowInsets.ime…)` itself and left
  # the follow to Compose, which a user's device did not do.
  describe 'keyboardAvoidancePadding → Modifier.keyboardAvoidance' do
    let(:imports) { Set.new }

    # generate returns a hash whose :code is the emitted LazyColumn.
    def code_for(extra)
      described_class.generate({ 'type' => 'ScrollView', 'id' => 'form_scroll' }.merge(extra), 0, imports)[:code]
    end

    it 'passes the declared clearance and the list state it scrolls through' do
      code = code_for('keyboardAvoidancePadding' => 32)
      expect(code).to include('val scrollPagingStateformscroll = rememberLazyListState()')
      expect(code).to include('state = scrollPagingStateformscroll,')
      expect(code).to include('.keyboardAvoidance(scrollPagingStateformscroll, 32)')
      expect(imports).to include(:keyboard_avoidance, :lazy_list_state)
    end

    it 'passes the SSoT default of 20 explicitly when the layout does not declare it' do
      expect(code_for({})).to include('.keyboardAvoidance(scrollPagingStateformscroll, 20)')
    end

    it 'is the last modifier, on the LazyColumn itself' do
      code = code_for('keyboardAvoidancePadding' => 32, 'width' => 'matchParent')
      expect(code).to include('.fillMaxWidth()')
      expect(code.index('.keyboardAvoidance(')).to be > code.index('.fillMaxWidth()')
      expect(code.index('.keyboardAvoidance(')).to be < code.index(') {')
    end

    it 'does not spell the viewport half itself any more (one implementation, in the library)' do
      code = code_for('keyboardAvoidancePadding' => 32)
      expect(code).not_to include('imePadding')
      expect(code).not_to include('WindowInsets.ime')
    end

    it 'emits no call when keyboardAvoidance is false' do
      code = code_for('keyboardAvoidance' => false, 'keyboardAvoidancePadding' => 32)
      expect(code).not_to include('keyboardAvoidance(')
      expect(code).not_to include('rememberLazyListState')
    end

    it 'falls back to the default clearance for a non-numeric value (the validator reports the type)' do
      expect(code_for('keyboardAvoidancePadding' => 'big')).to include('.keyboardAvoidance(scrollPagingStateformscroll, 20)')
    end

    it 'shares the state with defaultScrollAnchor rather than emitting a second one' do
      code = code_for('defaultScrollAnchor' => 'bottom')
      expect(code.scan('rememberLazyListState()').size).to eq(1)
      expect(code).to include('state = scrollPagingStateformscroll,')
      expect(code).to include('.keyboardAvoidance(scrollPagingStateformscroll, 20)')
    end

    # The emit is well-typed against a stub universe of the symbols it names
    # (spec/support/kotlin_compiler.rb): the list state, the LazyColumn's
    # `state` parameter and the library modifier's signature
    # `Modifier.keyboardAvoidance(LazyListState, Int)`. Types against stubs
    # only — not the Compose compiler's rules, and the stub signature is a
    # TRANSCRIPTION of KotlinJsonUI's `KeyboardAvoidance.kt`, not a compile
    # against it.
    it 'emits a scrollable whose keyboard avoidance compiles' do
      result = described_class.generate(
        { 'type' => 'ScrollView', 'id' => 'form_scroll', 'keyboardAvoidancePadding' => 32, 'child' => [] },
        1, imports
      )
      expect(<<~KOTLIN).to compile_as_kotlin
        annotation class Composable
        class SemanticsScope { var testTagsAsResourceId: Boolean = false }
        class LazyListState
        @Composable
        fun rememberLazyListState(): LazyListState = LazyListState()
        object Modifier {
            fun testTag(tag: String): Modifier = this
            fun semantics(block: SemanticsScope.() -> Unit): Modifier = this
        }
        @Composable
        fun Modifier.keyboardAvoidance(listState: LazyListState, clearanceDp: Int = 20): Modifier = this
        class LazyListScope { fun item(content: () -> Unit) { content() } }
        @Composable
        fun LazyColumn(state: LazyListState = rememberLazyListState(), modifier: Modifier = Modifier, content: LazyListScope.() -> Unit) { LazyListScope().content() }
        @Composable
        fun Host() {
        #{result[:code]}#{result[:closing]}
        }
      KOTLIN
    end
  end


  # ---------------------------------------------------------------- 1.8.109
  #
  # Every attribute this component READS is declared for kotlin in the SSoT.
  # `keyboardAvoidance` was declared `platform: "swift"` from the initial
  # commit while this component had read it all along (`!= false` decides
  # imePadding and, from 1.8.108, the clearance) — so the kjui validator
  # filed an Android `keyboardAvoidance: false` as "for Swift platform" and
  # did not type-check it, and a platform matrix drawn from the declaration
  # showed the attribute iOS-only. The population is read from the
  # declaration and the component's source, not from a list.
  describe 'the attributes this component reads are declared for kotlin' do
    let(:defs) do
      JSON.parse(File.read(File.join(
        File.dirname(JsonUIShared::LayoutValidator.method(:validate_layout).source_location.first),
        'attribute_definitions.json'
      )))
    end
    let(:source) { File.read(File.expand_path('../../../lib/compose/components/scrollview_component.rb', __dir__)) }

    it 'declares keyboardAvoidance and keyboardAvoidancePadding for kotlin' do
      %w[keyboardAvoidance keyboardAvoidancePadding].each do |attr|
        expect(source).to include("'#{attr}'"), "#{attr}: the component no longer reads it — drop it from this arm"
        platforms = Array(defs['ScrollView'][attr]['platform'])
        expect(platforms).to include('kotlin'), "ScrollView.#{attr} platform=#{platforms.inspect}: read here, not declared for kotlin"
      end
    end
  end

end
