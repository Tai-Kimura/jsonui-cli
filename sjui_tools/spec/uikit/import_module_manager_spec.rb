# frozen_string_literal: true

require 'uikit/import_module_manager'

RSpec.describe SjuiTools::UIKit::ImportModuleManager do
  describe '.add_type_import_mapping' do
    it 'adds a new type import mapping' do
      described_class.add_type_import_mapping('CustomView', 'CustomModule')
      expect(described_class.type_import_mapping['CustomView']).to eq('CustomModule')
    end
  end

  describe '.type_import_mapping' do
    it 'returns the mapping hash' do
      expect(described_class.type_import_mapping).to be_a(Hash)
      expect(described_class.type_import_mapping['Web']).to eq('WebKit')
    end
  end

  describe '#add_import_module_for_type' do
    let(:manager) { described_class.new }

    it 'adds import module for known type' do
      manager.add_import_module_for_type('Web')
      imports = manager.generate_import_statements

      expect(imports).to include('import WebKit')
    end

    it 'does nothing for unknown type' do
      manager.add_import_module_for_type('Unknown')
      imports = manager.generate_import_statements

      expect(imports).not_to include('import Unknown')
    end
  end

  describe '#reset' do
    let(:manager) { described_class.new }

    it 'clears import modules' do
      manager.add_import_module_for_type('Web')
      manager.reset
      imports = manager.generate_import_statements

      expect(imports).not_to include('import WebKit')
    end
  end

  describe '#generate_import_statements' do
    let(:manager) { described_class.new }

    it 'includes UIKit and SwiftJsonUI by default' do
      imports = manager.generate_import_statements

      expect(imports).to include('import UIKit')
      expect(imports).to include('import SwiftJsonUI')
    end

    it 'includes added imports' do
      manager.add_import_module_for_type('Web')
      imports = manager.generate_import_statements

      expect(imports).to include('import WebKit')
    end
  end
end
