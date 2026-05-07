# frozen_string_literal: true

require 'swiftui/converter_factory'

RSpec.describe SjuiTools::SwiftUI::ConverterFactory do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  let(:factory) { described_class.new }

  describe '#create_converter' do
    context 'with Label component' do
      let(:component) { { 'type' => 'Label', 'text' => 'Hello' } }

      it 'returns LabelConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::LabelConverter)
      end
    end

    context 'with Text component' do
      let(:component) { { 'type' => 'Text', 'text' => 'Hello' } }

      it 'returns LabelConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::LabelConverter)
      end
    end

    context 'with Button component' do
      let(:component) { { 'type' => 'Button', 'text' => 'Click' } }

      it 'returns ButtonConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ButtonConverter)
      end
    end

    context 'with View component' do
      let(:component) { { 'type' => 'View' } }

      it 'returns ViewConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ViewConverter)
      end
    end

    context 'with SafeAreaView component' do
      let(:component) { { 'type' => 'SafeAreaView' } }

      it 'returns ViewConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ViewConverter)
      end
    end

    context 'with TextField component' do
      let(:component) { { 'type' => 'TextField' } }

      it 'returns TextFieldConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::TextFieldConverter)
      end
    end

    context 'with Image component' do
      let(:component) { { 'type' => 'Image' } }

      it 'returns ImageConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ImageConverter)
      end
    end

    context 'with CircleImage component' do
      let(:component) { { 'type' => 'CircleImage' } }

      it 'returns ImageConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ImageConverter)
      end
    end

    context 'with ScrollView component' do
      let(:component) { { 'type' => 'ScrollView' } }

      it 'returns ScrollViewConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ScrollViewConverter)
      end
    end

    context 'with Scroll component' do
      let(:component) { { 'type' => 'Scroll' } }

      it 'returns ScrollViewConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ScrollViewConverter)
      end
    end

    context 'with Toggle component' do
      let(:component) { { 'type' => 'Toggle' } }

      it 'returns ToggleConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ToggleConverter)
      end
    end

    context 'with Switch component' do
      let(:component) { { 'type' => 'Switch' } }

      it 'returns ToggleConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ToggleConverter)
      end
    end

    context 'with Progress component' do
      let(:component) { { 'type' => 'Progress' } }

      it 'returns ProgressConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::ProgressConverter)
      end
    end

    context 'with Slider component' do
      let(:component) { { 'type' => 'Slider' } }

      it 'returns SliderConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::SliderConverter)
      end
    end

    context 'with Indicator component' do
      let(:component) { { 'type' => 'Indicator' } }

      it 'returns IndicatorConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::IndicatorConverter)
      end
    end

    context 'with Table component' do
      let(:component) { { 'type' => 'Table' } }

      it 'returns TableConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::TableConverter)
      end
    end

    context 'with Collection component' do
      let(:component) { { 'type' => 'Collection' } }

      it 'returns CollectionConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::CollectionConverter)
      end
    end

    context 'with SelectBox component' do
      let(:component) { { 'type' => 'SelectBox' } }

      it 'returns SelectBoxConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::SelectBoxConverter)
      end
    end

    context 'with Web component' do
      let(:component) { { 'type' => 'Web' } }

      it 'returns WebConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::WebConverter)
      end
    end

    context 'with WebView component' do
      let(:component) { { 'type' => 'WebView' } }

      it 'returns WebConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::WebConverter)
      end
    end

    context 'with Radio component' do
      let(:component) { { 'type' => 'Radio' } }

      it 'returns RadioConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::RadioConverter)
      end
    end

    context 'with Segment component' do
      let(:component) { { 'type' => 'Segment' } }

      it 'returns SegmentConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::SegmentConverter)
      end
    end

    context 'with Blur component' do
      let(:component) { { 'type' => 'Blur' } }

      it 'returns BlurConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::BlurConverter)
      end
    end

    context 'with GradientView component' do
      let(:component) { { 'type' => 'GradientView' } }

      it 'returns GradientViewConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::GradientViewConverter)
      end
    end

    context 'with IconLabel component' do
      let(:component) { { 'type' => 'IconLabel' } }

      it 'returns IconLabelConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::IconLabelConverter)
      end
    end

    context 'with NetworkImage component' do
      let(:component) { { 'type' => 'NetworkImage' } }

      it 'returns NetworkImageConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::NetworkImageConverter)
      end
    end

    context 'with DynamicComponent component' do
      let(:component) { { 'type' => 'DynamicComponent' } }

      it 'returns DynamicComponentConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::DynamicComponentConverter)
      end
    end

    context 'with Include component' do
      let(:component) { { 'type' => 'Include' } }

      it 'raises error because Include should be expanded by process_includes' do
        expect { factory.create_converter(component) }.to raise_error(RuntimeError, /Include type should have been expanded/)
      end
    end

    context 'with include property' do
      let(:component) { { 'include' => 'partial_view' } }

      it 'raises error because include should be expanded by process_includes' do
        expect { factory.create_converter(component) }.to raise_error(RuntimeError, /Include should have been expanded/)
      end
    end

    context 'with TabView component' do
      let(:component) { { 'type' => 'TabView' } }

      it 'returns TabViewConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::Views::TabViewConverter)
      end
    end

    context 'with unknown component type' do
      let(:component) { { 'type' => 'UnknownComponent' } }

      it 'returns DefaultConverter' do
        converter = factory.create_converter(component)
        expect(converter).to be_a(SjuiTools::SwiftUI::DefaultConverter)
      end
    end

    context 'with indent level' do
      let(:component) { { 'type' => 'Label', 'text' => 'Test' } }

      it 'passes indent level to converter' do
        converter = factory.create_converter(component, 2)
        expect(converter.instance_variable_get(:@indent_level)).to eq(2)
      end
    end
  end

  describe 'SwitchConverter' do
    let(:converter) { SjuiTools::SwiftUI::SwitchConverter.new({ 'id' => 'mySwitch' }) }

    it 'generates Toggle code' do
      code = converter.convert
      expect(code).to include('Toggle(')
      expect(code).to include('isOn: $mySwitchIsOn')
    end

    it 'hides labels' do
      code = converter.convert
      expect(code).to include('.labelsHidden()')
    end
  end

  describe 'CheckboxConverter' do
    let(:converter) { SjuiTools::SwiftUI::CheckboxConverter.new({ 'id' => 'myCheck' }) }

    it 'generates Image with tap gesture' do
      code = converter.convert
      expect(code).to include('Image(systemName:')
      expect(code).to include('.onTapGesture')
    end

    it 'toggles checked state' do
      code = converter.convert
      expect(code).to include('myCheckIsChecked.toggle()')
    end
  end

  describe 'DefaultConverter' do
    let(:converter) { SjuiTools::SwiftUI::DefaultConverter.new({ 'type' => 'CustomWidget' }) }

    it 'generates unsupported message' do
      code = converter.convert
      expect(code).to include('Unsupported component: CustomWidget')
      expect(code).to include('.foregroundColor(.red)')
    end
  end
end
