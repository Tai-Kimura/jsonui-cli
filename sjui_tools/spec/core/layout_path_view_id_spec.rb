# frozen_string_literal: true

require 'json'
require 'core/layout_path'

# The viewId a node's handlers are handed (JsonUIShared::LayoutPath.view_id):
# its id, else `<drawn type, first letter lowercased>_<path>` — 4f's ruling on
# sjui-codegen-state-declarations-collide-by-name (1.9.0). The table is the
# shared one, shared/core/layout_path_vectors.json `view_id_cases`, which the
# kjui codegen and both Dynamic runtimes run too.
RSpec.describe 'JsonUIShared::LayoutPath.view_id' do
  vectors_path = File.expand_path('../../../shared/core/layout_path_vectors.json', __dir__)
  cases = File.exist?(vectors_path) ? JSON.parse(File.read(vectors_path, encoding: 'UTF-8'))['view_id_cases'] : []

  it 'the shared table is here and has cases' do
    expect(cases).not_to be_empty
  end

  cases.each do |c|
    it c['name'] do
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

  it 'a node on its own is its own root' do
    expect(JsonUIShared::LayoutPath.view_id('type' => 'Slider')).to eq('slider_0')
  end
end
