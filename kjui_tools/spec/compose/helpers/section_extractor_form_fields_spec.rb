# frozen_string_literal: true

require 'compose/helpers/section_extractor'

# Regression: lint-generated-size-ratchet-held-a-consumers-android-red (2026-10-21).
# A form's text field emits a text-sync LaunchedEffect that declares its own
# `val newValue` inside the lambda, and a SelectBox's onValueChange its own
# `val index`. The val-merge counted those lambda locals as sibling-level
# declarations, so the next field's `newValue` read as a reference and chained
# every field into one chunk: a 30-field form became one 832-line section
# (39% of the JVM method limit) with no container left inside to cut. The
# shape below is that form's, written here (two fields, a label, a picker row).
RSpec.describe KjuiTools::Compose::Helpers::SectionExtractor do
  let(:opts) { { view_name: 'Form', data_type: 'FormData', viewmodel_type: 'FormViewModel' } }

  def field(key)
    <<~KOTLIN.chomp
      val textFieldState_#{key} = rememberTextFieldState(initialText = data.#{key})
      LaunchedEffect(data.#{key}) { if (textFieldState_#{key}.text.toString() != data.#{key}) textFieldState_#{key}.edit { replace(0, length, data.#{key}) } }
      LaunchedEffect(textFieldState_#{key}.text) { val newValue = textFieldState_#{key}.text.toString(); if (newValue != data.#{key}) { viewModel.updateData(mapOf("#{key}" to newValue)) } }
      val focusRequester_#{key} = remember { FocusRequester() }
      CustomTextFieldWithMargins(
          state = textFieldState_#{key},
          modifier = Modifier.focusRequester(focusRequester_#{key})
      )
      val resolved_text_#{key} = Configuration.Font.resolve(FontSpec(size = 14))
      Text(
          text = "#{key}",
          fontSize = resolved_text_#{key}.size ?: TextUnit.Unspecified
      )
      SelectBox(
          items = data.#{key}Items,
          onValueChange = { newValue ->
              val index = data.#{key}Items.indexOf(newValue)
              viewModel.updateData(mapOf("#{key}Index" to index))
          }
      )
    KOTLIN
  end

  def form
    "Column(modifier = Modifier.fillMaxWidth()) {\n" +
      [field('title'), field('author'), field('publisher')].join("\n").gsub(/^/, '    ') +
      "\n}\n"
  end

  # The split form must still be Kotlin: each field's state, its LaunchedEffects
  # and its text field in one section, nothing reaching another section's
  # local. Types against stubs only — not the Compose compiler's rules.
  it 'returns a split form that compiles' do
    new_body, fns = described_class.extract(form, **opts, line_threshold: 20)
    expect(fns.size).to be >= 3
    fields = %w[title author publisher]
    data = fields.flat_map { |k| ["val #{k}: String = \"\"", "val #{k}Items: List<String> = emptyList()"] }.join(', ')
    expect(<<~KOTLIN).to compile_as_kotlin
      annotation class Composable
      interface Modifier { companion object : Modifier }
      fun Modifier.fillMaxWidth(): Modifier = this
      class FocusRequester
      fun Modifier.focusRequester(r: FocusRequester): Modifier = this
      interface ColumnScope
      fun Column(modifier: Modifier = Modifier, content: ColumnScope.() -> Unit) {}
      class TextBuffer(var text: String) { val length: Int get() = text.length; fun replace(start: Int, end: Int, s: String) { text = s } }
      class TextFieldState(var text: CharSequence) { fun edit(block: TextBuffer.() -> Unit) { TextBuffer(text.toString()).block() } }
      fun rememberTextFieldState(initialText: String): TextFieldState = TextFieldState(initialText)
      fun <T> remember(calc: () -> T): T = calc()
      fun LaunchedEffect(key1: Any?, block: suspend () -> Unit) {}
      fun CustomTextFieldWithMargins(state: TextFieldState, modifier: Modifier = Modifier) {}
      class TextUnit { companion object { val Unspecified = TextUnit() } }
      class FontSpec(val size: Int = 0)
      class Resolved(val size: TextUnit? = null)
      object Configuration { object Font { fun resolve(spec: FontSpec): Resolved = Resolved() } }
      fun Text(text: String, fontSize: TextUnit = TextUnit.Unspecified) {}
      fun SelectBox(items: List<String>, onValueChange: (String) -> Unit) {}
      class FormData(#{data})
      class FormViewModel { fun updateData(values: Map<String, Any>) {} }

      @Composable
      fun FormView(data: FormData, viewModel: FormViewModel) {
      #{new_body}
      }

      #{fns.join("\n")}
    KOTLIN
  end

  it 'reads only the vals a chunk declares at its own level' do
    text = described_class.top_level_text(
      "val a = remember { val b = 1 }\nLaunchedEffect(x) { val newValue = \"{\" }\nval c = \"x}y\"\n"
    )
    expect(text.scan(/\bval\s+(\w+)/).flatten).to eq(%w[a c])
    expect(text.lines.size).to eq(3)
  end

  it "does not chain a form's fields through the locals of their lambdas" do
    body = form
    new_body, fns = described_class.extract(body, **opts, line_threshold: 20)
    calls = new_body.scan(/^\s*(Section\w*)\(data, viewModel\)/).flatten
    expect(calls.size).to be >= 3
    owner = lambda do |key|
      fns.select { |f| f.include?("textFieldState_#{key} = rememberTextFieldState") }
    end
    %w[title author publisher].each do |key|
      expect(owner.call(key).size).to eq(1)
      section = owner.call(key).first
      # the state travels with every consumer of it, and with nothing of the other fields
      expect(section).to include("state = textFieldState_#{key}", "LaunchedEffect(textFieldState_#{key}.text)")
      expect(section).not_to match(/textFieldState_(?!#{key}\b)\w+ = rememberTextFieldState/)
    end
    expect(fns.map { |f| f.lines.size }.max).to be < body.lines.size / 2
  end
  it 'sees only the declarations whose scope is still open' do
    lines = ['val a = 1', 'items(n) { cellIndex ->', '    val cellId = "x{"', '}', 'Column {',
             '    val b = remember { val c = 2 }', '    LazyColumn { items(3) { i ->']
    expect(described_class.visible_declarations(lines)).to eq(%w[a b i])
  end

  # A consumer's home screen, reduced to the 40 lines that still misfire: a grid whose
  # items lambda declares `val cellId`, then a list whose only "cellId" is the
  # string naming the key (kjui's own collection scaffolding, no screen's text).
  # Counting the grid's closed lambda local as in scope below it made the
  # list's chunk take `cellId` as a parameter, and the call site passed a name
  # not in scope there (Unresolved reference 'cellId').
  it "does not hand a section a closed sibling lambda's local as a parameter" do
    body = <<~KOTLIN
      Box(
      ) {
          Box(
          ) {
              Column(
              ) {
                  if (data.gridVisibility != "gone") {
                  VisibilityWrapper(
                  ) {
                  LazyVerticalGrid(
                  ) {
                      if (section0 != null) {
                          if (enrichedData0 != null) {
                              items(enrichedData0.size, key = { (enrichedData0[it]["cellId"] as? String) ?: it.toString() }) { cellIndex ->
                                  Box(
                                  ) {
                                      val cellId = (currentCellData["cellId"] as? String) ?: (currentCellData["cellId"] as? String) ?: "$cellIndex"
                                  }
                              }
                          }
                      }
                  }
                  }
                  }
                  if (data.listVisibility != "gone") {
                  VisibilityWrapper(
                  ) {
                  val enrichedData0 = if (cellData0 != null) remember(cellData0.data) { com.kotlinjsonui.utils.CellIdGenerator.enrichCellIds(cellData0.data, "cellId") } else null
                  LazyVerticalGrid(
                  ) {
                      if (section0 != null) {
                          if (enrichedData0 != null) {
                          }
                      }
                  }
                  }
                  }
              }
          }
      }
    KOTLIN
    new_body, fns = described_class.extract(body, **opts, line_threshold: 10, enclosing_depth: 2)
    expect(fns).not_to be_empty
    (fns + [new_body]).each do |code|
      expect(code).not_to match(/\bSection\w*\([^)]*\bcellId\b/), code
    end
  end

  it "types a section's parameters from the declarations still in scope only" do
    state = described_class::State.new(view_name: 'Home', data_type: 'HomeData', viewmodel_type: 'HomeViewModel',
                                       threshold: 10)
    lines = ['items(gridItems.size) { cellIndex ->', '    val cellId = gridItems[cellIndex].id', '}']
    seg = 'Text(text = enrichCellIds(data.listCells, "cellId").size.toString())'
    expect(state.send(:cell_params_for, lines, lines.size, seg, {})).to eq([])
  end

  # A sibling-level val read by a later sibling still travels with it: the
  # pagerState example in section_extractor_spec.rb holds that.
end
