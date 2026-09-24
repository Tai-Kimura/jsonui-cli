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

    it 'parses --force and --skip-existing (non-interactive overwrite control)' do
      cmd = described_class.allocate
      cmd.instance_variable_set(:@args, ['--force', '--skip-existing'])
      opts = cmd.send(:parse_converter_options)
      expect(opts[:force]).to be true
      expect(opts[:skip_existing]).to be true
    end

    # jui-g-converter-drops-spec-prop-descriptions: `jui g converter --from /
    # --all` hands the spec's descriptions down as JSON.
    it 'parses --attribute-descriptions into a Hash' do
      cmd = described_class.allocate
      cmd.instance_variable_set(:@args, ['--attribute-descriptions', '{"title":"見出し","onTap":"tapped"}'])
      expect(cmd.send(:parse_converter_options)[:attribute_descriptions])
        .to eq('title' => '見出し', 'onTap' => 'tapped')
    end

    it 'exits 1 naming the option on a malformed --attribute-descriptions' do
      ['{"title":', '["title"]', '{"title":1}'].each do |bad|
        cmd = described_class.allocate
        cmd.instance_variable_set(:@args, ['--attribute-descriptions', bad])
        expect { cmd.send(:parse_converter_options) }
          .to raise_error(SystemExit) { |e| expect(e.status).to eq(1) }
          .and output(/--attribute-descriptions/).to_stdout
      end
    end
  end

  describe '#converter_command_line' do
    def recorded(*args)
      cmd = described_class.allocate
      cmd.instance_variable_set(:@original_args, ['converter', *args])
      cmd.send(:converter_command_line)
    end

    it 'records the invocation as before' do
      expect(recorded('Meter', '--attributes', 'a:Int', '--skip-existing'))
        .to eq('rjui g converter Meter --attributes a:Int --skip-existing')
    end

    it 'leaves the descriptions JSON out, in either spelling' do
      expect(recorded('Meter', '--attributes', 'a:Int', '--attribute-descriptions', '{"a":"見出し"}', '--force'))
        .to eq('rjui g converter Meter --attributes a:Int --force')
      expect(recorded('Meter', '--attribute-descriptions={"a":"x"}', '--container'))
        .to eq('rjui g converter Meter --container')
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
