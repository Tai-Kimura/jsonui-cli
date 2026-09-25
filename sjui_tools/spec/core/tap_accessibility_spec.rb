# frozen_string_literal: true

require 'core/tap_accessibility'
require 'json'

# The tap shapes (shared/core/tap_accessibility.rb; this tool's copy is pinned
# to it by shared_core_mirror_spec) and the declaration they read: every
# component_metadata.json type states `interactive`, and the rule's two lists
# are that declaration with its aliases. The vectors are the table the
# KotlinJsonUI and SwiftJsonUI Dynamic runtimes also run, from byte-identical
# copies — so a declaration changed here without the rule, or the rule
# without the declaration, is red here before it reaches them.
RSpec.describe JsonUIShared::TapAccessibility do
  shared_core = File.expand_path('../../../shared/core', __dir__)
  metadata_path = File.join(shared_core, 'component_metadata.json')
  vectors_path = File.join(shared_core, 'tap_accessibility_vectors.json')

  if File.exist?(metadata_path)
    metadata = JSON.parse(File.read(metadata_path))
    types = metadata.reject { |k, _| k.start_with?('_') }
    with_aliases = ->(names) { names.flat_map { |t| [t] + Array(types[t]['aliases']) }.uniq.sort }

    it 'reads a declared interactive on every component_metadata type (absence is not an answer)' do
      missing = types.reject { |_, v| [true, false].include?(v['interactive']) }.keys
      expect(missing).to eq([])
    end

    it 'holds exactly the declared interactive types, with their aliases' do
      declared = with_aliases.call(types.select { |_, v| v['interactive'] == true }.keys)
      expect(described_class::INTERACTIVE_TYPES.sort).to eq(declared)
    end

    it 'knows exactly the declared types, with their aliases' do
      expect(described_class::KNOWN_TYPES.sort).to eq(with_aliases.call(types.keys))
    end
  end

  if File.exist?(vectors_path)
    vectors = JSON.parse(File.read(vectors_path))

    it 'carries the same lists the libraries read' do
      expect(vectors['interactive_types']).to eq(described_class::INTERACTIVE_TYPES.sort)
      expect(vectors['known_types']).to eq(described_class::KNOWN_TYPES.sort)
    end

    it 'has every shape, and a node that is no tap' do
      shapes = vectors['cases'].flat_map { |c| c['shapes'].values }
      expect(shapes.compact.uniq.sort).to eq(%w[button combine none])
      expect(shapes).to include(nil)
    end

    vectors['cases'].each do |vector|
      it vector['name'] do
        tree = JSON.parse(JSON.generate(vector['layout']))
        described_class.annotate!(tree)
        got = {}
        described_class.walk(tree) { |n| got[n['id']] = n[described_class::SHAPE_KEY] if vector['shapes'].key?(n['id']) }
        expect(got).to eq(vector['shapes'])
      end
    end
  end
end
