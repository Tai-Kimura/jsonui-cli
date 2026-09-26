# frozen_string_literal: true

require 'core/attribute_validator'

# A layout written inline where the declaration takes a layout's name — a
# tab's `child` (a tab names its layout with `view`), a section's header /
# cell / footer as a node — is declared nowhere and drawn by no path (sjui,
# kjui, rjui, both Dynamic runtimes read names; 4f's ruling, 1.9.0). The
# shared validator names it once, in one sentence. sjui's build going on
# without an inline cell: collection_converter_spec (extract_view_name).
RSpec.describe 'an inline layout: named, not drawn' do
  let(:validator) { SjuiTools::Core::AttributeValidator.new(:swiftui) }

  def named(component)
    validator.validate(component).select { |m| m.include?('inline layout') }
  end

  it 'names a tab with a child, once' do
    tab = { 'type' => 'TabView', 'width' => 'matchParent', 'height' => 100,
            'tabs' => [{ 'title' => 'T1', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] }, { 'title' => 'T2', 'view' => 't2' }] }
    expect(named(tab)).to eq(["[TabView] 'tabs[0].child' is an inline layout, which is not declared and is not drawn — name a layout file instead"])
  end

  it 'names a section node, once each, and not a named cell' do
    list = { 'type' => 'Collection', 'width' => 'matchParent', 'height' => 100, 'items' => '@{rows}', 'cellIdProperty' => 'id',
             'sections' => [{ 'cell' => { 'type' => 'Label', 'text' => 'x' } }, { 'cell' => 'row_cell', 'header' => { 'type' => 'View' } }] }
    expect(named(list).size).to eq(2)
    expect(named(list).join).to include("'sections[0].cell'").and include("'sections[1].header'")
    expect(validator.validate(list).grep(/expects string, got object/)).to be_empty
  end

  it 'says nothing for names' do
    expect(named({ 'type' => 'Collection', 'items' => '@{rows}', 'sections' => [{ 'cell' => 'row_cell' }] })).to be_empty
    expect(named({ 'type' => 'TabView', 'tabs' => [{ 'title' => 'a', 'view' => 'a_tab' }] })).to be_empty
  end
end
