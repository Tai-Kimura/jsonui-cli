# frozen_string_literal: true

require 'swiftui/views/base_view_converter'
require 'swiftui/view_registry'
require 'swiftui/views/view_converter'

RSpec.describe SjuiTools::SwiftUI::Views::BaseViewConverter do
  describe '.validation_enabled' do
    after do
      described_class.validation_enabled = true
    end

    it 'is enabled by default' do
      expect(described_class.validation_enabled?).to be true
    end

    it 'can be disabled' do
      described_class.validation_enabled = false
      expect(described_class.validation_enabled?).to be false
    end
  end

  describe 'color helper' do
    # Create a test class to access protected methods
    let(:test_converter) do
      Class.new(described_class) do
        def test_get_swiftui_color(color)
          get_swiftui_color(color)
        end
      end
    end

    let(:component) { { 'type' => 'View' } }

    before do
      described_class.validation_enabled = false
    end

    after do
      described_class.validation_enabled = true
    end

    it 'converts hex color to Color initializer' do
      converter = test_converter.new(component)
      result = converter.test_get_swiftui_color('#FF0000')

      # Should be a Color expression
      expect(result).to include('Color')
    end

    it 'handles color names' do
      converter = test_converter.new(component)

      # Test common color names
      expect(converter.test_get_swiftui_color('red')).to include('red')
      expect(converter.test_get_swiftui_color('blue')).to include('blue')
    end
  end

  describe 'frame helper' do
    let(:test_converter) do
      Class.new(described_class) do
        include SjuiTools::SwiftUI::Views::FrameHelper

        attr_reader :generated_code

        def initialize(component)
          super(component)
          @generated_code = []
        end

        def test_apply_frame_size
          apply_frame_size
          # Emit from modifier bag to get the generated code
          @modifier_bag.emit_all(self)
          @generated_code.join("\n")
        end

        def add_modifier_line(line)
          @generated_code << line
        end
      end
    end

    before do
      described_class.validation_enabled = false
    end

    after do
      described_class.validation_enabled = true
    end

    context 'with fixed width and height' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 100,
          'height' => 50
        }
      end

      it 'generates frame modifier with fixed dimensions' do
        converter = test_converter.new(component)
        result = converter.test_apply_frame_size

        expect(result).to include('.frame(')
        expect(result).to include('width: 100')
        expect(result).to include('height: 50')
      end
    end

    context 'with infinity width' do
      let(:component) do
        {
          'type' => 'View',
          'width' => 'infinity'
        }
      end

      it 'generates frame with infinity' do
        converter = test_converter.new(component)
        result = converter.test_apply_frame_size

        # Implementation uses width: infinity or maxWidth: .infinity
        expect(result).to include('.frame(')
        expect(result).to include('infinity')
      end
    end
  end

  describe 'spacing helper' do
    let(:test_converter) do
      Class.new(described_class) do
        include SjuiTools::SwiftUI::Views::SpacingHelper

        attr_reader :generated_code

        def initialize(component)
          super(component)
          @generated_code = []
        end

        def test_apply_padding
          apply_padding
          # Emit from modifier bag to get the generated code
          @modifier_bag.emit_all(self)
          @generated_code.join("\n")
        end

        def test_apply_margins
          apply_margins
          # Emit from modifier bag to get the generated code
          @modifier_bag.emit_all(self)
          @generated_code.join("\n")
        end

        def add_modifier_line(line)
          @generated_code << line
        end
      end
    end

    before do
      described_class.validation_enabled = false
    end

    after do
      described_class.validation_enabled = true
    end

    context 'with individual padding values' do
      let(:component) do
        {
          'type' => 'View',
          'paddingTop' => 10,
          'paddingBottom' => 20,
          'paddingLeft' => 15,
          'paddingRight' => 15
        }
      end

      it 'generates individual padding modifiers' do
        converter = test_converter.new(component)
        result = converter.test_apply_padding

        expect(result).to include('.padding(.top, 10)')
        expect(result).to include('.padding(.bottom, 20)')
        expect(result).to include('.padding(.leading, 15)')
        expect(result).to include('.padding(.trailing, 15)')
      end
    end

    context 'with paddings array' do
      let(:component) do
        {
          'type' => 'View',
          'paddings' => [10, 15, 20, 15]
        }
      end

      it 'generates padding modifiers' do
        converter = test_converter.new(component)
        result = converter.test_apply_padding

        # Implementation may use individual padding calls or EdgeInsets
        expect(result).to include('.padding')
        expect(result).to include('10')
        expect(result).to include('20')
      end
    end

    context 'with margin values' do
      let(:component) do
        {
          'type' => 'View',
          'topMargin' => 16,
          'bottomMargin' => 8
        }
      end

      it 'generates margin as padding modifiers' do
        converter = test_converter.new(component)
        result = converter.test_apply_margins

        expect(result).to include('.padding(.top, 16)')
        expect(result).to include('.padding(.bottom, 8)')
      end
    end
  end

  describe 'apply_modifiers' do
    let(:test_converter) do
      Class.new(described_class) do
        def convert
          add_line "TestView()"
          apply_modifiers
          generated_code
        end
      end
    end

    before do
      described_class.validation_enabled = false
    end

    after do
      described_class.validation_enabled = true
    end

    context 'with shadow (detailed)' do
      let(:component) do
        {
          'type' => 'View',
          'shadow' => {
            'radius' => 10,
            'offsetX' => 2,
            'offsetY' => 4,
            'color' => '#000000'
          }
        }
      end

      it 'adds shadow with all parameters' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.shadow(')
        expect(code).to include('radius: 10')
      end
    end

    context 'with shadow (pipe string)' do
      let(:component) do
        {
          'type' => 'View',
          'shadow' => '#000000|2|2|0.5|4'
        }
      end

      it 'parses the five-field UIKit contract' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to match(/\.shadow\(color: \(.+\)\.opacity\(0\.5\), radius: 4\.0, x: 2\.0, y: 2\.0\)/)
      end
    end

    context 'with shadow (malformed string)' do
      let(:component) do
        {
          'type' => 'View',
          'shadow' => '#000000|2|2|4'
        }
      end

      it 'draws nothing — anything but exactly five fields is invalid' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).not_to include('.shadow')
      end
    end

    context 'with clipToBounds' do
      let(:component) do
        {
          'type' => 'View',
          'clipToBounds' => true
        }
      end

      it 'adds clipped modifier' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.clipped()')
      end
    end

    context 'with offset' do
      let(:component) do
        {
          'type' => 'View',
          'offsetX' => 10,
          'offsetY' => 20
        }
      end

      it 'adds offset modifier' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.offset(x: 10, y: 20)')
      end
    end

    context 'with hidden' do
      let(:component) do
        {
          'type' => 'View',
          'hidden' => true
        }
      end

      it 'adds hidden modifier' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.opacity(0).accessibilityHidden(true)')
      end
    end

    context 'with enabled false' do
      let(:component) do
        {
          'type' => 'View',
          'enabled' => false
        }
      end

      it 'adds disabled modifier' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.disabled(true)')
      end
    end

    context 'with tag' do
      let(:component) do
        {
          'type' => 'View',
          'tag' => 1
        }
      end

      it 'adds tag modifier' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.tag(1)')
      end
    end

    context 'with touchDisabledState' do
      let(:component) do
        {
          'type' => 'View',
          'touchDisabledState' => true
        }
      end

      it 'adds allowsHitTesting false' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.allowsHitTesting(false)')
      end
    end

    context 'with onclick' do
      let(:component) do
        {
          'type' => 'View',
          'onClick' => 'handleTap'
        }
      end

      it 'adds onTapGesture' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.onTapGesture')
        expect(code).to include('data.handleTap?()')
      end
    end

    context 'with onClick containing colon' do
      let(:component) do
        {
          'type' => 'View',
          'onClick' => 'handleAction:'
        }
      end

      it 'passes self as parameter' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('data.handleAction?(self)')
      end
    end

    context 'with indexBelow (numeric)' do
      let(:component) do
        {
          'type' => 'View',
          'indexBelow' => 2
        }
      end

      it 'adds zIndex modifier' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.zIndex(-2)')
      end
    end

    context 'with indexBelow (view reference)' do
      let(:component) do
        {
          'type' => 'View',
          'indexBelow' => 'otherView'
        }
      end

      it 'adds default zIndex' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('.zIndex(-1)')
      end
    end

    context 'with className' do
      let(:component) do
        {
          'type' => 'View',
          'className' => 'myCustomClass'
        }
      end

      it 'adds className comment' do
        converter = test_converter.new(component)
        code = converter.convert
        expect(code).to include('// className: myCustomClass')
      end
    end
  end

  describe '#is_binding?' do
    let(:test_converter) do
      Class.new(described_class) do
        def test_is_binding?(value)
          is_binding?(value)
        end
      end
    end

    let(:component) { { 'type' => 'View' } }

    before do
      described_class.validation_enabled = false
    end

    after do
      described_class.validation_enabled = true
    end

    it 'returns true for binding expression' do
      converter = test_converter.new(component)
      expect(converter.test_is_binding?('@{property}')).to be true
    end

    it 'returns false for plain text' do
      converter = test_converter.new(component)
      expect(converter.test_is_binding?('plain text')).to be false
    end
  end

  describe '#extract_binding_property' do
    let(:test_converter) do
      Class.new(described_class) do
        def test_extract_binding_property(value)
          extract_binding_property(value)
        end
      end
    end

    let(:component) { { 'type' => 'View' } }

    before do
      described_class.validation_enabled = false
    end

    after do
      described_class.validation_enabled = true
    end

    it 'extracts property name from binding' do
      converter = test_converter.new(component)
      expect(converter.test_extract_binding_property('@{userName}')).to eq('userName')
    end

    it 'returns value for non-binding' do
      converter = test_converter.new(component)
      expect(converter.test_extract_binding_property('plainValue')).to eq('plainValue')
    end

    it 'returns nil for nil' do
      converter = test_converter.new(component)
      expect(converter.test_extract_binding_property(nil)).to be_nil
    end
  end

  describe '#apply_confirmation_dialog' do
    let(:test_converter) do
      Class.new(described_class) do
        def convert
          add_line "TestView()"
          apply_modifiers
          generated_code
        end
      end
    end

    before do
      described_class.validation_enabled = false
    end

    after do
      described_class.validation_enabled = true
    end

    context 'with confirmationDialog attribute' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showDeleteConfirm}',
            'title' => 'Confirm Delete',
            'message' => 'Are you sure you want to delete?',
            'actions' => '@{deleteActions}'
          }
        }
      end

      it 'generates confirmationDialog modifier' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('.confirmationDialog(')
        expect(code).to include('"Confirm Delete"')
        expect(code).to include('isPresented: $data.showDeleteConfirm')
        expect(code).to include('titleVisibility: .automatic')
      end

      it 'includes actions binding' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('data.deleteActions')
      end

      it 'includes message closure' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('message: {')
        expect(code).to include('Text("Are you sure you want to delete?")')
      end
    end

    context 'with binding title' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => '@{dialogTitle}',
            'actions' => '@{actions}'
          }
        }
      end

      it 'uses binding for title' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('data.dialogTitle')
        expect(code).not_to include('"@{dialogTitle}"')
      end
    end

    context 'with titleVisibility visible' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => 'Delete Item',
            'titleVisibility' => 'visible',
            'actions' => '@{actions}'
          }
        }
      end

      it 'sets titleVisibility to .visible' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('titleVisibility: .visible')
      end
    end

    context 'with titleVisibility hidden' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => 'Delete Item',
            'titleVisibility' => 'hidden',
            'actions' => '@{actions}'
          }
        }
      end

      it 'sets titleVisibility to .hidden' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('titleVisibility: .hidden')
      end
    end

    context 'with binding message' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => 'Delete',
            'message' => '@{deleteMessage}',
            'actions' => '@{actions}'
          }
        }
      end

      it 'uses binding for message' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('Text(data.deleteMessage)')
      end
    end

    context 'without confirmationDialog' do
      let(:component) do
        {
          'type' => 'View'
        }
      end

      it 'does not generate confirmationDialog modifier' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).not_to include('.confirmationDialog(')
      end
    end

    context 'without message' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => 'Delete Item',
            'actions' => '@{actions}'
          }
        }
      end

      it 'does not include message closure' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).not_to include('message: {')
        expect(code).to include(', actions: {')
      end
    end

    context 'with empty title' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'actions' => '@{actions}'
          }
        }
      end

      it 'uses empty string for title' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('""')
      end
    end

    context 'with layout attribute' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => 'Select Action',
            'layout' => {
              'name' => 'delete_confirmation_actions',
              'data' => '@{dialogData}'
            }
          }
        }
      end

      it 'generates view from layout file with data binding' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('.confirmationDialog(')
        expect(code).to include('DeleteConfirmationActionsView(data: data.dialogData)')
      end

      it 'does not include actions binding' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).not_to include('actionsView')
      end
    end

    context 'with layout attribute with .json extension' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => 'Confirm',
            'layout' => {
              'name' => 'dialog_actions.json',
              'data' => '@{confirmData}'
            }
          }
        }
      end

      it 'removes .json extension and generates PascalCase view name' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('DialogActionsView(data: data.confirmData)')
        expect(code).not_to include('.json')
      end
    end

    context 'with layout and message' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => 'Delete',
            'message' => 'Are you sure?',
            'layout' => {
              'name' => 'confirm_actions',
              'data' => '@{actionsData}'
            }
          }
        }
      end

      it 'includes both layout view and message' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).to include('ConfirmActionsView(data: data.actionsData)')
        expect(code).to include('message: {')
        expect(code).to include('Text("Are you sure?")')
      end
    end

    context 'without actions or layout' do
      let(:component) do
        {
          'type' => 'View',
          'confirmationDialog' => {
            'isPresented' => '@{showConfirm}',
            'title' => 'Empty'
          }
        }
      end

      it 'does not generate confirmationDialog modifier' do
        converter = test_converter.new(component)
        code = converter.convert

        expect(code).not_to include('.confirmationDialog(')
      end
    end
  end

  describe 'modifier_bag' do
    let(:test_converter) do
      Class.new(described_class) do
        def convert
          add_line "TestView()"
          apply_modifiers
          generated_code
        end
      end
    end

    before do
      described_class.validation_enabled = false
    end

    after do
      described_class.validation_enabled = true
    end

    it 'is accessible' do
      converter = test_converter.new({ 'type' => 'View' })
      expect(converter.modifier_bag).to be_a(SjuiTools::SwiftUI::Views::ModifierBag)
    end

    it 'registers background in bag' do
      converter = test_converter.new({ 'type' => 'View', 'background' => '#FF0000' })
      converter.convert
      expect(converter.modifier_bag.key?(:background)).to be true
    end

    it 'later registration wins for background' do
      converter = test_converter.new({ 'type' => 'View', 'background' => '#FF0000' })
      converter.modifier_bag.register(:background, ".background(Color.blue)")
      code = converter.convert
      # The bag should emit the last registered value
      expect(code).to include('.background(Color.blue)')
    end
  end
