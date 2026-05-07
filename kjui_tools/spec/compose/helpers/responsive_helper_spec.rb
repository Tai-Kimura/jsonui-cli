# frozen_string_literal: true

require 'compose/helpers/responsive_helper'

RSpec.describe KjuiTools::Compose::Helpers::ResponsiveHelper do
  let(:required_imports) { Set.new }

  describe '.responsive?' do
    it 'returns true for component with responsive block' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'responsive' => { 'regular' => { 'orientation' => 'horizontal' } }
      }
      expect(described_class.responsive?(component)).to be true
    end

    it 'returns false for component without responsive block' do
      component = { 'type' => 'View', 'orientation' => 'vertical' }
      expect(described_class.responsive?(component)).to be false
    end

    it 'returns false for nil' do
      expect(described_class.responsive?(nil)).to be false
    end
  end

  describe '.build_condition' do
    it 'returns nil for nil size class (default)' do
      expect(described_class.build_condition(nil)).to be_nil
    end

    it 'returns Compact condition for compact' do
      result = described_class.build_condition('compact')
      expect(result).to eq('windowSizeClass.widthSizeClass == WindowWidthSizeClass.Compact')
    end

    it 'returns Medium condition for medium' do
      result = described_class.build_condition('medium')
      expect(result).to eq('windowSizeClass.widthSizeClass == WindowWidthSizeClass.Medium')
    end

    it 'returns Expanded condition for regular' do
      result = described_class.build_condition('regular')
      expect(result).to eq('windowSizeClass.widthSizeClass == WindowWidthSizeClass.Expanded')
    end

    it 'returns landscape condition for landscape' do
      result = described_class.build_condition('landscape')
      expect(result).to eq('isLandscape')
    end

    it 'returns compound condition for regular-landscape' do
      result = described_class.build_condition('regular-landscape')
      expect(result).to eq('windowSizeClass.widthSizeClass == WindowWidthSizeClass.Expanded && isLandscape')
    end

    it 'returns compound condition for compact-landscape' do
      result = described_class.build_condition('compact-landscape')
      expect(result).to eq('windowSizeClass.widthSizeClass == WindowWidthSizeClass.Compact && isLandscape')
    end

    it 'returns compound condition for medium-landscape' do
      result = described_class.build_condition('medium-landscape')
      expect(result).to eq('windowSizeClass.widthSizeClass == WindowWidthSizeClass.Medium && isLandscape')
    end
  end

  describe '.add_responsive_imports' do
    it 'adds window_size_class and local_configuration imports' do
      imports = Set.new
      described_class.add_responsive_imports(imports)
      expect(imports).to include(:window_size_class)
      expect(imports).to include(:local_configuration)
    end

    it 'handles nil imports set gracefully' do
      expect { described_class.add_responsive_imports(nil) }.not_to raise_error
    end
  end

  describe '.build_if_else_chain' do
    it 'generates if/else chain for multiple branches' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 },
          'landscape' => { 'spacing' => 16 },
          'regular-landscape' => { 'orientation' => 'horizontal', 'spacing' => 32 }
        }
      }

      branches = JsonUIShared::ResponsiveResolver.build_branches(component)

      result = described_class.build_if_else_chain(branches, 0, required_imports) do |attrs, depth, _imports|
        "#{' ' * (depth * 4)}// #{attrs['orientation'] || 'vertical'} spacing=#{attrs['spacing']}"
      end

      expect(result).to include('isLandscape')
      expect(result).to include('WindowWidthSizeClass.Expanded')
      expect(result).to include('} else if')
      expect(result).to include('} else {')
      expect(required_imports).to include(:window_size_class)
      expect(required_imports).to include(:local_configuration)
    end

    it 'generates code without conditions when no responsive overrides' do
      component = { 'type' => 'View', 'orientation' => 'vertical' }
      branches = JsonUIShared::ResponsiveResolver.build_branches(component)

      result = described_class.build_if_else_chain(branches, 0, required_imports) do |attrs, depth, _imports|
        "#{' ' * (depth * 4)}// default"
      end

      # No if/else when there are no conditional branches
      expect(result).not_to include('if (')
      expect(result).to include('// default')
    end

    it 'orders branches by priority (compound first)' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal' },
          'regular-landscape' => { 'orientation' => 'horizontal' }
        }
      }

      branches = JsonUIShared::ResponsiveResolver.build_branches(component)

      result = described_class.build_if_else_chain(branches, 0, required_imports) do |attrs, depth, _imports|
        "#{' ' * (depth * 4)}// branch"
      end

      # regular-landscape should appear before regular in conditions
      expanded_landscape_pos = result.index('Expanded && isLandscape')
      expanded_only_pos = result.index('Expanded)')
      # The compound condition (Expanded && isLandscape) should come first
      expect(expanded_landscape_pos).to be < expanded_only_pos
    end
  end

  describe '.generate_container_wrapper' do
    it 'generates a composable function with content parameter' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
        }
      }

      result = described_class.generate_container_wrapper(
        'ResponsiveContentArea', component, 0, required_imports
      ) do |attrs, depth, _imports|
        layout = attrs['orientation'] == 'horizontal' ? 'Row' : 'Column'
        "#{' ' * (depth * 4)}#{layout}() { content() }"
      end

      func_code = result[:function_code]
      expect(func_code).to include('@Composable')
      expect(func_code).to include('private fun ResponsiveContentArea(')
      expect(func_code).to include('windowSizeClass: WindowSizeClass,')
      expect(func_code).to include('content: @Composable () -> Unit')
      expect(func_code).to include('val isLandscape = LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE')
      expect(func_code).to include('WindowWidthSizeClass.Expanded')
      expect(func_code).to include('Row() { content() }')
      expect(func_code).to include('Column() { content() }')
    end

    it 'adds responsive imports' do
      component = {
        'type' => 'View',
        'responsive' => { 'regular' => { 'spacing' => 24 } }
      }

      described_class.generate_container_wrapper(
        'Test', component, 0, required_imports
      ) { |_attrs, _depth, _imports| '// code' }

      expect(required_imports).to include(:window_size_class)
      expect(required_imports).to include(:local_configuration)
    end
  end

  describe '.generate_leaf_wrapper' do
    it 'generates a composable function without content parameter' do
      component = {
        'type' => 'Label',
        'text' => 'Hello',
        'fontSize' => 14,
        'responsive' => {
          'regular' => { 'fontSize' => 20 }
        }
      }

      result = described_class.generate_leaf_wrapper(
        'ResponsiveLabel', component, 0, required_imports
      ) do |attrs, depth, _imports|
        "#{' ' * (depth * 4)}Text(fontSize = #{attrs['fontSize']}.sp)"
      end

      func_code = result[:function_code]
      expect(func_code).to include('@Composable')
      expect(func_code).to include('private fun ResponsiveLabel(')
      expect(func_code).to include('windowSizeClass: WindowSizeClass')
      expect(func_code).not_to include('content:')
      expect(func_code).to include('Text(fontSize = 20.sp)')
      expect(func_code).to include('Text(fontSize = 14.sp)')
    end

    it 'generates code for component without responsive' do
      component = {
        'type' => 'Label',
        'text' => 'Hello',
        'fontSize' => 14
      }

      result = described_class.generate_leaf_wrapper(
        'StaticLabel', component, 0, required_imports
      ) do |attrs, depth, _imports|
        "#{' ' * (depth * 4)}Text(fontSize = #{attrs['fontSize']}.sp)"
      end

      func_code = result[:function_code]
      # Should still generate the function but with no if/else
      expect(func_code).to include('Text(fontSize = 14.sp)')
      expect(func_code).not_to include('if (')
    end
  end

  describe '.indent' do
    it 'indents text by specified level' do
      expect(described_class.indent('hello', 1)).to eq('    hello')
      expect(described_class.indent('hello', 2)).to eq('        hello')
    end

    it 'returns text unchanged at level 0' do
      expect(described_class.indent('hello', 0)).to eq('hello')
    end

    it 'handles multi-line text' do
      result = described_class.indent("line1\nline2", 1)
      expect(result).to eq("    line1\n    line2")
    end

    it 'preserves empty lines' do
      result = described_class.indent("line1\n\nline2", 1)
      expect(result).to eq("    line1\n\n    line2")
    end
  end

  describe 'full integration scenario' do
    it 'handles the example from the task description' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 },
          'landscape' => { 'spacing' => 16 },
          'regular-landscape' => { 'orientation' => 'horizontal', 'spacing' => 32 }
        },
        'child' => [
          { 'type' => 'Text', 'text' => 'Hello' },
          { 'type' => 'Text', 'text' => 'World' }
        ]
      }

      result = described_class.generate_container_wrapper(
        'ResponsiveContentArea', component, 0, required_imports
      ) do |attrs, depth, _imports|
        layout = attrs['orientation'] == 'horizontal' ? 'Row' : 'Column'
        arrangement = layout == 'Row' ? 'horizontalArrangement' : 'verticalArrangement'
        spacing = attrs['spacing'] || 0
        "#{' ' * (depth * 4)}#{layout}(#{arrangement} = Arrangement.spacedBy(#{spacing}.dp)) { content() }"
      end

      func_code = result[:function_code]

      # Should have 3 conditional branches + 1 default
      # regular-landscape (highest priority compound)
      expect(func_code).to include('Expanded && isLandscape')
      expect(func_code).to include('Arrangement.spacedBy(32.dp)')

      # regular
      expect(func_code).to include('Expanded)')
      expect(func_code).to include('Arrangement.spacedBy(24.dp)')

      # landscape
      expect(func_code).to include('isLandscape')
      expect(func_code).to include('Arrangement.spacedBy(16.dp)')

      # default
      expect(func_code).to include('} else {')
      expect(func_code).to include('Arrangement.spacedBy(8.dp)')
    end
  end
end
