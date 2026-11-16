# frozen_string_literal: true

require 'swiftui/setup/hotloader_generator'

RSpec.describe SjuiTools::SwiftUI::Setup::HotLoaderGenerator do
  let(:temp_dir) { File.realpath(Dir.mktmpdir('hotloader_gen_test')) }
  let(:output_path) { File.join(temp_dir, 'HotLoaderSetup.swift') }

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '.generate' do
    it 'creates the HotLoaderSetup.swift file' do
      described_class.generate(output_path)

      expect(File.exist?(output_path)).to be true
    end

    it 'includes SwiftUI import' do
      described_class.generate(output_path)
      content = File.read(output_path)

      expect(content).to include('import SwiftUI')
    end

    it 'includes SwiftJsonUI import' do
      described_class.generate(output_path)
      content = File.read(output_path)

      expect(content).to include('import SwiftJsonUI')
    end

    it 'defines HotLoaderSetup struct' do
      described_class.generate(output_path)
      content = File.read(output_path)

      expect(content).to include('public struct HotLoaderSetup')
    end

    it 'includes configure method' do
      described_class.generate(output_path)
      content = File.read(output_path)

      expect(content).to include('public static func configure()')
    end

    it 'includes disable method' do
      described_class.generate(output_path)
      content = File.read(output_path)

      expect(content).to include('public static func disable()')
    end

    it 'defines HotLoaderModifier' do
      described_class.generate(output_path)
      content = File.read(output_path)

      expect(content).to include('public struct HotLoaderModifier: ViewModifier')
    end

    it 'includes enableHotLoader extension' do
      described_class.generate(output_path)
      content = File.read(output_path)

      expect(content).to include('public func enableHotLoader()')
    end

    it 'includes DEBUG preprocessor directives' do
      described_class.generate(output_path)
      content = File.read(output_path)

      expect(content).to include('#if DEBUG')
      expect(content).to include('#endif')
    end

    it 'includes HotLoader configuration' do
      described_class.generate(output_path)
      content = File.read(output_path)

      expect(content).to include('HotLoader.instance.isHotLoadEnabled')
    end

    it 'outputs success message' do
      expect { described_class.generate(output_path) }.to output(/Generated HotLoader setup file/).to_stdout
    end
  end
end
