# frozen_string_literal: true

require 'xml/helpers/attribute_mapper'

RSpec.describe XmlGenerator::AttributeMapper do
  let(:mapper) { described_class.new }

  describe '#initialize' do
    it 'creates mapper without arguments' do
      expect(mapper).to be_a(described_class)
    end

    it 'creates mapper with drawable generator' do
      mapper_with_drawable = described_class.new(double('DrawableGenerator'))
      expect(mapper_with_drawable).to be_a(described_class)
    end
  end

  describe '#map_dimension' do
    it 'maps integer to dp' do
      result = mapper.map_dimension(16)
      expect(result).to eq('16dp')
    end

    it 'maps matchParent' do
      result = mapper.map_dimension('matchParent')
      expect(result).to eq('match_parent')
    end

    it 'maps wrapContent' do
      result = mapper.map_dimension('wrapContent')
      expect(result).to eq('wrap_content')
    end

    it 'maps match_parent' do
      result = mapper.map_dimension('match_parent')
      expect(result).to eq('match_parent')
    end
  end

  describe '#map_attribute' do
    context 'standard attributes' do
      it 'maps contentDescription' do
        result = mapper.map_attribute('contentDescription', 'Button description', 'Button', nil)
        expect(result[:name]).to eq('contentDescription')
        expect(result[:value]).to eq('Button description')
      end

      it 'maps tag' do
        result = mapper.map_attribute('tag', 'my_tag', 'View', nil)
        expect(result[:name]).to eq('tag')
      end

      it 'maps elevation' do
        result = mapper.map_attribute('elevation', 8, 'View', nil)
        expect(result[:name]).to eq('elevation')
      end

      it 'maps rotation' do
        result = mapper.map_attribute('rotation', 45, 'View', nil)
        expect(result[:name]).to eq('rotation')
        expect(result[:value]).to eq('45.0')
      end

      it 'maps scaleX' do
        result = mapper.map_attribute('scaleX', 1.5, 'View', nil)
        expect(result[:name]).to eq('scaleX')
      end
    end

    context 'tools namespace attributes' do
      it 'maps title to tools namespace' do
        result = mapper.map_attribute('title', 'My Title', 'View', nil)
        expect(result[:namespace]).to eq('tools')
        expect(result[:name]).to eq('title')
      end

      it 'maps count to tools namespace' do
        result = mapper.map_attribute('count', 5, 'View', nil)
        expect(result[:namespace]).to eq('tools')
        expect(result[:name]).to eq('count')
      end

      it 'skips tools attributes with data binding' do
        result = mapper.map_attribute('title', '@{data.title}', 'View', nil)
        expect(result).to be_nil
      end
    end

    context 'constraint attributes' do
      it 'maps constraintStartToStartOf' do
        result = mapper.map_attribute('constraintStartToStartOf', 'parent', 'View', nil)
        expect(result[:namespace]).to eq('app')
        expect(result[:name]).to eq('layout_constraintStart_toStartOf')
        expect(result[:value]).to eq('parent')
      end

      it 'maps constraintEndToEndOf to view id' do
        result = mapper.map_attribute('constraintEndToEndOf', 'other_view', 'View', nil)
        expect(result[:value]).to eq('@id/other_view')
      end

      it 'maps constraintTopToBottomOf' do
        result = mapper.map_attribute('constraintTopToBottomOf', 'header', 'View', nil)
        expect(result[:name]).to eq('layout_constraintTop_toBottomOf')
      end
    end

    context 'binding expressions' do
      it 'skips items binding for RecyclerView' do
        result = mapper.map_attribute('items', '@{data.list}', 'RecyclerView', nil)
        expect(result).to be_nil
      end

      it 'skips visibility binding' do
        result = mapper.map_attribute('visibility', '@{data.isVisible}', 'View', nil)
        expect(result).to be_nil
      end

      it 'skips progress binding' do
        result = mapper.map_attribute('progress', '@{data.progress}', 'ProgressBar', nil)
        expect(result).to be_nil
      end

      it 'skips tint with statusColor' do
        result = mapper.map_attribute('tint', '@{data.statusColor}', 'ImageView', nil)
        expect(result).to be_nil
      end
    end

    context 'unknown attributes' do
      it 'returns nil for unknown attribute' do
        result = mapper.map_attribute('unknownAttribute', 'value', 'View', nil)
        expect(result).to be_nil
      end
    end
  end
end
