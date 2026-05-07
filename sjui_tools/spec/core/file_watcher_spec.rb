# frozen_string_literal: true

require 'core/file_watcher'
require 'fileutils'

RSpec.describe SjuiTools::Core::FileWatcher do
  let(:temp_dir) { File.realpath(Dir.mktmpdir('file_watcher_test')) }

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'stores directories and extensions' do
      watcher = described_class.new([temp_dir], extensions: ['json', 'swift'])
      expect(watcher.instance_variable_get(:@directories)).to eq([temp_dir])
      expect(watcher.instance_variable_get(:@extensions)).to eq(['json', 'swift'])
    end

    it 'filters out non-existent directories' do
      watcher = described_class.new([temp_dir, '/nonexistent/path'])
      expect(watcher.instance_variable_get(:@directories)).to eq([temp_dir])
    end

    it 'accepts single directory as string' do
      watcher = described_class.new(temp_dir)
      expect(watcher.instance_variable_get(:@directories)).to eq([temp_dir])
    end

    it 'stores callback block' do
      callback = proc { |file, type| }
      watcher = described_class.new(temp_dir, &callback)
      expect(watcher.instance_variable_get(:@callback)).to eq(callback)
    end

    it 'defaults to json extension' do
      watcher = described_class.new(temp_dir)
      expect(watcher.instance_variable_get(:@extensions)).to eq(['json'])
    end
  end

  describe '#start' do
    context 'with empty directories' do
      it 'does nothing' do
        watcher = described_class.new('/nonexistent/path')
        watcher.start
        expect(watcher.listener).to be_nil
      end
    end

    context 'with valid directories' do
      it 'creates listener' do
        watcher = described_class.new(temp_dir)
        watcher.start
        expect(watcher.listener).not_to be_nil
        watcher.stop
      end
    end
  end

  describe '#stop' do
    it 'stops the listener' do
      watcher = described_class.new(temp_dir)
      watcher.start
      expect { watcher.stop }.not_to raise_error
    end

    it 'handles nil listener' do
      watcher = described_class.new('/nonexistent/path')
      expect { watcher.stop }.not_to raise_error
    end
  end

  describe '#file_patterns (private)' do
    it 'creates regex patterns from extensions' do
      watcher = described_class.new(temp_dir, extensions: ['json', 'swift'])
      patterns = watcher.send(:file_patterns)
      
      expect(patterns.length).to eq(2)
      expect(patterns[0]).to eq(/\.json$/)
      expect(patterns[1]).to eq(/\.swift$/)
    end

    it 'escapes special characters' do
      watcher = described_class.new(temp_dir, extensions: ['a.b'])
      patterns = watcher.send(:file_patterns)
      
      expect(patterns.first).to eq(/\.a\.b$/)
    end
  end

  describe '#should_process? (private)' do
    let(:watcher) { described_class.new(temp_dir, extensions: ['json']) }

    it 'returns true for matching extension' do
      expect(watcher.send(:should_process?, 'test.json')).to be true
    end

    it 'returns false for non-matching extension' do
      expect(watcher.send(:should_process?, 'test.swift')).to be false
    end

    it 'returns false for hidden files' do
      expect(watcher.send(:should_process?, '.hidden.json')).to be false
    end

    it 'returns false for files starting with dot' do
      expect(watcher.send(:should_process?, '.gitignore')).to be false
    end
  end

  describe '#handle_changes (private)' do
    it 'calls callback for modified files' do
      changes = []
      watcher = described_class.new(temp_dir, extensions: ['json']) do |file, type|
        changes << { file: file, type: type }
      end

      watcher.send(:handle_changes, ['test.json'], [], [])

      expect(changes.length).to eq(1)
      expect(changes.first[:file]).to eq('test.json')
      expect(changes.first[:type]).to eq(:modified)
    end

    it 'calls callback for added files' do
      changes = []
      watcher = described_class.new(temp_dir, extensions: ['json']) do |file, type|
        changes << { file: file, type: type }
      end

      watcher.send(:handle_changes, [], ['new.json'], [])

      expect(changes.first[:type]).to eq(:added)
    end

    it 'calls callback for removed files' do
      changes = []
      watcher = described_class.new(temp_dir, extensions: ['json']) do |file, type|
        changes << { file: file, type: type }
      end

      watcher.send(:handle_changes, [], [], ['deleted.json'])

      expect(changes.first[:type]).to eq(:removed)
    end

    it 'skips files with non-matching extensions' do
      changes = []
      watcher = described_class.new(temp_dir, extensions: ['json']) do |file, type|
        changes << { file: file, type: type }
      end

      watcher.send(:handle_changes, ['test.swift'], [], [])

      expect(changes).to be_empty
    end

    it 'skips hidden files' do
      changes = []
      watcher = described_class.new(temp_dir, extensions: ['json']) do |file, type|
        changes << { file: file, type: type }
      end

      watcher.send(:handle_changes, ['.hidden.json'], [], [])

      expect(changes).to be_empty
    end

    it 'handles duplicate files in multiple lists' do
      changes = []
      watcher = described_class.new(temp_dir, extensions: ['json']) do |file, type|
        changes << { file: file, type: type }
      end

      watcher.send(:handle_changes, ['test.json'], ['test.json'], [])

      expect(changes.length).to eq(1)
    end
  end
end
