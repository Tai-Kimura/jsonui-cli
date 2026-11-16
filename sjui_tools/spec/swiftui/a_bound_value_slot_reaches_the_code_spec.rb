# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'stringio'
require 'swiftui/json_to_swiftui_converter'
require 'swiftui/data_model_updater'
require_relative '../support/emitted_swift'

# A value the view takes as a String — an image's name, a font, a weight — was
# pasted between quotes when it was a binding: `icon: "@{v}"` asked for an asset
# named "@{v}", `fontWeight: "@{v}"` for a weight of that name. The build went on
# and drew the default. A binding is now the data's value (`(data.v)`), resolved
# at run time as Android and the web already did; a written value is written as
# it was.
RSpec.describe 'a bound value slot on the iOS build path' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }
  before { allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data } }

  def size
    { 'width' => 'matchParent', 'height' => 40 }
  end

  def built(node)
    Dir.mktmpdir('sjui_value_slot') do |dir|
      path = File.join(dir, 'probe.json')
      File.write(path, JSON.generate(
                         'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
                         'child' => [{ 'data' => [{ 'name' => 'v', 'class' => 'String', 'defaultValue' => '' }] },
                                     node.merge(size)]
                       ))
      err = StringIO.new
      orig = $stderr
      $stderr = err
      begin
        swift = Array(SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path)).join("\n")
      ensure
        $stderr = orig
      end
      yield swift
    end
  end

  def code_lines(swift)
    swift.lines.reject { |l| l.strip.start_with?('//') }.join
  end

  # [node without the slot, slot, the line it reaches when bound, the line when written 'w_name']
  BOUND_NAME_CASES = [
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'hint', 'placeholder: (data.v)', 'placeholder: "w_name"'],
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'placeholder', 'placeholder: (data.v)', 'placeholder: "w_name"'],
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'defaultImage', 'defaultImage: (data.v)', 'defaultImage: "w_name"'],
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'loadingImage', 'loadingImage: (data.v)', 'loadingImage: "w_name"'],
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'errorImage', 'errorImage: (data.v)', 'errorImage: "w_name"'],
    [{ 'type' => 'Image', 'id' => 'i' }, 'defaultImage', 'Image((data.v))', 'Image("w_name")'],
    [{ 'type' => 'Image', 'id' => 'i' }, 'errorImage', 'Image((data.v))', 'Image("w_name")'],
    [{ 'type' => 'Image', 'id' => 'i' }, 'loadingImage', 'Image((data.v))', 'Image("w_name")'],
    [{ 'type' => 'IconLabel', 'id' => 'il', 'text' => 'x' }, 'icon_on', 'iconOn: (data.v)', 'iconOn: "w_name"'],
    [{ 'type' => 'IconLabel', 'id' => 'il', 'text' => 'x' }, 'icon_off', 'iconOff: (data.v)', 'iconOff: "w_name"'],
    [{ 'type' => 'IconLabel', 'id' => 'il', 'text' => 'x' }, 'font', 'fontName: (data.v)', 'fontName: "w_name"'],
    [{ 'type' => 'CheckBox', 'id' => 'c', 'text' => 'x' }, 'icon', 'icon: (data.v)', 'icon: "w_name"'],
    [{ 'type' => 'CheckBox', 'id' => 'c', 'text' => 'x' }, 'src', 'icon: (data.v)', 'icon: "w_name"'],
    [{ 'type' => 'CheckBox', 'id' => 'c', 'text' => 'x' }, 'selectedIcon', 'selectedIcon: (data.v)', 'selectedIcon: "w_name"'],
    [{ 'type' => 'Radio', 'id' => 'r', 'text' => 'x', 'group' => 'g' }, 'icon', ': (data.v))', ': "w_name")'],
    [{ 'type' => 'Radio', 'id' => 'r', 'text' => 'x', 'group' => 'g' }, 'selectedIcon', '? (data.v) :', '? "w_name" :'],
    [{ 'type' => 'TextField', 'id' => 't', 'text' => '@{v}', 'hint' => 'h' }, 'hintFont', 'hintFont: (data.v)', 'hintFont: "w_name"'],
    [{ 'type' => 'TextView', 'id' => 't', 'text' => '@{v}', 'hint' => 'h' }, 'hintFont', 'hintFont: (data.v)', 'hintFont: "w_name"']
  ].freeze

  BOUND_NAME_CASES.each do |node, slot, bound_line, written_line|
    it "#{node['type']}.#{slot}: a binding is the data's value" do
      built(node.merge(slot => '@{v}')) do |swift|
        expect(code_lines(swift)).not_to include('@{v}')
        expect(swift).to include(bound_line)
      end
    end

    it "#{node['type']}.#{slot}: a written name is the literal it was" do
      built(node.merge(slot => 'w_name')) { |swift| expect(swift).to include(written_line) }
    end
  end

  it 'Label.fontWeight: a binding is resolved from the weight vocabulary at run time' do
    built({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'fontWeight' => '@{v}' }) do |swift|
      expect(code_lines(swift)).not_to include('@{v}')
      expect(swift).to match(/fontWeight: \(\[.*"bold": \.bold.*\]\[\(data\.v\)\.lowercased\(\)\] \?\? \.regular\)/)
    end
  end

  # The bound weight is a Font.Weight and a bound name a String, as the
  # initializers take them.
  it 'the bound weight and the bound name type-check', :swift_compile do
    built({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'fontWeight' => '@{v}' }) do |swift|
      weight = swift[/fontWeight: (.*),$/, 1]
      expect(weight).to include('(data.v).lowercased()')
      expect(<<~SWIFT).to compile_as_swift
        import SwiftUI
        struct D { var v: String = "" }
        let data = D()
        let weight: Font.Weight = #{weight}
        let name: String = (data.v)
      SWIFT
    end
  end

  it 'Label.fontWeight: a written weight keeps the String initializer' do
    built({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'fontWeight' => 'bold' }) do |swift|
      expect(swift).to include('fontWeight: "bold",')
    end
  end

  it 'Label.fontWeight: a bound weight with partialAttributes is a Font.Weight too' do
    node = { 'type' => 'Label', 'id' => 'l', 'text' => 'ab', 'fontWeight' => '@{v}',
             'partialAttributes' => [{ 'range' => [0, 1], 'fontWeight' => '@{v}' }] }
    built(node) do |swift|
      expect(code_lines(swift)).not_to include('@{v}')
      expect(swift.scan('[(data.v).lowercased()]').size).to be >= 2
    end
  end
end
