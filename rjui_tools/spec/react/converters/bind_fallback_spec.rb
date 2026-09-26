# frozen_string_literal: true

require_relative '../../spec_helper'
require 'json'
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
require 'react/react_generator'

# `bind` is the alternative spelling for a component's primary value binding
# (SSoT common.bind, primaryValue). The dispatch folds it into the attribute it
# stands for on the node a built-in converter draws — its style merged —
# (JsonUIShared::BindFold, in BaseConverter#create_converter_for_child and
# ReactGenerator#convert_component); no converter reads `bind` itself. Each read
# it last in its own chain (`with_bind_fallback`), so a literal `isOn: false`
# beside `bind` drew the binding, and a TextField's bind was bound on web only.
RSpec.describe 'bind as the primary value binding' do
  let(:config) { { 'use_tailwind' => true, 'typescript' => true } }

  # Through the dispatch: the node is a child, as every drawn node but the
  # root is (create_converter_for_child).
  def convert(_klass, json)
    parent = { 'class' => 'View', 'id' => 'parent', 'child' => [json.merge('type' => json['class'])] }
    RjuiTools::React::Converters::ViewConverter.new(parent, config).convert(2)
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

  # Not on a Collection (ruled 2026-09-26): rjui was the one path that read
  # `bind` as the items — sjui, kjui and both Dynamic renderers never did — so
  # a Collection bound that way drew on web only. `items` is its data source;
  # the shared validator warns on `bind` there (ticket
  # collection-attributes-declared-but-not-drawn-on-some-paths).
  it 'does not read bind as the item source on Collection' do
    result = convert(
      RjuiTools::React::Converters::CollectionConverter,
      { 'class' => 'Collection', 'bind' => '@{rows}', 'sections' => [{ 'cell' => 'RowCell' }] }
    )
    expect(result).not_to include('data.rows')
  end

  # The component's own value attribute wins; `bind` beside it is dropped.
  it 'yields to an explicit value attribute' do
    result = convert(
      RjuiTools::React::Converters::SwitchConverter,
      { 'class' => 'Switch', 'isOn' => '@{explicit}', 'bind' => '@{ignored}' }
    )
    expect(result).to include('data.explicit')
    expect(result).not_to include('data.ignored')
  end

  # `isOn: false` is a value, not an absence: it is the Switch's value, and
  # `bind` beside it is dropped. The chains read it as falsy and fell through
  # to `bind`, so the binding was drawn.
  it 'takes a static false as the value' do
    result = convert(
      RjuiTools::React::Converters::SwitchConverter,
      { 'class' => 'Switch', 'isOn' => false, 'bind' => '@{fallback}' }
    )
    expect(result).not_to include('data.fallback')
  end

  # The style cases of the shared table: the child's style merged
  # (BaseConverter#apply_style), then folded.
  it 'draws each style case as the table says' do
    vectors = File.expand_path('../../../../shared/core/bind_fold_vectors.json', __dir__)
    skip 'shared vectors not present in this layout' unless File.exist?(vectors)

    require 'tmpdir'
    date, switch = JSON.parse(File.read(vectors))['style_cases']
    Dir.mktmpdir do |dir|
      [date, switch].each { |c| c['styles'].each { |name, body| File.write(File.join(dir, "#{name}.json"), JSON.generate(body)) } }
      draw = lambda do |c|
        parent = { 'class' => 'View', 'id' => 'parent', 'child' => [c['node'].merge('id' => 'x')] }
        RjuiTools::React::Converters::ViewConverter.new(parent, config.merge('styles_directory' => dir)).convert(2)
      end
      expect(draw.call(date)).to include('data.day')
      on = draw.call(switch)
      expect(on).not_to include('data.on')
      expect(on).to include('defaultChecked')
    end
  end

  # The root node is dispatched by ReactGenerator#convert_component, not the
  # child path: it folds too.
  it 'folds the root node at ReactGenerator#convert_component' do
    generator = RjuiTools::React::ReactGenerator.allocate
    generator.instance_variable_set(:@config, config)
    generator.instance_variable_set(:@extension_converters, {})
    root = generator.send(:convert_component, { 'type' => 'Switch', 'id' => 'r', 'bind' => '@{rootOn}' })
    expect(root).to include('data.rootOn')
    kept = generator.send(:convert_component, { 'type' => 'Switch', 'id' => 'r', 'isOn' => false, 'bind' => '@{rootOn}' })
    expect(kept).not_to include('data.rootOn')
  end

  # An extension converter (the app's own component) gets its node as written.
  it 'hands an extension converter its node with bind' do
    seen = nil
    extension = Class.new do
      define_method(:initialize) { |json, _config| seen = json }
      define_method(:convert) { |_indent = 0| '<Mine />' }
      define_method(:convert_node) { |_indent = 0| '<Mine />' }
    end
    parent = { 'class' => 'View', 'id' => 'parent', 'child' => [{ 'type' => 'Switch', 'bind' => '@{b}' }] }
    RjuiTools::React::Converters::ViewConverter.new(parent, config.merge('_extension_converters' => { 'Switch' => extension })).convert(2)
    expect(seen).to include('bind' => '@{b}')
    expect(seen).not_to have_key('isOn')
  end

  # No converter reads `bind`: the dispatch folds it (code only — a comment
  # naming it does not count).
  it 'is read by no converter' do
    token = /\['bind'\]|\["bind"\]|with_bind_fallback\(/
    hits = lambda do |text, name|
      # map + compact, not filter_map: Ruby 2.6 (the consumer floor and a
      # CI leg until jsonui-cli 1.9.0; 3.2 since) has no filter_map
      text.lines.each_with_index.map do |line, i|
        next if line.strip.start_with?('#')

        "#{name}:#{i + 1}" if line.sub(/#.*/, '') =~ token
      end.compact
    end
    # the scan tells a read from a comment (both sides)
    expect(hits.call("          value = attributes['bind']\n", 'read').size).to eq(1)
    expect(hits.call("        # attributes['bind'] was read here\n", 'comment').size).to eq(0)

    lib = File.expand_path('../../../lib/react', __dir__)
    files = Dir.glob(File.join(lib, '**', '*.rb'))
    expect(files.size).to be > 30
    found = files.flat_map { |f| hits.call(File.read(f), f.delete_prefix("#{lib}/")) }
    expect(found).to eq([])
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
