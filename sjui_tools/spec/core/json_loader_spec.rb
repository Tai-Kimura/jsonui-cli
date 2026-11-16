# frozen_string_literal: true

require 'core/json_loader'
require 'tempfile'
require 'json'

RSpec.describe SjuiTools::Core::JsonLoader do
  describe '.load_file' do
    context 'with valid JSON file' do
      let(:json_content) { { 'key' => 'value', 'number' => 42 } }

      it 'parses JSON content correctly' do
        Tempfile.create(['test', '.json']) do |file|
          file.write(JSON.generate(json_content))
          file.rewind

          result = described_class.load_file(file.path)
          expect(result).to eq(json_content)
        end
      end
    end

    context 'with non-existent file' do
      it 'returns nil' do
        result = described_class.load_file('/non/existent/file.json')
        expect(result).to be_nil
      end
    end

    context 'with invalid JSON' do
      it 'raises an error' do
        Tempfile.create(['test', '.json']) do |file|
          file.write('{ invalid json }')
          file.rewind

          expect {
            described_class.load_file(file.path)
          }.to raise_error(/Failed to parse JSON/)
        end
      end
    end

    context 'with nested JSON' do
      let(:nested_json) do
        {
          'level1' => {
            'level2' => {
              'value' => 'deep'
            }
          },
          'array' => [1, 2, 3]
        }
      end

      it 'parses nested structure correctly' do
        Tempfile.create(['test', '.json']) do |file|
          file.write(JSON.generate(nested_json))
          file.rewind

          result = described_class.load_file(file.path)
          expect(result['level1']['level2']['value']).to eq('deep')
          expect(result['array']).to eq([1, 2, 3])
        end
      end
    end
  end

  describe '.save_file' do
    context 'with pretty format (default)' do
      let(:data) { { 'key' => 'value' } }

      it 'saves JSON with pretty formatting' do
        Tempfile.create(['test', '.json']) do |file|
          described_class.save_file(file.path, data)
          content = File.read(file.path)

          expect(content).to include("\n")
          expect(JSON.parse(content)).to eq(data)
        end
      end
    end

    context 'with compact format' do
      let(:data) { { 'key' => 'value' } }

      it 'saves JSON without formatting' do
        Tempfile.create(['test', '.json']) do |file|
          described_class.save_file(file.path, data, pretty: false)
          content = File.read(file.path)

          expect(content).not_to include("\n")
          expect(JSON.parse(content)).to eq(data)
        end
      end
    end
  end

  describe '.load_and_merge' do
    context 'with multiple files' do
      it 'merges files in order' do
        file1 = Tempfile.new(['config1', '.json'])
        file2 = Tempfile.new(['config2', '.json'])

        begin
          file1.write(JSON.generate({ 'a' => 1, 'b' => 2 }))
          file1.rewind
          file2.write(JSON.generate({ 'b' => 3, 'c' => 4 }))
          file2.rewind

          result = described_class.load_and_merge(file1.path, file2.path)

          expect(result['a']).to eq(1)
          expect(result['b']).to eq(3)  # Second file overwrites
          expect(result['c']).to eq(4)
        ensure
          file1.close
          file1.unlink
          file2.close
          file2.unlink
        end
      end
    end

    context 'with nested merge' do
      it 'deep merges nested hashes' do
        file1 = Tempfile.new(['config1', '.json'])
        file2 = Tempfile.new(['config2', '.json'])

        begin
          file1.write(JSON.generate({ 'nested' => { 'a' => 1, 'b' => 2 } }))
          file1.rewind
          file2.write(JSON.generate({ 'nested' => { 'b' => 3, 'c' => 4 } }))
          file2.rewind

          result = described_class.load_and_merge(file1.path, file2.path)

          expect(result['nested']['a']).to eq(1)
          expect(result['nested']['b']).to eq(3)
          expect(result['nested']['c']).to eq(4)
        ensure
          file1.close
          file1.unlink
          file2.close
          file2.unlink
        end
      end
    end

    context 'with non-existent file in list' do
      it 'skips non-existent files' do
        file1 = Tempfile.new(['config1', '.json'])

        begin
          file1.write(JSON.generate({ 'key' => 'value' }))
          file1.rewind

          result = described_class.load_and_merge(
            file1.path,
            '/non/existent/file.json'
          )

          expect(result['key']).to eq('value')
        ensure
          file1.close
          file1.unlink
        end
      end
    end
  end

  describe '.validate_structure' do
    context 'with all required keys present' do
      let(:data) { { 'name' => 'Test', 'version' => '1.0' } }

      it 'returns true' do
        result = described_class.validate_structure(
          data,
          required_keys: ['name', 'version']
        )
        expect(result).to be true
      end
    end

    context 'with missing required keys' do
      let(:data) { { 'name' => 'Test' } }

      it 'raises an error' do
        expect {
          described_class.validate_structure(
            data,
            required_keys: ['name', 'version']
          )
        }.to raise_error(/Missing required keys: version/)
      end
    end

    context 'with unknown keys' do
      let(:data) { { 'name' => 'Test', 'extra' => 'value' } }

      it 'prints warning but returns true' do
        expect {
          result = described_class.validate_structure(
            data,
            required_keys: ['name'],
            optional_keys: []
          )
          expect(result).to be true
        }.to output(/Warning: Unknown keys found: extra/).to_stdout
      end
    end

    context 'with optional keys' do
      let(:data) { { 'name' => 'Test', 'optional' => 'value' } }

      it 'does not warn for known optional keys' do
        expect {
          result = described_class.validate_structure(
            data,
            required_keys: ['name'],
            optional_keys: ['optional']
          )
          expect(result).to be true
        }.not_to output.to_stdout
      end
    end
  end
end
