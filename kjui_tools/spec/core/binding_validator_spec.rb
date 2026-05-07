# frozen_string_literal: true

require 'core/binding_validator'

RSpec.describe KjuiTools::Core::BindingValidator do
  subject(:validator) { described_class.new }

  describe '#initialize' do
    it 'creates validator with empty warnings' do
      expect(validator.warnings).to be_empty
    end
  end

  describe '#validate' do
    context 'with simple property binding' do
      let(:json_data) do
        {
          'type' => 'Text',
          'data' => [{ 'name' => 'userName', 'class' => 'String' }],
          'text' => '@{userName}'
        }
      end

      it 'returns no warnings for simple binding' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with nested property binding' do
      let(:json_data) do
        {
          'type' => 'Text',
          'data' => [
            { 'name' => 'user', 'class' => 'User' },
            { 'name' => 'name', 'class' => 'String' }
          ],
          'text' => '@{user.name}'
        }
      end

      it 'returns no warnings for nested property access' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with safe call chaining' do
      let(:json_data) do
        {
          'type' => 'Text',
          'data' => [
            { 'name' => 'user', 'class' => 'User?' },
            { 'name' => 'name', 'class' => 'String' }
          ],
          'text' => '@{user?.name}'
        }
      end

      it 'returns no warnings for safe call chaining' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with action binding' do
      let(:json_data) do
        {
          'type' => 'Button',
          'data' => [{ 'name' => 'onButtonTap', 'class' => '(() -> Unit)?' }],
          'onTap' => '@{onButtonTap}'
        }
      end

      it 'returns no warnings for action binding' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with simple boolean negation' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [{ 'name' => 'isHidden', 'class' => 'Boolean' }],
          'visibility' => '@{!isHidden}'
        }
      end

      it 'returns no warnings for simple negation' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with simple array index' do
      let(:json_data) do
        {
          'type' => 'Text',
          'data' => [{ 'name' => 'items', 'class' => 'List<String>' }],
          'text' => '@{items[0]}'
        }
      end

      it 'returns no warnings for simple array index' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with data. prefix in Collection cell' do
      let(:json_data) do
        {
          'type' => 'Collection',
          'sections' => [
            {
              'cell' => {
                'type' => 'Text',
                'text' => '@{data.name}'
              }
            }
          ]
        }
      end

      it 'returns no warnings for data. prefix bindings' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end
  end

  describe 'business logic detection' do
    context 'with ternary operator' do
      let(:json_data) do
        {
          'type' => 'Text',
          'data' => [{ 'name' => 'isLoggedIn', 'class' => 'Boolean' }],
          'text' => '@{isLoggedIn ? "Welcome" : "Please login"}'
        }
      end

      it 'returns warning for ternary operator' do
        warnings = validator.validate(json_data, 'TestFile.json')
        expect(warnings.length).to eq(1)
        expect(warnings.first).to include('ternary operator')
        expect(warnings.first).to include('move condition logic to ViewModel')
      end
    end

    context 'with comparison operators' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [{ 'name' => 'count', 'class' => 'Int' }],
          'visibility' => '@{count > 0}'
        }
      end

      it 'returns warning for comparison operator' do
        warnings = validator.validate(json_data)
        expect(warnings.length).to eq(1)
        expect(warnings.first).to include('comparison operator')
      end
    end

    context 'with logical operators' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'isLoggedIn', 'class' => 'Boolean' },
            { 'name' => 'hasPermission', 'class' => 'Boolean' }
          ],
          'hidden' => '@{isLoggedIn && hasPermission}'
        }
      end

      it 'returns warning for && operator' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('logical operator')
      end
    end

    context 'with elvis operator' do
      let(:json_data) do
        {
          'type' => 'Text',
          'data' => [{ 'name' => 'userName', 'class' => 'String?' }],
          'text' => '@{userName ?: "Guest"}'
        }
      end

      it 'returns warning for elvis operator or ternary' do
        warnings = validator.validate(json_data)
        # Elvis operator ?: matches both elvis and ternary patterns
        expect(warnings.first).to match(/elvis operator|ternary operator/)
      end
    end

    context 'with method call with arguments' do
      let(:json_data) do
        {
          'type' => 'Text',
          'data' => [
            { 'name' => 'date', 'class' => 'Date' },
            { 'name' => 'format', 'class' => 'String' }
          ],
          'text' => '@{date.format("yyyy-MM-dd")}'
        }
      end

      it 'returns warning for method call with arguments' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('method call with arguments')
      end
    end

    context 'with string interpolation' do
      let(:json_data) do
        {
          'type' => 'Text',
          'data' => [
            { 'name' => 'firstName', 'class' => 'String' },
            { 'name' => 'lastName', 'class' => 'String' }
          ],
          'text' => '@{"$firstName $lastName"}'
        }
      end

      it 'returns warning for string interpolation' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('string interpolation')
      end
    end

    context 'with not-null assertion' do
      let(:json_data) do
        {
          'type' => 'Text',
          'data' => [{ 'name' => 'optionalValue', 'class' => 'String?' }],
          'text' => '@{optionalValue!!}'
        }
      end

      it 'returns warning for not-null assertion' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('not-null assertion')
      end
    end

    context 'with range operator' do
      let(:json_data) do
        {
          'type' => 'View',
          'items' => '@{0..10}'
        }
      end

      it 'returns warning for range operator' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('range operator')
      end
    end
  end

  describe 'recursive validation' do
    context 'with children array' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [{ 'name' => 'count', 'class' => 'Int' }],
          'child' => [
            {
              'type' => 'Text',
              'text' => '@{count > 0 ? "Has items" : "Empty"}'
            }
          ]
        }
      end

      it 'validates children and returns warnings' do
        warnings = validator.validate(json_data)
        expect(warnings.length).to be >= 1
        expect(warnings.any? { |w| w.include?('ternary operator') }).to be true
      end
    end

    context 'with nested children' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'a', 'class' => 'Boolean' },
            { 'name' => 'b', 'class' => 'Boolean' }
          ],
          'child' => [
            {
              'type' => 'View',
              'child' => [
                {
                  'type' => 'Text',
                  'text' => '@{a && b}'
                }
              ]
            }
          ]
        }
      end

      it 'validates deeply nested children' do
        warnings = validator.validate(json_data)
        expect(warnings.length).to eq(1)
        expect(warnings.first).to include('logical operator')
      end
    end

    context 'with sections (Collection/Table)' do
      let(:json_data) do
        {
          'type' => 'Collection',
          'data' => [
            { 'name' => 'isExpanded', 'class' => 'Boolean' }
          ],
          'sections' => [
            {
              'header' => {
                'type' => 'Text',
                'text' => '@{isExpanded ? "Hide" : "Show"}'
              },
              'cell' => {
                'type' => 'Text',
                'text' => '@{data.name}'
              }
            }
          ]
        }
      end

      it 'validates section components' do
        warnings = validator.validate(json_data)
        expect(warnings.length).to eq(1)
        expect(warnings.first).to include('ternary operator')
      end
    end
  end

  describe '#check_binding' do
    context 'with simple property' do
      it 'returns no warnings' do
        warnings = validator.check_binding('userName', 'text', 'Text')
        expect(warnings).to be_empty
      end
    end

    context 'with ternary operator' do
      it 'returns warning' do
        warnings = validator.check_binding('isActive ? "Yes" : "No"', 'text', 'Text')
        expect(warnings.first).to include('ternary operator')
      end
    end
  end

  describe 'file name in warnings' do
    let(:json_data) do
      {
        'type' => 'Text',
        'data' => [{ 'name' => 'count', 'class' => 'Int' }],
        'text' => '@{count > 0}'
      }
    end

    it 'includes file name in warning message' do
      warnings = validator.validate(json_data, 'MyScreen.json')
      expect(warnings.first).to include('[MyScreen.json]')
    end

    it 'works without file name' do
      warnings = validator.validate(json_data)
      expect(warnings.first).not_to include('[')
    end
  end

  describe 'skipped attributes' do
    context 'with data section' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'count', 'class' => 'Int' }
          ],
          'child' => [
            {
              'type' => 'Text',
              'text' => '@{count}'
            }
          ]
        }
      end

      it 'does not validate data section as binding' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with include' do
      let(:json_data) do
        {
          'type' => 'View',
          'include' => 'header',
          'child' => []
        }
      end

      it 'does not validate include as binding' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with style' do
      let(:json_data) do
        {
          'type' => 'View',
          'style' => 'primary_button',
          'child' => []
        }
      end

      it 'does not validate style as binding' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end
  end

  describe 'undefined variable detection' do
    context 'with undefined variable' do
      let(:json_data) do
        {
          'type' => 'Text',
          'text' => '@{undefinedVar}'
        }
      end

      it 'warns when binding variable is not defined in data' do
        warnings = validator.validate(json_data, 'Test.json')
        expect(warnings.length).to eq(1)
        expect(warnings.first).to include("Binding variable 'undefinedVar'")
        expect(warnings.first).to include('is not defined in data')
      end
    end

    context 'with multiple undefined variables' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [{ 'name' => 'definedVar', 'class' => 'String' }],
          'child' => [
            { 'type' => 'Text', 'text' => '@{definedVar}' },
            { 'type' => 'Text', 'text' => '@{undefinedVar1}' },
            { 'type' => 'Text', 'text' => '@{undefinedVar2}' }
          ]
        }
      end

      it 'warns for each undefined variable' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("'undefinedVar1'") }).to be true
        expect(warnings.any? { |w| w.include?("'undefinedVar2'") }).to be true
        expect(warnings.none? { |w| w.include?("'definedVar'") }).to be true
      end
    end

    context 'with type inference' do
      it 'suggests Boolean for isXxx variables' do
        json_data = { 'type' => 'View', 'hidden' => '@{isVisible}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "Boolean"')
      end

      it 'suggests (() -> Unit)? for onXxx variables' do
        json_data = { 'type' => 'Button', 'onTap' => '@{onSubmit}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "(() -> Unit)?"')
      end

      it 'suggests ((Int) -> Unit)? for onTabChange variable' do
        json_data = { 'type' => 'TabView', 'onTabChange' => '@{handleTabChange}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "((Int) -> Unit)?"')
      end

      it 'suggests ((Int) -> Unit)? for onTabChange attribute' do
        json_data = { 'type' => 'TabView', 'onTabChange' => '@{tabHandler}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "((Int) -> Unit)?"')
      end

      it 'suggests List<Any> for xxxItems variables' do
        json_data = { 'type' => 'View', 'items' => '@{menuItems}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "List<Any>"')
      end

      it 'suggests Int for xxxCount variables' do
        json_data = { 'type' => 'Text', 'text' => '@{itemCount}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "Int"')
      end
    end

    context 'with ViewModel class in data' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'class' => 'MyViewModel' },
            { 'name' => 'userName', 'class' => 'String' }
          ],
          'child' => [
            { 'type' => 'Text', 'text' => '@{userName}' }
          ]
        }
      end

      it 'ignores ViewModel class declarations in data' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end
  end

  describe '#has_warnings?' do
    it 'returns false when no warnings' do
      json_data = {
        'type' => 'Text',
        'data' => [{ 'name' => 'text', 'class' => 'String' }],
        'text' => '@{text}'
      }
      validator.validate(json_data)
      expect(validator.has_warnings?).to be false
    end

    it 'returns true when has warnings' do
      json_data = { 'type' => 'Text', 'text' => '@{undefined}' }
      validator.validate(json_data)
      expect(validator.has_warnings?).to be true
    end
  end

  describe 'unused data property detection' do
    context 'with unused data property' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'usedProp', 'class' => 'String' },
            { 'name' => 'unusedProp', 'class' => 'String' }
          ],
          'child' => [
            { 'type' => 'Text', 'text' => '@{usedProp}' }
          ]
        }
      end

      it 'warns for unused data property' do
        warnings = validator.validate(json_data, 'Test.json')
        expect(warnings.any? { |w| w.include?("'unusedProp'") && w.include?('never used') }).to be true
      end

      it 'does not warn for used data property' do
        warnings = validator.validate(json_data, 'Test.json')
        expect(warnings.none? { |w| w.include?("'usedProp'") && w.include?('never used') }).to be true
      end
    end

    context 'with property used in shared_data' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'headerTitle', 'class' => 'String' }
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
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?("'headerTitle'") && w.include?('never used') }).to be true
      end
    end

    context 'with property used in include data' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'itemName', 'class' => 'String' }
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
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?("'itemName'") && w.include?('never used') }).to be true
      end
    end

    context 'with multiple unused properties' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'unused1', 'class' => 'String' },
            { 'name' => 'unused2', 'class' => 'Int' },
            { 'name' => 'used', 'class' => 'Boolean' }
          ],
          'child' => [
            { 'type' => 'View', 'hidden' => '@{used}' }
          ]
        }
      end

      it 'warns for each unused property' do
        warnings = validator.validate(json_data)
        unused_warnings = warnings.select { |w| w.include?('never used') }
        expect(unused_warnings.length).to eq(2)
        expect(warnings.any? { |w| w.include?("'unused1'") }).to be true
        expect(warnings.any? { |w| w.include?("'unused2'") }).to be true
      end
    end
  end
end
