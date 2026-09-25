# frozen_string_literal: true

require 'set'
require 'compose/components/button_component'
require 'compose/components/toggle_component'
require 'compose/components/text_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'
require_relative '../support/kotlin_compiler'

# An empty or blank tap handler names no method (shared/core/
# tap_accessibility.rb `handler?`), so it is no handler: the components that
# take an onClick parameter get their empty one, and a partial range gets no
# link. They used to emit `data.?.invoke()` / `data.   ?.invoke()`, which is
# not Kotlin (ticket kjui-empty-onclick-emits-invalid-kotlin). The
# `.clickable` path is covered per vector in spec/core/tap_accessibility_role_spec.rb.
RSpec.describe 'kjui empty and blank tap handlers' do
  EMPTY_TAP_HANDLERS = [
    { 'onClick' => '' }, { 'onClick' => '   ' }, { 'onClick' => '@{}' }, { 'onClick' => '@{ }' },
    { 'onclick' => '' }, { 'onclick' => '   ' }, { 'onclick' => [] }, { 'onclick' => ['', ' '] }
  ].freeze
  # A call on a blank name: `data.?.invoke()`, `data.   ?.invoke()`, `data.@{}?.invoke()`.
  EMPTY_TAP_CALL = /data\.(\s*|@\{\s*\})\?/.freeze

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
    KjuiTools::Compose::Components::ButtonComponent.reset_counter!
    KjuiTools::Compose::Components::TextComponent.counter = 0
  end

  EMPTY_TAP_HANDLERS.each do |handler|
    context handler.inspect do
      it 'gives a Button its empty onClick' do
        result = KjuiTools::Compose::Components::ButtonComponent
                 .generate({ 'type' => 'Button', 'text' => 'Go' }.merge(handler), 0, Set.new)
        expect(result).to include('onClick = { }')
        expect(result).not_to match(EMPTY_TAP_CALL)
      end

      it 'gives a Toggle its empty onCheckedChange' do
        result = KjuiTools::Compose::Components::ToggleComponent
                 .generate({ 'type' => 'Toggle' }.merge(handler), 0, Set.new)
        expect(result).to include('onCheckedChange = { },')
        expect(result).not_to match(EMPTY_TAP_CALL)
      end

      it 'gives a partial range no click' do
        range = { 'range' => [0, 4], 'fontColor' => '#FF0000' }.merge(handler)
        result = KjuiTools::Compose::Components::TextComponent
                 .generate({ 'type' => 'Label', 'text' => 'Open terms', 'partialAttributes' => [range] }, 0, Set.new)
        expect(result).to include('onClick = null')
        expect(result).not_to match(EMPTY_TAP_CALL)
      end
    end
  end

  # The controls: a real handler still reaches each, and a blank element of an
  # array is dropped from the calls instead of being called.
  it 'calls only the named elements of an onclick array' do
    handler = { 'onclick' => ['', 'onOpen', '  '] }
    button = KjuiTools::Compose::Components::ButtonComponent
             .generate({ 'type' => 'Button', 'text' => 'Go' }.merge(handler), 0, Set.new)
    expect(button).to include('onClick = { data.onOpen?.invoke() }')
    clickable = KjuiTools::Compose::Helpers::ModifierBuilder
                .build_clickable({ 'type' => 'Label', 'id' => 't', 'text' => 'x' }.merge(handler), Set.new)
    expect(clickable.grep(/\.clickable/)).to eq(['.clickable { data.onOpen?.invoke() }'])
  end

  # The handler lambdas every path emits — the part this ticket changes — for
  # each blank variant and the controls, type-checked in one kotlinc run
  # against the data members they call. `data.?.invoke()` is what failed.
  it 'emits handler lambdas that compile' do
    variants = EMPTY_TAP_HANDLERS + [{ 'onClick' => '@{onGo}' }, { 'onclick' => ['', 'onGo'] }]
    emitted = variants.flat_map do |handler|
      [
        KjuiTools::Compose::Components::ButtonComponent.generate({ 'type' => 'Button', 'text' => 'Go' }.merge(handler), 0, Set.new),
        KjuiTools::Compose::Components::ToggleComponent.generate({ 'type' => 'Toggle' }.merge(handler), 0, Set.new),
        KjuiTools::Compose::Components::TextComponent.generate(
          { 'type' => 'Label', 'text' => 'Open terms', 'partialAttributes' => [{ 'range' => [0, 4] }.merge(handler)] }, 0, Set.new
        )
      ]
    end.join("\n")
    lambdas = emitted.scan(/^\s*(?:onClick|onCheckedChange) = (\{.*\}),?$/).flatten
    # A blank range gets `onClick = null`, not a lambda: 2 per blank variant,
    # 3 per control, and one null per blank variant.
    expect(lambdas.size).to eq((EMPTY_TAP_HANDLERS.size * 2) + 6)
    expect(emitted.scan(/^\s*onClick = null,?$/).size).to eq(EMPTY_TAP_HANDLERS.size)
    names = lambdas.join.scan(/data\.(\w+)\?\.invoke\(\)/).flatten.uniq
    expect(names).to eq(['onGo'])
    expect(<<~KOTLIN).to compile_as_kotlin
      class Data(#{names.map { |n| "val #{n}: (() -> Unit)? = null" }.join(', ')})
      fun handlers(data: Data): List<() -> Unit> = listOf(
      #{lambdas.map { |l| "    #{l}" }.join(",\n")}
      )
    KOTLIN
  end

  it 'still wires a real handler on each path' do
    button = KjuiTools::Compose::Components::ButtonComponent
             .generate({ 'type' => 'Button', 'text' => 'Go', 'onClick' => '@{onGo}' }, 0, Set.new)
    toggle = KjuiTools::Compose::Components::ToggleComponent
             .generate({ 'type' => 'Toggle', 'onclick' => 'onFlip' }, 0, Set.new)
    label = KjuiTools::Compose::Components::TextComponent
            .generate({ 'type' => 'Label', 'text' => 'Open terms',
                        'partialAttributes' => [{ 'range' => [0, 4], 'onclick' => 'onTerms' }] }, 0, Set.new)
    expect(button).to include('onClick = { data.onGo?.invoke() }')
    expect(toggle).to include('onCheckedChange = { data.onFlip?.invoke() },')
    expect(label).to include('onClick = { data.onTerms?.invoke() }')
  end
end
