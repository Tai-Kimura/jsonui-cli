# frozen_string_literal: true

# 2026-08-05 plan 49 lane B — what a `@{...}` declaration emits.
#
# `jui conformance codegen-effect` found 54 ios attributes whose BOUND form
# did not survive the converter: 12 interpolated the expression into code
# position (`fontSize: @{v},` — not a program), 13 into a string literal (the
# characters `@{v}` on screen), 12 froze to a constant because Ruby read the
# expression as a value (`"@{x}"` is truthy, `.to_i` is 0), and the rest were
# dropped. None of it was visible to a validator: the SSoT declares every one
# of these `["…", "binding"]`.
#
# These examples pin the emitted TEXT for the bound spelling next to the
# static one, because the pair is the invariant that matters — the fix is only
# correct if the static declaration still emits exactly what it emitted
# before, and both halves are asserted here for that reason.
require_relative '../../spec_helper'
require 'swiftui/view_registry'
require 'swiftui/views/base_view_converter'
require 'swiftui/views/label_converter'
require 'swiftui/views/textview_converter'
require 'swiftui/views/textfield_converter'
require 'swiftui/views/progress_converter'
require 'swiftui/views/indicator_converter'
require 'swiftui/views/radio_converter'
require 'swiftui/views/checkbox_converter'
require 'swiftui/views/slider_converter'
require 'swiftui/views/button_converter'
require 'swiftui/views/icon_label_converter'
require 'swiftui/views/view_converter'
require 'swiftui/views/collection_converter'
require 'swiftui/views/image_converter'
require 'swiftui/views/selectbox_converter'
require 'swiftui/views/color_helper'
require 'swiftui/converter_factory'