end

# `enabled` is declared boolean|binding on `common`, and the codegen only ever
# matched the literal `false` — a layout that wrote `enabled: "@{isEnabled}"`
# got nothing at all, on a declared attribute that raises no build warning.
RSpec.describe SjuiTools::SwiftUI::Views::ViewConverter, 'enabled' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def view(value)
    json = { 'type' => 'View', 'onClick' => '@{tap}' }
    json['enabled'] = value unless value == :absent
    described_class.new(json, 0, nil).convert
  end

  it 'disables on a binding' do
    expect(view('@{isEnabled}')).to include('.disabled(!((data.isEnabled')
  end

  it 'honours the negation and default forms' do
    expect(view('@{!isLoading}')).to include('.disabled(!(!(data.isLoading')
    expect(view('@{ready ?? true}')).to include('?? true')
  end

  it 'still disables on the literal false' do
    expect(view(false)).to include('.disabled(true)')
  end

  it 'emits nothing for true or absent' do
    expect(view(true)).not_to include('.disabled(')
    expect(view(:absent)).not_to include('.disabled(')
  end
end

# The binding forms of both already resolved through ViewBindingHandler; the
# literal `canTap: false` matched nothing and did nothing.
RSpec.describe SjuiTools::SwiftUI::Views::ViewConverter, 'touch gating' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def view(extra)
    described_class.new({ 'type' => 'View', 'onClick' => '@{tap}' }.merge(extra), 0, nil).convert
  end

  it 'blocks hit testing for a literal canTap false' do
    expect(view('canTap' => false)).to include('.allowsHitTesting(false)')
  end

  it 'still blocks it for userInteractionEnabled false' do
    expect(view('userInteractionEnabled' => false)).to include('.allowsHitTesting(false)')
  end

  # Same modifier as the binding form takes, so the two forms agree.
  it 'blocks it for the binding forms' do
    expect(view('canTap' => '@{isTappable}')).to include('.allowsHitTesting((data.isTappable ?? false))')
    expect(view('userInteractionEnabled' => '@{isInteractive}'))
      .to include('.allowsHitTesting((data.isInteractive ?? false))')
  end

  it 'emits nothing for true or absent' do
    expect(view('canTap' => true)).not_to include('.allowsHitTesting')
    expect(view({})).not_to include('.allowsHitTesting')
  end
