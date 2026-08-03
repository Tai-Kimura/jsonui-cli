# frozen_string_literal: true

require 'swiftui/views/network_image_converter'

RSpec.describe SjuiTools::SwiftUI::Views::NetworkImageConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic src' do
      let(:component) { { 'type' => 'NetworkImage', 'src' => 'https://example.com/image.jpg' } }

      it 'generates NetworkImage' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('NetworkImage(')
        expect(code).to include('url: "https://example.com/image.jpg"')
      end
    end

    context 'with placeholder' do
      let(:component) do
        {
          'type' => 'NetworkImage',
          'src' => 'https://example.com/image.jpg',
          'placeholder' => 'placeholder_image'
        }
      end

      it 'includes placeholder' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('placeholder: "placeholder_image"')
      end
    end

    context 'with contentMode' do
      it 'handles AspectFill' do
        component = { 'type' => 'NetworkImage', 'src' => 'url', 'contentMode' => 'AspectFill' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('contentMode: .fill')
      end

      it 'handles aspectFit' do
        component = { 'type' => 'NetworkImage', 'src' => 'url', 'contentMode' => 'aspectFit' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('contentMode: .fit')
      end

      # fill = stretch (canonical image.fill = stretch,
      # shared/core/attribute_semantics.json) — NetworkImage carries the
      # .stretch case for it.
      it 'maps fill and scaleToFill to .stretch' do
        %w[fill scaleToFill].each do |mode|
          component = { 'type' => 'NetworkImage', 'src' => 'url', 'contentMode' => mode }
          code = described_class.new(component).convert
          expect(code).to include('contentMode: .stretch'), "expected #{mode} -> .stretch"
        end
      end

      it 'handles center' do
        component = { 'type' => 'NetworkImage', 'src' => 'url', 'contentMode' => 'center' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('contentMode: .center')
      end

      it 'defaults to fit' do
        component = { 'type' => 'NetworkImage', 'src' => 'url', 'contentMode' => 'unknown' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('contentMode: .fit')
      end
    end

    context 'with renderingMode' do
      it 'handles template' do
        component = { 'type' => 'NetworkImage', 'src' => 'url', 'renderingMode' => 'template' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('renderingMode: .template')
      end

      it 'handles original' do
        component = { 'type' => 'NetworkImage', 'src' => 'url', 'renderingMode' => 'original' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('renderingMode: .original')
      end

      it 'defaults to nil' do
        component = { 'type' => 'NetworkImage', 'src' => 'url', 'renderingMode' => 'unknown' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('renderingMode: nil')
      end
    end

    context 'with headers' do
      let(:component) do
        {
          'type' => 'NetworkImage',
          'src' => 'https://example.com/image.jpg',
          'headers' => {
            'Authorization' => 'Bearer token',
            'X-Custom' => 'value'
          }
        }
      end

      it 'includes headers' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('headers: [')
        expect(code).to include('"Authorization": "Bearer token"')
        expect(code).to include('"X-Custom": "value"')
      end
    end

    context 'with background and cornerRadius' do
      let(:component) do
        {
          'type' => 'NetworkImage',
          'src' => 'url',
          'background' => '#FFFFFF',
          'cornerRadius' => 8
        }
      end

      it 'applies background modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.background(')
      end

      it 'applies cornerRadius modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(8)')
      end
    end

    context 'with alpha' do
      let(:component) { { 'type' => 'NetworkImage', 'src' => 'url', 'alpha' => 0.5 } }

      it 'applies opacity modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0.5)')
      end
    end

    context 'with opacity' do
      let(:component) { { 'type' => 'NetworkImage', 'src' => 'url', 'opacity' => 0.8 } }

      it 'applies opacity modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0.8)')
      end
    end

    context 'with hidden' do
      let(:component) { { 'type' => 'NetworkImage', 'src' => 'url', 'hidden' => true } }

      it 'applies hidden modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0).accessibilityHidden(true)')
      end
    end

    context 'with template variable' do
      let(:component) { { 'type' => 'NetworkImage', 'src' => '{{imageUrl}}' } }

      it 'processes template variable' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('url:')
      end
    end

    context 'with empty src' do
      let(:component) { { 'type' => 'NetworkImage' } }

      it 'uses empty url' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('url: ""')
      end
    end

    # The NetworkImage view has taken all three since it was written; the
    # codegen passed none of them, so a layout that set them got the built-in
    # ProgressView and broken-photo glyph on the SwiftUI path only.
    describe 'defaultImage / loadingImage / errorImage' do
      it 'passes each one through' do
        code = described_class.new({
          'type' => 'NetworkImage', 'src' => 'http://x/y.png',
          'defaultImage' => 'ph', 'loadingImage' => 'spin', 'errorImage' => 'broken'
        }).convert

        expect(code).to include('defaultImage: "ph"')
        expect(code).to include('loadingImage: "spin"')
        expect(code).to include('errorImage: "broken"')
      end

      it 'omits them when absent' do
        code = described_class.new({ 'type' => 'NetworkImage', 'src' => 'http://x/y.png' }).convert

        expect(code).not_to include('loadingImage:')
        expect(code).not_to include('errorImage:')
      end
    end
  end
end
