# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/switch_converter'
require 'react/converters/toggle_converter'
require 'react/converters/slider_converter'
require 'react/converters/progress_converter'
require 'react/converters/radio_converter'
require 'react/converters/segment_converter'
require 'react/converters/select_box_converter'
require 'react/converters/text_field_converter'
require 'react/converters/collection_converter'
require 'react/data_model_generator'
require 'react/converters/view_converter'

# `bind` is the alternative spelling for a component's primary value binding.
# It is honoured by eight Compose components and by the iOS checkbox/text-field
# paths; web read it nowhere, so a layout written with `bind` rendered an
# unbound control on the web and nothing said so.
RSpec.describe 'bind as the primary value binding' do
  let(:config) { { 'use_tailwind' => true, 'typescript' => true } }

  def convert(klass, json)
    klass.new(json, config).convert(2)
  end

  {
    'Switch' => [RjuiTools::React::Converters::SwitchConverter, {}],
    'Toggle' => [RjuiTools::React::Converters::ToggleConverter, {}],
    'Slider' => [RjuiTools::React::Converters::SliderConverter, {}],
    'Radio' => [RjuiTools::React::Converters::RadioConverter, { 'items' => %w[a b] }],
    'Segment' => [RjuiTools::React::Converters::SegmentConverter, { 'items' => %w[a b] }],
    'SelectBox' => [RjuiTools::React::Converters::SelectBoxConverter, { 'items' => %w[a b] }],
    'TextField' => [RjuiTools::React::Converters::TextFieldConverter, {}]
  }.each do |name, (klass, extra)|
    it "wires bind to the value on #{name}" do
      result = convert(klass, { 'class' => name, 'bind' => '@{bound}' }.merge(extra))
      expect(result).to include('data.bound')
    end
  end

  it 'wires bind to the item source on Collection' do
    result = convert(
      RjuiTools::React::Converters::CollectionConverter,
      { 'class' => 'Collection', 'bind' => '@{rows}', 'sections' => [{ 'cell' => 'RowCell' }] }
    )
    expect(result).to include('data.rows')
  end

  # The component's own value attribute is the primary spelling; `bind` is only
  # the fallback, so a layout that sets both keeps behaving as it did.
  it 'yields to an explicit value attribute' do
    result = convert(
      RjuiTools::React::Converters::SwitchConverter,
      { 'class' => 'Switch', 'isOn' => '@{explicit}', 'bind' => '@{ignored}' }
    )
    expect(result).to include('data.explicit')
    expect(result).not_to include('data.ignored')
  end

  # `isOn: false` is a value, not an absence — the chains treat it as falsy and
  # always have, so the fallback must not start firing for it.
  it 'keeps the existing truthiness of the value chains' do
    result = convert(
      RjuiTools::React::Converters::SwitchConverter,
      { 'class' => 'Switch', 'isOn' => false, 'bind' => '@{fallback}' }
    )
    expect(result).to include('data.fallback')
  end

  it 'emits nothing extra when bind is absent' do
    with_bind = convert(RjuiTools::React::Converters::SliderConverter,
                        { 'class' => 'Slider', 'value' => '@{v}' })
    plain = convert(RjuiTools::React::Converters::SliderConverter,
                    { 'class' => 'Slider', 'value' => '@{v}', 'bind' => '@{unused}' })
    expect(plain).to eq(with_bind)
  end

  # Without this the JSX references a Data property the model never declared.
  describe 'Data model' do
    # The generator reads its config from ConfigManager at construction; only
    # the pure extraction is under test here.
    let(:generator) { RjuiTools::React::DataModelGenerator.allocate }

    it 'registers the bound property and its change handler' do
      bindings = generator.send(
        :extract_value_bindings,
        { 'type' => 'Switch', 'id' => 'flag', 'bind' => '@{isEnabled}' }
      )
      expect(bindings).to have_key('isEnabled')
      expect(bindings['isEnabled'][:type]).to eq('boolean')
    end

    it 'types the binding per component' do
      slider = generator.send(:extract_value_bindings, { 'type' => 'Slider', 'bind' => '@{vol}' })
      field = generator.send(:extract_value_bindings, { 'type' => 'TextField', 'bind' => '@{name}' })
      expect(slider['vol'][:type]).to eq('number')
      expect(field['name'][:type]).to eq('string')
    end
  end
end

# indexBelow / tint — two more spellings web read nowhere.
RSpec.describe 'z-order and tint spellings on web' do
  let(:config) { { 'use_tailwind' => true } }

  def view(extra)
    RjuiTools::React::Converters::ViewConverter.new(
      { 'class' => 'View', 'width' => 10, 'height' => 10 }.merge(extra), config
    ).convert(2)
  end

  # CSS has no relative z-order, so this lands on the same answer the iOS
  # codegen gives for the view-ID form: behind, at z -1.
  it 'places a view behind for indexBelow' do
    expect(view('indexBelow' => 'header')).to include('z-[-1]')
  end

  # An explicit zIndex is the author being specific.
  it 'yields to an explicit zIndex' do
    result = view('indexBelow' => 'header', 'zIndex' => 50)
    expect(result).to include('z-50')
    expect(result).not_to include('z-[-1]')
  end

  it 'emits no z class without indexBelow' do
    expect(view({})).not_to include('z-')
  end

  describe 'tint' do
    def control(klass, extra)
      klass.new({ 'class' => 'Switch' }.merge(extra), config).convert(2)
    end

    it 'colours the Switch track' do
      expect(control(RjuiTools::React::Converters::SwitchConverter, 'tint' => '#FF0000'))
        .to include('#FF0000')
    end

    it 'colours the Toggle' do
      expect(control(RjuiTools::React::Converters::ToggleConverter, 'tint' => '#FF0000'))
        .to include('#FF0000')
    end

    # Same precedence as kjui's switch_component: onTintColor || tint || tintColor.
    it 'yields to onTintColor' do
      result = control(RjuiTools::React::Converters::SwitchConverter,
                       'tint' => '#FF0000', 'onTintColor' => '#00FF00')
      expect(result).to include('#00FF00')
      expect(result).not_to include('#FF0000')
    end

    # The track colour is the `peer-checked:bg-[...]` class. `tintColor` also
    # feeds `accentColor` from base_converter, which is a different CSS property
    # and stays where it is.
    it 'wins over the tintColor alias for the track' do
      result = control(RjuiTools::React::Converters::SwitchConverter,
                       'tint' => '#FF0000', 'tintColor' => '#0000FF')
      expect(result).to include('peer-checked:bg-[#FF0000]')
      expect(result).not_to include('peer-checked:bg-[#0000FF]')
    end
  end
end
