# frozen_string_literal: true

require_relative 'include_expander'

module RjuiTools
  module React
    # What an include call site hands the included component: each member of
    # its Data type, read off the including layout's data under the name the
    # include-expanded tree gives it (ruling 2026-10-02 — an include draws the
    # including layout's data, with the include node's maps over it; ticket
    # rjui-include-does-not-read-the-screens-data).
    #
    # A member's including name follows the expansion: a declared name takes
    # the include's id prefix; a bound name is the map's binding when a map
    # sets it, and takes the prefix otherwise; a handler derived from a bound
    # name (`on<Name>Change`, `set<Name>`) is derived again from the including
    # name. A member a map sets is the map's, and is not paired here.
    #
    # The members are the Data type's (data_model_generator.rb): its declared
    # data, the handlers and values its controls bind, and — UNDECLARED — the
    # names it binds without declaring them, which a partial may read off the
    # including layout's declaration as on sjui / kjui (ticket
    # rjui-partial-binding-an-undeclared-name-does-not-compile).
    module IncludedMembers
      module_function

      # [[member, including name], ...] in the Data type's order.
      def pairs(tree, prefix, map)
        map = map.transform_keys(&:to_s)
        gen = DataModelGenerator.allocate
        spell = ->(name) { prefix ? IncludeExpander.combine_with_prefix(prefix, name) : name }
        including = lambda do |name|
          next spell.call(name) unless map.key?(name)

          map[name].is_a?(String) ? map[name][/\A@\{([A-Za-z_][A-Za-z0-9_]*)\}\z/, 1] : nil
        end
        out = []
        add = lambda do |member, name|
          return if name.nil? || map.key?(member) || out.any? { |m, _| m == member }

          out << [member, name]
        end

        IncludeExpander.declared_names(tree).each { |name| add.call(name, spell.call(name)) }
        values = gen.send(:extract_value_bindings, tree)
        text_fields = gen.send(:extract_text_field_bindings, tree).to_a
        values.each_key { |name| add.call(name, including.call(name)) }
        gen.send(:extract_onclick_actions, tree).each { |name| add.call(name, including.call(name)) }
        text_fields.each do |name|
          outer = including.call(name)
          add.call("on#{gen.send(:capitalize_first, name)}Change", outer && "on#{gen.send(:capitalize_first, outer)}Change")
        end
        values.each do |name, info|
          next if text_fields.include?(name)

          outer = including.call(name)
          add.call(gen.send(:value_binding_handler_name, name, info), outer && gen.send(:value_binding_handler_name, outer, info))
        end
        gen.send(:extract_event_handler_bindings, tree).each_key { |name| add.call(name, including.call(name)) }
        undeclared(tree).each { |name| add.call(name, including.call(name)) }
        # The members the Data walk synthesizes (a TabView's tab state, its
        # setter, its tabs' Data) — synthesized on the expanded tree too, so
        # under the same name there, the include's id or not.
        synthesized(tree, gen).each { |name| add.call(name, name) }
        out
      end

      def synthesized(node, gen, names = [])
        case node
        when Hash
          gen.send(:tab_view_members, node).each { |m| names << m['name'] unless names.include?(m['name']) }
          child = node['child'] || node['children']
          (child.is_a?(Array) ? child : [child].compact).each { |c| synthesized(c, gen, names) }
        when Array
          node.each { |c| synthesized(c, gen, names) }
        end
        names
      end

      # The names a layout binds that its Data type has no other member for.
      def undeclared(tree)
        gen = DataModelGenerator.allocate
        members = IncludeExpander.declared_names(tree) +
                  gen.send(:extract_value_bindings, tree).keys +
                  gen.send(:extract_onclick_actions, tree).to_a +
                  gen.send(:extract_event_handler_bindings, tree).keys
        IncludeExpander.bound_names(tree) - members
      end
    end
  end
end

require_relative 'data_model_generator'
