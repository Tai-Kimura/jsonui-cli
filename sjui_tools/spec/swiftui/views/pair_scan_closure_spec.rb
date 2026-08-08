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

  # `fillEqually` used to share the separator arm with `equalSpacing`, which
  # made the two values draw the same picture — a SIZE value spelled as a GAP.
  # The canon cell is "equal frames on each child", i.e. equal weights, so it
  # routes to the weighted stack and emits no separator of its own.
  # F's dynamic half is SwiftJsonUI 4801af7 (`implicitWeight`).
  it 'fillEqually gives equal weights, not a separator' do
    code = stack('fillEqually')

    expect(code).to include('weight: 1')
    expect(code).not_to include('Spacer(minLength: 0)')
    expect(code).not_to eq(stack('equalSpacing'))
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

# distribution SIZE values (semantics.distribution perValueMapping, ruling
# 2026-08-05): the size half is carried to the CHILDREN, not spelled as a
# container arrangement. ios read `fill` on NEITHER face — it fell through
# every arm here and in the dynamic container, which is what
# `common/distribution__fill` measured as ios-inert. F's dynamic half is
# SwiftJsonUI 440c06a; these pin the codegen one.
RSpec.describe 'distribution fill (swiftui)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def stack(orientation:, children:)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(
      'type' => 'View', 'id' => 't', 'orientation' => orientation,
      'width' => 300, 'height' => 200, 'distribution' => 'fill',
      'child' => children
    ).convert.to_s
  end

  it 'grows every undeclared child on the main axis' do
    code = stack(orientation: 'horizontal',
                 children: Array.new(3) { |i| { 'type' => 'View', 'id' => "c#{i}", 'height' => 40 } })

    expect(code.scan('.frame(maxWidth: .infinity').length).to eq(3)
  end

  it 'grows the vertical main axis when that is the orientation' do
    code = stack(orientation: 'vertical',
                 children: Array.new(2) { |i| { 'type' => 'View', 'id' => "c#{i}", 'width' => 40 } })

    expect(code.scan('.frame(maxHeight: .infinity').length).to eq(2)
  end

  # `explicitChildSizeWins`: distribution's size half sits at the BOTTOM of
  # the size topic's explicit > bounds > fill order. Unlike the weighted main
  # axis, fill must not overwrite a size the child declared for itself.
  it 'leaves an explicitly sized child alone' do
    code = stack(orientation: 'horizontal',
                 children: [{ 'type' => 'View', 'id' => 'fixed', 'width' => 40, 'height' => 40 },
                            { 'type' => 'View', 'id' => 'grows', 'height' => 40 }])

    expect(code.scan('.frame(maxWidth: .infinity').length).to eq(1)
    expect(code).to include('width: 40')
  end

  # fill is a SIZE value: the children consume the free space themselves.
  # The gap construction belongs to equalSpacing/equalCentering.
  it 'emits no spacers of its own' do
    code = stack(orientation: 'horizontal',
                 children: Array.new(3) { |i| { 'type' => 'View', 'id' => "c#{i}", 'height' => 40 } })

    expect(code).not_to include('Spacer(minLength: 0)')
  end
end

