# frozen_string_literal: true

require 'swiftui/views/relative_positioning_helper'

RSpec.describe SjuiTools::SwiftUI::Views::RelativePositioningHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::RelativePositioningHelper
    end
  end
  let(:helper) { helper_class.new }

  describe '#has_relative_constraint?' do
    context 'with relative positioning properties' do
      it 'returns truthy for toLeftOf' do
        child = { 'toLeftOf' => 'target' }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for toRightOf' do
        child = { 'toRightOf' => 'target' }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for above' do
        child = { 'above' => 'target' }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for below' do
        child = { 'below' => 'target' }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for alignTop' do
        child = { 'alignTop' => true }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for alignBottom' do
        child = { 'alignBottom' => true }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for alignLeft' do
        child = { 'alignLeft' => true }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for alignRight' do
        child = { 'alignRight' => true }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for centerHorizontal' do
        child = { 'centerHorizontal' => true }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for centerVertical' do
        child = { 'centerVertical' => true }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for centerInParent' do
        child = { 'centerInParent' => true }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for alignTopView' do
        child = { 'alignTopView' => 'target' }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for alignTopOfView' do
        child = { 'alignTopOfView' => 'target' }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for toStartOf' do
        child = { 'toStartOf' => 'target' }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end

      it 'returns truthy for toEndOf' do
        child = { 'toEndOf' => 'target' }
        expect(helper.has_relative_constraint?(child)).to be_truthy
      end
    end

    context 'without relative positioning' do
      it 'returns falsy for empty hash' do
        expect(helper.has_relative_constraint?({})).to be_falsy
      end

      it 'returns falsy for non-hash' do
        expect(helper.has_relative_constraint?(nil)).to be_falsy
        expect(helper.has_relative_constraint?('string')).to be_falsy
      end

      it 'returns falsy for normal component' do
        child = { 'type' => 'Label', 'text' => 'Hello' }
        expect(helper.has_relative_constraint?(child)).to be_falsy
      end
    end
  end

  describe '#has_relative_positioning?' do
    context 'with relative children' do
      it 'returns true when any child has relative constraint' do
        children = [
          { 'type' => 'Label' },
          { 'type' => 'View', 'alignTop' => true }
        ]
        expect(helper.has_relative_positioning?(children)).to be true
      end
    end

    context 'without relative children' do
      it 'returns false for empty array' do
        expect(helper.has_relative_positioning?([])).to be false
      end

      it 'returns false for non-array' do
        expect(helper.has_relative_positioning?(nil)).to be false
        expect(helper.has_relative_positioning?({})).to be false
      end

      it 'returns false when no children have constraints' do
        children = [
          { 'type' => 'Label' },
          { 'type' => 'Button' }
        ]
        expect(helper.has_relative_positioning?(children)).to be false
      end
    end
  end

  describe '#calculate_relative_positions' do
    it 'returns positions hash' do
      children = [
        { 'id' => 'view1', 'type' => 'View' },
        { 'id' => 'view2', 'type' => 'View', 'toLeftOf' => 'view1' }
      ]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view1']).not_to be_nil
      expect(positions['view2']).not_to be_nil
    end

    it 'generates child IDs when not provided' do
      children = [
        { 'type' => 'View' },
        { 'type' => 'Label' }
      ]

      positions = helper.calculate_relative_positions(children)

      expect(positions['child_0']).not_to be_nil
      expect(positions['child_1']).not_to be_nil
    end

    it 'extracts toLeftOf constraint' do
      children = [{ 'id' => 'view', 'toLeftOf' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:toLeftOf)
      expect(positions['view'][:constraints].first[:target]).to eq('target')
    end

    it 'extracts toRightOf constraint' do
      children = [{ 'id' => 'view', 'toRightOf' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:toRightOf)
    end

    it 'extracts above constraint' do
      children = [{ 'id' => 'view', 'above' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:above)
    end

    it 'extracts below constraint' do
      children = [{ 'id' => 'view', 'below' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:below)
    end

    it 'extracts alignLeft with string target' do
      children = [{ 'id' => 'view', 'alignLeft' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:alignLeft)
      expect(positions['view'][:constraints].first[:target]).to eq('target')
    end

    it 'extracts alignLeft with parent target' do
      children = [{ 'id' => 'view', 'alignLeft' => true }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:alignLeft)
      expect(positions['view'][:constraints].first[:target]).to eq(:parent)
    end

    it 'extracts centerInParent constraint' do
      children = [{ 'id' => 'view', 'centerInParent' => true }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:centerInParent)
      expect(positions['view'][:constraints].first[:target]).to eq(:parent)
    end

    it 'extracts margins' do
      children = [{
        'id' => 'view',
        'topMargin' => 10,
        'bottomMargin' => 20,
        'leftMargin' => 5,
        'rightMargin' => 15
      }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:margins][:top]).to eq(10)
      expect(positions['view'][:margins][:bottom]).to eq(20)
      expect(positions['view'][:margins][:left]).to eq(5)
      expect(positions['view'][:margins][:right]).to eq(15)
    end

    it 'handles alternative margin property names' do
      children = [{
        'id' => 'view',
        'marginTop' => 10,
        'marginLeft' => 5,
        'startMargin' => 8
      }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:margins][:top]).to eq(10)
      expect(positions['view'][:margins][:left]).to eq(5)
    end

    it 'skips non-hash children' do
      children = [nil, 'string', { 'id' => 'valid' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions.keys).to contain_exactly('valid')
    end

    it 'extracts toStartOf constraint' do
      children = [{ 'id' => 'view', 'toStartOf' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:toStartOf)
      expect(positions['view'][:constraints].first[:target]).to eq('target')
    end

    it 'extracts toEndOf constraint' do
      children = [{ 'id' => 'view', 'toEndOf' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:toEndOf)
      expect(positions['view'][:constraints].first[:target]).to eq('target')
    end

    it 'extracts alignRight with string target' do
      children = [{ 'id' => 'view', 'alignRight' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:alignRight)
      expect(positions['view'][:constraints].first[:target]).to eq('target')
    end

    it 'extracts alignRight with parent target' do
      children = [{ 'id' => 'view', 'alignRight' => true }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:alignRight)
      expect(positions['view'][:constraints].first[:target]).to eq(:parent)
    end

    it 'extracts alignTop with string target' do
      children = [{ 'id' => 'view', 'alignTop' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:alignTop)
      expect(positions['view'][:constraints].first[:target]).to eq('target')
    end

    it 'extracts alignTop with parent target' do
      children = [{ 'id' => 'view', 'alignTop' => true }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:alignTop)
      expect(positions['view'][:constraints].first[:target]).to eq(:parent)
    end

    it 'extracts alignBottom with string target' do
      children = [{ 'id' => 'view', 'alignBottom' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:alignBottom)
      expect(positions['view'][:constraints].first[:target]).to eq('target')
    end

    it 'extracts alignBottom with parent target' do
      children = [{ 'id' => 'view', 'alignBottom' => true }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:alignBottom)
      expect(positions['view'][:constraints].first[:target]).to eq(:parent)
    end

    it 'extracts centerHorizontal with string target' do
      children = [{ 'id' => 'view', 'centerHorizontal' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:centerHorizontal)
      expect(positions['view'][:constraints].first[:target]).to eq('target')
    end

    it 'extracts centerHorizontal with parent target' do
      children = [{ 'id' => 'view', 'centerHorizontal' => true }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:centerHorizontal)
      expect(positions['view'][:constraints].first[:target]).to eq(:parent)
    end

    it 'extracts centerVertical with string target' do
      children = [{ 'id' => 'view', 'centerVertical' => 'target' }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:centerVertical)
      expect(positions['view'][:constraints].first[:target]).to eq('target')
    end

    it 'extracts centerVertical with parent target' do
      children = [{ 'id' => 'view', 'centerVertical' => true }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:constraints].first[:type]).to eq(:centerVertical)
      expect(positions['view'][:constraints].first[:target]).to eq(:parent)
    end

    it 'handles marginStart and marginEnd' do
      children = [{
        'id' => 'view',
        'marginStart' => 12,
        'marginEnd' => 18
      }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:margins][:left]).to eq(12)
      expect(positions['view'][:margins][:right]).to eq(18)
    end

    # A relative position is a fixed inset, so a bounded margin has no slack to
    # flex into and collapses to its lower bound.
    it 'collapses bounded margins to their lower bound' do
      children = [{
        'id' => 'view',
        'minStartMargin' => 8,
        'maxStartMargin' => 40,
        'minEndMargin' => 6
      }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:margins][:left]).to eq(8)
      expect(positions['view'][:margins][:right]).to eq(6)
    end

    it 'still prefers a fixed margin over a bounded one' do
      children = [{ 'id' => 'view', 'startMargin' => 4, 'minStartMargin' => 8 }]

      positions = helper.calculate_relative_positions(children)

      expect(positions['view'][:margins][:left]).to eq(4)
    end
  end
end
