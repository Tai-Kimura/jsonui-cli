# frozen_string_literal: true

require 'json'
require 'core/layout_path'

# A node's position and the viewId its handlers are handed
# (JsonUIShared::LayoutPath, byte-identical to shared/core/layout_path.rb):
# its id, else `<drawn type, first letter lowercased>_<path>` — 4f's ruling
# on sjui-codegen-state-declarations-collide-by-name (1.9.0). The table is the
# shared one, shared/core/layout_path_vectors.json, which the sjui and kjui
# codegen and both Dynamic runtimes run too.
#
# ⚠️ An include is where rjui differs, by construction: rjui does not expand
# an include into the layout — it calls the included layout's own component —
# so the nodes inside it are stamped from that file's own root, where sjui
# and kjui stamp the expanded tree (`0_0_0` there, `0` here for the included
# root). The include itself still takes the one index in its parent's list,
# so nothing around it moves; that much is the shared case, run below.
RSpec.describe 'JsonUIShared::LayoutPath (rjui)' do
  vectors = JSON.parse(File.read(File.expand_path('../../../shared/core/layout_path_vectors.json', __dir__), encoding: 'UTF-8'))

  paths = lambda do |tree|
    got = {}
    walk = lambda do |node|
      next unless node.is_a?(Hash)

      got[node['id']] = node[JsonUIShared::LayoutPath::KEY] if node['id']
      JsonUIShared::LayoutPath.children(node).each { |child| walk.call(child) }
    end
    walk.call(tree)
    got
  end

  it 'the shared tables are here and have cases' do
    expect(vectors['cases']).not_to be_empty
    expect(vectors['view_id_cases']).not_to be_empty
  end

  vectors['cases'].each do |c|
    it "path: #{c['name']}" do
      tree = JsonUIShared::LayoutPath.stamp!(JSON.parse(JSON.generate(c['layout'])))
      expected = c['expect']
      # The nodes an include brings in are the included component's own
      # (see above); the include's own index and every node around it are
      # the table's.
      expected = expected.reject { |id, _| c['includes']&.values&.any? { |inc| paths.(JsonUIShared::LayoutPath.stamp!(JSON.parse(JSON.generate(inc)))).key?(id) } }
      expect(paths.(tree).slice(*expected.keys)).to eq(expected)
    end
  end

  it 'an include takes one index, and the included layout is its own root' do
    c = vectors['cases'].find { |x| x['includes'] }
    tree = JsonUIShared::LayoutPath.stamp!(JSON.parse(JSON.generate(c['layout'])))
    expect(tree['child'][0][JsonUIShared::LayoutPath::KEY]).to eq('0_0')
    included = JsonUIShared::LayoutPath.stamp!(JSON.parse(JSON.generate(c['includes'].values.first)))
    expect(paths.(included)).to eq('p' => '0', 'p0' => '0_0', 'p1' => '0_1')
  end

  vectors['view_id_cases'].each do |c|
    it "viewId: #{c['name']}" do
      tree = JsonUIShared::LayoutPath.stamp!(JSON.parse(JSON.generate(c['layout'])))
      got = {}
      walk = lambda do |node|
        next unless node.is_a?(Hash)

        got[node['_label']] = JsonUIShared::LayoutPath.view_id(node) if node['_label']
        JsonUIShared::LayoutPath.children(node).each { |child| walk.call(child) }
      end
      walk.call(tree)
      expect(got.slice(*c['expect'].keys)).to eq(c['expect'])
    end
  end
end
