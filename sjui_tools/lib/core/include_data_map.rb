# frozen_string_literal: true

module JsonUIShared
  # What an included layout reads (ruling 2026-10-02; the SSoT's
  # common/include, common/data and common/shared_data): the including
  # layout's data, as it is, with the include node's maps over it —
  # `shared_data` first, then `data`. A map's key is a name the included
  # layout binds; its value is a literal, or a binding read in the including
  # layout's scope. The same answer on every face and in dynamic mode
  # (KotlinJsonUI's DynamicIncludeComponent already read it so).
  #
  # Until jsonui-cli 1.9.6 sjui / kjui codegen dropped an object map (they
  # merged only an array `data`, as declarations), and rjui handed the
  # included component the maps alone — none of the including layout's data
  # (tickets native-include-object-map-is-ignored,
  # rjui-include-does-not-read-the-screens-data).
  module IncludeDataMap
    module_function

    BINDING = /@\{([^}]+)\}/.freeze

    # The include node's maps, merged: { name => value }. An array `data`
    # is not a map — it declares data, and the expanders merge it as before.
    def of(include_node)
      return {} unless include_node.is_a?(Hash)

      %w[shared_data data].each_with_object({}) do |key, map|
        map.merge!(include_node[key]) if include_node[key].is_a?(Hash)
      end
    end

    # Rewrites the expanded included tree in place: every `@{name}` whose
    # name is a map key reads the map's value instead. `spelled` turns a map
    # key into the name the expanded tree binds (the include's id prefix,
    # when there is one, is already on every binding). A whole-string
    # binding takes the value as it is (a Bool stays a Bool); one inside a
    # longer string takes a binding as written and a literal as its text.
    # Dotted names (`@{item.x}`, `@{this.x}`) are never a map key.
    def apply!(tree, map, spelled = ->(name) { name })
      return tree if map.empty?

      by_name = map.each_with_object({}) { |(key, value), out| out[spelled.call(key.to_s)] = value }
      rewrite(tree, by_name)
    end

    def rewrite(node, by_name)
      case node
      when Hash
        node.each_key do |key|
          # A nested include's own maps are read in THIS layout's scope, so
          # they are rewritten too; only declarations are not bindings.
          next if key == 'data' && node[key].is_a?(Array)

          node[key] = rewrite(node[key], by_name)
        end
        node
      when Array
        node.map! { |item| rewrite(item, by_name) }
      when String
        whole = node.match(/\A@\{([^}]+)\}\z/)
        return by_name[whole[1]] if whole && by_name.key?(whole[1])

        node.gsub(BINDING) do |match|
          name = Regexp.last_match(1)
          next match unless by_name.key?(name)

          value = by_name[name]
          value.is_a?(String) ? value : value.to_s
        end
      else
        node
      end
    end
  end
end
