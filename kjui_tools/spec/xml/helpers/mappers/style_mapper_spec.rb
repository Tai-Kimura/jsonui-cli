# frozen_string_literal: true

require 'xml/helpers/mappers/style_mapper'
require 'xml/helpers/mappers/text_mapper'
require 'xml/helpers/resource_resolver'

RSpec.describe XmlGenerator::Mappers::StyleMapper do
  let(:text_mapper) { XmlGenerator::Mappers::TextMapper.new }
  let(:mapper) { described_class.new(text_mapper) }

  describe '#map_style_attributes' do
    context 'background attributes' do
      it 'maps background color' do
        result = mapper.map_style_attributes('background', '#FF0000', nil, 'View')
        expect(result[:name]).to eq('background')
      end

      it 'maps backgroundColor' do
        result = mapper.map_style_attributes('backgroundColor', '#00FF00', nil, 'View')
        expect(result[:name]).to eq('background')
      end
    end

    context 'alpha/visibility attributes' do
      it 'maps opacity to alpha' do
        result = mapper.map_style_attributes('opacity', 0.5, nil, 'View')
        expect(result[:name]).to eq('alpha')
        expect(result[:value]).to eq('0.5')
      end

      it 'maps alpha' do
        result = mapper.map_style_attributes('alpha', 0.8, nil, 'View')
        expect(result[:value]).to eq('0.8')
      end

      it 'maps visibility visible' do
        result = mapper.map_style_attributes('visibility', 'visible', nil, 'View')
        expect(result[:value]).to eq('visible')
      end

      it 'maps visibility gone' do
        result = mapper.map_style_attributes('visibility', false, nil, 'View')
        expect(result[:value]).to eq('gone')
      end

      it 'maps visibility invisible' do
        result = mapper.map_style_attributes('visibility', 'invisible', nil, 'View')
        expect(result[:value]).to eq('invisible')
      end
    end

    context 'enabled/clickable/focusable' do
      it 'maps enabled' do
        result = mapper.map_style_attributes('enabled', true, nil, 'View')
        expect(result[:name]).to eq('enabled')
        expect(result[:value]).to eq('true')
      end

      it 'maps clickable' do
        result = mapper.map_style_attributes('clickable', true, nil, 'View')
        expect(result[:name]).to eq('clickable')
      end

      it 'maps focusable' do
        result = mapper.map_style_attributes('focusable', true, nil, 'View')
        expect(result[:name]).to eq('focusable')
      end
    end

    context 'image attributes' do
      it 'maps local src' do
        result = mapper.map_style_attributes('src', 'icon.png', nil, 'ImageView')
        expect(result[:name]).to eq('src')
        expect(result[:value]).to eq('@drawable/icon')
      end

      it 'maps network src for ImageView' do
        result = mapper.map_style_attributes('src', 'https://example.com/image.jpg', nil, 'ImageView')
        expect(result[:namespace]).to eq('tools')
      end

      it 'maps src to url for NetworkImage' do
        result = mapper.map_style_attributes('src', 'https://example.com/image.jpg', nil, 'NetworkImage')
        expect(result[:name]).to eq('url')
      end

      it 'maps url attribute' do
        result = mapper.map_style_attributes('url', 'https://example.com/img.jpg', nil, 'NetworkImage')
        expect(result[:name]).to eq('url')
      end

      it 'maps placeholderImage' do
        result = mapper.map_style_attributes('placeholderImage', 'placeholder.png', nil, 'NetworkImage')
        expect(result[:name]).to eq('placeholderImage')
        expect(result[:value]).to eq('@drawable/placeholder')
      end

      it 'maps placeholder for NetworkImage' do
        result = mapper.map_style_attributes('placeholder', 'loading', nil, 'NetworkImage')
        expect(result[:name]).to eq('placeholderImage')
      end

      it 'maps errorImage' do
        result = mapper.map_style_attributes('errorImage', 'error.png', nil, 'NetworkImage')
        expect(result[:name]).to eq('errorImage')
      end

      it 'maps crossfadeEnabled' do
        result = mapper.map_style_attributes('crossfadeEnabled', true, nil, 'NetworkImage')
        expect(result[:name]).to eq('crossfadeEnabled')
      end

      it 'maps cacheEnabled' do
        result = mapper.map_style_attributes('cacheEnabled', true, nil, 'NetworkImage')
        expect(result[:name]).to eq('cacheEnabled')
      end

      it 'maps scaleType fill to centerCrop' do
        result = mapper.map_style_attributes('scaleType', 'fill', nil, 'ImageView')
        expect(result[:value]).to eq('centerCrop')
      end

      it 'maps scaleType fit to fitCenter' do
        result = mapper.map_style_attributes('scaleType', 'fit', nil, 'ImageView')
        expect(result[:value]).to eq('fitCenter')
      end

      it 'maps tint' do
        result = mapper.map_style_attributes('tint', '#FF0000', nil, 'ImageView')
        expect(result[:name]).to eq('tint')
      end
    end

    context 'blur attributes' do
      it 'maps blurRadius' do
        result = mapper.map_style_attributes('blurRadius', 10, nil, 'BlurView')
        expect(result[:name]).to eq('blurRadius')
        expect(result[:value]).to eq('10.0')
      end

      it 'maps blurOverlayColor' do
        result = mapper.map_style_attributes('blurOverlayColor', '#80000000', nil, 'BlurView')
        expect(result[:name]).to eq('blurOverlayColor')
      end

      it 'maps downsampleFactor' do
        result = mapper.map_style_attributes('downsampleFactor', 4, nil, 'BlurView')
        expect(result[:name]).to eq('downsampleFactor')
      end

      it 'maps blurEnabled' do
        result = mapper.map_style_attributes('blurEnabled', true, nil, 'BlurView')
        expect(result[:name]).to eq('blurEnabled')
      end
    end

    context 'gradient attributes' do
      it 'maps gradientStartColor' do
        result = mapper.map_style_attributes('gradientStartColor', '#FF0000', nil, 'GradientView')
        expect(result[:name]).to eq('gradientStartColor')
      end

      it 'maps gradientEndColor' do
        result = mapper.map_style_attributes('gradientEndColor', '#0000FF', nil, 'GradientView')
        expect(result[:name]).to eq('gradientEndColor')
      end

      it 'maps gradientColors array' do
        result = mapper.map_style_attributes('gradientColors', ['#FF0000', '#00FF00', '#0000FF'], nil, 'GradientView')
        expect(result[:name]).to eq('gradientColors')
        expect(result[:value]).to include('|')
      end

      it 'maps gradientDirection vertical' do
        result = mapper.map_style_attributes('gradientDirection', 'vertical', nil, 'GradientView')
        expect(result[:name]).to eq('gradientOrientation')
        expect(result[:value]).to eq('top_bottom')
      end

      it 'maps gradientDirection horizontal' do
        result = mapper.map_style_attributes('gradientDirection', 'horizontal', nil, 'GradientView')
        expect(result[:value]).to eq('left_right')
      end

      it 'maps gradientType linear' do
        result = mapper.map_style_attributes('gradientType', 'linear', nil, 'GradientView')
        expect(result[:value]).to eq('linear')
      end

      it 'maps gradientType radial' do
        result = mapper.map_style_attributes('gradientType', 'radial', nil, 'GradientView')
        expect(result[:value]).to eq('radial')
      end

      it 'maps gradientAngle' do
        result = mapper.map_style_attributes('gradientAngle', 45, nil, 'GradientView')
        expect(result[:name]).to eq('gradientAngle')
      end

      it 'maps gradientRadius' do
        result = mapper.map_style_attributes('gradientRadius', 100, nil, 'GradientView')
        expect(result[:name]).to eq('gradientRadius')
      end
    end

    context 'SafeAreaView attributes' do
      it 'maps safeAreaInsetPositions array' do
        result = mapper.map_style_attributes('safeAreaInsetPositions', ['top', 'bottom'], nil, 'SafeAreaView')
        expect(result[:name]).to eq('safeAreaInsetPositions')
        expect(result[:value]).to eq('top|bottom')
      end

      it 'maps applyTopInset' do
        result = mapper.map_style_attributes('applyTopInset', true, nil, 'SafeAreaView')
        expect(result[:name]).to eq('applyTopInset')
      end

      it 'maps applyBottomInset' do
        result = mapper.map_style_attributes('applyBottomInset', true, nil, 'SafeAreaView')
        expect(result[:name]).to eq('applyBottomInset')
      end
    end

    context 'unknown attribute' do
      it 'returns nil for unknown attribute' do
        result = mapper.map_style_attributes('unknown', 'value', nil, 'View')
        expect(result).to be_nil
      end
    end
  end
end
