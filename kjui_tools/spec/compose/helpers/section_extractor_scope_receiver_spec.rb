# frozen_string_literal: true

require_relative '../../spec_helper'
require 'compose/helpers/section_extractor'
require_relative '../../support/kotlin_compiler'

# A lifted section keeps the scope its scope-bound modifiers need (ticket
# kjui-section-extractor-drops-columnscope-for-weight). The guard took every PascalCase call's lambda for a receiver,
# so a `.weight(` under `CollectionReorderScope(...) {` (no receiver) or in the arguments of a call inside a
# `VisibilityWrapper(...) {` (BoxScope only) was lifted into a section with none: "Expression 'weight' of type 'Float'
# cannot be invoked" in the client's large screen, four times. A receiver-transparent wrapper is now walked past like
# control flow, a VisibilityWrapper provides BoxScope only, and the section takes the receiver its needs name.
RSpec.describe KjuiTools::Compose::Helpers::SectionExtractor do
  let(:opts) { { view_name: 'Probe', data_type: 'ProbeData', viewmodel_type: 'ProbeViewModel' } }

  def texts(prefix, n) = (0...n).map { |i| "                Text(text = data.#{prefix}#{i})" }.join("\n")

  # A Column whose children carry `.weight(`: one under a reorder scope (no receiver), one as a VisibilityWrapper's own
  # modifier, and one in the arguments of a Column inside a VisibilityWrapper's BoxScope content - the client's shapes.
  def body
    <<~KOTLIN
      Column(modifier = Modifier.fillMaxSize()) {
          CollectionReorderScope(data.reorder) {
              Box(
                  modifier = Modifier
                      .weight(1f)
              ) {
      #{texts('a', 8)}
              }
          }
          VisibilityWrapper(
              visibility = data.panelVisibility,
              modifier = Modifier.weight(1.15f),
          ) {
              Column {
      #{texts('b', 8)}
              }
          }
          Row(modifier = Modifier.fillMaxWidth()) {
              Box(modifier = Modifier.weight(1f)) {
      #{texts('c', 8)}
              }
          }
      }
    KOTLIN
  end

  describe '.scope_bound_needs_outer_receiver?' do
    it 'takes a reorder scope and a VisibilityWrapper for what they provide' do
      under_reorder = "CollectionReorderScope(state) {\n    Box(\n        modifier = Modifier\n            .weight(1f)\n    ) {\n    }\n}\n"
      expect(described_class.scope_bound_needs_outer_receiver?(under_reorder)).to eq(true)
      under_wrapper_args = "VisibilityWrapper(\n    visibility = v,\n) {\n    Column(modifier = Modifier.weight(1f)) {\n    }\n}\n"
      expect(described_class.scope_bound_needs_outer_receiver?(under_wrapper_args)).to eq(true)
      # A VisibilityWrapper's BoxScope is a Box's: its `.align(` / `.matchParentSize(` are met inside.
      box_align = "VisibilityWrapper(\n    visibility = v,\n) {\n    Text(modifier = Modifier.align(Alignment.Center))\n}\n"
      expect(described_class.scope_bound_needs_outer_receiver?(box_align)).to eq(false)
      # Control: a Column inside the chunk meets the weight of its children.
      in_column = "Column {\n    CollectionReorderScope(state) {\n        Box(modifier = Modifier.weight(1f)) {\n        }\n    }\n}\n"
      expect(described_class.scope_bound_needs_outer_receiver?(in_column)).to eq(false)
    end
  end

  describe '.extract' do
    it 'gives every lifted section that needs the Column the Column as its receiver, and the file compiles' do
      new_body, fns = described_class.extract(body, **opts, line_threshold: 12)
      expect(fns).not_to be_empty
      fns.map(&:to_s).each do |fn|
        header = fn.lines.find { |l| l.include?('fun ') }
        # A section that is not inside its own Row / Column for its `.weight(` must take a receiver.
        needs_outer = described_class.scope_bound_needs_outer_receiver?(fn.lines.drop_while { |l| !l.include?(') {') }.drop(1).join)
        expect(header).to include('ColumnScope.'), fn if needs_outer
      end
      emitted = "@Composable\nfun Probe(data: ProbeData, viewModel: ProbeViewModel) {\n#{new_body}\n}\n\n#{fns.map(&:to_s).join("\n\n")}"
      expect(<<~KOTLIN).to compile_as_kotlin
        annotation class Composable
        open class Modifier_
        object Modifier : Modifier_()
        fun Modifier_.fillMaxSize(): Modifier_ = this
        fun Modifier_.fillMaxWidth(): Modifier_ = this
        class Alignment { companion object { val Center = Alignment() } }
        @DslMarker annotation class LayoutScopeMarker
        @LayoutScopeMarker interface ColumnScope { fun Modifier_.weight(weight: Float): Modifier_ = this }
        @LayoutScopeMarker interface RowScope { fun Modifier_.weight(weight: Float): Modifier_ = this }
        @LayoutScopeMarker interface BoxScope { fun Modifier_.align(a: Alignment): Modifier_ = this }
        fun Column(modifier: Modifier_ = Modifier, content: ColumnScope.() -> Unit) {}
        fun Row(modifier: Modifier_ = Modifier, content: RowScope.() -> Unit) {}
        fun Box(modifier: Modifier_ = Modifier, content: BoxScope.() -> Unit) {}
        fun VisibilityWrapper(visibility: String, modifier: Modifier_ = Modifier, content: BoxScope.() -> Unit) {}
        fun CollectionReorderScope(state: Any?, content: () -> Unit) {}
        fun Text(text: String) {}
        class ProbeData {
            val reorder: Any? = null
            val panelVisibility: String = "visible"
            #{(%w[a b c].product((0...8).to_a)).map { |p, i| "val #{p}#{i}: String = \"\"" }.join("\n            ")}
        }
        class ProbeViewModel
        #{emitted.gsub(/^private fun androidx\.compose\.foundation\.layout\./, 'private fun ')}
      KOTLIN
    end
  end
end
