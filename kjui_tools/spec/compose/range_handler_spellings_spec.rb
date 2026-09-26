# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# A partialAttributes range's handler in both declared spellings: `onClick`
# (a binding) is canonical, `onclick` (a selector) its alias. Every path reads
# both, the canonical one first (TapAccessibility.range_handler; 4f ruling,
# jsonui-cli 1.9.0). The normalizer folds `onclick` into `onClick` (its declared
# alias), so onClick may hold a method name as well as a binding. kjui read both and took `onclick` first.
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
    'onClick holding a name (the alias folded)' => [{ 'range' => 'Terms', 'onClick' => 'onTerms', 'onclick' => 'onOther' }, '{ data.onTerms?.invoke() }'],
    'onclick holding a binding' => [{ 'range' => 'Terms', 'onclick' => '@{onTerms}' }, '{ data.onTerms?.invoke() }'],
    'onclick array' => [{ 'range' => 'Terms', 'onclick' => %w[onA onB] }, '{ data.onA?.invoke(); data.onB?.invoke() }'],
    'none' => [{ 'range' => 'Terms' }, 'null']
  }.each do |name, (range, want)|
    it(name) { expect(call.call(emit.call([range]))).to eq(want) }
  end

  # PartialAttribute.fromJsonRange mirrors the library's signature (its
  # onClick is `(() -> Unit)?`): each spelling's call is a lambda it takes.
  it 'emits Kotlin that compiles, each spelling' do
    emits = [[{ 'range' => 'Terms', 'onClick' => '@{onTerms}' }], [{ 'range' => 'Terms', 'onclick' => %w[onA onB] }]]
            .map { |r| emit.call(r) }
    body = emits.each_with_index.map { |e, i| "fun emitted#{i}(data: RangeData) {\n#{e}\n}" }.join("\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emits.join("\n"))}
      class RangeData(val onTerms: (() -> Unit)? = null, val onA: (() -> Unit)? = null, val onB: (() -> Unit)? = null)
      object LocalTextStyle { val current: TextStyle = TextStyle() }
      val TextStyle.fontFamily: FontFamily? get() = null
      val TextStyle.fontWeight: FontWeight? get() = null
      val TextStyle.fontStyle: FontStyle? get() = null
      fun TextStyle.copy(color: Color = this.color, fontFamily: FontFamily? = null, fontWeight: FontWeight? = null,
                         fontSize: TextUnit = this.fontSize, fontStyle: FontStyle? = null): TextStyle = this
      class PartialAttribute {
          companion object {
              fun fromJsonRange(range: Any, text: String, fontColor: String? = null, fontSize: Int? = null,
                                fontWeight: String? = null, background: String? = null, underline: Boolean = false,
                                strikethrough: Boolean = false, onClick: (() -> Unit)? = null): PartialAttribute? = null
          }
      }
      fun PartialAttributesText(text: String, partialAttributes: List<PartialAttribute> = emptyList(),
                                linkable: Boolean = false, modifier: Modifier = Modifier,
                                style: TextStyle = TextStyle(), linksEnabled: Boolean = true) {}
      #{body}
    KOTLIN
  end
end
