# frozen_string_literal: true

require 'set'
require 'compose/components/text_component'
require_relative '../../support/kotlin_compiler'
require_relative '../../support/compose_stub_universe'

# Under autoShrink / minimumScaleFactor the line follows the glyphs TextAutoSize shrinks (ticket
# kjui-autoshrink-keeps-the-line-height): Compose shrinks the font size only, so a line height in sp stayed and a
# bounded Label fitted fewer shrunk lines than web. Every path passes its line height through LabelLineHeight.shrinking.
RSpec.describe KjuiTools::Compose::Components::TextComponent do
  let(:base) { { 'type' => 'Label', 'id' => 't', 'width' => 200, 'height' => 40, 'text' => 'Sample text' } }
  paths = { 'plain' => {}, 'partial' => { 'partialAttributes' => [{ 'range' => [0, 3], 'fontColor' => '#FF0000' }] },
            'linkable' => { 'linkable' => true } }
  shrinks = { 'autoShrink' => { 'autoShrink' => true }, 'minimumScaleFactor' => { 'minimumScaleFactor' => 0.25 } }
  lines = { 'the theme line' => {}, 'fontSize' => { 'fontSize' => 14 }, 'lineHeightMultiple' => { 'lineHeightMultiple' => 1.5 },
            'lineSpacing' => { 'lineSpacing' => 4 } }

  def gen(json)
    described_class.counter = 0
    imports = Set.new
    [described_class.generate(json, 0, imports, nil), imports]
  end

  paths.each do |path, path_attrs|
    shrinks.each do |shrink, shrink_attrs|
      lines.each do |line, line_attrs|
        it "the #{path} Label under #{shrink} with #{line} passes its line height through LabelLineHeight.shrinking" do
          code, imports = gen(base.merge(path_attrs, shrink_attrs, line_attrs))
          expect(code).to match(/lineHeight = LabelLineHeight\.shrinking\(.+, LocalTextStyle\.current\.fontSize\)/)
          expect(code.scan('lineHeight = LabelLineHeight.shrinking(').length).to eq(1)
          expect(imports).to include(:label_line_height)
        end
      end
    end

    it "the #{path} Label that does not shrink keeps its line height as it was" do
      code, = gen(base.merge(path_attrs, 'lineHeightMultiple' => 1.5))
      expect(code).not_to include('LabelLineHeight.shrinking(')
    end
  end

  # The emits above, handed to a compiler (KotlinJsonUI 2.64.0's LabelLineHeight.shrinking and PartialAttributesText
  # signatures). Types only — a green says well-typed against these stubs.
  it 'emits Kotlin that compiles' do
    emits = paths.flat_map do |_, path_attrs|
      shrinks.flat_map { |_, shrink_attrs| lines.map { |_, line_attrs| gen(base.merge(path_attrs, shrink_attrs, line_attrs)).first } }
    end
    all = emits.join("\n")
    stubs = ComposeStubUniverse.common_stages(all)
    body = emits.each_with_index.map { |e, i| "fun emitted#{i}(data: ShrinkData) {\n#{e}\n}" }.join("\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{stubs}
      class ShrinkData
      class TextAlign { companion object { val Center = TextAlign(); val Start = TextAlign(); val End = TextAlign(); val Unspecified = TextAlign() } }
      interface TextAutoSize { companion object { fun StepBased(minFontSize: TextUnit, maxFontSize: TextUnit): TextAutoSize = object : TextAutoSize {} } }
      class TextLayoutResult
      fun Modifier.lineSpacingBetween(spacing: Float): Modifier = this
      fun Modifier.wrapContentHeight(align: Alignment = Alignment.CenterVertically): Modifier = this
      class Density
      object LocalDensity { val current = Density() }
      object LabelLineHeight {
          fun multiple(fontSize: Float?, multiple: Float, style: TextStyle, density: Density): TextUnit = TextUnit()
          fun spaced(fontSize: Float?, spacing: Float, style: TextStyle, density: Density): TextUnit = TextUnit()
          fun shrinking(lineHeight: TextUnit, fontSize: TextUnit, fallbackFontSize: TextUnit): TextUnit = lineHeight
      }
      val TextStyle.fontFamily: FontFamily? get() = null
      val TextStyle.fontWeight: FontWeight? get() = null
      val TextStyle.fontStyle: FontStyle? get() = null
      fun TextStyle.copy(color: Color = this.color, fontFamily: FontFamily? = null, fontWeight: FontWeight? = null,
                         fontSize: TextUnit = this.fontSize, letterSpacing: Any? = null, fontStyle: FontStyle? = null,
                         lineHeight: TextUnit? = null, textAlign: TextAlign? = null): TextStyle = this
      fun Text(text: String, color: Color = Color(), fontFamily: FontFamily? = null, fontWeight: FontWeight? = null,
               fontSize: TextUnit = TextUnit(), letterSpacing: Any? = null, fontStyle: FontStyle? = null,
               style: TextStyle? = null, modifier: Modifier = Modifier, textAlign: TextAlign? = null,
               autoSize: TextAutoSize?, maxLines: Int = Int.MAX_VALUE, overflow: Any? = null) {}
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
