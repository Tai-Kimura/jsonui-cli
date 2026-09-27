# frozen_string_literal: true

require_relative '../../lib/core/binding_validator'

# A data property named only through an attribute declared for OTHER
# platforms or modes is the layout's data all the same, and is not "defined
# but never used" here (jsonui-cli 1.9.0). Until then the validator skipped
# such an attribute whole, so a shared layout that binds Web.reloadToken /
# onLoadFailed (declared for swift and kotlin: an iframe reports neither)
# warned twice on every web build, and a layout binding View.onDrop
# (react only) warned on every iOS and Android build — with nothing the face
# could change. The attribute is still not checked on this platform (a name
# it binds that data does not declare is not reported here).
RSpec.describe RjuiTools::Core::BindingValidator, '(a platform-restricted attribute counts as a use)' do
  subject(:validator) { described_class.new }

  def never_used(warnings, name)
    warnings.select { |w| w.include?("Data property '#{name}'") && w.include?('never used') }
  end

  def layout(node, data)
    { 'type' => 'View', 'id' => 'root', 'data' => data, 'child' => [node] }
  end

  it 'counts Web.reloadToken / onLoadFailed (swift and kotlin only) as uses of their data' do
    json = layout({ 'type' => 'Web', 'id' => 'web_view', 'url' => '@{url}',
                    'reloadToken' => '@{reloadToken}', 'onLoadFailed' => '@{onLoadFailed}' },
                  [{ 'name' => 'url', 'class' => 'String' }, { 'name' => 'reloadToken', 'class' => 'Int' },
                   { 'name' => 'onLoadFailed', 'class' => '(() -> Void)?' }])
    warnings = validator.validate(json, 'web_view.json')
    expect(never_used(warnings, 'reloadToken') + never_used(warnings, 'onLoadFailed')).to be_empty, warnings.join("\n")
  end

  it 'counts a handler named without braces in common.onLongPress (swift and kotlin only)' do
    json = layout({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'onLongPress' => 'handleHold' },
                  [{ 'name' => 'handleHold', 'class' => '(() -> Void)?' }])
    expect(never_used(validator.validate(json, 'a.json'), 'handleHold')).to be_empty
  end

  it 'still names a data property nothing binds (the check is not switched off)' do
    json = layout({ 'type' => 'Label', 'id' => 'l', 'text' => '@{shown}' },
                  [{ 'name' => 'shown', 'class' => 'String' }, { 'name' => 'orphan', 'class' => 'String' }])
    warnings = validator.validate(json, 'a.json')
    expect(never_used(warnings, 'orphan').size).to eq(1)
    expect(never_used(warnings, 'shown')).to be_empty
  end

  it 'does not check the other platform\'s attribute here: a name data lacks is not reported' do
    json = layout({ 'type' => 'Web', 'id' => 'w', 'url' => '@{shown}', 'reloadToken' => '@{missingOnPurpose}' }, [{ 'name' => 'shown', 'class' => 'String' }])
    warnings = validator.validate(json, 'a.json')
    expect(warnings.grep(/'missingOnPurpose'/)).to be_empty, warnings.join("\n")
  end
end
