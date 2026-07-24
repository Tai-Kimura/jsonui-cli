# frozen_string_literal: true

require 'compose/helpers/visibility_helper'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Helpers::VisibilityHelper do
  let(:required_imports) { Set.new }

  describe '.wrap_with_visibility' do
    it 'returns component unchanged when no visibility attributes' do
      json_data = { 'type' => 'Text' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to eq(component_code)
    end

    it 'wraps with VisibilityWrapper for static visibility' do
      json_data = { 'visibility' => 'invisible' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('VisibilityWrapper(')
      expect(result).to include('visibility = "invisible"')
    end

    it 'wraps with VisibilityWrapper for visibility binding' do
      json_data = { 'visibility' => '@{isVisible}' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('VisibilityWrapper(')
      expect(result).to include('visibility = data.isVisible')
    end

    it 'wraps with VisibilityWrapper for hidden attribute' do
      json_data = { 'hidden' => true }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('VisibilityWrapper(')
      expect(result).to include('hidden = true')
    end

    it 'wraps with VisibilityWrapper for hidden binding' do
      json_data = { 'hidden' => '@{isHidden}' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('hidden = data.isHidden')
    end

    # hidden = visibility:"invisible" shorthand — the component keeps its
    # layout space. Unlike a "gone"-capable visibility binding, a hidden
    # binding with weight must NOT be wrapped in a conditional-composition
    # guard: the weighted space stays allocated and VisibilityWrapper
    # draws it invisible.
    it 'does not emit a conditional guard for hidden binding with weight' do
      json_data = { 'hidden' => '@{isHidden}', 'weight' => 1 }
      component_code = <<~KOTLIN.chomp
        Text(
            "Hello",
            modifier = Modifier
                .weight(1f)
        )
      KOTLIN
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports, 'Column')
      expect(result).not_to include('if (')
      expect(result).to include('hidden = data.isHidden')
      expect(result).to include('modifier = Modifier.weight(1f)')
    end

    it 'includes closing bracket' do
      json_data = { 'visibility' => 'visible' }
      component_code = 'Text("Hello")'
      result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports)
      expect(result).to include('}')
    end

    # Regression: kjui-responsive-visibility-weight-second-branch-weight-remains.
    # When a responsive Collection/Embed inline if/else chain has `weight` +
    # `visibility` under a Column parent, the wrapper hoists ONE `.weight`,
    # and EVERY branch's inner `.weight(Nf)` must be stripped and replaced
    # with `.fillMaxHeight()`. A first-match-only sub left the else branch's
    # `.weight` inside the VisibilityWrapper content lambda (no ColumnScope)
    # → "Modifier.weight cannot be called in this context" compile halt.
    context 'weight strip across all branches of an inline chain' do
      let(:chain_code) do
        <<~KOTLIN.chomp
          if (with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp().value.toInt() } >= 840) {
              LazyVerticalGrid(
                  modifier = Modifier
                      .testTag("bar_list_collection")
                      .weight(1f),
              ) {
              }
          } else {
              CollectionStack(
                  modifier = Modifier
                      .testTag("bar_list_collection")
                      .weight(1f),
              ) {
              }
          }
        KOTLIN
      end

      it 'strips inner .weight from every branch and fills instead (Column parent)' do
        json_data = { 'visibility' => '@{contentVisibility}', 'weight' => 1 }
        result = described_class.wrap_with_visibility(json_data, chain_code, 0, required_imports, 'Column')

        # The wrapper owns the single weight...
        expect(result).to include('modifier = Modifier.weight(1f)')
        # ...and the gone-guard wraps the weighted child.
        expect(result).to include('if (data.contentVisibility.lowercase() != "gone")')

        # Exactly ONE `.weight(` survives — the wrapper's hoisted one. Both
        # branch weights are stripped (else they'd sit in the content lambda
        # which has no ColumnScope and fail to compile).
        expect(result.scan('.weight(').length).to eq(1)

        # Both branches now fill the weighted space instead.
        expect(result.scan('.fillMaxHeight()').length).to eq(2)
      end
    end

    # Regression: kjui-visibility-weight-gsub-strips-descendant-weights.
    # The wrap target's OWN modifier chain must lose its weight (hoisted to
    # the wrapper), but a weighted DESCENDANT (e.g. a centering spacer child
    # with its own `weight: 1`) must keep its `.weight(...)`. Stripping the
    # descendant breaks its layout AND perturbs section_extractor's
    # scope-bound lift heuristic (massive spurious churn). Only the
    # shallowest (top-level / branch-root) weight chains are transformed.
    context 'weight strip preserves weighted descendant children' do
      let(:container_code) do
        # `suggestion_cards_container` (weight:1 + visibility) wrapping two
        # weighted spacer children (also weight:1, same value).
        <<~KOTLIN.chomp
          Column(
              modifier = Modifier
                  .testTag("suggestion_cards_container")
                  .weight(1f),
          ) {
              Box(
                  modifier = Modifier
                      .testTag("suggestion_spacer_top")
                      .weight(1f)
                      .fillMaxWidth()
              ) {
              }
              Box(
                  modifier = Modifier
                      .testTag("suggestion_spacer_bottom")
                      .weight(1f)
                      .fillMaxWidth()
              ) {
              }
          }
        KOTLIN
      end

      it 'strips only the container weight, keeps both descendant spacer weights' do
        json_data = { 'visibility' => '@{suggestionCardsVisibility}', 'weight' => 1 }
        result = described_class.wrap_with_visibility(json_data, container_code, 0, required_imports, 'Column')

        # Wrapper hoists exactly one weight.
        expect(result).to include('modifier = Modifier.weight(1f)')

        # Both descendant spacers keep their `.weight(1f)`.
        top = result[/suggestion_spacer_top.*?\)\s*\{/m]
        bottom = result[/suggestion_spacer_bottom.*?\)\s*\{/m]
        expect(top).to include('.weight(1f)')
        expect(bottom).to include('.weight(1f)')

        # Total `.weight(` = wrapper hoist (1) + two preserved descendants (2).
        # The container's own weight was stripped (3, not 4).
        expect(result.scan('.weight(').length).to eq(3)

        # Exactly one fill was injected — onto the container chain only, NOT
        # the descendants.
        expect(result.scan('.fillMaxHeight()').length).to eq(1)
      end
    end

    # Regression: kjui-visibility-weight-fill-check-misses-post-weight-fill.
    # The fill-existence check must inspect the WHOLE chain, including the
    # part AFTER `.weight(...)`. A chain that already carries a fill modifier
    # downstream of its weight must NOT get a second, redundant fill injected.
    context 'weight strip skips fill injection when a fill already follows the weight' do
      let(:post_weight_fill_code) do
        # `grant_credits_item` (Row parent, weight:1 + visibility) whose own
        # chain already has `.fillMaxWidth()` AFTER the weight.
        <<~KOTLIN.chomp
          Column(
              modifier = Modifier
                  .testTag("grant_credits_item")
                  .weight(1f)
                  .wrapContentHeight()
                  .fillMaxWidth(),
          ) {
          }
        KOTLIN
      end

      it 'does not duplicate the fill modifier (Row parent, fill after weight)' do
        json_data = { 'visibility' => '@{grantCreditsVisibility}', 'weight' => 1 }
        result = described_class.wrap_with_visibility(json_data, post_weight_fill_code, 0, required_imports, 'Row')

        # Wrapper hoists the weight; the inner chain's weight is stripped.
        expect(result).to include('modifier = Modifier.weight(1f)')
        # The pre-existing `.fillMaxWidth()` is kept, and NO duplicate added.
        expect(result.scan('.fillMaxWidth()').length).to eq(1)
        # Inner weight gone (only the hoisted wrapper weight remains).
        expect(result.scan('.weight(').length).to eq(1)
      end
    end

    # Regression: kjui-section-extracted-box-drops-centerhorizontal-align.
    # When a View with `centerHorizontal: true` (e.g. from `responsive.regular`)
    # was wrapped with VisibilityWrapper under a Column or Row parent, the
    # helper STRIPPED the inner `.align(...)` without hoisting it — silently
    # erasing the alignment. VisibilityWrapper internally delegates to a
    # Box(modifier=modifier), which is in the caller's scope, so the
    # appropriately-typed `.align(...)` (ColumnScope.align for Column, etc.)
    # propagates correctly when hoisted onto the wrapper. Verify hoisting
    # works for all three parent scopes.
    context 'hoisting .align(...) onto VisibilityWrapper (regression)' do
      let(:component_code) do
        # Mimic the post-build_alignment+ContainerComponent emit shape that
        # wrap_with_visibility receives: a Box with `.align(...)` already
        # injected into the outer modifier chain.
        <<~KOTLIN.chomp
          Box(
              modifier = Modifier
                  .testTag("save_button")
                  .semantics { testTagsAsResourceId = true }
                  .align(Alignment.CenterHorizontally)
                  .widthIn(max = 400.dp)
                  .fillMaxWidth(),
              contentAlignment = Alignment.Center
          ) {
              Text("Save")
          }
        KOTLIN
      end

      it 'hoists ColumnScope.align(Alignment.CenterHorizontally) for Column parent' do
        json_data = { 'visibility' => '@{saveButtonVisibility}', 'centerHorizontal' => true }
        result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports, 'Column')
        expect(result).to include('VisibilityWrapper(')
        expect(result).to include('modifier = Modifier.align(Alignment.CenterHorizontally)')
        # And the inner Box must no longer carry the same align (would
        # otherwise resolve in BoxScope inside VisibilityWrapper's internal
        # Box and double-apply).
        inner = result.split('VisibilityWrapper(').last
        expect(inner.scan('.align(Alignment.CenterHorizontally)').size).to eq(1)
      end

      it 'hoists RowScope.align(Alignment.CenterVertically) for Row parent' do
        row_component_code = component_code.sub('Alignment.CenterHorizontally', 'Alignment.CenterVertically')
        json_data = { 'visibility' => '@{saveButtonVisibility}', 'centerVertical' => true }
        result = described_class.wrap_with_visibility(json_data, row_component_code, 0, required_imports, 'Row')
        expect(result).to include('modifier = Modifier.align(Alignment.CenterVertically)')
      end

      it 'still hoists for Box parent (existing behavior preserved)' do
        box_component_code = component_code.sub('Alignment.CenterHorizontally', 'BiasAlignment(0f, -1f)')
        json_data = { 'visibility' => '@{saveButtonVisibility}', 'centerHorizontal' => true }
        result = described_class.wrap_with_visibility(json_data, box_component_code, 0, required_imports, 'Box')
        expect(result).to include('modifier = Modifier.align(BiasAlignment(0f, -1f))')
      end

      it 'does NOT hoist when the container has no own alignment attrs' do
        # Guards against stealing a nested descendant's `.align(...)` —
        # only the wrapped container's OWN alignment hoists.
        json_data = { 'visibility' => '@{saveButtonVisibility}' }  # no centerHorizontal etc.
        result = described_class.wrap_with_visibility(json_data, component_code, 0, required_imports, 'Column')
        # The wrapper has no .align hoisted; the inner Box retains its own.
        expect(result).not_to match(/VisibilityWrapper\([^{]*modifier = Modifier\.align/m)
        expect(result).to include('.align(Alignment.CenterHorizontally)')  # untouched on inner
      end
    end
  end

  describe '.should_skip_render?' do
    it 'returns true for static gone visibility' do
      json_data = { 'visibility' => 'gone' }
      expect(described_class.should_skip_render?(json_data)).to be true
    end

    # hidden = visibility:"invisible" shorthand: keeps its layout space,
    # so a static hidden must still render (VisibilityWrapper draws it
    # invisible) — only static "gone" skips composition entirely.
    it 'returns false for static hidden (space-keeping, renders invisible)' do
      json_data = { 'hidden' => true }
      expect(described_class.should_skip_render?(json_data)).to be false
    end

    it 'returns false for visibility binding' do
      json_data = { 'visibility' => '@{isGone ? "gone" : "visible"}' }
      expect(described_class.should_skip_render?(json_data)).to be false
    end

    it 'returns false for hidden binding' do
      json_data = { 'hidden' => '@{isHidden}' }
      expect(described_class.should_skip_render?(json_data)).to be false
    end

    it 'returns false for visible visibility' do
      json_data = { 'visibility' => 'visible' }
      expect(described_class.should_skip_render?(json_data)).to be false
    end

    it 'returns false for no visibility attributes' do
      json_data = { 'type' => 'Text' }
      expect(described_class.should_skip_render?(json_data)).to be false
    end
  end
end
