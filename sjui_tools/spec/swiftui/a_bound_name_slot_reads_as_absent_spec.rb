# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'stringio'
require 'swiftui/json_to_swiftui_converter'
require 'swiftui/data_model_updater'
require_relative '../support/emitted_swift'

# An attribute that names something the generator has to know has no value yet
# when it is a binding. iOS answered four ways: `targetId: "@{v}"` for a view,
# `var selected@{v}` in the Data, `navigationMode: .@{v}`, and for a ScrollView's
# anchor an exception that stopped the whole build. Every face now reads it as
# absent and says so once (LayoutValidator.drop_name_slot_bindings!), on the tree
# the conversion draws: styles merged, includes expanded.
RSpec.describe 'a bound name slot on the iOS build path' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }
  before { allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data } }

  def size
    { 'width' => 'matchParent', 'height' => 40 }
  end

  def built(*nodes)
    Dir.mktmpdir('sjui_name_slot') do |dir|
      path = File.join(dir, 'probe.json')
      File.write(path, JSON.generate(
                         'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
                         'child' => [{ 'data' => [{ 'name' => 'v', 'class' => 'String', 'defaultValue' => '' }] }, *nodes]
                       ))
      err = StringIO.new
      orig = $stderr
      $stderr = err
      begin
        swift = SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path)
        swift = Array(swift).join("\n")
      ensure
        $stderr = orig
      end
      yield swift, err.string
    end
  end

  %w[alignTopOfView alignBottomOfView alignLeftOfView alignRightOfView alignTopView alignBottomView
     alignLeftView alignRightView alignCenterHorizontalView alignCenterVerticalView].each do |slot|
    it "#{slot}: no constraint on the binding, and a warning" do
      built({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', slot => '@{v}' }.merge(size)) do |swift, err|
        expect(swift).not_to be_empty
        expect(swift).not_to include('@{v}')
        expect(err).to include("'#{slot}' names a view and does not take a binding (@{v}); ignored.")
      end
    end
  end

  it 'a written view name is still the target' do
    built({ 'type' => 'Label', 'id' => 'anchor', 'text' => 'a' }.merge(size),
          { 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'alignBottomOfView' => 'anchor' }.merge(size)) do |swift, err|
      expect(swift).to include('targetId: "anchor"')
      expect(err).not_to include('does not take')
    end
  end

  it 'ScrollView.defaultScrollAnchor: the build goes on, with no anchor' do
    node = { 'type' => 'ScrollView', 'id' => 's', 'defaultScrollAnchor' => '@{v}', 'child' => [] }.merge(size)
    built(node) do |swift, err|
      expect(swift).not_to include('.defaultScrollAnchor')
      expect(err).to include("'defaultScrollAnchor' names an anchor")
    end
  end

  it 'the ScrollView converter itself takes a bound anchor for absent, with no exception' do
    node = { 'type' => 'ScrollView', 'id' => 's', 'defaultScrollAnchor' => '@{v}', 'child' => [] }.merge(size)
    code = SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_component(node, 0)
    expect(code).not_to include('.defaultScrollAnchor')
  end

  it 'a written anchor is still written' do
    node = { 'type' => 'ScrollView', 'id' => 's', 'defaultScrollAnchor' => 'bottom', 'child' => [] }.merge(size)
    built(node) { |swift, _| expect(swift).to include('.defaultScrollAnchor(.bottom)') }
  end

  it 'Embed.screen: a view is still written, for the modifiers that follow it' do
    built({ 'type' => 'Embed', 'id' => 'e', 'screen' => '@{v}' }.merge(size)) do |swift, err|
      expect(swift).to include('EmptyView()')
      expect(swift).not_to include('@{v}')
      expect(err.scan("'screen' names a screen").size).to eq(1)
    end
  end

  it 'what an Embed without a screen writes type-checks with the modifiers after it', :swift_compile do
    emitted = SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_component(
      { 'type' => 'Embed', 'id' => 'e', 'screen' => '@{v}' }.merge(size), 0
    )
    expect(emitted).to include('.accessibilityIdentifier')
    expect(<<~SWIFT).to compile_as_swift
      import SwiftUI
      struct Probe: View {
        var body: some View {
          #{emitted}
        }
      }
    SWIFT
  end

  it 'the Data property for a bound group type-checks', :swift_compile do
    props = SjuiTools::SwiftUI::DataModelUpdater.allocate.send(
      :extract_data_properties, { 'type' => 'Radio', 'id' => 'r', 'group' => '@{v}' }, [], {}
    )
    expect("struct Data { #{props.map { |p| "var #{p['name']}: String = \"\"" }.join('; ')} }").to compile_as_swift
  end

  it 'an override in `responsive` is taken off too' do
    node = { 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'responsive' => { 'compact' => { 'alignTopOfView' => '@{v}' } } }.merge(size)
    built(node) do |swift, err|
      expect(swift).not_to include('@{v}')
      expect(err).to include("'alignTopOfView' names a view")
    end
  end

  it 'Embed.navigationMode: no member named after the binding' do
    node = { 'type' => 'Embed', 'id' => 'e', 'screen' => 'other', 'navigationMode' => '@{v}' }.merge(size)
    built(node) do |swift, err|
      expect(swift).not_to include('.@{v}')
      expect(err).to include("'navigationMode' names a mode")
    end
  end

  it 'Collection.defaultScrollAnchor is the same rule' do
    node = { 'type' => 'Collection', 'id' => 'c', 'defaultScrollAnchor' => '@{v}', 'cellClasses' => ['Cell'], 'items' => '@{v}' }.merge(size)
    built(node) { |_, err| expect(err).to include("'defaultScrollAnchor' names an anchor") }
  end

  it 'an alias of the type is the same rule' do
    built({ 'type' => 'Scroll', 'id' => 's', 'defaultScrollAnchor' => '@{v}', 'child' => [] }.merge(size)) do |_, err|
      expect(err).to include("'defaultScrollAnchor' names an anchor")
    end
  end

  it 'the attribute elsewhere is not touched: a custom type keeps its own `group`' do
    tree = { 'type' => 'MyChip', 'id' => 'c', 'group' => '@{v}' }
    warnings = JsonUIShared::LayoutValidator.drop_name_slot_bindings!(tree, source_path: 'x')
    expect(warnings).to be_empty
    expect(tree['group']).to eq('@{v}')
  end

  it 'a slot inside an included layout is taken off the expanded tree' do
    Dir.mktmpdir('sjui_name_slot') do |dir|
      File.write(File.join(dir, 'part.json'), JSON.generate(
                                                'type' => 'View', 'id' => 'p', 'partial' => true,
                                                'child' => [{ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'alignTopOfView' => '@{v}' }.merge(size)]
                                              ))
      path = File.join(dir, 'probe.json')
      File.write(path, JSON.generate('type' => 'View', 'id' => 'root', 'child' => [{ 'include' => 'part' }]))
      err = StringIO.new
      orig = $stderr
      $stderr = err
      begin
        swift = Array(SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path)).join("\n")
      ensure
        $stderr = orig
      end
      expect(swift).not_to include('@{v}')
      expect(err.string).to include("'alignTopOfView' names a view")
    end
  end

  it 'convert_file is the same rule (the `sjui convert` path)' do
    Dir.mktmpdir('sjui_name_slot') do |dir|
      path = File.join(dir, 'probe.json')
      out = File.join(dir, 'Out.swift')
      File.write(path, JSON.generate('type' => 'View', 'id' => 'root', 'child' => [
                                       { 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'alignTopOfView' => '@{v}' }.merge(size)
                                     ]))
      err = StringIO.new
      orig = $stderr
      $stderr = err
      begin
        SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_file(path, out)
      ensure
        $stderr = orig
      end
      expect(err.string).to include("'alignTopOfView' names a view")
      expect(File.read(out)).not_to include('@{v}')
    end
  end

  it 'Radio.group: reads as no group, and the Data does not declare the binding' do
    built({ 'type' => 'Radio', 'id' => 'r', 'text' => 'x', 'group' => '@{v}' }.merge(size)) do |bound, err|
      expect(err.scan("'group' names a radio group").size).to eq(1)
      built({ 'type' => 'Radio', 'id' => 'r', 'text' => 'x' }.merge(size)) { |absent, _| expect(bound).to eq(absent) }
    end
    props = SjuiTools::SwiftUI::DataModelUpdater.allocate.send(
      :extract_data_properties, { 'type' => 'Radio', 'id' => 'r', 'group' => '@{v}' }, [], {}
    )
    expect(props.map { |p| p['name'] }).to eq(['selectedRadiogroup'])
  end
end
