# frozen_string_literal: true

# The wrapContent Collection's Column (kjui collection_component
# generate_non_lazy, jsonui-cli 1.9.0) scrolls inside the height its parent
# bounds it to: a layout step that hands the verticalScroll a bounded height,
# then the scroll. A spec that compiles the emit in one file declares the
# names that step uses here, and `unqualify` writes the fully-qualified
# Constraints the emit reaches as the stub's simple name. Compiled, not run:
# what the step does is measured on a device.
module ComposeBoundedScrollStubs
  KOTLIN = <<~KOTLIN
    class Placeable(val width: Int, val height: Int) { fun place(x: Int, y: Int) {} }
    class Constraints(val minWidth: Int = 0, val maxWidth: Int = 0, val minHeight: Int = 0, val maxHeight: Int = 0) {
        val hasBoundedHeight get() = maxHeight != Int.MAX_VALUE
        companion object { fun fitPrioritizingWidth(minWidth: Int, maxWidth: Int, minHeight: Int, maxHeight: Int) = Constraints(minWidth, maxWidth, minHeight, maxHeight) }
    }
    interface Measurable { fun measure(constraints: Constraints): Placeable }
    class MeasureResult
    class MeasureScope { fun layout(width: Int, height: Int, placementBlock: () -> Unit): MeasureResult = MeasureResult() }
    fun Modifier.layout(measure: MeasureScope.(Measurable, Constraints) -> MeasureResult): Modifier = this
  KOTLIN

  def self.unqualify(code)
    code.gsub('androidx.compose.ui.unit.Constraints', 'Constraints')
  end
end
