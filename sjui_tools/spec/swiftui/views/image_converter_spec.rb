# frozen_string_literal: true

require 'swiftui/views/image_converter'

RSpec.describe SjuiTools::SwiftUI::Views::ImageConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic image' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon_home'
        }
      end

      it 'generates Image view' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Image(')
        expect(code).to include('icon_home')
      end

      it 'adds resizable modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.resizable()')
      end

      it 'adds default aspectRatio fit' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.aspectRatio(contentMode: .fit)')
      end
    end

    context 'with srcName alias' do
      let(:component) do
        {
          'type' => 'Image',
          'srcName' => 'icon_settings'
        }
      end

      it 'uses srcName as src' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('icon_settings')
      end
    end

    context 'with contentMode AspectFit' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'photo',
          'contentMode' => 'AspectFit'
        }
      end

      it 'adds aspectRatio with fit' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.aspectRatio(contentMode: .fit)')
      end
    end

    context 'with contentMode fill / scaleToFill' do
      # fill = stretch (canonical image.fill = stretch,
      # shared/core/attribute_semantics.json): resizable WITHOUT an
      # aspectRatio modifier — SwiftUI has no stretch ContentMode member,
      # so absence of the modifier is the spelling.
      %w[fill scaleToFill].each do |mode|
        it "emits resizable without aspectRatio for #{mode}" do
          converter = described_class.new(
            { 'type' => 'Image', 'src' => 'photo', 'contentMode' => mode }
          )
          code = converter.convert
          expect(code).to include('.resizable()')
          expect(code).not_to include('.aspectRatio')
        end
      end
    end

    context 'with contentMode AspectFill' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'photo',
          'contentMode' => 'AspectFill'
        }
      end

      it 'adds aspectRatio with fill' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.aspectRatio(contentMode: .fill)')
      end
    end

    context 'with CircleImage type' do
      let(:component) do
        {
          'type' => 'CircleImage',
          'src' => 'avatar'
        }
      end

      it 'adds clipShape Circle' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.clipShape(Circle())')
      end
    end

    context 'with defaultImage' do
      let(:component) do
        {
          'type' => 'Image',
          'defaultImage' => 'placeholder'
        }
      end

      it 'uses defaultImage when no src' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Image("placeholder")')
      end
    end

    context 'with no image source' do
      let(:component) do
        {
          'type' => 'Image'
        }
      end

      it 'generates system photo image' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Image(systemName: "photo")')
      end
    end

    context 'with canTap and onclick' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon',
          'canTap' => true,
          'onClick' => 'handleTap'
        }
      end

      it 'adds onTapGesture' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.onTapGesture')
      end
    end

    context 'with background and cornerRadius' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon',
          'background' => '#F5F5F5',
          'cornerRadius' => 8
        }
      end

      it 'adds background modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.background(')
      end

      it 'adds cornerRadius modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(8)')
      end
    end

    context 'with alpha/opacity' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon',
          'alpha' => 0.5
        }
      end

      it 'adds opacity modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0.5)')
      end
    end

    context 'with hidden' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon',
          'hidden' => true
        }
      end

      it 'adds hidden modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0).accessibilityHidden(true)')
      end
    end

    context 'with onSrc callback' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'photo',
          'onSrc' => 'imageLoaded'
        }
      end

      it 'adds onAppear callback' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.onAppear')
        expect(code).to include('data.imageLoaded?()')
      end
    end

    # UIKit gets this free — UIImageView has `highlightedImage`, set by
    # SJUIImageView. SwiftUI has no such property, so the swap has to be driven
    # by a press gesture; the codegen emitted nothing at all.
    describe 'highlightSrc' do
      let(:component) do
        { 'type' => 'Image', 'id' => 'hero', 'src' => 'photo', 'highlightSrc' => 'photo_hl' }
      end

      it 'overlays the highlighted image and swaps on press' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Image("photo_hl")')
        expect(code).to include('.onLongPressGesture(minimumDuration: 0')
      end

      it 'hides the base image while pressed, so the two do not stack' do
        code = described_class.new(component).convert

        expect(code).to include('.opacity(heroIsPressed ? 0 : 1)')
        expect(code).to include('.opacity(heroIsPressed ? 1 : 0)')
      end

      it 'declares the press flag as local view state, not a data property' do
        converter = described_class.new(component)
        converter.convert

        expect(converter.state_variables)
          .to include('@State private var heroIsPressed = false')
      end

      it 'emits nothing when absent' do
        code = described_class.new({ 'type' => 'Image', 'src' => 'photo' }).convert

        expect(code).not_to include('onLongPressGesture')
      end
    end
  end
  # systemIcon reinterprets `src` as an SF Symbol name, which is a different
  # Image initializer rather than a modifier.
  describe 'systemIcon' do
    it 'switches src to the systemName initializer' do
      code = described_class.new({ 'type' => 'Image', 'src' => 'star.fill', 'systemIcon' => true }, 0, nil).convert
      expect(code).to include('Image(systemName: "star.fill")')
      expect(code).not_to include('Image("star.fill")')
    end

    it 'treats src as an asset name without it' do
      code = described_class.new({ 'type' => 'Image', 'src' => 'star.fill' }, 0, nil).convert
      expect(code).to include('Image("star.fill")')
      expect(code).not_to include('systemName')
    end
  end
end
