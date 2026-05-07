# frozen_string_literal: true

require 'uikit/ui_control_event_manager'

RSpec.describe SjuiTools::UIKit::UIControlEventManager do
  let(:manager) { described_class.new }

  describe '#initialize' do
    it 'starts with empty events' do
      expect(manager.generate_bind_view_method).to eq('')
    end
  end

  describe '#reset' do
    it 'clears all events' do
      manager.add_click_event('button', '@{onTap}')
      manager.reset
      expect(manager.generate_bind_view_method).to eq('')
    end
  end

  describe '#add_click_event' do
    context 'with valid value' do
      it 'adds click event' do
        manager.add_click_event('myButton', '@{handleClick}')
        result = manager.generate_bind_view_method

        expect(result).to include('myButton?.click')
        expect(result).to include('self?.handleClick?()')
      end

      it 'strips binding markers' do
        manager.add_click_event('btn', '@{onClick}')
        result = manager.generate_bind_view_method

        expect(result).to include('self?.onClick?()')
        expect(result).not_to include('@{')
      end
    end

    context 'with nil value' do
      it 'does not add event' do
        manager.add_click_event('button', 'nil')
        expect(manager.generate_bind_view_method).to eq('')
      end
    end
  end

  describe '#add_long_press_event' do
    context 'with valid value' do
      it 'adds long press event with duration' do
        manager.add_long_press_event('myView', { 'closure' => '@{onLongPress}', 'duration' => 0.5 })
        result = manager.generate_bind_view_method

        expect(result).to include('myView?.longPress')
        expect(result).to include('duration: 0.5')
        expect(result).to include('onLongPress?(gesture)')
      end
    end

    context 'with nil value' do
      it 'does not add event' do
        manager.add_long_press_event('view', 'nil')
        expect(manager.generate_bind_view_method).to eq('')
      end
    end
  end

  describe '#add_pan_event' do
    context 'with valid value' do
      it 'adds pan event' do
        manager.add_pan_event('dragView', '@{onPan}')
        result = manager.generate_bind_view_method

        expect(result).to include('dragView?.pan')
        expect(result).to include('onPan?(gesture)')
      end
    end

    context 'with nil value' do
      it 'does not add event' do
        manager.add_pan_event('view', 'nil')
        expect(manager.generate_bind_view_method).to eq('')
      end
    end
  end

  describe '#add_pinch_event' do
    context 'with valid value' do
      it 'adds pinch event' do
        manager.add_pinch_event('zoomView', '@{onPinch}')
        result = manager.generate_bind_view_method

        expect(result).to include('zoomView?.pinch')
        expect(result).to include('onPinch?(gesture)')
      end
    end

    context 'with nil value' do
      it 'does not add event' do
        manager.add_pinch_event('view', 'nil')
        expect(manager.generate_bind_view_method).to eq('')
      end
    end
  end

  describe '#generate_bind_view_method' do
    context 'with no events' do
      it 'returns empty string' do
        expect(manager.generate_bind_view_method).to eq('')
      end
    end

    context 'with single click event' do
      it 'generates complete bind view method' do
        manager.add_click_event('button', '@{onTap}')
        result = manager.generate_bind_view_method

        expect(result).to include('override func bindView()')
        expect(result).to include('super.bindView()')
        expect(result).to include('isUserInteractionEnabled = true')
      end
    end

    context 'with multiple events' do
      it 'includes all events' do
        manager.add_click_event('btn1', '@{onClick1}')
        manager.add_click_event('btn2', '@{onClick2}')
        manager.add_pan_event('dragArea', '@{onDrag}')

        result = manager.generate_bind_view_method

        expect(result).to include('btn1?.click')
        expect(result).to include('btn2?.click')
        expect(result).to include('dragArea?.pan')
      end
    end

    context 'with long press event' do
      it 'generates different format than click' do
        manager.add_long_press_event('view', { 'closure' => '@{onLongPress}', 'duration' => 1.0 })
        result = manager.generate_bind_view_method

        expect(result).to include('longPress(duration: 1.0)')
        expect(result).not_to include('.click')
      end
    end
  end
end
