# frozen_string_literal: true

require 'compose/components/radio_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'
require_relative '../../support/kotlin_compiler'

RSpec.describe KjuiTools::Compose::Components::RadioComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    context 'with items array' do
      it 'generates radio group with items' do
        json_data = {
          'type' => 'Radio',
          'items' => ['Option 1', 'Option 2', 'Option 3'],
          'selectedValue' => '@{selectedOption}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Column(')
        expect(result).to include('RadioButton(')
        expect(result).to include('Option 1')
        expect(result).to include('Option 2')
        expect(required_imports).to include(:clickable)
      end

      it 'generates radio group with label' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Choose an option',
          'items' => ['A', 'B'],
          'selectedValue' => '@{choice}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Choose an option')
      end

      it 'handles fontColor for text' do
        json_data = {
          'type' => 'Radio',
          'items' => ['A', 'B'],
          'selectedValue' => '@{choice}',
          'fontColor' => '#FF0000'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('color =')
      end
    end

    context 'with individual radio item' do
      it 'generates radio item with group' do
        json_data = {
          'type' => 'Radio',
          'group' => 'myGroup',
          'id' => 'option1',
          'text' => 'Option 1'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Row(')
        expect(result).to include('RadioButton(')
        expect(result).to include('Option 1')
      end

      it 'generates radio item with text only' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Radio Label'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('RadioButton(')
        expect(result).to include('Radio Label')
      end

      it 'generates radio with square icon (checkbox)' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Check this',
          'icon' => 'square',
          'selectedIcon' => 'checkmark.square.fill'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Checkbox(')
      end

      it 'generates radio with custom icons' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Star this',
          'icon' => 'star',
          'selectedIcon' => 'star.fill'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('IconButton(')
        expect(required_imports).to include(:icon_button)
        expect(required_imports).to include(:icons)
      end

      it 'handles selectedColor for custom icons' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Custom',
          'icon' => 'heart',
          'selectedIcon' => 'heart.fill',
          'selectedColor' => '#FF0000'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('tint =')
      end

      it 'handles fontColor for text' do
        json_data = {
          'type' => 'Radio',
          'text' => 'Colored',
          'fontColor' => '#333333'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('color =')
      end
    end

    context 'with options array' do
      it 'generates radio with static options' do
        json_data = {
          'type' => 'Radio',
          'options' => ['Red', 'Green', 'Blue'],
          'bind' => '@{color}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('Column(')
        expect(result).to include('RadioButton(')
        expect(result).to include('Red')
        expect(result).to include('Green')
        expect(result).to include('Blue')
      end

      it 'generates radio with hash options' do
        json_data = {
          'type' => 'Radio',
          'options' => [
            { 'value' => '1', 'label' => 'First' },
            { 'value' => '2', 'label' => 'Second' }
          ],
          'bind' => '@{selected}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('First')
        expect(result).to include('Second')
      end

      it 'generates radio with dynamic options binding' do
        json_data = {
          'type' => 'Radio',
          'options' => '@{availableOptions}',
          'bind' => '@{selectedOption}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('data.availableOptions.forEach')
      end

      it 'handles onValueChange callback' do
        json_data = {
          'type' => 'Radio',
          'options' => ['A', 'B'],
          'onValueChange' => '@{handleChange}'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('data.handleChange?.invoke()')
      end

      it 'handles selectedColor and unselectedColor' do
        json_data = {
          'type' => 'Radio',
          'options' => ['Yes', 'No'],
          'bind' => '@{answer}',
          'selectedColor' => '#007AFF',
          'unselectedColor' => '#CCCCCC'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('RadioButtonDefaults.colors')
        expect(result).to include('selectedColor')
        expect(result).to include('unselectedColor')
        expect(required_imports).to include(:radio_colors)
      end
    end
  end

  describe '.map_icon_name' do
    it 'maps circle to PanoramaFishEye' do
      result = described_class.send(:map_icon_name, 'circle')
      expect(result).to include('PanoramaFishEye')
    end

    it 'maps checkmark.circle.fill to CheckCircle' do
      result = described_class.send(:map_icon_name, 'checkmark.circle.fill')
      expect(result).to include('CheckCircle')
    end

    it 'maps star to Star' do
      result = described_class.send(:map_icon_name, 'star')
      expect(result).to include('Star')
    end

    it 'maps heart to Favorite' do
      result = described_class.send(:map_icon_name, 'heart')
      expect(result).to include('Favorite')
    end

    it 'returns default for unknown icon' do
      result = described_class.send(:map_icon_name, 'unknown')
      expect(result).to include('Star')
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
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'id' => 'genderRadio',
        'options' => ['Male', 'Female'],
        'selectedValue' => '@{gender}', # the options group's selection (a lone bind arrives as it: BindFold)
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onRadioChange?.invoke()')
      expect(result).not_to include('invoke("genderRadio"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'id' => 'genderRadio',
        'options' => ['Male', 'Female'],
        'selectedValue' => '@{gender}', # the options group's selection (a lone bind arrives as it: BindFold)
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onRadioChange?.invoke("genderRadio", "Male")')
      expect(result).to include('data.onRadioChange?.invoke("genderRadio", "Female")')
    end

    it 'generates invoke(viewId, value) when handler type is (String, String) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'id' => 'sizeRadio',
        'options' => ['Small', 'Large'],
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onRadioChange?.invoke("sizeRadio", "Small")')
      expect(result).to include('data.onRadioChange?.invoke("sizeRadio", "Large")')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '((String, String) -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'id' => 'genderRadio',
        'options' => ['Male', 'Female'],
        'selectedValue' => '@{gender}', # the options group's selection (a lone bind arrives as it: BindFold)
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onRadioChange?.invoke("genderRadio", "Male")')
    end

    it 'uses its position as the viewId when no id is specified (LayoutPath.view_id; it was the kind word)' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRadioChange' => { 'name' => 'onRadioChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Radio',
        'options' => ['Yes', 'No'],
        'onValueChange' => '@{onRadioChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onRadioChange?.invoke("radio_0", "Yes")')
    end
  end
  describe 'icon appearance' do
    def glyph(extra)
      described_class.generate(
        { 'type' => 'Radio', 'id' => 'r1', 'group' => 'g', 'text' => 'A' }.merge(extra), 0, Set.new
      )
    end

    it 'sizes and tints the default RadioButton' do
      code = glyph({ 'iconSize' => 32, 'iconColor' => '#FF0000' })
      expect(code).to include('modifier = Modifier.size(32.dp)')
      expect(code).to include('RadioButtonDefaults.colors(')
    end

    # iconColor is one tint for the whole glyph, unlike selectedColor which sets
    # only the selected state.
    it 'applies iconColor to both radio states' do
      code = glyph({ 'iconColor' => '#FF0000' })
      expect(code).to include('selectedColor = ')
      expect(code).to include('unselectedColor = ')
    end

    it 'tints the custom icon branch unconditionally rather than per state' do
      code = glyph({ 'icon' => 'star', 'selectedIcon' => 'star.fill', 'iconColor' => '#00FF00' })
      expect(code).to include('#00FF00')
      expect(code).not_to include('else Color.Gray')
    end

    it 'keeps the per-state tint when only selectedColor is given' do
      code = glyph({ 'icon' => 'star', 'selectedIcon' => 'star.fill', 'selectedColor' => '#00FF00' })
      expect(code).to include('tint = if (isSelected)')
      expect(code).to include('else Color.Gray')
    end

    # With no colour of its own the selected colour is still emitted: the
    # tint a container handed down, else theme primary (InheritedTint).
    it 'emits no size and only the handed-down tint when neither is declared' do
      code = glyph({})
      expect(code).not_to include('Modifier.size(')
      expect(code).to include('colors = RadioButtonDefaults.colors(selectedColor = jsonUITintOr(MaterialTheme.colorScheme.primary))')
    end
  end
end

# `checked` is the "Initial checked state" — a SEED, not an override. Letting
# it win pinned `selected = true` on a radio a group was driving, and the radio
# never switched again. The declared precedence (SSoT Radio.checked) is
# `bound selectedValue > literal selectedValue > checked` and names no group
# term: `group` picks WHICH key holds the selection, so it is not a rival to
# the seed. What stops the pinning is the unset-group guard, and it guards the
# grouped and lone arms alike — 51-C, mirroring the dynamic path (KotlinJsonUI
# f3bdd90 DynamicRadioComponent#itemIsSelected).
RSpec.describe KjuiTools::Compose::Components::RadioComponent do
  def selected_for(json)
    described_class.send(:radio_selected_expr, json, 'selectedRadiogroup', 'target')
  end

  it 'seeds a grouped radio until the group has chosen' do
    expect(selected_for('group' => 'g', 'checked' => true))
      .to eq('data.selectedRadiogroup == "target" || data.selectedRadiogroup.isEmpty()')
  end

  it 'lets selectedValue win over checked' do
    expect(selected_for('selectedValue' => 'Beta', 'checked' => true)).to eq('"Beta" == "target"')
  end

  it 'compares against the bound selectedValue when it is a binding' do
    expect(selected_for('selectedValue' => '@{sel}')).to eq('data.sel == "target"')
  end

  it 'honours checked on a lone radio with no group and no selectedValue' do
    expect(selected_for('checked' => true))
      .to eq('data.selectedRadiogroup == "target" || data.selectedRadiogroup.isEmpty()')
    expect(selected_for('checked' => '@{on}'))
      .to eq('data.selectedRadiogroup == "target" || ((data.on ?: false) && data.selectedRadiogroup.isEmpty())')
  end

  # A statically-off seed contributes nothing, and `.isEmpty()` on a non-null
  # String default is the codegen's "the group has not chosen" — `== null`
  # would be a compiler-warned always-false against the generated property.
  it 'adds nothing for a seed that is statically off' do
    expect(selected_for('checked' => false)).to eq('data.selectedRadiogroup == "target"')
  end

  it 'compares against value when declared, falling back to the id' do
    expect(selected_for('value' => 'optionB')).to eq('data.selectedRadiogroup == "optionB"')
    expect(selected_for({})).to eq('data.selectedRadiogroup == "target"')
  end

  # Every shape `items` is declared in draws, and what it draws type-checks —
  # a static selection (seeded), a bound one, and a bound list (forEach).
  # rel/v1.8.121 at 2f654ab3 raised NameError on all three: the body was
  # extracted from its caller (static seeding, 46b7d599) while the caller
  # gained `options` / `bound_items` (f5411c11), and the two merged without a
  # conflict. Stubs, types only: "well-typed Kotlin", not "valid Compose".
  describe 'the three shapes of items' do
    shapes = [
      { 'type' => 'Radio', 'items' => %w[a b], 'selectedValue' => 'a', 'text' => 'T', 'fontColor' => '#FF0000' },
      { 'type' => 'Radio', 'items' => %w[a b], 'selectedValue' => '@{sel}', 'margins' => [1, 2, 3, 4] },
      { 'type' => 'Radio', 'items' => '@{list}', 'selectedValue' => '@{sel}' }
    ]

    it 'each draws its options and writes the selection on a tap' do
      static, bound, list = shapes.map { |n| described_class.generate(n, 0, Set.new) }
      expect(static).to include('var seeded by remember { mutableStateOf("a") }', 'seeded = "b"', 'selected = seeded == "b"')
      expect(bound).to include('viewModel.updateData(mapOf("sel" to "b"))', 'selected = data.sel == "b"')
      expect(list).to include('data.list.forEach { item ->', 'viewModel.updateData(mapOf("sel" to item))')
    end

    it 'compiles' do
      emitted = shapes.each_with_index.map do |node, i|
        "fun shape#{i}(data: Data, viewModel: ViewModel) {\n#{described_class.generate(node, 0, Set.new)}\n}"
      end.join("\n\n")
      expect(<<~KOTLIN).to compile_as_kotlin
        interface Modifier { companion object : Modifier }
        class Dp
        val Int.dp: Dp get() = Dp()
        fun Modifier.padding(top: Dp = Dp(), end: Dp = Dp(), bottom: Dp = Dp(), start: Dp = Dp()): Modifier = this
        fun Modifier.fillMaxWidth(): Modifier = this
        fun Modifier.clickable(enabled: Boolean = true, onClick: () -> Unit): Modifier = this
        fun Modifier.width(width: Dp): Modifier = this
        fun Modifier.height(height: Dp): Modifier = this
        class Color(val argb: Int = 0) { companion object { val Black = Color() } }
        object android { object graphics { object Color { fun parseColor(hex: String): Int = 0 } } }
        interface Alignment { interface Vertical; companion object { val CenterVertically: Vertical = object : Vertical {} } }
        fun Column(modifier: Modifier = Modifier, content: () -> Unit) {}
        fun Row(verticalAlignment: Alignment.Vertical? = null, modifier: Modifier = Modifier, content: () -> Unit) {}
        class RadioButtonColors
        object RadioButtonDefaults { fun colors(selectedColor: Color = Color(), unselectedColor: Color = Color()) = RadioButtonColors() }
        fun RadioButton(selected: Boolean, onClick: () -> Unit, enabled: Boolean = true, colors: RadioButtonColors = RadioButtonColors()) {}
        class ColorScheme { val primary = Color() }
        object MaterialTheme { val colorScheme = ColorScheme() }
        fun jsonUITintOr(fallback: Color): Color = fallback
        fun Spacer(modifier: Modifier) {}
        fun Text(text: String, color: Color = Color()) {}
        class MutableState<T>(var value: T)
        operator fun <T> MutableState<T>.getValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>): T = value
        operator fun <T> MutableState<T>.setValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>, v: T) { value = v }
        fun <T> remember(calculation: () -> T): T = calculation()
        fun <T> mutableStateOf(value: T) = MutableState(value)
        class Data(val sel: String = "", val list: List<String> = emptyList())
        class ViewModel { fun updateData(values: Map<String, Any?>) {} }
        #{emitted}
      KOTLIN
    end
  end

  # fontSize is declared on Radio; the options of an `items` group drew the
  # colour only — the single radio's label reads both (label_font_args).
  describe 'the options of an items group take fontSize' do
    it 'draws each option label with the declared size and colour' do
      code = described_class.generate({ 'type' => 'Radio', 'id' => 'r', 'items' => %w[a b],
                                        'fontSize' => 18, 'fontColor' => '#FF0000' }, 0, Set.new)
      expect(code.scan(/Text\("[ab]", color = [^\n]*fontSize = 18\.sp\)/).size).to eq(2)
      bare = described_class.generate({ 'type' => 'Radio', 'id' => 'r', 'items' => %w[a] }, 0, Set.new)
      expect(bare).to include('Text("a", color = Color.Black)')
    end
  end
end
