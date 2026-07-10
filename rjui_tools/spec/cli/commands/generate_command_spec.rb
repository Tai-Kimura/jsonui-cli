# frozen_string_literal: true

require_relative '../../spec_helper'
require 'cli/commands/generate_command'

RSpec.describe RjuiTools::CLI::Commands::GenerateCommand do
  # Regression of `jui-generate-converter-comma-in-prop-type-breaks-attributes`:
  # a multi-arg closure type (`((String, String) -> Void)?`) contains commas,
  # so the --attributes value must be split on top-level commas only.
  describe '#parse_converter_options' do
    def parse(attrs_value)
      cmd = described_class.allocate
      cmd.instance_variable_set(:@args, ['--attributes', attrs_value])
      cmd.send(:parse_converter_options)
    end

    it 'keeps a comma-bearing closure type as one attribute' do
      opts = parse('onRangeChange:((String, String) -> Void)?,title:String')
      expect(opts[:attributes]).to eq(
        'onRangeChange' => '((String, String) -> Void)?',
        'title' => 'String'
      )
    end

    it 'still splits plain comma-separated attributes' do
      opts = parse('a:String,b:Int')
      expect(opts[:attributes]).to eq('a' => 'String', 'b' => 'Int')
    end
  end

  describe '#split_top_level_commas' do
    let(:cmd) { described_class.allocate }

    it 'protects commas inside brackets' do
      expect(cmd.send(:split_top_level_commas, 'pair:[String, Int],flag:Bool'))
        .to eq(['pair:[String, Int]', 'flag:Bool'])
    end

    it 'returns an empty array for an empty string' do
      expect(cmd.send(:split_top_level_commas, '')).to eq([])
    end
  end
end
