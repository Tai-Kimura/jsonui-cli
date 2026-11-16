# frozen_string_literal: true

require 'swiftui/view_registry'

RSpec.describe SjuiTools::SwiftUI::ViewRegistry do
  describe '#register_view' do
    it 'registers a view with id' do
      registry = described_class.new
      component = { 'type' => 'Label', 'text' => 'Hello' }

      registry.register_view('label1', component)

      positions = registry.resolve_positions
      expect(positions['label1']).not_to be_nil
    end

    it 'ignores nil id' do
      registry = described_class.new
      component = { 'type' => 'Label' }

      registry.register_view(nil, component)

      expect(registry.resolve_positions).to be_empty
    end

    it 'registers views in order' do
      registry = described_class.new
      registry.register_view('view1', { 'type' => 'View' })
      registry.register_view('view2', { 'type' => 'View' })
      registry.register_view('view3', { 'type' => 'View' })

      positions = registry.resolve_positions

      expect(positions['view1'][:zIndex]).to eq(0)
      expect(positions['view2'][:zIndex]).to eq(1)
      expect(positions['view3'][:zIndex]).to eq(2)
    end
  end

  describe 'relative constraints' do
    it 'collects alignTopOfView constraint' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignTopOfView' => 'target' })

      constraints = registry.get_constraints_for('source')

      expect(constraints.first[:type]).to eq(:align_top_of)
      expect(constraints.first[:target]).to eq('target')
    end

    it 'collects alignBottomOfView constraint' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignBottomOfView' => 'target' })

      constraints = registry.get_constraints_for('source')

      expect(constraints.first[:type]).to eq(:align_bottom_of)
    end

    it 'collects alignLeftOfView constraint' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignLeftOfView' => 'target' })

      constraints = registry.get_constraints_for('source')

      expect(constraints.first[:type]).to eq(:align_left_of)
    end

    it 'collects alignRightOfView constraint' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignRightOfView' => 'target' })

      constraints = registry.get_constraints_for('source')

      expect(constraints.first[:type]).to eq(:align_right_of)
    end

    it 'collects alignTopView constraint with spacing' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignTopView' => 'target', 'topMargin' => 10 })

      constraints = registry.get_constraints_for('source')

      expect(constraints.first[:type]).to eq(:above)
      expect(constraints.first[:spacing]).to eq(10)
    end

    it 'collects alignBottomView constraint' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignBottomView' => 'target', 'bottomMargin' => 5 })

      constraints = registry.get_constraints_for('source')

      expect(constraints.first[:type]).to eq(:below)
      expect(constraints.first[:spacing]).to eq(5)
    end

    it 'collects alignLeftView constraint' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignLeftView' => 'target', 'leftMargin' => 8 })

      constraints = registry.get_constraints_for('source')

      expect(constraints.first[:type]).to eq(:left_of)
      expect(constraints.first[:spacing]).to eq(8)
    end

    it 'collects alignRightView constraint' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignRightView' => 'target', 'rightMargin' => 12 })

      constraints = registry.get_constraints_for('source')

      expect(constraints.first[:type]).to eq(:right_of)
      expect(constraints.first[:spacing]).to eq(12)
    end
  end

  describe '#depends_on?' do
    it 'returns true when source depends on target' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignTopOfView' => 'target' })

      expect(registry.depends_on?('source', 'target')).to be true
    end

    it 'returns false when no dependency' do
      registry = described_class.new
      registry.register_view('view1', { 'type' => 'View' })
      registry.register_view('view2', { 'type' => 'View' })

      expect(registry.depends_on?('view1', 'view2')).to be false
    end
  end

  describe '#generate_alignment_modifiers' do
    it 'generates alignment guide for align_top_of' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignTopOfView' => 'target' })

      modifiers = registry.generate_alignment_modifiers('source')

      expect(modifiers.first).to include('.alignmentGuide(.top)')
    end

    it 'generates offset for above constraint' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignTopView' => 'target', 'topMargin' => 10 })

      modifiers = registry.generate_alignment_modifiers('source')

      expect(modifiers.first).to include('.offset(y: -10)')
    end

    it 'generates offset for below constraint' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignBottomView' => 'target', 'bottomMargin' => 5 })

      modifiers = registry.generate_alignment_modifiers('source')

      expect(modifiers.first).to include('.offset(y: 5)')
    end

    it 'returns empty array when no constraints' do
      registry = described_class.new
      registry.register_view('view1', { 'type' => 'View' })

      modifiers = registry.generate_alignment_modifiers('view1')

      expect(modifiers).to be_empty
    end
  end

  describe '#resolve_positions' do
    it 'includes relative constraint info' do
      registry = described_class.new
      registry.register_view('target', { 'type' => 'View' })
      registry.register_view('source', { 'type' => 'View', 'alignTopOfView' => 'target' })

      positions = registry.resolve_positions

      expect(positions['source'][:relative_to]).to eq('target')
      expect(positions['source'][:constraint_type]).to eq(:align_top_of)
    end
  end
end
