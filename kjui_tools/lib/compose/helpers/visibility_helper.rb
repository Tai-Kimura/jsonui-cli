# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      class VisibilityHelper
        def self.wrap_with_visibility(json_data, component_code, depth, required_imports, parent_type = nil)
          visibility_result = ModifierBuilder.build_visibility(json_data, required_imports)
          visibility_info = visibility_result[:visibility_info]

          # If no visibility attributes, return the component as-is
          return component_code if visibility_info.empty?

          # Build VisibilityWrapper
          wrapper_code = indent("VisibilityWrapper(", depth)

          # Add visibility parameters
          if visibility_info[:visibility_binding]
            wrapper_code += "\n" + indent("visibility = #{visibility_info[:visibility_binding]},", depth + 1)
          elsif visibility_info[:visibility]
            wrapper_code += "\n" + indent("visibility = \"#{visibility_info[:visibility]}\",", depth + 1)
          end

          if visibility_info[:hidden_binding]
            wrapper_code += "\n" + indent("hidden = #{visibility_info[:hidden_binding]},", depth + 1)
          elsif visibility_info[:hidden]
            wrapper_code += "\n" + indent("hidden = true,", depth + 1)
          end

          # Collect modifier parts that must live on the VisibilityWrapper
          # (because VisibilityWrapper breaks the parent scope)
          wrapper_modifier_parts = []

          # Pass weight modifier to VisibilityWrapper so it works within ColumnScope/RowScope
          weight_value = json_data['weight']
          has_weight_in_scope = weight_value && (parent_type == 'Column' || parent_type == 'Row')
          if has_weight_in_scope
            wrapper_modifier_parts << ".weight(#{weight_value}f)"
            fill_modifier = parent_type == 'Row' ? '.fillMaxWidth()' : '.fillMaxHeight()'

            # Strip the inner `.weight(Nf)` and add the fill modifier in its
            # place. The VisibilityWrapper now owns the weight (hoisted
            # above), so the wrap target's own modifier chain must drop its
            # weight and fill the weighted space the wrapper provides.
            #
            # This must hit the wrap target's OWN chain only — and, for a
            # responsive inline `if/else` chain, each *branch root* (same
            # shallowest indentation). It must NOT touch a descendant
            # component's legitimate `.weight(...)` (e.g. a weighted spacer
            # child inside the wrapped container) — doing so breaks that
            # child's layout AND, by removing `.weight(`, perturbs
            # section_extractor's scope-bound lift heuristic, causing massive
            # spurious churn. (Bug: kjui-visibility-weight-gsub-strips-
            # descendant-weights.)
            #
            # Two earlier shapes were both wrong: a first-match `sub` missed
            # the else branch's weight (compile halt:
            # kjui-responsive-visibility-weight-second-branch); an unbounded
            # `gsub` hit descendants (this bug). The fix: transform only the
            # weight-bearing `modifier = Modifier` chains whose `modifier`
            # line sits at the MINIMUM indentation among such chains — i.e.
            # the top-level / branch-root chains, never the deeper descendants.
            weight_re = /\n[ \t]*\.weight\(\s*#{Regexp.escape(weight_value.to_s)}f?\s*\)/
            # Weighted components are always emitted multi-line (see
            # collection_component's modifier note), so the `modifier =
            # Modifier` of a weight-bearing chain starts its own line; capture
            # that line's leading indent. `mid` is the chain segment BEFORE
            # the weight; `tail` is the segment AFTER it (the remaining
            # `.call(...)` continuation lines, each starting with `.`, which
            # stop before the component's closing `) {` / a sibling arg /
            # child content). Capturing the tail lets the fill-existence
            # check see a `.fillMaxWidth()`/`.fillMaxHeight()` that already
            # sits *after* the weight — otherwise we inject a redundant
            # duplicate fill (bug: kjui-visibility-weight-fill-check-misses-
            # post-weight-fill). Tempered so a match never spans into the
            # next chain.
            chain_re = /^([ \t]*)(modifier\s*=\s*Modifier)\b((?:(?!modifier\s*=\s*Modifier).)*?)#{weight_re}((?:\n[ \t]+\.[^\n]*)*)/m
            indents = component_code.scan(chain_re).map { |m| m[0].length }
            if indents.any?
              min_indent = indents.min
              component_code = component_code.gsub(chain_re) do
                indent = Regexp.last_match(1)
                head   = Regexp.last_match(2)
                mid    = Regexp.last_match(3)
                tail   = Regexp.last_match(4)
                if indent.length == min_indent
                  fill_indent = ' ' * (indent.length + 4)
                  # Check the ENTIRE chain (before AND after the weight) for an
                  # existing fill before injecting one.
                  has_fill = mid.include?(fill_modifier) || tail.include?(fill_modifier)
                  inserted = has_fill ? '' : "\n#{fill_indent}#{fill_modifier}"
                  "#{indent}#{head}#{inserted}#{mid}#{tail}"
                else
                  # Descendant chain — leave its weight and the whole match intact.
                  Regexp.last_match(0)
                end
              end
            end
          end

          # Hoist the wrapped container's outer `.align(...)` to the
          # VisibilityWrapper itself.
          #
          # VisibilityWrapper is a `@Composable` function that internally
          # delegates to `Box(modifier = modifier) { content() }`. Function
          # calls don't introduce a Layout node, so the inner Box is
          # effectively a direct child of whatever scope the caller is in:
          # if VisibilityWrapper(...) is called from ColumnScope, the inner
          # Box is ColumnScope's direct child and ColumnScope.align(...) on
          # the modifier resolves correctly. Same for RowScope and BoxScope.
          # That means hoisting works uniformly across all three parent
          # scopes — we just splice the `.align(...)` call (created in the
          # parent's scope) onto the wrapper's `modifier = Modifier...`
          # chain. The previous version skipped hoisting for Column/Row and
          # silently *dropped* the inner Box's align, which made
          # `responsive.regular.centerHorizontal: true` a no-op once
          # wrap_with_visibility ran on a Column-parent View (see
          # `kjui-section-extracted-box-drops-centerhorizontal-align`).
          #
          # IMPORTANT: only hoist when the wrapped container itself declared
          # alignment attrs. Otherwise the first `.align(...)` we match in
          # component_code belongs to a nested descendant, and hoisting it
          # onto the VisibilityWrapper strips that descendant's alignment.
          container_has_own_alignment =
            json_data['alignTop'] || json_data['alignBottom'] ||
            json_data['alignLeft'] || json_data['alignRight'] ||
            json_data['centerHorizontal'] || json_data['centerVertical'] ||
            json_data['centerInParent']

          if container_has_own_alignment
            # Use balanced parentheses matching to handle nested calls like BiasAlignment(-1f, 1f)
            # Anchor to the OUTER `modifier = Modifier` block so we don't steal
            # a descendant Box's align that happens to appear earlier in the string.
            outer_modifier_regex = /(modifier\s*=\s*Modifier\b(?:(?!\)\s*\{).)*?)(\n\s*\.align\(([^()]*(?:\([^()]*\))?[^()]*)\))/m
            if (m = component_code.match(outer_modifier_regex))
              align_content = m[3]
              wrapper_modifier_parts << ".align(#{align_content})"
              component_code = component_code.sub(m[2], '')
            end
          end

          # Build modifier parameter if any parts collected
          unless wrapper_modifier_parts.empty?
            modifier_chain = "Modifier" + wrapper_modifier_parts.join('')
            wrapper_code += "\n" + indent("modifier = #{modifier_chain},", depth + 1)
          end

          wrapper_code += "\n" + indent(") {", depth)
          wrapper_code += "\n" + component_code
          wrapper_code += "\n" + indent("}", depth)

          # When weight + visibility binding are combined, wrap in if-block to prevent
          # Compose from allocating weight space when gone (Compose keeps composition slots
          # even when a Composable returns early, so VisibilityWrapper's return doesn't help).
          # This guard is for "gone" ONLY — `hidden` is the boolean shorthand for
          # visibility:"invisible" (keeps its layout space), so a hidden binding must
          # NOT conditionally drop the composable: the weighted space stays allocated
          # and VisibilityWrapper draws it invisible.
          if has_weight_in_scope && visibility_info[:visibility_binding]
            gone_guard = indent("if (#{visibility_info[:visibility_binding]}.lowercase() != \"gone\") {", depth)
            gone_guard += "\n" + wrapper_code
            gone_guard += "\n" + indent("}", depth)
            wrapper_code = gone_guard
          end

          wrapper_code
        end
        
        def self.should_skip_render?(json_data)
          # Check if component should not be rendered at all (static gone).
          # `hidden: true` must NOT skip: hidden is the boolean shorthand for
          # visibility:"invisible" — the component keeps its layout space
          # (drawn invisible via VisibilityWrapper), only "gone" collapses.
          return true if json_data['visibility'] == 'gone' && !json_data['visibility'].to_s.include?('@{')
          false
        end
        
        private
        
        def self.indent(text, level)
          return text if level == 0
          spaces = '    ' * level
          text.split("\n").map { |line| 
            line.empty? ? line : spaces + line 
          }.join("\n")
        end
      end
    end
  end
end