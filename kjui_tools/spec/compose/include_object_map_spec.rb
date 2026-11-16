# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'compose/include_expander'

# An include node's object maps — `shared_data`, then `data` — are laid over
# the including layout's data for the included layout (ruling 2026-10-02;
# shared/core/include_data_map.rb; the SSoT's common/include). Until
# jsonui-cli 1.9.6 this expander dropped an object map, so the partial's
# `@{title}` read the screen's `title` whatever the map said (ticket
# native-include-object-map-is-ignored). The same arms are on sjui
# (spec/swiftui/include_object_map_spec.rb); every expander's tree is
# compared on one corpus by jui_tools/tests/test_include_maps_agree_on_every_expander.py.
RSpec.describe 'an include node object map (kjui)' do
  let(:dir) { Dir.mktmpdir('include_object_map') }

  after { FileUtils.rm_rf(dir) }

  def layout(name, tree)
    path = File.join(dir, "#{name}.json")
    FileUtils.mkdir_p(File.dirname(path))
    File.write(path, JSON.generate(tree))
  end

  before do
    layout('parts/panel', 'type' => 'View', 'id' => 'panel_root',
                          'child' => [{ 'type' => 'Label', 'id' => 't', 'text' => '@{title}' },
                                      { 'type' => 'Label', 'id' => 'n', 'text' => 'Hi @{name}' },
                                      { 'type' => 'View', 'id' => 'v', 'visibility' => '@{shown}' }])
  end

  # { id => what it draws } on the screen with `include_node` expanded.
  def drawn(include_node)
    tree = KjuiTools::Compose::IncludeExpander.process_includes(
      { 'type' => 'View', 'child' => [include_node] }, dir, nil, dir
    )
    out = {}
    walk = lambda do |node|
      next unless node.is_a?(Hash)

      out[node['id']] = node['text'] || node['visibility'] if node.key?('text') || node.key?('visibility')
      Array(node['child']).each { |c| walk.call(c) }
    end
    walk.call(tree)
    out
  end

  it 'reads a binding in the screen scope, a literal, and a Bool for a whole binding' do
    expect(drawn('include' => 'parts/panel', 'data' => { 'title' => '@{pageTitle}', 'name' => 'John', 'shown' => false }))
      .to eq('t' => '@{pageTitle}', 'n' => 'Hi John', 'v' => false)
  end

  it 'reads data over shared_data' do
    expect(drawn('include' => 'parts/panel', 'shared_data' => { 'title' => '@{a}', 'name' => 'x' },
                 'data' => { 'title' => '@{b}' }))
      .to include('t' => '@{b}', 'n' => 'Hi x')
  end

  # Under an id the partial's names are prefixed; a map key is still the
  # partial's name and its value is still the screen's.
  it 'reads the map under an id, and prefixes what no map sets' do
    expect(drawn('include' => 'parts/panel', 'id' => 'side', 'data' => { 'title' => '@{pageTitle}' }))
      .to eq('sideT' => '@{pageTitle}', 'sideN' => 'Hi @{sideName}', 'sideV' => '@{sideShown}')
  end

  # The control: no map, the screen's own names — the reading until 1.9.6
  # too, so the arms above are what moved.
  it 'reads the screen names without a map' do
    expect(drawn('include' => 'parts/panel'))
      .to eq('t' => '@{title}', 'n' => 'Hi @{name}', 'v' => '@{shown}')
  end

  # An array `data` declares; it is not a map.
  it 'merges an array data as declarations, as before' do
    tree = KjuiTools::Compose::IncludeExpander.process_includes(
      { 'type' => 'View', 'child' => [{ 'include' => 'parts/panel', 'data' => [{ 'name' => 'title', 'class' => 'String' }] }] },
      dir, nil, dir
    )
    expect(tree['child'].first['data']).to eq([{ 'name' => 'title', 'class' => 'String' }])
    expect(tree['child'].first['child'].first['text']).to eq('@{title}')
  end
end
