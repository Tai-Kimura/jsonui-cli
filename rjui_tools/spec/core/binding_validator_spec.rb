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

    context 'with ?? default (official support, binding SSoT track 15)' do
      it 'accepts a single ?? default with a literal' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'userName', 'type' => 'String' }] },
            { 'type' => 'Label', 'text' => "@{userName ?? 'Guest'}" }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'rejects more than one ?? (binding-double-default)' do
        component = {
          'type' => 'Label',
          'text' => "@{a ?? 'x' ?? 'y'}"
        }
        messages = validator.validate(component)
        expect(messages.any? { |m| m.include?('[binding-double-default]') }).to be true
        expect(validator.has_errors?).to be true
      end
    end

    context 'with canonical negation and two-way rules' do
      it 'accepts @{!flag} on a boolean attribute (hidden)' do
        component = {
          'type' => 'View',
          'hidden' => '@{!flag}'
        }
        messages = validator.validate(component)
        expect(messages.select { |m| m.include?('binding-negation-context') }).to be_empty
        expect(messages.select { |m| m.include?('negation operator') }).to be_empty
      end

      it 'rejects @{!flag} on a non-boolean known attribute (binding-negation-context)' do
        component = {
          'type' => 'Label',
          'text' => '@{!flag}'
        }
        messages = validator.validate(component)
        expect(messages.any? { |m| m.include?('[binding-negation-context]') }).to be true
      end

      it 'rejects a dotted path on a two-way attribute (binding-two-way-complex)' do
        component = {
          'type' => 'TextField',
          'text' => '@{user.email}'
        }
        messages = validator.validate(component)
        expect(messages.any? { |m| m.include?('[binding-two-way-complex]') }).to be true
      end

      it 'accepts a flat identifier on a two-way attribute' do
        component = {
          'type' => 'TextField',
          'text' => '@{email}'
        }
        messages = validator.validate(component)
        expect(messages.select { |m| m.include?('binding-two-way-complex') }).to be_empty
      end
    end

    context 'with Collection cell parent-scope dependence' do
      it 'warns when a cell binds a parent-screen data key (binding-cell-parent-scope)' do
        component = {
          'type' => 'View',
          'data' => [
            { 'name' => 'screenTitle', 'class' => 'String' },
            { 'name' => 'items', 'class' => 'Array' }
          ],
          'child' => [
            { 'type' => 'Label', 'text' => '@{screenTitle}' },
            {
              'type' => 'Collection',
              'items' => '@{items}',
              'sections' => [
                { 'cell' => { 'type' => 'Label', 'text' => '@{screenTitle}' } }
              ]
            }
          ]
        }
        messages = validator.validate(component)
        expect(messages.any? { |m| m.include?('[binding-cell-parent-scope]') }).to be true
      end

      it 'does not warn for item-scope (data.-prefixed) cell bindings' do
        component = {
          'type' => 'View',
          'data' => [{ 'name' => 'items', 'class' => 'Array' }],
          'child' => [
            {
              'type' => 'Collection',
              'items' => '@{items}',
              'sections' => [
                { 'cell' => { 'type' => 'Label', 'text' => '@{data.title}' } }
              ]
            }
          ]
        }
        messages = validator.validate(component)
        expect(messages.select { |m| m.include?('binding-cell-parent-scope') }).to be_empty
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

      it 'warns about zero-argument function call' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'items', 'type' => '[String]' }] },
            { 'type' => 'Label', 'text' => '@{items.first()}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings.any? { |w| w.include?('function call - move to ViewModel computed property') }).to be true
      end

      it 'warns about standalone zero-argument function call' do
        component = {
          'type' => 'Label',
          'text' => '@{getName()}'
        }
        warnings = validator.validate(component)
        expect(warnings.any? { |w| w.include?('function call - move to ViewModel computed property') }).to be true
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
    context 'with a handler referenced only from partialAttributes' do
      let(:component) do
        {
          'type' => 'View',
          'data' => [
            { 'name' => 'onNavigate', 'class' => '() => void' },
            { 'name' => 'reallyUnused', 'class' => 'string' }
          ],
          'child' => [
            {
              'type' => 'Label', 'text' => 'See the guide',
              'partialAttributes' => [{ 'range' => 'guide', 'onclick' => 'onNavigate' }]
            }
          ]
        }
      end

      # A partial handler is an ordinary handler reference, just nested one
      # level deeper. The scan did not descend into partialAttributes, so
      # declaring the handler warned and omitting it broke the generated
      # Data type — no spelling satisfied the zero-warning gate.
      it 'counts a partial onclick as a use' do
        warnings = validator.validate(component, 'Test.json')
        expect(warnings.none? { |w| w.include?("'onNavigate'") && w.include?('never used') }).to be true
      end

      it 'still reports a genuinely unused property' do
        warnings = validator.validate(component, 'Test.json')
        expect(warnings.any? { |w| w.include?("'reallyUnused'") && w.include?('never used') }).to be true
      end
    end

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

    context 'with dot-path bindings (root-segment resolution)' do
      it 'does not warn when the root variable of a dot-path is defined' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'user', 'type' => 'Object' }] },
            { 'type' => 'Label', 'text' => '@{user.name}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings.select { |w| w.include?('not defined in data') }).to be_empty
      end

      it 'marks the root variable as used (no unused-data warning for dot-path access)' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'user', 'type' => 'Object' }] },
            { 'type' => 'Label', 'text' => '@{user.name}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings.any? { |w| w.include?('never used') && w.include?("'user'") }).to be false
      end

      it 'warns about the undefined root only, never the path segments' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'other', 'type' => 'String' }] },
            { 'type' => 'Label', 'text' => '@{user.name}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings.any? { |w| w.include?("'user'") && w.include?('not defined in data') }).to be true
        expect(warnings.any? { |w| w.include?("'name'") }).to be false
      end

      it 'resolves bracket-indexed paths to their root variable' do
        component = {
          'type' => 'View',
          'child' => [
            { 'data' => [{ 'name' => 'items', 'type' => 'Array' }] },
            { 'type' => 'Label', 'text' => '@{items[0].title}' }
          ]
        }
        warnings = validator.validate(component)
        expect(warnings.select { |w| w.include?('not defined in data') }).to be_empty
        expect(warnings.any? { |w| w.include?("'title'") }).to be false
      end
    end
  end
end
