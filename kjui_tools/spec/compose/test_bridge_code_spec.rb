# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'stringio'
require 'compose/compose_builder'
require 'compose/data_model_updater'
require 'compose/test_bridge_code'
require 'core/config_manager'
require 'core/project_finder'

# The test bridge kjui emits (jsonui-test-runner spec section 10.3-10.4):
# testDeclaredClasses / applyTestInitialState / testSnapshot on every Data
# class, rememberTestBridge beside every screen's marker, and an updateData
# that takes the null an optional field may be set to. Whether a value fits
# is KotlinJsonUI's JsonUITestValue.check, unit-tested there against the
# shared coercion vector; these arms hold the code around it — above all that
# the class it judges by is the class the layout wrote.
module TestBridgeCodeSpec
  # A judge that accepts every value as it is: the arm asks about the code
  # kjui writes around the check (the map it passes, the update it calls,
  # the null it lets through, the colour it resolves), not about the check.
  JUDGE = <<~KOTLIN
    package com.kotlinjsonui.core

    data class RejectedKey(val key: String, val reason: String)
    sealed interface TestValueVerdict {
        data class Accepted(val value: Any?) : TestValueVerdict
        data class Rejected(val reason: String) : TestValueVerdict
    }
    object JsonUITestValue {
        var judgedBy: Map<String, String> = emptyMap()
        fun applyAll(
            values: Map<String, Any?>,
            declared: Map<String, String>,
            update: ((Map<String, Any?>) -> Unit)?,
            resolve: (key: String, accepted: Any?) -> TestValueVerdict = { _, v -> TestValueVerdict.Accepted(v) }
        ): List<RejectedKey> {
            judgedBy = declared
            val accepted = LinkedHashMap<String, Any?>()
            val rejected = mutableListOf<RejectedKey>()
            for ((key, value) in values) {
                if (key !in declared) { rejected += RejectedKey(key, "not a data field"); continue }
                when (val v = resolve(key, value)) {
                    is TestValueVerdict.Accepted ->
                        if (update == null) rejected += RejectedKey(key, "viewModel has no updateData") else accepted[key] = v.value
                    is TestValueVerdict.Rejected -> rejected += RejectedKey(key, v.reason)
                }
            }
            if (update != null && accepted.isNotEmpty()) update(accepted)
            return rejected
        }
        fun resolveColor(accepted: Any?, declaredClass: String, colorOf: (String) -> Any?): TestValueVerdict =
            when (accepted) {
                null -> TestValueVerdict.Accepted(null)
                is String -> colorOf(accepted)?.let { TestValueVerdict.Accepted(it) }
                    ?: TestValueVerdict.Rejected("type mismatch: expected $declaredClass")
                else -> TestValueVerdict.Rejected("type mismatch: expected $declaredClass")
            }
        fun snapshot(values: Map<String, Any?>, declared: Map<String, String>): Map<String, Any?> =
            values.filterKeys { declared[it] != null && !declared.getValue(it).startsWith("Color") && !declared.getValue(it).contains("->") }
    }
  KOTLIN

  COLOR_STUBS = <<~KOTLIN
    package androidx.compose.ui.graphics
    // androidx's Color holds a ULong and is built from an ARGB Long.
    data class Color(val value: ULong)
    fun Color(argb: Long): Color = Color(argb.toULong())
  KOTLIN

  COLOR_MANAGER_STUBS = <<~KOTLIN
    package com.kotlinjsonui.generated
    import androidx.compose.ui.graphics.Color
    object ColorManager { object compose { fun colorOrHex(value: String): Color? = if (value == "red") Color(0xFFFF0000) else null } }
  KOTLIN
end

