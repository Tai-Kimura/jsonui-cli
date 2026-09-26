# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/layout_path'
require 'core/tap_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# A handler's viewId is the node's id, else its drawn type with the first
# letter lowercased and its position in the layout (JsonUIShared::LayoutPath
# .view_id — switch_0_1, selectBox_0_3). kjui passed a kind word (`switch`,
# `selectbox`, …) or nothing, so two id-less controls handed their handlers the
# same viewId. And SelectBox.onValueChange by the handler's type (ruling ③).
RSpec.describe 'kjui codegen: viewId by position' do
  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  after { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::TapAccessibility.annotate!(comp)
    JsonUIShared::LayoutPath.stamp!(comp)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, comp, 0).to_s
  end
  typed = ->(names) { names.to_h { |n| [n, { 'class' => '((String) -> Unit)?' }] } }

  # Each handler that is passed a viewId, on an id-less node at 0_1 (after a
  # Label at 0_0). The `(String)` type makes every path pass the viewId.
  handlers = {
    'Switch onValueChange' => [{ 'type' => 'Switch', 'onValueChange' => '@{h}' }, 'switch_0_1'],
    'Toggle onValueChange' => [{ 'type' => 'Toggle', 'onValueChange' => '@{h}' }, 'switch_0_1'],
    'CheckBox onValueChange' => [{ 'type' => 'CheckBox', 'onValueChange' => '@{h}' }, 'checkBox_0_1'],
    'Slider onValueChange' => [{ 'type' => 'Slider', 'onValueChange' => '@{h}' }, 'slider_0_1'],
    'Segment onValueChange' => [{ 'type' => 'Segment', 'items' => %w[a b], 'onValueChange' => '@{h}' }, 'segment_0_1'],
    'Radio options onValueChange' => [{ 'type' => 'Radio', 'options' => %w[a b], 'bind' => '@{sel}', 'onValueChange' => '@{h}' }, 'radio_0_1'],
    'TextField onTextChange' => [{ 'type' => 'TextField', 'text' => '@{t}', 'onTextChange' => '@{h}' }, 'textField_0_1'],
    'TextView onTextChange' => [{ 'type' => 'TextView', 'text' => '@{t}', 'onTextChange' => '@{h}' }, 'textView_0_1'],
    'Button onClick' => [{ 'type' => 'Button', 'text' => 't', 'onClick' => '@{h}' }, 'button_0_1'],
    'View onClick' => [{ 'type' => 'View', 'onClick' => '@{h}' }, 'view_0_1'],
    'Label onLongPress' => [{ 'type' => 'Label', 'text' => 'x', 'onLongPress' => '@{h}' }, 'label_0_1'],
    'Image onClick' => [{ 'type' => 'Image', 'srcName' => 'ic_a', 'onClick' => '@{h}' }, 'image_0_1']
  }

  handlers.each do |label, (node, expected)|
    it "#{label} passes #{expected}, and an explicit id wins" do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = typed.call(%w[h])
      layout = ->(n) { { 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'first' }, n] } }
      expect(emit.call(layout.call(node))).to include("data.h?.invoke(\"#{expected}\"")
      expect(emit.call(layout.call(node.merge('id' => 'mine')))).to include('data.h?.invoke("mine"')
    end
  end

  it 'is the shared rule (LayoutPath.view_id) on every node it names' do
    vectors = File.expand_path('../../../shared/core/layout_path_vectors.json', __dir__)
    skip 'shared vectors not present in this layout' unless File.exist?(vectors)

    cases = JSON.parse(File.read(vectors))['view_id_cases']
    expect(cases.size).to be >= 5
    cases.each do |c|
      tree = JSON.parse(JSON.generate(c['layout']))
      JsonUIShared::LayoutPath.stamp!(tree)
      got = {}
      walk = lambda do |n|
        next unless n.is_a?(Hash)

        got[n['_label']] = KjuiTools::Compose::Helpers::ModifierBuilder.view_id(n) if n['_label']
        JsonUIShared::LayoutPath.children(n).each { |child| walk.call(child) }
      end
      walk.call(tree)
      expect(got.slice(*c['expect'].keys)).to eq(c['expect']), c['name']
    end
  end

  it 'no emitter names a viewId by a kind word' do
    lib = File.expand_path('../../lib/compose', __dir__)
    hits = Dir.glob(File.join(lib, '**', '*.rb')).flat_map do |f|
      File.readlines(f).each_with_index.select { |line, _| line =~ /json_data\['id'\] \|\| '[a-z]+'/ }
          .map { |line, i| "#{File.basename(f)}:#{i + 1}: #{line.strip}" }
    end
    expect(hits).to be_empty
  end

  it 'two id-less TextViews in one scope, two id-less Embeds: distinct names, and the file compiles' do
    code = emit.call('type' => 'View', 'child' => [{ 'type' => 'TextView', 'text' => '@{a}' },
                                                   { 'type' => 'TextView', 'text' => '@{b}' }])
    expect(code).to include('val textFieldState_textView_0_0', 'val textFieldState_textView_0_1')
    embeds = emit.call('type' => 'View', 'child' => [{ 'type' => 'Embed', 'screen' => 'x' }, { 'type' => 'Embed', 'screen' => 'x' }])
    expect(embeds).to include('embedId = "embed_0_0"', 'embedId = "embed_0_1"')
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(code)}
      class Data(val a: String = "", val b: String = "")
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      fun screen(data: Data, viewModel: ViewModel) {
      #{code}
      }
    KOTLIN
  end

  # --- SelectBox.onValueChange by the handler's type (ruling ③) --------------
  # A lone `(String)` receives the selected item, whatever the binding; it was
  # handed the viewId and the index (two arguments, one parameter). `(String,
  # Int)` is the viewId and the index; `(String, String)` the viewId and the
  # item.
  types = { '(String)' => '(String) -> Unit', '(String, Int)' => '(String, Int) -> Unit',
            '(String, String)' => '(String, String) -> Unit', '(Int)' => '(Int) -> Unit' }
  bindings = { 'an item binding' => { 'selectedItem' => '@{item}' }, 'an index binding' => { 'selectedIndex' => '@{idx}' },
               'no binding' => {} }
  calls = { '(String)' => 'data.pick?.invoke(newValue)', '(String, Int)' => 'data.pick?.invoke("sb", index)',
            '(String, String)' => 'data.pick?.invoke("sb", newValue)', '(Int)' => 'data.pick?.invoke(index)' }

  it 'SelectBox calls each handler type with its arguments under each binding, and all twelve compile' do
    functions = types.flat_map do |label, klass|
      bindings.map do |binding_label, binding|
        KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = { 'pick' => { 'class' => "(#{klass})?" } }
        code = KjuiTools::Compose::Components::SelectBoxComponent.generate(
          { 'type' => 'SelectBox', 'id' => 'sb', 'items' => %w[a b], 'onValueChange' => '@{pick}' }.merge(binding), 0, Set.new
        )
        expect(code).to include(calls[label]), "#{label} × #{binding_label}\n#{code}"
        # the index without an index binding is the item's first index
        if label.include?('Int') && !binding_label.include?('index')
          expect(code).to include('val index = listOf("a", "b").indexOf(newValue)')
        end
        [label, binding_label, klass, code]
      end
    end
    functions.group_by { |f| f[2] }.each_with_index do |(klass, group), t|
      body = group.each_with_index.map { |(_, _, _, code), i| "fun sb#{t}_#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}" }.join("\n\n")
      expect(<<~KOTLIN).to compile_as_kotlin
        #{ComposeStubUniverse.common_stages(body)}
        class Data(val item: String = "", val idx: Int = 0, val pick: (#{klass})? = null)
        class ViewModel { fun updateData(values: Map<String, Any?>) {} }
        #{body}
      KOTLIN
    end
  end

  # A date has no index: a date SelectBox declared `(String, Int)` or `(Int)`
  # is not called, and a block comment names it; `(String)` and `(String,
  # String)` are called with the date.
  it 'a date SelectBox calls the date handlers and names the index ones, and all four compile' do
    bodies = { '(String)' => 'data.pick?.invoke(newValue)', '(String, String)' => 'data.pick?.invoke("sb", newValue)',
               '(String, Int)' => nil, '(Int)' => nil }.map.with_index do |(label, call), i|
      klass = types[label]
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = { 'pick' => { 'class' => "(#{klass})?" } }
      code = KjuiTools::Compose::Components::SelectBoxComponent.generate(
        { 'type' => 'SelectBox', 'id' => 'sb', 'selectItemType' => 'Date', 'selectedDate' => '@{day}', 'onValueChange' => '@{pick}' },
        0, Set.new
      )
      if call
        expect(code).to include(call), code
      else
        expect(code).not_to include('data.pick?.invoke'), code
        expect(code).to include('/* ERROR: SelectBox.onValueChange pick is not called: a date SelectBox has no index: declare onValueChange as (String) or (String, String) */')
      end
      "class DateData#{i}(val day: String = \"\", val pick: (#{klass})? = null)\n" \
        "fun date#{i}(data: DateData#{i}, viewModel: ViewModel) {\n#{code}\n}"
    end.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(bodies)}
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{bodies}
    KOTLIN
  end
end
