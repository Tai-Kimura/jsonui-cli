# frozen_string_literal: true

require 'uikit/view_binding_handler_factory'

RSpec.describe SjuiTools::UIKit::ViewBindingHandlerFactory do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }

  describe '.create_handler' do
    it 'creates ButtonBindingHandler for Button' do
      handler = described_class.create_handler('Button', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::ButtonBindingHandler)
    end

    it 'creates CheckBindingHandler for Check' do
      handler = described_class.create_handler('Check', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::CheckBindingHandler)
    end

    it 'creates CollectionViewBindingHandler for CollectionView' do
      handler = described_class.create_handler('CollectionView', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::CollectionViewBindingHandler)
    end

    it 'creates NetworkImageBindingHandler for NetworkImage' do
      handler = described_class.create_handler('NetworkImage', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::NetworkImageBindingHandler)
    end

    it 'creates NetworkImageBindingHandler for CircleImage' do
      handler = described_class.create_handler('CircleImage', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::NetworkImageBindingHandler)
    end

    it 'creates IconLabelBindingHandler for IconLabel' do
      handler = described_class.create_handler('IconLabel', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::IconLabelBindingHandler)
    end

    it 'creates ImageBindingHandler for Image' do
      handler = described_class.create_handler('Image', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::ImageBindingHandler)
    end

    it 'creates LabelBindingHandler for Label' do
      handler = described_class.create_handler('Label', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::LabelBindingHandler)
    end

    it 'creates RadioBindingHandler for Radio' do
      handler = described_class.create_handler('Radio', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::RadioBindingHandler)
    end

    it 'creates ScrollBindingHandler for Scroll' do
      handler = described_class.create_handler('Scroll', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::ScrollBindingHandler)
    end

    it 'creates SelectBoxBindingHandler for SelectBox' do
      handler = described_class.create_handler('SelectBox', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::SelectBoxBindingHandler)
    end

    it 'creates SwitchBindingHandler for Switch' do
      handler = described_class.create_handler('Switch', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::SwitchBindingHandler)
    end

    it 'creates TextFieldBindingHandler for TextField' do
      handler = described_class.create_handler('TextField', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::TextFieldBindingHandler)
    end

    it 'creates TextViewBindingHandler for TextView' do
      handler = described_class.create_handler('TextView', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::TextViewBindingHandler)
    end

    it 'creates default ViewBindingHandler for unknown type' do
      handler = described_class.create_handler('Unknown', binding_content, reset_text_views, reset_constraint_views)
      expect(handler).to be_a(SjuiTools::UIKit::ViewBindingHandler)
    end
  end
end
