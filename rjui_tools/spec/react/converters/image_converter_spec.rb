# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/image_converter'

RSpec.describe RjuiTools::React::Converters::ImageConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'with basic image' do
      it 'renders an img tag with src' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/path/to/image.png'
        })
        result = converter.convert
        expect(result).to include('<img')
        expect(result).to include('src="/path/to/image.png"')
        expect(result).to include('/>')
      end
    end

    context 'with srcName' do
      it 'uses srcName with images path prefix' do
        converter = create_converter({
          'type' => 'Image',
          'srcName' => 'logo'
        })
        result = converter.convert
        expect(result).to include('src="/images/logo.svg"')
      end
    end

    context 'with url instead of src' do
      it 'uses url as src' do
        converter = create_converter({
          'type' => 'Image',
          'url' => 'https://example.com/image.jpg'
        })
        result = converter.convert
        expect(result).to include('src="https://example.com/image.jpg"')
      end
    end

    context 'with defaultImage' do
      it 'uses defaultImage as fallback' do
        converter = create_converter({
          'type' => 'Image',
          'defaultImage' => 'default.png'
        })
        result = converter.convert
        expect(result).to include('src="/images/default.png"')
      end
    end

    context 'with no source specified' do
      it 'uses placeholder image' do
        converter = create_converter({
          'type' => 'Image'
        })
        result = converter.convert
        expect(result).to include('src="/images/placeholder.png"')
      end
    end

    context 'with binding expression' do
      it 'converts src binding to JSX expression' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '@{imageUrl}'
        })
        result = converter.convert
        expect(result).to include('src={data.imageUrl}')
      end
    end

    context 'with alt text' do
      it 'includes alt attribute' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'alt' => 'Test Image'
        })
        result = converter.convert
        expect(result).to include('alt="Test Image"')
      end
    end

    context 'with accessibilityLabel' do
      it 'uses accessibilityLabel as alt' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'accessibilityLabel' => 'Accessible Image'
        })
        result = converter.convert
        expect(result).to include('alt="Accessible Image"')
      end
    end
  end

  describe '#build_class_name' do
    context 'with contentMode' do
      it 'maps aspectFit to object-contain' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'contentMode' => 'aspectFit'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('object-contain')
      end

      it 'maps aspectFill to object-cover' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'contentMode' => 'aspectFill'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('object-cover')
      end

      it 'maps center to object-none object-center' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'contentMode' => 'center'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('object-none')
        expect(classes).to include('object-center')
      end

      it 'maps scaleToFill to object-fill' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'contentMode' => 'scaleToFill'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('object-fill')
      end

      it 'defaults to object-cover' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('object-cover')
      end
    end

    context 'with CircleImage type' do
      it 'adds rounded-full class' do
        converter = create_converter({
          'type' => 'CircleImage',
          'src' => '/avatar.png'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('rounded-full')
      end
    end

    context 'with canTap' do
      it 'adds cursor-pointer class' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'canTap' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('cursor-pointer')
      end
    end

    context 'with onclick' do
      it 'adds cursor-pointer class' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'onclick' => 'handleClick'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('cursor-pointer')
      end
    end
  end

  describe '#build_style_attr' do
    context 'with cornerRadius' do
      it 'adds borderRadius style' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'cornerRadius' => 8
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("borderRadius: '8px'")
      end

      it 'does not add borderRadius for CircleImage' do
        converter = create_converter({
          'type' => 'CircleImage',
          'src' => '/avatar.png',
          'cornerRadius' => 8
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).not_to include('borderRadius')
      end
    end
  end

  describe '#build_onclick_attr' do
    context 'with onclick' do
      it 'adds onClick attribute' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'canTap' => true,
          'onclick' => 'handleImageClick'
        })
        result = converter.convert
        expect(result).to include('onClick={handleImageClick}')
      end
    end

    context 'with onclick using colon syntax' do
      it 'converts to arrow function with this' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'canTap' => true,
          'onclick' => 'handleImageClick:'
        })
        result = converter.convert
        expect(result).to include('onClick={() => handleImageClick(this)}')
      end
    end

    context 'without canTap' do
      it 'does not add onClick when canTap is false' do
        converter = create_converter({
          'type' => 'Image',
          'src' => '/image.png',
          'onclick' => 'handleImageClick'
        })
        result = converter.convert
        expect(result).to include('onClick={handleImageClick}')
      end
    end
  end

  describe 'testId and tag attributes' do
    it 'includes data-testid when testId is present' do
      converter = create_converter({
        'type' => 'Image',
        'src' => '/image.png',
        'testId' => 'hero-image'
      })
      result = converter.convert
      expect(result).to include('data-testid="hero-image"')
    end

    it 'includes data-tag when tag is present' do
      converter = create_converter({
        'type' => 'Image',
        'src' => '/image.png',
        'tag' => 'product-image'
      })
      result = converter.convert
      expect(result).to include('data-tag="product-image"')
    end
  end
end
