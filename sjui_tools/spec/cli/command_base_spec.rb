# frozen_string_literal: true

require 'cli/command_base'

RSpec.describe SjuiTools::CLI::CommandBase do
  let(:command) { described_class.new }

  describe '#run' do
    it 'raises NotImplementedError' do
      expect { command.run([]) }.to raise_error(NotImplementedError, /Subclasses must implement/)
    end
  end

  describe '#load_config' do
    before do
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({ 'mode' => 'swiftui' })
    end

    it 'loads config from ConfigManager' do
      result = command.send(:load_config)
      expect(result).to eq({ 'mode' => 'swiftui' })
    end
  end

  describe '#project_dir' do
    before do
      allow(SjuiTools::Core::ProjectFinder).to receive(:project_dir).and_return('/path/to/project')
    end

    it 'returns project directory' do
      result = command.send(:project_dir)
      expect(result).to eq('/path/to/project')
    end
  end

  describe '#project_exists?' do
    context 'when project file exists' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return('/path/to/project.xcodeproj')
      end

      it 'returns true' do
        expect(command.send(:project_exists?)).to be true
      end
    end

    context 'when project file does not exist' do
      before do
        allow(SjuiTools::Core::ProjectFinder).to receive(:project_file_path).and_return(nil)
      end

      it 'returns false' do
        expect(command.send(:project_exists?)).to be false
      end
    end
  end
end
