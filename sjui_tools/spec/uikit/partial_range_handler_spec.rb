# frozen_string_literal: true

require 'uikit/handlers/label_binding_handler'
require_relative '../support/swift_compiler'

# The UIKit codegen gives a partialAttributes range its closure by the rule
# every path reads (shared/core/tap_accessibility.rb `range_handler`), the one
# the UIKit label reads at run time (SwiftJsonUI PartialRangeHandler): onClick
# first, then onclick, its alias, each a binding or a method name. A binding
# gets `setPartialAttributeOnClick`; a name is the selector the label performs,
# so it gets none. From jsonui-cli 1.9.0 the normalizer folds onclick into
# onClick, so a name arrives in onClick.
RSpec.describe 'sjui UIKit partialAttributes range handler' do
  def emitted(range)
    content = []
    SjuiTools::UIKit::LabelBindingHandler.new(content, {}, {})
                                         .handle_specific_binding('label', 'partialAttributes', [range.merge('range' => [0, 5])])
    content.join
  end

  CLOSURE = 'label?.setPartialAttributeOnClick(at: 0, handler: onTerms)'

  {
    'onClick binding' => [{ 'onClick' => '@{onTerms}' }, true],
    'onclick holding a binding' => [{ 'onclick' => '@{onTerms}' }, true],
    'both: onClick wins' => [{ 'onClick' => '@{onTerms}', 'onclick' => 'onOther' }, true],
    'onClick holding a name (the alias folded): a selector' => [{ 'onClick' => 'onTerms' }, false],
    'onclick holding a name: a selector' => [{ 'onclick' => 'onTerms' }, false],
    'onClick neither a binding nor a name: the alias is read' => [{ 'onClick' => '@{onOther} now', 'onclick' => '@{onTerms}' }, true],
    'onClick blank: the alias is read' => [{ 'onClick' => '@{ }', 'onclick' => '@{onTerms}' }, true]
  }.each do |name, (range, closure)|
    it name do
      out = emitted(range)
      if closure
        expect(out).to include(CLOSURE)
        expect(out.scan('setPartialAttributeOnClick').size).to eq(1)
      else
        expect(out).not_to include('setPartialAttributeOnClick')
      end
    end
  end

  # The closure line against SJUILabel's signature (the label stubbed: the
  # spec runs without UIKit).
  it 'writes a closure line that compiles against setPartialAttributeOnClick' do
    out = emitted('onclick' => '@{onTerms}')
    expect(<<~SWIFT).to compile_as_swift
      final class UITapGestureRecognizer {}
      final class ProbeLabel {
          func setPartialAttributeOnClick(at index: Int, handler: ((UITapGestureRecognizer) -> Void)?) {}
      }
      final class ProbeBinding {
          var label: ProbeLabel? = ProbeLabel()
          var onTerms: ((UITapGestureRecognizer) -> Void)?
          func bindView() {
      #{out}
          }
      }
    SWIFT
  end
end
