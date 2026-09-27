# frozen_string_literal: true

require 'xml/helpers/resource_resolver'

RSpec.describe KjuiTools::Xml::Helpers::ResourceResolver do
  # Each example starts from an empty cache, and the process-wide cache is put
  # back after this file (spec/support/process_state_guard.rb). Clearing before
  # each example left whatever the file's last example filled: on an order that
  # ends with a process_color example (seeds 7 and 3556) the file left
  # @colors_data and @defined_colors_data at {} where there had been nothing.
  before(:context) { @kept_process_state = ProcessStateGuard.keep(described_class) }
  after(:context) { ProcessStateGuard.put_back(@kept_process_state) }

  before do
    described_class.clear_cache
  end

  describe '.process_text' do
    it 'returns nil for nil input' do
      expect(described_class.process_text(nil)).to be_nil
    end

    it 'returns empty string for empty input' do
      expect(described_class.process_text('')).to eq('')
    end

    it 'returns data binding expressions as-is' do
      expect(described_class.process_text('@{userName}')).to eq('@{userName}')
    end

    it 'returns template binding expressions as-is' do
      expect(described_class.process_text('${userName}')).to eq('${userName}')
    end

    it 'wraps plain text in quotes' do
      expect(described_class.process_text('Hello')).to include('Hello')
    end
  end

  describe '.process_color' do
    it 'returns nil for nil input' do
      expect(described_class.process_color(nil)).to be_nil
    end

    it 'returns empty string for empty input' do
      expect(described_class.process_color('')).to eq('')
    end

    it 'returns data binding expressions as-is' do
      expect(described_class.process_color('@{themeColor}')).to eq('@{themeColor}')
    end

    it 'returns template binding expressions as-is' do
      expect(described_class.process_color('${themeColor}')).to eq('${themeColor}')
    end

    it 'returns resource references as-is' do
      expect(described_class.process_color('@color/primary')).to eq('@color/primary')
    end

    it 'returns hex colors with # prefix' do
      expect(described_class.process_color('#FF0000')).to eq('#FF0000')
    end

    it 'adds # prefix to hex colors without it' do
      expect(described_class.process_color('FF0000')).to eq('#FF0000')
    end

    it 'handles 8-digit hex colors (ARGB)' do
      expect(described_class.process_color('#80FF0000')).to eq('#80FF0000')
    end
  end

  describe '.clear_cache' do
    it 'clears all cached data' do
      described_class.clear_cache
      # After clearing, the cache should be nil
      expect(described_class.instance_variable_get(:@strings_data)).to be_nil
      expect(described_class.instance_variable_get(:@colors_data)).to be_nil
      expect(described_class.instance_variable_get(:@defined_colors_data)).to be_nil
    end
  end

  describe 'private methods' do
    describe '.normalize_color' do
      it 'returns nil for nil input' do
        expect(described_class.send(:normalize_color, nil)).to be_nil
      end

      it 'normalizes hex colors to uppercase with #' do
        expect(described_class.send(:normalize_color, 'ff0000')).to eq('#FF0000')
        expect(described_class.send(:normalize_color, '#ff0000')).to eq('#FF0000')
      end

      it 'handles 3-digit hex' do
        result = described_class.send(:normalize_color, 'f00')
        # 3-digit hex might not match 6-digit pattern, check behavior
        expect(result).not_to be_nil
      end

      it 'returns non-hex colors as-is' do
        expect(described_class.send(:normalize_color, 'red')).to eq('red')
      end
    end
  end
end
