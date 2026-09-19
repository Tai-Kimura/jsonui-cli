# frozen_string_literal: true

require 'compose/components/selectbox_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::SelectBoxComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    context 'standard SelectBox' do
      it 'generates basic SelectBox component' do
        json_data = { 'type' => 'SelectBox' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('SelectBox(')
        expect(required_imports).to include(:selectbox_component)
      end

      it 'maps 4-element paddings as [top, right, bottom, left] to contentPadding' do
        json_data = { 'type' => 'SelectBox', 'paddings' => [1, 2, 3, 4] }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include(
          'contentPadding = PaddingValues(top = 1.dp, end = 2.dp, bottom = 3.dp, start = 4.dp)'
        )
      end

      it 'generates SelectBox with static options array' do
        json_data = {
          'type' => 'SelectBox',
          'options' => ['Option 1', 'Option 2', 'Option 3']
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('options = listOf(')
        expect(result).to include('Option 1')
        expect(result).to include('Option 2')
      end

      it 'generates SelectBox with items array' do
        json_data = {
          'type' => 'SelectBox',
          'items' => ['A', 'B', 'C']
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('options = listOf(')
      end

      it 'generates SelectBox with hash options' do
        json_data = {
          'type' => 'SelectBox',
          'options' => [
            { 'value' => '1', 'label' => 'First' },
            { 'value' => '2', 'label' => 'Second' }
          ]
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('First')
        expect(result).to include('Second')
      end

      it 'generates SelectBox with dynamic options binding' do
        json_data = {
          'type' => 'SelectBox',
          'options' => '@{availableOptions}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('options = data.availableOptions')
      end

      it 'generates SelectBox with selectedItem binding' do
        json_data = {
          'type' => 'SelectBox',
          'selectedItem' => '@{selectedValue}',
          'options' => ['A', 'B']
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('value = data.selectedValue')
        expect(result).to include('onValueChange')
      end

      it 'generates SelectBox with bind attribute' do
        json_data = {
          'type' => 'SelectBox',
          'bind' => '@{choice}',
          'options' => ['A', 'B']
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('value = data.choice')
      end

      it 'generates SelectBox with hint' do
        json_data = {
          'type' => 'SelectBox',
          'hint' => 'Select an option'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('placeholder = "Select an option"')
      end

      it 'generates SelectBox with placeholder' do
        json_data = {
          'type' => 'SelectBox',
          'placeholder' => 'Choose one'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('placeholder = "Choose one"')
      end

      # Spec canonical `prompt` is the primary key, with hint/placeholder as
      # aliases. The codegen must accept all three and prefer prompt when
      # multiple are set.
      it 'generates SelectBox with prompt (canonical primary key)' do
        json_data = {
          'type' => 'SelectBox',
          'prompt' => 'Choose one'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('placeholder = "Choose one"')
      end

      it 'prefers prompt over hint and placeholder when multiple are present' do
        json_data = {
          'type' => 'SelectBox',
          'prompt' => 'from prompt',
          'hint' => 'from hint',
          'placeholder' => 'from placeholder'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('placeholder = "from prompt"')
        expect(result).not_to include('"from hint"')
        expect(result).not_to include('"from placeholder"')
      end

      it 'generates disabled SelectBox' do
        json_data = {
          'type' => 'SelectBox',
          'disabled' => true
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('enabled = false')
      end

      it 'generates SelectBox with enabled false' do
        json_data = {
          'type' => 'SelectBox',
          'enabled' => false
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('enabled = false')
      end

      it 'generates SelectBox with background color' do
        json_data = {
          'type' => 'SelectBox',
          'background' => '#FFFFFF'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('backgroundColor')
      end

      it 'generates SelectBox with borderColor' do
        json_data = {
          'type' => 'SelectBox',
          'borderColor' => '#000000'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('borderColor')
      end

      it 'generates SelectBox with fontColor' do
        json_data = {
          'type' => 'SelectBox',
          'fontColor' => '#333333'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('textColor')
      end

      it 'generates SelectBox with hintColor' do
        json_data = {
          'type' => 'SelectBox',
          'hintColor' => '#999999'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('hintColor')
      end

      it 'generates SelectBox with cornerRadius' do
        json_data = {
          'type' => 'SelectBox',
          'cornerRadius' => 8
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('cornerRadius = 8')
      end

      it 'generates SelectBox with cancelButtonBackgroundColor' do
        json_data = {
          'type' => 'SelectBox',
          'cancelButtonBackgroundColor' => '#FF0000'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('cancelButtonBackgroundColor')
      end

      it 'generates SelectBox with cancelButtonTextColor' do
        json_data = {
          'type' => 'SelectBox',
          'cancelButtonTextColor' => '#FFFFFF'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('cancelButtonTextColor')
      end
    end

    # SSoT SelectBox.caretAttributes — a cross-platform object since 1.8.101
    # (UIKit-only before). Present: the face draws the caret itself; absent:
    # the native arrow and every existing baseline stay where they are.
    context 'caretAttributes' do
      let(:fixture_caret) do
        # The `SelectBox/caretAttributes__static` fixture value, verbatim.
        { 'width' => 32, 'height' => 32, 'tintColor' => '#FF0000',
          'background' => '#00AA00', 'rightMargin' => 24 }
      end

      it 'emits nothing when the object is absent, so the picture does not move' do
        result = described_class.generate({ 'type' => 'SelectBox', 'items' => %w[One Two] }, 0, required_imports)
        expect(result).not_to include('caret =')
        expect(required_imports).not_to include(:selectbox_caret)
      end

      it 'hands the fixture object to the library as a SelectBoxCaret' do
        json_data = { 'type' => 'SelectBox', 'items' => %w[One Two Three], 'caretAttributes' => fixture_caret }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include(
          'caret = SelectBoxCaret(width = 32, height = 32, ' \
          'tintColor = Color(android.graphics.Color.parseColor("#FF0000")), ' \
          'background = Color(android.graphics.Color.parseColor("#00AA00")), ' \
          'rightMargin = 24),'
        )
        expect(required_imports).to include(:selectbox_caret)
      end

      it 'an empty object is still present: the face draws its own caret with the defaults' do
        json_data = { 'type' => 'SelectBox', 'items' => %w[One], 'caretAttributes' => {} }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('caret = SelectBoxCaret(),')
      end

      it 'resolves src as a drawable name, the way Image resolves its src' do
        json_data = { 'type' => 'SelectBox', 'items' => %w[One], 'caretAttributes' => { 'src' => 'My-Arrow.png', 'rightMargin' => 12 } }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('caret = SelectBoxCaret(painter = painterResource(id = R.drawable.my_arrow), rightMargin = 12),')
        expect(required_imports).to include(:painter_resource, :r_class)
      end

      it 'leaves a key of the wrong type out rather than emitting it as 0' do
        json_data = { 'type' => 'SelectBox', 'items' => %w[One], 'caretAttributes' => { 'width' => '32', 'rightMargin' => 24 } }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('caret = SelectBoxCaret(rightMargin = 24),')
      end

      it 'is not emitted for a date picker, which has no closed-state caret' do
        json_data = { 'type' => 'SelectBox', 'selectItemType' => 'Date', 'caretAttributes' => fixture_caret }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('DateSelectBox(')
        expect(result).not_to include('caret =')
        expect(required_imports).not_to include(:selectbox_caret)
      end

      it 'does not touch a SelectBox whose caretAttributes is not an object' do
        json_data = { 'type' => 'SelectBox', 'items' => %w[One], 'caretAttributes' => 'nope' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).not_to include('caret =')
      end

      # One broad arm (spec/support/kotlin_compiler.rb): the fixture call,
      # with its modifier chain, is well-typed against a stub universe.
      # ⚠️ The SelectBoxCaret / SelectBox stubs below are a hand transcription
      # of library/.../SelectBox.kt, so this proves the emit is Kotlin — not
      # that it matches the library. That second half is the codegen
      # conformance host, which compiles the generated code against the real
      # library (KotlinJsonUI conformance-host/scripts/generate_codegen_host.rb).
      it 'emits a call that compiles, caret included' do
        json_data = {
          'type' => 'SelectBox', 'id' => 'target', 'width' => 200, 'height' => 'wrapContent',
          'items' => %w[One Two Three], 'caretAttributes' => fixture_caret
        }
        result = described_class.generate(json_data, 1, required_imports)
        expect(<<~KOTLIN).to compile_as_kotlin
          annotation class Composable
          class Color(val argb: Int) { companion object { val Unspecified = Color(0) } }
          object android { object graphics { object Color { fun parseColor(s: String): Int = 0 } } }
          class Painter
          class Dp(val value: Float)
          val Int.dp: Dp get() = Dp(toFloat())
          class SemanticsScope { var testTagsAsResourceId: Boolean = false }
          object Modifier {
              fun testTag(tag: String): Modifier = this
              fun semantics(block: SemanticsScope.() -> Unit): Modifier = this
              fun requiredWidth(width: Dp): Modifier = this
              fun wrapContentHeight(): Modifier = this
          }
          // transcribed from library/src/main/kotlin/com/kotlinjsonui/components/SelectBox.kt
          data class SelectBoxCaret(
              val painter: Painter? = null,
              val width: Int? = null,
              val height: Int? = null,
              val tintColor: Color? = null,
              val background: Color? = null,
              val rightMargin: Int = 0
          )
          @Composable
          fun SelectBox(
              value: String,
              onValueChange: (String) -> Unit,
              options: List<String>,
              modifier: Modifier = Modifier,
              caret: SelectBoxCaret? = null
          ) {}
          @Composable
          fun Host() {
          #{result}
          }
        KOTLIN
      end
    end

    context 'DateSelectBox' do
      it 'generates DateSelectBox for date type' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('DateSelectBox(')
        expect(required_imports).to include(:date_selectbox_component)
      end

      it 'generates DateSelectBox with datePickerMode' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'datePickerMode' => 'date'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('datePickerMode = "date"')
      end

      it 'generates DateSelectBox with datePickerStyle' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'datePickerStyle' => 'wheels'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('datePickerStyle = "wheels"')
      end

      it 'generates DateSelectBox with dateFormat' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'dateFormat' => 'yyyy-MM-dd'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('dateFormat = "yyyy-MM-dd"')
      end

      it 'generates DateSelectBox with dateStringFormat' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'dateStringFormat' => 'MM/dd/yyyy'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('dateFormat = "MM/dd/yyyy"')
      end

      it 'generates DateSelectBox with minuteInterval' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'minuteInterval' => 15
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('minuteInterval = 15')
      end

      it 'generates DateSelectBox with minimumDate' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'minimumDate' => '2020-01-01'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('minimumDate = "2020-01-01"')
      end

      it 'generates DateSelectBox with maximumDate' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'maximumDate' => '2030-12-31'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('maximumDate = "2030-12-31"')
      end

      it 'adds fillMaxWidth for date picker by default' do
        json_data = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('.fillMaxWidth()')
      end
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      result = described_class.send(:indent, 'text', 0)
      expect(result).to eq('text')
    end

    it 'adds indentation for level 1' do
      result = described_class.send(:indent, 'text', 1)
      expect(result).to eq('    text')
    end
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'id' => 'countrySelect',
        'selectedItem' => '@{country}',
        'options' => ['USA', 'Japan', 'UK'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSelectionChange?.invoke()')
      expect(result).not_to include('invoke("countrySelect"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'id' => 'countrySelect',
        'selectedItem' => '@{country}',
        'options' => ['USA', 'Japan', 'UK'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSelectionChange?.invoke("countrySelect", newValue)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, String) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'id' => 'languageSelect',
        'options' => ['English', 'Japanese'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSelectionChange?.invoke("languageSelect", newValue)')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'id' => 'countrySelect',
        'selectedItem' => '@{country}',
        'options' => ['USA', 'Japan', 'UK'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onSelectionChange?.invoke("countrySelect", newValue)')
    end

    it 'uses default selectbox id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'SelectBox',
        'options' => ['A', 'B'],
        'onValueChange' => '@{onSelectionChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onSelectionChange?.invoke("selectbox", newValue)')
    end

    # The payload is the new value of the SELECTION BINDING, as on sjui
    # (selectbox_converter_spec 'with onValueChange on a bound selectedIndex'):
    # a bound selectedIndex hands the handler the Int index, not the item
    # String, so one `((Int) -> Unit)?` declaration compiles on both platforms.
    context 'with a bound selectedIndex' do
      let(:json_data) do
        {
          'type' => 'SelectBox',
          'id' => 'countrySelect',
          'items' => '@{countries}',
          'selectedIndex' => '@{countryIndex}',
          'onValueChange' => '@{onSelectionChange}'
        }
      end

      it 'passes the Int index, not the item, to an (Int) -> Unit handler' do
        KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
          'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((Int) -> Unit)?' }
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('val index = data.countries.indexOf(newValue)')
        expect(result).to include('viewModel.updateData(mapOf("countryIndex" to index))')
        expect(result).to include('data.onSelectionChange?.invoke(index)')
        expect(result).not_to include('invoke(newValue)')
      end

      it 'passes viewId + Int index to a (String, Int) -> Unit handler' do
        KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
          'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((String, Int) -> Unit)?' }
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('data.onSelectionChange?.invoke("countrySelect", index)')
      end
    end

    it 'still passes the item String when selectedItem is bound' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onSelectionChange' => { 'name' => 'onSelectionChange', 'class' => '((String, String) -> Unit)?' }
      }
      json_data = {
        'type' => 'SelectBox',
        'id' => 'countrySelect',
        'items' => ['USA', 'Japan'],
        'selectedItem' => '@{country}',
        'onValueChange' => '@{onSelectionChange}'
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('viewModel.updateData(mapOf("country" to newValue))')
      expect(result).to include('data.onSelectionChange?.invoke("countrySelect", newValue)')
      expect(result).not_to include('val index')
    end
  end
end
