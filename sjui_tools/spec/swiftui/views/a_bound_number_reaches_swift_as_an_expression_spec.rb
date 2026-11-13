# frozen_string_literal: true

require 'json'
require 'swiftui/json_to_swiftui_converter'
require 'swiftui/views/base_view_converter'
require_relative '../../support/emitted_swift'

# A binding on an attribute a converter writes itself. Three converters pasted
# the value: `"alpha": "@{x}"` on a TextView emitted `.opacity(@{x})`, the build
# exited 0 with no warning, and Xcode stopped on the generated file. The others
# cast it: `"cornerRadius": "@{x}"` on a Button emitted `cornerRadius: 0` and
# compiled. The sweep is over the attribute table, so a new attribute or a new
# component is in it the day it is declared.
RSpec.describe 'a bound number reaches Swift as an expression' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  BOUND_NUMBER_ATTRIBUTE_TABLE = JSON.parse(File.read(File.expand_path('../../../../shared/core/attribute_definitions.json', __dir__)))
  BOUND = '@{v}'
  NOT_VALUES = %w[_comment $jui id type style include data child children binding bindingScript partial variables
                  shared_data sectionHeader cellClasses headerClasses footerClasses sections].freeze

  def emit(node, definitions = {})
    Thread.current[:sjui_data_definitions] = definitions
    SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_component(node, 0).to_s
  ensure
    Thread.current[:sjui_data_definitions] = nil
  end

  # `@{` outside a string literal and a comment: what Swift cannot read.
  def unreadable(code)
    code.lines.map(&:strip).reject { |line| line.start_with?('//') }
        .select { |line| line.gsub(/"(?:[^"\\]|\\.)*"/, '""').include?('@{') }
  end

  def self.cases
    common = BOUND_NUMBER_ATTRIBUTE_TABLE['common'].reject { |name, _| name.start_with?('_') }
    BOUND_NUMBER_ATTRIBUTE_TABLE.flat_map do |type, own|
      next [] if %w[_comment common].include?(type) || !own.is_a?(Hash)

      common.merge(own).flat_map do |attr, definition|
        next [] if NOT_VALUES.include?(attr) || !definition.is_a?(Hash) || attr.start_with?('_')

        values = [BOUND]
        values += [[BOUND, BOUND], [BOUND, BOUND, BOUND, BOUND]] if Array(definition['type']).flatten.include?('array')
        (definition['properties'] || {}).each_key { |prop| values << { prop => BOUND, 'color' => '#000000' } }
        values.map { |value| [type, attr, value] }
      end
    end
  end

  it 'never writes a binding where Swift reads code, on any declared attribute of any type' do
    allow(SjuiTools::Core::Logger).to receive(:warn)
    leaks = self.class.cases.flat_map do |type, attr, value|
      code = begin
        silence_stream { emit({ 'type' => type, 'id' => 'p', attr => value }) }
      rescue NoMethodError, TypeError
        '' # the converter refuses this shape outright; nothing reaches Swift
      end
      unreadable(code).map { |line| "#{type}.#{attr} #{value.inspect}: #{line}" }
    end
    expect(leaks).to eq([]), leaks.uniq.first(40).join("\n")
  end

  def silence_stream
    original = $stdout
    $stdout = File.open(File::NULL, 'w')
    yield
  ensure
    $stdout = original
  end

  DRAWS = {
    [{ 'type' => 'TextView', 'alpha' => BOUND }] => '.opacity(Double(data.v ?? 0))',
    [{ 'type' => 'TextField', 'alpha' => BOUND }] => '.opacity(Double(data.v ?? 0))',
    [{ 'type' => 'SelectBox', 'alpha' => BOUND }] => '.opacity(Double(data.v ?? 0))',
    [{ 'type' => 'Label', 'alpha' => BOUND }] => '.opacity(Double(data.v ?? 0))',
    [{ 'type' => 'Switch', 'alpha' => BOUND }] => '.opacity(Double(data.v ?? 0))',
    [{ 'type' => 'TextView', 'cornerRadius' => BOUND }] => 'cornerRadius: CGFloat(data.v ?? 0),',
    [{ 'type' => 'SelectBox', 'cornerRadius' => BOUND }] => 'cornerRadius: CGFloat(data.v ?? 0),',
    [{ 'type' => 'Button', 'cornerRadius' => BOUND }] => 'cornerRadius: CGFloat(data.v ?? 0),',
    [{ 'type' => 'Switch', 'cornerRadius' => BOUND }] => '.cornerRadius(CGFloat(data.v ?? 0))',
    [{ 'type' => 'Button', 'borderWidth' => BOUND }] => 'borderWidth: CGFloat(data.v ?? 0),',
    [{ 'type' => 'Button', 'fontSize' => BOUND }] => 'fontSize: CGFloat(data.v ?? 0),',
    [{ 'type' => 'TextView', 'maxHeight' => BOUND }] => 'maxHeight: CGFloat(data.v ?? 0),',
    [{ 'type' => 'TextView', 'minHeight' => BOUND }] => 'minHeight: CGFloat(data.v ?? 0),',
    [{ 'type' => 'TextView', 'flexible' => true, 'maxHeight' => BOUND }] => '.frame(maxHeight: CGFloat(data.v ?? 0))',
    [{ 'type' => 'TextView', 'containerInset' => BOUND }] => 'containerInset: EdgeInsets(top: CGFloat(data.v ?? 0)',
    [{ 'type' => 'TextView', 'padding' => BOUND }] => 'containerInset: EdgeInsets(top: CGFloat(data.v ?? 0)',
    [{ 'type' => 'TextView', 'hintFontSize' => BOUND }] => 'hintFontSize: CGFloat(data.v ?? 0),',
    # the sides it does not name keep SelectBoxView's default (0 / 12; ruling 2026-11-13)
    [{ 'type' => 'SelectBox', 'paddingTop' => BOUND }] => 'padding: EdgeInsets(top: CGFloat(data.v ?? 0), leading: 12',
    [{ 'type' => 'SelectBox', 'paddings' => [BOUND, 2] }] => 'padding: EdgeInsets(top: CGFloat(data.v ?? 0), leading: 2',
    [{ 'type' => 'SelectBox', 'fontSize' => BOUND }] => 'fontSize: CGFloat(data.v ?? 0),',
    [{ 'type' => 'SelectBox', 'caretAttributes' => { 'width' => BOUND } }] => 'CaretAttributes(width: CGFloat(data.v ?? 0))',
    [{ 'type' => 'TextField', 'fieldPadding' => BOUND }] => '.padding(CGFloat(data.v ?? 0))',
    [{ 'type' => 'TextField', 'textPaddingLeft' => BOUND }] => '.padding(.leading, CGFloat(data.v ?? 0))',
    [{ 'type' => 'View', 'tag' => BOUND }] => '.tag(data.v)',
    [{ 'type' => 'View', 'margins' => BOUND }] => '.padding(.all, CGFloat(data.v ?? 0))',
    [{ 'type' => 'View', 'margins' => [BOUND, 2] }] => '.padding(.vertical, CGFloat(data.v ?? 0))',
    [{ 'type' => 'Label', 'edgeInset' => BOUND }] => '.padding(CGFloat(data.v ?? 0))',
    [{ 'type' => 'Label', 'shadow' => { 'radius' => BOUND } }] => '.shadow(radius: CGFloat(data.v ?? 0), x: 0, y: 0)',
    [{ 'type' => 'Label', 'shadow' => { 'offsetX' => BOUND } }] => '.shadow(radius: 5, x: CGFloat(data.v ?? 0), y: 0)',
    [{ 'type' => 'Label', 'shadow' => { 'offsetY' => BOUND } }] => '.shadow(radius: 5, x: 0, y: CGFloat(data.v ?? 0))',
    [{ 'type' => 'Label', 'shadow' => { 'color' => '#000000', 'opacity' => BOUND } }] => '.opacity(Double(data.v ?? 0)), radius: 5',
    [{ 'type' => 'Label', 'textShadow' => { 'color' => '#000000', 'blur' => BOUND } }] => 'radius: CGFloat(data.v ?? 0), x: 0, y: 1)',
    [{ 'type' => 'Image', 'maxZoom' => BOUND }] => 'CGFloat(data.v ?? 0))',
    [{ 'type' => 'IconLabel', 'iconSize' => BOUND }] => 'iconSize: CGFloat(data.v ?? 0)',
    [{ 'type' => 'CheckBox', 'iconSize' => BOUND }] => 'iconSize: CGFloat(data.v ?? 0),',
    [{ 'type' => 'View', 'borderColor' => '#000000', 'borderWidth' => 1, 'cornerRadius' => BOUND }] => 'RoundedRectangle(cornerRadius: CGFloat(data.v ?? 0))',
    [{ 'type' => 'IconLabel', 'textShadow' => { 'color' => '#000000', 'blur' => BOUND } }] => 'radius: CGFloat(data.v ?? 0), x: 0, y: 1)',
    [{ 'type' => 'IconLabel', 'textShadow' => { 'color' => '#000000', 'offset' => [BOUND, 2] } }] => 'radius: 1, x: CGFloat(data.v ?? 0), y: 2)',
    [{ 'type' => 'Label', 'textShadow' => { 'color' => '#000000', 'offset' => [BOUND, 2] } }] => 'radius: 1, x: CGFloat(data.v ?? 0), y: 2)',
    [{ 'type' => 'Label', 'edgeInset' => [BOUND] }] => '.padding(CGFloat(data.v ?? 0))',
    [{ 'type' => 'Label', 'edgeInset' => [BOUND, 2] }] => '.padding(.vertical, CGFloat(data.v ?? 0))',
    [{ 'type' => 'Label', 'edgeInset' => [BOUND, 2, 3] }] => '.padding(.top, CGFloat(data.v ?? 0))',
    [{ 'type' => 'Label', 'edgeInset' => [BOUND, 2, 3, 4] }] => '.padding(EdgeInsets(top: CGFloat(data.v ?? 0)',
    [{ 'type' => 'View', 'margins' => [BOUND] }] => '.padding(.all, CGFloat(data.v ?? 0))',
    [{ 'type' => 'View', 'margins' => [BOUND, 2, 3, 4] }] => '.padding(.top, CGFloat(data.v ?? 0))',
    [{ 'type' => 'View', 'insets' => BOUND }] => '.padding(CGFloat(data.v ?? 0))',
    [{ 'type' => 'View', 'insets' => [BOUND] }] => '.padding(CGFloat(data.v ?? 0))',
    [{ 'type' => 'View', 'insets' => [BOUND, 2] }] => '.padding(.vertical, CGFloat(data.v ?? 0))',
    [{ 'type' => 'View', 'insets' => [BOUND, 2, 3, 4] }] => '.padding(.top, CGFloat(data.v ?? 0))',
    [{ 'type' => 'TextView', 'hintAttributes' => { 'fontColor' => '#000000' }, 'hintFontSize' => BOUND }] => 'hintFontSize: CGFloat(data.v ?? 0),',
    [{ 'type' => 'TextView', 'hintAttributes' => { 'fontColor' => '#000000' }, 'hintLineHeightMultiple' => BOUND }] => 'hintLineHeightMultiple: CGFloat(data.v ?? 0),',
    [{ 'type' => 'TextView', 'flexible' => true, 'minHeight' => 40, 'maxHeight' => BOUND }] => '.frame(minHeight: 40, maxHeight: CGFloat(data.v ?? 0))',
    [{ 'type' => 'Collection', 'containerInset' => BOUND }] => '.contentMargins(.all, CGFloat(data.v ?? 0), for: .scrollContent)'
  }.freeze

  DRAWS.each do |(node), line|
    it "#{node.reject { |k, _| k == 'type' }.to_json} on #{node['type']} draws #{line}" do
      expect(silence_stream { emit({ 'id' => 'p' }.merge(node)) }).to include(line)
    end
  end

  # A written value keeps the bytes it always had.
  WRITTEN = {
    [{ 'type' => 'TextView', 'alpha' => 0.5 }] => '.opacity(0.5)',
    [{ 'type' => 'Label', 'alpha' => 0.5 }] => '.opacity(0.5)',
    [{ 'type' => 'Switch', 'alpha' => 0.5 }] => '.opacity(0.5)',
    [{ 'type' => 'TextView', 'cornerRadius' => 7 }] => 'cornerRadius: 7,',
    [{ 'type' => 'Button', 'cornerRadius' => 7 }] => 'cornerRadius: 7,',
    [{ 'type' => 'Switch', 'cornerRadius' => 7 }] => '.cornerRadius(7)',
    [{ 'type' => 'View', 'tag' => 3 }] => '.tag(3)',
    [{ 'type' => 'View', 'margins' => [1, 2] }] => '.padding(.vertical, 1)',
    [{ 'type' => 'Label', 'shadow' => { 'radius' => 3, 'offsetX' => 1, 'offsetY' => 2 } }] => '.shadow(radius: 3, x: 1, y: 2)',
    [{ 'type' => 'Label', 'shadow' => { 'color' => '#000000', 'opacity' => 0.4 } }] => '.opacity(0.4), radius: 5, x: 0, y: 0)',
    [{ 'type' => 'SelectBox', 'paddings' => [1, 2] }] => 'padding: EdgeInsets(top: 1, leading: 2, bottom: 1, trailing: 2)',
    [{ 'type' => 'TextView', 'containerInset' => 4 }] => 'containerInset: EdgeInsets(top: 4, leading: 4, bottom: 4, trailing: 4)'
  }.freeze

  WRITTEN.each do |(node), line|
    it "a written #{node.reject { |k, _| k == 'type' }.to_json} on #{node['type']} stays #{line}" do
      expect(silence_stream { emit({ 'id' => 'p' }.merge(node)) }).to include(line)
    end
  end

  # What names something at generation time cannot take a binding: it is said,
  # and the attribute reads as absent.
  NAMES = {
    { 'type' => 'TextField', 'nextFocus' => BOUND } => 'nextFocus',
    { 'type' => 'Radio', 'group' => BOUND } => 'group',
    { 'type' => 'Embed', 'screen' => BOUND } => 'screen'
  }.freeze

  NAMES.each do |node, attribute|
    it "says #{attribute} on #{node['type']} does not take a binding, and pastes it nowhere" do
      expect(SjuiTools::Core::Logger).to receive(:warn).with(/'#{attribute}' .*does not take a binding/).at_least(:once)
      expect(silence_stream { emit({ 'id' => 'p' }.merge(node)) }).not_to include('@{')
    end
  end

  it 'keeps a bound group out of the name of the selection variable' do
    allow(SjuiTools::Core::Logger).to receive(:warn)
    tree = { 'type' => 'View', 'child' => [{ 'type' => 'Radio', 'group' => BOUND }] }
    expect(SjuiTools::SwiftUI::Views::RadioConverter.scan_groups(tree).keys.join).not_to include('@{')
  end

  it 'writes a selector name given as a binding as the name' do
    code = silence_stream { emit({ 'type' => 'Button', 'id' => 'p', 'text' => 'x', 'onclick' => BOUND }) }
    expect(code).to include('data.v?()')
  end

  # Declared Int, CGFloat, Double, optional or a String: the slot compiles.
  DECLARED = {
    'Int' => ['var v: Int = 1', { 'class' => 'Int', 'defaultValue' => 1 }],
    'CGFloat' => ['var v: CGFloat = 1', { 'class' => 'CGFloat', 'defaultValue' => 1 }],
    'Double' => ['var v: Double = 1', { 'class' => 'Double', 'defaultValue' => 1 }],
    'Int?' => ['var v: Int? = nil', { 'class' => 'Int' }],
    'Double?' => ['var v: Double? = nil', { 'class' => 'Double' }],
    'String' => ['var v: String = "1"', { 'class' => 'String', 'defaultValue' => '1' }]
  }.freeze

  DECLARED.each do |name, (property, definition)|
    it "compiles the modifiers it writes with the property declared #{name}" do
      nodes = [
        { 'type' => 'Switch', 'id' => 'a', 'alpha' => BOUND, 'cornerRadius' => BOUND, 'margins' => BOUND },
        { 'type' => 'Label', 'id' => 'b', 'alpha' => BOUND, 'shadow' => { 'radius' => BOUND, 'offsetX' => BOUND, 'offsetY' => BOUND } },
        { 'type' => 'Label', 'id' => 'c', 'shadow' => { 'color' => '#000000', 'opacity' => BOUND } }
      ]
      lines = nodes.flat_map { |node| silence_stream { emit(node, 'v' => definition) }.lines.map(&:strip) }
      chain = lines.select { |line| line.match?(/\A\.(opacity|shadow|cornerRadius|padding)\(/) }
      expect(chain.size).to be >= 6
      fragment = "Color.clear\n#{chain.join("\n")}"
      expect(compilable_view(fragment, data: [property])).to compile_as_swift
    end
  end
end
