# frozen_string_literal: true

require 'swiftui/views/scrollview_converter'
require 'swiftui/converter_factory'

RSpec.describe SjuiTools::SwiftUI::Views::ScrollViewConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with default vertical scroll' do
      let(:component) do
        {
          'type' => 'ScrollView'
        }
      end

      it 'generates AdvancedKeyboardAvoidingScrollView' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.vertical')
      end

      it 'uses VStack for children' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('VStack')
      end
    end

    # keyboardDismissMode is opt-in: unset must emit nothing (keyboard stays
    # on scroll — user-confirmed default), a valid value passes through.
    context 'with keyboardDismissMode' do
      it 'emits nothing when unset' do
        code = described_class.new({ 'type' => 'ScrollView' }).convert
        expect(code).not_to include('keyboardDismissMode')
      end

      it 'passes interactive through' do
        code = described_class.new({ 'type' => 'ScrollView', 'keyboardDismissMode' => 'interactive' }).convert
        expect(code).to include('keyboardDismissMode: "interactive"')
      end

      it 'passes onDrag through' do
        code = described_class.new({ 'type' => 'ScrollView', 'keyboardDismissMode' => 'onDrag' }).convert
        expect(code).to include('keyboardDismissMode: "onDrag"')
      end

      it 'emits nothing for none (the default)' do
        code = described_class.new({ 'type' => 'ScrollView', 'keyboardDismissMode' => 'none' }).convert
        expect(code).not_to include('keyboardDismissMode')
      end
    end

    context 'with horizontal scroll' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'horizontalScroll' => true
        }
      end

      it 'generates horizontal scroll view' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.horizontal')
      end

      it 'uses HStack for children' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('HStack')
      end
    end

    context 'with orientation horizontal' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'orientation' => 'horizontal'
        }
      end

      it 'generates horizontal scroll view' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.horizontal')
      end
    end

    context 'with scroll indicators hidden' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'showsVerticalScrollIndicator' => false
        }
      end

      it 'hides scroll indicators' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('showsIndicators: false')
      end
    end

    context 'with horizontal scroll indicator hidden' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'orientation' => 'horizontal',
          'showsHorizontalScrollIndicator' => false
        }
      end

      it 'hides horizontal scroll indicators' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('showsIndicators: false')
      end
    end

    context 'with scrollEnabled false' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'scrollEnabled' => false
        }
      end

      it 'emits scrollDisabled(true) without falling back to disabled(true)' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.scrollDisabled(true)')
        expect(code).not_to include('.disabled(true)')
      end
    end

    context 'with scrollEnabled bound to data' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'scrollEnabled' => '@{canScroll}'
        }
      end

      it 'emits scrollDisabled with negated binding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.scrollDisabled(!data.canScroll)')
        expect(code).not_to include('.disabled(data.canScroll == false)')
      end
    end

    context 'with bounces false' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'bounces' => false
        }
      end

      it 'adds note about bounce behavior' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('bounce behavior')
      end
    end

    context 'with contentInsetAdjustmentBehavior' do
      context 'when never' do
        let(:component) do
          {
            'type' => 'ScrollView',
            'contentInsetAdjustmentBehavior' => 'never'
          }
        end

        it 'adds ignoresSafeArea modifier' do
          converter = described_class.new(component)
          code = converter.convert

          expect(code).to include('.ignoresSafeArea()')
        end
      end

      context 'when scrollableAxes' do
        let(:component) do
          {
            'type' => 'ScrollView',
            'contentInsetAdjustmentBehavior' => 'scrollableAxes'
          }
        end

        it 'adds ignoresSafeArea with horizontal edges' do
          converter = described_class.new(component)
          code = converter.convert

          expect(code).to include('.ignoresSafeArea(edges: .horizontal)')
        end
      end

      context 'when unknown value' do
        let(:component) do
          {
            'type' => 'ScrollView',
            'contentInsetAdjustmentBehavior' => 'custom'
          }
        end

        it 'adds comment with value' do
          converter = described_class.new(component)
          code = converter.convert

          expect(code).to include('// contentInsetAdjustmentBehavior: custom')
        end
      end
    end

    context 'with paging enabled' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'paging' => true
        }
      end

      it 'adds scrollTargetBehavior modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.scrollTargetBehavior(.paging)')
      end

      it 'adds iOS 17 note' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iOS 17')
      end
    end

    context 'with paging as string' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'paging' => 'true'
        }
      end

      it 'adds scrollTargetBehavior modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.scrollTargetBehavior(.paging)')
      end
    end

    context 'with maxZoom' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'maxZoom' => 3.0
        }
      end

      it 'adds MagnificationGesture' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('MagnificationGesture()')
        expect(code).to include('maxZoom: 3.0')
      end
    end

    context 'with single View child' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'child' => {
            'type' => 'View',
            'orientation' => 'horizontal'
          }
        }
      end

      it 'inherits orientation from child' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.horizontal')
      end
    end

    context 'with keyboardAvoidance enabled (default)' do
      let(:component) do
        {
          'type' => 'ScrollView'
        }
      end

      it 'generates AdvancedKeyboardAvoidingScrollView without configuration' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.vertical')
        expect(code).not_to include('KeyboardAvoidanceConfiguration')
      end
    end

    context 'with keyboardAvoidance explicitly true' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'keyboardAvoidance' => true
        }
      end

      it 'generates AdvancedKeyboardAvoidingScrollView without configuration' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.vertical')
        expect(code).not_to include('KeyboardAvoidanceConfiguration')
      end
    end

    context 'with keyboardAvoidance disabled' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'keyboardAvoidance' => false
        }
      end

      it 'generates AdvancedKeyboardAvoidingScrollView with isEnabled false' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.vertical')
        expect(code).to include('KeyboardAvoidanceConfiguration(isEnabled: false)')
      end
    end

    context 'with keyboardAvoidance disabled and horizontal scroll' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'horizontalScroll' => true,
          'keyboardAvoidance' => false
        }
      end

      it 'generates horizontal scroll with keyboard avoidance disabled' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.horizontal')
        expect(code).to include('KeyboardAvoidanceConfiguration(isEnabled: false)')
      end
    end
  end

  describe '#extract_horizontal_from_gravity' do
    let(:converter) { described_class.new({ 'type' => 'ScrollView' }) }

    it 'extracts center from center gravity' do
      expect(converter.extract_horizontal_from_gravity('center')).to eq('center')
    end

    it 'extracts left from left|top' do
      expect(converter.extract_horizontal_from_gravity('left|top')).to eq('left')
    end

    it 'extracts right from right|bottom' do
      expect(converter.extract_horizontal_from_gravity('right|bottom')).to eq('right')
    end

    it 'handles array gravity format' do
      expect(converter.extract_horizontal_from_gravity(['right', 'top'])).to eq('right')
    end

    it 'returns left as default for nil' do
      expect(converter.extract_horizontal_from_gravity(nil)).to eq('left')
    end

    it 'returns left for invalid gravity' do
      expect(converter.extract_horizontal_from_gravity('invalid')).to eq('left')
    end
  end

  # ---------------------------------------------------------------- 1.8.107
  #
  # A child's `visibility` is honored by THIS container. Reported 2026-09-20:
  # a `visibility: "@{x}"` moved from a ScrollView to its direct child
  # vanished from the iOS output with 0 warnings (kjui wrapped it). The
  # three containers that call the factory themselves (ScrollView, Blur,
  # GradientView) go through BaseViewConverter#render_child_honoring_visibility
  # now; these arms pin each site on each container.
  describe 'a direct child that declares visibility (1.8.107)' do
    let(:factory) { SjuiTools::SwiftUI::ConverterFactory.new }

    def child(id, extra = {})
      { 'type' => 'View', 'id' => id, 'width' => 'matchParent', 'height' => 'wrapContent',
        'visibility' => '@{contentVisibility}' }.merge(extra)
    end

    def code_for(children, extra = {})
      described_class.new({ 'type' => 'ScrollView' }.merge(extra).merge('child' => children), 0, nil, factory).convert
    end

    it 'wraps a single child in VisibilityWrapper' do
      code = code_for([child('content_container')])
      expect(code).to include('VisibilityWrapper(data.contentVisibility) {')
      expect(code.scan('VisibilityWrapper(').length).to eq(1)
    end

    it 'wraps each of several children that declare visibility, and only those' do
      code = code_for([child('a'), { 'type' => 'View', 'id' => 'b' }, child('c', 'visibility' => '@{other}')])
      expect(code).to include('VisibilityWrapper(data.contentVisibility) {')
      expect(code).to include('VisibilityWrapper(data.other) {')
      expect(code.scan('VisibilityWrapper(').length).to eq(2)
    end

    it 'emits no wrapper when no child declares visibility' do
      code = code_for([{ 'type' => 'View', 'id' => 'plain' }, { 'type' => 'View', 'id' => 'plain2' }])
      expect(code).not_to include('VisibilityWrapper(')
    end


    it 'puts the wrapper INSIDE the VStack a single child gets, beside the Spacer' do
      code = code_for([child('content_container')])
      stack_at = code.index('VStack(')
      wrapper_at = code.index('VisibilityWrapper(')
      spacer_at = code.index('Spacer(minLength: 0)')
      expect(stack_at).to be < wrapper_at
      expect(wrapper_at).to be < spacer_at
      # the VStack is not what gets hidden: it opens before the wrapper and
      # its Spacer sits after the wrapper closes
      expect(code[wrapper_at..spacer_at]).to include("}\n")
    end

    it 'wraps the single child of a horizontal scroll too' do
      code = code_for([child('content_container')], 'orientation' => 'horizontal')
      expect(code).to include('HStack(')
      expect(code).to include('VisibilityWrapper(data.contentVisibility) {')
    end

    it 'still renders the child inside the wrapper' do
      code = code_for([child('content_container')])
      wrapper_at = code.index('VisibilityWrapper(')
      expect(code.index('content_container')).to be > wrapper_at
    end
  end


  # ---------------------------------------------------------------- 1.8.108
  #
  # `keyboardAvoidancePadding` (SSoT: ScrollView, number, default 20) reaches
  # KeyboardAvoidanceConfiguration.additionalPadding. Reported 2026-09-22: a
  # focused field flush against the fixed footer and no layout attribute to
  # ask for room; the library parameter existed and nothing emitted it.
  describe 'keyboardAvoidancePadding (1.8.108)' do
    def code_for(extra)
      described_class.new({ 'type' => 'ScrollView' }.merge(extra)).convert
    end

    it 'passes a declared padding as additionalPadding' do
      code = code_for('keyboardAvoidancePadding' => 32)
      expect(code).to include('AdvancedKeyboardAvoidingScrollView(.vertical, showsIndicators: true, configuration: KeyboardAvoidanceConfiguration(additionalPadding: 32)) {')
    end

    it 'keeps a fractional value fractional' do
      expect(code_for('keyboardAvoidancePadding' => 12.5)).to include('additionalPadding: 12.5)')
    end

    it 'emits no configuration when the layout does not declare it, so the library default (the SSoT 20) applies' do
      expect(code_for({})).not_to include('KeyboardAvoidanceConfiguration')
    end

    it 'is ignored when keyboardAvoidance is false: the disabled configuration wins' do
      code = code_for('keyboardAvoidance' => false, 'keyboardAvoidancePadding' => 32)
      expect(code).to include('KeyboardAvoidanceConfiguration(isEnabled: false)')
      expect(code).not_to include('additionalPadding')
    end

    it 'keeps keyboardDismissMode beside the configuration' do
      code = code_for('keyboardAvoidancePadding' => 32, 'keyboardDismissMode' => 'interactive')
      expect(code).to include('configuration: KeyboardAvoidanceConfiguration(additionalPadding: 32), keyboardDismissMode: "interactive")')
    end

    it 'emits nothing for a non-numeric value (the validator reports the type)' do
      expect(code_for('keyboardAvoidancePadding' => 'big')).not_to include('additionalPadding')
    end

    # The emitted call is well-typed against a stub of the library's
    # initializer (the real one: SwiftJsonUI KeyboardAvoidanceConfiguration /
    # AdvancedKeyboardAvoidingScrollView, argument order configuration then
    # keyboardDismissMode), compiled against the SwiftUI SDK.
    describe 'the emitted Swift compiles', :swift_compile do
      it 'type-checks the configuration beside keyboardDismissMode' do
        code = code_for('keyboardAvoidancePadding' => 32, 'keyboardDismissMode' => 'interactive')
        body = code.lines.map { |l| "        #{l}" }.join
        expect(<<~SWIFT).to compile_as_swift
          struct KeyboardAvoidanceConfiguration {
              var isEnabled: Bool
              var additionalPadding: CGFloat
              init(isEnabled: Bool = true, additionalPadding: CGFloat = 20) {
                  self.isEnabled = isEnabled; self.additionalPadding = additionalPadding
              }
          }
          struct AdvancedKeyboardAvoidingScrollView<Content: View>: View {
              init(_ axes: Axis.Set = .vertical, showsIndicators: Bool = true,
                   configuration: KeyboardAvoidanceConfiguration = .init(),
                   keyboardDismissMode: String? = nil, @ViewBuilder content: () -> Content) {}
              var body: some View { EmptyView() }
          }
          struct Host: View {
              var body: some View {
          #{body}
              }
          }
        SWIFT
      end
    end
  end

end
