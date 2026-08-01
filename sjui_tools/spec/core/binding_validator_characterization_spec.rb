# frozen_string_literal: true

require 'core/binding_validator'

# Characterization of BindingValidator paths not covered by
# binding_validator_spec: cell-scope portability, inferred attribute types,
# fontColor type checking, shared_data complexity, and the reporting helpers.
# Fixes current behavior ahead of the validator consolidation (W3-2).
RSpec.describe SjuiTools::Core::BindingValidator do
  subject(:validator) { described_class.new }

  describe 'reporting helpers' do
    it 'has no errors on a fresh validator' do
      expect(validator.has_errors?).to be(false)
    end

    it 'prints each warning with the SJUI Warning prefix' do
      validator.validate(
        'type' => 'Label',
        'data' => [{ 'name' => 'n', 'class' => 'String' }],
        'text' => '@{missing}'
      )
      expect { validator.print_warnings }
        .to output(/\[SJUI Warning\].*'missing' in 'Label\.text' is not defined/).to_stdout
    end
  end

  describe 'cell scope portability (binding-cell-parent-scope)' do
    it 'warns when an inline cell binds a parent screen data property' do
      warnings = validator.validate(
        'type' => 'View',
        'data' => [{ 'name' => 'parentProp', 'class' => 'String' }],
        'child' => [
          { 'type' => 'Collection',
            'sections' => [{ 'cell' => { 'type' => 'Label', 'text' => '@{parentProp}' } }] }
        ]
      )
      expect(warnings).to include(
        a_string_matching(/\[binding-cell-parent-scope\] Cell binding '@\{parentProp\}' in 'Label\.text' refers to parent screen data property 'parentProp'/)
      )
    end
  end

  describe '#infer_type for undeclared binding targets' do
    it 'infers callback signatures for event attributes' do
      expect(validator.send(:infer_type, 'v', 'onTabChange')).to eq('((Int) -> Void)?')
      expect(validator.send(:infer_type, 'v', 'onClick')).to eq('(() -> Void)?')
    end

    it 'infers collection shapes' do
      expect(validator.send(:infer_type, 'v', 'items')).to eq('CollectionDataSource')
      expect(validator.send(:infer_type, 'v', 'sections')).to eq('[Any]')
    end

    it 'infers scalar types for layout attributes' do
      expect(validator.send(:infer_type, 'v', 'selectedIndex')).to eq('Int')
      expect(validator.send(:infer_type, 'v', 'hidden')).to eq('Bool')
      expect(validator.send(:infer_type, 'v', 'topMargin')).to eq('CGFloat')
      expect(validator.send(:infer_type, 'v', 'paddingTop')).to eq('CGFloat')
    end

    it 'infers src by component family: URL string for Network*, Image otherwise' do
      expect(validator.send(:infer_type, 'v', 'src', 'NetworkImage')).to eq('String')
      expect(validator.send(:infer_type, 'v', 'src', 'Image')).to eq('Image')
    end
  end

  describe 'mode-scoped attributes are exempt from binding checks' do
    it 'skips bindings on attributes scoped to the other mode (widthWeight is UIKit-only)' do
      warnings = validator.validate(
        'type' => 'View',
        'data' => [{ 'name' => 'w', 'class' => 'Int' }],
        'widthWeight' => '@{w}'
      )
      expect(warnings).not_to include(a_string_matching(/widthWeight/))
    end
  end

  describe 'fontColor binding type check' do
    it 'warns when the bound property is neither Color nor String' do
      warnings = validator.validate(
        'type' => 'Label',
        'data' => [{ 'name' => 'c', 'class' => 'Int' }],
        'fontColor' => '@{c}'
      )
      expect(warnings).to include(
        a_string_matching(/'Label\.fontColor' binding '@\{c\}' has type 'Int' but should be 'Color' or 'String'/)
      )
    end
  end

  describe "include shared_data complexity" do
    it 'warns on complex expressions instead of resolving their variables' do
      warnings = validator.validate(
        'type' => 'View',
        'data' => [{ 'name' => 'a', 'class' => 'Int' }],
        'child' => [
          { 'type' => 'Include', 'include' => 'foo',
            'shared_data' => { 'k' => '@{a > 1 ? a : a}' } }
        ]
      )
      expect(warnings).to include(
        a_string_matching(/shared_data\.k' contains complex expression/)
      )
      expect(warnings).not_to include(a_string_matching(/'a > 1' .*not defined/))
    end
  end
end
