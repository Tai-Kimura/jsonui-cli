# frozen_string_literal: true

require 'core/binding_validator'

# A date SelectBox has no index: an onValueChange declared to take one —
# `(Int)`, `(String, Int)` — is not called on any path, and the build says so
# (BindingValidatorCore.date_pick_handler_problem; 4f's ruling on
# control-onclick-is-called-differently-on-every-path, 1.9.0). The shared
# core is the same bytes in sjui, kjui and rjui. sjui writes an `// ERROR:`
# comment where the call would be (selectbox_on_value_change_arity_spec).
RSpec.describe SjuiTools::Core::BindingValidator do
  subject(:validator) { described_class.new }

  def warnings_for(klass, box = {})
    validator.validate(
      'type' => 'View',
      'data' => [{ 'name' => 'pick', 'class' => klass }, { 'name' => 'day', 'class' => 'String' }],
      'child' => [{ 'type' => 'SelectBox', 'id' => 'when', 'selectItemType' => 'Date',
                    'selectedDate' => '@{day}', 'onValueChange' => '@{pick}' }.merge(box)]
    ).grep(/SelectBox\.onValueChange/)
  end

  it 'names a date handler declared to take an index' do
    ['((String, Int) -> Void)?', '((Int) -> Void)?', '((String, Int) -> Unit)?'].each do |klass|
      expect(warnings_for(klass)).to eq([
        "[id=when] 'SelectBox.onValueChange' 'pick' (#{klass}) is not called: " \
        'a date SelectBox has no index: declare onValueChange as (String) or (String, String)'
      ])
    end
  end

  it 'says nothing for a date handler that takes the date, or nothing' do
    ['((String) -> Void)?', '((String, String) -> Void)?', '(() -> Void)?', 'Function'].each do |klass|
      expect(warnings_for(klass)).to be_empty, klass
    end
  end

  it 'says nothing for a list SelectBox, whose pick has an index' do
    expect(warnings_for('((String, Int) -> Void)?', 'selectItemType' => 'Normal', 'items' => %w[a b])).to be_empty
    expect(warnings_for('((Int) -> Void)?', 'selectItemType' => nil)).to be_empty
  end

  it 'reads the closure parameters as the codegen does' do
    core = JsonUIShared::BindingValidatorCore
    expect(core.closure_parameters('((String, Int) -> Void)?')).to eq(%w[String Int])
    expect(core.closure_parameters('((String) -> Void)?')).to eq(%w[String])
    expect(core.closure_parameters('(() -> Void)?')).to eq([])
    expect(core.closure_parameters('String')).to be_nil
  end
end