RSpec.describe 'bound-value emission (swiftui codegen)' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }
  before { SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {} }

  def convert(klass, json)
    SjuiTools::SwiftUI::Views.const_get(klass).new(json, 0, nil).convert
  end

  # Containers need the factory to render their children — a ViewConverter
  # built without one emits an empty `children: [`, which is exactly the shape
  # a relative-positioning or child-order example has to look at.
  def convert_tree(json)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter(json, 0, nil, factory, nil).convert.to_s
  end

  # `@{` can never legally appear in emitted Swift — every binding is supposed
  # to have become a property access. This is the same structural test the
  # conformance check runs, kept here so a converter added later cannot
  # reintroduce the leak without a red spec.
  def expect_no_leak(code)
    expect(code).not_to include('@{')
  end

  describe 'numeric slots take an expression, never the raw text' do
    it 'CheckBox spacing / fontSize' do
      static = convert(:CheckboxConverter,
                       'type' => 'CheckBox', 'text' => 'A', 'spacing' => 8, 'fontSize' => 20)
      expect(static).to include('spacing: 8,')
      expect(static).to include('fontSize: 20,')

      bound = convert(:CheckboxConverter,
                      'type' => 'CheckBox', 'text' => 'A',
                      'spacing' => '@{gap}', 'fontSize' => '@{size}')
      expect_no_leak(bound)
      expect(bound).to include('spacing: CGFloat(data.gap ?? 0),')
      expect(bound).to include('fontSize: CGFloat(data.size ?? 0),')
    end

    it 'View spacing lands in the stack line' do
      static = convert(:ViewConverter,
                       'type' => 'View', 'orientation' => 'horizontal', 'spacing' => 8,
                       'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect(static).to include('spacing: 8)')

      bound = convert(:ViewConverter,
                      'type' => 'View', 'orientation' => 'horizontal', 'spacing' => '@{gap}',
                      'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect_no_leak(bound)
      expect(bound).to include('spacing: CGFloat(data.gap ?? 0))')
    end

    it 'Slider range bounds' do
      static = convert(:SliderConverter, 'type' => 'Slider', 'minimum' => 0, 'maximum' => 10)
      expect(static).to include('in: 0...10)')

      bound = convert(:SliderConverter,
                      'type' => 'Slider', 'minimum' => '@{lo}', 'maximum' => '@{hi}')
      expect_no_leak(bound)
      expect(bound).to include('in: Double(data.lo ?? 0)...Double(data.hi ?? 0))')
    end

    it 'padding keeps every edge — a bound one used to wipe the static ones' do
      bound = convert(:ViewConverter,
                      'type' => 'View', 'paddingTop' => '@{top}', 'paddingLeft' => 4,
                      'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect_no_leak(bound)
      expect(bound).to include('.padding(.leading, 4)')
      expect(bound).to include('.padding(.top, CGFloat(data.top ?? 0))')
    end

    it 'the topPadding alias emits what paddingTop emits' do
      canonical = convert(:ViewConverter, 'type' => 'View', 'paddingTop' => '@{top}',
                                          'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      aliased = convert(:ViewConverter, 'type' => 'View', 'topPadding' => '@{top}',
                                        'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect(aliased).to eq(canonical)
    end

    it 'Label lines keeps the 0-means-unlimited rule' do
      expect(convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'lines' => 0))
        .to include('lineLimit: nil,')
      expect(convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'lines' => 3))
        .to include('lineLimit: 3,')

      bound = convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'lines' => '@{n}')
      expect_no_leak(bound)
      expect(bound).to include('lineLimit: (Int(data.n ?? 0) == 0 ? nil : Int(data.n ?? 0)),')
    end

    it 'Label lineHeightMultiple keeps the UIKit formula' do
      static = convert(:LabelConverter,
                       'type' => 'Label', 'text' => 'a', 'lineHeightMultiple' => 1.5, 'fontSize' => 20)
      expect(static).to include('lineSpacing: 10.0,')

      bound = convert(:LabelConverter,
                      'type' => 'Label', 'text' => 'a', 'lineHeightMultiple' => '@{m}', 'fontSize' => 20)
      expect_no_leak(bound)
      expect(bound).to include('lineSpacing: ((CGFloat(data.m ?? 0) - 1) * 20),')
    end
  end

  describe 'string slots take the value, not the characters `@{…}`' do
    it 'IconLabel text' do
      bound = convert(:IconLabelConverter, 'type' => 'IconLabel', 'text' => '@{caption}')
      expect_no_leak(bound)
      expect(bound).to include('text: (data.caption ?? ""),')
    end

    it 'Radio label wins over text, bound or not' do
      expect(convert(:RadioConverter, 'type' => 'Radio', 'label' => 'A', 'text' => 'B'))
        .to include('Text("A")')

      bound = convert(:RadioConverter, 'type' => 'Radio', 'label' => '@{caption}')
      expect_no_leak(bound)
      expect(bound).to include('Text((data.caption ?? ""))')
    end

    it 'TextView fontFamily reaches fontName, which is the family' do
      expect(convert(:TextViewConverter, 'type' => 'TextView', 'fontFamily' => 'Inter'))
        .to include('fontName: "Inter"')

      bound = convert(:TextViewConverter, 'type' => 'TextView', 'fontFamily' => '@{family}')
      expect_no_leak(bound)
      expect(bound).to include('fontName: (data.family ?? "")')
    end
  end

  describe 'enum slots carry the vocabulary into the Swift' do
    it 'Label textAlign' do
      expect(convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'textAlign' => 'Center'))
        .to include('textAlignment: .center')

      bound = convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'textAlign' => '@{align}')
      expect_no_leak(bound)
      expect(bound).to include('"center": .center')
      expect(bound).to include('[(data.align ?? "").lowercased()] ?? .leading)')
    end

    it 'TextField contentType stays Optional so an unknown value turns autofill off' do
      expect(convert(:TextFieldConverter, 'type' => 'TextField', 'contentType' => 'newPassword'))
        .to include('.textContentType(.newPassword)')

      bound = convert(:TextFieldConverter, 'type' => 'TextField', 'contentType' => '@{ct}')
      expect_no_leak(bound)
      expect(bound).to include('"newpassword": .newPassword')
      expect(bound).not_to include('.lowercased()] ?? ')
    end

    it 'a bound font resolves weight-or-family the way a written one does' do
      expect(convert(:CheckboxConverter, 'type' => 'CheckBox', 'text' => 'a', 'font' => 'bold'))
        .to include('fontWeight: .bold,')

      bound = convert(:CheckboxConverter, 'type' => 'CheckBox', 'text' => 'a', 'font' => '@{w}')
      expect_no_leak(bound)
      expect(bound).to include('"bold": .bold')
      expect(bound).to include('[(data.w ?? "").lowercased()]')
    end

    it 'Button fontWeight passes a Font.Weight rather than a dead string' do
      expect(convert(:ButtonConverter, 'type' => 'Button', 'text' => 'a', 'fontWeight' => 'bold'))
        .to include('fontWeight: "bold",')

      bound = convert(:ButtonConverter, 'type' => 'Button', 'text' => 'a', 'fontWeight' => '@{w}')
      expect_no_leak(bound)
      expect(bound).to include('fontWeight: (["ultralight": Font.Weight.ultraLight')
    end
  end

  describe 'boolean slots are conditions, not Ruby truthiness' do
    it 'Label linkable' do
      expect(convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'linkable' => true))
        .to include('linkable: true')
      expect(convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'linkable' => false))
        .not_to include('linkable:')

      bound = convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'linkable' => '@{live}')
      expect_no_leak(bound)
      expect(bound).to include('linkable: (data.live ?? false)')
    end

    it 'TextField secure picks the view at run time' do
      expect(convert(:TextFieldConverter, 'type' => 'TextField', 'secure' => true))
        .to include('SecureField(')

      bound = convert(:TextFieldConverter, 'type' => 'TextField', 'secure' => '@{hide}')
      expect_no_leak(bound)
      expect(bound).to include('if (data.hide ?? false) {')
      expect(bound).to include('SecureField(')
      expect(bound).to include('TextField(')
    end

    it 'a bound parent-relative constraint becomes a conditional element' do
      static = convert_tree(
                       'type' => 'View',
                       'child' => [{ 'type' => 'Label', 'text' => 'a', 'id' => 'x', 'alignTop' => true },
                                   { 'type' => 'Label', 'text' => 'b', 'id' => 'y', 'alignBottom' => true }])
      expect(static).to include('constraints: [')
      expect(static).to include('RelativePositionConstraint(type: .parentTop, targetId: "")')
      expect(static).not_to include('compactMap')

      bound = convert_tree(
                      'type' => 'View',
                      'child' => [{ 'type' => 'Label', 'text' => 'a', 'id' => 'x', 'alignTop' => '@{pin}' },
                                  { 'type' => 'Label', 'text' => 'b', 'id' => 'y', 'alignBottom' => true }])
      expect_no_leak(bound)
      expect(bound).to include('(data.pin ?? false) ? RelativePositionConstraint(type: .parentTop, targetId: "") : nil')
      expect(bound).to include('] as [RelativePositionConstraint?]).compactMap { $0 },')
    end

    it 'Radio checked seeds the glyph the way the dynamic runtime does' do
      bound = convert(:RadioConverter,
                      'type' => 'Radio', 'id' => 'opt', 'value' => 'A', 'checked' => '@{on}')
      expect_no_leak(bound)
      expect(bound).to include('|| ((data.on ?? false) && selectedDefaultgroup.isEmpty)')
    end
  end

  describe 'spellings that were read by nothing on this platform' do
    it 'Radio spacing opens the row with it' do
      expect(convert(:RadioConverter, 'type' => 'Radio', 'text' => 'a', 'spacing' => 8))
        .to include('HStack(spacing: 8) {')
      expect(convert(:RadioConverter, 'type' => 'Radio', 'text' => 'a'))
        .to include('HStack {')
    end

    it 'TextView textAlign and input reach the editor through the environment' do
      code = convert(:TextViewConverter,
                     'type' => 'TextView', 'textAlign' => 'Center', 'input' => 'email')
      expect(code).to include('.multilineTextAlignment(.center)')
      expect(code).to include('.keyboardType(.emailAddress)')
    end

    it 'Button textAlign' do
      expect(convert(:ButtonConverter, 'type' => 'Button', 'text' => 'a', 'textAlign' => 'Right'))
        .to include('.multilineTextAlignment(.trailing)')
    end

    it 'View direction reverses the children along the orientation axis' do
      forward = convert_tree(
                        'type' => 'View', 'orientation' => 'vertical',
                        'child' => [{ 'type' => 'Label', 'text' => 'first' },
                                    { 'type' => 'Label', 'text' => 'second' }])
      reversed = convert_tree(
                         'type' => 'View', 'orientation' => 'vertical', 'direction' => 'bottomToTop',
                         'child' => [{ 'type' => 'Label', 'text' => 'first' },
                                     { 'type' => 'Label', 'text' => 'second' }])
      expect(forward.index('first')).to be < forward.index('second')
      expect(reversed.index('first')).to be > reversed.index('second')

      # The axis has to match: bottomToTop means nothing to a row.
      horizontal = convert_tree(
                           'type' => 'View', 'orientation' => 'horizontal', 'direction' => 'bottomToTop',
                           'child' => [{ 'type' => 'Label', 'text' => 'first' },
                                       { 'type' => 'Label', 'text' => 'second' }])
      expect(horizontal.index('first')).to be < horizontal.index('second')
    end

    it 'the declared input vocabulary maps to distinct keyboards' do
      seen = %w[default alphabet email number decimal phone url].map do |input|
        convert(:TextFieldConverter, 'type' => 'TextField', 'input' => input)[/\.keyboardType\(([^)]*)\)/, 1]
      end
      # `alphabet` and `phone` and the lower-case `url` all used to land on
      # `.default` next to the value that MEANS default.
      expect(seen.uniq.length).to eq(seen.length)
    end

    it 'Progress indicatorStyle sizes the way Indicator does' do
      # `.controlSize` reads like the right API for a size vocabulary and does
      # nothing to a determinate ProgressView on ios: the 3PF round-3 measure
      # put BOTH declared values inert against their control. Indicator has
      # used `scaleEffect` for the same vocabulary all along and its `large`
      # measures active, so the two share one table now.
      large = convert(:ProgressConverter, 'type' => 'Progress', 'indicatorStyle' => 'large')
      expect(large).to include('.scaleEffect(1.5)')
      expect(large).not_to include('.controlSize(')
      # medium is scale 1.0 = no modifier: a `value-is-default` fixture, not a
      # converter that ignores the attribute.
      expect(convert(:ProgressConverter, 'type' => 'Progress', 'indicatorStyle' => 'medium'))
        .not_to include('.scaleEffect(')
      expect(convert(:IndicatorConverter, 'type' => 'Indicator', 'indicatorStyle' => 'large'))
        .to include('.scaleEffect(1.5)')
    end

    it 'bound animating with hidesWhenStopped wraps the if in Group' do
      # An `if` is a statement, not a view — the base converter's modifier
      # chain (accessibilityIdentifier, frame, ...) cannot attach to it, and
      # the bare emit failed the codegen-host compile outright
      # (Indicator/animating__binding, "generic parameter could not be
      # inferred" at the Group call site).
      code = convert(:IndicatorConverter,
                     'type' => 'Indicator', 'animating' => '@{boundAnimating}')
      expect(code).to match(/Group \{\s*\n\s*if data\.boundAnimating \{/)
    end
  end

  describe 'declarations the orchestrator routed back to this lane' do
    it 'the placeholder is styled rather than commented about' do
      code = convert(:TextFieldConverter,
                     'type' => 'TextField', 'id' => 'email', 'hint' => 'Email',
                     'hintColor' => '#999999', 'hintFontSize' => 12, 'textAlign' => 'Center')
      # The native field must be handed an EMPTY placeholder, or both draw.
      expect(code).to include('TextField("", text:')
      expect(code).to include('.styledPlaceholder("Email"')
      expect(code).to include('TextFieldPlaceholderStyle(')
      expect(code).to include('hintFontSize: 12')
      expect(code).to include('alignment: textFieldPlaceholderAlignment(for: .center)')
      expect(code).not_to include("doesn't directly support")
    end

    it 'hintAttributes carries the same three spellings' do
      code = convert(:TextFieldConverter,
                     'type' => 'TextField', 'hint' => 'Email',
                     'hintAttributes' => { 'fontColor' => '#999999', 'fontSize' => 12 })
      expect(code).to include('.styledPlaceholder("Email"')
      expect(code).to include('hintFontSize: 12')
    end

    it 'an undeclared placeholder style leaves the native placeholder alone' do
      code = convert(:TextFieldConverter, 'type' => 'TextField', 'hint' => 'Email')
      expect(code).to include('TextField("Email", text:')
      expect(code).not_to include('styledPlaceholder')
    end

    it 'common.borderStyle draws a dashed and a dotted border on ios too' do
      base = { 'type' => 'View', 'borderWidth' => 2, 'borderColor' => '#FF0000',
               'child' => [{ 'type' => 'Label', 'text' => 'a' }] }
      expect(convert_tree(base)).to include('.stroke(SwiftJsonUIConfiguration.shared.getColor(for: "#FF0000") ?? Color.black, lineWidth: 2)')
      expect(convert_tree(base.merge('borderStyle' => 'dashed'))).to include('style: StrokeStyle(lineWidth: 2, dash: [6, 3])')
      expect(convert_tree(base.merge('borderStyle' => 'dotted'))).to include('lineCap: .round, dash: [2, 2 * 2]')
    end

    # The rule lives in shared/core/attribute_semantics.json (semantics.border)
    # and nowhere else: the PAIR requests a border, neither half does on its
    # own, and there is no default border colour. It has been re-derived from
    # the declaration — and reversed — more than once; these examples pin it
    # so the next derivation goes red instead of shipping.
    it 'a border needs both borderWidth and borderColor' do
      pair = convert_tree('type' => 'View', 'borderWidth' => 2, 'borderColor' => '#FF0000',
                          'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect(pair).to include('.stroke(')

      { 'borderWidth' => 2, 'borderColor' => '#FF0000', 'borderStyle' => 'dashed' }.each do |key, value|
        alone = convert_tree('type' => 'View', key => value,
                             'child' => [{ 'type' => 'Label', 'text' => 'a' }])
        expect(alone).not_to include('.stroke('), "#{key} alone must not summon a border"
      end
    end

    it 'a bound width is a stroke width, not a zero one' do
      code = convert_tree('type' => 'View', 'borderWidth' => '@{w}', 'borderColor' => '#FF0000',
                          'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect_no_leak(code)
      expect(code).to include('lineWidth: CGFloat(data.w ?? 0)')
      # One overlay, not two: the binding handler used to register a second
      # one over the top of this, and `:border` is a multi-value bag key.
      expect(code.scan('.stroke(').length).to eq(1)
    end

    # A bound colour is usually a String property naming one, and every
    # colour slot in SwiftUI takes a `Color`. The generated code kept the
    # binding — `codegen-effect` asks whether it survived, not whether it
    # typechecks — and the ios conformance host stopped on
    # `cannot convert value of type 'String' to expected argument type
    # 'Color'`. Compiling 621 generated views is what found it.
    it 'a bound colour is resolved, not pasted into a Color slot' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'brand' => { 'class' => 'String', 'defaultValue' => '#FF0000' }
      }
      %w[tintColor background tapBackground].each do |attribute|
        code = convert_tree('type' => 'View', attribute => '@{brand}',
                            'child' => [{ 'type' => 'Label', 'text' => 'a' }])
        expect_no_leak(code)
        expect(code).to include('getColor(for: data.brand)'),
                        "#{attribute} must resolve the colour, not hand a String to a Color slot"
      end
    ensure
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    end

    it 'a Color-typed property passes through untouched' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'accent' => { 'class' => 'Color', 'defaultValue' => 'Color.red' }
      }
      code = convert_tree('type' => 'View', 'tintColor' => '@{accent}',
                          'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect(code).to include('.tint(data.accent)')
      expect(code).not_to include('getColor(for: data.accent)')
    ensure
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    end

    # `swift_number_expr` answers optionality; it does not answer TYPE. A
    # `cornerRadius` declared `Int` in the data section — the ordinary way to
    # declare one — is a perfectly good read and still not a CGFloat. Only the
    # first of these stopped the ios host build; the rest came out of diffing
    # declared data types against use sites across the generated tree.
    it 'every dimension slot casts as well as unwraps' do
      cases = {
        'cornerRadius' => '.cornerRadius(CGFloat(data.n ?? 0))',
        'minWidth' => 'minWidth: CGFloat(data.n ?? 0)',
        'maxWidth' => 'maxWidth: CGFloat(data.n ?? 0)',
        'minHeight' => 'minHeight: CGFloat(data.n ?? 0)',
        'maxHeight' => 'maxHeight: CGFloat(data.n ?? 0)',
        'idealWidth' => 'idealWidth: CGFloat(data.n ?? 0)'
      }
      cases.each do |attribute, expected|
        code = convert_tree('type' => 'View', attribute => '@{n}',
                            'child' => [{ 'type' => 'Label', 'text' => 'a' }])
        expect_no_leak(code)
        expect(code).to include(expected), "#{attribute} must cast, not just unwrap"
      end
    end

    # `view_binding_handler` carried a second copy of all six size spellings,
    # and every `.frame(` categorises to `:frame_size` — a MULTI_VALUE bag key
    # that `apply_binding_modifiers` fills with `register`, which REPLACES the
    # whole array. So one bound size attribute deleted every static frame on
    # the same view. Measured as the ios codegen-parity four
    # (`common_{max,min}{Width,Height}__binding`): the bound fixture and the
    # static fixture point at the same number, so they must draw the same
    # picture, and codegen's differed because it had lost the other axis.
    it 'a bound size constraint does not delete the static frame beside it' do
      %w[minWidth maxWidth minHeight maxHeight].each do |attribute|
        code = convert(:ViewConverter, 'type' => 'View', 'id' => 't',
                       'width' => 'wrapContent', 'height' => 200, attribute => '@{n}')
        expect(code).to include('.frame(minHeight: 200, idealHeight: 200, maxHeight: 200)'),
                        "#{attribute} must not clobber the declared height"
        # Count the BOUND spelling: the declared height frame legitimately
        # carries `minHeight:` / `maxHeight:` of its own.
        expect(code.scan(/#{attribute}: CGFloat\(data\.n \?\? 0\)/).length).to eq(1),
               "#{attribute} must be emitted once, not by two owners"
      end
    end

    # The same mechanism, one step less visible: `width`/`height` did not
    # double-emit because the entry that replaced the array happened to carry
    # the same text as one of the entries it destroyed. The other axis still
    # went missing.
    # The trailing `alignment:` is the container default an omitted `gravity`
    # now resolves to (gravityDefaults.omittedEntirely). It is not what this
    # example is about — both axes surviving in one frame call is.
    it 'a bound width keeps the static height (and the reverse)' do
      code = convert(:ViewConverter, 'type' => 'View', 'id' => 't',
                     'width' => '@{n}', 'height' => 100)
      expect(code).to include('.frame(width: CGFloat(data.n ?? 0), height: 100,')

      code = convert(:ViewConverter, 'type' => 'View', 'id' => 't',
                     'width' => 100, 'height' => '@{n}')
      expect(code).to include('.frame(width: 100, height: CGFloat(data.n ?? 0),')
    end

    it 'a bound Label fontSize reaches the font modifier as a CGFloat' do
      code = convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'fontSize' => '@{size}')
      expect(code).to include('.font(.system(size: CGFloat(data.size ?? 0)))')
    end

    # `fontWeight` is declared `["string", "number", "binding"]`, and the two
    # halves of the codegen were reading the union differently: the Data model
    # generator declared `var w: Int`, this side sent it through the NAME
    # table, and the emit was `[…][data.w.lowercased()]` — `value of type
    # 'Int' has no member 'lowercased'`. Both halves were internally
    # consistent, so only a compiler could see it. The data section decides.
    it 'a bound weight follows the type the data section declared' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'w' => { 'class' => 'Int', 'defaultValue' => 600 }
      }
      numeric = convert(:ButtonConverter, 'type' => 'Button', 'text' => 'a', 'fontWeight' => '@{w}')
      expect(numeric).to include('600: .semibold')
      expect(numeric).to include('[Int(data.w)]')
      expect(numeric).not_to include('lowercased')

      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'w' => { 'class' => 'String', 'defaultValue' => 'bold' }
      }
      named = convert(:ButtonConverter, 'type' => 'Button', 'text' => 'a', 'fontWeight' => '@{w}')
      expect(named).to include('"bold": .bold')
      expect(named).to include('(data.w).lowercased()')
    ensure
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    end

    it 'a written-out numeric weight resolves too' do
      # `Font.Weight.from(string:)` knows names only, so `600` arrived as
      # .regular through the String initializer.
      expect(convert(:ButtonConverter, 'type' => 'Button', 'text' => 'a', 'fontWeight' => 600))
        .to include('fontWeight: .semibold')
      expect(convert(:ButtonConverter, 'type' => 'Button', 'text' => 'a', 'fontWeight' => 'bold'))
        .to include('fontWeight: "bold"')
    end

    # Following the union thread: `common.weight` and `Label.fontWeight` carry
    # the same `["number", "string"]` declaration `Button.fontWeight` does.
    it 'Label resolves a numeric weight instead of crashing or freezing' do
      # `label_converter` kept a PRIVATE copy of the weight table that called
      # `.downcase` on the value — a declared `fontWeight: 600` raised
      # NoMethodError and took `sjui build` with it — and its other branch
      # quoted the number for an initializer that knows names only.
      expect(convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'fontWeight' => 600))
        .to include('fontWeight: .semibold')
      expect {
        convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'fontWeight' => 600,
                                 'partialAttributes' => [{ 'range' => [0, 1] }])
      }.not_to raise_error
      expect(convert(:LabelConverter, 'type' => 'Label', 'text' => 'a', 'fontWeight' => 'bold'))
        .to include('fontWeight: "bold"')
    end

    it 'a numeric slot parses a String-declared property instead of casting it' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'p' => { 'class' => 'String', 'defaultValue' => '8' }
      }
      # `CGFloat(data.p)` does not compile for a String, and neither does the
      # `?? 0` the numeric emitter would append.
      expect(convert_tree('type' => 'View', 'paddingTop' => '@{p}',
                          'child' => [{ 'type' => 'Label', 'text' => 'a' }]))
        .to include('.padding(.top, CGFloat(Double(data.p) ?? 0))')
    ensure
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    end

    it 'a bound contentMode goes through the library seam, and only the seam' do
      static = convert(:ImageConverter, 'type' => 'Image', 'src' => 'x', 'contentMode' => 'fit')
      expect(static.scan('.aspectRatio(').length).to eq(1)

      bound = convert(:ImageConverter, 'type' => 'Image', 'src' => 'x',
                      'width' => 140, 'height' => 80, 'contentMode' => '@{mode}')
      expect_no_leak(bound)
      # ONE owner: the seam resolves the whole vocabulary at run time,
      # including the stretch that is spelled as the ABSENCE of aspectRatio —
      # the old handler ternary (`== "fill" ? .fill : .fit`) could not, and
      # binding(fill) drew a different picture from literal fill (run 5,
      # Image_contentMode__binding d=29).
      expect(bound).to include(
        '.imageContentMode(ImageContentModeIntent.from(data.mode ?? ""), size: (width: 140, height: 80))'
      )
      expect(bound.scan('.aspectRatio(').length).to eq(0)
      # The seam owns .resizable() too (positional modes must not have it).
      expect(bound.scan('.resizable()').length).to eq(0)
    end

    it 'scrollTo keys an effect on a plain value, not a Combine publisher' do
      code = convert(:CollectionConverter,
                     'type' => 'Collection', 'id' => 't', 'width' => 200, 'height' => 200,
                     'sections' => [{ 'cell' => 'conformance_cell' }], 'items' => '@{items}',
                     'scrollTo' => '@{scrollTarget}', 'scrollAnchor' => 'center')
      # `.throttle` only typechecks on a publisher, which is what forced
      # consumers to declare PassthroughSubject in their data section — the
      # spelling the SSoT withdrew because kjui passes unknown classes
      # through to Kotlin verbatim. Compose keys `LaunchedEffect(data.x)` and
      # web a `useEffect`; `.onChange(of:)` is the same shape.
      expect(code).to include('.onChange(of: data.scrollTarget) { _, index in')
      expect(code).not_to include('.throttle(')
      expect(code).to include('scrollProxy.scrollTo(index, anchor: .center)')
    end

    it 'autocorrectionType default leaves it to the platform' do
      # `default` and `yes` both emitted `.autocorrectionDisabled(false)`, so
      # the attribute reacted to being PRESENT and not to its value
      # (codegen-effect C2/presence-only). The SSoT says `default` means
      # "leave it to the platform" and web deliberately emits nothing.
      def corr(v)
        convert(:TextFieldConverter, 'type' => 'TextField', 'autocorrectionType' => v)
      end
      expect(corr('default')).not_to include('.autocorrectionDisabled')
      expect(corr('yes')).to include('.autocorrectionDisabled(false)')
      expect(corr('on')).to include('.autocorrectionDisabled(false)')
      expect(corr('no')).to include('.autocorrectionDisabled(true)')
      expect(corr('off')).to include('.autocorrectionDisabled(true)')
    end

    it 'a bound clipToBounds resolves at render time' do
      expect(convert_tree('type' => 'View', 'clipToBounds' => true,
                          'child' => [{ 'type' => 'Label', 'text' => 'a' }]))
        .to include('.clipped()')

      bound = convert_tree('type' => 'View', 'clipToBounds' => '@{shouldClip}',
                           'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect_no_leak(bound)
      # The flag is a PARAMETER, not a call-site branch: a branch would freeze
      # at whatever the generator saw.
      expect(bound).to include('.clipToBounds((data.shouldClip ?? false))')
      expect(bound).not_to include('.clipped()')
    end

    it 'SelectBox font reaches the label, nested spelling first' do
      expect(convert(:SelectBoxConverter, 'type' => 'SelectBox', 'items' => %w[A], 'font' => 'Inter'))
        .to include('fontName: "Inter"')
      expect(convert(:SelectBoxConverter, 'type' => 'SelectBox', 'items' => %w[A],
                                          'font' => 'Inter', 'labelAttributes' => { 'font' => 'bold' }))
        .to include('fontName: "bold"')
    end

    it 'hintAttributes wins over the flat placeholder spelling' do
      code = convert(:TextFieldConverter,
                     'type' => 'TextField', 'hint' => 'E',
                     'hintColor' => '#111111', 'hintFontSize' => 20,
                     'hintAttributes' => { 'fontColor' => '#999999', 'fontSize' => 12 })
      # A bag scoped to the hint is the more specific statement — the ordinary
      # cascade rule, and the one every other reader in the ecosystem takes.
      expect(code).to include('"#999999"')
      expect(code).not_to include('"#111111"')
      expect(code).to include('hintFontSize: 12')
    end

    it 'a bound colour resolves through the same colour registry' do
      code = convert_tree('type' => 'View', 'borderWidth' => 2, 'borderColor' => '@{c}',
                          'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect_no_leak(code)
      expect(code).to include('.stroke(SwiftJsonUIConfiguration.shared.getColor(for: data.c) ?? Color.black, lineWidth: 2)')
      expect(code.scan('.stroke(').length).to eq(1)
    end

    it 'a bound weight makes the parent a weighted stack' do
      static = convert_tree('type' => 'View', 'orientation' => 'horizontal',
                            'child' => [{ 'type' => 'Label', 'text' => 'a', 'weight' => 1 },
                                        { 'type' => 'Label', 'text' => 'b' }])
      expect(static).to include('WeightedHStack(')
      expect(static).to include('weight: 1.0')

      bound = convert_tree('type' => 'View', 'orientation' => 'horizontal',
                           'child' => [{ 'type' => 'Label', 'text' => 'a', 'weight' => '@{share}' },
                                       { 'type' => 'Label', 'text' => 'b' }])
      expect_no_leak(bound)
      expect(bound).to include('WeightedHStack(')
      expect(bound).to include('weight: CGFloat(data.share ?? 0)')
    end

    it 'a written-out Radio selectedValue opens the group on that option' do
      converter = SjuiTools::SwiftUI::Views::RadioConverter.new(
        { 'type' => 'Radio', 'id' => 'group', 'items' => %w[A B], 'selectedValue' => 'B' }, 0, nil
      )
      converter.convert
      # The seed leaves through `state_variables` — the generated file's
      # `@State` block — rather than the returned snippet.
      expect(converter.state_variables).to include('@State private var selectedGroup: String = "B"')
    end

    it 'a bound SelectBox selectedValue resolves to its index at run time' do
      code = convert(:SelectBoxConverter,
                     'type' => 'SelectBox', 'items' => %w[A B], 'selectedValue' => '@{picked}')
      expect_no_leak(code)
      expect(code).to include('selectedIndex: ["A", "B"].firstIndex(of: (data.picked ?? "")),')
    end

    it 'bound date bounds are parsed, not pasted' do
      code = convert(:SelectBoxConverter,
                     'type' => 'SelectBox', 'selectItemType' => 'Date',
                     'minimumDate' => '@{from}', 'maximumDate' => '2030-01-01')
      expect_no_leak(code)
      expect(code).to include('minimumDate: (data.from ?? "").toDate(format: "yyyy-MM-dd") ?? Date(),')
      expect(code).to include('maximumDate: "2030-01-01".toDate(format: "yyyy-MM-dd") ?? Date()')
    end

    it 'a bound enum table carries the alias spellings the normalizer never sees' do
      code = convert(:TextFieldConverter, 'type' => 'TextField', 'contentType' => '@{ct}')
      # `emailAddress` and `phone` are `valueAliases` in the SSoT: a written
      # declaration is rewritten at build time, a bound one is not, so the
      # emitted table has to know both spellings.
      %w[email emailaddress telephonenumber tel phone].each do |token|
        expect(code).to include("\"#{token}\":")
      end
    end
  end

  describe 'the canonical parser is not bypassed' do
    it 'an inline default does not escape into a two-way position' do
      code = convert(:SliderConverter, 'type' => 'Slider', 'value' => '@{level ?? 3}')
      expect(code).to include('$data.level')
      expect(code).not_to include('$data.level ?? 3')
    end

    it 'a bound margin brackets its default' do
      code = convert(:ViewConverter, 'type' => 'View', 'topMargin' => '@{gap ?? 12}',
                                     'child' => [{ 'type' => 'Label', 'text' => 'a' }])
      expect(code).to include('.padding(.top, CGFloat(data.gap ?? 12))')
    end
  end
end
