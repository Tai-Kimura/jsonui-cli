# frozen_string_literal: true

require 'swiftui/binding/view_binding_handler'

RSpec.describe SjuiTools::SwiftUI::Binding::ViewBindingHandler do
  let(:handler) { described_class.new }

  describe '#is_binding?' do
    context 'with valid binding syntax' do
      it 'returns true for @{property}' do
        expect(handler.is_binding?('@{userName}')).to be true
      end

      it 'returns true for nested property' do
        expect(handler.is_binding?('@{user.name}')).to be true
      end
    end

    context 'with invalid syntax' do
      it 'returns false for plain strings' do
        expect(handler.is_binding?('plain text')).to be false
      end

      it 'returns false for incomplete binding' do
        expect(handler.is_binding?('@{incomplete')).to be false
        expect(handler.is_binding?('incomplete}')).to be false
      end

      it 'returns false for non-strings' do
        expect(handler.is_binding?(123)).to be false
        expect(handler.is_binding?(nil)).to be false
      end
    end
  end

  describe '#parse_binding' do
    context 'with valid binding' do
      it 'returns viewModel.data binding' do
        result = handler.parse_binding('@{userName}')
        expect(result).to eq('$data.userName')
      end

      it 'handles nested properties' do
        result = handler.parse_binding('@{user.profile.name}')
        expect(result).to eq('$data.user.profile.name')
      end
    end

    context 'with invalid binding' do
      it 'returns nil for plain strings' do
        expect(handler.parse_binding('plain text')).to be_nil
      end

      it 'returns nil for incomplete binding' do
        expect(handler.parse_binding('@{incomplete')).to be_nil
      end
    end
  end

  describe '#get_value' do
    context 'with binding expression' do
      it 'returns parsed binding' do
        result = handler.get_value('@{property}')
        expect(result).to eq('$data.property')
      end
    end

    context 'with literal value' do
      it 'returns the value' do
        expect(handler.get_value('literal')).to eq('literal')
        expect(handler.get_value(42)).to eq(42)
      end
    end

    context 'with nil value' do
      it 'returns default' do
        expect(handler.get_value(nil, 'default')).to eq('default')
      end
    end
  end

  describe '#handle_common_binding' do
    let(:component) { { 'type' => 'View' } }

    context 'with visibility binding' do
      it 'returns nil (handled by VisibilityWrapper)' do
        result = handler.handle_common_binding(component, 'visibility', '@{isVisible}')
        # Visibility is handled by VisibilityWrapper in child_renderer.rb, not here
        expect(result).to be_nil
      end
    end

    context 'with background binding' do
      # Background is a color, so it's read-only and wrapped through the shared color resolver.
      it 'returns background modifier' do
        result = handler.handle_common_binding(component, 'background', '@{bgColor}')
        expect(result).to include('.background(')
        expect(result).to include('data.bgColor')
        expect(result).not_to include('$data.bgColor')
      end
    end

    context 'with cornerRadius binding' do
      # cornerRadius takes CGFloat (read-only), so uses data. not $data.
      it 'returns cornerRadius modifier' do
        result = handler.handle_common_binding(component, 'cornerRadius', '@{radius}')
        expect(result).to eq('.cornerRadius(data.radius)')
      end
    end

    context 'with opacity binding' do
      # opacity takes Double (read-only), so uses data. not $data.
      it 'returns opacity modifier' do
        result = handler.handle_common_binding(component, 'opacity', '@{alpha}')
        expect(result).to eq('.opacity(data.alpha)')
      end
    end

    context 'with alpha binding (alias)' do
      it 'returns opacity modifier' do
        result = handler.handle_common_binding(component, 'alpha', '@{alphaValue}')
        expect(result).to eq('.opacity(data.alphaValue)')
      end
    end

    context 'with disabled binding' do
      # disabled takes Bool (read-only), so uses data. not $data.
      it 'returns disabled modifier' do
        result = handler.handle_common_binding(component, 'disabled', '@{isDisabled}')
        expect(result).to eq('.disabled(data.isDisabled)')
      end
    end

    context 'with non-binding value' do
      it 'returns nil' do
        expect(handler.handle_common_binding(component, 'opacity', 0.5)).to be_nil
      end
    end

    context 'with unknown key' do
      it 'returns nil' do
        expect(handler.handle_common_binding(component, 'unknown', '@{value}')).to be_nil
      end
    end
  end

  describe '#process_bindings' do
    context 'with multiple bindings' do
      let(:component) do
        {
          'type' => 'View',
          'opacity' => '@{alpha}',
          'background' => '@{bgColor}',
          'text' => 'Static text'
        }
      end

      it 'returns array of modifiers' do
        result = handler.process_bindings(component)

        expect(result).to include('.opacity(data.alpha)')
        expect(result.any? { |m| m.include?('.background(') && m.include?('data.bgColor') }).to be true
      end

      it 'does not include non-binding values' do
        result = handler.process_bindings(component)
        expect(result.any? { |m| m&.include?('Static text') }).to be false
      end
    end

    context 'with no bindings' do
      let(:component) do
        {
          'type' => 'View',
          'opacity' => 0.5,
          'text' => 'Static'
        }
      end

      it 'returns empty array' do
        result = handler.process_bindings(component)
        expect(result).to be_empty
      end
    end
  end

  describe '#handle_specific_binding' do
    it 'returns nil (base implementation)' do
      expect(handler.handle_specific_binding({}, 'key', 'value')).to be_nil
    end
  end
end
