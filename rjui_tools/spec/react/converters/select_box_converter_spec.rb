# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/select_box_converter'

RSpec.describe RjuiTools::React::Converters::SelectBoxConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic select with string items' do
      it 'generates select with options' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['Option 1', 'Option 2', 'Option 3'] })
        result = converter.convert
        expect(result).to include('<select')
        expect(result).to include('<option value="Option 1">Option 1</option>')
        expect(result).to include('<option value="Option 2">Option 2</option>')
        expect(result).to include('<option value="Option 3">Option 3</option>')
      end
    end

    context 'with hash items' do
      it 'generates options with value and text' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => [{ 'value' => '1', 'text' => 'First' }, { 'value' => '2', 'text' => 'Second' }] })
        result = converter.convert
        expect(result).to include('<option value="1">First</option>')
        expect(result).to include('<option value="2">Second</option>')
      end
    end

    context 'with items binding' do
      it 'generates dynamic options mapping' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => '@{options}' })
        result = converter.convert
        expect(result).to include('{data.options?.map((item) => {')
        expect(result).to include('{opt.text || opt.label}')
      end

      # Regression: rjui-selectbox-dynamic-items-assumes-object-shape +
      # rjui-selectbox-dynamic-object-branch-ts2339-on-string-items —
      # canonical items are a plain string array ([String], matching
      # SwiftJsonUI SelectBoxView), so the option row must branch on the
      # element shape, AND the branch must go through a widening cast so
      # string[] declarations don't narrow the object branch to `never`.
      # Object key/value use nullish fallbacks (?? not ||) so an empty-string
      # value ("all items" idiom) stays a valid key/value instead of
      # collapsing to undefined
      # (rjui-selectbox-object-items-empty-value-key-warning).
      it 'supports canonical string-array items via a widened typeof branch' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => '@{sortOptions}' })
        result = converter.convert
        expect(result).to include('const opt = item as string | number | { value?: string | number; id?: string | number; text?: string; label?: string };')
        expect(result).to include("typeof opt === 'object' && opt !== null")
        expect(result).to include('<option key={String(opt)} value={String(opt)}>{String(opt)}</option>')
        expect(result).to include("<option key={String(opt.value ?? opt.id ?? '')} value={String(opt.value ?? opt.id ?? '')}>{opt.text || opt.label}</option>")
        expect(result).not_to include('item.value')
        expect(result).not_to include('opt.value || opt.id')
      end

      it 'omits the TS cast in JavaScript mode' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => '@{sortOptions}' }, { 'use_tailwind' => true, 'typescript' => false })
        result = converter.convert
        expect(result).to include('const opt = item;')
        expect(result).not_to include(' as string')
      end
    end

    context 'with placeholder/hint/prompt' do
      it 'adds a selectable placeholder option (no disabled/hidden so picking clears value)' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'placeholder' => 'Select one...' })
        result = converter.convert
        expect(result).to include('<option value="">Select one...</option>')
        expect(result).not_to include('disabled hidden')
      end

      # Spec canonical `prompt` is the primary key, with hint/placeholder as
      # aliases. Match the iOS / Android SelectBox surfaces.
      it 'accepts prompt as the canonical primary key' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'prompt' => 'Pick a thing' })
        result = converter.convert
        expect(result).to include('<option value="">Pick a thing</option>')
      end

      it 'prefers prompt over hint and placeholder when multiple are present' do
        converter = create_converter(
          'class' => 'SelectBox',
          'items' => ['A', 'B'],
          'prompt' => 'from prompt',
          'hint' => 'from hint',
          'placeholder' => 'from placeholder'
        )
        result = converter.convert
        expect(result).to include('<option value="">from prompt</option>')
        expect(result).not_to include('from hint')
        expect(result).not_to include('from placeholder')
      end
    end

    context 'with selectedValue binding' do
      it 'generates value binding' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'selectedValue' => '@{selected}' })
        result = converter.convert
        expect(result).to include('value={data.selected}')
      end
    end

    # Regression: rjui-selectbox-selectedindex-binding-not-emitted —
    # selectedIndex is a two-way binding, so the <select> must be controlled:
    # the bound index resolves to the same value string the <option> rows emit.
    context 'with selectedIndex binding' do
      it 'emits a controlled value resolving dynamic items at the bound index' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => '@{groupFilterOptions}', 'selectedIndex' => '@{groupFilterIndex}' })
        result = converter.convert
        expect(result).to include('value={(() => { const sel = data.groupFilterOptions?.[data.groupFilterIndex ?? -1]')
        expect(result).to include("typeof sel === 'object' ? String(sel.value ?? sel.id ?? '') : String(sel ?? '')")
        expect(result).to include(' as string | number | { value?: string | number; id?: string | number } | undefined')
      end

      it 'omits the TS cast in JavaScript mode' do
        converter = create_converter(
          { 'class' => 'SelectBox', 'items' => '@{opts}', 'selectedIndex' => '@{idx}' },
          { 'use_tailwind' => true, 'typescript' => false }
        )
        result = converter.convert
        expect(result).to include('const sel = data.opts?.[data.idx ?? -1];')
        expect(result).not_to include(' as string')
      end

      it 'indexes into a static value list for static items' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'selectedIndex' => '@{selectedIdx}' })
        result = converter.convert
        expect(result).to include("value={['A', 'B'][data.selectedIdx ?? -1] ?? ''}")
      end

      it 'uses option values for static hash items' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => [{ 'value' => '1', 'text' => 'First' }, { 'value' => '2', 'text' => 'Second' }], 'selectedIndex' => '@{idx}' })
        result = converter.convert
        expect(result).to include("value={['1', '2'][data.idx ?? -1] ?? ''}")
      end

      it 'prefers selectedValue when both bindings are present' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'selectedValue' => '@{val}', 'selectedIndex' => '@{idx}' })
        result = converter.convert
        expect(result).to include('value={data.val}')
        expect(result).not_to include('data.idx ?? -1')
      end
    end

    context 'with static default value' do
      it 'generates defaultValue' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'value' => 'B' })
        result = converter.convert
        expect(result).to include('defaultValue="B"')
      end
    end

    context 'with onChange handler' do
      it 'generates onChange with optional chaining' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A', 'B'], 'onChange' => '@{handleChange}' })
        result = converter.convert
        expect(result).to include('onChange={(e) => data.handleChange?.(e.target.value)}')
      end
    end

    context 'with borderColor' do
      it 'applies border color' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'borderColor' => '#CCCCCC' })
        result = converter.convert
        expect(result).to include('border-[#CCCCCC]')
      end
    end

    context 'with fontColor' do
      it 'applies font color' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'fontColor' => '#333333' })
        result = converter.convert
        expect(result).to include('text-[#333333]')
      end
    end

    context 'with enabled=false' do
      it 'adds disabled state' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'enabled' => false })
        result = converter.convert
        expect(result).to include('disabled')
        expect(result).to include('opacity-50')
        expect(result).to include('cursor-not-allowed')
      end
    end

    context 'with enabled binding (regression: rjui-button-enabled-binding-compares-bool-to-string)' do
      it 'negates the boolean binding instead of comparing to "true"' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'enabled' => '@{isEditable}' })
        result = converter.convert
        expect(result).to include('disabled={!data.isEditable}')
        expect(result).not_to include('!== "true"')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'testId' => 'country-select' })
        result = converter.convert
        expect(result).to include('data-testid="country-select"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => ['A'], 'visibility' => '@{showSelect}' })
        result = converter.convert
        expect(result).to include('{data.showSelect !== "gone" &&')
      end
    end
  end
end
