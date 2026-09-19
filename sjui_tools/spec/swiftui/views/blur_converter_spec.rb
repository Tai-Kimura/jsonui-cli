# frozen_string_literal: true

require 'swiftui/views/blur_converter'
require 'swiftui/converter_factory'

RSpec.describe SjuiTools::SwiftUI::Views::BlurConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with no children' do
      let(:component) { { 'type' => 'Blur' } }

      it 'generates Color.clear as placeholder with the default effect' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Color.clear')
        # An absent effectStyle rides through the library table, which
        # defaults it to `regular` — same resolution as the dynamic path.
        expect(code).to include('.jsonUIVisualEffect(nil)')
      end
    end

    context 'with regular style' do
      let(:component) do
        {
          'type' => 'Blur',
          'style' => 'regular'
        }
      end

      it 'ignores the style-file name and applies the default effect' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.jsonUIVisualEffect(nil)')
      end
    end

    # `effectStyle` is the declared attribute. This used to read `style`, which
    # is `common.style` — the STYLE FILE name — so a Blur inside a styled screen
    # had its style-file reference matched against blur appearances while the
    # declared attribute was ignored.
    context 'with effectStyle Dark' do
      let(:component) do
        {
          'type' => 'Blur',
          'effectStyle' => 'Dark'
        }
      end

      it 'routes the declared value through the library table' do
        converter = described_class.new(component)
        code = converter.convert

        # `jsonUIVisualEffect` resolves material + tint + colour scheme from
        # the ONE `VisualEffectStyle` table the dynamic BlurConverter reads,
        # so the two ios paths cannot answer differently. The old emit
        # hardcoded `.ultraThinMaterial` for every value.
        expect(code).to include('.jsonUIVisualEffect("Dark")')
        expect(code).not_to include('.background(.ultraThinMaterial)')
      end
    end

    context 'with effectStyle Light' do
      let(:component) do
        {
          'type' => 'Blur',
          'effectStyle' => 'Light'
        }
      end

      it 'routes the declared value through the library table' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.jsonUIVisualEffect("Light")')
      end
    end

    context 'with effectStyle ExtraLight' do
      let(:component) { { 'type' => 'Blur', 'effectStyle' => 'ExtraLight' } }

      it 'passes the declared spelling through unnormalised' do
        # Case/alias normalisation lives in VisualEffectStyle.from — the emit
        # forwards the layout's spelling verbatim, like the dynamic path.
        expect(described_class.new(component).convert)
          .to include('.jsonUIVisualEffect("ExtraLight")')
      end
    end

    context 'with a style FILE reference' do
      let(:component) { { 'type' => 'Blur', 'style' => 'glass_panel' } }

      it 'does not treat the style file name as a blur appearance' do
        code = described_class.new(component).convert

        expect(code).to include('.jsonUIVisualEffect(nil)')
        expect(code).not_to include('glass_panel')
      end
    end

    context 'with common modifiers' do
      let(:component) do
        {
          'type' => 'Blur',
          'cornerRadius' => 12,
          'alpha' => 0.8
        }
      end

      it 'applies common modifiers' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(12)')
        expect(code).to include('.opacity(0.8)')
      end
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
      described_class.new({ 'type' => 'Blur' }.merge(extra).merge('child' => children), 0, nil, factory).convert
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

    it 'still renders the child inside the wrapper' do
      code = code_for([child('content_container')])
      wrapper_at = code.index('VisibilityWrapper(')
      expect(code.index('content_container')).to be > wrapper_at
    end
  end

end
