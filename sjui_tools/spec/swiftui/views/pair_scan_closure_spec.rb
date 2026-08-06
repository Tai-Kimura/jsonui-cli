# frozen_string_literal: true

# 2026-07-31 pair-scan closure — SwiftUI-codegen behaviours added when the
# component-aware coverage scan exposed silently-dropped attributes.
require_relative '../../spec_helper'
require 'swiftui/view_registry'
require 'swiftui/views/label_converter'
require 'swiftui/views/textview_converter'
require 'swiftui/views/textfield_converter'
require 'swiftui/views/collection_converter'
require 'swiftui/views/image_converter'
require 'swiftui/views/network_image_converter'
require 'swiftui/views/progress_converter'
require 'swiftui/views/radio_converter'
require 'swiftui/views/selectbox_converter'
require 'swiftui/views/toggle_converter'
require 'swiftui/views/checkbox_converter'
require 'swiftui/views/view_converter'
require 'swiftui/views/color_helper'

RSpec.describe 'pair-scan closure (swiftui)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }
  before { SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {} }

  def convert(klass, json)
    SjuiTools::SwiftUI::Views.const_get(klass).new(json, 0, nil).convert
  end

  it 'Label: styled hint swaps in when the bound text is empty (both keys required)' do
    code = convert(:LabelConverter,
                   'type' => 'Label', 'text' => '@{title}',
                   'hint' => 'No title', 'hintColor' => '#999999',
                   'hintAttributes' => { 'fontSize' => 12 })
    expect(code).to include('.isEmpty ?')
    expect(code).to include('No title')
    expect(code).to include('fontColor: (')

    static_empty = convert(:LabelConverter,
                           'type' => 'Label', 'text' => '',
                           'hint' => 'Empty', 'hintAttributes' => { 'fontColor' => '#888888', 'fontSize' => 11 })
    expect(static_empty).to include('Empty')
    expect(static_empty).to include('fontSize: 11,')

    bare = convert(:LabelConverter, 'type' => 'Label', 'text' => '', 'hint' => 'X')
    expect(bare).not_to include('"X"')
  end

  it 'TextView: truncation, submit label, scroll opt-out' do
    code = convert(:TextViewConverter,
                   'type' => 'TextView', 'text' => '@{memo}', 'id' => 'memo_field',
                   'lineBreakMode' => 'Tail', 'returnKeyType' => 'Done', 'scrollEnabled' => false)
    expect(code).to include('.truncationMode(.tail)')
    expect(code).to include('.submitLabel(.done)')
    expect(code).to include('.scrollDisabled(true)')
  end

  it 'TextField: explicit hideOnFocused true empties the placeholder while focused' do
    code = convert(:TextFieldConverter,
                   'type' => 'TextField', 'id' => 'name_field', 'text' => '@{name}',
                   'hint' => 'Your name', 'hideOnFocused' => true)
    expect(code).to include('data.nameFieldIsFocused ? "" :')

    default = convert(:TextFieldConverter,
                      'type' => 'TextField', 'id' => 'name_field', 'text' => '@{name}',
                      'hint' => 'Your name')
    expect(default).not_to include('IsFocused ? ""')
  end

  it 'Collection: ScrollView vocabulary (insets, safe-area, keyboard opt-out, direction)' do
    code = convert(:CollectionConverter,
                   'type' => 'Collection', 'id' => 'cards', 'horizontalScroll' => true,
                   'containerInset' => 8, 'contentInsetAdjustmentBehavior' => 'never',
                   'keyboardAvoidance' => false, 'items' => '@{rows}')
    expect(code).to include('.contentMargins(.all, 8, for: .scrollContent)')
    expect(code).to include('.ignoresSafeArea()')
    expect(code).to include('.ignoresSafeArea(.keyboard)')
  end

  it 'Image: renderingMode, fallback imagery, clamped pinch zoom' do
    code = convert(:ImageConverter,
                   'type' => 'Image', 'id' => 'photo', 'src' => 'pic',
                   'renderingMode' => 'template', 'minZoom' => 1.0, 'maxZoom' => 3.0)
    expect(code).to include('.renderingMode(.template)')
    expect(code).to include('.scaleEffect(photoZoomScale)')
    expect(code).to include('min(max(value.magnification, 1.0), 3.0)')

    fallback = convert(:ImageConverter, 'type' => 'Image', 'errorImage' => 'broken')
    expect(fallback).to include('Image("broken")')
  end

  it 'NetworkImage: canonical url and hint spellings' do
    code = convert(:NetworkImageConverter,
                   'type' => 'NetworkImage', 'url' => 'https://x/y.png', 'hint' => 'ph')
    expect(code).to include('url: "https://x/y.png"')
    expect(code).to include('placeholder: "ph"')
  end

  # `indicatorStyle` is declared `["medium", "large"]` — a SIZE, not a shape.
  # This pinned `linear`, a value the SSoT does not declare and the validator
  # warns on, and the converter read it as the shape: both declared values
  # mapped to CircularProgressViewStyle(), so the attribute emitted one
  # constant whatever you wrote.
  it 'Progress: indicatorStyle sizes the indicator, and the color/tintColor accent spellings' do
    large = convert(:ProgressConverter,
                    'type' => 'Progress', 'progress' => 0.4,
                    'indicatorStyle' => 'large', 'color' => '#FF0000')
    expect(large).to include('.scaleEffect(1.5)')
    expect(large).to include('.tint(')

    medium = convert(:ProgressConverter,
                     'type' => 'Progress', 'progress' => 0.4,
                     'indicatorStyle' => 'medium', 'color' => '#FF0000')
    expect(medium).not_to include('.scaleEffect(')
    expect(medium).not_to eq(large)
  end

  it 'Radio: per-state colours and the value identity' do
    code = convert(:RadioConverter,
                   'type' => 'Radio', 'id' => 'opt_a', 'text' => 'A', 'value' => 'A_VALUE',
                   'checkedColor' => '#00FF00', 'uncheckedColor' => '#CCCCCC')
    expect(code).to include('== "A_VALUE"')
    expect(code).to match(/foregroundColor\(.*\?.*:.*\)/)
  end

  it 'SelectBox: selectedValue alias, labelAttributes precedence, hintColor' do
    code = convert(:SelectBoxConverter,
                   'type' => 'SelectBox', 'items' => %w[A B],
                   'selectedValue' => '@{picked}', 'fontColor' => '#111111',
                   'labelAttributes' => { 'fontColor' => '#222222', 'fontSize' => 18 },
                   'hintColor' => '#999999', 'onValueChange' => '@{onPick}')
    expect(code).to include('fontSize: 18,')
    expect(code).to include('hintColor:')
    expect(code).to include('data.picked')
  end

  it 'Switch/Toggle: tint spelling and the value state alias' do
    code = convert(:ToggleConverter,
                   'type' => 'Switch', 'id' => 'sw', 'value' => '@{isOn}', 'tint' => '#123456')
    expect(code).to include('$data.isOn')
    expect(code).to include('.tint(')
  end

  it 'CheckBox: value is the on/off state alias' do
    code = convert(:CheckboxConverter,
                   'type' => 'CheckBox', 'id' => 'cb', 'value' => '@{agreed}')
    expect(code).to include('$data.agreed')
  end
