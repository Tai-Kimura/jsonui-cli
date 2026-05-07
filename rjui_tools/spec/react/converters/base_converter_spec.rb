# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/base_converter'
require 'react/converters/view_converter'

RSpec.describe RjuiTools::React::Converters::BaseConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  # Use ViewConverter as concrete implementation for testing BaseConverter
  def create_converter(json_data, config = nil)
    RjuiTools::React::Converters::ViewConverter.new(json_data, config || default_config)
  end

  describe '#build_class_name' do
    context 'with min/max size constraints' do
      it 'maps minWidth to min-w class' do
        converter = create_converter({
          'type' => 'View',
          'minWidth' => 100
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('min-w-[100px]')
      end

      it 'maps maxWidth to max-w class' do
        converter = create_converter({
          'type' => 'View',
          'maxWidth' => 200
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('max-w-[200px]')
      end

      it 'maps minHeight to min-h class' do
        converter = create_converter({
          'type' => 'View',
          'minHeight' => 50
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('min-h-[50px]')
      end

      it 'maps maxHeight to max-h class' do
        converter = create_converter({
          'type' => 'View',
          'maxHeight' => 300
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('max-h-[300px]')
      end

      it 'maps matchParent to full width/height' do
        converter = create_converter({
          'type' => 'View',
          'minWidth' => 'matchParent',
          'maxHeight' => 'matchParent'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('min-w-full')
        expect(classes).to include('max-h-full')
      end
    end

    context 'with RTL-aware paddings' do
      it 'maps paddingStart to ps- class' do
        converter = create_converter({
          'type' => 'View',
          'paddingStart' => 16
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('ps-4')
      end

      it 'maps paddingEnd to pe- class' do
        converter = create_converter({
          'type' => 'View',
          'paddingEnd' => 8
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('pe-2')
      end
    end

    context 'with alternative padding formats' do
      it 'supports paddingTop/paddingRight/paddingBottom/paddingLeft format' do
        converter = create_converter({
          'type' => 'View',
          'paddingTop' => 16,
          'paddingRight' => 8
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('pt-4')
        expect(classes).to include('pr-2')
      end

      it 'maps insets to padding' do
        converter = create_converter({
          'type' => 'View',
          'insets' => [16, 8]
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('py-4')
        expect(classes).to include('px-2')
      end

      it 'maps insetHorizontal to horizontal padding' do
        converter = create_converter({
          'type' => 'View',
          'insetHorizontal' => 16
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('px-4')
      end
    end

    context 'with RTL-aware margins' do
      it 'maps startMargin to ms- class' do
        converter = create_converter({
          'type' => 'View',
          'startMargin' => 16
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('ms-4')
      end

      it 'maps endMargin to me- class' do
        converter = create_converter({
          'type' => 'View',
          'endMargin' => 8
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('me-2')
      end
    end

    context 'with disabled state' do
      it 'adds opacity-50 and pointer-events-none when enabled is false' do
        converter = create_converter({
          'type' => 'View',
          'enabled' => false
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('opacity-50')
        expect(classes).to include('pointer-events-none')
      end

      it 'does not add disabled classes when enabled is true' do
        converter = create_converter({
          'type' => 'View',
          'enabled' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).not_to include('opacity-50')
        expect(classes).not_to include('pointer-events-none')
      end
    end

    context 'with userInteractionEnabled' do
      it 'adds pointer-events-none when userInteractionEnabled is false' do
        converter = create_converter({
          'type' => 'View',
          'userInteractionEnabled' => false
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('pointer-events-none')
      end
    end

    context 'with offset' do
      it 'adds transform style for offsetX and offsetY' do
        converter = create_converter({
          'type' => 'View',
          'offsetX' => 10,
          'offsetY' => 20
        })
        converter.send(:build_class_name)
        dynamic_styles = converter.instance_variable_get(:@dynamic_styles)
        expect(dynamic_styles['transform']).to eq("'translate(10px, 20px)'")
      end

      it 'defaults missing offset values to 0' do
        converter = create_converter({
          'type' => 'View',
          'offsetX' => 15
        })
        converter.send(:build_class_name)
        dynamic_styles = converter.instance_variable_get(:@dynamic_styles)
        expect(dynamic_styles['transform']).to eq("'translate(15px, 0px)'")
      end
    end

    context 'with tintColor' do
      it 'adds accentColor style' do
        converter = create_converter({
          'type' => 'View',
          'tintColor' => '#FF0000'
        })
        converter.send(:build_class_name)
        dynamic_styles = converter.instance_variable_get(:@dynamic_styles)
        expect(dynamic_styles['accentColor']).to eq("'#FF0000'")
      end
    end
  end

  describe '#build_testid_attr' do
    it 'returns data-testid attribute when testId is present' do
      converter = create_converter({
        'type' => 'View',
        'testId' => 'my-test-id'
      })
      attr = converter.send(:build_testid_attr)
      expect(attr).to eq(' data-testid="my-test-id"')
    end

    it 'returns empty string when testId is not present' do
      converter = create_converter({
        'type' => 'View'
      })
      attr = converter.send(:build_testid_attr)
      expect(attr).to eq('')
    end
  end

  describe '#build_tag_attr' do
    it 'returns data-tag attribute when tag is present' do
      converter = create_converter({
        'type' => 'View',
        'tag' => 'custom-tag'
      })
      attr = converter.send(:build_tag_attr)
      expect(attr).to eq(' data-tag="custom-tag"')
    end

    it 'returns empty string when tag is not present' do
      converter = create_converter({
        'type' => 'View'
      })
      attr = converter.send(:build_tag_attr)
      expect(attr).to eq('')
    end
  end

  describe '#convert_binding' do
    context 'with simple property binding' do
      it 'converts @{title} to {data.title}' do
        converter = create_converter({ 'type' => 'View' })
        result = converter.send(:convert_binding, '@{title}')
        expect(result).to eq('{data.title}')
      end
    end

    context 'with data prefix binding' do
      it 'converts @{data.name} to {data.name}' do
        converter = create_converter({ 'type' => 'View' })
        result = converter.send(:convert_binding, '@{data.name}')
        expect(result).to eq('{data.name}')
      end
    end

    context 'with viewModel prefix binding' do
      it 'converts @{viewModel.onTap} to {data.onTap}' do
        converter = create_converter({ 'type' => 'View' })
        result = converter.send(:convert_binding, '@{viewModel.onTap}')
        expect(result).to eq('{data.onTap}')
      end
    end

    context 'with nested property binding' do
      it 'converts @{item.name} to {data.item.name}' do
        converter = create_converter({ 'type' => 'View' })
        result = converter.send(:convert_binding, '@{item.name}')
        expect(result).to eq('{data.item.name}')
      end
    end

    context 'with plain text (no binding)' do
      it 'returns plain text as-is' do
        converter = create_converter({ 'type' => 'View' })
        result = converter.send(:convert_binding, 'Hello World')
        expect(result).to eq('Hello World')
      end
    end
  end

  describe '#build_onclick_attr' do
    context 'with onClick binding format' do
      it 'converts @{onTap} to data.onTap' do
        converter = create_converter({
          'type' => 'View',
          'onClick' => '@{onTap}'
        })
        attr = converter.send(:build_onclick_attr)
        expect(attr).to eq(' onClick={data.onTap}')
      end

      it 'converts @{viewModel.onTap} to data.onTap' do
        converter = create_converter({
          'type' => 'View',
          'onClick' => '@{viewModel.onTap}'
        })
        attr = converter.send(:build_onclick_attr)
        expect(attr).to eq(' onClick={data.onTap}')
      end
    end

    context 'with onclick selector format' do
      it 'converts selector to data.selector' do
        converter = create_converter({
          'type' => 'View',
          'onclick' => 'handleClick'
        })
        attr = converter.send(:build_onclick_attr)
        expect(attr).to eq(' onClick={data.handleClick}')
      end
    end

    context 'with link action' do
      it 'generates window.open for link action' do
        converter = create_converter({
          'type' => 'View',
          'onClick' => { 'action' => 'link', 'url' => 'https://example.com' }
        })
        attr = converter.send(:build_onclick_attr)
        expect(attr).to eq(" onClick={() => window.open('https://example.com', '_blank')}")
      end
    end
  end
end
