# frozen_string_literal: true

require_relative '../spec_helper'
require 'core/node_keys'

# A predicate over a layout node's key set reads the keys the layout wrote
# (RjuiTools::Core::NodeKeys.written), never the node's raw `keys`: the
# generator stamps every node it converts with its position, and from
# 2de6da9b a data-only element counted that stamp and was drawn as an empty
# <div />. The scan below holds the family closed: a node's `keys` read
# directly, by any of the names the tools give a node, is red here.
RSpec.describe 'RjuiTools::Core::NodeKeys' do
  it "leaves out the generator's position stamp, and only that" do
    node = { 'data' => [], JsonUIShared::LayoutPath::KEY => '0_1', '_other' => 1 }
    expect(RjuiTools::Core::NodeKeys.written(node)).to eq(%w[data _other])
  end

  NODE_NAMES = %w[node child json json_data component attributes item entry_node].freeze
  LIB = File.expand_path('../../lib', __dir__)

  def raw_node_key_reads
    # `map { }.compact`, not `filter_map`: the suite ran on Ruby 2.6 too,
    # until jsonui-cli 1.9.0 (the floor is 3.2 since).
    Dir.glob(File.join(LIB, '**', '*.rb')).sort.flat_map do |file|
      File.readlines(file, encoding: 'UTF-8').each_with_index.map do |line, i|
        next if line.lstrip.start_with?('#') || file.end_with?('node_keys.rb')
        next unless line.match?(/\b(?:#{NODE_NAMES.join('|')})\.keys\b/)
        # The tap rule is a shared/core mirror, which cannot call this tool's
        # NodeKeys: it subtracts its own WRITTEN_STAMPS, pinned below to hold
        # every stamp NodeKeys leaves out.
        next if file.end_with?('core/tap_accessibility.rb') && line.match?(/\.keys - WRITTEN_STAMPS\)/)

        "#{file.sub("#{LIB}/", '')}:#{i + 1}: #{line.strip}"
      end.compact
    end
  end

  it 'is the only way the tool reads a node\'s keys' do
    expect(raw_node_key_reads).to be_empty, raw_node_key_reads.join("\n")
  end

  it "the tap rule's written keys leave out every stamp NodeKeys leaves out" do
    require 'core/tap_accessibility'
    expect(JsonUIShared::TapAccessibility::WRITTEN_STAMPS).to include(*RjuiTools::Core::NodeKeys::STAMPS)
  end

  # The scan can see what it forbids: a line of the forbidden shape is found.
  it 'finds the shape it forbids (control)' do
    line = "          child.keys == ['data'] && child['data'].is_a?(Array)"
    expect(line.match?(/\b(?:#{NODE_NAMES.join('|')})\.keys\b/)).to be(true)
  end
end
