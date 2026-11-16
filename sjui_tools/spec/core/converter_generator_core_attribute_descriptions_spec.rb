# frozen_string_literal: true

require 'core/converter_generator_core'

# The description each attribute gets in attribute_definitions/<Name>.json.
#
# Until 1.8.113 `jui g converter --from / --all` handed the tools only
# `name:type`, so every regeneration replaced the component spec's
# `props.items[].description` with "<key> attribute"
# (jui-g-converter-drops-spec-prop-descriptions). The canonical copy is
# shared/core/converter_generator_core.rb; the mirror spec pins the per-tool
# copies byte-identical, so pinning the behaviour once is enough. Each tool's
# generator spec pins that its output goes through it.
RSpec.describe JsonUIShared::ConverterGeneratorCore do
  describe '.parse_attribute_descriptions' do
    it 'returns the {attribute => description} object' do
      expect(described_class.parse_attribute_descriptions('{"title":"見出し","onTap":"tapped"}'))
        .to eq('title' => '見出し', 'onTap' => 'tapped')
    end

    it 'accepts an empty object' do
      expect(described_class.parse_attribute_descriptions('{}')).to eq({})
    end

    it 'refuses what is not JSON, naming the option' do
      expect { described_class.parse_attribute_descriptions('{"title":') }
        .to raise_error(ArgumentError, /--attribute-descriptions is not valid JSON/)
    end

    it 'refuses JSON that is not an object of strings' do
      ['["title"]', '"title"', '{"title":1}', '{"title":null}', '{"title":{"text":"x"}}'].each do |bad|
        expect { described_class.parse_attribute_descriptions(bad) }
          .to raise_error(ArgumentError, /takes a JSON object/), bad
      end
    end
  end

  describe '.attribute_description' do
    let(:options) { { attribute_descriptions: { 'title' => '見出し', 'blank' => "  \n" } } }

    it 'uses the handed-down description' do
      expect(described_class.attribute_description(options, 'title', 'title attribute')).to eq('見出し')
    end

    it 'falls back when the attribute has none, or a blank one' do
      expect(described_class.attribute_description(options, 'count', 'count attribute')).to eq('count attribute')
      expect(described_class.attribute_description(options, 'blank', 'blank attribute')).to eq('blank attribute')
    end

    it 'falls back when no descriptions were handed down (a direct `g converter`)' do
      expect(described_class.attribute_description({}, 'title', 'title attribute')).to eq('title attribute')
      expect(described_class.attribute_description(nil, 'title', 'title attribute')).to eq('title attribute')
    end
  end
end
