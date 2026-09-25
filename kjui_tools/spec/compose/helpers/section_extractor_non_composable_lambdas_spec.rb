# frozen_string_literal: true

require 'compose/helpers/section_extractor'
require 'compose/compose_builder'
require 'json'
require 'tmpdir'
require 'stringio'

# kjui-section-extractor-lifts-statements-out-of-an-androidview-factory.
#
# The depth-driven cut took any line that starts with a capital letter for a
# Compose container. Once a Web / WebView sat deep enough — the Box an id
# adds, a visibility wrapper, or plain nesting each add a level — the deepest
# point was inside AndroidView's `factory = { context -> WebView(context)
# .apply { … } }`, and the statements on the WebView were lifted into
# `@Composable` SectionN functions. They lost their receiver ("Unresolved
# reference 'settings'") and were called where no @Composable call can be
# made. `jui build` exited 0; Gradle was the first to say anything.
RSpec.describe KjuiTools::Compose::Helpers::SectionExtractor do
  let(:opts) { { view_name: 'Probe', data_type: 'ProbeData', viewmodel_type: 'ProbeViewModel' } }

  # The spec's own spelling of a lifted call, so the arms read the output
  # the same way whatever the implementation calls it.
  LIFTED_CALL = /\bSection\d+(?:_\d+)*\(data, viewModel\b/.freeze

  # The text of the lambda opened by the first `opener`, braces balanced.
  def lambda_text(src, opener)
    start = src.index(opener) or return nil
    depth = 0
    open = src.index('{', start)
    (open...src.size).each do |k|
      depth += 1 if src[k] == '{'
      depth -= 1 if src[k] == '}'
      return src[open..k] if depth.zero?
    end
    nil
  end

  # Every converter that emits an AndroidView, and the layout type it
  # converts. The matrix below runs each of them.
  ANDROID_VIEW_CONVERTERS = {
    'web_component.rb' => 'Web',
    'webview_component.rb' => 'WebView'
  }.freeze

  it 'runs every converter that emits an AndroidView (a new one joins the matrix)' do
    components = File.expand_path('../../../lib/compose/components', __dir__)
    emitting = Dir.glob(File.join(components, '*.rb'))
                  .select { |f| File.read(f).include?('indent("AndroidView(') }
                  .map { |f| File.basename(f) }.sort
    expect(emitting).to eq(ANDROID_VIEW_CONVERTERS.keys.sort)
  end

  describe 'a Web / WebView deep enough to be cut' do
    let(:temp_dir) { Dir.mktmpdir('kjui_android_view_depth') }
    let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }

    before do
      FileUtils.mkdir_p(layouts_dir)
      config = { 'source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts',
                 'view_directory' => 'kotlin/com/example/app/views', 'package_name' => 'com.example.app' }
      allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
      allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
      allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
      allow(Dir).to receive(:pwd).and_return(temp_dir)
    end

    after { FileUtils.rm_rf(temp_dir) }

    def screen(type, id:, visibility:, nest:)
      web = { 'type' => type, 'width' => 'matchParent', 'height' => 200, 'url' => '@{pageUrl}' }
      web['id'] = 'page' if id
      web['visibility'] = '@{pageVisibility}' if visibility
      nest.times { web = { 'type' => 'View', 'orientation' => 'vertical', 'child' => [web] } }
      { 'type' => 'View', 'orientation' => 'vertical', 'width' => 'matchParent', 'height' => 'matchParent',
        'child' => [{ 'data' => [{ 'name' => 'pageUrl', 'class' => 'String', 'defaultValue' => '' },
                                 { 'name' => 'pageVisibility', 'class' => 'Visibility', 'defaultValue' => 'visible' }] },
                    web] }
    end

    # [generated source, layouts the build recorded as failed, what it printed]
    def build(layout)
      File.write(File.join(layouts_dir, 'probe.json'), JSON.generate(layout))
      builder = KjuiTools::Compose::ComposeBuilder.new
      printed = StringIO.new
      $stdout = printed
      begin
        builder.build_file(File.join(layouts_dir, 'probe.json'))
      ensure
        $stdout = STDOUT
      end
      [File.read(Dir.glob(File.join(temp_dir, '**', 'ProbeGeneratedView.kt')).first), builder.failed_files,
       printed.string]
    end

    # The build ends non-zero on a recorded failure (build.rb exits 1 on the
    # failed_files list), so a refused cut stops `jui build` by name
    # instead of shipping Kotlin that only Gradle rejects.
    it 'records the layout as failed when the check refuses a cut' do
      allow(described_class).to receive(:extract)
        .and_raise(described_class::UnsafeCutError, 'section extractor: probe refusal')
      _src, failed, printed = build(screen('Web', id: true, visibility: true, nest: 0))
      expect(failed.map { |f| File.basename(f) }).to eq(['probe.json'])
      expect(printed).to include('section extractor: probe refusal')
    end

    # id + visibility is the reported layout; the others reach the same
    # depth through nesting instead (measured on 1.8.119: every one of them
    # put 5 section calls in the factory).
    SHAPES = [
      { id: true, visibility: true, nest: 0 },
      { id: true, visibility: false, nest: 1 },
      { id: false, visibility: true, nest: 1 },
      { id: false, visibility: false, nest: 2 },
      { id: true, visibility: true, nest: 3 }
    ].freeze

    ANDROID_VIEW_CONVERTERS.each_value do |type|
      SHAPES.each do |shape|
        it "keeps the #{type} factory whole (#{shape.map { |k, v| "#{k}=#{v}" }.join(', ')})" do
          src, failed, = build(screen(type, **shape))
          expect(failed).to be_empty

          factory = lambda_text(src, 'factory = { context ->')
          expect(factory).to include('settings.javaScriptEnabled = true')
          expect(factory).not_to match(LIFTED_CALL)
          expect(lambda_text(src, 'WebView(context).apply {')).to include('loadUrl(data.pageUrl)')
          expect(lambda_text(src, 'update = { webView ->')).not_to match(LIFTED_CALL)

          # The body was still cut — the AndroidView travels whole inside a
          # section — so this is not the extractor switched off.
          expect(src).to match(/private fun Section\w+\(/)
        end
      end
    end
  end

  describe 'lambdas that are not @Composable content, in general' do
    # The same defect without a WebView: a LaunchedEffect block is a
    # coroutine, and a capital letter inside it (`Snapshot.withMutableSnapshot
    # {`) or the block itself used to read as a container.
    def launched_effect_body(statements)
      <<~KOTLIN
        Column {
            Row {
                Box {
                    LaunchedEffect(data.key) {
        #{statements.map { |s| s.gsub(/^/, ' ' * 16) }.join("\n")}
                    }
                }
            }
        }
      KOTLIN
    end

    let(:statement) do
      <<~KOTLIN.chomp
        if (data.ready) {
            Snapshot.withMutableSnapshot {
                Log.d("probe", "ready")
            }
        }
      KOTLIN
    end

    it 'does not lift the statements of a LaunchedEffect block' do
      new_body, fns = described_class.extract(launched_effect_body([statement] * 4), **opts)
      block = lambda_text(([new_body] + fns).join("\n"), 'LaunchedEffect(data.key) {')
      expect(block.scan('Snapshot.withMutableSnapshot {').size).to eq(4)
      expect(block).not_to match(LIFTED_CALL)
      expect(fns).not_to be_empty # the Box around it still lifts
    end

    it 'does not lift the branches of a large if / else inside a LaunchedEffect' do
      branch = (1..60).map { |i| "Log.d(\"probe\", \"#{i}\")" }
      gate = ["if (data.ready) {", *branch.map { |l| "    #{l}" }, "} else {", *branch.map { |l| "    #{l}" }, "}"]
      new_body, fns = described_class.extract(launched_effect_body([gate.join("\n")]), **opts)
      block = lambda_text(([new_body] + fns).join("\n"), 'LaunchedEffect(data.key) {')
      expect(block.scan('Log.d("probe"').size).to eq(120)
      expect(block).not_to match(LIFTED_CALL)
    end
  end

  describe 'a lambda the kinds do not know' do
    # `topBar` is a @Composable slot, but not one kjui emits, so it reads as
    # :opaque. The cut paths refuse the same lambdas the final check refuses:
    # the body is cut outside it, and nothing is cut and then rejected.
    let(:body) do
      <<~KOTLIN
        Column {
            Row {
                Scaffold(
                    topBar = {
                        Box {
                            CollectionStack(
                                lazyContent = {
                                    Box {
                                        Column {
                                            Text(text = data.a)
                                            Text(text = data.b)
                                        }
                                    }
                                }
                            )
                            Row {
                                Box {
                                    Text(text = data.c)
                                    Text(text = data.d)
                                }
                            }
                        }
                    }
                ) {
                    Text(text = data.title)
                }
            }
        }
      KOTLIN
    end

    it 'is left whole, and the body is cut outside it' do
      new_body, fns = described_class.extract(body, **opts)
      top_bar = lambda_text(([new_body] + fns).join("\n"), 'topBar = {')
      expect(top_bar.scan(/Text\(text = data\.[abcd]\)/).size).to eq(4)
      expect(top_bar).not_to match(LIFTED_CALL)
      expect(fns).not_to be_empty
    end
  end

  describe '.lambda_kind' do
    def kind(snippet)
      lines = snippet.lines.map(&:chomp)
      described_class.lambda_kind(lines, lines.size - 1)
    end

    # Pairs on either side of each boundary: the same surface with the
    # opposite answer.
    {
      'Box {' => :composable,
      'WebView(context).apply {' => :opaque,
      "Column(\n    modifier = Modifier.fillMaxSize()\n) {" => :composable,
      "LaunchedEffect(\n    data.key\n) {" => :opaque,
      'LaunchedEffect(data.key) {' => :opaque,
      'lazyContent = {' => :composable,
      'placeholder = {' => :composable,
      'factory = { context ->' => :opaque,
      'update = { webView ->' => :opaque,
      'onClick = {' => :opaque,
      'section?.let { cellData ->' => :transparent,
      'cellData.data.forEachIndexed { cellIndex, item ->' => :transparent,
      'mutableListOf("all").apply {' => :opaque,
      'if (data.ready) {' => :transparent,
      '} else {' => :transparent,
      "if (\n    data.ready\n) {" => :transparent,
      '"tab" -> {' => :transparent,
      'items(cells.size, key = { idx -> idx }) { cellIndex ->' => :composable,
      'key(cellId) {' => :composable,
      'remember {' => :opaque
    }.each do |snippet, expected|
      it "reads #{snippet.lines.map(&:strip).join(' ').inspect} as #{expected}" do
        expect(kind(snippet)).to eq(expected)
      end
    end
  end

  describe 'the check on every cut' do
    it 'raises when a section call stands inside a lambda that is not @Composable' do
      body = <<~KOTLIN
        AndroidView(
            factory = { context ->
                WebView(context).apply {
                    Section0_0(data, viewModel)
                }
            }
        )
      KOTLIN
      expect { described_class.assert_calls_composable!(body, 'Probe') }
        .to raise_error(described_class::UnsafeCutError, /inside `WebView\(context\)\.apply \{`/)
    end

    it 'accepts section calls where a @Composable call can be made' do
      body = <<~KOTLIN
        Column {
            Section0(data, viewModel)
            if (data.ready) {
                Section1(data, viewModel)
            }
            CollectionStack(
                lazyContent = {
                    Section2(data, viewModel)
                }
            )
            cellData.data.forEachIndexed { cellIndex, item ->
                Section3(data, viewModel, cellIndex, item)
            }
        }
      KOTLIN
      expect { described_class.assert_calls_composable!(body, 'Probe') }.not_to raise_error
    end

    it 'runs on what extract returns, whichever step put the call there' do
      body = <<~KOTLIN
        Column {
            Row {
                Box {
                    AndroidView(
                        factory = { context ->
                            WebView(context).apply {
                                Section9(data, viewModel)
                            }
                        }
                    )
                }
            }
        }
      KOTLIN
      expect { described_class.extract(body, **opts) }.to raise_error(described_class::UnsafeCutError)
    end
  end
end
