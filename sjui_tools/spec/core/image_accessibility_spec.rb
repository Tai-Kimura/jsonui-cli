# frozen_string_literal: true

require 'core/image_accessibility'
require 'core/string_manager_core'
require 'json'

# The role each image gets from its alt and the tappable around it
# (shared/core/image_accessibility.rb; this tool's copy is pinned to it by
# shared_core_mirror_spec). The vectors are the table the KotlinJsonUI and
# SwiftJsonUI Dynamic runtimes also run, from their byte-identical copies.
RSpec.describe JsonUIShared::ImageAccessibility do
  shared_core = File.expand_path('../../../shared/core', __dir__)
  vectors_path = File.join(shared_core, 'image_accessibility_vectors.json')

  def images(node, out = [])
    return out unless node.is_a?(Hash)

    out << node if described_class.image?(node)
    described_class.children(node).each { |c| images(c, out) }
    out
  end

  if File.exist?(vectors_path)
    cases = JSON.parse(File.read(vectors_path)).fetch('cases')

    it 'has cases, and every role in them' do
      expect(cases).not_to be_empty
      expect(cases.flat_map { |c| c['roles'].values }.uniq.sort).to eq(%w[control decorative label])
    end

    cases.each do |vector|
      it vector['name'] do
        layout = JSON.parse(JSON.generate(vector['layout']))
        infos = described_class.annotate!(layout, source_path: 'probe.json')

        roles = images(layout).to_h { |img| [img['id'], img[described_class::ROLE_KEY]] }
        expect(roles).to eq(vector['roles'])

        controls = vector['roles'].select { |_, r| r == 'control' }.keys
        expect(infos.size).to eq(controls.size)
        controls.each { |id| expect(infos.map { |i| i[:message] }.join("\n")).to include("'#{id}'") }
        expect(infos.map { |i| i[:level] }.uniq).to eq(controls.empty? ? [] : [:info])
      end
    end
  end

  describe 'the vocabulary it reads, against the declarations' do
    definitions_path = File.join(shared_core, 'attribute_definitions.json')
    metadata_path = File.join(shared_core, 'component_metadata.json')

    before do
      skip 'shared/core not present in this layout' unless File.exist?(definitions_path)
    end

    it 'counts as images exactly Image, its type aliases and NetworkImage' do
      metadata = JSON.parse(File.read(metadata_path))
      declared = ['Image', 'NetworkImage'] + metadata['Image']['aliases'] + metadata['NetworkImage']['aliases']
      expect(described_class::IMAGE_TYPES.sort).to eq(declared.sort)
    end

    it 'reads alt under its canonical name and every declared alias, on both image components' do
      definitions = JSON.parse(File.read(definitions_path))
      %w[Image NetworkImage].each do |component|
        alt = definitions[component]['alt']
        expect(described_class::ALT_KEYS).to eq(['alt'] + alt['aliases'])
        expect(alt).not_to have_key('platform')
      end
    end

    it 'reads alt under each of those spellings, the canonical one first' do
      described_class::ALT_KEYS.each do |key|
        expect(described_class.alt(key => 'probe')).to eq('probe')
      end
      both = described_class::ALT_KEYS.to_h { |key| [key, key] }
      expect(described_class.alt(both)).to eq('alt')
    end

    it 'takes as taps only activations declared on every component' do
      # The tap rule's keys: the image rule asks it whether a node operates.
      common = JSON.parse(File.read(definitions_path))['common']
      tap = JsonUIShared::TapAccessibility
      (tap::TAP_KEYS + [tap::LONG_PRESS_KEY]).each { |key| expect(common).to have_key(key) }
    end

    it 'takes as naming text the localized text vocabulary, less alt (read off images)' do
      expect(described_class::TEXT_KEYS).to eq(JsonUIShared::StringManagerCore::STRING_PROPERTIES - ['alt'])
    end
  end
end
