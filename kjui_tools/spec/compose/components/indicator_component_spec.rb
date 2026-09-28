# frozen_string_literal: true

require 'compose/components/indicator_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::IndicatorComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates indicator component' do
      json_data = { 'type' => 'Indicator' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result.to_s).to match(/Indicator|Progress/)
    end

    it 'generates indicator with progress' do
      json_data = { 'type' => 'Indicator', 'progress' => 0.5 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result.to_s).to match(/ProgressIndicator/)
    end
  end

  # kjui-indicator-style-loses-to-a-declared-wrapcontent: a wrapContent axis is
  # the content's size, and indicatorStyle sets the content's size, so only a
  # length beats the style. matchParent keeps its old picture (not ruled).
  describe 'indicatorStyle against a declared width / height' do
    gen = ->(extra) { described_class.generate({ 'type' => 'Indicator' }.merge(extra), 0, Set.new) }

    it 'draws the style size when both axes are wrapContent (the conformance fixtures)' do
      { 'small' => '.size(16.dp)', 'large' => '.size(48.dp)' }.each do |style, size|
        code = gen.call('indicatorStyle' => style, 'width' => 'wrapContent', 'height' => 'wrapContent')
        expect(code).to include(size), code
        expect(code).not_to include('wrapContent')
      end
      # the snake spelling is the same declaration
      expect(gen.call('indicatorStyle' => 'large', 'width' => 'wrap_content', 'height' => 'wrap_content'))
        .to include('.size(48.dp)')
      # a frame's wrapContent axes, too
      expect(gen.call('indicatorStyle' => 'large', 'frame' => { 'width' => 'wrapContent', 'height' => 'wrapContent' }))
        .to include('.size(48.dp)')
    end

    it 'draws the style size when one axis is wrapContent and the other undeclared' do
      code = gen.call('indicatorStyle' => 'large', 'width' => 'wrapContent')
      expect(code).to include('.size(48.dp)')
      expect(code).not_to include('wrapContentWidth')
    end

    it 'mixed: the length axis takes the length, the wrapContent axis the style size' do
      code = gen.call('indicatorStyle' => 'large', 'width' => 30, 'height' => 'wrapContent')
      expect(code).to include('.requiredWidth(30.dp)')
      expect(code).to include('.height(48.dp)')
      expect(code).not_to include('wrapContentHeight')
      expect(code).not_to include('.size(48.dp)')

      code = gen.call('indicatorStyle' => 'small', 'width' => 'wrapContent', 'height' => 30)
      expect(code).to include('.requiredHeight(30.dp)')
      expect(code).to include('.width(16.dp)')
      expect(code).not_to include('wrapContentWidth')

      framed = gen.call('indicatorStyle' => 'large', 'frame' => { 'width' => 30, 'height' => 'wrapContent' })
      expect(framed).to include('.requiredWidth(30.dp)')
      expect(framed).to include('.height(48.dp)')
    end

    it 'a length on both axes still wins over the style' do
      code = gen.call('indicatorStyle' => 'large', 'width' => 40, 'height' => 40)
      expect(code).to include('.requiredWidth(40.dp)', '.requiredHeight(40.dp)')
      expect(code).not_to include('48.dp')
    end

    it 'matchParent still wins on its axis (not ruled: unchanged)' do
      code = gen.call('indicatorStyle' => 'large', 'width' => 'matchParent')
      expect(code).to include('.fillMaxWidth()')
      expect(code).not_to include('48.dp')
    end

    it 'without a style size of its own (medium / linear), wrapContent is emitted as before' do
      %w[medium linear].each do |style|
        code = gen.call('indicatorStyle' => style, 'width' => 'wrapContent', 'height' => 'wrapContent')
        expect(code).to include('.wrapContentWidth()', '.wrapContentHeight()')
        expect(code).not_to match(/\.size\(/)
      end
    end
  end
end