end

# onPan / onPinch — declared `binding` on `common` for every platform, emitted
# by no SwiftUI converter until 2026-07. The payload is cumulative per gesture
# (DragGesture.Value.translation / MagnifyGesture.Value.magnification); the
# call shape follows the declared closure class via
# get_event_handler_invocation, so () -> Void handlers stay argument-free.
RSpec.describe SjuiTools::SwiftUI::Views::ViewConverter, 'pan and pinch gestures' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  before { SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {} }

  def view(extra)
    described_class.new({ 'type' => 'View' }.merge(extra), 0, nil).convert
  end

  it 'emits a simultaneous drag gesture for an onPan binding' do
    code = view('onPan' => '@{onSurfacePan}')
    expect(code).to include('.simultaneousGesture(')
    expect(code).to include('DragGesture(minimumDistance: 10).onChanged { value in')
    expect(code).to include('data.onSurfacePan?()')
    # A background-less container is not hittable without a content shape
    expect(code).to include('.contentShape(Rectangle())')
  end

  it 'passes the translation payload when the handler declares CGSize' do
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
      'onSurfacePan' => { 'class' => '((CGSize) -> Void)?' }
    }
    expect(view('onPan' => '@{onSurfacePan}')).to include('data.onSurfacePan?(value.translation)')
  end

  it 'emits a magnify gesture for an onPinch binding' do
    code = view('onPinch' => '@{onSurfacePinch}')
    expect(code).to include('MagnifyGesture().onChanged { value in')
    expect(code).to include('data.onSurfacePinch?()')
  end

  it 'passes the scale payload when the handler declares CGFloat' do
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
      'onSurfacePinch' => { 'class' => '((CGFloat) -> Void)?' }
    }
    expect(view('onPinch' => '@{onSurfacePinch}')).to include('data.onSurfacePinch?(value.magnification)')
  end

  it 'emits nothing without the attributes or for non-binding values' do
    expect(view({})).not_to include('simultaneousGesture')
    expect(view('onPan' => 'plainName')).not_to include('DragGesture')
  end
end
