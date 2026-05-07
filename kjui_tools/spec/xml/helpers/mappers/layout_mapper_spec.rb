# frozen_string_literal: true

require 'xml/helpers/mappers/layout_mapper'
require 'xml/helpers/mappers/dimension_mapper'

RSpec.describe XmlGenerator::Mappers::LayoutMapper do
  let(:dimension_mapper) { XmlGenerator::Mappers::DimensionMapper.new }
  let(:mapper) { described_class.new(dimension_mapper) }

  describe '#map_layout_attributes' do
    context 'dimension attributes' do
      it 'maps width' do
        result = mapper.map_layout_attributes('width', 100, 'View', nil)
        expect(result[:name]).to eq('layout_width')
        expect(result[:value]).to eq('100dp')
      end

      it 'maps height' do
        result = mapper.map_layout_attributes('height', 50, 'View', nil)
        expect(result[:name]).to eq('layout_height')
        expect(result[:value]).to eq('50dp')
      end

      it 'maps matchParent width' do
        result = mapper.map_layout_attributes('width', 'matchParent', 'View', nil)
        expect(result[:value]).to eq('match_parent')
      end

      it 'maps wrapContent height' do
        result = mapper.map_layout_attributes('height', 'wrapContent', 'View', nil)
        expect(result[:value]).to eq('wrap_content')
      end
    end

    context 'padding attributes' do
      it 'maps padding as single value' do
        result = mapper.map_layout_attributes('padding', 16, 'View', nil)
        expect(result[:name]).to eq('padding')
        expect(result[:value]).to eq('16dp')
      end

      it 'maps padding as array' do
        result = mapper.map_layout_attributes('padding', [10, 20, 30, 40], 'View', nil)
        expect(result[:name]).to eq('padding')
        expect(result[:value]).to eq('10dp')
      end

      it 'maps paddings' do
        result = mapper.map_layout_attributes('paddings', 8, 'View', nil)
        expect(result[:name]).to eq('padding')
      end

      it 'maps paddingTop' do
        result = mapper.map_layout_attributes('paddingTop', 10, 'View', nil)
        expect(result[:name]).to eq('paddingTop')
      end

      it 'maps paddingBottom' do
        result = mapper.map_layout_attributes('paddingBottom', 10, 'View', nil)
        expect(result[:name]).to eq('paddingBottom')
      end

      it 'maps paddingLeft to paddingStart' do
        result = mapper.map_layout_attributes('paddingLeft', 10, 'View', nil)
        expect(result[:name]).to eq('paddingStart')
      end

      it 'maps paddingRight to paddingEnd' do
        result = mapper.map_layout_attributes('paddingRight', 10, 'View', nil)
        expect(result[:name]).to eq('paddingEnd')
      end
    end

    context 'margin attributes' do
      it 'maps margin as single value' do
        result = mapper.map_layout_attributes('margin', 16, 'View', nil)
        expect(result[:name]).to eq('layout_margin')
        expect(result[:value]).to eq('16dp')
      end

      it 'maps margin as array' do
        result = mapper.map_layout_attributes('margin', [10, 20, 30, 40], 'View', nil)
        expect(result[:value]).to eq('10dp')
      end

      it 'maps topMargin' do
        result = mapper.map_layout_attributes('topMargin', 10, 'View', nil)
        expect(result[:name]).to eq('layout_marginTop')
      end

      it 'maps bottomMargin' do
        result = mapper.map_layout_attributes('bottomMargin', 10, 'View', nil)
        expect(result[:name]).to eq('layout_marginBottom')
      end

      it 'maps leftMargin to layout_marginStart' do
        result = mapper.map_layout_attributes('leftMargin', 10, 'View', nil)
        expect(result[:name]).to eq('layout_marginStart')
      end

      it 'maps rightMargin to layout_marginEnd' do
        result = mapper.map_layout_attributes('rightMargin', 10, 'View', nil)
        expect(result[:name]).to eq('layout_marginEnd')
      end
    end

    context 'layout specific' do
      it 'maps orientation' do
        result = mapper.map_layout_attributes('orientation', 'vertical', 'LinearLayout', nil)
        expect(result[:name]).to eq('orientation')
        expect(result[:value]).to eq('vertical')
      end

      it 'maps weight' do
        result = mapper.map_layout_attributes('weight', 1, 'View', nil)
        expect(result[:name]).to eq('layout_weight')
        expect(result[:value]).to eq('1')
      end

      it 'maps gravity center' do
        result = mapper.map_layout_attributes('gravity', 'center', 'View', nil)
        expect(result[:name]).to eq('gravity')
        expect(result[:value]).to eq('center')
      end

      it 'maps gravity array' do
        result = mapper.map_layout_attributes('gravity', ['center', 'top'], 'View', nil)
        expect(result[:value]).to eq('center|top')
      end

      it 'maps layout_gravity' do
        result = mapper.map_layout_attributes('layout_gravity', 'center', 'View', nil)
        expect(result[:name]).to eq('layout_gravity')
      end
    end

    context 'unknown attribute' do
      it 'returns nil for unknown attribute' do
        result = mapper.map_layout_attributes('unknown', 'value', 'View', nil)
        expect(result).to be_nil
      end
    end
  end

  describe '#map_alignment_attributes' do
    context 'in LinearLayout parent' do
      it 'maps alignTop to layout_gravity top' do
        result = mapper.map_alignment_attributes('alignTop', true, 'LinearLayout')
        expect(result[:name]).to eq('layout_gravity')
        expect(result[:value]).to eq('top')
      end

      it 'maps alignBottom to layout_gravity bottom' do
        result = mapper.map_alignment_attributes('alignBottom', true, 'LinearLayout')
        expect(result[:value]).to eq('bottom')
      end

      it 'maps alignLeft to layout_gravity start' do
        result = mapper.map_alignment_attributes('alignLeft', true, 'LinearLayout')
        expect(result[:value]).to eq('start')
      end

      it 'maps centerHorizontal to layout_gravity center_horizontal' do
        result = mapper.map_alignment_attributes('centerHorizontal', true, 'LinearLayout')
        expect(result[:value]).to eq('center_horizontal')
      end

      it 'maps centerInParent to layout_gravity center' do
        result = mapper.map_alignment_attributes('centerInParent', true, 'LinearLayout')
        expect(result[:value]).to eq('center')
      end
    end

    context 'in ConstraintLayout parent' do
      it 'maps alignTop to layout_constraintTop_toTopOf' do
        result = mapper.map_alignment_attributes('alignTop', true, 'ConstraintLayout')
        expect(result[:namespace]).to eq('app')
        expect(result[:name]).to eq('layout_constraintTop_toTopOf')
        expect(result[:value]).to eq('parent')
      end

      it 'maps alignBottom to layout_constraintBottom_toBottomOf' do
        result = mapper.map_alignment_attributes('alignBottom', true, 'ConstraintLayout')
        expect(result[:name]).to eq('layout_constraintBottom_toBottomOf')
      end

      it 'maps alignLeft to layout_constraintStart_toStartOf' do
        result = mapper.map_alignment_attributes('alignLeft', true, 'ConstraintLayout')
        expect(result[:name]).to eq('layout_constraintStart_toStartOf')
      end

      it 'maps alignRight to layout_constraintEnd_toEndOf' do
        result = mapper.map_alignment_attributes('alignRight', true, 'ConstraintLayout')
        expect(result[:name]).to eq('layout_constraintEnd_toEndOf')
      end
    end

    context 'in RelativeLayout parent' do
      it 'maps alignTop to layout_alignParentTop' do
        result = mapper.map_alignment_attributes('alignTop', true, 'RelativeLayout')
        expect(result[:name]).to eq('layout_alignParentTop')
      end

      it 'maps centerHorizontal to layout_centerHorizontal' do
        result = mapper.map_alignment_attributes('centerHorizontal', true, 'RelativeLayout')
        expect(result[:name]).to eq('layout_centerHorizontal')
      end
    end

    context 'relative positioning' do
      it 'maps alignTopOfView in ConstraintLayout' do
        result = mapper.map_alignment_attributes('alignTopOfView', 'other', 'ConstraintLayout')
        expect(result[:name]).to eq('layout_constraintBottom_toTopOf')
        expect(result[:value]).to eq('@id/other')
      end

      it 'maps alignBottomOfView in ConstraintLayout' do
        result = mapper.map_alignment_attributes('alignBottomOfView', 'other', 'ConstraintLayout')
        expect(result[:name]).to eq('layout_constraintTop_toBottomOf')
      end

      it 'maps above in RelativeLayout' do
        result = mapper.map_alignment_attributes('above', 'header', 'RelativeLayout')
        expect(result[:name]).to eq('layout_above')
        expect(result[:value]).to eq('@id/header')
      end

      it 'maps below in RelativeLayout' do
        result = mapper.map_alignment_attributes('below', 'header', 'RelativeLayout')
        expect(result[:name]).to eq('layout_below')
      end

      it 'maps toLeftOf in RelativeLayout' do
        result = mapper.map_alignment_attributes('toLeftOf', 'button', 'RelativeLayout')
        expect(result[:name]).to eq('layout_toStartOf')
      end

      it 'maps toRightOf in RelativeLayout' do
        result = mapper.map_alignment_attributes('toRightOf', 'button', 'RelativeLayout')
        expect(result[:name]).to eq('layout_toEndOf')
      end
    end

    context 'unknown attribute' do
      it 'returns nil for unknown alignment' do
        result = mapper.map_alignment_attributes('unknown', 'value', nil)
        expect(result).to be_nil
      end
    end
  end
end
