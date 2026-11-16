# frozen_string_literal: true

require 'core/logger'

RSpec.describe SjuiTools::Core::Logger do
  before do
    described_class.level = :info
  end

  describe '.level' do
    it 'defaults to :info' do
      described_class.instance_variable_set(:@level, nil)
      expect(described_class.level).to eq(:info)
    end

    it 'can be set' do
      described_class.level = :debug
      expect(described_class.level).to eq(:debug)
    end
  end

  describe '.set_level' do
    it 'sets valid level' do
      described_class.set_level(:debug)
      expect(described_class.level).to eq(:debug)
    end

    it 'sets level from string' do
      described_class.set_level('warn')
      expect(described_class.level).to eq(:warn)
    end

    it 'falls back to info for invalid level' do
      expect { described_class.set_level(:invalid) }.to output(/Invalid log level/).to_stdout
      expect(described_class.level).to eq(:info)
    end
  end

  describe '.error' do
    it 'outputs error message' do
      expect { described_class.error('test error') }.to output(/ERROR: test error/).to_stdout
    end
  end

  describe '.warn' do
    it 'outputs warning at warn level' do
      described_class.level = :warn
      expect { described_class.warn('test warning') }.to output(/WARNING: test warning/).to_stdout
    end

    it 'outputs warning at info level' do
      described_class.level = :info
      expect { described_class.warn('test warning') }.to output(/WARNING/).to_stdout
    end

    it 'does not output warning at error level' do
      described_class.level = :error
      expect { described_class.warn('test warning') }.not_to output.to_stdout
    end
  end

  describe '.info' do
    it 'outputs info at info level' do
      described_class.level = :info
      expect { described_class.info('test info') }.to output(/test info/).to_stdout
    end

    it 'does not output info at warn level' do
      described_class.level = :warn
      expect { described_class.info('test info') }.not_to output.to_stdout
    end
  end

  describe '.debug' do
    it 'outputs debug at debug level' do
      described_class.level = :debug
      expect { described_class.debug('test debug') }.to output(/DEBUG: test debug/).to_stdout
    end

    it 'does not output debug at info level' do
      described_class.level = :info
      expect { described_class.debug('test debug') }.not_to output.to_stdout
    end
  end

  describe '.success' do
    it 'outputs success at info level' do
      described_class.level = :info
      expect { described_class.success('done') }.to output(/✓ done/).to_stdout
    end

    it 'does not output success at warn level' do
      described_class.level = :warn
      expect { described_class.success('done') }.not_to output.to_stdout
    end
  end
end
