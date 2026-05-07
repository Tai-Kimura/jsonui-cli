# frozen_string_literal: true

require 'cli/commands/convert'

RSpec.describe SjuiTools::CLI::Commands::Convert do
  let(:command) { described_class.new }
  let(:temp_dir) { Dir.mktmpdir('convert_test') }

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#run' do
    context 'with --help flag' do
      it 'shows help and exits' do
        expect { command.run(['--help']) }.to raise_error(SystemExit)
      end
    end

    context 'with no arguments' do
      it 'exits with error' do
        expect { command.run([]) }.to raise_error(SystemExit)
      end

      it 'shows error message' do
        expect { begin; command.run([]); rescue SystemExit; end }.to output(/Input file or command is required/).to_stdout
      end
    end

    context 'with non-existent file' do
      it 'exits with error' do
        expect { command.run(['nonexistent.json']) }.to raise_error(SystemExit)
      end

      it 'shows file not found error' do
        expect { begin; command.run(['nonexistent.json']); rescue SystemExit; end }.to output(/Input file not found/).to_stdout
      end
    end

    context 'with unsupported conversion' do
      let(:input_file) { File.join(temp_dir, 'test.json') }

      before do
        File.write(input_file, '{"type": "View"}')
      end

      it 'exits with error for unknown types' do
        expect { command.run([input_file, '--from', 'unknown', '--to', 'unknown']) }.to raise_error(SystemExit)
      end

      it 'shows unsupported conversion error' do
        expect { begin; command.run([input_file, '--from', 'unknown', '--to', 'unknown']); rescue SystemExit; end }.to output(/Unsupported conversion/).to_stdout
      end
    end

    context 'with to-group subcommand' do
      before do
        allow(command).to receive(:convert_to_group_reference)
      end

      it 'calls convert_to_group_reference' do
        command.run(['to-group'])
        expect(command).to have_received(:convert_to_group_reference)
      end
    end

    context 'with json to swiftui conversion' do
      let(:input_file) { File.join(temp_dir, 'test.json') }

      before do
        File.write(input_file, '{"type": "View"}')
        allow(command).to receive(:convert_json_to_swiftui)
      end

      it 'calls convert_json_to_swiftui' do
        command.run([input_file])
        expect(command).to have_received(:convert_json_to_swiftui).with(input_file, nil)
      end

      it 'passes output file' do
        output_file = File.join(temp_dir, 'output.swift')
        command.run([input_file, output_file])
        expect(command).to have_received(:convert_json_to_swiftui).with(input_file, output_file)
      end
    end
  end

  describe '#parse_options (private)' do
    it 'parses --from option' do
      args = ['--from', 'json', 'input.json']
      options = command.send(:parse_options, args)
      expect(options[:from]).to eq('json')
    end

    it 'parses --to option' do
      args = ['--to', 'swiftui', 'input.json']
      options = command.send(:parse_options, args)
      expect(options[:to]).to eq('swiftui')
    end

    it 'preserves non-option arguments' do
      args = ['input.json', 'output.swift']
      command.send(:parse_options, args)
      expect(args).to eq(['input.json', 'output.swift'])
    end
  end

  describe '#convert_json_to_swiftui (private)' do
    let(:input_file) { File.join(temp_dir, 'test.json') }

    before do
      File.write(input_file, '{"type": "View", "children": []}')
    end

    it 'outputs progress message' do
      require 'swiftui/json_to_swiftui_converter'

      converter = instance_double(SjuiTools::SwiftUI::JsonToSwiftUIConverter)
      allow(SjuiTools::SwiftUI::JsonToSwiftUIConverter).to receive(:new).and_return(converter)
      allow(converter).to receive(:convert_file).and_return('output.swift')

      expect { command.send(:convert_json_to_swiftui, input_file, nil) }.to output(/Converting.*to SwiftUI/).to_stdout
    end

    it 'handles conversion errors' do
      require 'swiftui/json_to_swiftui_converter'

      converter = instance_double(SjuiTools::SwiftUI::JsonToSwiftUIConverter)
      allow(SjuiTools::SwiftUI::JsonToSwiftUIConverter).to receive(:new).and_return(converter)
      allow(converter).to receive(:convert_file).and_raise(StandardError.new('Test error'))

      expect { command.send(:convert_json_to_swiftui, input_file, nil) }.to raise_error(SystemExit)
    end
  end

  describe '#convert_to_group_reference (private)' do
    context 'with --help flag' do
      it 'shows help and exits' do
        expect { command.send(:convert_to_group_reference, ['--help']) }.to raise_error(SystemExit)
      end
    end

    context 'with --force flag' do
      before do
        # Mock the converter
        require 'uikit/tools/convert_to_group_reference'

        converter = instance_double(SjuiTools::UIKit::Tools::ConvertToGroupReference)
        allow(SjuiTools::UIKit::Tools::ConvertToGroupReference).to receive(:new).and_return(converter)
        allow(converter).to receive(:convert)
      end

      it 'passes force option to converter' do
        converter = instance_double(SjuiTools::UIKit::Tools::ConvertToGroupReference)
        allow(SjuiTools::UIKit::Tools::ConvertToGroupReference).to receive(:new).and_return(converter)
        expect(converter).to receive(:convert).with(true)

        command.send(:convert_to_group_reference, ['--force'])
      end
    end
  end
end
