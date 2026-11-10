# frozen_string_literal: true

require 'json'
require_relative 'style_loader'

module RjuiTools
  module React
    # Where an included layout's root sits in the layout that includes it.
    #
    # sjui and kjui expand an include before they convert it, so the partial's
    # root is converted as a child of the including container and takes what
    # that container hands its children: the overlay placement
    # (`absolute bottom-0 left-0`, the stacked grid cell), the axis a
    # `matchParent` height is on, the size half of `distribution`, and the
    # wrapContent cap. rjui draws an include as a call of the partial's own
    # component, generated once and with no container above its root, so all
    # of it was lost there (ticket rjui-include-root-relative-placement-
    # dropped: an `alignLeft` / `alignBottom` root drew at the top left of an
    # overlay, a `matchParent` height in a row grew sideways).
    #
    # The include call site converts the partial's root twice, with and
    # without what its container hands it, and passes the difference of the
    # two static class lists as `jsonuiPlace={{ add, drop }}`; the partial's
    # root applies it to its own class (`jsonuiPlaceClass`). The run-time
    # parts of the class (`${...}`, the partial's own data) stay in the
    # partial. A call site whose container hands the root nothing that changes
    # it passes nothing.
    module IncludePlace
      # What a container adds to a child's json for the child to read
      # (ViewConverter#convert_children, BaseConverter#convert_children /
      # #with_parent_bounds). Held to the converters by
      # spec/react/include_place_spec.rb.
      CONTEXT_KEYS = %w[
        _overlay _parent_orientation _parent_distribution
        _parent_bounded_width _parent_bounded_height
      ].freeze

      PROP = 'jsonuiPlace'
      HELPER = 'jsonuiPlaceClass'

      module_function

      # The layouts directory the include paths are read against.
      def layouts_dir(config)
        config['_layouts_dir'] || (config['layouts_directory'] && File.expand_path(config['layouts_directory']))
      end

      # The include nodes from *include_node* down to the element its partial
      # draws (a partial whose root is itself an include is followed), and
      # that element: [[include, ...], root]. nil when a partial cannot be read
      # or the includes go round. Read once per file in a build.
      def resolve(include_node, config)
        dir = layouts_dir(config)
        return nil unless dir && include_node.is_a?(Hash) && include_node['include'].is_a?(String)

        cache = (config['_partial_root_cache'] ||= {})
        chain = [include_node]
        loop do
          include_path = chain.last['include']
          return nil if chain[0...-1].any? { |n| n['include'] == include_path }

          tree = cache.fetch(include_path) do
            path = File.join(dir, "#{include_path}.json")
            cache[include_path] =
              if File.file?(path)
                begin
                  StyleLoader.load_and_merge(JSON.parse(File.read(path, encoding: 'UTF-8')))
                rescue JSON::ParserError
                  nil
                end
              end
          end
          return nil unless tree.is_a?(Hash)
          return [chain, tree] unless tree['include'].is_a?(String)

          chain << tree
        end
      end

      # The element a container lays out for *child*: the child, or for an
      # include, the root its partial draws.
      def laid_out(child, config)
        return child unless child.is_a?(Hash) && child['include'].is_a?(String)

        resolved = resolve(child, config)
        resolved ? resolved[1] : child
      end

      # The JavaScript expression of the DOM id an include's root carries in
      # the including layout (the id the partial's root writes, under the
      # prefixes of the includes above it — design U8), or nil when an include
      # on the way has a bound id. With the prefix off, the include's literal
      # id is the root's (the component's `id` prop).
      def root_dom_id_js(include_node, config)
        resolved = resolve(include_node, config)
        return nil unless resolved

        chain, root = resolved
        root_id = root['id']
        return nil unless literal_id?(root_id)

        unless config['_include_id_prefix']
          outer = chain.first['id']
          return nil if outer && !literal_id?(outer)

          return js_string(outer || root_id)
        end

        prefix = 'idPrefix'
        chain.each do |node|
          id = node['id']
          next if id.nil?
          return nil unless literal_id?(id)

          prefix = "jsonuiIncludePrefix(#{prefix}, #{js_string(id)})"
        end
        "jsonuiIncludeId(#{prefix}, #{js_string(root_id)})"
      end

      # The ids a layout declares itself: its elements' literal ids, not the
      # ids inside a layout it includes (another component) and not an
      # include node's id (a prefix, not an element).
      def declared_ids(node, ids = [])
        case node
        when Hash
          return ids if node['include']

          ids << node['id'] if literal_id?(node['id'])
          kids = node['child'] || node['children']
          declared_ids(kids, ids) if kids
        when Array
          node.each { |n| declared_ids(n, ids) }
        end
        ids
      end

      def literal_id?(id)
        id.is_a?(String) && !id.empty? && !id.include?('@{')
      end

      # The component name an include of *stem* calls (IncludeConverter).
      def component_name(stem)
        stem.split('_').map(&:capitalize).join
      end

      # The static class tokens of the first element in *jsx* — the run-time
      # `${...}` parts of a template literal left out; [] for a className
      # that is another expression, or none.
      def root_class_tokens(jsx)
        attr = locate_class_attr(jsx)
        return [] unless attr

        static_tokens(attr[:value])
      end

      # *jsx* with the first element's class put through jsonuiPlaceClass,
      # or — when that element is a call of a partial that takes the prop
      # (an included layout whose root is itself an include) — the prop
      # handed on. *forward_components* names those partials' components.
      def apply(jsx, forward_components = [])
        tag = locate_first_tag(jsx)
        return jsx unless tag

        attr = locate_class_attr(jsx)
        if attr
          wrapped = "{#{HELPER}(#{expression_of(attr[:value])}, #{PROP})}"
          return jsx[0...attr[:value_start]] + wrapped + jsx[attr[:value_end]..]
        end

        insert_at = tag[:name_end]
        if forward_components.include?(tag[:name])
          jsx.dup.insert(insert_at, " #{PROP}={#{PROP}}")
        elsif tag[:name].match?(/\A[a-z]/)
          jsx.dup.insert(insert_at, " className={#{HELPER}(\"\", #{PROP})}")
        else
          jsx
        end
      end

      # The `{{ add: "...", drop: "..." }}` value, or nil when both are empty.
      def prop_value(inside, placed)
        add = placed - inside
        drop = inside - placed
        return nil if add.empty? && drop.empty?

        pairs = []
        pairs << "add: #{js_string(add.join(' '))}" unless add.empty?
        pairs << "drop: #{js_string(drop.join(' '))}" unless drop.empty?
        "{{ #{pairs.join(', ')} }}"
      end

      def js_string(text)
        "\"#{text.gsub('\\') { '\\\\' }.gsub('"', '\\"')}\""
      end

      # --- scanning ---------------------------------------------------------

      def static_tokens(value)
        if value.start_with?('"')
          value[1...-1].split(/\s+/).reject(&:empty?)
        elsif value.start_with?('{')
          inner = value[1...-1].strip
          return [] unless inner.start_with?('`') && inner.end_with?('`')

          template_static_text(inner).split(/\s+/).reject(&:empty?)
        else
          []
        end
      end

      def expression_of(value)
        if value.start_with?('"')
          js_string(value[1...-1])
        else
          value[1...-1].strip
        end
      end

      # The text of a template literal with its `${...}` parts taken out.
      def template_static_text(literal)
        out = +''
        i = 1
        while i < literal.length - 1
          if literal[i] == '\\'
            out << literal[i, 2]
            i += 2
          elsif literal[i] == '$' && literal[i + 1] == '{'
            i = skip_braces(literal, i + 1)
            out << ' '
          else
            out << literal[i]
            i += 1
          end
        end
        out
      end

      # The first element tag: { start:, name:, name_end:, end: }.
      def locate_first_tag(jsx)
        start = jsx.index(/<[A-Za-z]/)
        return nil unless start

        name = jsx[start + 1..][/\A[A-Za-z][\w.]*/]
        name_end = start + 1 + name.length
        i = name_end
        attrs = []
        loop do
          i += 1 while i < jsx.length && jsx[i].match?(/\s/)
          return nil if i >= jsx.length
          break if jsx[i] == '>' || jsx[i, 2] == '/>'

          if jsx[i] == '{'
            i = skip_braces(jsx, i)
            next
          end
          attr_name = jsx[i..][/\A[\w:.-]+/]
          return nil unless attr_name

          i += attr_name.length
          unless jsx[i] == '='
            attrs << { name: attr_name, value: nil }
            next
          end

          i += 1
          value_start = i
          if jsx[i] == '"'
            close = jsx.index('"', i + 1)
            return nil unless close

            i = close + 1
          elsif jsx[i] == '{'
            i = skip_braces(jsx, i)
          else
            return nil
          end
          attrs << { name: attr_name, value: jsx[value_start...i], value_start: value_start, value_end: i }
        end
        { start: start, name: name, name_end: name_end, end: i, attrs: attrs }
      end

      def locate_class_attr(jsx)
        tag = locate_first_tag(jsx)
        return nil unless tag

        tag[:attrs].find { |a| a[:name] == 'className' && a[:value] }
      end

      # The index just past the `}` that closes the `{` at *open*, reading
      # string and template literals (and the `${...}` inside the latter).
      def skip_braces(text, open)
        depth = 0
        i = open
        while i < text.length
          c = text[i]
          case c
          when '{'
            depth += 1
            i += 1
          when '}'
            depth -= 1
            i += 1
            return i if depth.zero?
          when '"', "'"
            i = skip_quoted(text, i, c)
          when '`'
            i = skip_template(text, i)
          else
            i += 1
          end
        end
        i
      end

      def skip_quoted(text, open, quote)
        i = open + 1
        while i < text.length
          return i + 1 if text[i] == quote
          i += text[i] == '\\' ? 2 : 1
        end
        i
      end

      def skip_template(text, open)
        i = open + 1
        while i < text.length
          c = text[i]
          return i + 1 if c == '`'

          if c == '\\'
            i += 2
          elsif c == '$' && text[i + 1] == '{'
            i = skip_braces(text, i + 1)
          else
            i += 1
          end
        end
        i
      end
    end
  end
end
