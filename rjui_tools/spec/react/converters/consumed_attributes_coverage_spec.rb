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
#    grow it silently.
#
# base_converter is checked against the common table only (its reads run
# for every component; per-component tables cover keys like fontColor).
RSpec.describe 'Converter consumed-attribute coverage' do
  CONVERTERS_DIR = File.expand_path('../../../lib/react/converters', __dir__)

  CONSUMED = {
    'base_converter.rb' => %w[accessibilityLabel alignBottom alignBottomOfView alignBottomView alignCenterHorizontalView alignCenterVerticalView alignLeft alignLeftOfView alignLeftView alignRight alignRightOfView alignRightView alignTop alignTopOfView alignTopView alt background bind borderColor borderStyle borderWidth bottomMargin bottomPadding canTap centerHorizontal centerInParent centerVertical className clipToBounds cornerRadius direction enabled endMargin font fontColor fontFamily fontSize fontWeight gravity height hidden id indexBelow insetHorizontal insets key leftMargin leftPadding margins maxHeight maxWidth minHeight minWidth offsetX offsetY onClick onclick opacity orientation padding paddingBottom paddingEnd paddingLeft paddingRight paddingStart paddingTop paddings propertyName rightMargin rightPadding shadow startMargin tag testId textAlign tintColor topMargin topPadding userInteractionEnabled visibility weight width zIndex],
    'blur_converter.rb' => %w[backgroundColor blurRadius cornerRadius effectStyle intensity onClick onclick],
    'button_converter.rb' => %w[buttonType cornerRadius disabledBackground disabledFontColor enabled fontColor highlightBackground highlightColor href image partialAttributes tapBackground text tintColor],
    'circle_view_converter.rb' => %w[background backgroundColor borderColor borderStyle borderWidth fillColor onClick onclick shadow strokeColor strokeWidth],
    'collection_converter.rb' => %w[autoChangeTrackingId cellClasses cellIdProperty columnCount columnSpacing columns contentInset currentPage defaultScrollAnchor footerClasses headerClasses id itemSpacing items layout lazy lineSpacing onItemAppear orientation paging scrollDirection scrollEnabled scrollTo sections spacing],
    'embed_converter.rb' => %w[events id navigationMode params screen],
    'gradient_view_converter.rb' => %w[angle colors cornerRadius direction endPoint gradient gradientDirection gradientType locations onClick onclick orientation startPoint],
    'icon_label_converter.rb' => %w[fontColor fontSize fontWeight icon iconMargin iconOff iconOn iconPosition iconSize iconTintColor icon_off icon_on onClick onclick selected spacing strikethrough text tintColor underline],
    'image_converter.rb' => %w[canTap contentMode cornerRadius defaultImage onClick onclick src srcName url],
    'include_converter.rb' => %w[shared_data],
    'indicator_converter.rb' => %w[borderWidth color halfSpinner height size strokeWidth tintColor width],
    'label_converter.rb' => %w[autoShrink disabledFontColor edgeInset enabled font fontColor fontSize fontWeight gravity highlightAttributes highlightColor lineBreakMode lineHeight lineHeightMultiple lineSpacing lines linkable minimumScaleFactor onClick onclick partialAttributes selected strikethrough text textAlign textTransform underline],
    'network_image_converter.rb' => %w[canTap circle circleImage contentMode cornerRadius defaultImage errorImage imageUrl onClick onclick placeholder scaleType src url],
    'progress_converter.rb' => %w[barHeight maximumValue progress progressHeight progressTintColor tintColor trackColor trackTintColor value],
    'radio_converter.rb' => %w[enabled group items onValueChange selectedValue text tintColor],
    'scroll_view_converter.rb' => %w[bounces contentInset contentInsetAdjustmentBehavior horizontalScroll maxZoom orientation paging scrollBehavior scrollEnabled scrollMode showsHorizontalScrollIndicator showsVerticalScrollIndicator],
    'segment_converter.rb' => %w[backgroundColor enabled fontColor fontSize height items onValueChange selectedBackground selectedFontColor selectedIndex selectedTabIndex],
    'select_box_converter.rb' => %w[background borderColor colorScheme datePickerMode datePickerStyle dateStringFormat enabled font fontColor fontSize hint hintColor items labelAttributes maximumDate minimumDate minuteInterval multiple onChange onValueChange onValueChanged placeholder placeholderColor prompt selectItemType selectedDate selectedIndex selectedValue size textAlign value],
    'slider_converter.rb' => %w[enabled maximum maximumTrackTintColor minimum minimumTrackTintColor onValueChange range step tintColor value],
    'switch_converter.rb' => %w[checked enabled isOn label offTintColor onTintColor onValueChange text thumbTintColor tint tintColor value],
    'tab_view_converter.rb' => %w[background height onValueChange selectedIndex showLabels tabBarBackground tabs tintColor unselectedColor width],
    'text_field_converter.rb' => %w[autoFocus autocapitalizationType autocorrectionType background becomeFirstResponder borderStyle borderWidth caretAttributes contentType cornerRadius disabledBackground editable enabled fontColor hint hintColor input maxLength name nextFocus onBeginEditing onBlur onChange onEndEditing onFocus onSubmit onTextChange padding pattern placeholder placeholderColor readOnly required returnKeyType secure shadow text textPaddingLeft],
    'text_view_converter.rb' => %w[autoFocus background becomeFirstResponder borderColor borderWidth cols containerInset cornerRadius disabledBackground editable enabled flexible fontColor hideOnFocused hint hintAttributes hintColor hintFont hintFontSize hintLineHeightMultiple keyboardType lines maxHeight maxLength minHeight name onChange onTextChange padding pattern placeholder placeholderColor readOnly required resize rows scrollEnabled selectable text],
    'toggle_converter.rb' => %w[checked enabled isOn label onTintColor onValueChange text tint tintColor],
    'view_converter.rb' => %w[bottomPadding centerHorizontal centerInParent centerVertical distribution draggable flexWrap height highlightBackground highlighted leftPadding onClick onDragEnter onDragLeave onDragOver onDragStart onDrop onLongPress onPan onPinch onclick orientation padding paddingBottom paddingEnd paddingLeft paddingRight paddingStart paddingTop paddings rightPadding safeAreaInsetPositions spacing tapBackground topPadding],
    'web_converter.rb' => %w[accessibilityLabel allow allowCamera allowDownloads allowGeolocation allowMicrophone allowModals allowPopupsToEscapeSandbox allowsFullScreen allowsInlineMediaPlayback html htmlContent javaScriptCanOpenWindowsAutomatically javaScriptEnabled lazyLoad loading sandbox scrollEnabled src title url]
  }.freeze

  UNDECLARED = {
    'base_converter.rb' => %w[accessibilityLabel alt direction font fontColor fontFamily fontSize fontWeight insetHorizontal insets key offsetX offsetY orientation textAlign zIndex],
    'blur_converter.rb' => %w[backgroundColor intensity],
    'button_converter.rb' => %w[href partialAttributes],
    'circle_view_converter.rb' => %w[backgroundColor fillColor strokeColor strokeWidth],
    'collection_converter.rb' => %w[contentInset onItemAppear scrollDirection spacing],
    'embed_converter.rb' => %w[],
    'gradient_view_converter.rb' => %w[angle colors direction endPoint gradientType orientation startPoint],
    'icon_label_converter.rb' => %w[fontWeight icon iconOff iconOn iconSize iconTintColor spacing strikethrough underline],
    'image_converter.rb' => %w[defaultImage url],
    'include_converter.rb' => %w[],
    'indicator_converter.rb' => %w[halfSpinner size strokeWidth],
    'label_converter.rb' => %w[disabledFontColor],
    'network_image_converter.rb' => %w[circle circleImage imageUrl scaleType],
    'progress_converter.rb' => %w[barHeight maximumValue progressHeight trackColor value],
    'radio_converter.rb' => %w[items],
    'scroll_view_converter.rb' => %w[contentInset horizontalScroll],
    'segment_converter.rb' => %w[backgroundColor fontColor fontSize selectedBackground selectedFontColor selectedTabIndex],
    'select_box_converter.rb' => %w[onChange placeholderColor textAlign value],
    'slider_converter.rb' => %w[maximumTrackTintColor minimumTrackTintColor range],
    'switch_converter.rb' => %w[label text],
    'tab_view_converter.rb' => %w[],
    'text_field_converter.rb' => %w[autoFocus becomeFirstResponder editable name onChange readOnly],
    'text_view_converter.rb' => %w[autoFocus becomeFirstResponder lines name onChange placeholderColor readOnly],
    'toggle_converter.rb' => %w[label text],
    'view_converter.rb' => %w[],
    'web_converter.rb' => %w[accessibilityLabel allowCamera allowDownloads allowGeolocation allowMicrophone allowModals allowPopupsToEscapeSandbox allowsFullScreen allowsInlineMediaPlayback htmlContent javaScriptCanOpenWindowsAutomatically javaScriptEnabled lazyLoad loading scrollEnabled src title]
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
