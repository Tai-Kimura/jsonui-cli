# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'json'
require 'set'

# A partialAttributes range's handler in both declared spellings: `onClick`
# (a binding) is canonical, `onclick` (a selector) its alias. Every path reads
# both, the canonical one first (TapAccessibility.range_handler; 4f ruling,
# jsonui-cli 1.9.0). kjui read both and took `onclick` first.
RSpec.describe 'kjui: a range\'s handler in either spelling' do
  emit = lambda do |ranges|
    KjuiTools::Compose::Components::TextComponent.reset_counter!
    node = { 'type' => 'Label', 'id' => 'l', 'text' => 'Terms and more', 'partialAttributes' => ranges }
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, node, 0)
  end
  call = ->(code) { code[/onClick = (\{[^}]*\}|null)/, 1] }

  {
    'onClick (canonical)' => [{ 'range' => 'Terms', 'onClick' => '@{onTerms}' }, '{ data.onTerms?.invoke() }'],
    'onclick (alias)' => [{ 'range' => 'Terms', 'onclick' => 'onTerms' }, '{ data.onTerms?.invoke() }'],
    'both: the canonical one' => [{ 'range' => 'Terms', 'onClick' => '@{onTerms}', 'onclick' => 'onOther' }, '{ data.onTerms?.invoke() }'],
    'onClick not a binding: the alias' => [{ 'range' => 'Terms', 'onClick' => 'onTerms', 'onclick' => 'onOther' }, '{ data.onOther?.invoke() }'],
    'onclick array' => [{ 'range' => 'Terms', 'onclick' => %w[onA onB] }, '{ data.onA?.invoke(); data.onB?.invoke() }'],
    'none' => [{ 'range' => 'Terms' }, 'null']
  }.each do |name, (range, want)|
    it(name) { expect(call.call(emit.call([range]))).to eq(want) }
  end
end
