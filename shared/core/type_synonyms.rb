# frozen_string_literal: true

require 'json'

module JsonUIShared
  # The type-spelling synonyms for Ruby — shared/core/type_synonyms.json, the
  # one table, read beside this file (each tool's lib/core carries the file
  # and this mirror). The validator (attribute_validator_core.rb) resolves a
  # node's section with it, holding no list of its own; a converter factory
  # is to draw a synonym as it says in the same way (the type_synonyms_draw
  # specs measure the factories that do).
  #
  # An entry: `canonical` (the section the spelling validates against),
  # `render_as` (the type a renderer draws where that is not the canonical
  # one), and any other key — an attribute the spelling means (HStack: a
  # View with `orientation: horizontal`).
  module TypeSynonyms
    DEFAULT_PATH = File.join(__dir__, 'type_synonyms.json')
    META_KEYS = %w[canonical render_as].freeze

    class << self
      # spelling -> entry, read once per path. A table that cannot be used —
      # missing (what a plain copy of a tool leaves: the file is a link into
      # shared/core), not JSON, or not the declared shape — reads as empty:
      # the validator names it and records the validation stage incomplete,
      # once (attribute_validator_core.rb#type_synonyms, from `load`), and a
      # converter then draws a synonym spelling as an undeclared type. No
      # tool raises on it: raising stopped the build before the ledger was
      # written.
      def entries(path = DEFAULT_PATH)
        @entries ||= {}
        @entries[path] ||= load(path).first
      end

      # [entries, problem] for the table at `path` — the one parser of it.
      # `problem` is nil, or [said, entry] when the table cannot be used:
      # what the validator prints where it meets the table, and the ledger
      # entry it records. Read as UTF-8 whatever the locale says (the table's
      # text is UTF-8): a library reader, such as tap_accessibility.rb, may
      # run where the entry point did not set the default encoding.
      def load(path = DEFAULT_PATH)
        return [{}, ["type_synonyms.json not found at #{path}", "#{path} was not found"]] unless File.exist?(path)

        begin
          parsed = JSON.parse(File.read(path, encoding: 'UTF-8'))
        rescue JSON::ParserError => e
          reason = e.message.lines.first.to_s.strip
          return [{}, ["#{path} does not parse: #{reason}", "#{path} does not parse (#{reason})"]]
        end
        entries = parsed.is_a?(Hash) ? parsed['synonyms'] : nil
        unless entries.is_a?(Hash) && entries.values.all? { |e| e.is_a?(Hash) && e['canonical'].is_a?(String) }
          shape = '`synonyms` must map each spelling to an object with a `canonical` string'
          return [{}, ["#{path}: #{shape}", "#{path} is not the declared shape (#{shape})"]]
        end

        [entries, nil]
      end

      # The type `type` is drawn as: its synonym's target, or itself.
      def drawn_as(type, path = DEFAULT_PATH)
        entry = entries(path)[type]
        entry ? (entry['render_as'] || entry['canonical']) : type
      end

      # The spellings an app registers as components of its own. Each tool
      # sets them from its registry (sjui's custom converters, kjui's
      # COMPONENT_MAPPINGS, rjui's extension converters) before it reads a
      # layout. A node spelled so is the app's, whatever the spelling: its
      # converter is asked first, so it is drawn as written, and what
      # classifies it must not read it as the synonym it also is.
      def app_types=(types)
        @app_types = Array(types).map(&:to_s).uniq.freeze
      end

      def app_types
        @app_types || []
      end

      # The type a node spelled `type` is drawn as: an app's own spelling as
      # written; else its synonym's target, then the canonical section of a
      # declared alias (ComponentAliases). What classifies a node by its type
      # (which data it needs, which imports, whether it takes focus) asks
      # this, not the spelling as written, so it agrees with the converter
      # that draws the node; a list of types to compare it with holds the
      # drawn types only.
      def drawn_type(type, path = DEFAULT_PATH)
        return type unless type.is_a?(String)
        return type if app_types.include?(type)

        JsonUIShared::ComponentAliases.canonical(drawn_as(type, path))
      end

      # The spelling `written` means when case is ignored, or nil. Type names
      # are their SSoT spellings, case-sensitive (1.9.0): `switch` is no
      # Switch, and what names an unknown type offers this one ("did you
      # mean"). `known` is the types the caller draws; the table's synonyms,
      # the declared alias sections and the app's types are added. nil when
      # `written` is itself one of them, or none matches.
      def case_only_match(written, known = [], path = DEFAULT_PATH)
        return nil unless written.is_a?(String)

        pool = known + app_types + entries(path).keys + JsonUIShared::ComponentAliases.table.keys
        return nil if pool.include?(written)

        pool.find { |spelling| spelling.casecmp?(written) }
      end

      # The declared section a node spelled `type` is validated against:
      # its synonym's `canonical` (not `render_as` — CircleImage is drawn as
      # CircleImage and validated as Image), then a declared alias's canonical
      # section. What looks a type's attributes up asks this.
      def section(type, path = DEFAULT_PATH)
        return type unless type.is_a?(String)

        entry = entries(path)[type]
        JsonUIShared::ComponentAliases.canonical(entry ? entry['canonical'] : type)
      end

      # `node` as a converter factory is given it: an app's own spelling as
      # written; else canonicalized (the synonym's type and the attributes it
      # means), then its alias section resolved. A copy when anything
      # changed; `node` itself otherwise.
      def drawn(node, path = DEFAULT_PATH)
        return node if node.is_a?(Hash) && app_types.include?(node['type'])

        JsonUIShared::ComponentAliases.resolve(canonicalize(node, path))
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

        # (map + compact, not filter_map: the tools ran on Ruby 2.6 until
        # jsonui-cli 1.9.0; the floor is 3.2 since)
        implied(type, path).map do |key, meant|
          next unless node.key?(key) && node[key] != meant

          "#{type} means #{key} #{meant}, and the node sets #{key} #{node[key]}: " \
            "drawn as #{drawn_as(type, path)} with #{key} #{node[key]}"
        end.compact
      end

    end
  end

  # The declared component aliases — attribute_definitions.json sections that
  # are `_alias_of` pointers (EditText -> TextField, Check -> CheckBox, …) —
  # for the converter factories, which draw an alias as its canonical
  # section. Read from the definitions beside this file, with the rule the
  # validator follows (attribute_validator_core.rb resolve_component_alias):
  # one hop, and a pointer to a missing or alias-shaped section is ignored.
  module ComponentAliases
    DEFAULT_DEFINITIONS = File.join(__dir__, 'attribute_definitions.json')

    class << self
      # alias spelling -> canonical section, read once per path. A missing
      # file reads as empty, as TypeSynonyms.entries reads a missing table:
      # the validator names it and records the validation stage incomplete
      # (load_definitions), and a converter then draws an alias as an
      # undeclared type. A malformed file raises (JSON::ParserError).
      def table(path = DEFAULT_DEFINITIONS)
        @tables ||= {}
        @tables[path] ||= File.exist?(path) ? read(path) : {}
      end

      # The canonical section `type` is an alias of, or `type` itself.
      def canonical(type, path = DEFAULT_DEFINITIONS)
        table(path)[type] || type
      end

      # `node` with its type resolved to the canonical section when it is an
      # alias (a copy); anything else is `node` itself.
      def resolve(node, path = DEFAULT_DEFINITIONS)
        return node unless node.is_a?(Hash) && node['type'].is_a?(String)

        target = table(path)[node['type']]
        target ? node.merge('type' => target) : node
      end

      private

      def read(path)
        definitions = JSON.parse(File.read(path, encoding: 'UTF-8'))
        definitions.each_with_object({}) do |(name, section), aliases|
          next unless section.is_a?(Hash) && section['_alias_of'].is_a?(String)

          target = definitions[section['_alias_of']]
          next unless target.is_a?(Hash) && !target['_alias_of'].is_a?(String)

          aliases[name] = section['_alias_of']
        end
      end
    end
  end
end
