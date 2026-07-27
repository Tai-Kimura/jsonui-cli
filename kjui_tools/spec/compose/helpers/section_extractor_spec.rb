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

    # Regression: kjui-section-extractor-scope-bound-modifier-guard-incomplete.
    # `VisibilityWrapper(modifier = Modifier.weight(1f), ...)` puts `.weight(`
    # inline in a named-argument value on the OPENING line — not at the line
    # start, and not on its own modifier-chain line. The earlier guard only
    # matched line-start prefixes and missed this form, lifting the chunk
    # into a file-scope @Composable where `weight` no longer resolves against
    # any scope receiver. Symptom in the consumer: 50 of 51 compile errors
    # of the form `Expression 'weight' of type 'Float' cannot be invoked`.
    it 'does not lift a chunk whose opening line carries `.weight(` inside an inline `modifier =` named argument' do
      body = <<~KOTLIN
        Row(modifier = Modifier.fillMaxWidth().height(44.dp)) {
            VisibilityWrapper(visibility = data.purchaseTabVisibility, modifier = Modifier.weight(1f)) {
                Box(modifier = Modifier.fillMaxHeight()) {
                    Text(text = data.purchaseTabLabel)
                    Text(text = data.purchaseTabBadge)
                    Image(painter = painterResource(R.drawable.tab_icon))
                }
            }
            VisibilityWrapper(visibility = data.searchTabVisibility, modifier = Modifier.weight(1f)) {
                Box(modifier = Modifier.fillMaxHeight()) {
                    Text(text = data.searchTabLabel)
                    Text(text = data.searchTabBadge)
                    Image(painter = painterResource(R.drawable.tab_icon))
                }
            }
        }
      KOTLIN
      new_body, fns = described_class.extract(body, **opts, line_threshold: 6)

      # The `.weight(1f)` calls stay in the body — both VisibilityWrapper
      # chunks are not lifted.
      expect(new_body.scan('Modifier.weight(1f)').size).to eq(2)
      # No lifted section function carries `.weight(` itself (would lose
      # the scope receiver and fail to compile).
      fns.each { |f| expect(f).not_to include('.weight(') }
      # Descendants inside each VisibilityWrapper still get lifted via
      # recursion (the inner Box children).
      expect(fns.size).to be >= 4
    end

    # Same regression, second form: `.align(` appears mid-chain on a single
    # `Modifier.testTag(...).semantics{...}.align(...).widthIn(...)` line.
    # Match must be on the full chunk body, not a line-start anchor.
    it 'does not lift a chunk whose opening modifier-chain has `.align(` past the first step' do
      body = <<~KOTLIN
        Column(modifier = Modifier.fillMaxSize()) {
            Box(modifier = Modifier.testTag("next_button_wrapper").semantics { testTagsAsResourceId = true }.align(Alignment.CenterHorizontally).widthIn(max = 720.dp).padding(bottom = 16.dp)) {
                Row {
                    Text(text = data.label)
                    Text(text = data.helper)
                    Text(text = data.caption)
                    Text(text = data.footnote)
                }
            }
            Box(modifier = Modifier.testTag("prev_button_wrapper").semantics { testTagsAsResourceId = true }.align(Alignment.CenterHorizontally).widthIn(max = 720.dp).padding(bottom = 16.dp)) {
                Row {
                    Text(text = data.label2)
                    Text(text = data.helper2)
                    Text(text = data.caption2)
                    Text(text = data.footnote2)
                }
            }
        }
      KOTLIN
      new_body, fns = described_class.extract(body, **opts, line_threshold: 6)

      # The `.align(` calls stay in the body — both Box chunks are not lifted.
      expect(new_body.scan('.align(Alignment.CenterHorizontally)').size).to eq(2)
      fns.each { |f| expect(f).not_to include('.align(') }
      # Recursion still reaches the inner Row → Text children.
      expect(fns.size).to be >= 4
    end

    # Regression: kjui-section-extractor-val-var-guard-blocks-text-resolve-pattern.
    # The previous guard (`children_have_val_var_sibling?`) refused to split
    # any parent that had a `val foo = ...` child, on the assumption that
    # such a binding might be consumed by a sibling that the extractor would
    # otherwise strand. Now `merge_val_chunks` runs first: each val is fused
    # with the latest subsequent sibling that references its name, so the
    # fused chunk travels as a single liftable unit. For the TextField state
    # pattern, this means val + LaunchedEffect + CustomTextField merge into
    # one Section that self-contains the binding.
    it 'fuses `val textFieldState_x = ...` with every subsequent referencing sibling so the merged chunk lifts as a single section' do
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
      expect(fns).not_to be_empty
      # One Section function must own the entire textFieldState_one cluster:
      # the val declaration plus both consumers.
      merged = fns.find { |f| f.include?('val textFieldState_one') }
      expect(merged).not_to be_nil
      expect(merged).to include('LaunchedEffect(textFieldState_one.text)')
      expect(merged).to include('CustomTextField(')
      expect(merged).to include('state = textFieldState_one')
      # No val/var leaks back to the parent body — every binding sits inside
      # its Section function.
      expect(new_body).not_to include('val textFieldState_one')
    end

    # Regression: kjui-section-extractor-val-var-guard-blocks-text-resolve-pattern.
    # The mypage Text emit pattern: each Text node generates a
    # `val resolved_textNNN = Configuration.Font.resolve(FontSpec(...))`
    # immediately followed by the Text consumer that reads four fields off
    # the binding. The bug report shows 308 such pairs in MypageGeneratedView;
    # the old val guard refused to split any wrapper Column containing this
    # pattern, leaving ~800 lines per section copy inline.
    it 'fuses `val resolved_textNNN = Configuration.Font.resolve(...)` with the immediately-following Text consumer' do
      body = <<~KOTLIN
        Column(modifier = Modifier.testTag("hero_section")) {
            Box(modifier = Modifier.testTag("avatar")) {
                AsyncImage(model = data.userAvatarUrl)
            }
            val resolved_text348 = Configuration.Font.resolve(FontSpec(
                family = null,
                weight = FontWeight.Bold,
                size = 23.sp,
                italic = false
            ))
            Text(
                text = "${data.userDisplayName}",
                fontFamily = resolved_text348.family,
                fontWeight = resolved_text348.weight,
                fontSize = resolved_text348.size ?: TextUnit.Unspecified
            )
            val resolved_text349 = Configuration.Font.resolve(FontSpec(
                family = null,
                weight = null,
                size = 15.sp,
                italic = false
            ))
            Text(
                text = "${data.userHandle}",
                fontFamily = resolved_text349.family,
                fontWeight = resolved_text349.weight,
                fontSize = resolved_text349.size ?: TextUnit.Unspecified
            )
        }
      KOTLIN

      new_body, fns = described_class.extract(body, **opts, line_threshold: 10)

      # 3 children of the wrapper Column lift cleanly: the Box, plus two
      # (val + Text) merged pairs.
      expect(fns.size).to eq(3)

      # Each resolved_textNNN binding ends up in the SAME Section function
      # as its Text consumer.
      pair348 = fns.find { |f| f.include?('val resolved_text348') }
      expect(pair348).not_to be_nil
      expect(pair348).to include('"${data.userDisplayName}"')
      expect(pair348).to include('fontFamily = resolved_text348.family')

      pair349 = fns.find { |f| f.include?('val resolved_text349') }
      expect(pair349).not_to be_nil
      expect(pair349).to include('"${data.userHandle}"')
      expect(pair349).to include('fontFamily = resolved_text349.family')

      # No val survives in the parent body.
      expect(new_body).not_to include('val resolved_text348')
      expect(new_body).not_to include('val resolved_text349')
      # Three Section calls inside the wrapper Column.
      expect(new_body.scan(/Section\d+(?:_\d+)*\(data, viewModel\)/).size).to eq(3)
    end

    # Regression: kjui-section-extractor-responsive-else-branch-not-lifted.
    # When the outer responsive `if/else` already has the regular branch's
    # children lifted (so its container holds only `SectionN(data, viewModel)`
    # calls) and the else branch is still inline, find_splittable_children
    # would tie on `total_lines` (the lifted Section calls are 1 line each,
    # but so are any single-leaf chunks) and keep picking the already-lifted
    # container on every iteration, never reaching the else branch. The
    # `all_children_already_lifted?` skip lets the search move past the
    # exhausted regular branch and process the inline else branch.
    it 'lifts inside the outer else-branch when the outer if-branch is already fully lifted' do
      # Outer responsive: if (regular) Row else Column. Each branch contains
      # the SAME panel-responsive sub-tree (nested if/else with .weight on
      # the regular sub-branch). Without the skip, only the outer if-branch
      # gets its sub-branches lifted; the outer else-branch stays inline.
      panel_responsive = <<~K.chomp
        if (cond2) {
            Column(
                modifier = Modifier
                    .testTag("regular_panel")
                    .weight(1f)
            ) {
                Column(modifier = Modifier.testTag("hero")) {
                    Text(text = data.a)
                    Text(text = data.b)
                }
                Column(modifier = Modifier.testTag("taste")) {
                    Text(text = data.c)
                    Text(text = data.d)
                }
            }
        } else {
            Column(modifier = Modifier.testTag("default_panel")) {
                Column(modifier = Modifier.testTag("hero")) {
                    Text(text = data.a)
                    Text(text = data.b)
                }
                Column(modifier = Modifier.testTag("taste")) {
                    Text(text = data.c)
                    Text(text = data.d)
                }
            }
        }
      K
      indented = panel_responsive.lines.map { |l| "            #{l}" }.join
      body = <<~KOTLIN
        Column(modifier = Modifier.fillMaxSize()) {
            if (cond) {
                Row(modifier = Modifier.fillMaxWidth()) {
        #{indented}
                }
            } else {
                Column(modifier = Modifier.fillMaxWidth()) {
        #{indented}
                }
            }
        }
      KOTLIN
      new_body, fns = described_class.extract(body, **opts, line_threshold: 10)

      # Branch extraction lifts the outer if/else branch bodies wholesale
      # (ColumnScope-receiver extensions, since the gate sits inside the
      # wrapper Column), then recurses so the nested panel-responsive gates
      # inside each lifted branch are split further. Nothing content-shaped
      # stays inline in the outer body.
      expect(fns.size).to be >= 2
      expect(new_body.scan(/testTag\("hero"\)/).size).to eq(0)
      expect(new_body.scan(/testTag\("taste"\)/).size).to eq(0)
      expect(new_body.scan(/testTag\("regular_panel"\)/).size).to eq(0)
      expect(new_body.scan(/testTag\("default_panel"\)/).size).to eq(0)
      # Every hero/taste/panel occurrence lives inside SOME lifted function
      # (both outer branches' copies).
      all_fns = fns.join("\n")
      # hero/taste appear once per panel-responsive branch (regular+default)
      # per outer branch = 4 copies; panel wrappers once per outer branch = 2.
      expect(all_fns.scan(/testTag\("hero"\)/).size).to eq(4)
      expect(all_fns.scan(/testTag\("taste"\)/).size).to eq(4)
      expect(all_fns.scan(/testTag\("regular_panel"\)/).size).to eq(2)
      expect(all_fns.scan(/testTag\("default_panel"\)/).size).to eq(2)
    end

    # Regression: kjui-section-extractor-val-merge-breaks-collection-cell-scope.
    # `items(N) { cellIndex -> ... }` introduces a lambda-scope parameter and
    # the body typically references outer LazyListScope locals like
    # `val cellData0 = section0?.cells` and items-scope locals like
    # `val cellViewModel = viewModel(key = ...)`. After the val+consumer merge
    # batch, the merged chunk and the BarInfoCellView consumer were getting
    # lifted to file-scope `private fun SectionN(data, viewModel)` helpers
    # where `cellIndex` / `cellData0` / `cellViewModel` no longer resolve
    # — 100 compile errors across 4 Collection-using screens (item_detail,
    # chat, history_confirm, item_detail). The fix: a chunk
    # that references any kjui Collection-emit local without declaring it
    # itself cannot be lifted; the chunk stays inline inside its lambda.
    it 'does not lift chunks that reference Collection cell-scope locals (cellIndex / cellData0 / cellViewModel)' do
      body = <<~KOTLIN
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            val section0 = data.contentSections?.sections?.getOrNull(0)
            val cellData0 = section0?.cells
            if (section0 != null) {
                if (cellData0 != null) {
                    items(cellData0.data.size, key = { idx -> idx.toString() }) { cellIndex ->
                        val currentCellData = cellData0.data[cellIndex]
                        val cellId = (currentCellData["cellId"] as? String) ?: "$cellIndex"
                        val cellViewModel: BarInfoCellViewModel = viewModel(key = "item_detail/bar_info_cell_cell_0_${cellId}_${viewModel.hashCode()}")
                        LaunchedEffect(currentCellData) { cellViewModel.updateData(currentCellData) }
                        BarInfoCellView(
                            viewModel = cellViewModel,
                            modifier = Modifier.testTag("content_list_item_$cellIndex").fillMaxWidth()
                        )
                    }
                }
            }
        }
      KOTLIN

      new_body, fns = described_class.extract(
        body,
        view_name: 'BarDetail',
        data_type: 'BarDetailData',
        viewmodel_type: 'BarDetailViewModel',
        line_threshold: 10
      )

      # No section function is allowed to mention any cell-scope local that
      # would be unresolved at file scope.
      fns.each do |f|
        expect(f).not_to include('cellIndex')
        expect(f).not_to include('cellData0')
        expect(f).not_to include('cellViewModel')
        expect(f).not_to include('currentCellData')
      end

      # The items lambda body stays intact — every reference still lives
      # inside its declaring scope.
      expect(new_body).to include('items(cellData0.data.size')
      expect(new_body).to include('val currentCellData = cellData0.data[cellIndex]')
      expect(new_body).to include('BarInfoCellView(')
    end

    # Regression: kjui-section-extractor-free-var-heuristic-misses-pagerstate.
    # `val pagerState = rememberPagerState(...)` is consumed by multiple
    # subsequent siblings (initial LaunchedEffect, snapshotFlow
    # LaunchedEffect, PageIndicator, HorizontalPager) that are *not
    # themselves vals* and may be separated by unrelated children. The
    # previous single-forward-scan merge only captured the chain up to the
    # last sibling that declared a downstream val (here: the initial
    # LaunchedEffect with `val target`), leaving the later pagerState
    # consumers as standalone lift candidates. They'd be lifted into
    # file-scope Section functions where `pagerState` no longer resolved,
    # producing 35 errors across history_confirm and item_detail.
    # The fix: scan all previously-emitted result chunks (not just adjacent),
    # and absorb every child plus any intermediate chunks into the earliest
    # chunk whose declared vals are referenced.
    it 'pulls every pagerState consumer into the same Section as the `val pagerState = rememberPagerState(...)` declaration' do
      body = <<~KOTLIN
        Column(modifier = Modifier.fillMaxSize()) {
            Text(text = data.title)
            val pageCount = data.candidateItems?.sections?.firstOrNull()?.cells?.data?.size ?: 0
            val pagerState = rememberPagerState(initialPage = data.currentPage) { pageCount }
            LaunchedEffect(data.currentPage) {
                val target = data.currentPage.coerceIn(0, (pageCount - 1).coerceAtLeast(0))
                if (pagerState.currentPage != target) pagerState.animateScrollToPage(target)
            }
            LaunchedEffect(pagerState) {
                snapshotFlow { pagerState.currentPage }.collect { page ->
                    viewModel.updateData(mapOf("currentPage" to page))
                    data.onPageChanged?.invoke(page)
                }
            }
            PageIndicator(
                pagerState = pagerState,
                modifier = Modifier.fillMaxWidth()
            )
            HorizontalPager(
                state = pagerState,
                modifier = Modifier.fillMaxSize()
            ) { page ->
                Text(text = "$page")
            }
            Text(text = data.footer)
        }
      KOTLIN

      new_body, fns = described_class.extract(
        body, **opts, line_threshold: 10
      )

      # All pagerState references end up inside the SAME Section function
      # — the one that also carries `val pagerState = rememberPagerState`.
      decl_fn = fns.find { |f| f.include?('val pagerState = rememberPagerState') }
      expect(decl_fn).not_to be_nil
      expect(decl_fn).to include('snapshotFlow { pagerState.currentPage }')
      expect(decl_fn).to include('PageIndicator(')
      expect(decl_fn).to include('pagerState = pagerState')
      expect(decl_fn).to include('HorizontalPager(')
      expect(decl_fn).to include('state = pagerState')

      # No other Section function carries an unresolved `pagerState` reference.
      fns.each do |f|
        next if f.equal?(decl_fn)
        expect(f).not_to include('pagerState')
      end

      # No `pagerState` token leaks into the parent body — every occurrence
      # sits inside the merged Section function.
      expect(new_body).not_to include('pagerState')
    end

    # Regression: kjui-section-extractor-lift-into-lazygridscope.
    # kjui codegen emits `// Section N: <id> (M columns)` header comments
    # as direct children of `LazyVerticalGrid { ... }` (and other Lazy*Scope
    # containers). Before this fix, a comment-only chunk passed every
    # cannot_lift? guard and got promoted into an effectively-empty
    # `@Composable private fun SectionN(data, viewModel) {}`. The call
    # site `SectionN(data, viewModel)` then sat inside LazyGridScope —
    # `@LazyScopeMarker` forbids direct @Composable invocations there,
    # producing `@Composable invocations can only happen from the context
    # of a @Composable function`. Two errors across shop_items_list and
    # favorite_list.
    it 'refuses to lift a comment-only chunk inside a LazyVerticalGrid LazyGridScope body' do
      body = <<~KOTLIN
        Column(modifier = Modifier.fillMaxSize()) {
            Text(text = data.title)
            if (with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp().value.toInt() } >= 840) {
                LazyVerticalGrid(
                    columns = GridCells.Fixed(5),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    // Section 1: shop_items_list/shop_item_list_item (5 columns)
                    data.gridItems?.sections?.getOrNull(0)?.let { section ->
                        section.cells?.let { cellData ->
                            items(cellData.data.size, key = { idx -> idx.toString() }) { cellIndex ->
                                LaunchedEffect(Unit) { data.onItemAppear?.invoke(cellIndex) }
                                Box(modifier = Modifier.fillMaxWidth()) {
                                    Text(text = data.label)
                                }
                            }
                        }
                    }
                }
            } else {
                Text(text = data.fallback)
            }
            Text(text = data.footer)
        }
      KOTLIN

      new_body, fns = described_class.extract(
        body,
        view_name: 'ItemsList',
        data_type: 'ItemsListData',
        viewmodel_type: 'ItemsListViewModel',
        line_threshold: 10
      )

      # Branch extraction may relocate the whole gate (grid included) into a
      # lifted function; the invariants are location-independent:
      everything = ([new_body] + fns).join("\n")

      # 1. The comment header survives exactly once, still inside the
      #    LazyVerticalGrid body — never wrapped into its own Section.
      expect(everything.scan('// Section 1: shop_items_list/shop_item_list_item (5 columns)').size).to eq(1)

      # 2. No lifted function carries just a comment line as its body.
      fns.each do |f|
        body_lines = f.lines[5..-2] || []  # rough body slice (skip signature)
        body_text = body_lines.map(&:strip).reject(&:empty?).join("\n")
        expect(body_text).not_to match(/\A\/\/[^\n]*\z/m)
      end

      # 3. No `SectionN(data, viewModel)` call appears on the line
      #    immediately after the LazyVerticalGrid opener (wherever the grid
      #    ended up) — the comment line must still be the first child; a
      #    Section call there would sit in LazyGridScope where @Composable
      #    invocations are forbidden.
      lines = everything.lines.map(&:chomp)
      grid_open = lines.find_index { |l| l.include?('LazyVerticalGrid(') }
      expect(grid_open).not_to be_nil
      body_start = lines.each_with_index.find { |l, i| i > grid_open && l.strip.end_with?('{') }&.last
      expect(body_start).not_to be_nil
      first_inside = lines[(body_start + 1)..].find { |l| !l.strip.empty? }
      expect(first_inside).not_to match(/Section\d+(?:_\d+)*\(data, viewModel\)/)
    end

    it 'lifts inside both branches of a responsive if/else so the duplication shrinks to single-line calls' do
      # The if/else duplicates the body across size-class branches. After
      # extraction, each branch references the same SectionN helpers, so
      # the bytecode cost of the duplicated branch drops to N function-call
      # opcodes regardless of how large each section body is.
      body = <<~KOTLIN
        if (with(LocalDensity.current) { LocalWindowInfo.current.containerSize.width.toDp().value.toInt() } >= 840) {
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
      # Branch extraction lifts EACH branch body wholesale into its own
      # Section function (recursing within), so the gate skeleton shrinks to
      # exactly one call per branch — the strongest possible shape for the
      # JVM/ART method-size ceilings.
      expect(fns.size).to be >= 2
      expect(new_body.scan(/Section\d+(?:_\d+)*\(data, viewModel\)/).size).to eq(2)
      # The body itself shouldn't carry the duplicated literal Texts.
      expect(new_body.scan('Text(text = data.line1)').size).to eq(0)
    end
  end

  # ---- depth bounding (2026-07-28 batch) ------------------------------------

  describe 'depth-bounded extraction' do
    let(:opts) do
      { view_name: 'DeepView', data_type: 'DeepViewData', viewmodel_type: 'DeepViewViewModel' }
    end

    def spine(levels, leaf: 'Text("leaf")')
      lines = []
      levels.times { |i| lines << ('    ' * i) + (i.zero? ? 'Box(modifier = Modifier.fillMaxSize()) {' : 'Column {') }
      lines << ('    ' * levels) + leaf
      (levels - 1).downto(0) { |i| lines << ('    ' * i) + '}' }
      lines.join("\n")
    end

    def functions_within_bounds?(fns)
      fns.all? do |fn|
        depth = described_class.body_depth(fn) - 1
        depth <= described_class::HARD_BODY_DEPTH
      end
    end

    it 'triggers on depth even when the body is under the line threshold' do
      body = spine(10)
      expect(body.lines.size).to be < 100
      new_body, fns, waivers = described_class.extract(body, **opts)
      expect(fns).not_to be_empty
      expect(waivers).to be_empty
      expect(described_class.body_depth(new_body)).to be <= described_class::HARD_BODY_DEPTH
      expect(functions_within_bounds?(fns)).to be true
    end

    it 'packs several levels per function instead of one wrapper per level' do
      _new_body, fns, = described_class.extract(spine(12), **opts)
      expect(fns.size).to be <= 4
    end

    it 'measures depth on braces, ignoring template braces inside strings' do
      expect(described_class.body_depth('Text("${a} { } ${b}")')).to eq(0)
    end

    it 'reports a waiver instead of silently shipping an unboundable body' do
      # Lazy DSL all the way down: the chunk cannot be lifted.
      lines = ['LazyColumn {']
      8.times { |i| lines << ('    ' * (i + 1)) + 'items(10) { cellIndex ->' }
      lines << ('    ' * 9) + 'Text("deep $cellIndex")'
      8.downto(1) { |i| lines << ('    ' * i) + '}' }
      lines << '}'
      body = lines.join("\n")
      new_body, _fns, waivers = described_class.extract(body, **opts)
      expect(described_class.body_depth(new_body)).to be > described_class::HARD_BODY_DEPTH
      expect(waivers).not_to be_empty
    end

    it 'lifts a scope-bound spine as a receiver extension' do
      lines = ['Column {']
      lines << '    Box(modifier = Modifier.weight(1f)) {'
      8.times { |i| lines << ('    ' * (i + 2)) + 'Column {' }
      lines << ('    ' * 10) + 'Text("deep")'
      7.downto(0) { |i| lines << ('    ' * (i + 2)) + '}' }
      lines << '    }'
      lines << '}'
      new_body, fns, waivers = described_class.extract(lines.join("\n"), **opts)
      expect(waivers).to be_empty
      expect(described_class.body_depth(new_body)).to be <= described_class::HARD_BODY_DEPTH
      expect(functions_within_bounds?(fns)).to be true
      # The .weight-carrying segment must ride a ColumnScope receiver if lifted whole.
      scoped = fns.select { |f| f.include?('.weight(') }
      scoped.each do |f|
        expect(f).to include('androidx.compose.foundation.layout.ColumnScope.') if f.match?(/private fun \S*Section/)
      end
    end
  end

end
