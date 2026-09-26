# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'core/attribute_validator'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# What the layout writes as a binding reaches the Kotlin as an expression, and
# what the emit writes around it compiles
# (docs/bugs/kjui-dynamic-components-that-skip-the-common-modifiers.md, the
# follow-ups after C). Each block is one family, measured over every emitter
# first; the counts before are in the ticket.
RSpec.describe 'kjui codegen: bound values reach the Kotlin' do
  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  after { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::TapAccessibility.annotate!(comp)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, comp, 0).to_s
  end

  # Every type the codegen draws, with what opens its main branch.
  drawn = {
    'TextField' => { 'text' => '@{t}' }, 'TextView' => { 'text' => '@{t}' }, 'Button' => { 'text' => 't' },
    'Label' => { 'text' => 't' }, 'View' => {}, 'Image' => { 'srcName' => 'ic_a' },
    'NetworkImage' => { 'url' => 'https://example.invalid/x.png' }, 'CircleImage' => { 'srcName' => 'ic_a' },
    'Switch' => {}, 'CheckBox' => {}, 'Radio' => { 'text' => 'r' }, 'Slider' => {}, 'Progress' => {}, 'Indicator' => {},
    'SelectBox' => { 'items' => %w[a b] }, 'Segment' => { 'items' => %w[a b] },
    'ScrollView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'SafeAreaView' => { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'Collection' => { 'items' => '@{rows}', 'cellClasses' => ['ItemCell'] },
    'WebView' => { 'url' => 'about:blank' }, 'Web' => { 'url' => 'about:blank' },
    'TabView' => { 'tabs' => [{ 'title' => 'a' }] }, 'Embed' => { 'screen' => 'm' },
    'GradientView' => { 'gradient' => ['#FF0000', '#0000FF'] }, 'Blur' => {}, 'IconLabel' => { 'text' => 't' }
  }

  # --- every key an emitter reads, bound ------------------------------------
  # The keys are read off the emitters (json_data['x'] in lib/compose), so a
  # key a new branch reads is in without a list to edit. Each is bound on every
  # drawn type — TextField, TextView and Button also with a declared width and
  # with margins, which open their other branches — with the companions that
  # make the branch read it. What is left is named below, and classified: none
  # of them is a number.
  lib = File.expand_path('../../lib/compose', __dir__)
  keys = Dir.glob(File.join(lib, '**', '*.rb')).flat_map { |f| File.read(f).scan(/json_data\['([A-Za-z]+)'\]/).flatten }.uniq.sort -
         %w[type id child children include style data sections cell header footer tabs items options screen params events
            platform responsive shared_data partialAttributes gradient layout orientation]
  companion = {
    'minuteInterval' => { 'selectItemType' => 'Date', 'datePickerMode' => 'time' },
    'maxHeight' => { 'flexible' => true }, 'minHeight' => { 'flexible' => true },
    'hintFontSize' => { 'hint' => 'h' }, 'hintLineHeightMultiple' => { 'hint' => 'h' }
  }
  branches = { 'TextField' => [{ 'width' => 200 }, { 'margins' => [1, 1, 1, 1] }],
               'TextView' => [{ 'width' => 200 }, { 'margins' => [1, 1, 1, 1] }],
               'Button' => [{ 'width' => 200 }, { 'margins' => [1, 1, 1, 1] }] }
  # Not numbers — ids, handler names declared `string`, a group name, enum
  # lists, class names, a user agent, a comment's flag. A binding is not their
  # declared form; kept here by name so a new leak is red and a fixed one says
  # so.
  not_numbers = {
    'TextField' => %w[fieldId nextFocus nextFocusId onBeginEditing onBlur onEndEditing onFocus],
    'TextView' => %w[hideOnFocused], 'Radio' => %w[group],
    'WebView' => %w[userAgent], 'Web' => %w[userAgent]
  }
  # (Collection's cellClasses / headerClasses / footerClasses left this list
  # when the class-list reader on rel stopped raising on a string;
  # SafeAreaView's edges / safeAreaInsetPositions when the words became what
  # they reserve (SafeAreaEdges) — a binding is no declared word and reserves
  # nothing, where it was written into the emitted edge list.)

  it 'no bound number reaches the Kotlin as the layout spelled it, nor raises' do
    expect(keys.size).to be > 200
    left = Hash.new { |h, k| h[k] = [] }
    drawn.each do |type, extra|
      ([{}] + (branches[type] || [])).each do |variant|
        keys.each do |key|
          node = { 'type' => type }.merge(extra, variant, companion[key] || {}, key => "@{v_#{key}}")
          code = begin
            emit.call(node)
          rescue StandardError => e
            "RAISE #{e.class}"
          end
          left[type] << key if code.start_with?('RAISE') || code.include?("@{v_#{key}}")
        end
      end
    end
    expect(left.transform_values { |k| k.uniq.sort }.reject { |_, v| v.empty? }).to eq(not_numbers)
  end

  # The bound forms, each on the branch that writes it, type-check. Data's
  # numbers are nullable where the emit must say what an unset one is.
  bound_nodes = {
    'Indicator strokeWidth' => { 'type' => 'Indicator', 'strokeWidth' => '@{n}' },
    'SelectBox minuteInterval' => { 'type' => 'SelectBox', 'selectItemType' => 'Date', 'datePickerMode' => 'time',
                                    'minuteInterval' => '@{i}' },
    'SelectBox fontSize' => { 'type' => 'SelectBox', 'items' => %w[a b], 'fontSize' => '@{i}' },
    'TextField hintFontSize' => { 'type' => 'TextField', 'text' => '@{t}', 'hint' => 'h', 'hintFontSize' => '@{n}',
                                  'hintLineHeightMultiple' => 1.5 },
    'TextField textPaddingLeft' => { 'type' => 'TextField', 'text' => '@{t}', 'textPaddingLeft' => '@{n}' },
    'TextField fieldPadding' => { 'type' => 'TextField', 'text' => '@{t}', 'fieldPadding' => '@{n}' },
    'TextField paddings' => { 'type' => 'TextField', 'text' => '@{t}', 'paddings' => ['@{n}', '@{n}'] },
    'TextView height' => { 'type' => 'TextView', 'text' => '@{t}', 'width' => 200, 'height' => '@{n}' },
    'TextView flexible' => { 'type' => 'TextView', 'text' => '@{t}', 'flexible' => true, 'minHeight' => '@{n}',
                             'maxHeight' => '@{n}', 'margins' => [1, 1, 1, 1] },
    'TextView maxLines and hint' => { 'type' => 'TextView', 'text' => '@{t}', 'maxLines' => '@{i}', 'hint' => 'h',
                                      'hintFontSize' => '@{n}', 'hintLineHeightMultiple' => '@{n}' },
    'Button paddings' => { 'type' => 'Button', 'text' => 't', 'paddingTop' => '@{n}', 'paddingLeft' => 8 },
    'Button padding' => { 'type' => 'Button', 'text' => 't', 'padding' => '@{n}' },
    'Slider step' => { 'type' => 'Slider', 'step' => '@{f}', 'maximumValue' => 10 },
    'Slider bound range' => { 'type' => 'Slider', 'step' => 1, 'minimumValue' => '@{f}', 'maximumValue' => '@{f}' },
    'Slider bound value' => { 'type' => 'Slider', 'value' => '@{f}' },
    'Image size' => { 'type' => 'Image', 'srcName' => 'ic_a', 'size' => '@{n}' },
    'NetworkImage size' => { 'type' => 'NetworkImage', 'url' => 'https://example.invalid/x.png', 'size' => '@{n}' },
    'CircleImage size' => { 'type' => 'CircleImage', 'srcName' => 'ic_a', 'size' => '@{n}' },
    'Blur blurRadius' => { 'type' => 'Blur', 'blurRadius' => '@{n}' },
    'IconLabel iconMargin' => { 'type' => 'IconLabel', 'text' => 't', 'iconMargin' => '@{n}' },
    'Collection spacing' => { 'type' => 'Collection', 'items' => '@{rows}', 'lineSpacing' => '@{n}',
                              'columnSpacing' => '@{n}', 'insetHorizontal' => '@{n}' },
    'Embed params' => { 'type' => 'Embed', 'screen' => 'other', 'params' => '@{p}' }
  }

  it 'every bound number is an expression the compiler takes' do
    functions = bound_nodes.each_with_index.map do |(label, node), i|
      code = emit.call(node)
      expect(code).not_to include('@{'), "#{label}\n#{code}"
      "// #{label}\nfun bound#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}"
    end.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(functions)}
      class Data(val n: Int? = null, val i: Int = 1, val f: Float? = null, val t: String = "",
                 val p: Map<String, Any> = emptyMap(), val rows: List<Any> = emptyList())
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{functions}
    KOTLIN
  end

  it 'a static value is written as before (a bound form does not leak into the static path)' do
    expect(emit.call('type' => 'Indicator', 'strokeWidth' => 3)).to include('strokeWidth = 3.dp')
    expect(emit.call('type' => 'TextView', 'text' => '@{t}', 'maxLines' => 4)).to include('maxLines = 4,')
    expect(emit.call('type' => 'Button', 'text' => 't', 'paddingTop' => 4, 'paddingLeft' => 8))
      .to include('contentPadding = PaddingValues(start = 8.dp, top = 4.dp)')
    expect(emit.call('type' => 'Slider', 'step' => 0.25)).to include('steps = 3,')
  end

  # --- a control's `enabled` -------------------------------------------------
  # `enabled = data.on` was the bare value: a nullable binding did not
  # type-check against the Boolean parameter. It is enabled_expression, as on
  # every other stage.
  enabled_nodes = {
    'Switch' => { 'type' => 'Switch', 'isOn' => '@{b}' }, 'Switch with a label' => { 'type' => 'Switch', 'isOn' => '@{b}', 'label' => 'L' },
    'Slider' => { 'type' => 'Slider', 'value' => '@{f}' },
    'Segment' => { 'type' => 'Segment', 'items' => %w[a b], 'selectedIndex' => '@{i}' },
    'Button' => { 'type' => 'Button', 'text' => 't' }, 'TextField' => { 'type' => 'TextField', 'text' => '@{t}' }
  }

  it 'a nullable `enabled` binding compiles on every control that takes it as an argument' do
    functions = enabled_nodes.each_with_index.map do |(label, node), i|
      code = emit.call(node.merge('enabled' => '@{on}'))
      expect(code).to include('enabled = (data.on ?: false)'), "#{label}\n#{code}"
      expect(code).not_to match(/enabled = data\.on\b/)
      "// #{label}\nfun enabled#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}"
    end.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(functions)}
      class Data(val on: Boolean? = null, val b: Boolean = false, val f: Float = 0f, val i: Int = 0, val t: String = "")
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{functions}
    KOTLIN
    expect(emit.call(enabled_nodes['Switch'].merge('enabled' => false))).to include('enabled = false')
  end

  # --- CheckBox's handler argument -------------------------------------------
  it 'a CheckBox handler takes the new value by the lambda\'s own name for it' do
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = { 'changed' => { 'class' => '((String, Boolean) -> Unit)' } }
    bound = emit.call('type' => 'CheckBox', 'isOn' => '@{on}', 'onValueChange' => '@{changed}')
    seeded = emit.call('type' => 'CheckBox', 'onValueChange' => '@{changed}')
    labelled = emit.call('type' => 'CheckBox', 'isOn' => '@{on}', 'label' => 'L', 'onValueChange' => '@{changed}')
    expect(bound).to include('{ newValue -> viewModel.updateData(mapOf("on" to newValue)); data.changed?.invoke("checkBox_0", newValue) }')
    expect(labelled).to include('data.changed?.invoke("checkBox_0", newValue)')
    expect(seeded).to include('{ seeded = it; data.changed?.invoke("checkBox_0", it) }')
    functions = [bound, seeded, labelled].each_with_index.map { |c, i| "fun cb#{i}(data: Data, viewModel: ViewModel) {\n#{c}\n}" }.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(functions)}
      class Data(val on: Boolean = false, val changed: ((String, Boolean) -> Unit)? = null)
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{functions}
    KOTLIN
  end

  # --- a handler that names nothing ------------------------------------------
  # `{ // ERROR: … },` — the line comment ran to the end of the line and took
  # the lambda's `}` and the argument's `,` with it. A block comment cannot,
  # and the layout's text in it cannot close it or break the line.
  error_nodes = {
    'Switch' => { 'type' => 'Switch', 'onValueChange' => "flip */ now\nnext()" },
    'CheckBox' => { 'type' => 'CheckBox', 'onValueChange' => 'flip' },
    'CheckBox with icons' => { 'type' => 'CheckBox', 'src' => 'ic_a', 'selectedIcon' => 'ic_b', 'onValueChange' => 'flip' },
    'Slider' => { 'type' => 'Slider', 'onValueChange' => 'slide' },
    'SelectBox' => { 'type' => 'SelectBox', 'items' => %w[a], 'onValueChange' => 'pick' },
    'Button' => { 'type' => 'Button', 'text' => 't', 'onClick' => 'press' }
  }

  it 'a handler that names nothing is a block comment in an empty lambda, and the file compiles' do
    functions = error_nodes.each_with_index.map do |(label, node), i|
      code = emit.call(node)
      expect(code).not_to include('{ // ERROR'), "#{label}\n#{code}"
      expect(code).to match(%r{= \{ /\* ERROR: [^\n]*\*/ \}}), "#{label}\n#{code}"
      "// #{label}\nfun err#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}"
    end.join("\n\n")
    expect(functions).not_to include("\nnext()")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(functions)}
      class Data
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{functions}
    KOTLIN
  end

  it 'a comment line the emit writes carries the layout\'s text on one line' do
    code = emit.call('type' => 'Embed', 'screen' => "other\nfun injected() {}")
    expect(code).not_to include("\nfun injected")
    expect(code).to include('// Embed: other fun injected() {}')
  end

  # --- Label: the standard order, on every branch -----------------------------
  stage_attrs = { 'id' => 'n', 'margins' => [7, 7, 7, 7], 'width' => 111, 'height' => 53, 'offsetX' => 3, 'offsetY' => 3,
                  'alpha' => 0.5, 'shadow' => '#000000|0|2|0.5|4', 'background' => '#3366CC', 'paddings' => [5, 5, 5, 5] }
  order = ['.testTag("n")', '.padding(top = 7.dp', '.requiredWidth(111.dp)', '.absoluteOffset(x = 3.dp', '.alpha(0.5f)',
           '.dropShadow(', '.background(Color(', '.padding(top = 5.dp']
  label_branches = {
    'Label' => { 'type' => 'Label', 'text' => 'hello' },
    'Label with partial attributes' => { 'type' => 'Label', 'text' => 'hello',
                                         'partialAttributes' => [{ 'range' => [0, 2], 'fontColor' => '#FF0000' }] },
    'Label linkable' => { 'type' => 'Label', 'text' => 'see https://example.invalid', 'linkable' => true }
  }

  label_branches.each do |label, node|
    it "#{label}: testTag → margins → size → offset → alpha → shadow → background → padding" do
      code = emit.call(node.merge(stage_attrs))
      at = order.map { |marker| code.index(marker) }
      expect(at).to all(be_a(Integer)), "#{order.zip(at).inspect}\n#{code}"
      expect(at).to eq(at.sort), "#{order.zip(at).inspect}\n#{code}"
    end
  end

  it 'the Text emitter no build reached is gone' do
    source = File.read(File.join(lib, 'components', 'text_component.rb'))
    expect(source).not_to include('def self.generate_with_partial_attributes(')
    expect(source).not_to include('def self.build_text_style(')
  end

  # --- `bind` beside the control's own value ---------------------------------
  # SSoT common.bind: "an alternative spelling to each component's own value
  # attribute, which takes precedence when both are set". The own attribute is
  # the value — shown and written, a static one as the seed of the control's
  # own state — and `bind` is the value only when there is none. It showed a
  # static isOn while the operation wrote `bind`, so the control never moved.
  own_first = {
    'Switch' => [{ 'type' => 'Switch', 'isOn' => true, 'bind' => '@{on}' }, 'onCheckedChange = { seeded = it }'],
    'CheckBox' => [{ 'type' => 'CheckBox', 'checked' => true, 'bind' => '@{on}' }, 'onCheckedChange = { seeded = it }'],
    'Slider' => [{ 'type' => 'Slider', 'value' => 0.5, 'bind' => '@{level}' }, 'onValueChange = { seeded = it }']
  }

  own_first.each do |label, (node, written)|
    it "#{label}: its own static value is shown and written, and `bind` is not" do
      code = emit.call(node)
      expect(code).to include('var seeded by remember', written)
      expect(code).not_to include('updateData')
    end
  end

  it '`bind` alone is the value, shown and written' do
    expect(emit.call('type' => 'Switch', 'bind' => '@{on}')).to include('checked = data.on,', 'mapOf("on" to newValue)')
    expect(emit.call('type' => 'CheckBox', 'bind' => '@{on}')).to include('checked = data.on,', 'mapOf("on" to newValue)')
    expect(emit.call('type' => 'Slider', 'bind' => '@{level}')).to include('mapOf("level" to newValue.toDouble())')
  end

  it 'a CheckBox bound through `value` writes it' do
    expect(emit.call('type' => 'CheckBox', 'value' => '@{v}')).to include('checked = data.v,', 'mapOf("v" to newValue)')
  end
end