# gravity's unspecified axis (semantics.gravityDefaults, ruled 2026-08-07).
#
# The ruling is deliberately UNOBSERVABLE — "No activeness observable —
# default-vs-default renders identically" — so no fixture can hold it and the
# emit is the only place it can be machine-checked. It says a single-axis
# gravity leaves the other axis at the container default (top | start), never
# unset and never inherited, and it states the consequence up front: in LTR
# `left` and `top` both resolve to (start, top) and are therefore identical.
# The Wave 2 note that ios draws them the same picture is the contract being
# honoured; a fixture expecting them to differ tests a promise the SSoT never
# made.
RSpec.describe 'gravity unspecified axis (swiftui)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def stack(gravity, orientation: 'horizontal')
    component = { 'type' => 'View', 'id' => 't', 'orientation' => orientation,
                  'width' => 'matchParent', 'height' => 'matchParent',
                  'child' => [{ 'type' => 'View', 'id' => 'c', 'width' => 40, 'height' => 40 }] }
    component['gravity'] = gravity unless gravity.nil?
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert.to_s
  end

  it 'resolves each axis independently — a named axis does not disturb the other' do
    # `left` names only the horizontal axis; the vertical one takes `top`.
    expect(stack('left')).to eq(stack('left|top'))
    # `top` names only the vertical axis; the horizontal one takes `start`.
    expect(stack('top')).to eq(stack('left|top'))
  end

  it 'makes left and top observationally identical in LTR, as the ruling states' do
    expect(stack('left')).to eq(stack('top'))
    expect(stack('left', orientation: 'vertical')).to eq(stack('top', orientation: 'vertical'))
  end

  # The ruling promises a RESOLVED GRAVITY per axis, not a byte-identical
  # emit, and absent gravity currently reaches the same packing by a different
  # route: the spacer construction is identical, but the outer `.frame` omits
  # its `alignment:` argument, so it falls to SwiftUI's `.center` where the
  # three named forms all say `.topLeading`. Recorded in 51-B-progress rather
  # than "fixed" here — every gravity-less view in every project emits through
  # this line, so changing it is a measured question, not a spec edit.
  it 'reaches the same packing when gravity is absent entirely' do
    expect(stack(nil).scan('Spacer(minLength: 0)').length)
      .to eq(stack('left|top').scan('Spacer(minLength: 0)').length)
  end

  it 'does not treat the unnamed axis as unset — bottom still leaves start alone' do
    expect(stack('bottom')).to eq(stack('left|bottom'))
    expect(stack('right')).to eq(stack('right|top'))
  end
end

# `backgroundFill` (semantics.backgroundFill, ruled 2026-08-07): ONE fill per
# surface, and the more specific declaration wins — `gradient` names a list of
# stops where `background` names one colour, so `background` is the FALLBACK,
# not a layer underneath. ios honoured neither reading: BOTH emit paths drew
# the colour and left the declared gradient invisible, by two different
# mechanisms.
RSpec.describe 'background vs gradient (swiftui)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  GRADIENT = ['#00FF00', '#0000FF'].freeze

  def view(attrs)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(
      { 'type' => 'View', 'id' => 't', 'width' => 100, 'height' => 100 }.merge(attrs)
    ).convert.to_s
  end

  def with_child(attrs)
    view(attrs.merge('child' => [{ 'type' => 'Label', 'id' => 'c', 'text' => 'x' }]))
  end

  # Childless View: this path turns `background` into `Rectangle().fill(...)`,
  # so it never reaches MODIFIER_ORDER at all — the gradient sat behind an
  # opaque rectangle.
  it 'fills the childless Rectangle with the gradient, not the colour' do
    code = view('background' => '#FF0000', 'gradient' => GRADIENT)

    expect(code).to include('.fill(LinearGradient(')
    expect(code).not_to include('#FF0000')
    # and not a second copy laid behind the fill it already is
    expect(code).not_to include('.background(LinearGradient(')
  end

  # With children the colour and the gradient both reached the bag, adjacent in
  # MODIFIER_ORDER, and SwiftUI lays the later `.background` further back.
  it 'drops the fallback colour when a gradient is declared alongside it' do
    code = with_child('background' => '#FF0000', 'gradient' => GRADIENT)

    expect(code).to include('.background(LinearGradient(')
    expect(code).not_to include('#FF0000')
  end

  it 'leaves both single-declaration cases exactly as they were' do
    expect(view('background' => '#FF0000')).to include('.fill(SwiftJsonUIConfiguration')
    expect(view('gradient' => GRADIENT)).to include('.background(LinearGradient(')
    expect(with_child('background' => '#FF0000')).to include('.background(SwiftJsonUIConfiguration')
  end
end

