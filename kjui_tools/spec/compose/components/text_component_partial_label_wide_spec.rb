# frozen_string_literal: true

require 'set'
require 'compose/components/text_component'

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

  EXPECTED = {
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
  }.freeze

  EXPECTED.each do |name, (extra, fragment)|
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
end
