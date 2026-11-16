# frozen_string_literal: true

require 'core/logger'

RSpec.describe KjuiTools::Core::Logger do
  describe '.info' do
    it 'prints message with indentation' do
      expect { described_class.info('Test message') }.to output(/  Test message/).to_stdout
    end
  end

  describe '.success' do
    it 'prints message with checkmark' do
      expect { described_class.success('Success message') }.to output(/✅ Success message/).to_stdout
    end
  end

  describe '.error' do
    it 'prints message with error icon' do
      expect { described_class.error('Error message') }.to output(/❌ Error message/).to_stdout
    end
  end

  describe '.warn' do
    it 'prints message with warning icon' do
      expect { described_class.warn('Warning message') }.to output(/⚠️  Warning message/).to_stdout
    end
  end

  describe '.debug' do
    context 'when DEBUG environment variable is set' do
      before do
        ENV['DEBUG'] = '1'
      end

      after do
        ENV.delete('DEBUG')
      end

      it 'prints debug message' do
        expect { described_class.debug('Debug message') }.to output(/🔍 Debug message/).to_stdout
      end
    end

    context 'when DEBUG environment variable is not set' do
      before do
        ENV.delete('DEBUG')
      end

      it 'does not print debug message' do
        expect { described_class.debug('Debug message') }.not_to output.to_stdout
      end
    end
  end

  describe '.newline' do
    it 'prints empty line' do
      expect { described_class.newline }.to output("\n").to_stdout
    end
  end
end