# `Collection.listStyle` (semantics.collectionSeparators, ruled 2026-08-07).
# The converter hardcoded `PlainListStyle()` and never read the attribute, so a
# declared listStyle was inert on the codegen face. The ruling is explicit that
# the hardcoding could not be replaced before the vocabulary existed — a bare
# string can be neither validated nor discriminated — and it enumerates the
# four values from the only implementation that reads it.
RSpec.describe 'Collection listStyle (swiftui)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  # The List path: lazy, single column, vertical, no sections.
  def list(style)
    component = { 'type' => 'Collection', 'id' => 't', 'width' => 200, 'height' => 200,
                  'cellClasses' => ['conformance_cell'], 'items' => '@{items}' }
    component['listStyle'] = style unless style.nil?
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert.to_s
  end

  {
    'plain' => 'PlainListStyle()',
    'grouped' => 'GroupedListStyle()',
    'insetGrouped' => 'InsetGroupedListStyle()',
    'sidebar' => 'SidebarListStyle()',
  }.each do |declared, swiftui|
    it "maps #{declared} to #{swiftui}" do
      expect(list(declared)).to include(".listStyle(#{swiftui})")
    end
  end

  # Both are `plain` by declaration: it is the default AND the stated fallback
  # for an unrecognised value.
  it 'falls back to plain when absent or unrecognised' do
    expect(list(nil)).to include('.listStyle(PlainListStyle())')
    expect(list('bogus')).to include('.listStyle(PlainListStyle())')
  end
end

# `Collection.cellWidth` / `cellHeight` — "Fixed width/height for EVERY cell"
# (attribute_definitions). Sixteen call sites render a cell and they had grown
# four dialects of the frame: some applied both, some only the height plus a
# grid fill, and SEVEN applied nothing — so whether a declared cell size was
# honoured depended on which container shape the layout selected. The
# conformance probe's shape landed on a do-nothing site, which is how it
# measured the spelling unread while four sites plainly read it.
#
# These run across the shapes that route differently, so the dialects cannot
# quietly diverge again.
RSpec.describe 'Collection cell sizing (swiftui)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  SHAPES = {
    'sections + bound items' => { 'sections' => [{ 'cell' => 'conformance_cell' }], 'items' => '@{items}' },
    'list (no sections)' => { 'cellClasses' => ['conformance_cell'], 'items' => '@{items}' },
    'grid, columns 2' => { 'columns' => 2, 'sections' => [{ 'cell' => 'conformance_cell' }], 'items' => '@{items}' },
    'horizontal' => { 'orientation' => 'horizontal', 'sections' => [{ 'cell' => 'conformance_cell' }], 'items' => '@{items}' },
    'non-lazy' => { 'lazy' => false, 'sections' => [{ 'cell' => 'conformance_cell' }], 'items' => '@{items}' },
  }.freeze

  def collection(shape, extra = {})
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(
      { 'type' => 'Collection', 'id' => 't', 'width' => 200, 'height' => 200 }
        .merge(SHAPES.fetch(shape)).merge(extra)
    ).convert.to_s
  end

  SHAPES.each_key do |shape|
    it "honours a declared cell size on the #{shape} shape" do
      expect(collection(shape, 'cellWidth' => 37)).to include('.frame(width: 37, alignment: .topLeading)')
      expect(collection(shape, 'cellHeight' => 41)).to include('.frame(height: 41, alignment: .topLeading)')
    end

    # Two values must not emit the same text — that is the C2 judgement the
    # codegen differential makes, spelled as a unit test.
    it "discriminates two cell widths on the #{shape} shape" do
      expect(collection(shape, 'cellWidth' => 8)).not_to eq(collection(shape, 'cellWidth' => 17))
    end
  end

  # The grid column governs the width until a cellWidth is declared, and then
  # the declaration wins: "overrides whatever width the cell layout asked for".
  it 'lets a declared cellWidth override the grid fill' do
    expect(collection('grid, columns 2')).to include('.frame(maxWidth: .infinity)')
    expect(collection('grid, columns 2', 'cellWidth' => 37)).to include('.frame(width: 37, alignment: .topLeading)')
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
