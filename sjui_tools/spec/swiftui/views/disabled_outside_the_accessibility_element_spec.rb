# frozen_string_literal: true

require 'swiftui/converter_factory'

# `.disabled` has to be applied OUTSIDE the accessibility element, not only
# inside it.
#
# `apply_accessibility_identifier` forms the container's accessibility element
# after the modifier bag has emitted `.disabled(...)`. An element created
# outside the disabled environment never receives the notEnabled trait, so
# XCUITest reads the view as enabled while it really is disabled — the view
# does not respond to touches, and the test that checks for that reports the
# opposite.
#
# The dynamic face reached this conclusion first, on this same fixture:
# `DynamicModifierHelper.standardOrder` carries a second
# `Stage("disabledOuter")` after `Stage("accessibilityId")`, annotated
# "measured: the View-hosted enabled__false conformance fixture". This gate
# keeps the static face's emission mirroring that stage.
#
# The assertion is about ORDER, not presence: `.disabled(true)` was already
# emitted before this change, and the fixture still failed. A test that only
# asked "is it emitted" would have been green throughout.
RSpec.describe 'disabled outside the accessibility element' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all)  { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(component)
    out = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert
    out.is_a?(Array) ? out.join("\n") : out.to_s
  end

  def positions(code, needle)
    code.each_line.each_with_index.select { |l, _| l.include?(needle) }.map(&:last)
  end

  let(:disabled_view) do
    { 'type' => 'View', 'id' => 'target', 'width' => 200, 'height' => 200,
      'enabled' => false,
      'child' => [{ 'type' => 'View', 'id' => 'box', 'width' => 40, 'height' => 40 }] }
  end

  it 'emits .disabled after the accessibility identifier' do
    code = emit(disabled_view)
    id_line = positions(code, '.accessibilityIdentifier("target")').last
    after = positions(code, '.disabled(').select { |n| n > id_line }
    expect(after).not_to be_empty,
                         "no .disabled after .accessibilityIdentifier:\n#{code}"
  end

  it 'keeps the inner one too, so the subtree stays disabled' do
    code = emit(disabled_view)
    id_line = positions(code, '.accessibilityIdentifier("target")').last
    before = positions(code, '.disabled(').select { |n| n < id_line }
    expect(before).not_to be_empty, "the inner .disabled disappeared:\n#{code}"
  end

  it 'emits nothing extra for an enabled view' do
    # Control: the outer application is conditional on the bag holding a
    # disabled entry, not unconditional.
    code = emit(disabled_view.merge('enabled' => true).tap { |c| c.delete('enabled') })
    expect(code).not_to include('.disabled(')
  end

  it 'covers the bound spelling as well' do
    code = emit(disabled_view.merge('enabled' => '@{isOn}'))
    id_line = positions(code, '.accessibilityIdentifier("target")').last
    after = positions(code, '.disabled(').select { |n| n > id_line }
    expect(after).not_to be_empty, "bound enabled lost its outer .disabled:\n#{code}"
  end
end
