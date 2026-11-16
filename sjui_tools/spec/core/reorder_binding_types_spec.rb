# frozen_string_literal: true

require 'core/binding_validator'

# Collection.onReorder / reorderable, the types a binding to them is given when
# the data does not declare one (ticket jui-collection-drag-to-reorder, ruling B
# 2026-11-13): onReorder is called with (section, from, to); reorderable is on
# or off. The handler's own name says nothing (any name may be bound).
RSpec.describe SjuiTools::Core::BindingValidator do
  subject(:validator) { described_class.new }

  it 'gives onReorder the (section, from, to) handler type, whatever the name' do
    expect(validator.send(:infer_type, 'moveStop', 'onReorder')).to eq('((Int, Int, Int) -> Void)?')
    expect(validator.send(:infer_type, 'onReorder', 'onReorder')).to eq('((Int, Int, Int) -> Void)?')
  end

  it 'gives a bound reorderable a boolean' do
    expect(validator.send(:infer_type, 'editing', 'reorderable')).to eq('Bool')
  end

  it 'leaves onItemAppear and onClick as they were' do
    expect(validator.send(:infer_type, 'v', 'onClick')).not_to eq('((Int, Int, Int) -> Void)?')
  end
end
