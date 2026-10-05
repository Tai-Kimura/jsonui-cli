# frozen_string_literal: true

require_relative '../../spec_helper'
require 'compose/components/text_component'

# attribute_semantics lineHeightMultipleBase / lineSpacingBetween (2026-10-05
# user rulings): lineHeightMultiple and lineSpacing start from L, one line of
# a Label that declares no lineHeight — KotlinJsonUI's LabelLineHeight
# resolves it (the declared fontSize x 1.3, or the theme's line height), the
# same object the dynamic face calls. lineHeightMultiple makes every line
# m x L; lineSpacing goes between lines only. Both used to start from the
# font size with 14 for none: three lines at 1.8 drew 76.5 where L gives
# 129.6, and lineSpacing 16 drew 90 where between-lines gives 104.
RSpec.describe 'kjui codegen: a Label line height starts from one undeclared line' do
  let(:required_imports) { Set.new }

  def label(attrs)
    KjuiTools::Compose::Components::TextComponent.counter = 0
    KjuiTools::Compose::Components::TextComponent.generate({ 'type' => 'Label', 'text' => 'a' }.merge(attrs), 0, required_imports)
  end

  it 'multiplies L, not the font size (no fontSize: the theme decides L)' do
    out = label('lineHeightMultiple' => 1.8)
    expect(out).to include('lineHeight = LabelLineHeight.multiple(null, 1.8f, LocalTextStyle.current)')
    expect(out).not_to include('25.2')
    expect(required_imports).to include(:label_line_height, :local_text_style)
    expect(out).to include('// Requires KotlinJsonUI >= 2.43.5 (LabelLineHeight, lineSpacingBetween)')
  end

  it 'passes a declared fontSize so L is that size x 1.3' do
    expect(label('lineHeightMultiple' => 1.5, 'fontSize' => 14))
      .to include('LabelLineHeight.multiple(14f, 1.5f, LocalTextStyle.current)')
  end

  it 'adds lineSpacing to L and takes it back after the last line' do
    out = label('lineSpacing' => 16)
    expect(out).to include('lineHeight = LabelLineHeight.spaced(null, 16f, LocalTextStyle.current)')
    expect(out).to include('.lineSpacingBetween(16f)')
    expect(required_imports).to include(:line_spacing_between)
  end

  it 'lets lineHeightMultiple win over lineSpacing, with no between-lines cut' do
    out = label('lineHeightMultiple' => 1.8, 'lineSpacing' => 16)
    expect(out).to include('LabelLineHeight.multiple(')
    expect(out).not_to include('.lineSpacingBetween(')
  end

  it 'carries a bound lineSpacing into both the style and the modifier' do
    out = label('lineSpacing' => '@{gap}')
    expect(out).to include('LabelLineHeight.spaced(null, (data.gap?.toFloat() ?: 0.0f), LocalTextStyle.current)')
    expect(out).to include('.lineSpacingBetween((data.gap?.toFloat() ?: 0.0f))')
  end

  it 'leaves a label with none of the three on the theme line height' do
    out = label({})
    expect(out).not_to include('lineHeight =')
    expect(out).not_to include('.lineSpacingBetween(')
  end

  # The hint's own fontSize is a declared size: one line of it is size x 1.3,
  # as the dynamic face draws (fontSize 12: 16), not the theme's 24.
  it "gives a hint's fontSize its own undeclared line while the hint shows" do
    KjuiTools::Compose::Components::TextComponent.counter = 0
    out = KjuiTools::Compose::Components::TextComponent.generate(
      { 'type' => 'Label', 'hint' => 'h', 'hintAttributes' => { 'fontSize' => 12 } }, 0, required_imports
    )
    expect(out).to match(/lineHeight = if \(\w+\.isEmpty\(\)\) 15\.6\.sp else LocalTextStyle\.current\.lineHeight/)
  end

  # The emitted style and modifier type-check against the library's API. The
  # stubs transcribe KotlinJsonUI's LabelLineHeight.kt signatures (Float?,
  # Float, TextStyle -> TextUnit; Modifier.lineSpacingBetween(Float)) — a
  # transcription, not a compile against the library itself, which the
  # conformance host's codegen build covers.
  it 'emits Kotlin that type-checks against LabelLineHeight' do
    shapes = [
      label('lineHeightMultiple' => 1.8),
      label('lineHeightMultiple' => '@{m}', 'fontSize' => 14),
      label('lineSpacing' => '@{gap}'),
      KjuiTools::Compose::Components::TextComponent.tap { |t| t.counter = 0 }.generate(
        { 'type' => 'Label', 'hint' => 'h', 'hintAttributes' => { 'fontSize' => 12, 'lineHeightMultiple' => 1.5 },
          'lineSpacing' => 4 }, 0, required_imports
      )
    ]
    body = shapes.each_with_index.map do |out, i|
      style = out[/style = (LocalTextStyle\.current\.copy\(.*\)),$/, 1] or raise "no style in shape #{i}:\n#{out}"
      spacing = out[/(\.lineSpacingBetween\(.*\))$/, 1]
      vars = out.scan(/\b(labelText\d+)\.isEmpty\(\)/).flatten.uniq.map { |v| "val #{v} = \"\"" }
      "fun shape#{i}(data: Data) {\n  #{vars.join("\n  ")}\n  val style = #{style}\n  val modifier: Modifier = Modifier#{spacing}\n}"
    end.join("\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      class TextUnit(val value: Float)
      val Double.sp: TextUnit get() = TextUnit(toFloat())
      class TextStyle(val lineHeight: TextUnit = TextUnit(0f)) {
          fun copy(lineHeight: TextUnit = this.lineHeight): TextStyle = TextStyle(lineHeight)
      }
      object LocalTextStyle { val current: TextStyle = TextStyle() }
      object LabelLineHeight {
          fun multiple(fontSize: Float?, multiple: Float, style: TextStyle): TextUnit = TextUnit(0f)
          fun spaced(fontSize: Float?, spacing: Float, style: TextStyle): TextUnit = TextUnit(0f)
      }
      interface Modifier { companion object : Modifier }
      fun Modifier.lineSpacingBetween(spacing: Float): Modifier = this
      class Data(val m: Double? = null, val gap: Int? = null)
      #{body}
    KOTLIN
  end
end
