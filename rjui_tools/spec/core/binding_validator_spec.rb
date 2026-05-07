#!/usr/bin/env ruby

require_relative '../../lib/core/binding_validator'

RSpec.describe RjuiTools::Core::BindingValidator do
  let(:validator) { described_class.new }

  describe '#validate' do
    context 'with simple valid bindings and data defined' do
      it 'accepts simple property binding when data is defined' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'userName', 'type' => 'String' }] },
            { 'type' => 'Label', 'text' => '@{userName}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts action binding (onClick)' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'onButtonClick', 'type' => 'Function' }] },
            { 'type' => 'Button', 'onClick' => '@{onButtonClick}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts data. prefix binding (for Collection cells)' do
        component = {
          'type' => 'Label',
          'text' => '@{data.name}'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'warns about ternary operator as business logic' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'currentTab', 'type' => 'Number' }] },
            { 'type' => 'View', 'visibility' => "@{currentTab === 0 ? 'visible' : 'gone'}" }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.any? { |w| w.include?('ternary operator') }).to be true
      end
    end

    context 'with undefined binding variables (when data definitions exist)' do
      it 'warns about undefined variable when other data is defined' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
            { 'type' => 'Label', 'text' => '@{userName}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include("'userName'")
        expect(warnings.first).to include('is not defined in data')
      end

      it 'warns about undefined onClick handler when other data is defined' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
            { 'type' => 'Button', 'onClick' => '@{onButtonClick}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include("'onButtonClick'")
        expect(warnings.first).to include('is not defined in data')
        expect(warnings.first).to include('"class": "(() -> Void)?"')
      end

      it 'warns about ternary operator as business logic even with undefined variable' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
            { 'type' => 'View', 'visibility' => "@{currentTab === 0 ? 'visible' : 'gone'}" }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        # Should warn about ternary operator (business logic)
        expect(warnings.any? { |w| w.include?('ternary operator') }).to be true
      end

      it 'suggests correct type for array variables' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
            { 'type' => 'Collection', 'items' => '@{userItems}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('"class": "Array"')
      end

      it 'suggests correct type for boolean variables' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
            { 'type' => 'View', 'hidden' => '@{isHidden}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('"class": "Bool"')
      end

      it 'suggests ((Int) -> Void)? for onTabChange variable' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
            { 'type' => 'TabView', 'onTabChange' => '@{handleTabChange}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('"class": "((Int) -> Void)?"')
      end

      it 'suggests ((Int) -> Void)? for onTabChange attribute' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
            { 'type' => 'TabView', 'onTabChange' => '@{tabHandler}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('"class": "((Int) -> Void)?"')
      end
    end

    context 'without data definitions (ViewModel provides bindings)' do
      it 'does not warn about undefined variable when no data definitions exist' do
        component = {
          'type' => 'Label',
          'text' => '@{userName}'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'does not warn about undefined onClick handler when no data definitions exist' do
        component = {
          'type' => 'Button',
          'onClick' => '@{onButtonClick}'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with viewModel. prefix (not allowed)' do
      it 'warns about viewModel. prefix in text' do
        component = {
          'type' => 'Label',
          'text' => '@{viewModel.userName}'
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('viewModel. prefix')
      end
    end

    context 'with logical operators (business logic)' do
      it 'warns about AND operator' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [
              { 'name' => 'isLoggedIn', 'type' => 'Boolean' },
              { 'name' => 'hasPermission', 'type' => 'Boolean' }
            ] },
            { 'type' => 'View', 'hidden' => '@{isLoggedIn && hasPermission}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('logical operator')
      end
    end

    context 'with arithmetic operators (business logic)' do
      it 'warns about addition' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'count', 'type' => 'Number' }] },
            { 'type' => 'Label', 'text' => '@{count + 1}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('arithmetic operator')
      end
    end

    context 'with nil coalescing (business logic)' do
      it 'warns about nil coalescing operator' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'userName', 'type' => 'String' }] },
            { 'type' => 'Label', 'text' => "@{userName ?? 'Guest'}" }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('nil coalescing')
      end
    end

    context 'with function calls (business logic)' do
      it 'warns about function call with arguments' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'createdAt', 'type' => 'Date' }] },
            { 'type' => 'Label', 'text' => '@{formatDate(createdAt)}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('function call with arguments')
      end
    end

    context 'with nested components' do
      it 'validates child components and finds undefined variables when data exists' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
            {
              'type' => 'Label',
              'text' => '@{undefinedVar}'
            }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include("'undefinedVar'")
      end

      it 'finds data definitions in nested children' do
        component = {
          'type' => 'View',
          'child' => [
            {
              'type' => 'View',
              'child' => [
                { 'data' => [{ 'name' => 'deepVar', 'type' => 'String' }] },
                { 'type' => 'Label', 'text' => '@{deepVar}' }
              ]
            }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with file name context' do
      it 'includes file name in warning message' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
            { 'type' => 'Label', 'text' => '@{undefinedVar}' }
          ]
        }
        warnings = validator.validate(component, 'test_component.json')
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('[test_component.json]')
      end
    end

    context 'with non-binding values' do
      it 'ignores regular string values' do
        component = {
          'type' => 'Label',
          'text' => 'Hello World'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'ignores numeric values' do
        component = {
          'type' => 'View',
          'width' => 100
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'skipped attributes' do
      it 'skips data attribute' do
        component = {
          'type' => 'View',
          'data' => [{ 'name' => 'userName', 'type' => 'String' }],
          'child' => [
            { 'type' => 'Label', 'text' => '@{userName}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'skips style attribute' do
        component = {
          'type' => 'View',
          'style' => 'my_style'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with ViewModel class declaration' do
      it 'does not treat ViewModel class as data property but triggers data check when other data exists' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [
              { 'class' => 'MyViewModel', 'name' => 'viewModel' },
              { 'class' => 'String', 'name' => 'otherVar' }
            ] },
            { 'type' => 'Label', 'text' => '@{userName}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include("'userName'")
      end

      it 'does not warn when only ViewModel is defined (no other data)' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'class' => 'MyViewModel', 'name' => 'viewModel' }] },
            { 'type' => 'Label', 'text' => '@{userName}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end
  end

  describe '#check_binding' do
    it 'returns empty array for simple property' do
      warnings = validator.check_binding('userName', 'text', 'Label')
      expect(warnings).to be_empty
    end

    it 'returns warning for viewModel. prefix' do
      warnings = validator.check_binding('viewModel.userName', 'text', 'Label')
      expect(warnings).not_to be_empty
      expect(warnings.first).to include('viewModel. prefix')
    end
  end

  describe '#has_warnings?' do
    it 'returns false when no warnings' do
      component = {
        'type' => 'View',
        'child' => [
          { 'data' => [{ 'name' => 'name', 'type' => 'String' }] },
          { 'type' => 'Label', 'text' => '@{name}' }
        ]
      }
      validator.validate(component)
      expect(validator.has_warnings?).to be false
    end

    it 'returns true when there are warnings' do
      component = {
        'type' => 'View',
        'child' => [
          { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
          { 'type' => 'Label', 'text' => '@{undefinedVar}' }
        ]
      }
      validator.validate(component)
      expect(validator.has_warnings?).to be true
    end
  end

  describe '#print_warnings' do
    it 'prints warnings to stdout' do
      component = {
        'type' => 'View',
        'child' => [
          { 'data' => [{ 'name' => 'otherVar', 'class' => 'String' }] },
          { 'type' => 'Label', 'text' => '@{undefinedVar}' }
        ]
      }
      validator.validate(component)

      expect {
        validator.print_warnings
      }.to output(/\[RJUI Binding Warning\]/).to_stdout
    end
  end

  describe 'unused data property detection' do
    context 'with unused data property' do
      let(:component) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'usedProp', 'class' => 'string' },
            { 'name' => 'unusedProp', 'class' => 'string' }
          ],
          'child' => [
            { 'type' => 'Label', 'text' => '@{usedProp}' }
          ]
        }
      end

      it 'warns for unused data property' do
        warnings = validator.validate(component, 'Test.json')
        expect(warnings.any? { |w| w.include?("'unusedProp'") && w.include?('never used') }).to be true
      end

      it 'does not warn for used data property' do
        warnings = validator.validate(component, 'Test.json')
        expect(warnings.none? { |w| w.include?("'usedProp'") && w.include?('never used') }).to be true
      end
    end

    context 'with property used in shared_data' do
      let(:component) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'headerTitle', 'class' => 'string' }
          ],
          'child' => [
            {
              'include' => 'header',
              'shared_data' => {
                'title' => 'headerTitle'
              }
            }
          ]
        }
      end

      it 'does not warn for property used in shared_data' do
        warnings = validator.validate(component)
        expect(warnings.none? { |w| w.include?("'headerTitle'") && w.include?('never used') }).to be true
      end
    end

    context 'with property used in include data' do
      let(:component) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'itemName', 'class' => 'string' }
          ],
          'child' => [
            {
              'include' => 'item_view',
              'data' => {
                'name' => 'itemName'
              }
            }
          ]
        }
      end

      it 'does not warn for property used in include data' do
        warnings = validator.validate(component)
        expect(warnings.none? { |w| w.include?("'itemName'") && w.include?('never used') }).to be true
      end
    end

    context 'with multiple unused properties' do
      let(:component) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'unused1', 'class' => 'string' },
            { 'name' => 'unused2', 'class' => 'number' },
            { 'name' => 'used', 'class' => 'boolean' }
          ],
          'child' => [
            { 'type' => 'View', 'hidden' => '@{used}' }
          ]
        }
      end

      it 'warns for each unused property' do
        warnings = validator.validate(component)
        unused_warnings = warnings.select { |w| w.include?('never used') }
        expect(unused_warnings.length).to eq(2)
        expect(warnings.any? { |w| w.include?("'unused1'") }).to be true
        expect(warnings.any? { |w| w.include?("'unused2'") }).to be true
      end
    end
  end
end
