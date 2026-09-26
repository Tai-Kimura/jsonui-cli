# frozen_string_literal: true

require 'compose/compose_builder'
require 'compose/helpers/modifier_builder'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# A Label's links — a partialAttributes range with a handler, and a link
# `linkable` detects — stop with `userInteractionEnabled`: `false` on the
# Label or on a view around it stops them, a binding gates them (the tap rule,
# shared/core/tap_accessibility.rb; 4f ruling, jsonui-cli 1.9.0).
#
# kjui passes that to the library's PartialAttributesText as `linksEnabled`,
# because the pointer blocker is not enough: each link is a semantics node of
# its own, and TalkBack's double tap called its action through the blocker —
# the range's handler ran, the URL opened (measured, API 35 emulator;
# KotlinJsonUI LinkSpanUnderOuterClickableProbe / LabelLinksStopWith-
# UserInteractionTest). The linkable branch took no blocker at all, so a
# touch on a detected link went through `false`.
#
# canTap and enabled are the Label's own tap and state; they do not reach
# its links here, and the arms pin that they are not read.
RSpec.describe 'kjui: a Label\'s links stop with userInteractionEnabled' do
  tap = JsonUIShared::TapAccessibility
  counters = %w[TextComponent TextFieldComponent TextViewComponent ButtonComponent ConstraintLayoutComponent]
  emit = lambda do |node|
    counters.each { |c| KjuiTools::Compose::Components.const_get(c).reset_counter! }
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    tap.annotate!(comp)
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, comp, 0)
  end

  linkable = ->(more = {}) { { 'type' => 'Label', 'id' => 'l', 'text' => 'See https://example.com', 'linkable' => true }.merge(more) }
  ranged = lambda do |more = {}|
    { 'type' => 'Label', 'id' => 'l', 'text' => 'Terms and Privacy',
      'partialAttributes' => [{ 'range' => 'Terms', 'onClick' => '@{onTerms}' }] }.merge(more)
  end
  inside = ->(flag, child) { { 'type' => 'View', 'id' => 'p', 'userInteractionEnabled' => flag, 'child' => [child] } }
  links = ->(code) { code[/linksEnabled = (.+),$/, 1] }

  { 'linkable' => linkable, 'partialAttributes' => ranged }.each do |shape, label|
    describe "a #{shape} Label" do
      it 'passes no linksEnabled with no flag (the control: the links are operable)' do
        expect(links.call(emit.call(label.call))).to be_nil
      end

      it 'stops its links under its own false, and under a View\'s false' do
        expect(links.call(emit.call(label.call('userInteractionEnabled' => false)))).to eq('false')
        expect(links.call(emit.call(inside.call(false, label.call)))).to eq('false')
      end

      it 'gates its links on its own binding, on a View\'s, and on both, outermost first' do
        expect(links.call(emit.call(label.call('userInteractionEnabled' => '@{u}')))).to eq('(data.u ?: false)')
        expect(links.call(emit.call(inside.call('@{a}', label.call)))).to eq('(data.a ?: false)')
        expect(links.call(emit.call(inside.call('@{a}', label.call('userInteractionEnabled' => '@{u}')))))
          .to eq('(data.a ?: false) && (data.u ?: false)')
      end

      it 'reads neither canTap nor enabled for its links' do
        %w[canTap enabled].each do |key|
          expect(links.call(emit.call(label.call(key => false)))).to be_nil, key
          expect(links.call(emit.call(label.call(key => '@{x}')))).to be_nil, key
        end
      end

      it 'takes the pointer blocker for its own flag' do
        expect(emit.call(label.call('userInteractionEnabled' => false))).to include('PointerEventPass.Initial')
        expect(emit.call(label.call('userInteractionEnabled' => '@{u}'))).to include('.pointerInput((data.u ?: false))')
        expect(emit.call(label.call)).not_to include('PointerEventPass.Initial')
      end
    end
  end

  # What the arms above read, handed to a compiler: PartialAttributesText and
  # PartialAttribute.fromJsonRange mirror the library's signatures
  # (KotlinJsonUI library/.../components/PartialAttributesText.kt), so
  # `linksEnabled` in a place the library does not take it does not
  # type-check. Types only — a green says well-typed against these stubs.
  it 'emits Kotlin that compiles' do
    trees = [
      linkable.call('userInteractionEnabled' => false), linkable.call('userInteractionEnabled' => '@{u}'),
      inside.call('@{a}', linkable.call('userInteractionEnabled' => '@{u}')),
      ranged.call('userInteractionEnabled' => false), ranged.call('userInteractionEnabled' => '@{u}', 'onClick' => '@{onTap}'),
      inside.call(false, ranged.call), linkable.call, ranged.call
    ]
    emits = trees.map { |t| emit.call(t) }
    expect(emits.count { |e| e.include?('linksEnabled = ') }).to eq(6)
    all = emits.join("\n")
    stubs = ComposeStubUniverse.common_stages(all)
    body = emits.each_with_index.map { |e, i| "fun emitted#{i}(data: LinkData) {\n#{e}\n}" }.join("\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{stubs}
      class LinkData(val onTerms: (() -> Unit)? = null, val onTap: (() -> Unit)? = null,
                     val u: Boolean? = null, val a: Boolean? = null)
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
