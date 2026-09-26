# frozen_string_literal: true

require 'core/attribute_validator'
require 'swiftui/json_to_swiftui_converter'
require 'core/stage_failures'

# A layout written inline where the declaration takes a layout's name — a
# tab's `child` (a tab names its layout with `view`), a section's header /
# cell / footer as a node — is declared nowhere and drawn by no path (sjui,
# kjui, rjui, both Dynamic runtimes read names; 4f's ruling, 1.9.0). The
# shared validator names it once, in one sentence; sjui's build raised on an
# inline cell (extract_view_name on a Hash with no className) and goes on
# without it now.
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

  it 'sjui: the build goes on, and draws the named cell only' do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
    dir = Dir.mktmpdir('inline_layout')
    path = File.join(dir, 'probe.json')
    File.write(path, JSON.generate('type' => 'View', 'child' => [
      { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'cellIdProperty' => 'id',
        'sections' => [{ 'cell' => { 'type' => 'Label', 'text' => 'INLINE_CELL_MARK' } }, { 'cell' => 'row_cell' }] }
    ]))
    result = nil
    expect { result = SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path) }.not_to raise_error
    expect(result.first.to_s).not_to include('INLINE_CELL_MARK')
    expect(result.first.to_s).to include('RowCell')
  ensure
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    FileUtils.rm_rf(dir) if dir
  end
end