end

# distribution gap values (semantics.distribution iosGapConstruction,
# 2026-08-06): the two GAP values used to share one 1/1/1 spacer emit, which
# is neither — ios drew one picture for both while android/web distinguish
# them (run-5 collapsedPairs).
RSpec.describe 'distribution gap construction (swiftui)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def stack(distribution, orientation: 'horizontal')
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(
      'type' => 'View', 'id' => 't', 'orientation' => orientation,
      'width' => 'matchParent', 'height' => 'matchParent',
      'distribution' => distribution,
      'child' => Array.new(3) { |i| { 'type' => 'View', 'id' => "c#{i}", 'width' => 40, 'height' => 40 } }
    ).convert.to_s
  end

  it 'equalSpacing: between-children only, ends flush (justify-between)' do
    code = stack('equalSpacing')
    expect(code.scan('Spacer(minLength: 0)').length).to eq(2)
    lines = code.lines.map(&:strip)
    si = lines.index { |l| l.start_with?('HStack(') }
    expect(lines[si + 1]).not_to include('Spacer'), 'ends must be flush — no leading spacer'
  end

  it 'equalCentering: one spacer per end, two per pair — ends are half a between gap' do
    code = stack('equalCentering')
    # 3 children: 1 leading + 2×2 between + 1 trailing = 6
    expect(code.scan('Spacer(minLength: 0)').length).to eq(6)
    lines = code.lines.map(&:strip)
    si = lines.index { |l| l.start_with?('HStack(') }
    expect(lines[si + 1]).to include('Spacer'), 'equalCentering has an END unit'
  end

  it 'a gap distribution suppresses the gravity-default trailing spacer' do
    # Without the suppression, default gravity handed equalSpacing a phantom
    # end gap (3 spacers, not 2) and equalCentering a doubled one.
    expect(stack('equalSpacing', orientation: 'vertical').scan('Spacer(minLength: 0)').length).to eq(2)
    expect(stack('equalCentering', orientation: 'vertical').scan('Spacer(minLength: 0)').length).to eq(6)
  end

  it 'fillEqually keeps its single separator (a SIZE value, untouched by the gap rule)' do
    expect(stack('fillEqually').scan('Spacer(minLength: 0)').length).to eq(3)
  end

  # F's dynamic implementation (e8f99c7, measured): the TRAILING end unit
  # stays out of a wrapContent axis, where a spacer expands the container
  # and swallows the trailing padding. The leading unit is unconditional on
  # both faces; fixed sizes keep the trailing unit (free space for the
  # ratio, cannot be expanded — the old widthExpands gate was too narrow).
  it 'equalCentering on a wrapContent axis drops only the trailing end unit' do
    code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(
      'type' => 'View', 'id' => 't', 'orientation' => 'horizontal',
      'width' => 'wrapContent', 'height' => 60, 'distribution' => 'equalCentering',
      'child' => Array.new(3) { |i| { 'type' => 'View', 'id' => "c#{i}", 'width' => 40, 'height' => 40 } }
    ).convert.to_s
    # 1 leading + 2x2 between, no trailing
    expect(code.scan('Spacer(minLength: 0)').length).to eq(5)
  end

  it 'equalCentering on a FIXED axis keeps the trailing end unit' do
    code = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(
      'type' => 'View', 'id' => 't', 'orientation' => 'horizontal',
      'width' => 300, 'height' => 60, 'distribution' => 'equalCentering',
      'child' => Array.new(3) { |i| { 'type' => 'View', 'id' => "c#{i}", 'width' => 40, 'height' => 40 } }
    ).convert.to_s
    expect(code.scan('Spacer(minLength: 0)').length).to eq(6)
  end
end

# Group-2 backlog closure (2026-07-31).
RSpec.describe 'backlog closure group 2 (swiftui)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  it 'common.indexAbove degrades to zIndex, mirroring indexBelow' do
    named = SjuiTools::SwiftUI::Views::ViewConverter.new(
      { 'type' => 'View', 'indexAbove' => 'other' }, 0, nil
    ).convert
    expect(named).to include('.zIndex(1)')

    numeric = SjuiTools::SwiftUI::Views::ViewConverter.new(
      { 'type' => 'View', 'indexAbove' => '3' }, 0, nil
    ).convert
    expect(numeric).to include('.zIndex(3)')
  end
end
