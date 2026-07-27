# frozen_string_literal: true

require 'set'

module KjuiTools
  module Compose
    module Helpers
      # SectionExtractor splits an oversized `@Composable` body into file-scope
      # `@Composable private fun SectionN(data, viewModel)` helpers, mirroring
      # what sjui's `view_updater.rb` does for SwiftUI `@ViewBuilder private
      # func sectionN()` extraction.
      #
      # Why: Kotlin / Compose codegen emits the entire body of a screen as a
      # single lambda chain inside `MypageGeneratedView`. Each container
      # lambda compiles to its own JVM method, and the JVM has a hard 65,536
      # byte / method bytecode limit. Large layouts with `responsive` (which
      # duplicates the body across an `if/else` for size-class branches)
      # cross that limit and `Method too large` blocks the entire app build.
      #
      # How: post-process the static body code string. Find the largest
      # PascalCase / lazy-DSL container with multiple children. Lift each
      # child block whose first word is a real Composable (PascalCase) and
      # which neither carries a scope-bound modifier at its opening nor
      # references a sibling `val`/`var` local from the same parent scope.
      # The lifted block becomes a `@Composable private fun SectionN(data,
      # viewModel)` registered with the caller; the call site shrinks to a
      # single `SectionN(data, viewModel)` line. Recurse into lifted bodies
      # so cell-sized sections stay below the JVM ceiling.
      #
      # Restrictions (mirrors the data-closure-scope-leak guard from the
      # earlier file-scope responsive-helper attempt):
      # - LazyListScope DSL (`item`, `items`, `stickyHeader`, ...) cannot be
      #   lifted as a chunk — it must stay inside its `LazyColumn` / `LazyRow`
      #   parent. We recurse INTO `item { ... }` instead.
      # - Scope-bound modifiers (`.weight(`, `.align(`, ...) at the chunk's
      #   opening signal that the chunk relies on its parent's
      #   RowScope/ColumnScope/BoxScope receiver. Recurse instead of lift.
      # - Containers whose body declares `val`/`var` siblings (e.g.
      #   `val textFieldState_x = rememberTextFieldState(...)` next to a
      #   `CustomTextField(state = textFieldState_x, ...)` call) cannot be
      #   split — lifting any child would either lose the declaration's
      #   scope or strand the declaration without consumers. Skip the whole
      #   candidate container.
      module SectionExtractor
        # Sjui's view_updater.rb uses LINE_THRESHOLD = 100; Compose's modifier
        # chains are slightly denser, but 100 also picks up `responsive`
        # if/else bodies (the primary trigger) so we match.
        DEFAULT_LINE_THRESHOLD = 100

        # Depth bound (2026-07-28 depth-bounding batch, shared with sjui's
        # SectionBounder): the acceptance gate measures a function BODY's
        # brace peak (item's measure_view_depth.py) at <= 5. TARGET is one
        # stricter and drives cutting — margin is the point, "one modifier
        # from the limit" is the disease. Bodies stuck between TARGET and
        # HARD are accepted silently; over HARD (or over the line bound with
        # no safe cut) earns a waiver so nothing oversized ships silently.
        TARGET_BODY_DEPTH = 4
        HARD_BODY_DEPTH = 5
        HARD_BODY_LINES = 250

        Waiver = Struct.new(:function, :depth, :lines)

        # True when a scope-bound modifier inside `code` needs a receiver
        # from OUTSIDE it: no receiver-PROVIDING opener (a PascalCase
        # container lambda, a lazy-DSL block, or a content/lazyContent named
        # lambda) sits on its enclosing-brace stack within the code. Depth
        # alone is the wrong test in both directions — the previous
        # substring-anywhere guard poisoned every list screen (an inner
        # `.align(` whose Row lives inside the chunk froze it at depth 9+),
        # while a plain depth check misses `.weight(` under an `if {`
        # (control flow adds depth but provides no scope, and lifting that
        # without a receiver does not compile).
        def self.scope_bound_needs_outer_receiver?(code)
          provider_stack = []
          code.each_line do |raw|
            line = raw.strip
            next if line.empty?
            if provider_stack.none? && SCOPE_BOUND_MODIFIER_PREFIXES.any? { |m| line.include?(m) }
              return true
            end
            opens = line.count('{')
            closes = line.count('}')
            net = opens - closes
            if net.positive?
              provides = line.match?(/\A[A-Z]\w*\s*\(/) || line.match?(/\A\)\s*\{\z/) ||
                         line.match?(/\A(?:item|items|itemsIndexed|stickyHeader)\b/) ||
                         line.match?(/\b(?:content|lazyContent)\s*=\s*\{/)
              net.times { provider_stack << provides }
            elsif net.negative?
              (-net).times { provider_stack.pop }
            end
          end
          false
        end

        # Brace nesting peak with string literals and // comments stripped.
        # Kotlin template braces (`${...}`) sit inside the string literal, so
        # the quote scan drops them along with the rest of the string.
        def self.body_depth(code)
          depth = 0
          peak = 0
          code.each_line do |line|
            cleaned = +''
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
                cleaned << ch
              end
              i += 1
            end
            cleaned.each_char do |c|
              case c
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

        LAZY_DSL_KEYWORDS = %w[item items itemsIndexed stickyHeader stickyHeaders].freeze

        # Identifier patterns that kjui's Collection / Lazy emit binds in the
        # immediately-enclosing scope:
        #   - `items(N, key = ...) { cellIndex -> ... }` — lambda parameter
        #   - `itemsIndexed(...) { idx, item -> ... }` — lambda parameters
        #   - `val cellData0 = section0?.cells` — outer LazyListScope local
        #   - `val currentCellData = cellData0.data[cellIndex]` — items-lambda
        #     scope local that references cellIndex
        #   - `val cellViewModel = viewModel(key = "...")` — items-lambda local
        #   - `val cellId = ...` — same scope
        # Any chunk that references one of these names *without declaring it
        # itself* is reaching across a lambda boundary that a file-scope
        # `@Composable private fun SectionN(data, viewModel)` cannot bridge.
        # Refuse the lift; recurse only.
        OUTER_SCOPE_LOCAL_PATTERN = /\b(?:cell[A-Z]\w*|section\d+|currentCellData|enrichedData\d+)\b/

        # Cell-scope locals kjui's collection emission binds, with the Kotlin
        # types the emit itself spells. A chain segment referencing one of
        # these (declared OUTSIDE it) can still lift — the lifted function
        # takes them as parameters. Anything not in this table refuses.
        KNOWN_CELL_PARAM_TYPES = {
          'cellIndex' => 'Int',
          'index' => 'Int',
          'cellId' => 'String',
          'currentCellData' => 'Map<String, Any>',
          # kjui cell loops bind `item` to a cells.data row:
          'item' => 'Map<String, Any>',
          # Wrapper-scope emissions (compose_builder's fixed spellings):
          'modifier' => 'Modifier',
          'edges' => 'List<String>',
          'safeAreaConfig' => 'com.kotlinjsonui.dynamic.SafeAreaConfig',
          # `?.let { section -> }` / `?.let { cellData -> }` collection
          # unwraps — non-optional by construction:
          'section' => 'com.kotlinjsonui.data.CollectionDataSection',
          'cellData' => 'com.kotlinjsonui.data.CollectionDataSection.CellData',
        }.freeze

        # `enrichedDataN` = CellIdGenerator.enrichCellIds(...) -> List<Map<String, Any>>
        ENRICHED_DATA_PATTERN = /\Aenriched[A-Z]\w*\z|\AenrichedData\d+\z/

        def self.known_cell_param_type(name)
          return KNOWN_CELL_PARAM_TYPES[name] if KNOWN_CELL_PARAM_TYPES.key?(name)
          return 'List<Map<String, Any>>' if name.match?(/\AenrichedData\d+\z/)
          # Collection model locals (library types, FQN so no import wiring):
          return 'com.kotlinjsonui.data.CollectionDataSection?' if name.match?(/\Asection\d+\z/)
          return 'com.kotlinjsonui.data.CollectionDataSection.CellData?' if name.match?(/\AcellData\d+\z/)
          nil
        end

        # Modifier substrings that need a parent scope receiver to compile.
        # `.weight(` requires RowScope/ColumnScope; `.align(` requires the
        # corresponding scope; `.fillParentMaxSize(` / `.animateItemPlacement(`
        # / `.animateItem(` (Compose 1.7+) require LazyItemScope. We match
        # these as substrings anywhere in the chunk body — see `cannot_lift?`
        # for the rationale.
        SCOPE_BOUND_MODIFIER_PREFIXES = %w[
          .weight(
          .align(
          .alignBy(
          .alignByBaseline(
          .matchParentSize(
          .fillParentMaxSize(
          .fillParentMaxWidth(
          .fillParentMaxHeight(
          .animateItemPlacement(
          .animateItem(
        ].freeze

        # Returns [new_body, [function_string, ...]]. When the body is shorter
        # than `line_threshold` or no splittable container is found, the body
        # is returned unchanged with an empty function list.
        def self.extract(body, view_name:, data_type:, viewmodel_type:, line_threshold: DEFAULT_LINE_THRESHOLD, enclosing_depth: 0)
          state = State.new(
            view_name: view_name,
            data_type: data_type,
            viewmodel_type: viewmodel_type,
            threshold: line_threshold
          )
          new_body = state.process(body, "Section", env: { 'modifier' => 'Modifier' })

          # The caller wraps this body in fixed chrome (the Dynamic-mode
          # Box + if/else adds 2 brace levels). When body + chrome would
          # break the gate, lift the WHOLE body into one function — the
          # wrapper then carries a single call and the body's own depth is
          # already bounded (or waived) by the pass above.
          if enclosing_depth.positive? &&
             body_depth(new_body) + enclosing_depth > HARD_BODY_DEPTH
            new_body = state.lift_whole_body(new_body)
          end

          # Second-chance passes. stabilize() can fixpoint order-dependently:
          # a cut inside a big body may only become available after sibling
          # extractions have thinned it, and the outer loop has already moved
          # on. Re-running the pass on each still-violating FUNCTION (with
          # its own parameters as env) converges further — measured on a real
          # 1,400-line screen: first pass left a depth-8 function that a
          # second pass cut to 3.
          3.times do
            changed = false
            state.functions.each_with_index do |fn, i|
              parsed = parse_function(fn)
              next unless parsed
              body = parsed[:body]
              next unless body_depth(body) > HARD_BODY_DEPTH ||
                          body.lines.size > HARD_BODY_LINES
              extra_env = parsed[:params].reject { |n, _| %w[data viewModel].include?(n) }.to_h
              reprocessed = state.process(
                body, "#{parsed[:name]}_", env: extra_env
              )
              next if reprocessed == body
              state.functions[i] = fn.sub(body) { reprocessed }
              changed = true
            end
            break unless changed
          end

          [new_body, state.functions, state.waivers(new_body)]
        end

        # Splits a build_function() emission back into name / typed params /
        # body (the text between the signature's ") {" and the final "}").
        def self.parse_function(fn)
          lines = fn.lines.map(&:chomp)
          open_idx = lines.index { |l| l.strip == ') {' }
          return nil unless open_idx
          name = fn[/private fun (?:[\w.]+\.)?(\w+)\(/, 1]
          return nil unless name
          params = lines[1...open_idx].map do |l|
            m = l.strip.match(/\A(\w+):\s*(.+?),?\z/)
            m && [m[1], m[2]]
          end.compact
          body = lines[(open_idx + 1)...-1].join("\n")
          { name: name, params: params, body: body }
        end

        class State
          attr_reader :functions

          # Lifts the entire (already-processed) body into one Section whose
          # call replaces it. `modifier` is the wrapper's parameter.
          def lift_whole_body(body)
            name = next_name('Section')
            params = real_reference?(body, 'modifier') ? [['modifier', 'Modifier']] : []
            @functions << build_function(name, body, extra_params: params)
            args = (%w[data viewModel] + params.map(&:first)).join(', ')
            "#{name}(#{args})"
          end

          # Post-hoc audit: the final body plus every emitted function is
          # measured; anything over the HARD bounds is a waiver the caller
          # must surface. Silent fall-through is exactly how 1,327-line
          # sections survived the trigger-based extractor.
          def waivers(final_body)
            out = []
            body_depth = SectionExtractor.body_depth(final_body)
            body_lines = final_body.lines.size
            if body_depth > SectionExtractor::HARD_BODY_DEPTH ||
               body_lines > SectionExtractor::HARD_BODY_LINES
              out << SectionExtractor::Waiver.new("#{@view_name} (main body)", body_depth, body_lines)
            end
            @functions.each do |fn|
              name = fn[/private fun (?:[\w.]+\.)?(\w+)/, 1] || 'Section?'
              depth = SectionExtractor.body_depth(fn) - 1 # the fun's own brace
              lines = fn.lines.size
              if depth > SectionExtractor::HARD_BODY_DEPTH || lines > SectionExtractor::HARD_BODY_LINES
                out << SectionExtractor::Waiver.new(name, depth, lines)
              end
            end
            out
          end

          def initialize(view_name:, data_type:, viewmodel_type:, threshold:)
            @view_name = view_name
            @data_type = data_type
            @viewmodel_type = viewmodel_type
            @threshold = threshold
            @functions = []
            @top_level_counter = 0
            # name => receiver FQN prefix, for sections emitted as scope
            # extensions; used to keep their call sites inside a matching
            # receiver context.
            @scoped_names = {}
          end

          # Recursively split `code` if it is over the threshold and a
          # splittable container exists. `prefix` is the base name used for
          # extracted children (`Section`, then `Section0_`, `Section0_1_`,
          # ...). At the outermost call we iterate until no more candidates
          # remain, so parallel structures like the two branches of a
          # `responsive` `if/else` both get their children lifted.
          def process(code, prefix, env: {})
            return code unless code.lines.size > @threshold ||
                               SectionExtractor.body_depth(code) > SectionExtractor::TARGET_BODY_DEPTH

            previous = nil
            current = code
            while previous != current
              previous = current
              current = process_once(current, prefix, env)
            end
            current
          end

          private

          def process_once(code, prefix, env)
            # Responsive `if (…) { … } else { … }` gates first: each branch
            # duplicates the subtree, so branch extraction halves the inline
            # body per gate and is the primary defense against the JVM 64KB /
            # ART JIT method-size ceilings (a large responsive screen used to
            # keep ~8k lines inline in the single ScrollView item lambda —
            # one View away from `Method too large`).
            gated = extract_if_else_branches(code, prefix, env)
            return gated if gated

            result = find_splittable_children(code)
            # Depth violations with no multi-child container (a single-child
            # spine, or scopes all the way down) fall through to a chain cut.
            # The same fallback runs when a container WAS found but every
            # child refused to lift — a no-change children pass must not
            # block the chain, or a depth-10 body fixpoints untouched.
            unless result
              return chain_cut_or_self(code, prefix, env)
            end

            header_lines, child_codes, trailer_lines = result
            child_indent = detect_child_indent(child_codes.first)

            new_body_lines = header_lines.dup
            all_lines = code.lines.map(&:chomp)
            child_codes.each do |child_code|
              name = next_name(prefix)
              child_pos = all_lines.index(child_code.lines.first&.chomp) || header_lines.size
              child_env = visible_decl_env(all_lines, child_pos, env)

              if cannot_lift?(child_code) || references_env?(child_code, child_env)
                # Recurse into the chunk so its descendants can still be
                # lifted. The recursion replaces oversized children inside
                # the chunk with section calls; the chunk itself stays in
                # place (scope-bound or lazy-DSL constraint). It carries the
                # declaration-visibility env so nested cuts can type-pass or
                # refuse names declared in THIS chunk.
                lifted = process(child_code, "#{name}_", env: child_env)
                lifted.lines.each { |l| new_body_lines << l.chomp }
              else
                lifted_body = process(child_code, "#{name}_")
                @functions << build_function(name, lifted_body)
                new_body_lines << "#{child_indent}#{name}(data, viewModel)"
              end
            end

            new_body_lines.concat(trailer_lines)
            rebuilt = new_body_lines.join("\n")
            return chain_cut_or_self(code, prefix, env) if rebuilt == code
            rebuilt
          end

          def chain_cut_or_self(code, prefix, env)
            if SectionExtractor.body_depth(code) > SectionExtractor::TARGET_BODY_DEPTH ||
               code.lines.size > SectionExtractor::HARD_BODY_LINES
              cut = chain_cut(code, prefix, env)
              return cut if cut
            end
            code
          end

          # Fully-qualified receiver types for scope-bound branch extraction.
          # FQNs sidestep the import machinery entirely.
          SCOPE_RECEIVERS = {
            'Row' => 'androidx.compose.foundation.layout.RowScope.',
            'Column' => 'androidx.compose.foundation.layout.ColumnScope.',
            'Box' => 'androidx.compose.foundation.layout.BoxScope.',
            'item' => 'androidx.compose.foundation.lazy.LazyItemScope.',
            'items' => 'androidx.compose.foundation.lazy.LazyItemScope.',
            'itemsIndexed' => 'androidx.compose.foundation.lazy.LazyItemScope.'
          }.freeze

          # Finds the first `if (…) {` whose branch bodies are large enough to
          # be worth lifting, and replaces each branch body with a
          # `SectionN(data, viewModel)` call whose definition is a file-scope
          # @Composable — as a scope-receiver extension (FQ receiver type)
          # when the branch content needs the enclosing container's scope.
          # Returns the rewritten code, or nil when no gate qualifies.
          def extract_if_else_branches(code, prefix, env)
            lines = code.lines.map(&:chomp)
            depth = 0

            lines.each_with_index do |line, idx|
              stripped = line.strip
              opens = stripped.count('{')
              closes = stripped.count('}')

              if stripped =~ /\Aif\s*\(/ && opens > closes
                segments = if_else_segments(lines, idx)
                if segments
                  branch_line_total = segments[:branches].sum { |b| b[:end_idx] - b[:start] + 1 }
                  if branch_line_total > @threshold
                    rewritten = lift_branches(lines, segments, prefix, env)
                    return rewritten if rewritten
                  end
                end
              end

              depth += opens - closes
            end

            nil
          end

          # Maps an `if` opener at `if_idx` to its then/else branch ranges:
          #   { branches: [{start:, end_idx:}, ...], boundaries: [if_idx, else_idx..., close_idx] }
          # Handles `} else {` and `} else if (…) {` chains. Returns nil when
          # the shape is unrecognized.
          def if_else_segments(lines, if_idx)
            branches = []
            boundaries = [if_idx]
            depth = 0
            branch_start = if_idx + 1

            (if_idx...lines.size).each do |i|
              stripped = lines[i].strip

              if i == if_idx
                depth += stripped.count('{') - stripped.count('}')
                next
              end

              # Branch boundaries must be detected BEFORE the generic depth
              # update: `} else {` is a net-zero line (one close, one open),
              # so depth alone never returns to 0 there and the whole
              # then+else span would fuse into a single (brace-unbalanced)
              # branch.
              if depth == 1 && stripped.start_with?('}')
                if stripped =~ /\A\}\s*else(\s+if\s*\(.*)?\s*\{\z/
                  branches << { start: branch_start, end_idx: i - 1 }
                  boundaries << i
                  branch_start = i + 1
                  next # net-zero line: depth stays 1 inside the new branch
                elsif stripped == '}'
                  branches << { start: branch_start, end_idx: i - 1 }
                  boundaries << i
                  return { branches: branches, boundaries: boundaries }
                end
                # Any other `}…` line at depth 1 (e.g. `})`) means this is
                # not the simple gate shape we handle — fall through to the
                # generic update and ultimately refuse.
              end

              depth += stripped.count('{') - stripped.count('}')
              return nil if depth <= 0
            end

            nil
          end

          # Lifts each branch body of the gate into its own Section function.
          # Returns rewritten code, or nil when any branch cannot be lifted
          # (all-or-nothing keeps the boundary bookkeeping simple: a partial
          # lift would still shrink the body on the next process_once pass).
          def lift_branches(lines, segments, prefix, env)
            receiver = enclosing_receiver(lines, segments[:boundaries].first)

            branch_bodies = segments[:branches].map do |b|
              lines[b[:start]..b[:end_idx]].join("\n")
            end

            # Refuse when a branch reaches into cell-lambda locals it doesn't
            # declare, or needs a scope receiver we couldn't identify.
            gate_env = visible_decl_env(lines, segments[:boundaries].first, env)
            branch_bodies.each do |body|
              return nil if references_env?(body, gate_env)
              return nil if references_outer_scope_local?(body)
              return nil if dangling_lazy_dsl?(body)
              needs_scope = SectionExtractor.scope_bound_needs_outer_receiver?(body)
              # Calls to receiver-extension sections require the SAME receiver
              # on the lifted function; mixed or unknown receivers can't be
              # bridged by a single extension signature.
              scoped = scoped_call_names(body).map { |n| @scoped_names[n] }.uniq
              return nil if scoped.size > 1
              needs_scope ||= scoped.any?
              return nil if scoped.any? && scoped.first != receiver
              return nil if needs_scope && receiver.nil?
            end

            calls = branch_bodies.map do |body|
              name = next_name(prefix)
              lifted_body = process(body, "#{name}_")
              needs_scope = SectionExtractor.scope_bound_needs_outer_receiver?(body)
              needs_scope ||= scoped_call_names(lifted_body).any?
              fn_receiver = needs_scope ? receiver : nil
              @functions << build_function(name, lifted_body, receiver: fn_receiver)
              @scoped_names[name] = fn_receiver if fn_receiver
              name
            end

            indent = lines[segments[:boundaries].first].match(/\A(\s*)/)[1]
            out = lines[0...segments[:boundaries].first]
            segments[:branches].each_with_index do |_b, k|
              out << lines[segments[:boundaries][k]] # `if (…) {` / `} else {`
              out << "#{indent}    #{calls[k]}(data, viewModel)"
            end
            out << lines[segments[:boundaries].last] # final `}`
            out.concat(lines[(segments[:boundaries].last + 1)..] || [])
            out.join("\n")
          end

          # Walks upward from the gate opener to the nearest enclosing block
          # opener and maps its keyword to a scope-receiver FQN. Returns nil
          # when the enclosing scope is unknown (e.g. LazyColumn's own DSL
          # block, where an extracted @Composable couldn't be called anyway).
          def enclosing_receiver(lines, gate_idx)
            depth = 0
            (gate_idx - 1).downto(0) do |i|
              stripped = lines[i].strip
              next if stripped.empty?
              depth += stripped.count('}') - stripped.count('{')
              if depth < 0
                keyword = container_keyword(lines, i)
                # Control flow is receiver-TRANSPARENT: `if (...) {` around a
                # grid does not change which scope the grid's `.weight(`
                # resolves against. Keep walking to the real container.
                if %w[if else when].include?(keyword)
                  depth = 0
                  next
                end
                return SCOPE_RECEIVERS[keyword]
              end
            end
            nil
          end

          # `Section`-prefixed top-level lifts share a global counter so
          # successive `process_once` iterations (one per parallel sibling
          # container) don't reuse `Section0` and collide. Nested prefixes
          # like `Section0_` carry their own per-call counters built from
          # the suffix after the underscore — those don't collide because
          # they're scoped to a single lifted chunk.
          def next_name(prefix)
            if prefix == "Section"
              name = "Section#{@top_level_counter}"
              @top_level_counter += 1
              name
            else
              key = "@_counter_#{prefix.gsub(/[^A-Za-z0-9]/, '_')}"
              n = instance_variable_get(key) || 0
              instance_variable_set(key, n + 1)
              "#{prefix}#{n}"
            end
          end

          # Cuts a single-child spine at a container enclosing the deepest
          # point, packing brace levels up to the budget into the parent —
          # the move `find_splittable_children` cannot make (it needs >1
          # children). Mirrors sjui SectionBounder's chain cut. Returns the
          # rewritten code, or nil when no enclosing container survives the
          # scope guards.
          def chain_cut(code, prefix, env)
            lines = code.lines.map(&:chomp)

            # Deepest line + the stack of container opens enclosing it.
            depth = 0
            peak = 0
            deep_idx = nil
            stack = []
            deep_stack = nil
            lines.each_with_index do |line, idx|
              stripped = line.strip
              opens = stripped.count('{')
              closes = stripped.count('}')
              net = opens - closes
              if net.positive?
                net.times { stack << idx }
              elsif net.negative?
                (-net).times { stack.pop }
              end
              depth += net
              if depth > peak
                peak = depth
                deep_idx = idx
                deep_stack = stack.dup
              end
            end
            return nil unless deep_idx && deep_stack

            # Containers only (PascalCase Composables), never lazy-DSL blocks
            # or lambda scopes — the lifted segment's first line must be a
            # complete composable statement.
            # NOTE: kjui runs under the host's system Ruby (2.6) in consumer
            # projects — Enumerable#filter_map (2.7+) is unavailable there,
            # and a NoMethodError here is swallowed by the per-file rescue as
            # a "Failed to process" that silently leaves the PREVIOUS
            # generated file on disk. map+compact only.
            candidates = deep_stack.each_with_index.map do |open_idx, order|
              keyword = container_keyword(lines, open_idx)
              if keyword && (keyword[0] =~ /[A-Z]/ || keyword == 'key')
                # Multi-line openers (`Column(` ... `) {`) are extractable as
                # a unit: the segment starts at the KEYWORD line, carrying
                # the whole argument list into the lifted function.
                seg_start = container_open_start(lines, open_idx)
                next if seg_start.nil? || seg_start.zero?
                [open_idx, seg_start, order]
              elsif lines[open_idx].strip.match?(/\A(?:lazyContent|content)\s*=\s*\{\z/)
                # A named lambda ARGUMENT (`CollectionStack(..., lazyContent =
                # {`) — the brace belongs to the argument, but the liftable
                # unit is the whole enclosing CALL. Walk back over the open
                # paren to the PascalCase call opener.
                call_start = call_open_start(lines, open_idx)
                next if call_start.nil? || call_start.zero?
                [open_idx, call_start, order]
              end
            end.compact
            return nil if candidates.empty?

            # Cut as deep as the budget allows (parent keeps levels up to
            # TARGET-1), stepping inward past segments the scope guards
            # refuse.
            budget_order = SectionExtractor::TARGET_BODY_DEPTH - 1
            start_at = candidates.index { |_, _, order| order >= budget_order } || (candidates.size - 1)
            # Budget-deep first (packs levels), stepping inward; when every
            # deeper segment is refused (cell-scope locals), step OUTWARD —
            # a shallower segment self-contains the declarations that made
            # the deep ones unliftable.
            ordered = candidates[start_at..] + (start_at.positive? ? candidates[0...start_at].reverse : [])
            ordered.each do |open_idx, seg_start, _order|
              close_idx = segment_close_index(lines, seg_start, open_idx)
              next unless close_idx
              # Pull immediately-preceding sibling `val` declarations the
              # segment references into it (the chain-cut form of
              # merge_val_chunks): `val section0 = ...` / `val cellData0 =
              # ...` right above a grid travel with it, making the segment
              # self-contained instead of refused.
              seg_start = merge_leading_vals(lines, seg_start, close_idx)
              next if close_idx - seg_start + 1 >= lines.size # no progress

              seg_lines = lines[seg_start..close_idx]
              seg = seg_lines.join("\n")
              next if dangling_lazy_dsl?(seg)

              # Cell-scope locals declared outside the segment become typed
              # parameters when their type is spellable; otherwise refuse.
              extra_params = cell_params_for(lines, seg_start, seg, env)
              next if extra_params.nil?

              scoped = scoped_call_names(seg).map { |n| @scoped_names[n] }.uniq
              next if scoped.size > 1
              needs_scope = SectionExtractor.scope_bound_needs_outer_receiver?(seg)
              needs_scope ||= scoped.any?
              receiver = enclosing_receiver(lines, seg_start)
              next if scoped.any? && scoped.first != receiver
              next if needs_scope && receiver.nil?

              name = next_name(prefix)
              child_env = extra_params.to_h
              lifted_body = process(dedent_code(seg), "#{name}_", env: child_env)
              fn_receiver = needs_scope ? receiver : nil
              @functions << build_function(name, lifted_body, receiver: fn_receiver, extra_params: extra_params)
              @scoped_names[name] = fn_receiver if fn_receiver

              indent = lines[seg_start].match(/\A(\s*)/)[1]
              args = (['data', 'viewModel'] + extra_params.map(&:first)).join(', ')
              out = lines[0...seg_start]
              out << "#{indent}#{name}(#{args})"
              out.concat(lines[(close_idx + 1)..] || [])
              return out.join("\n")
            end
            nil
          end

          # Widens `seg_start` upward over contiguous sibling `val NAME = ...`
          # lines (and their wrapped continuations) that declare names the
          # segment references. Iterates because vals reference each other
          # (`enrichedData0` uses `cellData0` uses `section0`).
          def merge_leading_vals(lines, seg_start, close_idx)
            loop do
              seg = lines[seg_start..close_idx].join("\n")
              declared = seg.scan(/\b(?:val|var)\s+(\w+)\b/).flatten.to_set
              idx = seg_start - 1
              idx -= 1 while idx >= 0 && lines[idx].strip.empty?
              break if idx.negative?
              m = lines[idx].strip.match(/\Aval\s+(\w+)[\s:=]/)
              break unless m
              break if declared.include?(m[1])
              break unless seg.match?(/\b#{Regexp.escape(m[1])}\b/)
              seg_start = idx
            end
            seg_start
          end

          # Typed parameters for chunk-local names the segment references but
          # does not declare. FAIL-CLOSED in both directions:
          #   - only names actually DECLARED ABOVE the segment in this chunk
          #     (or the wrapper's `modifier` parameter) may become parameters
          #     — a pattern match against a name that exists nowhere would
          #     emit a call site that does not resolve;
          #   - any above-declared reference whose type is not spellable
          #     refuses the cut — Section4-style extraction of a body using
          #     `modifier`/`edges` without passing them does not compile.
          # Returns [] when self-contained, nil when the cut must be refused.
          def cell_params_for(lines, seg_start, seg, env)
            declared_inside = seg.scan(/\b(?:val|var)\s+(\w+)\b/).flatten.to_set
            seg.scan(/\{\s*(\w+(?:\s*,\s*\w+)*)\s*->/).flatten.each do |params|
              params.split(',').each { |p| declared_inside << p.strip }
            end

            declared_above = []
            lines[0...seg_start].each do |raw|
              l = raw.strip
              l.scan(/\b(?:val|var)\s+(\w+)\b/).flatten.each { |n| declared_above << n }
              l.scan(/\{\s*(\w+(?:\s*,\s*\w+)*)\s*->/).flatten.each do |params|
                params.split(',').each { |p| declared_above << p.strip }
              end
            end
            # Names available as the CURRENT function's own parameters
            # (`modifier` on the wrapper; a lifted section's extra params).
            declared_above.concat(env.keys)

            out = []
            declared_above.uniq.each do |n|
              next if declared_inside.include?(n)
              next unless real_reference?(seg, n)
              type = env[n] || SectionExtractor.known_cell_param_type(n)
              return nil if type.nil?
              out << [n, type]
            end
            out.sort_by(&:first)
          end

          # True when `code` references a name that only exists as a
          # parameter of the CURRENT function (env) — a plain
          # (data, viewModel) lift would strand it.
          def references_env?(code, env)
            env.keys.any? { |n| real_reference?(code, n) }
          end

          # env extended with every declaration visible ABOVE `upto_idx` in
          # this chunk. Values are the spellable type or nil (in scope but
          # untyped — referencing it blocks any lift). This is what an
          # INLINE recursion must carry: its chunk text no longer contains
          # the enclosing declarations, but its call sites still sit in
          # their scope — without this, a nested cut stranded
          # `enrichedData0` references and emitted non-compiling code.
          def visible_decl_env(lines, upto_idx, env)
            merged = env.dup
            lines[0...upto_idx].each do |raw|
              l = raw.strip
              l.scan(/\b(?:val|var)\s+(\w+)\b/).flatten.each do |n|
                merged[n] = SectionExtractor.known_cell_param_type(n) unless merged.key?(n)
              end
              l.scan(/\{\s*(\w+(?:\s*,\s*\w+)*)\s*->/).flatten.each do |params|
                params.split(',').each do |raw_p|
                  n = raw_p.strip
                  merged[n] = SectionExtractor.known_cell_param_type(n) unless merged.key?(n)
                end
              end
            end
            merged
          end

          # A genuine value reference — NOT a named-argument label
          # (`modifier = Modifier.padding(...)`) and not a declaration. In
          # `modifier = modifier` only the RHS occurrence counts, which is
          # exactly the wrapper-root usage that needs the parameter.
          def real_reference?(code, name)
            return false if code.match?(/\b(?:val|var)\s+#{Regexp.escape(name)}\b/)
            code.match?(/\b#{Regexp.escape(name)}\b(?!\s*=[^=])/)
          end

          # First line of the container call whose lambda opens at
          # `open_idx`: the line itself for `Box {`, or the `Column(` line
          # for a multi-line argument list ending in `) {`.
          def container_open_start(lines, open_idx)
            opening = lines[open_idx].strip
            return open_idx if opening =~ /\A\w/

            balance = opening.count(')') - opening.count('(')
            idx = open_idx - 1
            while idx >= 0 && balance.positive?
              s = lines[idx].strip
              balance += s.count(')') - s.count('(')
              return idx if balance <= 0
              idx -= 1
            end
            nil
          end

          # Walks back from a named-lambda-argument opener to the PascalCase
          # call line whose argument list is still open there.
          def call_open_start(lines, open_idx)
            balance = 0
            idx = open_idx
            while idx >= 0
              st = lines[idx].strip
              balance += st.count(')') - st.count('(')
              if balance.negative?
                return st.match?(/\A[A-Z]\w*\s*\(/) ? idx : nil
              end
              idx -= 1
            end
            nil
          end

          # End of the liftable segment starting at `seg_start`: where BOTH
          # the braces and the parens opened since `seg_start` return to
          # balance — for `CollectionStack(args, lazyContent = { ... })` that
          # is the call's closing `)`, one line past the lambda's `}`.
          def segment_close_index(lines, seg_start, open_idx)
            brace = 0
            paren = 0
            (seg_start...lines.size).each do |i|
              st = lines[i].strip
              brace += st.count('{') - st.count('}')
              paren += st.count('(') - st.count(')')
              return i if i >= open_idx && brace <= 0 && paren <= 0
            end
            nil
          end

          # Index of the line where the brace opened on `open_idx` closes.
          def brace_close_index(lines, open_idx)
            depth = 0
            (open_idx...lines.size).each do |i|
              s = lines[i].strip
              depth += s.count('{') - s.count('}')
              return i if i > open_idx && depth <= 0
              return i if i == open_idx && depth.zero? && s.include?('}')
            end
            nil
          end

          # Returns [header_lines, [child_code, ...], trailer_lines] or nil.
          # Picks the splittable container whose children span the most total
          # lines (mirrors sjui's preference for the densest section).
          def find_splittable_children(code)
            lines = code.lines.map(&:chomp)
            abs_depth = 0
            candidates = []

            lines.each_with_index do |line, idx|
              stripped = line.strip
              next if stripped.empty?

              brace_opens = stripped.count('{')
              brace_closes = stripped.count('}')

              if brace_opens > brace_closes
                candidates << { open_idx: idx, depth: abs_depth + 1 }
              end

              abs_depth += brace_opens - brace_closes
            end

            best_result = nil

            candidates.each do |container|
              # Find the call keyword (e.g. `Column`). For multi-line opens
              # where the `{` is on a `) {` line, the keyword lives on the
              # line that opens the matching `(` further up.
              first_word = container_keyword(lines, container[:open_idx])
              next unless splittable_container_keyword?(first_word)

              children = find_children_inside(lines, container[:open_idx], container[:depth])
              next unless children && children.size > 1
              # Pre-merge `val foo = ...` children with subsequent siblings
              # that reference `foo`, so the binding travels with its
              # consumers into any extracted section. kjui codegen emits this
              # pattern in two forms:
              #   - `val resolved_textNNN = Configuration.Font.resolve(...)`
              #     immediately followed by one Text consumer
              #   - `val textFieldState_x = rememberTextFieldState(...)`
              #     followed by one or more LaunchedEffect / CustomTextField
              #     siblings that reference the state
              # The earlier guard (refuse to split any parent whose children
              # include a `val`) was overly broad: in mypage's wrapper
              # Column, 30+ `val resolved_textNNN` siblings blocked the
              # entire section from ever splitting, leaving 800+ lines
              # inline per copy × 4 responsive combinations and re-tripping
              # `Method too large`.
              children = merge_val_chunks(lines, children)
              next unless children.size > 1
              # A container whose children are ALL already-lifted
              # `SectionN(data, viewModel)` calls offers no lift potential.
              # Without this skip, such a container can tie on `total_lines`
              # with deeper unlifted containers and, because we update only
              # on strict-greater, hog the `best_result` slot indefinitely.
              # The outer-loop iteration then sees no change (every child
              # hits the already-lifted `cannot_lift?` guard) and exits
              # before reaching genuinely-unlifted containers (e.g. the
              # opposite branch of a `responsive` if/else).
              next if all_children_already_lifted?(lines, children)

              total_lines = children.sum { |c| c[:end_idx] - c[:start] + 1 }
              if best_result.nil? || total_lines > best_result[:total_lines]
                best_result = {
                  open_idx: container[:open_idx],
                  children: children,
                  total_lines: total_lines
                }
              end
            end

            return nil unless best_result

            header = lines[0..best_result[:open_idx]]
            child_codes = best_result[:children].map do |c|
              lines[c[:start]..c[:end_idx]].join("\n")
            end
            last_end = best_result[:children].last[:end_idx]
            trailer = lines[(last_end + 1)..] || []

            [header, child_codes, trailer]
          end

          def splittable_container_keyword?(word)
            return false unless word
            return true if word[0] =~ /[A-Z]/
            LAZY_DSL_KEYWORDS.include?(word)
          end

          # Returns the identifier that opened the call ending on `open_idx`.
          # For a single-line opener like `Box {`, the keyword is the first
          # word of that line. For multi-line openers where the brace lands
          # on a `) {` line, the keyword sits on the line that contained the
          # matching `(`. We paren-balance backwards until balance returns
          # to zero.
          def container_keyword(lines, open_idx)
            opening = lines[open_idx].strip
            first_word = opening.match(/^(\w+)/)&.[](1)
            return first_word if first_word

            balance = opening.count(')') - opening.count('(')
            idx = open_idx - 1
            while idx >= 0 && balance > 0
              s = lines[idx].strip
              balance += s.count(')') - s.count('(')
              return s.match(/^(\w+)/)&.[](1) if balance <= 0

              idx -= 1
            end
            nil
          end

          # Sjui's same-named function, ported verbatim. Tracks brace and
          # paren depth so multi-line modifier chains (lines starting with
          # `.`) are not mistaken for new child boundaries.
          def find_children_inside(lines, open_line_idx, container_depth)
            children = []
            current_child_start = nil
            brace_depth = container_depth
            paren_depth = 0

            (open_line_idx + 1...lines.size).each do |i|
              stripped = lines[i].strip
              next if stripped.empty?

              brace_opens = stripped.count('{')
              brace_closes = stripped.count('}')
              new_brace_depth = brace_depth + brace_opens - brace_closes

              if new_brace_depth < container_depth
                if current_child_start
                  end_idx = i - 1
                  end_idx -= 1 while end_idx >= current_child_start && lines[end_idx].strip.empty?
                  children << { start: current_child_start, end_idx: end_idx }
                end
                break
              end

              if brace_depth == container_depth && paren_depth == 0 && !stripped.start_with?('.')
                if current_child_start && current_child_start < i
                  end_idx = i - 1
                  end_idx -= 1 while end_idx >= current_child_start && lines[end_idx].strip.empty?
                  children << { start: current_child_start, end_idx: end_idx }
                end
                current_child_start = i
              end

              if brace_depth == container_depth && new_brace_depth == container_depth
                paren_depth += stripped.count('(') - stripped.count(')')
              elsif brace_depth != container_depth && new_brace_depth == container_depth
                paren_depth += stripped.count('(') - stripped.count(')')
              elsif brace_depth == container_depth && new_brace_depth > container_depth
                # `) {` line — close one paren, open a nested brace. Sjui's
                # original three-branch form misses this case and lets a
                # stale paren_depth survive past the nested block, fusing
                # subsequent siblings into one chunk.
                paren_depth += stripped.count('(') - stripped.count(')')
              end

              brace_depth = new_brace_depth
            end

            children.size > 1 ? children : nil
          end

          # If any child block starts with `val` / `var`, lifting siblings
          # could either lose the binding or strand it. Refuse to split the
          # whole parent container in that case.
          def comment_only_chunk?(lines)
            lines.all? do |line|
              s = line.strip
              s.empty? ||
                s.start_with?('//') ||
                s.start_with?('/*') ||
                s.start_with?('*')
            end
          end

          # A lazy-DSL call (`item` / `items` / `itemsIndexed` / `stickyHeader`)
          # is "dangling" when no lazy container OPENED WITHIN THE CHUNK is
          # active at that point — its receiver is the enclosing (out-of-chunk)
          # Lazy*Scope, so lifting the chunk to a file-scope @Composable strips
          # the scope and the DSL no longer resolves (`Unresolved reference
          # 'items'`). A chunk that wraps the DSL in its own LazyColumn /
          # LazyRow / Lazy*Grid / CollectionStack lazyContent is self-contained
          # and fine. Intermediate non-DSL lambdas (`let { … }`) don't break
          # receiver visibility in Kotlin, so "any in-chunk lazy container
          # currently open" is the right containment test.
          def dangling_lazy_dsl?(code)
            depth = 0
            lazy_depths = []
            pending_lazy = false

            code.lines.each do |raw|
              s = raw.strip
              next if s.empty?

              pending_lazy = true if s =~ /\b(?:LazyColumn|LazyRow|LazyVerticalGrid|LazyHorizontalGrid)\s*\(/
              lazy_open_here = s =~ /lazyContent\s*=\s*\{/ ? true : false

              if lazy_depths.empty? && s =~ /(?:\A|[\s{(.])(?:item|items|itemsIndexed|stickyHeader)\s*[({]/
                return true
              end

              opens = s.count('{')
              closes = s.count('}')
              if opens > closes
                depth += opens - closes
                if pending_lazy || lazy_open_here
                  lazy_depths << depth
                  pending_lazy = false
                end
              elsif closes > opens
                depth -= closes - opens
                lazy_depths.pop while lazy_depths.any? && lazy_depths.last > depth
              end
            end

            false
          end

          # Names of receiver-extension sections that `code` calls.
          def scoped_call_names(code)
            code.scan(/\b(Section\d+(?:_\d+)*)\(data, viewModel\)/).flatten.uniq
                .select { |n| @scoped_names.key?(n) }
          end

          def references_outer_scope_local?(code)
            declared_inside = code.scan(/\b(?:val|var)\s+(\w+)\b/).flatten.to_set
            # Lambda parameters are declarations too: a chunk containing the
            # whole `items(…) { cellIndex -> … }` lambda self-contains
            # cellIndex — without this, any branch enclosing a Collection
            # emission is misread as leaking cell-scope locals and large
            # responsive gates around Collections are never extracted.
            code.scan(/\{\s*(\w+(?:\s*,\s*\w+)*)\s*->/).flatten.each do |params|
              params.split(',').each { |p| declared_inside << p.strip }
            end
            code.scan(OUTER_SCOPE_LOCAL_PATTERN).flatten.uniq.any? do |id|
              !declared_inside.include?(id)
            end
          end

          # Walk children left-to-right. For each child, look back over the
          # entire result so far and find the EARLIEST emitted chunk whose
          # declared vals are referenced by this child. If found, absorb
          # this child plus everything between (including unrelated chunks
          # already in `result`) into a single merged chunk replacing the
          # earlier ones.
          #
          # The single-forward-scan version this replaces missed any
          # consumer that came after a non-val sibling: `val A; useA;
          # Text(unrelated); useA` would yield `[merged(A+useA), Text,
          # useA]`, stranding the second `useA` in a file-scope lift. The
          # production trigger was `rememberPagerState` paired with multiple
          # downstream consumers (initial LaunchedEffect, snapshot-flow
          # LaunchedEffect, PageIndicator, HorizontalPager) spread across
          # several siblings — only the first consumer was being captured.
          #
          # Lookback covers every result chunk's declared val names (vals
          # declared at the chunk's sibling level — `scan_declared_vals`),
          # so a chain of vals (`val pageCount; val pagerState =
          # rememberPagerState(...){ pageCount }`) merges transitively.
          # Contiguity-fill (absorbing intermediate result chunks) is a
          # consequence of replacing `result[target..]` with one chunk
          # spanning the original target chunk's start through the current
          # child's end.
          def merge_val_chunks(lines, children)
            return children if children.empty?

            result = []

            children.each do |child|
              body = lines[child[:start]..child[:end_idx]].join("\n")

              merge_target = nil
              result.each_with_index do |prev, idx|
                prev_vars = scan_declared_vals(lines, prev)
                next if prev_vars.empty?
                if prev_vars.any? { |v| body =~ /\b#{Regexp.escape(v)}\b/ }
                  merge_target = idx
                  break
                end
              end

              if merge_target
                merged = {
                  start: result[merge_target][:start],
                  end_idx: child[:end_idx]
                }
                result = result[0...merge_target] + [merged]
              else
                result << child
              end
            end

            result
          end

          def scan_declared_vals(lines, chunk)
            body = lines[chunk[:start]..chunk[:end_idx]].join("\n")
            body.scan(/\b(?:val|var)\s+(\w+)\b/).flatten
          end

          def val_name_of(lines, child)
            (child[:start]..child[:end_idx]).each do |i|
              s = lines[i].strip
              next if s.empty?
              m = s.match(/^(?:val|var)\s+(\w+)\b/)
              return m && m[1]
            end
            nil
          end

          def all_children_already_lifted?(lines, children)
            children.all? do |child|
              first_line = nil
              (child[:start]..child[:end_idx]).each do |i|
                content = lines[i].strip
                next if content.empty?
                first_line = content
                break
              end
              !first_line.nil? && first_line =~ /\ASection\d+(?:_\d+)*\(data, viewModel\)\z/
            end
          end

          # A chunk is "cannot lift" if its first non-empty line declares a
          # local binding, starts with a lazy-DSL keyword, or its opening
          # carries a scope-bound modifier line before the lambda body
          # opens. In all three cases we recurse into the chunk rather than
          # extracting it as a section.
          def cannot_lift?(code)
            lines = code.lines.map(&:chomp)
            first = lines.find { |l| !l.strip.empty? }
            return false unless first

            stripped = first.strip

            # Comment-only chunks (single-line `//` rows, multi-line `/* ... */`
            # blocks, or interleaved blank lines) carry no @Composable
            # content. Lifting one emits an effectively empty
            # `@Composable private fun SectionN(data, viewModel) {}` and
            # replaces the original location with a `SectionN(data,
            # viewModel)` call. When that location sits inside a Lazy*Scope
            # (`LazyColumn`, `LazyVerticalGrid`, ...) the call becomes
            # `@Composable invocations can only happen from the context of
            # a @Composable function` because `@LazyScopeMarker` forbids
            # direct @Composable calls — only the lazy DSL functions
            # (`item`/`items`/`itemsIndexed`/`stickyHeader`) are allowed.
            # Anywhere else the lift is useless. Refuse in both cases.
            return true if comment_only_chunk?(lines)

            # Already-lifted `SectionN(data, viewModel)` calls — lifting them
            # again would cause an infinite outer-loop iteration in `process`
            # (each pass would wrap the previous lift in another section).
            return true if stripped =~ /\ASection\d+(?:_\d+)*\(data, viewModel\)\z/

            # Note: a chunk whose first line is `val foo = ...` is no longer
            # blanket-refused here. `find_splittable_children` runs
            # `merge_val_chunks` first so any val with a referencing sibling
            # is fused into a multi-line chunk whose body self-contains the
            # binding and its consumers — safe to lift as one section. An
            # orphan val (no referencing sibling) survives as a 1-line chunk;
            # lifting it into its own section is harmless (it's dead code
            # in that case anyway).

            first_word = stripped.match(/^(\w+)/)&.[](1)
            return true if first_word && LAZY_DSL_KEYWORDS.include?(first_word)

            # Lazy-DSL calls whose receiver scope lives OUTSIDE the chunk
            # (e.g. `data.gridItems?.…let { items(…) { … } }` directly under a
            # LazyVerticalGrid) — lifting would strip the Lazy*Scope receiver.
            return true if dangling_lazy_dsl?(code)

            # Collection / Lazy cell-scope locals leak through a file-scope
            # lift. Detect names matching the kjui-emit patterns (cellIndex,
            # cellData0, cellViewModel, cellId, currentCellData, section0,
            # ...) — if any are referenced without being declared inside the
            # chunk, the binding lives in an enclosing items / itemsIndexed
            # / stickyHeader lambda that the lifted Section function cannot
            # see. Recurse into the chunk instead. (False positive risk: a
            # `section42` constant identifier in a string template, e.g.
            # inside `"step_section3_button"`, would also match — but lift
            # suppression is harmless, the chunk just stays inline.)
            return true if references_outer_scope_local?(code)

            # Calls to receiver-extension sections (emitted by the if/else
            # branch pass): lifting the call site into a plain file-scope
            # function severs the receiver context and the extension no
            # longer resolves. These call-skeletons are tiny; keep inline.
            return true if scoped_call_names(code).any?

            # Scope-bound modifier anywhere in the chunk — including:
            #   (a) inline named-arg form on the opener line, e.g.
            #       `VisibilityWrapper(modifier = Modifier.weight(1f), ...)`
            #   (b) multi-step chains where the scope-bound call sits past
            #       the first step, e.g.
            #       `Box(modifier = Modifier.testTag(...).align(...).widthIn(...))`
            #   (c) multi-line chains where the call lives on its own line.
            # A previous version of this guard only inspected the opening
            # modifier-chain lines that preceded the lambda body and matched
            # by line-start, which missed (a) and (b). Lifting either form
            # to a file-scope @Composable strips the parent's
            # RowScope/ColumnScope/BoxScope/LazyItemScope receiver and the
            # call no longer resolves.
            # Depth-0 only: an inner `.weight(` whose Row lives inside the
            # chunk is self-contained and must not block the lift (the
            # substring-anywhere version froze every list screen).
            return true if SectionExtractor.scope_bound_needs_outer_receiver?(code)

            false
          end

          def build_function(name, body, receiver: nil, extra_params: [])
            params = ["    data: #{@data_type}", "    viewModel: #{@viewmodel_type}"]
            Array(extra_params).each { |n, t| params << "    #{n}: #{t}" }
            <<~KOTLIN.chomp
              @Composable
              private fun #{receiver}#{name}(
              #{params.join(",\n")}
              ) {
              #{indent_body(body)}
              }
            KOTLIN
          end

          def indent_body(code)
            dedent_code(code).lines.map { |l| l.strip.empty? ? "" : "    #{l.chomp}" }.join("\n")
          end

          def dedent_code(code)
            lines = code.lines
            non_empty = lines.reject { |l| l.strip.empty? }
            return code if non_empty.empty?

            min_indent = non_empty.map { |l| l.match(/^(\s*)/)[1].length }.min
            lines.map { |l| l.strip.empty? ? "\n" : l[min_indent..] }.join
          end

          def detect_child_indent(child_code)
            first_line = child_code&.lines&.find { |l| !l.strip.empty? }
            return "    " unless first_line

            first_line.match(/^(\s*)/)[1]
          end
        end
      end
    end
  end
end
