# frozen_string_literal: true

require 'core/binding_validator'

RSpec.describe SjuiTools::Core::BindingValidator do
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
          'type' => 'Label',
          'id' => 'label',
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
          'type' => 'Label',
          'id' => 'label',
          # W3-2: a dotted path counts as its ROOT variable only — 'name'
          # is a field of user, not a data property of its own.
          'data' => [
            { 'name' => 'user', 'class' => 'User' }
          ],
          'text' => '@{user.name}'
        }
      end

      it 'returns no warnings for nested property access' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with optional chaining' do
      let(:json_data) do
        {
          'type' => 'Label',
          'id' => 'label',
          'data' => [
            { 'name' => 'user', 'class' => 'User?' },
            { 'name' => 'name', 'class' => 'String' }
          ],
          'text' => '@{user?.name}'
        }
      end

      it 'returns no warnings for optional chaining' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with action binding' do
      let(:json_data) do
        {
          'type' => 'Button',
          'id' => 'button',
          'data' => [{ 'name' => 'onButtonTap', 'class' => '(() -> Void)?' }],
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
          'id' => 'view',
          'data' => [{ 'name' => 'isHidden', 'class' => 'Bool' }],
          'visibility' => '@{!isHidden}'
        }
      end

      # Negation generates invalid code (data.!isHidden); a computed property is required.
      it 'warns for negation operator' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('negation') }).to be true
      end
    end

    context 'with simple array index' do
      let(:json_data) do
        {
          'type' => 'Label',
          'id' => 'label',
          'data' => [{ 'name' => 'items', 'class' => '[String]' }],
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
                'type' => 'Label',
                'id' => 'cell_label',
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
          'type' => 'Label',
          'id' => 'label',
          'data' => [{ 'name' => 'isLoggedIn', 'class' => 'Bool' }],
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
          'id' => 'view',
          'data' => [{ 'name' => 'count', 'class' => 'Int' }],
          'visibility' => '@{count > 0}'
        }
      end

      it 'returns warning for comparison operator' do
        warnings = validator.validate(json_data)
        expect(warnings.length).to eq(1)
        expect(warnings.first).to include('comparison operator')
      end

      context 'with equality check' do
        let(:json_data) do
          {
            'type' => 'View',
            'data' => [{ 'name' => 'status', 'class' => 'String' }],
            'visibility' => '@{status == "active"}'
          }
        end

        it 'returns warning for equality operator' do
          warnings = validator.validate(json_data)
          expect(warnings.first).to include('comparison operator')
        end
      end

      context 'with not equal check' do
        let(:json_data) do
          {
            'type' => 'View',
            'data' => [{ 'name' => 'status', 'class' => 'String' }],
            'visibility' => '@{status != "deleted"}'
          }
        end

        it 'returns warning for not equal operator' do
          warnings = validator.validate(json_data)
          expect(warnings.first).to include('comparison operator')
        end
      end
    end

    context 'with logical operators' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'isLoggedIn', 'class' => 'Bool' },
            { 'name' => 'hasPermission', 'class' => 'Bool' }
          ],
          'hidden' => '@{isLoggedIn && hasPermission}'
        }
      end

      it 'returns warning for && operator' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('logical operator')
      end

      context 'with OR operator' do
        let(:json_data) do
          {
            'type' => 'View',
            'data' => [
              { 'name' => 'isAdmin', 'class' => 'Bool' },
              { 'name' => 'isModerator', 'class' => 'Bool' }
            ],
            'hidden' => '@{isAdmin || isModerator}'
          }
        end

        it 'returns warning for || operator' do
          warnings = validator.validate(json_data)
          expect(warnings.first).to include('logical operator')
        end
      end
    end

    context 'with nil coalescing (canonical `??` default — officially supported)' do
      # Intended diff (renderer-ssot-15-4): '@{path ?? default}' is canonical
      # (shared/core/binding_semantics.json) — the legacy "handle nil in
      # ViewModel" warning contradicted it and was removed.
      let(:json_data) do
        {
          'type' => 'Label',
          'id' => 'label',
          'data' => [{ 'name' => 'userName', 'class' => 'String?' }],
          'text' => '@{userName ?? "Guest"}'
        }
      end

      it 'does not warn for a single canonical default' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('nil coalescing') }).to be false
        expect(warnings.any? { |w| w.include?('binding-double-default') }).to be false
      end

      it 'errors on more than one ?? (binding-double-default)' do
        doubled = json_data.merge('text' => "@{userName ?? 'a' ?? 'b'}")
        warnings = validator.validate(doubled)
        expect(warnings.any? { |w| w.include?('binding-double-default') }).to be true
        expect(validator.errors.any? { |w| w.include?('binding-double-default') }).to be true
      end
    end

    context 'with method call with arguments' do
      let(:json_data) do
        {
          'type' => 'Label',
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

    context 'with zero-argument calls' do
      let(:json_data) do
        {
          'type' => 'Label',
          'data' => [
            { 'name' => 'items', 'class' => '[String]' }
          ],
          'text' => '@{items.first()}'
        }
      end

      it 'returns warning for zero-argument method call' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('method call - move to ViewModel computed property') }).to be true
      end

      it 'returns warning for standalone zero-argument function call' do
        warnings = validator.validate(json_data.merge('text' => '@{getName()}'))
        expect(warnings.any? { |w| w.include?('method call - move to ViewModel computed property') }).to be true
      end
    end

    context 'with string interpolation' do
      let(:json_data) do
        {
          'type' => 'Label',
          'data' => [
            { 'name' => 'firstName', 'class' => 'String' },
            { 'name' => 'lastName', 'class' => 'String' }
          ],
          'text' => '@{"\(firstName) \(lastName)"}'
        }
      end

      it 'returns warning for string interpolation' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('string interpolation')
      end
    end

    context 'with complex array subscript' do
      let(:json_data) do
        {
          'type' => 'Label',
          'data' => [
            { 'name' => 'items', 'class' => '[String]' },
            { 'name' => 'index', 'class' => 'Int' }
          ],
          'text' => '@{items[index + 1]}'
        }
      end

      it 'returns warning for arithmetic in array subscript' do
        warnings = validator.validate(json_data)
        # Can match either complex array subscript or arithmetic operator
        expect(warnings.first).to match(/complex array subscript|arithmetic operator/)
      end
    end

    context 'with type casting' do
      let(:json_data) do
        {
          'type' => 'Label',
          'data' => [{ 'name' => 'value', 'class' => 'Any' }],
          'text' => '@{value as? String}'
        }
      end

      it 'returns warning for type casting' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('type casting')
      end
    end

    context 'with force unwrap' do
      let(:json_data) do
        {
          'type' => 'Label',
          'data' => [{ 'name' => 'optionalValue', 'class' => 'String?' }],
          'text' => '@{optionalValue!}'
        }
      end

      it 'returns warning for force unwrap' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('force unwrap')
      end
    end

    context 'with range operator' do
      let(:json_data) do
        {
          'type' => 'View',
          'items' => '@{0...10}'
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
              'type' => 'Label',
              'text' => '@{count > 0 ? "Has items" : "Empty"}'
            }
          ]
        }
      end

      it 'validates children and returns warnings' do
        warnings = validator.validate(json_data)
        # Multiple patterns may match (ternary + comparison)
        expect(warnings.length).to be >= 1
        expect(warnings.any? { |w| w.include?('ternary operator') }).to be true
      end
    end

    context 'with nested children' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'a', 'class' => 'Bool' },
            { 'name' => 'b', 'class' => 'Bool' }
          ],
          'child' => [
            {
              'type' => 'View',
              'child' => [
                {
                  'type' => 'Label',
                  'id' => 'nested_label',
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
            { 'name' => 'isExpanded', 'class' => 'Bool' }
          ],
          'sections' => [
            {
              'header' => {
                'type' => 'Label',
                'id' => 'header_label',
                'text' => '@{isExpanded ? "Hide" : "Show"}'
              },
              'cell' => {
                'type' => 'Label',
                'id' => 'cell_label',
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

  describe 'nested attribute validation' do
    context 'with binding in nested object' do
      let(:json_data) do
        {
          'type' => 'Label',
          'id' => 'label',
          'data' => [{ 'name' => 'isDark', 'class' => 'Bool' }],
          'text' => 'Hello',
          'shadow' => {
            'color' => '@{isDark ? "#000000" : "#FFFFFF"}'
          }
        }
      end

      it 'validates bindings in nested objects' do
        warnings = validator.validate(json_data)
        expect(warnings.length).to eq(1)
        expect(warnings.first).to include('shadow.color')
      end
    end

    context 'with binding in array' do
      let(:json_data) do
        {
          'type' => 'View',
          'id' => 'view',
          'data' => [
            { 'name' => 'count', 'class' => 'Int' },
            { 'name' => 'simpleProp', 'class' => 'Bool' }
          ],
          'items' => [
            '@{count > 0}',
            '@{simpleProp}'
          ]
        }
      end

      it 'validates bindings in arrays' do
        warnings = validator.validate(json_data)
        expect(warnings.length).to eq(1)
        expect(warnings.first).to include('items[0]')
      end
    end
  end

  describe '#check_binding' do
    context 'with simple property' do
      it 'returns no warnings' do
        warnings = validator.check_binding('userName', 'text', 'Label')
        expect(warnings).to be_empty
      end
    end

    context 'with ternary operator' do
      it 'returns warning' do
        warnings = validator.check_binding('isActive ? "Yes" : "No"', 'text', 'Label')
        expect(warnings.first).to include('ternary operator')
      end
    end
  end

  describe 'file name in warnings' do
    let(:json_data) do
      {
        'type' => 'Label',
        'data' => [{ 'name' => 'count', 'class' => 'Int' }],
        'text' => '@{count > 0}'
      }
    end

    it 'includes file name in warning message' do
      warnings = validator.validate(json_data, 'MyScreen.json')
      expect(warnings.first).to include('MyScreen.json')
    end

    it 'includes view type when no id' do
      warnings = validator.validate(json_data)
      # Should show type when no id
      expect(warnings.first).to include('[Label]')
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
              'type' => 'Label',
              'id' => 'count_label',
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

  describe 'multiple warnings' do
    let(:json_data) do
      {
        'type' => 'View',
        'data' => [
          { 'name' => 'a', 'class' => 'Bool' },
          { 'name' => 'b', 'class' => 'Bool' },
          { 'name' => 'count', 'class' => 'Int' },
          { 'name' => 'value', 'class' => 'String?' }
        ],
        'visibility' => '@{a && b}',
        'child' => [
          {
            'type' => 'Label',
            'text' => '@{count > 0 ? "Yes" : "No"}'
          },
          {
            'type' => 'Label',
            'text' => '@{value ?? "default"}'
          }
        ]
      }
    end

    it 'collects all warnings' do
      warnings = validator.validate(json_data)
      # Multiple patterns can match same binding (ternary + comparison for the second child)
      expect(warnings.length).to be >= 2
      expect(warnings.any? { |w| w.include?('logical operator') }).to be true
      expect(warnings.any? { |w| w.include?('ternary operator') }).to be true
      # Intended diff (renderer-ssot-15-4): '@{value ?? "default"}' is
      # canonical and no longer warned
      expect(warnings.any? { |w| w.include?('nil coalescing') }).to be false
    end
  end

  describe 'undefined variable detection' do
    context 'with undefined variable' do
      let(:json_data) do
        {
          'type' => 'Label',
          'id' => 'label',
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
            { 'type' => 'Label', 'text' => '@{definedVar}' },
            { 'type' => 'Label', 'text' => '@{undefinedVar1}' },
            { 'type' => 'Label', 'text' => '@{undefinedVar2}' }
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
      it 'suggests Bool for isXxx variables' do
        json_data = { 'type' => 'View', 'hidden' => '@{isVisible}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "Bool"')
      end

      it 'suggests (() -> Void)? for onXxx variables' do
        json_data = { 'type' => 'Button', 'onTap' => '@{onSubmit}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "(() -> Void)?"')
      end

      it 'suggests ((Int) -> Void)? for onTabChange variable' do
        json_data = { 'type' => 'TabView', 'onTabChange' => '@{handleTabChange}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "((Int) -> Void)?"')
      end

      it 'suggests ((Int) -> Void)? for onTabChange attribute' do
        json_data = { 'type' => 'TabView', 'onTabChange' => '@{tabHandler}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "((Int) -> Void)?"')
      end

      it 'suggests [Any] for xxxItems variables' do
        json_data = { 'type' => 'View', 'items' => '@{menuItems}' }
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('"class": "[Any]"')
      end

      it 'suggests Int for xxxCount variables' do
        json_data = { 'type' => 'Label', 'text' => '@{itemCount}' }
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
            { 'type' => 'Label', 'id' => 'user_label', 'text' => '@{userName}' }
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
        'type' => 'Label',
        'id' => 'label',
        'data' => [{ 'name' => 'text', 'class' => 'String' }],
        'text' => '@{text}'
      }
      validator.validate(json_data)
      expect(validator.has_warnings?).to be false
    end

    it 'returns true when has warnings' do
      # 'undefined' joined the cross-language literal keywords in W3-2 —
      # use a real property name to trigger the undefined-variable warning.
      json_data = { 'type' => 'Label', 'id' => 'label', 'text' => '@{missingProp}' }
      validator.validate(json_data)
      expect(validator.has_warnings?).to be true
    end
  end

  describe 'visibility Boolean warning' do
    context 'with literal boolean true' do
      let(:json_data) do
        {
          'type' => 'View',
          'visibility' => true
        }
      end

      it 'warns against using Boolean for visibility' do
        warnings = validator.validate(json_data)
        expect(warnings.length).to eq(1)
        expect(warnings.first).to include('should use String enum')
        expect(warnings.first).to include('"visible", "gone", "invisible"')
      end
    end

    context 'with literal boolean false' do
      let(:json_data) do
        {
          'type' => 'View',
          'visibility' => false
        }
      end

      it 'warns against using Boolean for visibility' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('should use String enum')
      end
    end

    context 'with string boolean "true"' do
      let(:json_data) do
        {
          'type' => 'View',
          'visibility' => 'true'
        }
      end

      it 'warns against using Boolean string for visibility' do
        warnings = validator.validate(json_data)
        expect(warnings.first).to include('should use String enum')
      end
    end

    context 'with binding to boolean property (isXxx)' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [{ 'name' => 'isVisible', 'class' => 'Bool' }],
          'visibility' => '@{isVisible}'
        }
      end

      it 'warns that binding appears to be Boolean' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('appears to be Boolean') }).to be true
        expect(warnings.any? { |w| w.include?('"visible", "gone", or "invisible"') }).to be true
      end
    end

    context 'with binding to hasXxx property' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [{ 'name' => 'hasContent', 'class' => 'Bool' }],
          'visibility' => '@{hasContent}'
        }
      end

      it 'warns that binding appears to be Boolean' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('appears to be Boolean') }).to be true
      end
    end

    context 'with valid String visibility value' do
      let(:json_data) do
        {
          'type' => 'View',
          'visibility' => 'visible'
        }
      end

      it 'does not warn for valid visibility enum' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with valid visibility binding (xxxVisibility pattern)' do
      let(:json_data) do
        {
          'type' => 'View',
          'id' => 'view',
          'data' => [{ 'name' => 'contentVisibility', 'class' => 'String' }],
          'visibility' => '@{contentVisibility}'
        }
      end

      it 'does not warn for proper visibility property name' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end
  end

  describe 'confirmationDialog validation' do
    context 'with valid confirmationDialog bindings' do
      let(:json_data) do
        {
          'type' => 'Button',
          'id' => 'button',
          'text' => 'Delete',
          'data' => [
            { 'name' => 'showDeleteConfirm', 'class' => 'Bool' },
            { 'name' => 'deleteActions', 'class' => '(() -> AnyView)?' }
          ],
          'confirmationDialog' => {
            'isPresented' => '@{showDeleteConfirm}',
            'title' => 'Confirm Delete',
            'message' => 'Are you sure?',
            'actions' => '@{deleteActions}'
          }
        }
      end

      it 'returns no warnings for valid confirmationDialog' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with binding title and message' do
      let(:json_data) do
        {
          'type' => 'Button',
          'id' => 'button',
          'text' => 'Delete',
          'data' => [
            { 'name' => 'showConfirm', 'class' => 'Bool' },
            { 'name' => 'dialogTitle', 'class' => 'String' },
            { 'name' => 'dialogMessage', 'class' => 'String' },
            { 'name' => 'confirmActions', 'class' => '(() -> AnyView)?' }
          ],
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => '@{dialogTitle}',
            'message' => '@{dialogMessage}',
            'actions' => '@{confirmActions}'
          }
        }
      end

      it 'returns no warnings for binding title and message' do
        warnings = validator.validate(json_data)
        expect(warnings).to be_empty
      end
    end

    context 'with undefined confirmationDialog bindings' do
      let(:json_data) do
        {
          'type' => 'Button',
          'text' => 'Delete',
          'confirmationDialog' => {
            'isPresented' => '@{undefinedFlag}',
            'title' => 'Delete',
            'actions' => '@{undefinedActions}'
          }
        }
      end

      it 'warns for undefined binding variables' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("'undefinedFlag'") }).to be true
        expect(warnings.any? { |w| w.include?("'undefinedActions'") }).to be true
      end
    end

    context 'with type inference for confirmationDialog.actions' do
      let(:json_data) do
        {
          'type' => 'Button',
          'text' => 'Delete',
          'data' => [
            { 'name' => 'showConfirm', 'class' => 'Bool' }
          ],
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => 'Delete',
            'actions' => '@{deleteActions}'
          }
        }
      end

      it 'suggests (() -> AnyView)? for actions binding' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('"class": "(() -> AnyView)?"') }).to be true
      end
    end

    context 'with business logic in confirmationDialog bindings' do
      let(:json_data) do
        {
          'type' => 'Button',
          'text' => 'Delete',
          'data' => [
            { 'name' => 'isAdmin', 'class' => 'Bool' },
            { 'name' => 'showConfirm', 'class' => 'Bool' },
            { 'name' => 'actions', 'class' => '(() -> AnyView)?' }
          ],
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => '@{isAdmin ? "Admin Delete" : "Delete"}',
            'actions' => '@{actions}'
          }
        }
      end

      it 'warns for ternary operator in title binding' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('ternary operator') }).to be true
      end
    end
  end

  describe 'color type validation' do
    context 'with String type for color attributes' do
      let(:json_data) do
        {
          'type' => 'Label',
          'text' => 'Hello',
          'data' => [
            { 'name' => 'textColor', 'class' => 'String' },
            { 'name' => 'bgColor', 'class' => 'String' }
          ],
          'fontColor' => '@{textColor}',
          'background' => '@{bgColor}'
        }
      end

      # String is allowed for color attributes (color name resolved at runtime).
      it 'does not warn about String->Color type mismatch on fontColor' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("'Label.fontColor'") && w.include?("'String'") && w.include?("'Color'") }).to be false
      end

      # String is allowed for color attributes (color name resolved at runtime).
      it 'does not warn about String->Color type mismatch on background' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("'Label.background'") && w.include?("'String'") && w.include?("'Color'") }).to be false
      end
    end

    context 'with Color type for color attributes' do
      let(:json_data) do
        {
          'type' => 'Label',
          'id' => 'label',
          'text' => 'Hello',
          'data' => [
            { 'name' => 'textColor', 'class' => 'Color' },
            { 'name' => 'bgColor', 'class' => 'Color' }
          ],
          'fontColor' => '@{textColor}',
          'background' => '@{bgColor}'
        }
      end

      it 'does not warn for correct Color type' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('fontColor') || w.include?('background') }).to be false
      end
    end

    context 'with String type for borderColor' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'borderClr', 'class' => 'String' }
          ],
          'borderColor' => '@{borderClr}',
          'borderWidth' => 1
        }
      end

      # String is allowed for color attributes (color name resolved at runtime).
      it 'does not warn about String->Color type mismatch on borderColor' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("'View.borderColor'") && w.include?("'String'") }).to be false
      end
    end

    context 'with custom color attribute ending in Color' do
      let(:json_data) do
        {
          'type' => 'CustomView',
          'data' => [
            { 'name' => 'myCustomColor', 'class' => 'String' }
          ],
          'accentColor' => '@{myCustomColor}'
        }
      end

      # String is allowed for color attributes (color name resolved at runtime).
      it 'does not warn about String type on attributes ending in Color' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('accentColor') && w.include?("'String'") }).to be false
      end
    end
  end

  describe 'binding without id validation' do
    context 'with binding on component without id' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [{ 'name' => 'onTap', 'class' => '(() -> Void)?' }],
          'child' => [
            {
              'type' => 'Button',
              'text' => 'Tap me',
              'onClick' => '@{onTap}'
            }
          ]
        }
      end

      it 'warns when binding is used without id' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("has no 'id'") && w.include?('UIKit mode') }).to be true
      end
    end

    context 'with binding on component with id' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [{ 'name' => 'onTap', 'class' => '(() -> Void)?' }],
          'child' => [
            {
              'type' => 'Button',
              'id' => 'tap_button',
              'text' => 'Tap me',
              'onClick' => '@{onTap}'
            }
          ]
        }
      end

      it 'does not warn when binding has id' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("has no 'id'") }).to be false
      end
    end

    context 'with binding on root component' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [{ 'name' => 'onTap', 'class' => '(() -> Void)?' }],
          'onClick' => '@{onTap}'
        }
      end

      it 'warns for root component without id when it has bindings' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("has no 'id'") }).to be true
        expect(warnings.any? { |w| w.include?("onClick") && w.include?("@{onTap}") }).to be true
      end
    end

    context 'with non-binding attribute on component without id' do
      let(:json_data) do
        {
          'type' => 'View',
          'child' => [
            {
              'type' => 'Button',
              'text' => 'Static text'
            }
          ]
        }
      end

      it 'does not warn for non-binding attributes' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("has no 'id'") }).to be false
      end
    end

    context 'with multiple bindings on component without id' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'buttonText', 'class' => 'String' },
            { 'name' => 'onTap', 'class' => '(() -> Void)?' }
          ],
          'child' => [
            {
              'type' => 'Button',
              'text' => '@{buttonText}',
              'onClick' => '@{onTap}'
            }
          ]
        }
      end

      it 'warns for each binding attribute without id' do
        warnings = validator.validate(json_data)
        no_id_warnings = warnings.select { |w| w.include?("has no 'id'") }
        expect(no_id_warnings.length).to eq(2)
      end
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
            {
              'type' => 'Label',
              'id' => 'label',
              'text' => '@{usedProp}'
            }
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

    context 'with all properties used' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'userName', 'class' => 'String' },
            { 'name' => 'userAge', 'class' => 'Int' }
          ],
          'child' => [
            { 'type' => 'Label', 'id' => 'name_label', 'text' => '@{userName}' },
            { 'type' => 'Label', 'id' => 'age_label', 'text' => '@{userAge}' }
          ]
        }
      end

      it 'does not warn when all properties are used' do
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?('never used') }).to be true
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

    context 'with binding expression in shared_data' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'onTapAction', 'class' => '(() -> Void)?' }
          ],
          'child' => [
            {
              'include' => 'button_component',
              'shared_data' => {
                'onTap' => '@{onTapAction}'
              }
            }
          ]
        }
      end

      it 'does not warn for property used in binding expression in shared_data' do
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?("'onTapAction'") && w.include?('never used') }).to be true
      end
    end

    context 'with multiple unused properties' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'unused1', 'class' => 'String' },
            { 'name' => 'unused2', 'class' => 'Int' },
            { 'name' => 'used', 'class' => 'Bool' }
          ],
          'child' => [
            { 'type' => 'View', 'id' => 'view', 'hidden' => '@{used}' }
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

    context 'with property used in nested binding expression' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'user', 'class' => 'User' }
          ],
          'child' => [
            { 'type' => 'Label', 'id' => 'label', 'text' => '@{user.name}' }
          ]
        }
      end

      it 'does not warn for property used in nested expression' do
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?("'user'") && w.include?('never used') }).to be true
      end
    end

    context 'with no data section' do
      let(:json_data) do
        {
          'type' => 'View',
          'child' => [
            { 'type' => 'Label', 'text' => 'Static text' }
          ]
        }
      end

      it 'does not warn when there is no data section' do
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?('never used') }).to be true
      end
    end

    context 'with ViewModel class in data' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'class' => 'MyViewModel' },
            { 'name' => 'unusedProp', 'class' => 'String' }
          ],
          'child' => []
        }
      end

      it 'does not warn for ViewModel class (no name)' do
        warnings = validator.validate(json_data)
        unused_warnings = warnings.select { |w| w.include?('never used') }
        # Should only warn about unusedProp, not about ViewModel class
        expect(unused_warnings.length).to eq(1)
        expect(unused_warnings.first).to include("'unusedProp'")
      end
    end

    context 'with undefined variable in include data binding' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'definedProp', 'class' => 'String' }
          ],
          'child' => [
            {
              'include' => 'child_component',
              'data' => {
                'childProp' => '@{undefinedProp}'
              }
            }
          ]
        }
      end

      it 'warns for undefined variable in include data binding' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("'undefinedProp'") && w.include?('not defined') }).to be true
      end
    end

    context 'with undefined variable in include shared_data binding' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'definedProp', 'class' => 'String' }
          ],
          'child' => [
            {
              'include' => 'child_component',
              'shared_data' => {
                'sharedProp' => '@{anotherUndefinedProp}'
              }
            }
          ]
        }
      end

      it 'warns for undefined variable in include shared_data binding' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?("'anotherUndefinedProp'") && w.include?('not defined') }).to be true
      end
    end

    context 'with defined variable in include data binding' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'definedProp', 'class' => 'String' }
          ],
          'child' => [
            {
              'include' => 'child_component',
              'data' => {
                'childProp' => '@{definedProp}'
              }
            }
          ]
        }
      end

      it 'does not warn for defined variable in include data binding' do
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?("'definedProp'") && w.include?('not defined') }).to be true
      end

      it 'marks the property as used' do
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?("'definedProp'") && w.include?('never used') }).to be true
      end
    end

    context 'with complex expression in include data binding' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'isVisible', 'class' => 'Bool' }
          ],
          'child' => [
            {
              'include' => 'child_component',
              'data' => {
                'visibility' => '@{isVisible ? .visible : .gone}'
              }
            }
          ]
        }
      end

      it 'warns for complex ternary expression in include data' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('complex expression') && w.include?('visibility') }).to be true
      end
    end

    context 'with complex comparison in include data binding' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'count', 'class' => 'Int' }
          ],
          'child' => [
            {
              'include' => 'child_component',
              'data' => {
                'isEmpty' => '@{count == 0}'
              }
            }
          ]
        }
      end

      it 'warns for comparison expression in include data' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('complex expression') && w.include?('isEmpty') }).to be true
      end
    end

    context 'with method call in include data binding' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'items', 'class' => '[Item]' }
          ],
          'child' => [
            {
              'include' => 'child_component',
              'data' => {
                'itemName' => '@{items.first(where: { $0.id == 1 })?.name}'
              }
            }
          ]
        }
      end

      it 'warns for method call with arguments in include data' do
        warnings = validator.validate(json_data)
        expect(warnings.any? { |w| w.include?('complex expression') && w.include?('itemName') }).to be true
      end
    end

    context 'with simple property in include data binding' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'userName', 'class' => 'String' }
          ],
          'child' => [
            {
              'include' => 'child_component',
              'data' => {
                'name' => '@{userName}'
              }
            }
          ]
        }
      end

      it 'does not warn for simple property reference' do
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?('complex expression') }).to be true
      end
    end

    context 'with simple nested property in include data binding' do
      let(:json_data) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'user', 'class' => 'User' }
          ],
          'child' => [
            {
              'include' => 'child_component',
              'data' => {
                'name' => '@{user.name}'
              }
            }
          ]
        }
      end

      it 'does not warn for simple nested property reference' do
        warnings = validator.validate(json_data)
        expect(warnings.none? { |w| w.include?('complex expression') }).to be true
      end
    end
  end
  describe 'array-valued platform in attribute_definitions (regression)' do
    # Collection.onValueChange has platform: [swift, kotlin, react]. The old
    # `attr_def['platform'] != @my_platform` string comparison was always
    # true for Array values, silently excluding the attribute from binding
    # validation — its @{handler} usage was never collected and the data
    # property was wrongly reported as unused (surfaced by L1-normalized
    # layouts renaming onPageChanged -> onValueChange).
    it 'collects @{...} usage from attributes whose platform is an Array' do
      json_data = {
        'type' => 'View',
        'data' => [
          { 'name' => 'onPageChanged', 'class' => '((Int) -> Void)?' }
        ],
        'child' => [
          {
            'type' => 'Collection',
            'id' => 'pager',
            'onValueChange' => '@{onPageChanged}'
          }
        ]
      }
      warnings = validator.validate(json_data)
      expect(warnings.none? { |w| w.include?("'onPageChanged' is defined but never used") }).to be(true), warnings.inspect
    end
  end

  describe 'Embed structural rules (v1.5 nested params + isolated)' do
    def embed_layout(embed_attrs, data: [])
      {
        'type' => 'View',
        'id' => 'root',
        'data' => data,
        'child' => [
          { 'type' => 'Embed', 'id' => 'pane', 'screen' => 'foo' }.merge(embed_attrs)
        ]
      }
    end

    it 'accepts nested literal objects with scalar/binding leaves' do
      warnings = validator.validate(embed_layout(
        { 'params' => { 'profile' => { 'name' => '@{userName}', 'age' => 36 } } },
        data: [{ 'name' => 'userName', 'class' => 'String' }]
      ))
      expect(warnings.select { |w| w.include?('Embed.params') }).to be_empty, warnings.inspect
    end

    it 'warns on arrays anywhere in params' do
      warnings = validator.validate(embed_layout({
        'params' => { 'profile' => { 'tags' => %w[a b] } }
      }))
      expect(warnings).to include(a_string_matching(/Embed\.params\.profile\.tags.*array/))
    end

    it 'warns on non-camelCase keys at any level' do
      warnings = validator.validate(embed_layout({
        'params' => { 'profile' => { 'UserName' => 'x' } }
      }))
      expect(warnings).to include(a_string_matching(/Embed\.params\.profile\.UserName.*camelCase/))
    end

    it 'warns when a binding targets a dict-typed property (subtree binding)' do
      warnings = validator.validate(embed_layout(
        { 'params' => { 'profile' => '@{profileDict}' } },
        data: [{ 'name' => 'profileDict', 'class' => '[String: Any]' }]
      ))
      expect(warnings).to include(a_string_matching(/Embed\.params\.profile.*leaf-only/))
    end

    it 'warns on unknown navigationMode values' do
      warnings = validator.validate(embed_layout({ 'navigationMode' => 'floating' }))
      expect(warnings).to include(a_string_matching(/navigationMode.*unknown value 'floating'/))
    end

    it 'accepts isolated navigationMode without warnings' do
      warnings = validator.validate(embed_layout({ 'navigationMode' => 'isolated' }))
      expect(warnings.select { |w| w.include?('navigationMode') }).to be_empty, warnings.inspect
    end
  end

end
