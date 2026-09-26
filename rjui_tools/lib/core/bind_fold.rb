# frozen_string_literal: true

require 'json'

module JsonUIShared
  # `bind`, folded into the attribute it stands for, on the node a renderer
  # actually draws — after its style is merged and its responsive branch
  # resolved (4f's ruling, jsonui-cli 1.9.0). SSoT common.bind: "an
  # alternative spelling to each component's own value attribute, which takes
  # precedence when both are set"; `primaryValue` names, per section, the
  # attributes `bind` stands for:
  # - a lone `bind` becomes the first of them;
  # - beside any of them, `bind` is dropped (the shared validator names it);
  # - on a section the table does not name, `bind` stays.
  #
  # The one rule every path folds by: the jui normalizer (on a node whose
  # drawn form a style or a responsive branch does not change), the kjui /
  # sjui / rjui codegen at their component dispatch, KotlinJsonUI Dynamic's
  # BindFold and SwiftJsonUI Dynamic, over the one table (lane 31's generated
  # JsonUIBindPrimaryValue on the libraries). shared/core/bind_fold_vectors.json
  # holds the cases, `attributes_for_cases` the table's own.
  #
  # Canonical in shared/core; each tool's lib/core holds a byte-identical copy
  # (shared_core_mirror_spec), next to the attribute_definitions.json and
  # type_synonyms.json it reads.
  module BindFold
    module_function

    # The node with its `bind` folded; the same object when there is nothing
    # to fold. `type` is the spelling the caller draws (as written: the table
    # is not matched case-insensitively); a type-synonym is resolved to its
    # canonical section here, as a caller of attributes_for does.
    def fold(node, type = nil)
      return node unless node.is_a?(Hash) && node.key?('bind')

      type ||= node['type']
      values = attributes_for(synonyms.dig(type, 'canonical') || type, node)
      return node if values.empty?

      folded = node.reject { |key, _| key == 'bind' }
      folded[values.first] = node['bind'] if values.none? { |attr| node.key?(attr) }
      folded
    end

    # The attributes `bind` stands for on a node of `type`, the first being
    # where a lone `bind` goes: the table's entry for the type as written,
    # else for the section its `_alias_of` names (a type-synonym is the
    # caller's to resolve first). A list entry is the answer; an object entry {by,
    # whenAbsent, lists} answers lists[node[by]] when node[by] is a string the
    # lists name, else lists[whenAbsent]. No entry: [].
    def attributes_for(type, node)
      table = definitions.dig('common', 'bind', 'primaryValue')
      return [] unless table.is_a?(Hash) && type.is_a?(String)

      entry = table[type] || table[definitions.dig(type, '_alias_of')]
      entry = list_for(entry, node) if entry.is_a?(Hash)
      entry.is_a?(Array) ? entry.grep(String) : []
    end

    def list_for(entry, node)
      lists = entry['lists']
      return nil unless lists.is_a?(Hash) && entry['by'].is_a?(String)

      kind = node.is_a?(Hash) ? node[entry['by']] : nil
      kind = entry['whenAbsent'] unless kind.is_a?(String) && lists.key?(kind)
      lists[kind]
    end

    def definitions
      @definitions ||= read_table('attribute_definitions.json')
    end

    def synonyms
      @synonyms ||= (read_table('type_synonyms.json')['synonyms'] || {})
    end

    def read_table(name)
      path = File.join(__dir__, name)
      File.exist?(path) ? JSON.parse(File.read(path, encoding: 'UTF-8')) : {}
    end
  end
end
