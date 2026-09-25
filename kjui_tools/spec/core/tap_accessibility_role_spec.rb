# frozen_string_literal: true

require 'compose/helpers/modifier_builder'
require 'core/tap_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# kjui's `.clickable` carries `role = Role.Button` exactly where the shared
# vectors say a tap is a button (button or combine), and the Role import comes
# with it; a tap that is a control or holds one keeps a bare `.clickable`.
RSpec.describe 'kjui tap role' do
  vectors_path = File.expand_path('../../../shared/core/tap_accessibility_vectors.json', __dir__)
  next unless File.exist?(vectors_path)

  # Every `.clickable(...)` the vectors produce, with and without the role,
  # type-checks against Compose's signature (shared stub universe). Only the
  # `.clickable` element is this spec's subject; the long-press pointerInput
  # and the disabled semantics beside it are other specs'. The empty and
  # blank handlers are in the vectors too: they used to emit
  # `.clickable { data.?.invoke() }` (ticket kjui-empty-onclick-emits-invalid-kotlin).

  it 'emits clickable modifiers that compile' do
    chains = []
    JSON.parse(File.read(vectors_path))['cases'].each do |vector|
      tree = JSON.parse(JSON.generate(vector['layout']))
      JsonUIShared::TapAccessibility.annotate!(tree)
      JsonUIShared::TapAccessibility.walk(tree) do |node|
        clickable = KjuiTools::Compose::Helpers::ModifierBuilder.build_clickable(node, Set.new)
                                                                .select { |m| m.start_with?('.clickable') }
        next if clickable.empty?

        chains << "Modifier#{clickable.join}"
      end
    end
    expect(chains.join).to include('role = Role.Button')
    body = chains.each_with_index.map { |c, i| "fun tap#{i}(data: Data): Modifier = #{c}" }.join("\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.clickable(chains.join("\n"))}
      #{body}
    KOTLIN
  end

  # A `.clickable` exactly where the rule reads a handler
  # (TapAccessibility.handler? on either spelling) — gated shut or not, since
  # a disabled tap is still emitted as `.clickable(enabled = false)`. An empty
  # or blank handler gets none.
  it 'emits a clickable exactly where the rule reads a handler' do
    checked = 0
    JSON.parse(File.read(vectors_path))['cases'].each do |vector|
      tree = JSON.parse(JSON.generate(vector['layout']))
      JsonUIShared::TapAccessibility.walk(tree) do |node|
        keys = JsonUIShared::TapAccessibility::TAP_KEYS.select { |key| node.key?(key) }
        next if keys.empty?

        checked += 1
        want = keys.any? { |key| JsonUIShared::TapAccessibility.handler?(node[key]) }
        clickable = KjuiTools::Compose::Helpers::ModifierBuilder.build_clickable(node, Set.new)
                                                                .select { |m| m.start_with?('.clickable') }
        expect(clickable.any?).to eq(want), "#{vector['name']} / #{node['id']}: #{clickable.inspect}"
      end
    end
    expect(checked).to be >= 12
  end

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
