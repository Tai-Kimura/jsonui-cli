# frozen_string_literal: true

require 'swiftui/views/color_helper'

RSpec.describe SjuiTools::SwiftUI::Views::ColorHelper do
  let(:helper_instance) do
    Class.new do
      include SjuiTools::SwiftUI::Views::ColorHelper
    end.new
  end

  describe '#size_to_swiftui' do
    context 'with matchParent' do
      it 'returns .infinity' do
        expect(helper_instance.size_to_swiftui('matchParent')).to eq('.infinity')
      end
    end

    context 'with wrapContent' do
      it 'returns nil' do
        expect(helper_instance.size_to_swiftui('wrapContent')).to be_nil
      end
    end

    context 'with numeric values' do
      it 'handles Integer' do
        expect(helper_instance.size_to_swiftui(100)).to eq('100')
      end

      it 'handles Float' do
        expect(helper_instance.size_to_swiftui(100.5)).to eq('100.5')
      end
    end

    context 'with string values' do
      it 'handles numeric string' do
        expect(helper_instance.size_to_swiftui('100')).to eq('100')
      end

      it 'handles variable name' do
        expect(helper_instance.size_to_swiftui('screenWidth')).to eq('screenWidth')
      end
    end

    context 'with nil' do
      it 'returns nil' do
        expect(helper_instance.size_to_swiftui(nil)).to be_nil
      end
    end
  end

  describe '#get_swiftui_color' do
    context 'with hex color' do
      it 'returns configuration color getter' do
        result = helper_instance.get_swiftui_color('#FF0000')
        expect(result).to include('SwiftJsonUIConfiguration.shared.getColor')
        expect(result).to include('#FF0000')
      end
    end

    context 'with named color' do
      it 'returns configuration color getter' do
        result = helper_instance.get_swiftui_color('primary_color')
        expect(result).to include('SwiftJsonUIConfiguration.shared.getColor')
        expect(result).to include('primary_color')
      end
    end

    context 'with nil or empty' do
      it 'returns Color.clear for nil' do
        expect(helper_instance.get_swiftui_color(nil)).to eq('Color.clear')
      end

      it 'returns Color.clear for empty string' do
        expect(helper_instance.get_swiftui_color('')).to eq('Color.clear')
      end
    end

    context 'with binding expression' do
      after(:each) do
        # Clean up thread-local storage
        SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
      end

      it 'returns data binding with ?? Color.clear for optional property (no defaultValue)' do
        # Property without defaultValue is optional
        SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
          'buttonColor' => { 'name' => 'buttonColor', 'type' => 'Color' }
        }
        result = helper_instance.get_swiftui_color('@{buttonColor}')
        expect(result).to eq('data.buttonColor ?? Color.clear')
      end

      it 'returns data binding without ?? for non-optional property (with defaultValue)' do
        # Property with defaultValue is non-optional
        SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
          'buttonColor' => { 'name' => 'buttonColor', 'type' => 'Color', 'defaultValue' => '#FF0000' }
        }
        result = helper_instance.get_swiftui_color('@{buttonColor}')
        expect(result).to eq('data.buttonColor')
      end

      it 'resolves an UNDECLARED property as a colour name, not as a Color' do
        # A colour arrives from JSON as a string, so String is what an
        # undeclared property almost certainly is. `data.x ?? Color.clear`
        # only compiles if a `Color?` property happens to exist — it was
        # guessing the rarer case exactly where the generator knows least.
        SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
        result = helper_instance.get_swiftui_color('@{unknownColor}')
        expect(result).to eq('SwiftJsonUIConfiguration.shared.getColor(for: data.unknownColor) ?? Color.clear')
      end
    end
  end

  describe '#gradient_direction_to_swiftui' do
    context 'with vertical directions' do
      it 'handles vertical' do
        result = helper_instance.gradient_direction_to_swiftui('vertical')
        expect(result).to include('.top')
        expect(result).to include('.bottom')
      end

      it 'handles top_bottom' do
        result = helper_instance.gradient_direction_to_swiftui('top_bottom')
        expect(result).to include('startPoint: .top')
        expect(result).to include('endPoint: .bottom')
      end

      it 'handles bottom_top' do
        result = helper_instance.gradient_direction_to_swiftui('bottom_top')
        expect(result).to include('startPoint: .bottom')
        expect(result).to include('endPoint: .top')
      end
    end

    context 'with horizontal directions' do
      it 'handles horizontal' do
        result = helper_instance.gradient_direction_to_swiftui('horizontal')
        expect(result).to include('.leading')
        expect(result).to include('.trailing')
      end

      it 'handles left_right' do
        result = helper_instance.gradient_direction_to_swiftui('left_right')
        expect(result).to include('startPoint: .leading')
        expect(result).to include('endPoint: .trailing')
      end

      it 'handles right_left' do
        result = helper_instance.gradient_direction_to_swiftui('right_left')
        expect(result).to include('startPoint: .trailing')
        expect(result).to include('endPoint: .leading')
      end
    end

    context 'with diagonal directions' do
      it 'handles topLeft_bottomRight' do
        result = helper_instance.gradient_direction_to_swiftui('topLeft_bottomRight')
        expect(result).to include('startPoint: .topLeading')
        expect(result).to include('endPoint: .bottomTrailing')
      end

      it 'handles diagonal' do
        result = helper_instance.gradient_direction_to_swiftui('diagonal')
        expect(result).to include('startPoint: .topLeading')
        expect(result).to include('endPoint: .bottomTrailing')
      end

      it 'handles topRight_bottomLeft' do
        result = helper_instance.gradient_direction_to_swiftui('topRight_bottomLeft')
        expect(result).to include('startPoint: .topTrailing')
        expect(result).to include('endPoint: .bottomLeading')
      end

      it 'handles bottomLeft_topRight' do
        result = helper_instance.gradient_direction_to_swiftui('bottomLeft_topRight')
        expect(result).to include('startPoint: .bottomLeading')
        expect(result).to include('endPoint: .topTrailing')
      end

      it 'handles bottomRight_topLeft' do
        result = helper_instance.gradient_direction_to_swiftui('bottomRight_topLeft')
        expect(result).to include('startPoint: .bottomTrailing')
        expect(result).to include('endPoint: .topLeading')
      end
    end

    context 'with unknown direction' do
      it 'defaults to top-bottom' do
        result = helper_instance.gradient_direction_to_swiftui('unknown')
        expect(result).to include('startPoint: .top')
        expect(result).to include('endPoint: .bottom')
      end
    end
  end
end
