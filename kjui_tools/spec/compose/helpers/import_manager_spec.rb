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

    # Regression: kjui-keyboardactions-import-missing.
    # `textfield_component.rb` calls `required_imports.add(:keyboard_actions)`
    # whenever it emits `keyboardActions = KeyboardActions(...)` for
    # nextFocus / onSubmit wiring. Without a corresponding IMPORTS_MAP
    # entry, the Set add was silently dropped and the generated
    # `*GeneratedView.kt` referenced `KeyboardActions` without an
    # import → kotlinc Unresolved reference.
    it 'maps :keyboard_actions to androidx.compose.foundation.text.KeyboardActions' do
      result = described_class.get_imports_map
      expect(result).to have_key(:keyboard_actions)
      expect(result[:keyboard_actions]).to eq(
        'import androidx.compose.foundation.text.KeyboardActions'
      )
    end

    # Regression: radio_component custom icons emit `Icons.Filled.<Name>` /
    # `Icons.Outlined.<Name>` under the :icons key. Icons.* icons are extension
    # properties, so the Icons object AND the filled/outlined wildcard
    # extension imports are all required — painterResource alone left the
    # generated view with Unresolved reference 'Icons'.
    it 'maps :icons to Icons object plus filled/outlined extension imports' do
      result = described_class.get_imports_map
      expect(result[:icons]).to include('import androidx.compose.material.icons.Icons')
      expect(result[:icons]).to include('import androidx.compose.material.icons.filled.*')
      expect(result[:icons]).to include('import androidx.compose.material.icons.outlined.*')
      expect(result[:icons]).to include('import androidx.compose.ui.res.painterResource')
    end

    # Regression: tabview_component registers :material_icons for tab icons
    # (`Icons.Filled.<Name>`), but the key had no IMPORTS_MAP entry, so the
    # add was silently dropped and TabView screens failed to compile.
    it 'maps :material_icons to Icons object plus filled extension imports' do
      result = described_class.get_imports_map
      expect(result).to have_key(:material_icons)
      expect(result[:material_icons]).to include('import androidx.compose.material.icons.Icons')
      expect(result[:material_icons]).to include('import androidx.compose.material.icons.filled.*')
    end

    # Regression: kjui-keyboardactions-import-missing (focus chain refactor).
    # `textfield_component` now emits `val focusRequester_<id> = remember {
    # FocusRequester() }` + `.focusRequester(focusRequester_<id>)`. Both
    # the class and the modifier function must resolve.
    it 'maps :focus_requester to both FocusRequester class and focusRequester modifier' do
      result = described_class.get_imports_map
      expect(result).to have_key(:focus_requester)
      expect(result[:focus_requester]).to be_an(Array)
      expect(result[:focus_requester]).to include('import androidx.compose.ui.focus.FocusRequester')
      expect(result[:focus_requester]).to include('import androidx.compose.ui.focus.focusRequester')
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
