# frozen_string_literal: true

require 'compose/helpers/import_manager'

RSpec.describe KjuiTools::Compose::Helpers::ImportManager do
  describe '.get_imports_map' do
    it 'returns a hash of imports' do
      result = described_class.get_imports_map
      expect(result).to be_a(Hash)
    end

    it 'contains common imports' do
      result = described_class.get_imports_map
      expect(result).to have_key(:lazy_column)
      expect(result).to have_key(:background)
      expect(result).to have_key(:clickable)
    end

    it 'uses default package name' do
      result = described_class.get_imports_map
      expect(result[:r_class]).to include('com.example.kotlinjsonui.sample.R')
    end

    it 'uses provided package name' do
      result = described_class.get_imports_map('com.custom.app')
      expect(result[:r_class]).to include('com.custom.app.R')
    end

    it 'returns array for multi-import keys' do
      result = described_class.get_imports_map
      expect(result[:shape]).to be_an(Array)
      expect(result[:constraint_layout]).to be_an(Array)
    end

    it 'returns string for single-import keys' do
      result = described_class.get_imports_map
      expect(result[:lazy_column]).to be_a(String)
      expect(result[:background]).to be_a(String)
    end

    it 'includes component imports' do
      result = described_class.get_imports_map
      expect(result[:selectbox_component]).to include('SelectBox')
      expect(result[:visibility_wrapper]).to include('VisibilityWrapper')
    end

    it 'includes compose imports' do
      result = described_class.get_imports_map
      expect(result[:box]).to include('Box')
      expect(result[:arrangement]).to include('Arrangement')
    end
  end

  describe '.update_imports' do
    let(:base_content) do
      <<~KOTLIN
        package com.example.app

        import androidx.compose.runtime.Composable
        import androidx.compose.ui.Modifier

        @Composable
        fun MyComponent() {
        }
      KOTLIN
    end

    it 'adds single import' do
      required_imports = Set.new([:background])
      result = described_class.update_imports(base_content.dup, required_imports)
      expect(result).to include('import androidx.compose.foundation.background')
    end

    it 'adds multiple imports' do
      required_imports = Set.new([:background, :clickable])
      result = described_class.update_imports(base_content.dup, required_imports)
      expect(result).to include('import androidx.compose.foundation.background')
      expect(result).to include('import androidx.compose.foundation.clickable')
    end

    it 'adds array imports' do
      required_imports = Set.new([:shape])
      result = described_class.update_imports(base_content.dup, required_imports)
      expect(result).to include('import androidx.compose.foundation.shape.RoundedCornerShape')
      expect(result).to include('import androidx.compose.ui.draw.clip')
    end

    it 'does not duplicate existing imports' do
      content = base_content.dup + "import androidx.compose.foundation.background\n"
      required_imports = Set.new([:background])
      result = described_class.update_imports(content, required_imports)
      expect(result.scan('import androidx.compose.foundation.background').length).to eq(1)
    end

    it 'handles empty required imports' do
      result = described_class.update_imports(base_content.dup, Set.new)
      expect(result).to eq(base_content)
    end

    it 'handles unknown import keys' do
      required_imports = Set.new([:unknown_import])
      result = described_class.update_imports(base_content.dup, required_imports)
      expect(result).to eq(base_content)
    end
  end
end
