# frozen_string_literal: true

require 'uikit/view_binding_handler'

RSpec.describe SjuiTools::UIKit::ViewBindingHandler do
  let(:binding_content) { [] }
  let(:reset_text_views) { {} }
  let(:reset_constraint_views) { {} }
  let(:handler) { described_class.new(binding_content, reset_text_views, reset_constraint_views) }

  describe '#handle_common_binding' do
    it 'handles canTap' do
      result = handler.handle_common_binding('myView', 'canTap', 'true')

      expect(result).to be true
      expect(binding_content.join).to include('myView?.canTap = true')
    end

    it 'handles visibility' do
      result = handler.handle_common_binding('button', 'visibility', 'Visibility.GONE')

      expect(result).to be true
      expect(binding_content.join).to include('button?.visibility = Visibility.GONE')
    end

    it 'handles background' do
      result = handler.handle_common_binding('view', 'background', 'UIColor.red')

      expect(result).to be true
      expect(binding_content.join).to include('view?.setBackgroundColor(color: UIColor.red)')
    end

    it 'handles defaultBackground' do
      result = handler.handle_common_binding('btn', 'defaultBackground', 'UIColor.blue')

      expect(result).to be true
      expect(binding_content.join).to include('btn?.defaultBackgroundColor = UIColor.blue')
    end

    # Note: disabledBackground is only for SJUIButton, tested in ButtonBindingHandler

    it 'handles cornerRadius' do
      result = handler.handle_common_binding('card', 'cornerRadius', '8.0')

      expect(result).to be true
      expect(binding_content.join).to include('card?.layer.cornerRadius = 8.0')
    end

    it 'handles borderColor' do
      result = handler.handle_common_binding('view', 'borderColor', 'UIColor.black.cgColor')

      expect(result).to be true
      expect(binding_content.join).to include('view?.layer.borderColor = UIColor.black.cgColor')
    end

    it 'handles borderWidth' do
      result = handler.handle_common_binding('view', 'borderWidth', '1.0')

      expect(result).to be true
      expect(binding_content.join).to include('view?.layer.borderWidth = 1.0')
    end

    it 'handles clipToBounds' do
      result = handler.handle_common_binding('view', 'clipToBounds', 'true')

      expect(result).to be true
      expect(binding_content.join).to include('view?.clipsToBounds = true')
    end

    it 'handles alpha' do
      result = handler.handle_common_binding('view', 'alpha', '0.5')

      expect(result).to be true
      expect(binding_content.join).to include('view?.alpha = 0.5')
    end

    it 'handles bindingScript' do
      result = handler.handle_common_binding('view', 'bindingScript', 'customCode()')

      expect(result).to be true
      expect(binding_content.join).to include('customCode()')
    end

    context 'width binding' do
      it 'handles matchParent' do
        handler.handle_common_binding('view', 'width', 'matchParent')

        expect(binding_content.join).to include('UILayoutConstraintInfo.LayoutParams.matchParent')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles wrapContent' do
        handler.handle_common_binding('view', 'width', 'wrapContent')

        expect(binding_content.join).to include('UILayoutConstraintInfo.LayoutParams.wrapContent')
      end

      it 'handles numeric value' do
        handler.handle_common_binding('view', 'width', '200')

        expect(binding_content.join).to include('view?.constraintInfo?.width = 200')
      end
    end

    context 'height binding' do
      it 'handles matchParent' do
        handler.handle_common_binding('view', 'height', 'matchParent')

        expect(binding_content.join).to include('UILayoutConstraintInfo.LayoutParams.matchParent')
      end

      it 'handles wrapContent' do
        handler.handle_common_binding('view', 'height', 'wrapContent')

        expect(binding_content.join).to include('UILayoutConstraintInfo.LayoutParams.wrapContent')
      end

      it 'handles numeric value' do
        handler.handle_common_binding('view', 'height', '100')

        expect(binding_content.join).to include('view?.constraintInfo?.height = 100')
      end
    end

    it 'handles topMargin' do
      handler.handle_common_binding('view', 'topMargin', '10')

      expect(binding_content.join).to include('view?.constraintInfo?.topMargin = 10')
      expect(reset_constraint_views['view']).to be true
    end

    it 'handles rightMargin' do
      handler.handle_common_binding('view', 'rightMargin', '15')

      expect(binding_content.join).to include('view?.constraintInfo?.rightMargin = 15')
    end

    it 'handles bottomMargin' do
      handler.handle_common_binding('view', 'bottomMargin', '20')

      expect(binding_content.join).to include('view?.constraintInfo?.bottomMargin = 20')
    end

    it 'handles leftMargin' do
      handler.handle_common_binding('view', 'leftMargin', '25')

      expect(binding_content.join).to include('view?.constraintInfo?.leftMargin = 25')
    end

    it 'handles widthWeight' do
      handler.handle_common_binding('view', 'widthWeight', '0.5')

      expect(binding_content.join).to include('view?.constraintInfo?.widthWeight = 0.5')
    end

    it 'handles heightWeight' do
      handler.handle_common_binding('view', 'heightWeight', '0.3')

      expect(binding_content.join).to include('view?.constraintInfo?.heightWeight = 0.3')
    end

    # Easy難易度の新しい属性
    context 'size weight attributes' do
      it 'handles maxWidthWeight' do
        handler.handle_common_binding('view', 'maxWidthWeight', '0.8')

        expect(binding_content.join).to include('view?.constraintInfo?.maxWidthWeight = 0.8')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles minWidthWeight' do
        handler.handle_common_binding('view', 'minWidthWeight', '0.2')

        expect(binding_content.join).to include('view?.constraintInfo?.minWidthWeight = 0.2')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles maxHeightWeight' do
        handler.handle_common_binding('view', 'maxHeightWeight', '0.9')

        expect(binding_content.join).to include('view?.constraintInfo?.maxHeightWeight = 0.9')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles minHeightWeight' do
        handler.handle_common_binding('view', 'minHeightWeight', '0.1')

        expect(binding_content.join).to include('view?.constraintInfo?.minHeightWeight = 0.1')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles weight (alias for widthWeight)' do
        handler.handle_common_binding('view', 'weight', '0.7')

        expect(binding_content.join).to include('view?.constraintInfo?.widthWeight = 0.7')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles aspectWidth' do
        handler.handle_common_binding('view', 'aspectWidth', '16')

        expect(binding_content.join).to include('view?.constraintInfo?.aspectWidth = 16')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles aspectHeight' do
        handler.handle_common_binding('view', 'aspectHeight', '9')

        expect(binding_content.join).to include('view?.constraintInfo?.aspectHeight = 9')
        expect(reset_constraint_views['view']).to be true
      end
    end

    context 'padding attributes' do
      it 'handles paddingTop' do
        handler.handle_common_binding('view', 'paddingTop', '12')

        expect(binding_content.join).to include('view?.constraintInfo?.paddingTop = 12')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles paddingBottom' do
        handler.handle_common_binding('view', 'paddingBottom', '16')

        expect(binding_content.join).to include('view?.constraintInfo?.paddingBottom = 16')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles paddingLeft' do
        handler.handle_common_binding('view', 'paddingLeft', '8')

        expect(binding_content.join).to include('view?.constraintInfo?.paddingLeft = 8')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles paddingRight' do
        handler.handle_common_binding('view', 'paddingRight', '8')

        expect(binding_content.join).to include('view?.constraintInfo?.paddingRight = 8')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles paddingStart (RTL-aware)' do
        handler.handle_common_binding('view', 'paddingStart', '10')

        expect(binding_content.join).to include('view?.constraintInfo?.paddingStart = 10')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles paddingEnd (RTL-aware)' do
        handler.handle_common_binding('view', 'paddingEnd', '10')

        expect(binding_content.join).to include('view?.constraintInfo?.paddingEnd = 10')
        expect(reset_constraint_views['view']).to be true
      end

      # Note: innerPadding requires parsing (format: "top|left|bottom|right") - not supported for dynamic binding
    end

    context 'RTL-aware margin attributes' do
      it 'handles startMargin' do
        handler.handle_common_binding('view', 'startMargin', '12')

        expect(binding_content.join).to include('view?.constraintInfo?.startMargin = 12')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles endMargin' do
        handler.handle_common_binding('view', 'endMargin', '12')

        expect(binding_content.join).to include('view?.constraintInfo?.endMargin = 12')
        expect(reset_constraint_views['view']).to be true
      end
    end

    context 'min/max margin attributes' do
      it 'handles minTopMargin' do
        handler.handle_common_binding('view', 'minTopMargin', '5')

        expect(binding_content.join).to include('view?.constraintInfo?.minTopMargin = 5')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles maxTopMargin' do
        handler.handle_common_binding('view', 'maxTopMargin', '20')

        expect(binding_content.join).to include('view?.constraintInfo?.maxTopMargin = 20')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles minBottomMargin' do
        handler.handle_common_binding('view', 'minBottomMargin', '5')

        expect(binding_content.join).to include('view?.constraintInfo?.minBottomMargin = 5')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles maxBottomMargin' do
        handler.handle_common_binding('view', 'maxBottomMargin', '20')

        expect(binding_content.join).to include('view?.constraintInfo?.maxBottomMargin = 20')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles minLeftMargin' do
        handler.handle_common_binding('view', 'minLeftMargin', '5')

        expect(binding_content.join).to include('view?.constraintInfo?.minLeftMargin = 5')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles maxLeftMargin' do
        handler.handle_common_binding('view', 'maxLeftMargin', '20')

        expect(binding_content.join).to include('view?.constraintInfo?.maxLeftMargin = 20')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles minRightMargin' do
        handler.handle_common_binding('view', 'minRightMargin', '5')

        expect(binding_content.join).to include('view?.constraintInfo?.minRightMargin = 5')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles maxRightMargin' do
        handler.handle_common_binding('view', 'maxRightMargin', '20')

        expect(binding_content.join).to include('view?.constraintInfo?.maxRightMargin = 20')
        expect(reset_constraint_views['view']).to be true
      end
    end

    context 'layout alignment attributes' do
      it 'handles centerInParent' do
        handler.handle_common_binding('view', 'centerInParent', 'true')

        expect(binding_content.join).to include('view?.constraintInfo?.centerVertical = true')
        expect(binding_content.join).to include('view?.constraintInfo?.centerHorizontal = true')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles centerVertical' do
        handler.handle_common_binding('view', 'centerVertical', 'true')

        expect(binding_content.join).to include('view?.constraintInfo?.centerVertical = true')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles centerHorizontal' do
        handler.handle_common_binding('view', 'centerHorizontal', 'true')

        expect(binding_content.join).to include('view?.constraintInfo?.centerHorizontal = true')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles alignTop' do
        handler.handle_common_binding('view', 'alignTop', 'true')

        expect(binding_content.join).to include('view?.constraintInfo?.alignTop = true')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles alignBottom' do
        handler.handle_common_binding('view', 'alignBottom', 'true')

        expect(binding_content.join).to include('view?.constraintInfo?.alignBottom = true')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles alignLeft' do
        handler.handle_common_binding('view', 'alignLeft', 'true')

        expect(binding_content.join).to include('view?.constraintInfo?.alignLeft = true')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles alignRight' do
        handler.handle_common_binding('view', 'alignRight', 'true')

        expect(binding_content.join).to include('view?.constraintInfo?.alignRight = true')
        expect(reset_constraint_views['view']).to be true
      end
    end

    context 'size constraint attributes' do
      it 'handles minWidth' do
        handler.handle_common_binding('view', 'minWidth', '100')

        expect(binding_content.join).to include('view?.constraintInfo?.minWidth = 100')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles maxWidth' do
        handler.handle_common_binding('view', 'maxWidth', '300')

        expect(binding_content.join).to include('view?.constraintInfo?.maxWidth = 300')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles minHeight' do
        handler.handle_common_binding('view', 'minHeight', '50')

        expect(binding_content.join).to include('view?.constraintInfo?.minHeight = 50')
        expect(reset_constraint_views['view']).to be true
      end

      it 'handles maxHeight' do
        handler.handle_common_binding('view', 'maxHeight', '200')

        expect(binding_content.join).to include('view?.constraintInfo?.maxHeight = 200')
        expect(reset_constraint_views['view']).to be true
      end
    end

    context 'color attributes' do
      it 'handles tapBackground' do
        handler.handle_common_binding('view', 'tapBackground', 'UIColor.lightGray')

        expect(binding_content.join).to include('view?.tapBackgroundColor = UIColor.lightGray')
      end

      it 'handles highlightBackground' do
        handler.handle_common_binding('view', 'highlightBackground', 'UIColor.yellow')

        expect(binding_content.join).to include('view?.highlightBackgroundColor = UIColor.yellow')
      end

      it 'handles tintColor' do
        handler.handle_common_binding('view', 'tintColor', 'UIColor.blue')

        expect(binding_content.join).to include('view?.tintColor = UIColor.blue')
      end
    end

    context 'UIView standard attributes' do
      it 'handles userInteractionEnabled' do
        result = handler.handle_common_binding('view', 'userInteractionEnabled', 'true')

        expect(result).to be true
        expect(binding_content.join).to include('view?.isUserInteractionEnabled = true')
      end

      it 'handles tag' do
        result = handler.handle_common_binding('view', 'tag', '100')

        expect(result).to be true
        expect(binding_content.join).to include('view?.tag = 100')
      end
    end

    # Note: spacing is not a property of UILayoutConstraintInfo - not supported for dynamic binding

    it 'returns false for unknown key' do
      result = handler.handle_common_binding('view', 'unknownKey', 'value')

      expect(result).to be false
    end
  end

  describe '#handle_specific_binding' do
    it 'returns false by default' do
      result = handler.handle_specific_binding('view', 'key', 'value')

      expect(result).to be false
    end
  end
end
