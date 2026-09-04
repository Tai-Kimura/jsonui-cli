# frozen_string_literal: true

require 'swiftui/converter_factory'

# Third candidate for a BOUND `hidden`. The first two were measured wrong on
# the codegen conformance host and reverted:
#
#   fb68646f  `.accessibilityHidden` after the identifier  -> still visible
#   b35fc9aa  collapse with `children: .ignore`            -> still visible
#
# The static spelling has always worked by emitting NO identifier at all
# (`apply_accessibility_identifier` returns early), which is also what the
# dynamic face does — `applyAccessibilityId` returns early for visibility
# "invisible", with a comment saying an explicit accessibility container
# ignores an ancestor's `.accessibilityHidden`. Emitting no identifier is the
# one thing the working recipe does that neither failed candidate did.
#
# A flat modifier chain cannot skip a line conditionally, so the identifier
# carries the condition instead.
#
# ⚠️ KILL CONDITION, to be judged by the host and not by this file: if
# `common/hidden__binding_negation` reports the target NOT findable while its
# binding is false, this candidate is wrong and goes the way of the other two.
# That fixture is only observable because the codegen host now stages
# driver-free fixtures; before that, this could not have been judged at all.
RSpec.describe 'hidden binding identifier' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all)  { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(component)
    out = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert
    out.is_a?(Array) ? out.join("\n") : out.to_s
  end

  let(:bound) do
    { 'type' => 'View', 'id' => 'target', 'width' => 200, 'height' => 200,
      'hidden' => '@{boundHidden}',
      'child' => [{ 'type' => 'View', 'id' => 'box', 'width' => 40, 'height' => 40 }] }
  end

  it 'gives the identifier only while the binding says visible' do
    expect(emit(bound)).to include('.accessibilityIdentifier(data.boundHidden ? "" : "target")')
  end

  it 'keeps the declared id in the visible arm' do
    # The half that must NOT regress: hidden=false has to stay findable, which
    # is what `hidden__binding_negation` measures on the host.
    code = emit(bound)
    expect(code).to include('"target"')
  end

  it 'leaves a view with no hidden binding with a plain identifier' do
    code = emit(bound.reject { |k, _| k == 'hidden' })
    expect(code).to include('.accessibilityIdentifier("target")')
    expect(code).not_to include('? "" :')
  end

  it 'still emits no identifier at all for the static spelling' do
    # Unchanged by this commit, and the reason the static case never had the
    # defect. Scoped to the TARGET: the child `box` carries its own identifier,
    # so a bare "no identifier anywhere" assertion passes for the wrong reason
    # and fails for the wrong one too.
    code = emit(bound.merge('hidden' => true))
    expect(code).not_to include('.accessibilityIdentifier("target")')
    expect(code).to include('.accessibilityIdentifier("box")')
  end
end
