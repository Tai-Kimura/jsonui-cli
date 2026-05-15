# frozen_string_literal: true

require 'compose/helpers/section_extractor'

# Regression: kjui-auto-extract-sections-like-sjui
# Verifies the post-process pass that lifts oversized container children into
# file-scope `@Composable private fun SectionN(data, viewModel)` helpers,
# mirroring sjui's view_updater section extraction. Section extraction is the
# escape hatch for the JVM 65,536 byte / method bytecode limit that large
# layouts + `responsive` if/else duplication trip.
RSpec.describe KjuiTools::Compose::Helpers::SectionExtractor do
  let(:opts) do
    {
      view_name: 'Mypage',
      data_type: 'MypageData',
      viewmodel_type: 'MypageViewModel'
    }
  end

  describe '.extract' do
    it 'leaves a body under the threshold untouched and returns no functions' do
      body = "Column(modifier = Modifier.padding(8.dp)) {\n    Text(text = data.title)\n}\n"
      new_body, fns = described_class.extract(body, **opts, line_threshold: 100)
      expect(new_body).to eq(body)
      expect(fns).to be_empty
    end

    it 'lifts each child of a large container into a SectionN helper that takes (data, viewModel)' do
      body = <<~KOTLIN
        Column(
            modifier = Modifier.fillMaxSize()
        ) {
            Text(text = data.line1)
            Text(text = data.line2)
            Text(text = data.line3)
            Text(text = data.line4)
        }
      KOTLIN

      new_body, fns = described_class.extract(body, **opts, line_threshold: 5)

      expect(new_body).to include('Section0(data, viewModel)')
      expect(new_body).to include('Section1(data, viewModel)')
      expect(new_body).to include('Section2(data, viewModel)')
      expect(new_body).to include('Section3(data, viewModel)')
      expect(new_body).not_to include('Text(text = data.line1)')

      expect(fns.size).to eq(4)
      expect(fns.first).to include('@Composable')
      expect(fns.first).to include('private fun Section0(')
      expect(fns.first).to include('data: MypageData')
      expect(fns.first).to include('viewModel: MypageViewModel')
      expect(fns.first).to include('Text(text = data.line1)')
    end

    it 'walks back through multi-line `) {` openers to find the call keyword' do
      # The opening `) {` line has no first word; without paren-balance
      # look-back we would skip the outer Column and mistakenly pick a
      # smaller nested container.
      body = <<~KOTLIN
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp)
        ) {
            Text(text = data.a)
            Text(text = data.b)
            Text(text = data.c)
        }
      KOTLIN
      new_body, fns = described_class.extract(body, **opts, line_threshold: 5)
      expect(fns.size).to eq(3)
      expect(new_body).to include('Section0(data, viewModel)')
    end

    it 'recursively splits an oversized lifted child into sub-sections (Section0_0, Section0_1)' do
      body = <<~KOTLIN
        Column(modifier = Modifier.fillMaxSize()) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(8.dp)) {
                    Text(text = data.a)
                    Text(text = data.b)
                    Text(text = data.c)
                    Text(text = data.d)
                }
            }
            Spacer(modifier = Modifier.height(8.dp))
        }
      KOTLIN
      _, fns = described_class.extract(body, **opts, line_threshold: 4)
      # Section0 (Card chunk) is recursively split into Section0_0..3.
      names = fns.map { |f| f[/private fun (\w+)/, 1] }
      expect(names).to include('Section0', 'Section0_0', 'Section0_1', 'Section0_2', 'Section0_3')
    end

    it 'preserves `item { ... }` wrappers but lifts their inner contents' do
      # `item` is LazyListScope DSL — cannot be moved to a file-scope
      # @Composable function. Children inside the item's lambda body can be.
      body = <<~KOTLIN
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            item {
                Column(modifier = Modifier.padding(8.dp)) {
                    Text(text = data.a)
                    Text(text = data.b)
                    Text(text = data.c)
                    Text(text = data.d)
                }
            }
            item {
                Column(modifier = Modifier.padding(8.dp)) {
                    Text(text = data.e)
                    Text(text = data.f)
                    Text(text = data.g)
                    Text(text = data.h)
                }
            }
        }
      KOTLIN
      new_body, fns = described_class.extract(body, **opts, line_threshold: 6)
      # `item {` stays in place — never replaced with a SectionN call.
      expect(new_body).to include('item {')
      expect(new_body).not_to match(/^\s*Section\d+\(data, viewModel\)\s*$\s*item /m)
      # Inner Texts got lifted.
      expect(fns.size).to be >= 4
      expect(fns.first).to include('data: MypageData')
    end

    it 'does not lift a child whose opening modifier carries a scope-bound `.weight(1f)`' do
      # `.weight(1f)` belongs to RowScope/ColumnScope. Lifting the Column
      # chunk to a file-scope @Composable strips the receiver scope and
      # makes `.weight` unresolved. Recursion still descends into the
      # weighted block so its inner children can be lifted.
      body = <<~KOTLIN
        Row(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(8.dp)
            ) {
                Text(text = data.a)
                Text(text = data.b)
                Text(text = data.c)
                Text(text = data.d)
            }
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(8.dp)
            ) {
                Text(text = data.e)
                Text(text = data.f)
                Text(text = data.g)
                Text(text = data.h)
            }
        }
      KOTLIN
      new_body, fns = described_class.extract(body, **opts, line_threshold: 5)
      # The weighted Column chunks stay literal — we still see `.weight(1f)`
      # in the body, not the function signatures.
      expect(new_body.scan('.weight(1f)').size).to eq(2)
      fns.each { |f| expect(f).not_to include('.weight(1f)') }
      # The inner Text children got lifted into sub-sections.
      expect(fns.size).to be >= 4
    end

    it 'refuses to split a container whose body declares a sibling `val` (textfield state pattern)' do
      # `val textFieldState_x = rememberTextFieldState(...)` is consumed by
      # the immediately-following `CustomTextField(state = textFieldState_x,
      # ...)` call. Lifting either sibling would either lose the declaration
      # or strand it. Skip the parent container entirely.
      body = <<~KOTLIN
        Column(modifier = Modifier.fillMaxSize()) {
            val textFieldState_one = rememberTextFieldState(initialText = "hello")
            LaunchedEffect(textFieldState_one.text) {
                data.onChange?.invoke(textFieldState_one.text.toString())
            }
            CustomTextField(
                state = textFieldState_one,
                modifier = Modifier.fillMaxWidth()
            )
            Text(text = data.label)
        }
      KOTLIN
      new_body, fns = described_class.extract(body, **opts, line_threshold: 3)
      expect(fns).to be_empty
      expect(new_body).to eq(body)
    end

    it 'lifts inside both branches of a responsive if/else so the duplication shrinks to single-line calls' do
      # The if/else duplicates the body across size-class branches. After
      # extraction, each branch references the same SectionN helpers, so
      # the bytecode cost of the duplicated branch drops to N function-call
      # opcodes regardless of how large each section body is.
      body = <<~KOTLIN
        if (LocalConfiguration.current.screenWidthDp >= 840) {
            Row(modifier = Modifier.fillMaxSize()) {
                Column(modifier = Modifier.fillMaxWidth()) {
                    Text(text = data.line1)
                    Text(text = data.line2)
                    Text(text = data.line3)
                    Text(text = data.line4)
                }
                Column(modifier = Modifier.fillMaxWidth()) {
                    Text(text = data.right1)
                    Text(text = data.right2)
                    Text(text = data.right3)
                    Text(text = data.right4)
                }
            }
        } else {
            Column(modifier = Modifier.fillMaxSize()) {
                Column(modifier = Modifier.fillMaxWidth()) {
                    Text(text = data.line1)
                    Text(text = data.line2)
                    Text(text = data.line3)
                    Text(text = data.line4)
                }
                Column(modifier = Modifier.fillMaxWidth()) {
                    Text(text = data.right1)
                    Text(text = data.right2)
                    Text(text = data.right3)
                    Text(text = data.right4)
                }
            }
        }
      KOTLIN
      new_body, fns = described_class.extract(body, **opts, line_threshold: 6)
      expect(fns.size).to be >= 4
      # Both `Text(text = data.line1)` call sites must be replaced inside
      # the lifted sections, not the body. Body should mention SectionN
      # calls inside both branches.
      expect(new_body.scan(/Section\d+(?:_\d+)*\(data, viewModel\)/).size).to be >= 4
      # The body itself shouldn't carry the duplicated literal Texts.
      expect(new_body.scan('Text(text = data.line1)').size).to eq(0)
    end
  end
end
