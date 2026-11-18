# frozen_string_literal: true

require 'set'
require 'compose/components/text_component'
require_relative '../../support/kotlin_compiler'
require_relative '../../support/compose_stub_universe'

# A Label's own attributes on a partial / linkable Label (ticket kjui-label-underline-dropped-with-partial-attributes):
# the two branches drew only the font, its size, colour and alignment and dropped the rest without a word, while
# iOS and the web applied them. Each is emitted as the plain Label emits it, only when declared.
RSpec.describe KjuiTools::Compose::Components::TextComponent do
  let(:base) { { 'type' => 'Label', 'id' => 'probe', 'text' => 'hello world', 'fontSize' => 14 } }
  let(:partial) { { 'partialAttributes' => [{ 'range' => 'world', 'fontColor' => '#FF0000' }] } }
  let(:linkable) { { 'linkable' => true } }

  def gen(json)
    described_class.counter = 0
    described_class.generate(json, 0, Set.new, nil)
  end

  label_wide_cases = {
    'underline' => [{ 'underline' => true }, 'textDecoration = TextDecoration.Underline'],
    'strikethrough' => [{ 'strikethrough' => true }, 'textDecoration = TextDecoration.LineThrough'],
    'both lines' => [{ 'underline' => true, 'strikethrough' => true },
                     'textDecoration = TextDecoration.combine(listOf(TextDecoration.Underline, TextDecoration.LineThrough))'],
    'a coloured underline' => [{ 'underline' => { 'color' => '#00FF00' } }, '.styledTextLines(lineState_text1, underline = StyledLine('],
    'lines' => [{ 'lines' => 2 }, "maxLines = 2,\n"],
    'lineBreakMode' => [{ 'lineBreakMode' => 'Clip' }, 'overflow = TextOverflow.Clip'],
    'lineHeightMultiple' => [{ 'lineHeightMultiple' => 1.5 }, 'LabelLineHeight.multiple('],
    'lineSpacing' => [{ 'lineSpacing' => 6 }, '.lineSpacingBetween(6'],
    'textShadow' => [{ 'textShadow' => { 'color' => '#000000', 'radius' => 2, 'offset' => [1, 1] } }, 'shadow = Shadow('],
    'autoShrink' => [{ 'autoShrink' => true }, 'autoSize = TextAutoSize.StepBased('],
    'minimumScaleFactor' => [{ 'minimumScaleFactor' => 0.5 }, 'autoSize = TextAutoSize.StepBased('],
    'disabledFontColor' => [{ 'enabled' => false, 'disabledFontColor' => '#999999' }, 'color = Color(android.graphics.Color.parseColor("#999999"))'],
    'highlightColor' => [{ 'selected' => '@{isOn}', 'highlightColor' => '#00FF00' }, 'color = if (data.isOn) Color(android.graphics.Color.parseColor("#00FF00"))'],
    'highlightAttributes' => [{ 'selected' => true, 'highlightAttributes' => { 'fontSize' => 20 } }, 'size = 20.sp'],
    'hint' => [{ 'text' => '@{name}', 'hint' => 'type a name' }, '.isEmpty()) "type a name" else labelText'],
    'the hint bag\'s lineHeightMultiple' => [{ 'text' => '@{name}', 'hint' => 'type a name', 'hintAttributes' => { 'lineHeightMultiple' => 1.5 } },
                                          '.isEmpty()) jsonUILineHeight(jsonUIFontSize(resolved_text1.size ?: TextUnit.Unspecified), lineHeight = LabelLineHeight.multiple(14f, 1.5f'],
  }.freeze

  label_wide_cases.each do |name, (extra, fragment)|
    it "the partial Label applies #{name} as the plain one does" do
      plain = gen(base.merge(extra))
      expect(gen(base.merge(extra).merge(partial))).to include(fragment)
      expect(plain).to include(fragment.sub("maxLines = 2,\n", 'maxLines = 2')) unless name == 'hint' || name.start_with?('highlight', 'disabled')
    end

    it "the linkable Label applies #{name}" do
      expect(gen(base.merge(extra).merge(linkable))).to include(fragment)
    end
  end

  it 'the partial Label puts edgeInset inside its background, before its padding' do
    code = gen(base.merge('edgeInset' => 8, 'background' => '#EEEEEE').merge(partial))
    expect(code).to include('.padding(8.dp)')
    expect(code.index('.background(')).to be < code.index('.padding(8.dp)')
  end

  it 'names the KotlinJsonUI release when it passes the line rules, and only then' do
    with = gen(base.merge('lines' => 2).merge(partial))
    expect(with).to include("// Requires KotlinJsonUI >= #{described_class::PARTIAL_LINE_RULES_MIN_LIBRARY_VERSION}")
    expect(gen(base.merge('underline' => true).merge(partial))).not_to include('Requires KotlinJsonUI >= 2.64.0')
  end

  it 'leaves a partial Label that declares none of them as it was' do
    code = gen(base.merge('fontColor' => '#123456', 'textAlign' => 'Center').merge(partial))
    %w[textDecoration maxLines overflow autoSize onTextLayout shadow lineSpacingBetween styledTextLines labelText].each do |word|
      expect(code).not_to include(word)
    end
    expect(code).to include('color = Color(android.graphics.Color.parseColor("#123456"))', 'textAlign = TextAlign.Center')
  end

  it 'keeps the screen shape that underlined the whole text through a range: the Label underline adds no second line' do
    # the range's own underline over the whole text, and now the Label's too: one decoration, as iOS draws it
    code = gen(base.merge('underline' => true,
                          'partialAttributes' => [{ 'range' => 'hello world', 'underline' => { 'lineStyle' => 'Single' } }]))
    expect(code).to include('textDecoration = TextDecoration.Underline', "underline = true,\n")
    expect(code.scan('TextDecoration.Underline').length).to eq(1)
  end

  # What the arms above read, handed to a compiler: PartialAttributesText and PartialAttribute.fromJsonRange mirror
  # the library's signatures (KotlinJsonUI 2.64.0, library/.../components/PartialAttributesText.kt), so an argument
  # the library does not take does not type-check. textShadow is left out: the stub universe's Shadow is the
  # modifier's (a Dp radius), not the text's. Types only — a green says well-typed against these stubs.
  it 'emits Kotlin that compiles' do
    emits = label_wide_cases.reject { |name, _| name == 'textShadow' }.flat_map do |_, (extra, _)|
      [gen(base.merge(extra).merge(partial)), gen(base.merge(extra).merge(linkable))]
    end
    emits << gen(base.merge('edgeInset' => 8, 'background' => '#EEEEEE').merge(partial))
    all = emits.join("\n")
    stubs = ComposeStubUniverse.common_stages(all)
    body = emits.each_with_index.map { |e, i| "fun emitted#{i}(data: WideData) {\n#{e}\n}" }.join("\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{stubs}
      class WideData(val isOn: Boolean = false, val name: String = "")
      class TextDecoration { companion object {
          val Underline = TextDecoration(); val LineThrough = TextDecoration()
          fun combine(decorations: List<TextDecoration>) = TextDecoration()
      } }
      class TextAlign { companion object { val Center = TextAlign(); val Start = TextAlign(); val End = TextAlign(); val Unspecified = TextAlign() } }
      interface TextAutoSize { companion object { fun StepBased(minFontSize: TextUnit, maxFontSize: TextUnit): TextAutoSize = object : TextAutoSize {} } }
      class TextLayoutResult
      class StyledLine(val color: Color, val style: String)
      class StyledLineState { var layout: TextLayoutResult? = null }
      fun Modifier.styledTextLines(state: StyledLineState, underline: StyledLine? = null, strikethrough: StyledLine? = null): Modifier = this
      fun Modifier.lineSpacingBetween(spacing: Float): Modifier = this
      class Density
      object LocalDensity { val current = Density() }
      object LabelLineHeight {
          fun multiple(fontSize: Float?, multiple: Float, style: TextStyle, density: Density): TextUnit = TextUnit()
          fun spaced(fontSize: Float?, spacing: Float, style: TextStyle, density: Density): TextUnit = TextUnit()
          fun shrinking(lineHeight: TextUnit, ceiling: TextUnit): TextUnit = lineHeight
      }
      val TextStyle.fontFamily: FontFamily? get() = null
      val TextStyle.fontWeight: FontWeight? get() = null
      val TextStyle.fontStyle: FontStyle? get() = null
      fun TextStyle.copy(color: Color = this.color, fontFamily: FontFamily? = null, fontWeight: FontWeight? = null,
                         fontSize: TextUnit = this.fontSize, letterSpacing: Any? = null, fontStyle: FontStyle? = null,
                         lineHeight: Any? = null, textAlign: TextAlign? = null, textDecoration: TextDecoration? = null): TextStyle = this
      class PartialAttribute {
          companion object {
              fun fromJsonRange(range: Any, text: String, fontColor: String? = null, fontSize: Int? = null,
                                fontWeight: String? = null, background: String? = null, underline: Boolean = false,
                                strikethrough: Boolean = false, onClick: (() -> Unit)? = null): PartialAttribute? = null
          }
      }
      fun PartialAttributesText(text: String, partialAttributes: List<PartialAttribute> = emptyList(),
                                linkable: Boolean = false, modifier: Modifier = Modifier,
                                style: TextStyle = TextStyle(), linksEnabled: Boolean = true,
                                fontScaling: Boolean? = null, maxFontScale: Float? = null,
                                maxLines: Int = Int.MAX_VALUE, overflow: TextOverflow = TextOverflow.Clip,
                                autoSize: TextAutoSize? = null, onTextLayout: ((TextLayoutResult) -> Unit)? = null) {}
      #{body}
    KOTLIN
  end
end
