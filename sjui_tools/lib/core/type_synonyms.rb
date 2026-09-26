# frozen_string_literal: true

require 'json'

module JsonUIShared
  # The type-spelling synonyms for Ruby — shared/core/type_synonyms.json, the
  # one table, read beside this file (each tool's lib/core carries the file
  # and this mirror). The validator (attribute_validator_core.rb) resolves a
  # node's section with it, and every converter factory draws a synonym as
  # it says; neither holds a list of its own.
  #
  # An entry: `canonical` (the section the spelling validates against),
  # `render_as` (the type a renderer draws where that is not the canonical
  # one), and any other key — an attribute the spelling means (HStack: a
  # View with `orientation: horizontal`).
  module TypeSynonyms
    DEFAULT_PATH = File.join(__dir__, 'type_synonyms.json')
    META_KEYS = %w[canonical render_as].freeze

    class << self
      # spelling -> entry, read once per path. A malformed file raises,
      # naming it: a table that read as empty would draw every synonym as an
      # unknown type and validate it against common only, and say nothing.
      #
      # A missing file reads as empty. It is what a plain copy of a tool
      # leaves (the file is a link into shared/core), and the validator names
      # it and records the validation stage incomplete, once
      # (attribute_validator_core.rb#type_synonyms); a converter then draws a
      # synonym spelling as an undeclared type. Raising here instead stopped
      # the build before the ledger was written.
      def entries(path = DEFAULT_PATH)
        @entries ||= {}
        @entries[path] ||= File.exist?(path) ? read(path) : {}
      end

      # The type `type` is drawn as: its synonym's target, or itself.
      def drawn_as(type, path = DEFAULT_PATH)
        entry = entries(path)[type]
        entry ? (entry['render_as'] || entry['canonical']) : type
      end

      # The attributes the spelling `type` means ({} for most).
      def implied(type, path = DEFAULT_PATH)
        entry = entries(path)[type]
        entry ? entry.reject { |key, _| META_KEYS.include?(key) } : {}
      end

      # `node` as a renderer draws it. For a synonym, a copy whose `type` is
      # what it is drawn as, with the attributes its spelling means added
      # where the node does not set them — the node's own value is kept
      # where it sets one (the validator warns about the disagreement).
      # Anything else is `node` itself.
      def canonicalize(node, path = DEFAULT_PATH)
        return node unless node.is_a?(Hash)

        type = node['type']
        entry = type.is_a?(String) && entries(path)[type]
        return node unless entry

        drawn = node.merge('type' => entry['render_as'] || entry['canonical'])
        implied(type, path).each { |key, value| drawn[key] = value unless node.key?(key) }
        drawn
      end

      # Where `node` sets an attribute its spelling means otherwise: one
      # message per such attribute ([] for none).
      def disagreements(node, path = DEFAULT_PATH)
        type = node['type']
        return [] unless type.is_a?(String)

        # (map + compact, not filter_map: the tools run on Ruby 2.6)
        implied(type, path).map do |key, meant|
          next unless node.key?(key) && node[key] != meant

          "#{type} means #{key} #{meant}, and the node sets #{key} #{node[key]}: " \
            "drawn as #{drawn_as(type, path)} with #{key} #{node[key]}"
        end.compact
      end

      private

      def read(path)
        entries = JSON.parse(File.read(path))['synonyms']
        unless entries.is_a?(Hash) && entries.values.all? { |e| e.is_a?(Hash) && e['canonical'].is_a?(String) }
          raise "#{path}: `synonyms` must map each spelling to an object with a `canonical` string"
        end

        entries
      end
    end
  end
end
