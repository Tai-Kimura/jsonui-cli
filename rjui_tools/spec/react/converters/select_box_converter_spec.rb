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

    # An <option>'s own colour only reaches the dropdown popup; the CLOSED
    # control paints the prompt in its own inherited colour. So a declared
    # hintColor was invisible in the only state a non-interacting user sees —
    # measured as an inert conformance fixture (51-A). The `:has` variant is
    # the runtime condition in CSS, so the literal face needs no state.
    context 'with hintColor on the closed control' do
      it 'colours the closed control while the placeholder row is selected' do
        converter = create_converter(
          'class' => 'SelectBox', 'items' => ['A', 'B'],
          'prompt' => 'Choose', 'hintColor' => '#FF0000'
        )
        result = converter.convert
        expect(result).to include("[&:has(option:first-child:checked)]:text-[var(--jui-hint-color)]")
        expect(result).to include("'--jui-hint-color'")
      end

      it 'accepts the placeholderColor alias' do
        converter = create_converter(
          'class' => 'SelectBox', 'items' => ['A', 'B'],
          'prompt' => 'Choose', 'placeholderColor' => '#FF0000'
        )
        expect(converter.convert).to include('[&:has(option:first-child:checked)]:text-[var(--jui-hint-color)]')
      end

      it 'keeps the bound colour on the same custom property' do
        converter = create_converter(
          'class' => 'SelectBox', 'items' => ['A', 'B'],
          'prompt' => 'Choose', 'hintColor' => '@{hintColor}'
        )
        result = converter.convert
        expect(result).to include('[&:has(option:first-child:checked)]:text-[var(--jui-hint-color)]')
        expect(result).to include('ColorManager.resolveColor(data.hintColor)')
      end

      # No placeholder row, nothing for the variant to match — and a list box
      # has no closed state at all.
      it 'emits nothing without a placeholder row' do
        converter = create_converter('class' => 'SelectBox', 'items' => ['A', 'B'], 'hintColor' => '#FF0000')
        expect(converter.convert).not_to include('option:first-child:checked')
      end

      it 'emits nothing for a multiple select' do
        converter = create_converter(
          'class' => 'SelectBox', 'items' => ['A', 'B'],
          'prompt' => 'Choose', 'hintColor' => '#FF0000', 'multiple' => true
        )
        expect(converter.convert).not_to include('option:first-child:checked')
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

      # The write-back is a NUMBER both ways: the value side resolves the item
      # at the index, so reporting `e.target.value` (a string) contradicted
      # the declared `(value: number) => void` handler.
      it 'reports the selected INDEX back, not the option string' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => %w[A B], 'selectedIndex' => '@{idx}' })
        expect(converter.convert).to include('onChange={(e) => data.onIdxChange?.(e.target.selectedIndex)}')
      end

      # The placeholder row occupies DOM index 0, and picking it reports -1 —
      # the same "nothing selected" the value side renders for.
      it 'offsets the reported index past a placeholder row' do
        converter = create_converter({ 'class' => 'SelectBox', 'items' => %w[A B],
                                       'prompt' => 'Choose', 'selectedIndex' => '@{idx}' })
        expect(converter.convert).to include('onChange={(e) => data.onIdxChange?.(e.target.selectedIndex - 1)}')
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

    # `multiple` is declared platform: react — a list box is a web-only control
    # shape, and the value it reports is an array, not a string.
    context 'multiple' do
      def listbox(extra = {})
        create_converter(
          { 'class' => 'SelectBox', 'id' => 'tags', 'items' => %w[a b],
            'multiple' => true }.merge(extra)
        ).convert
      end

      it 'marks the select as a list box' do
        expect(listbox).to include(' multiple')
      end

      it 'passes size through as the visible row count' do
        expect(listbox('size' => 4)).to include(' size={4}')
        expect(listbox).not_to include('size={')
      end

      # e.target.value on a multi-select is only the FIRST selected option,
      # which silently loses every other selection.
      it 'reports every selected option' do
        expect(listbox('selectedValue' => '@{tags}'))
          .to include('Array.from(e.target.selectedOptions).map((o) => o.value)')
      end

      # React warns at runtime when a multi-select is given a scalar value.
      it 'normalises the bound value to an array' do
        expect(listbox('selectedValue' => '@{tags}'))
          .to include("value={Array.isArray(data.tags) ? data.tags : (data.tags == null || data.tags === '' ? [] : [data.tags])}")
      end

      it 'wraps a literal default value too' do
        expect(listbox('selectedValue' => 'a')).to include('defaultValue={["a"]}')
      end

      # A list box has no closed state to label, so a blank row is just a
      # selectable item meaning "nothing".
      it 'drops the placeholder row' do
        expect(listbox('prompt' => 'Pick')).not_to include('<option value="">')
      end

      it 'drops the arrow gutter and the pointer cursor' do
        result = listbox
        expect(result).not_to include('pr-8')
        expect(result).not_to include('cursor-pointer')
        expect(result).to include('px-3 py-2')
      end

      it 'leaves a single select alone' do
        result = create_converter({ 'class' => 'SelectBox', 'items' => %w[a b],
                                    'selectedValue' => '@{tag}', 'prompt' => 'Pick' }).convert
        expect(result).not_to include(' multiple')
        expect(result).to include('e.target.value')
        expect(result).to include('<option value="">Pick</option>')
      end
    end

    # labelAttributes is the same style object Label takes, and on a <select>
    # the closed-state text IS the label.
    context 'labelAttributes' do
      def styled(label, extra = {})
        create_converter(
          { 'class' => 'SelectBox', 'items' => %w[a], 'labelAttributes' => label }.merge(extra)
        ).convert
      end

      it 'styles the select text' do
        result = styled('fontColor' => '#FF0000', 'fontSize' => 18,
                        'textAlign' => 'Center', 'font' => 'bold')
        expect(result).to include('text-[#FF0000]')
        expect(result).to include('text-center')
        expect(result).to include('font-bold')
      end

      # Tailwind spells colour and font size both with `text-`, so two of them
      # have no defined winner — precedence is stylesheet order, not class
      # order. The override has to replace.
      it 'replaces the component-level colour rather than stacking on it' do
        result = styled({ 'fontColor' => '#FF0000' }, 'fontColor' => '#111111')
        expect(result).to include('text-[#FF0000]')
        expect(result).not_to include('text-[#111111]')
      end

      it 'replaces the component-level font size' do
        result = styled({ 'fontSize' => 18 }, 'fontSize' => 12)
        expect(result.scan(/text-(?:xs|sm|base|lg|xl)/).uniq.length).to eq(1)
      end

      it 'leaves the component-level keys in place for the keys it omits' do
        result = styled({ 'fontColor' => '#FF0000' }, 'fontSize' => 12)
        expect(result).to include('text-[#FF0000]')
        expect(result).to include('text-xs')
      end
    end

    context 'date picker' do
      def picker(extra)
        create_converter(
          { 'class' => 'SelectBox', 'id' => 'when', 'selectItemType' => 'Date' }.merge(extra)
        ).convert
      end

      # `step` is in seconds, so the interval is minutes * 60.
      it 'turns minuteInterval into a step on a time input' do
        expect(picker('datePickerMode' => 'time', 'minuteInterval' => 15)).to include('step={900}')
        expect(picker('datePickerMode' => 'datetime', 'minuteInterval' => 5)).to include('step={300}')
      end

      # A date input has no minutes to step through.
      it 'ignores minuteInterval on a date-only input' do
        expect(picker('minuteInterval' => 15)).not_to include('step=')
      end

      # The wheel/compact chrome is UIKit's; what the web can honour is whether
      # the picker is presented or merely available.
      it 'opens the picker on focus for graphical and inline' do
        expect(picker('datePickerStyle' => 'graphical')).to include('showPicker?.()')
        expect(picker('datePickerStyle' => 'inline')).to include('showPicker?.()')
      end

      it 'leaves the native control alone for the wheel styles' do
        expect(picker('datePickerStyle' => 'wheel')).not_to include('showPicker')
        expect(picker('datePickerStyle' => 'compact')).not_to include('showPicker')
        expect(picker({})).not_to include('showPicker')
      end

      # The input only ever speaks ISO, so a declared format is converted on
      # both edges rather than handing the ViewModel a shape it did not ask for.
      it 'round-trips the value through dateStringFormat' do
        result = picker('dateStringFormat' => 'yyyy/MM/dd', 'selectedDate' => '@{day}')
        expect(result).to include("value={toIsoDateValue(data.day, 'yyyy/MM/dd', 'date')}")
        expect(result).to include("data.onDayChange?.(formatDateValue(e.target.value, 'yyyy/MM/dd', 'date'))")
      end

      it 'passes the input type to the formatter' do
        result = picker('datePickerMode' => 'time', 'dateStringFormat' => 'HH:mm',
                        'selectedDate' => '@{at}')
        expect(result).to include("'HH:mm', 'time')")
      end

      it 'uses the raw value without a declared format' do
        result = picker('selectedDate' => '@{day}')
        expect(result).to include("value={data.day || ''}")
        expect(result).to include('data.onDayChange?.(e.target.value)')
      end
    end
  end
end
