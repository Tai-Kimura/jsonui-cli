#!/usr/bin/env ruby

require_relative '../../spec_helper'
require_relative '../../../lib/core/typed_attributes'

# Consumed-attribute coverage for every React converter (renderer SSoT
# Stage B). Two invariants:
#
# 1. The set of attribute keys each converter consumes (attributes['x']
#    reads in its source) matches the recorded inventory — adding or
#    removing a consumed attribute must update this spec, which keeps an
#    explicit, reviewable record of what each converter emits.
# 2. Every consumed key is either declared for that component in the
#    generated extraction tables (attribute_definitions.json) or listed
#    in the UNDECLARED allowlist below. The allowlist is the live record
#    of "converter reads not covered by the SSoT definitions" — shrink
#    it by declaring the attribute in attribute_definitions.json, never
#    grow it silently. The three faces' undeclared reads, each with its
#    reason, are jui_tools/tests/test_converter_reads_are_declared.py's
#    closed table (2.3.22); what is left here is base_converter's
#    per-component reads and toggle_converter's CheckBox reads, which this
#    scan files under the common table and Switch.
#
# base_converter is checked against the common table only (its reads run
# for every component; per-component tables cover keys like fontColor).
RSpec.describe 'Converter consumed-attribute coverage' do
  CONVERTERS_DIR = File.expand_path('../../../lib/react/converters', __dir__)

  CONSUMED = {
    'base_converter.rb' => %w[accessibilityLabel alignBottom alignBottomOfView alignBottomView alignCenterHorizontalView alignCenterVerticalView alignLeft alignLeftOfView alignLeftView alignRight alignRightOfView alignRightView alignTop alignTopOfView alignTopView alt background borderColor borderStyle borderWidth bottomMargin bottomPadding canTap centerHorizontal centerInParent centerVertical className clipToBounds contentDescription cornerRadius direction distribution effectStyle enabled endMargin font fontColor fontFamily fontSize fontWeight gravity height hidden id indexAbove indexBelow insetHorizontal insets key leftMargin leftPadding margins maxHeight maxWidth minHeight minWidth offsetX offsetY onClick onclick opacity orientation padding paddingBottom paddingEnd paddingLeft paddingRight paddingStart paddingTop paddings propertyName rightMargin rightPadding shadow startMargin tag tapBackground testId textAlign tintColor topMargin topPadding userInteractionEnabled visibility weight width zIndex],
    'blur_converter.rb' => %w[background blurRadius cornerRadius intensity onClick onclick],
    'button_converter.rb' => %w[buttonType cornerRadius disabledBackground disabledFontColor enabled fontColor highlightBackground highlightColor href image partialAttributes tapBackground text tintColor],
    'circle_view_converter.rb' => %w[background borderColor borderStyle borderWidth onClick onclick shadow],
    'collection_converter.rb' => %w[
      autoChangeTrackingId
      borderColor
      borderWidth
      cellClasses
      cellHeight
      cellIdProperty
      cellWidth
      columnCount
      columnSpacing
      columns
      contentInsetAdjustmentBehavior
      cornerRadius
      currentPage
      defaultScrollAnchor
      footerClasses
      headerClasses
      hideSeparator
      horizontalScroll
      id
      insetHorizontal
      insetVertical
      insets
      itemSpacing
      items
      layout
      lazy
      lineSpacing
      listStyle
      onItemAppear
      onValueChange
      orientation
      paging
      scrollEnabled
      scrollTo
      sectionSpacing
      sections
      showsHorizontalScrollIndicator
      showsVerticalScrollIndicator
    ],
    'embed_converter.rb' => %w[events id navigationMode params screen],
    'gradient_view_converter.rb' => %w[angle colors cornerRadius endPoint gradient gradientDirection gradientType locations onClick onclick orientation startPoint],
    'icon_label_converter.rb' => %w[
      fontColor
      fontSize
      fontWeight
      iconMargin
      iconPosition
      iconSize
      icon_off
      icon_on
      onClick
      onclick
      selected
      selectedFontColor
      strikethrough
      text
      textShadow
      tintColor
      underline
    ],
    'image_converter.rb' => %w[
      canTap
      contentMode
      cornerRadius
      defaultImage
      loading
      onClick
      onclick
      src
      srcName
    ],
    'include_converter.rb' => %w[id shared_data testId],
    'indicator_converter.rb' => %w[borderWidth color halfSpinner height strokeWidth tintColor width],
    # `minimumScaleFactor` is absent on purpose: the fit is measured at
    # runtime, so ReactGenerator#extract_auto_shrink_targets reads the size and
    # the factor off the layout JSON and hoists them into the effect. The
    # converter still reads `autoShrink` — that is what decides whether the ref
    # is attached at all. (The coverage ledger still sees the generator read:
    # conformance/coverage.py scans all of rjui_tools/lib and treats
    # non-converter files as serving every component.)
    'label_converter.rb' => %w[
      autoShrink
      disabledFontColor
      edgeInset
      enabled
      font
      fontColor
      fontSize
      fontWeight
      gravity
      highlightAttributes
      highlightColor
      hint
      hintAttributes
      hintColor
      lineBreakMode
      lineHeight
      lineHeightMultiple
      lineSpacing
      lines
      linkable
      onClick
      onclick
      partialAttributes
      placeholder
      selected
      strikethrough
      text
      textAlign
      textShadow
      textTransform
      tintColor
      underline
    ],
    'network_image_converter.rb' => %w[
      canTap
      circle
      contentMode
      cornerRadius
      defaultImage
      errorImage
      hint
      loading
      loadingImage
      onClick
      onclick
      placeholder
      src
      url
    ],
    'progress_converter.rb' => %w[height maximumValue progress progressHeight progressTintColor tintColor trackTintColor width],
    'radio_converter.rb' => %w[
      checked
      enabled
      group
      icon
      items
      label
      onValueChange
      selectedIcon
      selectedValue
      selected_icon
      spacing
      text
      tintColor
      value
    ],
    'scroll_view_converter.rb' => %w[
      borderColor
      borderWidth
      bounces
      contentInset
      contentInsetAdjustmentBehavior
      cornerRadius
      defaultScrollAnchor
      horizontalScroll
      maxZoom
      orientation
      paging
      scrollBehavior
      scrollEnabled
      scrollMode
      showsHorizontalScrollIndicator
      showsVerticalScrollIndicator
    ],
    'segment_converter.rb' => %w[
      background
      enabled
      fontColor
      fontSize
      height
      items
      onValueChange
      selectedFontColor
      selectedIndex
      selectedTabIndex
      tintColor
      valueChange
      width
    ],
    'select_box_converter.rb' => %w[background borderColor caretAttributes colorScheme datePickerMode datePickerStyle dateStringFormat enabled font fontColor fontSize hint hintColor items labelAttributes maximumDate minimumDate minuteInterval multiple onValueChange onValueChanged placeholder prompt selectItemType selectedDate selectedIndex selectedItem selectedValue size textAlign],
    'slider_converter.rb' => %w[enabled maximum minimum onValueChange progressTintColor range step tintColor trackTintColor value width],
    'switch_converter.rb' => %w[checked enabled isOn label offTintColor onTintColor onValueChange text thumbTintColor tint tintColor trackTintColor value],
    'tab_view_converter.rb' => %w[background enabled height onValueChange selectedIndex showLabels tabBarBackground tabs tintColor unselectedColor width],
    'text_field_converter.rb' => %w[
      autoFocus
      autocapitalizationType
      autocorrectionType
      background
      borderStyle
      borderWidth
      caretAttributes
      contentType
      cornerRadius
      disabledBackground
      editable
      enabled
      fontColor
      hint
      hintColor
      hintFont
      hintFontSize
      hintLineHeightMultiple
      input
      maxLength
      name
      nextFocus
      onBeginEditing
      onBlur
      onEndEditing
      onFocus
      onSubmit
      onTextChange
      padding
      pattern
      placeholder
      placeholderColor
      required
      returnKeyType
      secure
      shadow
      text
      textPaddingLeft
      tintColor
    ],
    'text_view_converter.rb' => %w[
      autoFocus
      background
      borderColor
      borderWidth
      cols
      containerInset
      cornerRadius
      disabledBackground
      edgeInset
      editable
      enabled
      flexible
      fontColor
      hideOnFocused
      hint
      hintAttributes
      hintColor
      hintFont
      hintFontSize
      hintLineHeightMultiple
      input
      keyboardType
      lineBreakMode
      maxHeight
      maxLength
      minHeight
      name
      onTextChange
      padding
      pattern
      placeholder
      required
      resize
      returnKeyType
      rows
      scrollEnabled
      selectable
      text
      tintColor
    ],
    'toggle_converter.rb' => %w[checked enabled icon isOn label onTintColor onValueChange selectedIcon spacing src text tintColor value],
    'view_converter.rb' => %w[bottomPadding centerHorizontal centerInParent centerVertical disabledBackground distribution draggable enabled flexWrap height highlightBackground highlighted leftPadding onClick onDragEnter onDragLeave onDragOver onDragStart onDrop onLongPress onPan onPinch onclick orientation padding paddingBottom paddingEnd paddingLeft paddingRight paddingStart paddingTop paddings rightPadding safeAreaInsetPositions spacing topPadding width],
    'web_converter.rb' => %w[allow allowCamera allowDownloads allowGeolocation allowMicrophone allowModals allowPopupsToEscapeSandbox allowsFullScreen allowsInlineMediaPlayback html javaScriptCanOpenWindowsAutomatically javaScriptEnabled lazyLoad sandbox scrollEnabled title url]
  }.freeze

  UNDECLARED = {
    'base_converter.rb' => %w[accessibilityLabel alt contentDescription direction font fontColor fontFamily fontSize fontWeight insetHorizontal insets key orientation textAlign],
    'blur_converter.rb' => %w[],
    'button_converter.rb' => %w[],
    'circle_view_converter.rb' => %w[],
    # onItemAppear left this list in 49-E: it was the SSoT's only `callback`-typed
    # attribute, which attr-codegen skips as "not extractable from JSON", so it
    # had no declaration for this scan to find. A layout carries `@{handler}` as a
    # string, so it is declared like every other handler now and the allowlist
    # tightens by one.
    'collection_converter.rb' => %w[],
    'embed_converter.rb' => %w[],
    'gradient_view_converter.rb' => %w[],
    'icon_label_converter.rb' => %w[],
    'image_converter.rb' => %w[],
    'include_converter.rb' => %w[],
    'indicator_converter.rb' => %w[],
    'label_converter.rb' => %w[],
    'network_image_converter.rb' => %w[],
    'progress_converter.rb' => %w[],
    'radio_converter.rb' => %w[],
    'scroll_view_converter.rb' => %w[],
    'segment_converter.rb' => %w[],
    'select_box_converter.rb' => %w[textAlign],
    'slider_converter.rb' => %w[],
    'switch_converter.rb' => %w[],
    'tab_view_converter.rb' => %w[],
    'text_field_converter.rb' => %w[],
    'text_view_converter.rb' => %w[],
    'toggle_converter.rb' => %w[icon selectedIcon spacing src],
    'view_converter.rb' => %w[],
    'web_converter.rb' => %w[]
  }.freeze

  def scan_consumed(file)
    File.read(File.join(CONVERTERS_DIR, file))
        .scan(/attributes\['([A-Za-z_$][A-Za-z0-9_]*)'\]/)
        .flatten.uniq.sort
  end

  def component_type_for(file)
    file.sub('_converter.rb', '').split('_').map(&:capitalize).join
  end

  it 'covers every converter file' do
    actual = Dir[File.join(CONVERTERS_DIR, '*_converter.rb')]
             .map { |f| File.basename(f) }.sort
    expect(actual).to eq(CONSUMED.keys.sort)
  end

  CONSUMED.each do |file, expected_keys|
    describe file do
      it 'consumes exactly the recorded attribute set' do
        expect(scan_consumed(file)).to eq(expected_keys)
      end

      it 'reads only declared attributes (plus the recorded undeclared allowlist)' do
        ta = RjuiTools::Core::TypedAttributes.new({ 'type' => component_type_for(file) })
        actual_undeclared = expected_keys.reject { |k| ta.declared?(k) }
        expect(actual_undeclared).to eq(UNDECLARED[file])
      end
    end
  end
end
