# frozen_string_literal: true

require_relative '../../lib/core/binding_validator'

# Every @{...} in a string value uses the layout's data, wherever it sits in
# the string (jsonui-cli 1.9.0). Until then only a value that started with
# "@{" and ended with "}" was read, and read whole:
#   - "Hi @{who}" used nothing, so 'who' was "defined but never used";
#   - "@{first} and @{second}" was read as the one expression
#     "first} and @{second", so 'and' was "not defined in data".
# A whole binding is now a value that is one @{...} and nothing else; its
# checks (undefined names, business logic, color type) are as before. A name
# data lacks is still not named inside mixed text: an app's own converter
# may keep that text literal (JsonUIDocument's CodeBlock.code samples), and
# the canon has no escape for "@{".
RSpec.describe RjuiTools::Core::BindingValidator, '(every @{...} in a string uses its data)' do
  subject(:validator) { described_class.new }

  def never_used(warnings, name)
    warnings.select { |w| w.include?("Data property '#{name}'") && w.include?('never used') }
  end

  def not_defined(warnings, name)
    warnings.select { |w| w.include?("Binding variable '#{name}'") && w.include?('not defined') }
  end

  def label(text, names)
    { 'type' => 'View', 'id' => 'root', 'data' => names.map { |n| { 'name' => n, 'class' => 'String' } },
      'child' => [{ 'type' => 'Label', 'id' => 'l', 'text' => text }] }
  end

  it 'counts a reference inside mixed text as a use' do
    warnings = validator.validate(label('Hi @{who}', %w[who]), 'a.json')
    expect(never_used(warnings, 'who')).to be_empty, warnings.join("\n")
  end

  it 'counts every reference of one string, between and around text' do
    warnings = validator.validate(label('@{title}: @{count} items', %w[title count]), 'a.json')
    expect(never_used(warnings, 'title') + never_used(warnings, 'count')).to be_empty, warnings.join("\n")
  end

  it 'reads a string that starts and ends with a binding as mixed text, not as one expression' do
    warnings = validator.validate(label('@{first} and @{second}', %w[first second]), 'a.json')
    expect(warnings).to be_empty, warnings.join("\n")
    undeclared = validator.validate(label('@{first} and @{second}', %w[someone]), 'a.json')
    expect(%w[first and second].flat_map { |n| not_defined(undeclared, n) }).to be_empty, undeclared.join("\n")
  end

  it 'names a name data lacks in a whole binding, and not inside mixed text' do
    whole = validator.validate(label('@{nobody}', %w[someone]), 'a.json')
    expect(not_defined(whole, 'nobody').size).to eq(1), whole.join("\n")
    mixed = validator.validate(label('Hi @{nobody}', %w[someone]), 'a.json')
    expect(not_defined(mixed, 'nobody')).to be_empty, mixed.join("\n")
  end

  it 'still names a data property no string references (the check is not switched off)' do
    warnings = validator.validate(label('Hi @{who}', %w[who orphan]), 'a.json')
    expect(never_used(warnings, 'orphan').size).to eq(1), warnings.join("\n")
  end

  it 'leaves a Collection cell\'s text to the cell scope: a name there is the item\'s, not the screen\'s' do
    json = { 'type' => 'View', 'id' => 'root',
             'data' => [{ 'name' => 'items', 'class' => 'CollectionDataSource' }, { 'name' => 'rowTitle', 'class' => 'String' }],
             'child' => [{ 'type' => 'Collection', 'id' => 'c', 'items' => '@{items}',
                           'sections' => [{ 'cell' => { 'type' => 'Label', 'id' => 'cl', 'text' => 'No. @{rowTitle}' } }] }] }
    warnings = validator.validate(json, 'a.json')
    expect(never_used(warnings, 'rowTitle').size).to eq(1), warnings.join("\n")
  end
end
