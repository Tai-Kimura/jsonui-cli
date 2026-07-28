# frozen_string_literal: true

module SjuiTools
  module SwiftUI
    # Bounds every emitted section function's size:
    #
    #   depth — HARD. Brace nesting per function (decl-relative, string
    #           literals and // comments stripped) must be <= MAX_DEPTH.
    #           Braces are the metric because ViewBuilder blocks are what
    #           nest the generic type; indentation over-reads (multi-line
    #           call arguments are indented far past their structural level)
    #           and modifier parens close on their own line.
    #   lines — SOFT. Split toward MAX_LINES whenever a safe cut exists;
    #           never contort for it (user ruling 2026-07-28).
    #
    # Section boundaries are AnyView-ERASED. An opaque `some View` result is
    # transparent to runtime type-metadata instantiation — the composed type
    # of the screen keeps its full depth through any number of function
    # boundaries, which is how an already-extracted 881-line section0() still
    # exhausted the 1MB device stack (the simulator's 8MB hides it). Only
    # value-level erasure (AnyView, a non-generic struct) truncates the
    # recursion. Placement is STRUCTURAL — every boundary, unconditionally —
    # never measurement-conditional, so an edit near a threshold cannot flip
    # AnyView on an unrelated sibling and change its transition/diffing
    # identity between two builds.
    #
    # Cutting is scope-aware. Enclosures classify as:
    #   :container  — a View constructor's parameterless trailing closure or
    #                 a responsiveN wrapper. Free cut zone.
    #   :anyview    — a multi-line AnyView( argument span. Its interior is a
    #                 View expression by construction and the slot is already
    #                 erased, so extraction there costs nothing.
    #   :expr       — other multi-line paren/bracket spans (config inits,
    #                 argument lists, tuple arrays). Not statement positions
    #                 themselves, but not binding either.
    #   :scope      — a ViewBuilder scope that BINDS NAMES: ForEach/content
    #                 closures with parameters, if / if-let blocks, plus
    #                 line-level `let` bindings. A cut below one is allowed
    #                 when every bound name the segment references has a
    #                 KNOWN Swift type — the extracted function takes them as
    #                 parameters. An unknown-typed reference forbids the cut.
    #   :imperative — action/modifier closures (`Button(action: {`,
    #                 `.onAppear {`), guard/switch/loops. NEVER cut inside.
    #
    # The known-type tables mirror the converters' exact emitted spellings
    # (collection_converter.rb, table_converter.rb): the emit site is the
    # single source of these names, so the tables live next to a spec that
    # pins them against the converters.
    #
    # The pass loop is monotone and guarded by strict progress; a violating
    # function with no safe cut is recorded as a WAIVER and reported, never
    # silently shipped — silent fall-through is exactly how an 881-line body
    # survived the previous splitter. Names are assigned only at emission,
    # in document order, so regeneration is a pure function of the input.
    class SectionBounder
      MAX_DEPTH = 5
      MAX_LINES = 250
      # Two depth lines: the acceptance gate measures a function BODY's brace
      # peak (the consumer's measure_view_depth.py), so BODY_DEPTH_HARD is
      # the real bound; BODY_DEPTH_MAX is one stricter and drives cutting,
      # buying margin — "one modifier away from the limit" is the disease
      # this exists to cure. A body stuck between the two is accepted
      # silently; only a body over the HARD bound earns a waiver warning.
      BODY_DEPTH_MAX = MAX_DEPTH - 1
      BODY_DEPTH_HARD = MAX_DEPTH
      BODY_LINES_MAX = MAX_LINES - 2

      # Closure parameter lists the converters emit, with their Swift types.
      # :unknown forbids cuts below when the name is referenced.
      #   - cellIndex/cellData: collection_converter enumerated cells
      #   - sectionIndex/section: dynamic-sections fallback
      #   - cell: IdentifiedCellItem ForEach
      #   - index, data: the reconfigured().map closure — `data` SHADOWS the
      #     struct's @Binding var data, so it must stay unknown
      #   - item: table_converter, element type never spelled
      FOREACH_PARAM_TYPES = {
        %w[cellIndex cellData] => { 'cellIndex' => 'Int', 'cellData' => '[String: Any]' },
        %w[sectionIndex section] => { 'sectionIndex' => 'Int', 'section' => 'CollectionDataSection' },
        %w[cell] => { 'cell' => 'IdentifiedCellItem' },
        %w[index data] => { 'index' => 'Int', 'data' => :unknown },
        %w[index] => { 'index' => 'Int' },
        %w[scrollProxy] => { 'scrollProxy' => 'ScrollViewProxy' },
        %w[item] => { 'item' => :unknown },
      }.freeze

      # Line-level `let NAME = ...` bindings the collection emission uses.
      LOCAL_TYPES = {
        'section' => 'CollectionDataSection',
        'cellsData' => '[[String: Any]]',
        'items' => '[IdentifiedCellItem]',
      }.freeze

      Waiver = Struct.new(:function, :depth, :lines, :reason)

      # A placeholder stands where an extracted child is called.
      #   prefix/suffix — text around the call (slot spelling preserved)
      #   params        — [[name, type], ...] passed through the boundary
      Placeholder = Struct.new(:chunk, :prefix, :suffix, :params)

      # One future function: ordered code lines / placeholders, plus the
      # typed environment it inherits (its own parameters).
      class Chunk
        attr_reader :items
        attr_accessor :env

        def initialize(items, env = {})
          @items = items
          @env = env
        end

        # Every pass rewrites items wholesale; the measurement cache rides
        # on that. Without it, find_violating_chunk re-measured EVERY chunk
        # of the tree on EVERY loop iteration — O(cuts x tree lines), which
        # cost seconds per large screen (2.1s for one 2.5k-line file,
        # measured; 7s on an efficiency core).
        def items=(new_items)
          @items = new_items
          @measure = nil
        end

        def cached_measure
          @measure ||= yield
        end

        def placeholders
          @items.select { |i| i.is_a?(Placeholder) }
        end
      end

      Frame = Struct.new(:kind, :delim, :open_index, :bindings)

      attr_reader :waivers

      def initialize
        @waivers = []
        # Item Strings survive across rounds untouched (cuts REPLACE ranges,
        # they never mutate a line), so noise-stripping and brace counts are
        # memoized by object identity. frames_per_item + measure walk every
        # line once per round; without this the same regex work re-ran
        # hundreds of times per large screen.
        @line_cache = {}.compare_by_identity
      end

      def line_info(line)
        @line_cache[line] ||= begin
          code = self.class.strip_noise(line)
          {
            code: code,
            stripped: code.strip,
            opens_brace: code.count('{'),
            closes_brace: code.count('}'),
          }
        end
      end

      # Splits `body_code` (a dedented multi-line String) until every
      # resulting function satisfies the bounds, then emits:
      #   [root_call_line, function_texts_joined]
      def bound(body_code, root_name: 'section0')
        root = Chunk.new(body_code.split("\n"))
        stabilize(root, root_name)
        [call_expression(root, 'section0').sub('section0', root_name), emit(root, root_name)]
      end

      # Bounds a pre-extracted child body (WeightedStack root child) and
      # returns just the emitted functions for it.
      def bound_child(body_code, name)
        root = Chunk.new(body_code.split("\n"))
        stabilize(root, name)
        emit(root, name)
      end

      # ---- measurement (mirrors the consumer's measure_view_depth.py:
      # braces only, strings stripped) --------------------------------------

      def self.strip_noise(line)
        out = +''
        in_string = false
        i = 0
        while i < line.length
          ch = line[i]
          if in_string
            if ch == '\\'
              i += 2
              next
            end
            in_string = false if ch == '"'
          elsif ch == '"'
            in_string = true
          elsif ch == '/' && line[i + 1] == '/'
            break
          else
            out << ch
          end
          i += 1
        end
        out
      end

      def self.max_brace_depth(lines)
        depth = 0
        peak = 0
        lines.each do |line|
          code = strip_noise(line)
          code.each_char do |ch|
            case ch
            when '{'
              depth += 1
              peak = depth if depth > peak
            when '}'
              depth -= 1
            end
          end
        end
        peak
      end

      private

      # ---- the pass loop ---------------------------------------------------

      def stabilize(root, root_name)
        guard = 0
        loop do
          guard += 1
          raise 'SectionBounder failed to stabilize (guard tripped)' if guard > 10_000

          chunk = find_violating_chunk(root)
          break unless chunk

          before = measure(chunk)
          progressed = try_passes(chunk)
          next if progressed && strictly_reduced?(before, measure(chunk))

          if before[0] > BODY_DEPTH_HARD || before[1] > BODY_LINES_MAX
            @waivers << Waiver.new(
              function_label(root, chunk, root_name),
              before[0], before[1],
              progressed ? 'cut made no progress' : 'no safe cut point'
            )
          end
          mark_waived(chunk)
        end
      end

      def find_violating_chunk(root)
        each_chunk(root) do |chunk|
          next if waived?(chunk)
          depth, lines = measure(chunk)
          return chunk if depth > BODY_DEPTH_MAX || lines > BODY_LINES_MAX
        end
        nil
      end

      def each_chunk(chunk, &block)
        block.call(chunk)
        chunk.placeholders.each { |ph| each_chunk(ph.chunk, &block) }
        nil
      end

      def measure(chunk)
        chunk.cached_measure do
          depth = 0
          peak = 0
          count = 0
          chunk.items.each do |item|
            count += 1
            next if item.is_a?(Placeholder) # call sites are brace-flat

            info = line_info(item)
            # Character order matters for the peak: `} else {` must close
            # before it reopens (opens-first overcounts by one), while
            # `VStack { }` must still register its momentary +1.
            info[:code].each_char do |ch|
              case ch
              when '{'
                depth += 1
                peak = depth if depth > peak
              when '}'
                depth -= 1
              end
            end
          end
          [peak, count]
        end
      end

      # Placeholders render as their (balanced, single-line) call sites.
      def rendered_lines(chunk)
        chunk.items.map do |item|
          if item.is_a?(Placeholder)
            "#{item.prefix}AnyView(__section__())#{item.suffix}"
          else
            item
          end
        end
      end

      def strictly_reduced?(before, after)
        b = [excess(before[0], BODY_DEPTH_MAX), excess(before[1], BODY_LINES_MAX)]
        a = [excess(after[0], BODY_DEPTH_MAX), excess(after[1], BODY_LINES_MAX)]
        (a <=> b) == -1 || (a == b && after[1] < before[1])
      end

      def excess(value, bound)
        value > bound ? value - bound : 0
      end

      def waived?(chunk)
        chunk.instance_variable_get(:@waived)
      end

      def mark_waived(chunk)
        chunk.instance_variable_set(:@waived, true)
      end

      def function_label(root, chunk, root_name)
        index = 0
        each_chunk(root) do |c|
          return "#{root_name}(+#{index})" if c.equal?(chunk)
          index += 1
        end
        root_name
      end

      def try_passes(chunk)
        depth, = measure(chunk)
        # One frame analysis per round, shared by every pass — recomputing
        # it per pass tripled the dominant cost on large screens.
        frames = frames_per_item(chunk)
        if depth > BODY_DEPTH_MAX
          # Depth violation: erase existing AnyView slots first (free), then
          # pack brace levels with a chain cut — per-child extraction would
          # peel one level per function and produce a wrapper chain of
          # near-empty sections, each an extra erased boundary at runtime.
          # When no container cut exists (the collection skeleton is scopes
          # all the way down), lift a whole `if` statement instead.
          pass_anyview_slots(chunk, frames) ||
            pass_chain_cut(chunk, frames) ||
            pass_if_block(chunk, frames) ||
            pass_container_children(chunk, frames)
        else
          # Lines-only violation: distribute children; chain cuts last.
          pass_anyview_slots(chunk, frames) ||
            pass_container_children(chunk, frames) ||
            pass_chain_cut(chunk, frames) ||
            pass_if_block(chunk, frames)
        end
      end

      # ---- scope analysis --------------------------------------------------

      KEYWORDS_IMPERATIVE = %w[guard for while switch repeat do case default return].freeze

      def frames_per_item(chunk)
        items = chunk.items
        stack = []
        per_item = []
        items.each_with_index do |item, idx|
          per_item << stack.dup
          next if item.is_a?(Placeholder) # call sites open and bind nothing

          info = line_info(item)
          code = info[:code]
          stripped = info[:stripped]

          # Line-level let bindings join the innermost frame's bindings so
          # later segments inside the same scope see them.
          if (m = stripped.match(/\A(?:if\s+)?let\s+(\w+)\s*=/))
            name = m[1]
            target = stack.last
            target.bindings[name] = LOCAL_TYPES.fetch(name, :unknown) if target
          end

          closes = [[code.count('}') - code.count('{'), '{'],
                    [code.count(')') - code.count('('), '('],
                    [code.count(']') - code.count('['), '[']]
          closes.each do |count, delim|
            next unless count.positive?
            count.times do
              pop_at = stack.rindex { |f| f.delim == delim }
              stack.delete_at(pop_at) if pop_at
            end
          end

          opens_brace = code.count('{') - code.count('}')
          opens_paren = code.count('(') - code.count(')')
          opens_bracket = code.count('[') - code.count(']')

          if opens_brace.positive?
            kind, bindings = classify_brace(stripped)
            opens_brace.times { |n| stack << Frame.new(kind, '{', idx, n.zero? ? bindings : {}) }
          end
          if opens_paren.positive?
            kind = code.rstrip.end_with?('AnyView(') ? :anyview : :expr
            opens_paren.times { stack << Frame.new(kind, '(', idx, {}) }
          end
          if opens_bracket.positive?
            opens_bracket.times { stack << Frame.new(:expr, '[', idx, {}) }
          end
        end
        per_item
      end

      def classify_brace(stripped)
        return [:imperative, {}] unless stripped.end_with?('{') || stripped.end_with?('in')

        # Closure with a parameter list: `... { a, b in`
        if (m = stripped.match(/\{\s*([\w\s,()]+?)\s+in\z/))
          names = m[1].split(',').map(&:strip).reject(&:empty?)
          typed = FOREACH_PARAM_TYPES.fetch(names) do
            names.to_h { |n| [n, :unknown] }
          end
          return [:scope, typed.dup]
        end
        return [:imperative, {}] unless stripped.end_with?('{')

        head = stripped[0...-1].rstrip
        # `} else {` / `} else if ... {` continue a ViewBuilder conditional.
        return [:scope, {}] if head.match?(/\A\}?\s*else(\s+if\b.*)?\z/)
        # A punctuation-only transition into a trailing closure — `) {` after
        # a multi-line initializer (DrawerContent(...args...) {) or `}) {`
        # after a multi-line action closure (Button's label slot). In emitted
        # code these trailing closures are always ViewBuilder content.
        return [:container, {}] if head.match?(/\A[\}\)\],]*\z/)
        # Modifier closures whose argument IS ViewBuilder content: their
        # interiors are legal statement positions. Everything else dot-braced
        # (.onAppear, .onTapGesture, ...) is imperative.
        if stripped.start_with?('.')
          viewbuilder_modifier = stripped.match?(
            /\A\.(overlay|background|mask|safeAreaInset|sheet|fullScreenCover|popover|confirmationDialog|contextMenu|toolbar|swipeActions|refreshable)\b/
          )
          return viewbuilder_modifier && head.count('(') == head.count(')') ? [:container, {}] : [:imperative, {}]
        end

        first_word = head[/\A[A-Za-z_][A-Za-z0-9_]*/]
        return [:imperative, {}] if first_word.nil?
        if first_word == 'if'
          bindings = {}
          if (m = head.match(/\Aif\s+let\s+(\w+)\s*=/))
            bindings[m[1]] = LOCAL_TYPES.fetch(m[1], :unknown)
          end
          return [:scope, bindings]
        end
        return [:imperative, {}] if KEYWORDS_IMPERATIVE.include?(first_word) ||
                                    %w[let var else].include?(first_word)
        return [:container, {}] if head.match?(/\Aresponsive\d+\z/)
        # A container line's parens are balanced once the trailing brace is
        # removed; an action/content closure argument leaves one open
        # (`Button(action: {`).
        return [:imperative, {}] unless head.count('(') == head.count(')')
        return [:imperative, {}] unless first_word[0].match?(/[A-Z]/)

        [:container, {}]
      end

      # A statement cut may sit under containers, AnyView spans and binding
      # scopes — never under an imperative closure, and never under an :expr
      # span (its content is a single expression, handled by slot cuts).
      def statement_cuttable?(frames)
        frames.all? { |f| %i[container anyview scope].include?(f.kind) }
      end

      def slot_cuttable?(frames)
        frames.none? { |f| f.kind == :imperative }
      end

      # Bound names visible at a position: chunk env + scope frames, in
      # introduction order (outermost first).
      def visible_bindings(chunk, frames)
        merged = chunk.env.dup
        frames.each { |f| merged.merge!(f.bindings) }
        merged
      end

      # Parameters an extracted segment needs: every visible bound name it
      # references. Returns nil when a referenced name has no known type.
      # References are scanned on RAW text: a name used only inside a string
      # interpolation ("\(cellData["x"])") is still a real reference.
      def required_params(chunk, frames, segment_items)
        bindings = visible_bindings(chunk, frames)
        return [] if bindings.empty?

        text = segment_items.map do |i|
          i.is_a?(Placeholder) ? i.params.map(&:first).join(' ') : i
        end.join("\n")

        params = []
        bindings.each do |name, type|
          next unless text.match?(/\b#{Regexp.escape(name)}\b/)
          return nil if type == :unknown
          params << [name, type]
        end
        params
      end

      # ---- pass 1: extract multi-line AnyView( interiors -------------------

      def pass_anyview_slots(chunk, frames)
        items = chunk.items

        items.each_with_index do |item, idx|
          next if item.is_a?(Placeholder)
          code = self.class.strip_noise(item)
          next unless code.rstrip.end_with?('AnyView(')
          next unless slot_cuttable?(frames[idx])

          close_idx = matching_close(items, idx, '(', ')')
          next unless close_idx && close_idx > idx + 1

          interior = items[(idx + 1)...close_idx]
          next if interior.size < 2

          params = required_params(chunk, frames[idx], interior)
          next if params.nil?

          open_line = item
          prefix = open_line[0...open_line.rindex('AnyView(')]
          close_line = items[close_idx].strip
          suffix = close_line[1..] || ''

          child = Chunk.new(dedent(interior), params.to_h)
          ph = Placeholder.new(child, prefix, suffix, params)
          chunk.items = items[0...idx] + [ph] + items[(close_idx + 1)..]
          return true
        end
        false
      end

      # ---- pass 2: extract a container's multi-line children ---------------

      def pass_container_children(chunk, frames)
        items = chunk.items

        best = nil
        items.each_with_index do |item, idx|
          next if item.is_a?(Placeholder)
          stripped = self.class.strip_noise(item).strip
          kind, = classify_brace(stripped)
          next unless kind == :container
          next unless statement_cuttable?(frames[idx])

          children = direct_children(items, idx)
          next unless children && children.count { |c| c[:multi] } >= 1 && children.size > 1

          span = children.sum { |c| c[:end] - c[:start] + 1 }
          best = { open: idx, children: children, span: span } if best.nil? || span > best[:span]
        end
        return false unless best

        open_frames = frames[best[:open]]
        rebuilt = items[0..best[:open]]
        replaced = false
        best[:children].each do |child|
          seg = items[child[:start]..child[:end]]
          params = child[:multi] ? required_params(chunk, open_frames, seg) : []
          if child[:multi] && params
            child_chunk = Chunk.new(dedent(seg), params.to_h)
            indent = leading_indent(items[child[:start]])
            rebuilt << Placeholder.new(child_chunk, indent, '', params)
            replaced = true
          else
            rebuilt.concat(seg)
          end
        end
        last_child_end = best[:children].last[:end]
        rebuilt.concat(items[(last_child_end + 1)..])
        return false unless replaced

        chunk.items = rebuilt
        true
      end

      def direct_children(items, open_idx)
        children = []
        depth = 1
        paren = 0
        current = nil
        i = open_idx + 1
        while i < items.size
          item = items[i]
          line = item.is_a?(Placeholder) ? 'AnyView(x())' : item
          code = self.class.strip_noise(line)
          stripped = code.strip

          # A closer line (`}` of a modifier's trailing closure returning to
          # child level, `)` of an argument list) is never a child boundary.
          if depth == 1 && paren.zero? && !stripped.empty? &&
             !stripped.start_with?('.') && !stripped.match?(/\A[\}\)\]]/)
            if current
              children << { start: current, end: prev_nonblank(items, i - 1, current), multi: nil }
            end
            current = i
          end

          d = code.count('{') - code.count('}')
          if depth == 1
            paren += code.count('(') - code.count(')')
            paren = 0 if paren.negative?
          end
          depth += d
          if depth <= 0
            children << { start: current, end: prev_nonblank(items, i - 1, current), multi: nil } if current
            break
          end
          i += 1
        end
        return nil if children.size < 2

        children.each { |c| c[:multi] = c[:end] > c[:start] }
        children
      end

      def prev_nonblank(items, from, floor)
        idx = from
        idx -= 1 while idx > floor && items[idx].is_a?(String) && items[idx].strip.empty?
        idx
      end

      # ---- pass 3: cut a single-child chain --------------------------------

      def pass_chain_cut(chunk, frames)
        items = chunk.items

        deep_idx = deepest_line_index(items)
        return false unless deep_idx

        # Enclosing statement-position frames of the deep point, outermost
        # first. Cut as DEEP as the budget allows so a spine packs several
        # levels per function instead of one.
        enclosing = frames[deep_idx].each_with_index.select do |f, _|
          %i[container scope].include?(f.kind)
        end
        return false if enclosing.empty?

        target_index = [BODY_DEPTH_MAX - 1, enclosing.size - 1].min
        target, = enclosing[target_index]
        # Extracting the chunk's own first line reproduces the chunk verbatim;
        # step one frame inward instead, or give up if there is nowhere to go.
        if target.open_index.zero?
          return false if target_index >= enclosing.size - 1
          target, = enclosing[target_index + 1]
        end
        # A :scope opening (if-let, ForEach closure) is not extractable as a
        # unit through a View-function boundary, and a punctuation-only
        # opening (`) {` of a multi-line initializer) has no self-contained
        # first line to carry into a function; cut at the nearest WHOLE
        # container at or inside the budget instead.
        unless chain_target?(items, target)
          inner = enclosing.drop(target_index).find do |f, _|
            chain_target?(items, f) && !f.open_index.zero?
          end
          return false unless inner
          target, = inner
        end
        open_idx = target.open_index
        return false unless statement_cuttable?(frames[open_idx])

        close_idx = matching_close(items, open_idx, '{', '}')
        return false unless close_idx

        tail = extend_modifier_tail(items, close_idx)
        seg = items[open_idx..tail]
        return false if seg.size >= items.size

        params = required_params(chunk, frames[open_idx], seg)
        return false if params.nil?

        child = Chunk.new(dedent(seg), params.to_h)
        indent = leading_indent(items[open_idx])
        ph = Placeholder.new(child, indent, '', params)
        chunk.items = items[0...open_idx] + [ph] + items[(tail + 1)..]
        true
      end

      # ---- pass 4: lift a whole `if` statement -----------------------------
      #
      # ViewBuilder supports `if` as a statement, so an entire if/else chain
      # can move into its own @ViewBuilder function. This is the only cut
      # that reduces the collection skeleton (wrapper > multi-line init >
      # if > if-let > ForEach), which contains no container to chain-cut.
      def pass_if_block(chunk, frames)
        items = chunk.items

        deep_idx = deepest_line_index(items)
        return false unless deep_idx

        # Outermost enclosing `if` frame of the deep point.
        target = frames[deep_idx].find do |f|
          next false unless f.kind == :scope
          line = items[f.open_index]
          line.is_a?(String) && self.class.strip_noise(line).strip.start_with?('if ')
        end
        return false unless target
        return false unless statement_cuttable?(frames[target.open_index])

        open_idx = target.open_index
        # matching_close walks the whole if/else chain: `} else {` is
        # brace-balanced, so the count returns to zero only at the final `}`.
        close_idx = matching_close(items, open_idx, '{', '}')
        return false unless close_idx

        seg = items[open_idx..close_idx]
        return false if seg.size >= items.size

        params = required_params(chunk, frames[open_idx], seg)
        return false if params.nil?

        child = Chunk.new(dedent(seg), params.to_h)
        indent = leading_indent(items[open_idx])
        ph = Placeholder.new(child, indent, '', params)
        chunk.items = items[0...open_idx] + [ph] + items[(close_idx + 1)..]
        true
      end

      def deepest_line_index(items)
        depth = 0
        peak = 0
        peak_idx = nil
        items.each_with_index do |item, idx|
          line = item.is_a?(Placeholder) ? 'AnyView(x())' : item
          code = self.class.strip_noise(line)
          code.each_char do |ch|
            case ch
            when '{'
              depth += 1
              if depth > peak
                peak = depth
                peak_idx = idx
              end
            when '}'
              depth -= 1
            end
          end
        end
        peak_idx
      end

      # ---- shared helpers --------------------------------------------------

      # A chain cut carries a container's OPENING LINE into the extracted
      # function, so that line must be self-contained: a real container
      # opening — not a `) {` transition out of a multi-line initializer, and
      # not a `.overlay {` modifier closure (a leading-dot expression is not
      # a statement on its own).
      def chain_target?(items, frame)
        return false unless frame.kind == :container
        line = items[frame.open_index]
        return false unless line.is_a?(String)
        stripped = self.class.strip_noise(line).strip
        !stripped.match?(/\A[\}\)\],.]/)
      end

      # Extends `from` (a subtree's closing line) over the trailing modifier
      # chain, INCLUDING any multi-line spans a modifier opens
      # (`.overlay(alignment: .topLeading) { ... }`, multi-line `.overlay(`
      # arguments). Stopping at the first non-dot line severed such spans
      # mid-closure and emitted a dangling `{` — a non-compiling parent.
      def extend_modifier_tail(items, from)
        tail = from
        while tail + 1 < items.size
          nxt = items[tail + 1]
          break unless nxt.is_a?(String) && nxt.strip.start_with?('.')

          code = self.class.strip_noise(nxt)
          brace = code.count('{') - code.count('}')
          paren = code.count('(') - code.count(')')
          if brace.positive? || paren.positive?
            span_end = balanced_end(items, tail + 1)
            return tail unless span_end # unbalanced to EOF: keep the chain intact
            tail = span_end
          else
            tail += 1
          end
        end
        tail
      end

      # Line index at which the braces+parens opened at `start` return to
      # balance, or nil when they never do.
      def balanced_end(items, start)
        depth = 0
        (start...items.size).each do |i|
          item = items[i]
          line = item.is_a?(Placeholder) ? 'AnyView(x())' : item
          code = self.class.strip_noise(line)
          depth += code.count('{') - code.count('}') + code.count('(') - code.count(')')
          return i if i > start && depth <= 0
          return i if i == start && depth.zero?
        end
        nil
      end

      def matching_close(items, open_idx, open_ch, close_ch)
        open_line = items[open_idx]
        code = self.class.strip_noise(open_line.is_a?(Placeholder) ? '' : open_line)
        depth = code.count(open_ch) - code.count(close_ch)
        return nil unless depth.positive?

        ((open_idx + 1)...items.size).each do |i|
          item = items[i]
          line = item.is_a?(Placeholder) ? 'AnyView(x())' : item
          c = self.class.strip_noise(line)
          depth += c.count(open_ch) - c.count(close_ch)
          return i if depth <= 0
        end
        nil
      end

      def leading_indent(item)
        return '' if item.is_a?(Placeholder)
        item[/\A\s*/]
      end

      def dedent(items)
        strings = items.select { |i| i.is_a?(String) && !i.strip.empty? }
        min = strings.map { |l| l[/\A\s*/].length }.min || 0
        items.map do |i|
          if i.is_a?(String)
            i.strip.empty? ? '' : i[min..]
          else
            i.prefix = i.prefix[min..] || '' if i.prefix.length >= min
            i
          end
        end
      end

      # ---- emission --------------------------------------------------------

      def call_expression(chunk, name)
        args = chunk.env.map { |n, _| "#{n}: #{n}" }.join(', ')
        "AnyView(#{name}(#{args}))"
      end

      # Depth-first, document-order naming: child i of `name` is `name_i`.
      def emit(root, root_name)
        out = []
        emit_chunk(root, root_name, out)
        out.join("\n")
      end

      def emit_chunk(chunk, name, out)
        child_names = {}
        chunk.placeholders.each_with_index do |ph, i|
          child_names[ph] = "#{name}_#{i}"
        end

        signature = chunk.env.map { |n, t| "#{n}: #{t}" }.join(', ')
        out << "    @ViewBuilder private func #{name}(#{signature}) -> some View {"
        chunk.items.each do |item|
          if item.is_a?(Placeholder)
            args = item.params.map { |n, _| "#{n}: #{n}" }.join(', ')
            call = "AnyView(#{child_names[item]}(#{args}))"
            out << "        #{item.prefix}#{call}#{item.suffix}".rstrip
          elsif item.strip.empty?
            out << ''
          else
            out << "        #{item.rstrip}"
          end
        end
        out << '    }'
        out << ''

        chunk.placeholders.each do |ph|
          emit_chunk(ph.chunk, child_names[ph], out)
        end
      end
    end
  end
end
