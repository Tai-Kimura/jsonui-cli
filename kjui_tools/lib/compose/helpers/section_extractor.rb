# frozen_string_literal: true

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
        OUTER_SCOPE_LOCAL_PATTERN = /\b(?:cell[A-Z]\w*|section\d+|currentCellData)\b/

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
        def self.extract(body, view_name:, data_type:, viewmodel_type:, line_threshold: DEFAULT_LINE_THRESHOLD)
          state = State.new(
            view_name: view_name,
            data_type: data_type,
            viewmodel_type: viewmodel_type,
            threshold: line_threshold
          )
          new_body = state.process(body, "Section")
          [new_body, state.functions]
        end

        class State
          attr_reader :functions

          def initialize(view_name:, data_type:, viewmodel_type:, threshold:)
            @view_name = view_name
            @data_type = data_type
            @viewmodel_type = viewmodel_type
            @threshold = threshold
            @functions = []
            @top_level_counter = 0
          end

          # Recursively split `code` if it is over the threshold and a
          # splittable container exists. `prefix` is the base name used for
          # extracted children (`Section`, then `Section0_`, `Section0_1_`,
          # ...). At the outermost call we iterate until no more candidates
          # remain, so parallel structures like the two branches of a
          # `responsive` `if/else` both get their children lifted.
          def process(code, prefix)
            return code if code.lines.size <= @threshold

            previous = nil
            current = code
            while previous != current
              previous = current
              current = process_once(current, prefix)
            end
            current
          end

          private

          def process_once(code, prefix)
            result = find_splittable_children(code)
            return code unless result

            header_lines, child_codes, trailer_lines = result
            child_indent = detect_child_indent(child_codes.first)

            new_body_lines = header_lines.dup
            child_codes.each do |child_code|
              name = next_name(prefix)

              if cannot_lift?(child_code)
                # Recurse into the chunk so its descendants can still be
                # lifted. The recursion replaces oversized children inside
                # the chunk with section calls; the chunk itself stays in
                # place (scope-bound or lazy-DSL constraint).
                lifted = process(child_code, "#{name}_")
                lifted.lines.each { |l| new_body_lines << l.chomp }
              else
                lifted_body = process(child_code, "#{name}_")
                @functions << build_function(name, lifted_body)
                new_body_lines << "#{child_indent}#{name}(data, viewModel)"
              end
            end

            new_body_lines.concat(trailer_lines)
            new_body_lines.join("\n")
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
          def references_outer_scope_local?(code)
            declared_inside = code.scan(/\b(?:val|var)\s+(\w+)\b/).flatten.to_set
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
            # Substring match is safe: a false positive (e.g. `.weight(`
            # inside a string literal — never actually emitted by our
            # codegen) only suppresses extraction, never produces wrong
            # code. Descendants are still reached via recursion.
            return true if SCOPE_BOUND_MODIFIER_PREFIXES.any? { |m| code.include?(m) }

            false
          end

          def build_function(name, body)
            <<~KOTLIN.chomp
              @Composable
              private fun #{name}(
                  data: #{@data_type},
                  viewModel: #{@viewmodel_type}
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
