# frozen_string_literal: true

require 'compose/components/text_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/visibility_helper'
require 'compose/helpers/resource_resolver'
require 'compose/helpers/font_spec_helper'

RSpec.describe KjuiTools::Compose::Components::TextComponent do
  let(:required_imports) { Set.new }

  before do
    # Reset the per-emission counter so each example gets `resolved_text1` etc.
    described_class.counter = 0
  end

  describe '.generate' do
    it 'generates basic text component' do
      json_data = { 'type' => 'Text', 'text' => 'Hello World' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Text(')
      expect(result).to include('text = "Hello World"')
    end

    it 'always emits Configuration.Font.resolve(FontSpec(...)) for Text' do
      json_data = { 'type' => 'Text', 'text' => 'Hi' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to match(/val resolved_text\d+ = Configuration\.Font\.resolve\(FontSpec\(/)
      expect(required_imports).to include(:configuration)
      expect(required_imports).to include(:font_spec)
    end

    it 'generates text with font size threading into FontSpec.size' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'fontSize' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('size = 16.sp,')
      expect(result).to include('fontSize = resolved_text1.size ?: TextUnit.Unspecified')
    end

    it 'generates text with font color' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'fontColor' => '#FF0000' }
      result = described_class.generate(json_data, 0, required_imports)
      # ResourceResolver.process_color returns parseColor format
      expect(result).to include('color = ')
      expect(result).to include('#FF0000')
    end

    it 'generates text with bold font weight via fontWeight' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'fontWeight' => 'bold' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('weight = FontWeight.Bold,')
      expect(result).to include('fontWeight = resolved_text1.weight,')
    end

    it 'generates text with font attribute for bold' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'font' => 'bold' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('weight = FontWeight.Bold,')
    end

    it 'generates text with font attribute for semibold' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'font' => 'semibold' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('weight = FontWeight.SemiBold,')
    end

    it 'generates text with custom font family via font attribute' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'font' => 'Roboto-Regular' }
      result = described_class.generate(json_data, 0, required_imports)
      # FontSpec.family is the JSON family string verbatim; the Configuration provider
      # is responsible for translating it to a FontFamily.
      expect(result).to include('family = "Roboto-Regular",')
    end

    it 'generates text with weights routed through FontSpec.weight' do
      weights = {
        'thin' => 'Thin',
        'light' => 'Light',
        'medium' => 'Medium',
        'semibold' => 'SemiBold'
      }

      weights.each do |input, output|
        described_class.counter = 0
        json_data = { 'type' => 'Text', 'text' => 'Test', 'fontWeight' => input }
        result = described_class.generate(json_data, 0, Set.new)
        expect(result).to include("weight = FontWeight.#{output},")
      end
    end

    it 'generates text with underline' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'underline' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textDecoration = TextDecoration.Underline')
      expect(required_imports).to include(:text_decoration)
    end

    it 'generates text with strikethrough' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'strikethrough' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textDecoration = TextDecoration.LineThrough')
    end

    it 'generates text with combined decorations' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'underline' => true, 'strikethrough' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('TextDecoration.combine')
    end

    # `lineStyle` enumerates "None", which is the declaration's own way of
    # saying "no line". The truthy test drew one for every object face alike,
    # so the one value that means OFF behaved like the three that mean ON.
    it 'draws no underline when the object face declares lineStyle None' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'underline' => { 'lineStyle' => 'None' } }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('textDecoration')
      expect(required_imports).not_to include(:text_decoration)
    end

    it 'draws no strikethrough when the object face declares lineStyle None' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'strikethrough' => { 'lineStyle' => 'None' } }
      expect(described_class.generate(json_data, 0, required_imports)).not_to include('textDecoration')
    end

    it 'still draws for the other declared lineStyle values and for a bare object' do
      %w[Single Double Thick].each do |style|
        json_data = { 'type' => 'Text', 'text' => 'Test', 'underline' => { 'lineStyle' => style } }
        expect(described_class.generate(json_data, 0, required_imports))
          .to include('textDecoration = TextDecoration.Underline')
      end
      bare = { 'type' => 'Text', 'text' => 'Test', 'underline' => { 'color' => '#FF0000' } }
      expect(described_class.generate(bare, 0, required_imports))
        .to include('textDecoration = TextDecoration.Underline')
    end

    it 'generates text with text alignment' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'textAlign' => 'center' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.Center')
      expect(required_imports).to include(:text_align)
    end

    it 'generates text with right alignment' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'textAlign' => 'right' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.End')
    end

    # Regression: kjui-label-gravity-center-not-vertically-centered.
    # A height-filling Label with gravity:center must vertically center its
    # glyphs (textAlign only handles horizontal). iOS centers via
    # .frame(alignment: .center); Android needs wrapContentHeight(align).
    it 'vertically centers a height:matchParent Label with gravity:center' do
      json_data = {
        'type' => 'Label', 'text' => 'Guide', 'height' => 'matchParent',
        'gravity' => 'center', 'textAlign' => 'center'
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.fillMaxHeight()')
      expect(result).to include('.wrapContentHeight(align = Alignment.CenterVertically)')
      expect(result).to include('textAlign = TextAlign.Center') # horizontal still emitted
    end

    it 'vertically centers a weighted Label inside a vertical (Column) container' do
      json_data = {
        'type' => 'Label', 'text' => 'Guide', 'weight' => 1, 'gravity' => 'center'
      }
      result = described_class.generate(json_data, 0, required_imports, 'Column')
      expect(result).to include('.weight(1f)')
      expect(result).to include('.wrapContentHeight(align = Alignment.CenterVertically)')
    end

    it 'generates text with max lines' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'lines' => 2 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('maxLines = 2')
    end

    it 'generates text with unlimited lines (0)' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'lines' => 0 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('maxLines = Int.MAX_VALUE')
    end

    it 'generates text with line break mode' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'lineBreakMode' => 'tail' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('overflow = TextOverflow.Ellipsis')
    end

    it 'generates text with clip line break mode' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'lineBreakMode' => 'clip' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('overflow = TextOverflow.Clip')
    end

    it 'generates text with lineHeightMultiple' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'fontSize' => 14, 'lineHeightMultiple' => 1.5 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('style = TextStyle')
      expect(result).to include('lineHeight')
    end

    it 'generates text with edgeInset' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'edgeInset' => [10, 20, 30, 40] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.padding(top = 10.dp, end = 20.dp, bottom = 30.dp, start = 40.dp)')
    end

    it 'generates text with single value edgeInset' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'edgeInset' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.padding(16.dp)')
    end

    it 'handles centerHorizontal for text alignment' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'centerHorizontal' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.Center')
    end

    it 'returns empty string for hidden visibility' do
      allow(KjuiTools::Compose::Helpers::VisibilityHelper).to receive(:should_skip_render?).and_return(true)
      json_data = { 'type' => 'Text', 'text' => 'Test', 'visibility' => 'gone' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to eq('')
    end

    it 'generates text with minimumScaleFactor' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'minimumScaleFactor' => 0.5 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('maxLines = 1')
      expect(result).to include('overflow = TextOverflow.Ellipsis')
    end

    # Regression family: kjui-label-lines-and-linebreakmode-double-overflow-emit.
    # `lines`, `autoShrink`, `minimumScaleFactor`, and `lineBreakMode` each
    # used to append their own `overflow = ...` (and `maxLines = ...` for
    # auto-shrink paths) independently. Combinations produced duplicate
    # named args — invalid Kotlin. Verify each combination emits each
    # named arg exactly once and that `lineBreakMode` takes precedence
    # over the implicit Ellipsis default.
    context 'overflow / maxLines deduplication' do
      it 'emits a single overflow when lines + lineBreakMode: tail are combined' do
        json_data = {
          'type' => 'Text', 'text' => 'Test',
          'lines' => 1, 'lineBreakMode' => 'Tail'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result.scan('overflow =').size).to eq(1)
        expect(result).to include('overflow = TextOverflow.Ellipsis')
        expect(result.scan('maxLines =').size).to eq(1)
        expect(result).to include('maxLines = 1')
      end

      it 'lineBreakMode: clip overrides the implicit Ellipsis from lines' do
        json_data = {
          'type' => 'Text', 'text' => 'Test',
          'lines' => 2, 'lineBreakMode' => 'clip'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result.scan('overflow =').size).to eq(1)
        expect(result).to include('overflow = TextOverflow.Clip')
        expect(result).not_to include('overflow = TextOverflow.Ellipsis')
      end

      it 'lineBreakMode: word resolves to Ellipsis (still emitted once)' do
        json_data = {
          'type' => 'Text', 'text' => 'Test',
          'lines' => 3, 'lineBreakMode' => 'word'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result.scan('overflow =').size).to eq(1)
        expect(result).to include('overflow = TextOverflow.Ellipsis')
        expect(result).to include('maxLines = 3')
      end

      it 'unmapped lineBreakMode (head) leaves the lines-default Ellipsis intact, once' do
        json_data = {
          'type' => 'Text', 'text' => 'Test',
          'lines' => 1, 'lineBreakMode' => 'head'
        }
        result = described_class.generate(json_data, 0, required_imports)
        # head/middle/char are silent-skip in the lineBreakMode case;
        # the lines-default Ellipsis survives.
        expect(result.scan('overflow =').size).to eq(1)
        expect(result).to include('overflow = TextOverflow.Ellipsis')
      end

      it 'emits a single maxLines / overflow when lines + autoShrink are combined' do
        json_data = {
          'type' => 'Text', 'text' => 'Test', 'fontSize' => 14,
          'lines' => 2, 'autoShrink' => true
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result.scan('maxLines =').size).to eq(1)
        # Explicit `lines` wins over autoShrink's implicit `maxLines = 1`
        expect(result).to include('maxLines = 2')
        expect(result.scan('overflow =').size).to eq(1)
        expect(result).to include('overflow = TextOverflow.Ellipsis')
        # autoSize emit is still present
        expect(result).to include('TextAutoSize.StepBased')
      end

      it 'emits a single maxLines / overflow when lines + minimumScaleFactor are combined' do
        json_data = {
          'type' => 'Text', 'text' => 'Test', 'fontSize' => 14,
          'lines' => 4, 'minimumScaleFactor' => 0.5
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result.scan('maxLines =').size).to eq(1)
        expect(result).to include('maxLines = 4')
        expect(result.scan('overflow =').size).to eq(1)
      end

      it 'emits autoSize + single maxLines/overflow when autoShrink + lineBreakMode: clip combine (lineBreakMode wins)' do
        json_data = {
          'type' => 'Text', 'text' => 'Test', 'fontSize' => 14,
          'autoShrink' => true, 'lineBreakMode' => 'clip'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result.scan('overflow =').size).to eq(1)
        expect(result).to include('overflow = TextOverflow.Clip')
        expect(result.scan('maxLines =').size).to eq(1)
        expect(result).to include('maxLines = 1')
      end

      it 'lines: 0 still emits Int.MAX_VALUE with no overflow (preserved semantics)' do
        json_data = { 'type' => 'Text', 'text' => 'Test', 'lines' => 0 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('maxLines = Int.MAX_VALUE')
        expect(result).not_to include('overflow =')
      end

      it 'lineBreakMode alone (no lines) emits only overflow, no maxLines' do
        json_data = { 'type' => 'Text', 'text' => 'Test', 'lineBreakMode' => 'tail' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('overflow = TextOverflow.Ellipsis')
        expect(result).not_to include('maxLines =')
      end
    end
  end

  describe '.generate_with_partial_attributes_for_linkable' do
    it 'generates PartialAttributesText for linkable text' do
      json_data = { 'type' => 'Text', 'text' => 'Test link', 'linkable' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('PartialAttributesText(')
      expect(result).to include('linkable = true')
      expect(required_imports).to include(:partial_attributes_text)
    end

    it 'emits a Configuration.Font.resolve(FontSpec(...)) block before the linkable component' do
      json_data = { 'type' => 'Text', 'text' => 'Link', 'linkable' => true, 'fontSize' => 14 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to match(/val resolved_text\d+ = Configuration\.Font\.resolve\(FontSpec\(/)
      expect(result).to include('fontSize = (resolved_text1.size ?: TextUnit.Unspecified)')
    end

    # kjui-partialattributes-label-missing-testtag: a linkable Label with an id
    # must carry the shared id testTag so it is findable by By.res(id).
    it 'emits testTag(id) on a linkable Label' do
      json_data = { 'type' => 'Label', 'id' => 'link_label', 'text' => 'Terms', 'linkable' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('PartialAttributesText(')
      expect(result).to include('.testTag("link_label")')
      expect(result).to include('.semantics { testTagsAsResourceId = true }')
    end
  end

  describe '.generate_with_partial_attributes_component' do
    it 'generates PartialAttributesText with partialAttributes' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'fontColor' => '#FF0000', 'fontSize' => 20 }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('PartialAttributesText(')
      expect(result).to include('partialAttributes = listOf(')
      expect(result).to include('PartialAttribute.fromJsonRange')
    end

    it 'emits a Configuration.Font.resolve(FontSpec(...)) block before the component' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello',
        'partialAttributes' => [{ 'range' => [0, 5], 'fontColor' => '#FF0000' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to match(/val resolved_text\d+ = Configuration\.Font\.resolve\(FontSpec\(/)
    end

    it 'handles string range' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => 'Hello', 'fontWeight' => 'bold' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('range = "Hello"')
    end

    it 'handles onclick in partial attributes' do
      json_data = {
        'type' => 'Text',
        'text' => 'Click here',
        'partialAttributes' => [
          { 'range' => [0, 5], 'onclick' => 'handleClick' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onClick = { data.handleClick?.invoke() }')
    end

    # kjui-partialattributes-label-missing-testtag: parity with every other
    # component + iOS accessibilityIdentifier.
    it 'emits testTag(id) on a partialAttributes Label so it is findable by id' do
      json_data = {
        'type' => 'Label', 'id' => 'sign_up_label', 'text' => 'Apply for membership',
        'partialAttributes' => [{ 'range' => [0, 5], 'fontColor' => '#FF0000' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('PartialAttributesText(')
      expect(result).to include('.testTag("sign_up_label")')
      expect(result).to include('.semantics { testTagsAsResourceId = true }')
    end

    it 'omits testTag when a partialAttributes Label has no id' do
      json_data = {
        'type' => 'Label', 'text' => 'No id',
        'partialAttributes' => [{ 'range' => [0, 2], 'fontColor' => '#FF0000' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('.testTag(')
    end
  end

  describe 'additional text attributes' do
    it 'generates text with binding expression' do
      json_data = { 'type' => 'Text', 'text' => '@{title}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.title')
    end

    it 'generates text with font bold' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'font' => 'bold' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('weight = FontWeight.Bold,')
    end

    it 'handles Label type same as Text' do
      json_data = { 'type' => 'Label', 'text' => 'Label Text' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Text(')
      expect(result).to include('Label Text')
    end
  end

  describe 'modifiers' do
    it 'applies width modifier' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'width' => 100 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Modifier')
    end

    it 'applies height modifier' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'height' => 50 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Modifier')
    end

    it 'applies background modifier' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'background' => '#FF0000' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.background')
    end

    it 'applies width with match_parent' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'width' => 'match_parent' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Modifier')
    end
  end

  describe 'additional partial attributes' do
    it 'generates text with background in partial attributes' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'background' => '#FFFF00' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('background = "#FFFF00"')
    end

    it 'generates text with underline in partial attributes' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'underline' => true }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('underline = true')
    end

    it 'generates text with strikethrough in partial attributes' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'strikethrough' => true }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('strikethrough = true')
    end

    # Inside `partialAttributes` the SSoT declares `underline` as an OBJECT and
    # nothing else, so the only spec-conformant spelling used to reach the
    # source as a Ruby Hash — `underline = {"lineStyle"=>"Single"}` is not
    # Kotlin, and every generated file carrying one failed to compile.
    it 'folds the declared object face of a partial underline to the API flag' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5],
            'underline' => { 'lineStyle' => 'Single', 'color' => '#FF0000', 'lineOffset' => 2 } }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('underline = true')
      expect(result).not_to include('=>')
    end

    it 'draws no line for a partial underline declared lineStyle None' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'underline' => { 'lineStyle' => 'None' } }
        ]
      }
      expect(described_class.generate(json_data, 0, required_imports)).not_to include('underline =')
    end

    it 'handles multiple partial attributes' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'fontColor' => '#FF0000' },
          { 'range' => [6, 11], 'fontColor' => '#00FF00' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('#FF0000')
      expect(result).to include('#00FF00')
    end

    it 'handles partial attributes without onclick' do
      json_data = {
        'type' => 'Text',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'fontColor' => '#FF0000' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onClick = null')
    end
  end

  describe 'linkable text styles' do
    it 'generates linkable text with fontSize' do
      json_data = { 'type' => 'Text', 'text' => 'Link', 'linkable' => true, 'fontSize' => 14 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('size = 14.sp,')
    end

    it 'generates linkable text with fontColor' do
      json_data = { 'type' => 'Text', 'text' => 'Link', 'linkable' => true, 'fontColor' => '#0000FF' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('color =')
    end

    it 'generates linkable text with font weight' do
      json_data = { 'type' => 'Text', 'text' => 'Link', 'linkable' => true, 'fontWeight' => 'medium' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('weight = FontWeight.Medium,')
    end

    it 'generates linkable text with text alignment' do
      json_data = { 'type' => 'Text', 'text' => 'Link', 'linkable' => true, 'textAlign' => 'center' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.Center')
    end

    it 'generates linkable text with edgeInset array' do
      json_data = { 'type' => 'Text', 'text' => 'Link', 'linkable' => true, 'edgeInset' => [5, 10, 5, 10] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.padding')
    end

    it 'generates linkable text with edgeInset number' do
      json_data = { 'type' => 'Text', 'text' => 'Link', 'linkable' => true, 'edgeInset' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.padding(8.dp)')
    end

    it 'generates linkable text with right alignment' do
      json_data = { 'type' => 'Text', 'text' => 'Link', 'linkable' => true, 'textAlign' => 'right' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.End')
    end

    it 'generates linkable text with left alignment' do
      json_data = { 'type' => 'Text', 'text' => 'Link', 'linkable' => true, 'textAlign' => 'left' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.Start')
    end
  end

  describe 'text shadow' do
    it 'generates text with textShadow' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'textShadow' => true }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('style = TextStyle')
      expect(result).to include('shadow = Shadow')
      expect(required_imports).to include(:shadow_style)
    end
  end

  describe 'left alignment' do
    it 'generates text with left alignment' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'textAlign' => 'left' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('textAlign = TextAlign.Start')
    end
  end

  describe 'word line break mode' do
    it 'generates text with word line break mode' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'lineBreakMode' => 'word' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('overflow = TextOverflow.Ellipsis')
    end
  end

  describe 'parent type handling' do
    it 'applies weight in Row parent' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'weight' => 1 }
      result = described_class.generate(json_data, 0, required_imports, 'Row')
      expect(result).to include('.weight')
    end

    it 'applies weight in Column parent' do
      json_data = { 'type' => 'Text', 'text' => 'Test', 'weight' => 1 }
      result = described_class.generate(json_data, 0, required_imports, 'Column')
      expect(result).to include('.weight')
    end
  end

  describe 'helper methods' do
    describe '.escape_string' do
      it 'escapes quotes' do
        result = described_class.send(:escape_string, 'text "with" quotes')
        expect(result).to eq('text \\"with\\" quotes')
      end

      it 'escapes newlines' do
        result = described_class.send(:escape_string, "line1\nline2")
        expect(result).to eq('line1\\nline2')
      end

      it 'escapes carriage returns' do
        result = described_class.send(:escape_string, "line1\rline2")
        expect(result).to eq('line1\\rline2')
      end

      it 'escapes tabs' do
        result = described_class.send(:escape_string, "col1\tcol2")
        expect(result).to eq('col1\\tcol2')
      end

      it 'escapes backslashes' do
        result = described_class.send(:escape_string, 'path\\to\\file')
        expect(result).to include('\\\\')
      end
    end

    describe '.quote' do
      it 'quotes and escapes text' do
        result = described_class.send(:quote, 'Hello "World"')
        expect(result).to start_with('"')
        expect(result).to end_with('"')
        expect(result).to include('\\"')
      end

      it 'handles backslashes' do
        result = described_class.send(:quote, 'C:\\path')
        expect(result).to include('\\\\')
      end
    end

    describe '.indent' do
      it 'adds indentation' do
        result = described_class.send(:indent, 'text', 2)
        expect(result).to eq('        text')
      end

      it 'returns unchanged for level 0' do
        result = described_class.send(:indent, 'text', 0)
        expect(result).to eq('text')
      end

      it 'preserves empty lines' do
        result = described_class.send(:indent, "line1\n\nline2", 1)
        expect(result).to eq("    line1\n\n    line2")
      end
    end

    describe '.build_text_style' do
      it 'returns nil when no style parts' do
        result = described_class.send(:build_text_style, { 'type' => 'Text' }, 0, Set.new)
        expect(result).to be_nil
      end

      it 'builds style with fontSize' do
        imports = Set.new
        result = described_class.send(:build_text_style, { 'fontSize' => 16 }, 0, imports)
        expect(result).to include('fontSize = 16.sp')
      end

      it 'builds style with fontColor' do
        imports = Set.new
        result = described_class.send(:build_text_style, { 'fontColor' => '#FF0000' }, 0, imports)
        expect(result).to include('color =')
      end

      it 'builds style with textAlign' do
        imports = Set.new
        result = described_class.send(:build_text_style, { 'textAlign' => 'center' }, 0, imports)
        expect(result).to include('textAlign = TextAlign.Center')
        expect(imports).to include(:text_align)
      end
    end

    describe 'Configuration.Font.resolve(FontSpec) emission' do
      let(:required_imports) { Set.new }

      it 'emits FontSpec block whenever Text is generated' do
        json_data = { 'type' => 'Text', 'text' => 'Test', 'fontSize' => 15 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to match(/Configuration\.Font\.resolve\(FontSpec\(/)
        expect(result).to include('size = 15.sp,')
        expect(required_imports).to include(:configuration)
        expect(required_imports).to include(:font_spec)
      end

      it 'threads weight name into FontSpec.weight (font = bold)' do
        json_data = { 'type' => 'Text', 'text' => 'Test', 'fontSize' => 15, 'font' => 'bold' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('weight = FontWeight.Bold,')
        expect(result).to include('size = 15.sp,')
      end

      it 'threads weight name into FontSpec.weight (fontWeight = semibold)' do
        json_data = { 'type' => 'Text', 'text' => 'Test', 'fontWeight' => 'semibold' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('weight = FontWeight.SemiBold,')
      end

      it 'threads explicit fontFamily literal into FontSpec.family' do
        json_data = { 'type' => 'Text', 'text' => 'Test', 'fontFamily' => 'cormorant_bold', 'fontSize' => 15 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('family = "cormorant_bold",')
      end

      it 'threads font-as-family-name into FontSpec.family' do
        json_data = { 'type' => 'Text', 'text' => 'Test', 'font' => 'Roboto-Regular' }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('family = "Roboto-Regular",')
      end

      it 'wires destructured fields onto Text(...) parameters' do
        json_data = { 'type' => 'Text', 'text' => 'Test', 'fontSize' => 12 }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('fontFamily = resolved_text1.family,')
        expect(result).to include('fontWeight = resolved_text1.weight,')
        expect(result).to include('fontSize = resolved_text1.size ?: TextUnit.Unspecified,')
        expect(result).to include('fontStyle = resolved_text1.style ?: FontStyle.Normal,')
      end
    end

    # highlightAttributes / highlightColor take over while `selected` is true.
    # Canonical semantics come from the iOS UIKit runtime, which keeps two
    # attribute dictionaries and swaps on `selected`.
    describe 'highlight state' do
      it 'resolves the highlight font through the same FontSpec provider' do
        json_data = {
          'type' => 'Text', 'text' => 'Hi', 'fontSize' => 14, 'selected' => '@{isChosen}',
          'highlightAttributes' => { 'font' => 'bold', 'fontSize' => 24, 'fontColor' => '#FF0000' }
        }
        result = described_class.generate(json_data, 0, required_imports)

        # Two resolve blocks, so an app's fontProvider sees both states.
        expect(result).to include('val resolved_text1 = Configuration.Font.resolve(')
        expect(result).to include('val resolved_text2 = Configuration.Font.resolve(')
        expect(result).to include('size = 24.sp')
        expect(result).to include('weight = FontWeight.Bold')
        expect(result).to include('fontSize = (if (data.isChosen) resolved_text2 else resolved_text1).size')
      end

      it 'swaps the colour on the same condition' do
        json_data = {
          'type' => 'Text', 'text' => 'Hi', 'fontColor' => '#000000',
          'selected' => '@{isChosen}', 'highlightColor' => '#00FF00'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to match(/color = if \(data\.isChosen\) .*#00FF00.*else .*#000000/)
      end

      # Compose has no "inherit" colour for Text.
      it 'falls back to Color.Unspecified when there is no base colour' do
        json_data = {
          'type' => 'Text', 'text' => 'Hi', 'selected' => '@{isChosen}',
          'highlightColor' => '#00FF00'
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('else Color.Unspecified')
      end

      # `if (true)` and an unreferenced `val` are both Kotlin warnings, and a
      # zero-warning build is a hard invariant for the consuming project.
      it 'emits no dead branch or unused val when selected is literally true' do
        json_data = {
          'type' => 'Text', 'text' => 'Hi', 'fontSize' => 14, 'selected' => true,
          'highlightAttributes' => { 'fontSize' => 24, 'fontColor' => '#FF0000' }
        }
        result = described_class.generate(json_data, 0, required_imports)

        expect(result).not_to include('if (true)')
        expect(result).not_to include('resolved_text1')
        expect(result).to include('fontSize = resolved_text2.size ?: TextUnit.Unspecified,')
      end

      it 'prefers highlightAttributes and falls through when it has no usable key' do
        both = described_class.generate({
          'type' => 'Text', 'text' => 'Hi', 'selected' => true,
          'highlightAttributes' => { 'fontColor' => '#FF0000' }, 'highlightColor' => '#00FF00'
        }, 0, required_imports)
        expect(both).to include('#FF0000')
        expect(both).not_to include('#00FF00')

        described_class.counter = 0
        empty = described_class.generate({
          'type' => 'Text', 'text' => 'Hi', 'selected' => true,
          'highlightAttributes' => {}, 'highlightColor' => '#00FF00'
        }, 0, required_imports)
        expect(empty).to include('#00FF00')
      end

      it 'swaps lineHeight, resolved against the highlight font size' do
        json_data = {
          'type' => 'Text', 'text' => 'Hi', 'fontSize' => 14, 'lineHeightMultiple' => 1.2,
          'selected' => '@{sel}',
          'highlightAttributes' => { 'fontSize' => 24, 'lineHeightMultiple' => 1.5 }
        }
        result = described_class.generate(json_data, 0, required_imports)

        # 24 * 1.5 highlighted, 14 * 1.2 not.
        expect(result).to include('lineHeight = (if (data.sel) 36.0 else 16.8).sp')
      end

      it 'falls back to the font line height when the base sets none' do
        json_data = {
          'type' => 'Text', 'text' => 'Hi', 'selected' => '@{sel}',
          'highlightAttributes' => { 'lineHeightMultiple' => 1.5 }
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('else TextUnit.Unspecified')
      end

      it 'swaps textAlign' do
        json_data = {
          'type' => 'Text', 'text' => 'Hi', 'textAlign' => 'Left', 'selected' => '@{sel}',
          'highlightAttributes' => { 'textAlign' => 'Center' }
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('textAlign = if (data.sel) TextAlign.Center else TextAlign.Start')
      end

      it 'uses TextAlign.Unspecified when the base sets no alignment' do
        json_data = {
          'type' => 'Text', 'text' => 'Hi', 'selected' => '@{sel}',
          'highlightAttributes' => { 'textAlign' => 'Center' }
        }
        result = described_class.generate(json_data, 0, required_imports)
        expect(result).to include('else TextAlign.Unspecified')
      end

      it 'emits nothing conditional without a driver, and no stale comment' do
        json_data = { 'type' => 'Text', 'text' => 'Hi', 'highlightColor' => '#00FF00' }
        result = described_class.generate(json_data, 0, required_imports)

        expect(result).not_to include('if (')
        expect(result).not_to include('// highlightColor')
      end
    end
  end
end

# `hint` + `hintAttributes` — a Label's placeholder. UIKit's SJUILabel swaps in
# the hint, styled by hintAttributes, when the text is empty, and it requires
# BOTH: a hint with no attributes shows nothing there.
RSpec.describe KjuiTools::Compose::Components::TextComponent, 'hintAttributes' do
  let(:required_imports) { Set.new }

  # ResourceResolver.data_definitions is a Thread.current global that other
  # specs set and do not always clear, and it decides whether a binding renders
  # with its `?: ""` default. Cleared here so these expectations do not depend
  # on the order rspec happens to run in (seed 37213 was the one that caught it).
  before { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  def label(extra)
    described_class.reset_counter!
    described_class.generate(
      { 'type' => 'Label', 'text' => '@{title}' }.merge(extra), 0, required_imports
    )
  end

  it 'swaps in the hint when the text is empty' do
    result = label('hint' => 'No title', 'hintAttributes' => { 'fontColor' => '#999999' })
    expect(result).to include('val labelText1 = "${data.title ?: ""}"')
    expect(result).to include('text = if (labelText1.isEmpty()) "No title" else labelText1,')
  end

  it 'styles it with the hint colour' do
    result = label('hint' => 'No title', 'hintAttributes' => { 'fontColor' => '#999999' })
    expect(result).to match(/color = if \(labelText1\.isEmpty\(\)\) Color\(.*999999/)
  end

  # The hint font goes through the same FontSpec resolver as the base one, so an
  # app's fontProvider is honoured in both states.
  it 'resolves a separate font for the hint' do
    result = label('hint' => 'None', 'fontSize' => 16,
                   'hintAttributes' => { 'fontSize' => 12, 'font' => 'bold' })
    expect(result).to include('size = 12.sp')
    expect(result).to include('size = 16.sp')
    expect(result).to include('fontSize = (if (labelText1.isEmpty()) resolved_text2 else resolved_text1).size')
  end

  # UIKit's own condition — both keys or nothing.
  it 'does nothing with a hint and no attributes' do
    result = label('hint' => 'No title')
    expect(result).not_to include('labelText')
    expect(result).to include('text = "${data.title ?: ""}",')
  end

  it 'does nothing with attributes and no hint' do
    expect(label('hintAttributes' => { 'fontColor' => '#999999' })).not_to include('labelText')
  end

  # An empty label is a hint first and a selected label second.
  it 'nests outside the highlight state' do
    result = label('hint' => 'None', 'hintAttributes' => { 'fontColor' => '#999999' },
                   'selected' => '@{isSel}', 'highlightColor' => '#FF0000', 'fontColor' => '#111111')
    expect(result).to match(
      /color = if \(labelText\d\.isEmpty\(\)\).*else \(if \(data\.isSel\)/
    )
  end

  it 'leaves a plain label untouched' do
    expect(label({})).not_to include('labelText')
  end
end
