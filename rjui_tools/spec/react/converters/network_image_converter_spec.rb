# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/network_image_converter'

RSpec.describe RjuiTools::React::Converters::NetworkImageConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'basic network image' do
      it 'generates NetworkImage component' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg' })
        result = converter.convert
        expect(result).to include('<NetworkImage')
        expect(result).to include('src="https://example.com/image.jpg"')
      end
    end

    context 'with src binding' do
      it 'generates dynamic src' do
        converter = create_converter({ 'class' => 'NetworkImage', 'src' => '@{imageUrl}' })
        result = converter.convert
        expect(result).to include('src={data.imageUrl}')
      end
    end

    context 'with placeholder/defaultImage' do
      # Canonical networkImage.noSrc = defaultImage (shared/core/
      # attribute_semantics.json): defaultImage is the no-src display and
      # travels as its own prop — never collapsed into placeholder.
      it 'passes defaultImage as its own prop' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'defaultImage' => 'default.png' })
        result = converter.convert
        expect(result).to include('defaultImage="default.png"')
        expect(result).not_to include('placeholder=')
      end

      it 'keeps hint/placeholder/loadingImage as the loading chain' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg',
                                       'placeholder' => 'loading.png', 'defaultImage' => 'default.png' })
        result = converter.convert
        expect(result).to include('placeholder="loading.png"')
        expect(result).to include('defaultImage="default.png"')
      end
    end

    context 'with errorImage' do
      it 'adds errorImage attribute' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'errorImage' => 'error.png' })
        result = converter.convert
        expect(result).to include('errorImage="error.png"')
      end
    end

    context 'with contentMode scaleAspectFill' do
      it 'maps to object-cover' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'contentMode' => 'scaleAspectFill' })
        result = converter.convert
        expect(result).to include('object-cover')
        expect(result).to include('contentMode="cover"')
      end
    end

    context 'with contentMode scaleAspectFit' do
      it 'maps to object-contain' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'contentMode' => 'scaleAspectFit' })
        result = converter.convert
        expect(result).to include('object-contain')
        expect(result).to include('contentMode="contain"')
      end
    end

    # Regression: rjui-networkimage-template-missing-id-and-fit-contentmode —
    # the canonical enum short forms (fit/fill/center/...) must normalize
    # into the NetworkImageProps union, not pass through verbatim.
    context 'with canonical contentMode fit' do
      it 'normalizes to contain' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'contentMode' => 'fit' })
        result = converter.convert
        expect(result).to include('contentMode="contain"')
        expect(result).to include('object-contain')
        expect(result).not_to include('contentMode="fit"')
      end
    end

    context 'with canonical contentMode fill' do
      # fill = stretch per shared/core/attribute_semantics.json —
      # AspectFill is the crop, and kjui already renders fill as FillBounds.
      it 'normalizes to fill (stretch, not cover)' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'contentMode' => 'fill' })
        result = converter.convert
        expect(result).to include('contentMode="fill"')
        expect(result).to include('object-fill')
      end
    end

    context 'with id' do
      it 'passes id through to the NetworkImage component' do
        converter = create_converter({ 'class' => 'NetworkImage', 'id' => 'tenant_logo_image', 'url' => 'https://example.com/image.jpg' })
        result = converter.convert
        expect(result).to match(/<NetworkImage id="tenant_logo_image"/)
      end
    end

    context 'with circle option' do
      it 'adds rounded-full class' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'circle' => true })
        result = converter.convert
        expect(result).to include('rounded-full')
      end
    end

    context 'with cornerRadius' do
      it 'adds corner radius class' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'cornerRadius' => 8 })
        result = converter.convert
        expect(result).to include('rounded-[8px]')
      end
    end

    context 'with canTap' do
      it 'adds cursor-pointer class' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'canTap' => true })
        result = converter.convert
        expect(result).to include('cursor-pointer')
      end
    end

    context 'with onClick handler' do
      it 'adds onClick binding' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'onClick' => '@{handleImageClick}' })
        result = converter.convert
        expect(result).to include('onClick={data.handleImageClick}')
      end
    end

    context 'with onLoad handler' do
      it 'adds onLoad binding' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'onLoad' => '@{handleLoad}' })
        result = converter.convert
        expect(result).to include('onLoad={data.handleLoad}')
      end
    end

    context 'with onError handler' do
      it 'adds onError binding' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'onError' => '@{handleError}' })
        result = converter.convert
        expect(result).to include('onError={data.handleError}')
      end
    end

    context 'with accessibilityLabel' do
      it 'uses label as alt text' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'accessibilityLabel' => 'Profile picture' })
        result = converter.convert
        expect(result).to include('alt="Profile picture"')
      end
    end

    # Regression companion (rjui-image-src-bare-name-string-key-collision):
    # alt resolves strings.json keys on NetworkImage too.
    context 'alt string-key resolution' do
      it 'resolves a registered key to a StringManager reference' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/i.jpg', 'alt' => 'profile_photo_alt' })
        allow(converter).to receive(:convert_string_key)
          .with('profile_photo_alt')
          .and_return('{StringManager.currentLanguage.profilePhotoAlt}')
        result = converter.convert
        expect(result).to include('alt={StringManager.currentLanguage.profilePhotoAlt}')
      end
    end

    context 'with testId' do
      it 'generates data-testid attribute' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'testId' => 'profile-image' })
        result = converter.convert
        expect(result).to include('data-testid="profile-image"')
      end
    end

    context 'with visibility binding' do
      it 'wraps with conditional rendering' do
        converter = create_converter({ 'class' => 'NetworkImage', 'url' => 'https://example.com/image.jpg', 'visibility' => '@{showImage}' })
        result = converter.convert
        expect(result).to include('{data.showImage !== "gone" &&')
      end
    end
  end
end
