# frozen_string_literal: true

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