RSpec.describe 'test bridge (kjui)' do
  let(:vector_cases) do
    JSON.parse(File.read(File.expand_path('../../../shared/core/initial_state_coercion_vectors.json', __dir__)))['cases']
  end

  let(:dir) { Dir.mktmpdir('kjui_test_bridge') }

  before do
    %w[Layouts Data Styles].each { |d| FileUtils.mkdir_p(File.join(dir, d)) }
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
      'source_directory' => '', 'layouts_directory' => 'Layouts', 'data_directory' => 'Data',
      'styles_directory' => 'Styles', 'package_name' => 'com.example.app', 'mode' => 'compose'
    )
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
  end

  before(:context) { @kept_process_state = ProcessStateGuard.keep(KjuiTools::Core::TypeConverter) }
  after(:context) { ProcessStateGuard.put_back(@kept_process_state) }

  after { FileUtils.rm_rf(dir) }

  # [ScreenData.kt, the updater, {property => item['class'] finalize was given}]
  def build_data(items)
    File.write(File.join(dir, 'Layouts', 'screen.json'),
               JSON.generate('type' => 'View', 'id' => 'root', 'data' => items))
    updater = KjuiTools::Compose::DataModelUpdater.new
    written_class = {}.compare_by_identity
    allow(updater).to receive(:finalize_data_property).and_wrap_original do |original, item, bindings|
      property = original.call(item, bindings)
      written_class[property] = item['class']
      property
    end
    out = StringIO.new
    $stdout = out
    updater.send(:process_json_file, File.join(dir, 'Layouts', 'screen.json'))
    [File.read(File.join(dir, 'Data', 'ScreenData.kt')), updater, written_class]
  ensure
    $stdout = STDOUT
  end

  # testDeclaredClasses as emitted: [[name, class]] in order.
  def declared_classes(kotlin)
    block = kotlin[/val testDeclaredClasses: Map<String, String> = (?:emptyMap\(\)|mapOf\(\n(.*?)\n        \))/m, 1].to_s
    block.lines.map { |line| line.strip.sub(/,\z/, '') }.reject(&:empty?).map do |pair|
      pair.match(/\A"((?:\\.|[^"])*)" to "((?:\\.|[^"])*)"\z/).captures.map { |s| s.gsub(/\\(.)/, '\1') }
    end
  end

  describe 'the class the check judges by' do
    # The orchestrator's ask (2026-10-16): support-1's normalized['declaredClass']
    # is the class the layout wrote — finalize_data_property's input
    # item['class'] — not the class kjui converted it to.
    it "is the declaredClass the shared normalizer keeps, and that is the item's class as written" do
      classes = vector_cases.flat_map { |c| c['data'].map { |d| d['class'] } }.uniq
      expect(classes.size).to be > 25
      items = classes.each_with_index.map { |klass, i| { 'name' => "f#{i}", 'class' => klass } }

      kotlin, updater, written_class = build_data(items)
      declared = updater.send(:declared_data_properties).keys

      expect(declared.size).to eq(classes.size)
      declared.each { |prop| expect(prop['declaredClass']).to eq(written_class[prop]), prop['name'] }
      expect(declared.map { |prop| prop['declaredClass'] }).to eq(classes)
      # The converted class is another spelling for some of them — which is why
      # the check is not handed it (Boolean -> Bool, Integer -> Int, ...).
      expect(declared.count { |prop| prop['class'] != prop['declaredClass'] }).to be > 0
      expect(declared_classes(kotlin)).to eq(items.map { |i| [i['name'], i['class']] })
    end

    # Each case of the shared vector, as a layout: the Data class hands the
    # library exactly the case's {name => class}. With that, the library's
    # unit test of the same vector is the generated screen's answer.
    it 'is, for every case of the shared coercion vector, the case data verbatim' do
      expect(vector_cases.size).to be > 80
      vector_cases.each do |vector_case|
        kotlin, = build_data(vector_case['data'])
        expect(declared_classes(kotlin)).to eq(vector_case['data'].map { |d| [d['name'], d['class']] }), vector_case['name']
      end
    end

    it 'leaves out a field the generator adds by itself, as validate does' do
      File.write(File.join(dir, 'Layouts', 'screen.json'), JSON.generate(
        'type' => 'View', 'id' => 'root', 'data' => [{ 'name' => 'email', 'class' => 'String', 'defaultValue' => '' }],
        'child' => [{ 'type' => 'TextField', 'id' => 'email_field', 'text' => '@{email}' }]
      ))
      out = StringIO.new
      $stdout = out
      KjuiTools::Compose::DataModelUpdater.new.send(:process_json_file, File.join(dir, 'Layouts', 'screen.json'))
      $stdout = STDOUT
      kotlin = File.read(File.join(dir, 'Data', 'ScreenData.kt'))

      expect(kotlin).to include('var emailFieldIsFocused: Boolean')
      expect(declared_classes(kotlin)).to eq([%w[email String]])
    ensure
      $stdout = STDOUT
    end
  end

  describe 'what the Data class does with the judge' do
    def view_model(items)
      updates = KjuiTools::Compose::ComposeBuilder.new.send(
        :generate_update_data_function,
        items.map { |i| KjuiTools::Core::TypeConverter.normalize_data_property(i, 'compose') }, 'Screen'
      )
      <<~KOTLIN
        import com.example.app.data.ScreenData
        import androidx.compose.ui.graphics.Color
        import kotlinx.coroutines.flow.MutableStateFlow
        import kotlinx.coroutines.flow.StateFlow
        import kotlinx.coroutines.flow.asStateFlow
        import kotlinx.coroutines.flow.update

        class ScreenViewModel {
            private val _data = MutableStateFlow(ScreenData())
            val data: StateFlow<ScreenData> = _data.asStateFlow()
        #{updates}
        }
      KOTLIN
    end

    let(:items) do
      [
        { 'name' => 'email', 'class' => 'String', 'defaultValue' => 'old' },
        { 'name' => 'nickname', 'class' => 'String?', 'defaultValue' => 'nick' },
        { 'name' => 'count', 'class' => 'Integer', 'defaultValue' => 1 },
        { 'name' => 'agreed', 'class' => 'Boolean', 'defaultValue' => false },
        { 'name' => 'tint', 'class' => 'Color', 'defaultValue' => '#000000' },
        { 'name' => 'onTap', 'class' => '(() -> Void)?' }
      ]
    end

    def run_with(main_body)
      kotlin, = build_data(items)
      source = view_model(items) + "\n" + <<~KOTLIN
        fun main() {
            val vm = ScreenViewModel()
        #{main_body}
        }
      KOTLIN
      KotlinCompiler.run(source, files: {
        KotlinCompiler::TEST_BRIDGE_STUBS_FILE => TestBridgeCodeSpec::JUDGE,
        'Color.kt' => TestBridgeCodeSpec::COLOR_STUBS, 'ColorManager.kt' => TestBridgeCodeSpec::COLOR_MANAGER_STUBS, 'ScreenData.kt' => kotlin
      })
    end

    def skip_without_compiler
      reason = KotlinCompiler.unavailable_reason
      skip("compile_as_kotlin: #{reason}") if reason
    end

    it 'applies what the judge accepts through updateData in one call, null included, colour resolved' do
      skip_without_compiler
      run = run_with(<<~KOTLIN)
        val rejected = vm.data.value.applyTestInitialState(
            mapOf("email" to "new", "nickname" to null, "count" to 7, "agreed" to true, "tint" to "red", "nope" to 1),
            vm::updateData
        )
        val d = vm.data.value
        println("judged " + com.kotlinjsonui.core.JsonUITestValue.judgedBy)
        println("rejected " + rejected)
        println("data " + listOf(d.email, d.nickname, d.count, d.agreed, d.tint))
        println("snapshot " + d.testSnapshot())
      KOTLIN
      expect(run.errors).to eq([])
      lines = run.output.lines.map(&:strip)
      expect(lines).to include(
        'judged {email=String, nickname=String?, count=Integer, agreed=Boolean, tint=Color, onTap=(() -> Void)?}'
      )
      expect(lines).to include('rejected [RejectedKey(key=nope, reason=not a data field)]')
      expect(lines).to include('data [new, null, 7, true, Color(value=4294901760)]')
      expect(lines).to include('snapshot {email=new, nickname=null, count=7, agreed=true}')
    end

    it 'rejects a colour spelling that names no colour, and keeps the field' do
      skip_without_compiler
      run = run_with(<<~KOTLIN)
        val rejected = vm.data.value.applyTestInitialState(mapOf("tint" to "no-such-colour"), vm::updateData)
        println("rejected " + rejected)
        println("tint " + vm.data.value.tint)
      KOTLIN
      expect(run.errors).to eq([])
      expect(run.output.lines.map(&:strip)).to include(
        'rejected [RejectedKey(key=tint, reason=type mismatch: expected Color)]', 'tint Color(value=4278190080)'
      )
    end

    it 'with no updateData, applies nothing and says why for each accepted key' do
      skip_without_compiler
      run = run_with(<<~KOTLIN)
        val rejected = vm.data.value.applyTestInitialState(mapOf("email" to "new"), null)
        println("rejected " + rejected)
        println("email " + vm.data.value.email)
      KOTLIN
      expect(run.errors).to eq([])
      expect(run.output.lines.map(&:strip)).to include(
        'rejected [RejectedKey(key=email, reason=viewModel has no updateData)]', 'email old'
      )
    end

    # updateData's null: only a nullable field takes it. A non-optional field
    # keeps its value (the judge never hands one a null, but updateData is
    # also the ViewModel's own entry point).
    it 'updateData sets a nullable field to null and leaves a non-null one as it was' do
      skip_without_compiler
      run = run_with(<<~KOTLIN)
        vm.updateData(mapOf("nickname" to null, "email" to null, "count" to null))
        val d = vm.data.value
        println("after " + listOf(d.nickname, d.email, d.count))
      KOTLIN
      expect(run.errors).to eq([])
      expect(run.output.lines.map(&:strip)).to include('after [null, old, 1]')
    end
  end

  describe 'the screen' do
    let(:project) { Dir.mktmpdir('kjui_test_bridge_screen') }
    let(:layouts_dir) { File.join(project, 'src/main/assets/Layouts') }
    let(:views) { File.join(project, 'src/main/kotlin/com/example/app/views') }
    let(:view_models) { File.join(project, 'src/main/kotlin/com/example/app/viewmodels') }

    before do
      FileUtils.mkdir_p([layouts_dir, views, view_models])
      allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
        'source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts',
        'view_directory' => 'kotlin/com/example/app/views', 'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
        'package_name' => 'com.example.app', 'project_path' => project
      )
      allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(project)
      allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
      allow(Dir).to receive(:pwd).and_return(project)
    end

    after { FileUtils.rm_rf(project) }

    def layout(name, tree)
      File.write(File.join(layouts_dir, "#{name}.json"), JSON.generate(tree))
    end

    def screen_tree
      { 'type' => 'View', 'id' => 'root', 'data' => [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => 'x' }],
        'child' => [{ 'type' => 'Label', 'id' => 'which', 'text' => '@{title}' }] }
    end

    # [GeneratedView body, whole file, printed]
    def build(name)
      out = StringIO.new
      $stdout = out
      KjuiTools::Compose::ComposeBuilder.new.build_file(File.join(layouts_dir, "#{name}.json"))
      file = Dir.glob(File.join(views, '**', "#{name.split('_').map(&:capitalize).join}GeneratedView.kt")).first
      content = File.read(file)
      [content[%r{// >>> GENERATED_CODE_START.*?// >>> GENERATED_CODE_END}m], content, out.string.gsub(/\e\[[0-9;]*m/, '')]
    ensure
      $stdout = STDOUT
    end

    it 'remembers the bridge inside the Box that wraps both branches, and hands it to the marker' do
      layout('home', screen_tree)
      body, content, = build('home')

      expect(content).to include('import com.kotlinjsonui.core.rememberTestBridge')
      expect(body).to include('val testBridge = rememberTestBridge(')
      expect(body).to include('snapshot = { data.testSnapshot() },')
      expect(body).to include('apply = { data.applyTestInitialState(it, viewModel::updateData) }')
      expect(body).to include('ScreenMarker("home", bridge = testBridge)')
      expect(body).to include("// Requires KotlinJsonUI >= #{KjuiTools::Compose::TestBridgeCode::MIN_LIBRARY_VERSION} (test bridge")
      box = body.index('Box(propagateMinConstraints = true)')
      expect(box).to be < body.index('rememberTestBridge(')
      expect(body.index('rememberTestBridge(')).to be < body.index('if (DynamicModeManager.isActive())')
    end

    it 'passes no update, and says so, for a ViewModel whose updateData kjui does not write' do
      layout('home', screen_tree)
      FileUtils.mkdir_p(File.join(view_models))
      File.write(File.join(view_models, 'HomeViewModel.kt'),
                 "package com.example.app.viewmodels\n\nclass HomeViewModel\n")
      body, _, printed = build('home')

      expect(body).to include('apply = { data.applyTestInitialState(it, null) }')
      expect(printed).to include("HomeViewModel.kt has no generated updateData")
      expect(printed).to include("'viewModel has no updateData'")
    end

    it 'gives a cell neither the bridge nor its import' do
      layout('item_cell', screen_tree.merge('id' => 'cell_root'))
      layout('list', 'type' => 'View', 'child' => [{ 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['item_cell'] }])
      body, content, = build('item_cell')

      expect(body).not_to include('rememberTestBridge')
      expect(content).not_to include('import com.kotlinjsonui.core.rememberTestBridge')
    end
  end
end
