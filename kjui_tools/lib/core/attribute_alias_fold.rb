# frozen_string_literal: true

require 'json'
require_relative 'type_synonyms'

module KjuiTools
  module Core
    # The SSoT's attribute `aliases` (attribute_definitions.json) folded into
    # their canonical names on a layout tree — rules 1 and 2 of `jui build`'s
    # L1 canonicalizer (jui_cli/core/normalizer/canonicalizer.py): a section's
    # own aliases over `common`'s, and where a node carries an alias beside its
    # canonical name the canonical one wins and the alias is named.
    #
    # `jui build` canonicalizes the layouts it hands kjui (normalizeLayouts,
    # on by default). A layout it did not — `kjui build` run directly, as the
    # conformance codegen host does, or `"normalizeLayouts": false` — kept the
    # alias, and an attribute the converters read by its canonical name alone
    # was never read: SelectBox `onValueChanged` built with no warning and the
    # handler was never called (jsonui-cli runtime handler census, conf_ci,
    # 2026-10-03; sjui reads the same alias since 77b4cae5). The fold reads
    # the declaration, so every declared alias is read, not one written here.
    # It is idempotent: a canonicalized tree comes back unchanged.
    module AttributeAliasFold
      DEFINITIONS = File.join(__dir__, 'attribute_definitions.json')
      CHILD_KEYS = %w[child children].freeze
      SECTION_NODE_KEYS = %w[header footer cell].freeze

      class << self
        # Folds `tree` in place; returns the warnings (one per alias dropped
        # beside its canonical name).
        def fold!(tree, source: nil)
          warnings = []
          fold_node(tree, warnings, source)
          warnings
        end

        # { alias => canonical } for the section `type` is validated against.
        def aliases_for(type)
          section = JsonUIShared::TypeSynonyms.section(type)
          @by_section ||= {}
          @by_section[section] ||= begin
            merged = alias_map(definitions['common'])
            section == 'common' ? merged : merged.merge(alias_map(definitions[section]))
          end
        end

        private

        def definitions
          @definitions ||= File.exist?(DEFINITIONS) ? JSON.parse(File.read(DEFINITIONS)) : {}
        end

        def alias_map(section_defs)
          return {} unless section_defs.is_a?(Hash)

          section_defs.each_with_object({}) do |(name, spec), map|
            next unless spec.is_a?(Hash) && spec['aliases'].is_a?(Array)

            spec['aliases'].each { |a| map[a] = name if a.is_a?(String) }
          end
        end

        def fold_node(node, warnings, source)
          return unless node.is_a?(Hash)

          aliases = node['type'].is_a?(String) ? aliases_for(node['type']) : aliases_for('common')
          node.keys.each do |key|
            canonical = aliases[key]
            next unless canonical

            value = node.delete(key)
            if node.key?(canonical)
              warnings << "#{source ? "[#{source}] " : ''}[id=#{node['id'] || node['type']}] " \
                          "'#{key}' is an alias of '#{canonical}' and both are set — keeping '#{canonical}', dropping '#{key}'"
            else
              node[canonical] = value
            end
          end
          CHILD_KEYS.each do |k|
            case node[k]
            when Array then node[k].each { |c| fold_node(c, warnings, source) }
            when Hash then fold_node(node[k], warnings, source)
            end
          end
          return unless node['sections'].is_a?(Array)

          node['sections'].each do |section|
            next unless section.is_a?(Hash)

            SECTION_NODE_KEYS.each { |k| fold_node(section[k], warnings, source) if section[k].is_a?(Hash) }
          end
        end
      end
    end
  end
end
