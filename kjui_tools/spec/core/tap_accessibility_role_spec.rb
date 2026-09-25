# frozen_string_literal: true

require 'compose/helpers/modifier_builder'
require 'core/tap_accessibility'
require 'json'
require 'set'

# kjui's `.clickable` carries `role = Role.Button` exactly where the shared
# vectors say a tap is a button (button or combine), and the Role import comes
# with it; a tap that is a control or holds one keeps a bare `.clickable`.
RSpec.describe 'kjui tap role' do
  vectors_path = File.expand_path('../../../shared/core/tap_accessibility_vectors.json', __dir__)
  next unless File.exist?(vectors_path)

  JSON.parse(File.read(vectors_path))['cases'].each do |vector|
    it vector['name'] do
      tree = JSON.parse(JSON.generate(vector['layout']))
      JsonUIShared::TapAccessibility.annotate!(tree)
      JsonUIShared::TapAccessibility.walk(tree) do |node|
        next unless vector['shapes'].key?(node['id'])

        imports = Set.new
        clickable = KjuiTools::Compose::Helpers::ModifierBuilder.build_clickable(node, imports).join(' ')
        want = %w[button combine].include?(vector['shapes'][node['id']])
        expect(clickable.include?('role = Role.Button')).to eq(want), "#{node['id']}: #{clickable}"
        expect(imports.include?(:role)).to eq(want)
      end
    end
  end
end
