# frozen_string_literal: true

require 'set'
require 'tmpdir'
require 'fileutils'
require 'compose/compose_builder'
require 'compose/components/switch_component'
require 'compose/components/checkbox_component'
require 'compose/components/radio_component'
require 'compose/components/progress_component'
require 'compose/components/indicator_component'
require 'compose/components/button_component'
require 'compose/components/table_component'
require 'compose/components/tabview_component'
require 'compose/generators/cell_generator'
require 'compose/helpers/import_manager'
require 'compose/helpers/resource_resolver'
require 'core/config_manager'
require 'core/project_finder'

# Generated Kotlin calls KotlinJsonUI's wrappers of the material3 controls a layout draws (>= 2.66.0), never the
# material3 controls themselves (ticket kjui-wrap-material3-calls-next): a later change of material3's API is then
# fixed inside the library, and generated code is not emitted again. The slider went first (JsonUISlider, 2.65.0,
# slider_component_spec.rb); this is the rest.
#
# Each emitter below is driven through every branch that drew a material3 control, and its output is read for a
# direct call of one. A call is the name not preceded by a word character or a dot, followed by `(` (so
# `JsonUISwitch(` and `Modifier.Switch(` do not count); a *Defaults object is any use of the name.
module Material3ControlsThroughWrappers
  REPLACED_CALLS = %w[
    Switch Checkbox RadioButton LinearProgressIndicator CircularProgressIndicator Button HorizontalDivider
    NavigationBar NavigationBarItem Scaffold BadgedBox Badge IconButton IconToggleButton Icon
  ].freeze
  REPLACED_DEFAULTS = %w[SwitchDefaults CheckboxDefaults RadioButtonDefaults ButtonDefaults NavigationBarItemDefaults].freeze
  # What the emits below use beyond ComposeStubUniverse.common_stages (types only).
  EXTRA_STUBS = <<~KOTLIN
    fun Modifier.scale(scale: Float): Modifier = this
    fun MutableInteractionSource.collectIsPressedAsState(): MutableState<Boolean> = MutableState(false)
  KOTLIN
end

RSpec.describe 'Material3 controls go through KotlinJsonUI\'s wrappers' do
  def direct_material3(code)
    calls = Material3ControlsThroughWrappers::REPLACED_CALLS.select { |name| code.match?(/(?<![\w.])#{name}\(/) }
    defaults = Material3ControlsThroughWrappers::REPLACED_DEFAULTS.select { |name| code.match?(/\b#{name}\b/) }
    calls.map { |c| "#{c}(" } + defaults
  end

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  # [component, node, the wrappers it must call]
  emits = {
    'Switch' => [KjuiTools::Compose::Components::SwitchComponent, [
      [{ 'type' => 'Switch', 'onTintColor' => '#007AFF', 'trackTintColor' => '#CCCCCC', 'thumbTintColor' => '#FFFFFF', 'enabled' => false },
       %w[JsonUISwitch]],
      [{ 'type' => 'Switch', 'text' => 'Wi-Fi', 'onTintColor' => '#007AFF', 'thumbTintColor' => '#FFFFFF', 'enabled' => '@{on}' },
       %w[JsonUISwitch]],
      [{ 'type' => 'Switch', 'isOn' => '@{flag}', 'text' => 'Late', 'labelPosition' => 'trailing' }, %w[JsonUISwitch]]
    ]],
    'CheckBox' => [KjuiTools::Compose::Components::CheckboxComponent, [
      [{ 'type' => 'CheckBox', 'checkColor' => '#007AFF', 'uncheckedColor' => '#CCCCCC', 'iconColor' => '#FFFFFF', 'enabled' => false },
       %w[JsonUICheckbox]],
      [{ 'type' => 'CheckBox', 'text' => 'Agree', 'isOn' => '@{agreed}', 'iconColor' => '#FFFFFF' }, %w[JsonUICheckbox]],
      [{ 'type' => 'CheckBox', 'icon' => 'off_img', 'selectedIcon' => 'on_img', 'iconColor' => '#123456', 'enabled' => true },
       %w[JsonUIIconToggleButton JsonUIIcon]]
    ]],
    'Radio' => [KjuiTools::Compose::Components::RadioComponent, [
      [{ 'type' => 'Radio', 'id' => 'r1', 'group' => 'g', 'text' => 'A', 'iconColor' => '#FF0000', 'iconSize' => 24 },
       %w[JsonUIRadioButton]],
      [{ 'type' => 'Radio', 'id' => 'r2', 'group' => 'g', 'text' => 'B', 'icon' => 'square', 'iconColor' => '#FF0000' },
       %w[JsonUICheckbox]],
      [{ 'type' => 'Radio', 'id' => 'r3', 'group' => 'g', 'text' => 'C', 'icon' => 'star', 'selectedIcon' => 'star.fill' },
       %w[JsonUIIconButton JsonUIIcon]],
      [{ 'type' => 'Radio', 'id' => 'r4', 'items' => %w[a b], 'selectedValue' => '@{sel}', 'checkedColor' => '#007AFF',
         'uncheckedColor' => '#CCCCCC' }, %w[JsonUIRadioButton]],
      [{ 'type' => 'Radio', 'id' => 'r5', 'text' => 'D', 'icon' => 'circle', 'enabled' => false }, %w[JsonUIRadioButton]]
    ]],
    'Progress' => [KjuiTools::Compose::Components::ProgressComponent, [
      [{ 'type' => 'Progress' }, %w[JsonUILinearProgressIndicator]],
      [{ 'type' => 'Progress', 'progress' => '@{p}', 'progressTintColor' => '#007AFF', 'trackTintColor' => '#CCCCCC' },
       %w[JsonUILinearProgressIndicator]]
    ]],
    'Indicator' => [KjuiTools::Compose::Components::IndicatorComponent, [
      [{ 'type' => 'Indicator', 'color' => '#007AFF', 'strokeWidth' => 3 }, %w[JsonUICircularProgressIndicator]],
      [{ 'type' => 'Indicator', 'indicatorStyle' => 'large', 'animating' => '@{busy}' }, %w[JsonUICircularProgressIndicator]],
      [{ 'type' => 'Indicator', 'indicatorStyle' => 'linear', 'color' => '#007AFF', 'trackColor' => '#CCCCCC' },
       %w[JsonUILinearProgressIndicator]]
    ]],
    'Button' => [KjuiTools::Compose::Components::ButtonComponent, [
      [{ 'type' => 'Button', 'text' => 'Go', 'background' => '#007AFF', 'disabledBackground' => '#CCCCCC', 'enabled' => '@{ok}' },
       %w[JsonUIButton]],
      [{ 'type' => 'Button', 'id' => 'b', 'text' => 'Press', 'tapBackground' => '#0000FF', 'highlightColor' => '#FF0000',
         'borderColor' => '#000000' }, %w[JsonUIButton]],
      [{ 'type' => 'Button', 'text' => 'Menu', 'image' => 'menu', 'fontColor' => '#FFFFFF' }, %w[JsonUIButton JsonUIIcon]]
    ]],
    'Table' => [KjuiTools::Compose::Components::TableComponent, [
      [{ 'type' => 'Table', 'header' => %w[Name Age], 'separatorInset' => { 'left' => 16 } }, %w[JsonUIDivider]]
    ]],
    'TabView' => [KjuiTools::Compose::Components::TabviewComponent, [
      [{ 'type' => 'TabView', 'tintColor' => '#007AFF', 'tabBarBackground' => '#FFFFFF', 'enabled' => '@{tabsOn}',
         'tabs' => [{ 'title' => 'Home', 'icon' => 'house', 'badge' => 3 },
                    { 'title' => 'Inbox', 'icon' => 'envelope', 'badge' => '@{unread}' },
                    { 'title' => 'Me', 'icon' => 'me_off', 'selectedIcon' => 'me_on', 'iconType' => 'resource' }] },
       %w[JsonUITabScaffold JsonUITabBar JsonUITabBarItem JsonUIIcon JsonUIBadgedBox]]
    ]]
  }

  emits.each do |type, (component, cases)|
    it "#{type}: calls the wrappers, and no material3 control or *Defaults directly, on every branch" do
      aggregate_failures do
        cases.each do |node, wrappers|
          imports = Set.new
          code = component.generate(node, 0, imports)
          expect(direct_material3(code)).to eq([]), "#{node.inspect}\n#{code}"
          wrappers.each { |w| expect(code).to match(/(?<![\w.])#{w}\(/), "#{w} in #{node.inspect}" }
          # each wrapper called is imported from com.kotlinjsonui.components
          map = KjuiTools::Compose::Helpers::ImportManager.get_imports_map
          lines = imports.flat_map { |k| Array(map[k]) }
          wrappers.each do |w|
            expect(lines).to include("import com.kotlinjsonui.components.#{w}"), "#{w}'s import for #{node.inspect}"
          end
          expect(lines.grep(/androidx\.compose\.material3\.(#{(Material3ControlsThroughWrappers::REPLACED_CALLS + Material3ControlsThroughWrappers::REPLACED_DEFAULTS).join('|')})$/)).to eq([])
        end
      end
    end
  end

  # The same emits, well-typed against stub universes that declare the wrappers with their parameters and no
  # material3 control (spec/support/compose_stub_universe.rb): a flat colour that is not a wrapper's parameter, or a
  # call that went back to material3, does not compile. Table is left out: its LazyColumn rows are not in a universe.
  it 'the emits compile against the wrappers\' signatures, with no material3 control declared' do
    controls = emits.reject { |type, _| %w[Table TabView].include?(type) }.flat_map do |_, (component, cases)|
      cases.map { |node, _| component.generate(node, 1, Set.new) }
    end
    functions = controls.each_with_index.map { |code, i| "fun emitted#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}" }.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(functions)}
      #{Material3ControlsThroughWrappers::EXTRA_STUBS}
      class Data(
          val on: Boolean? = null, val flag: Boolean = false, val agreed: Boolean = false, val sel: String = "",
          val selectedG: String = "", val p: Double = 0.0, val busy: Boolean = false, val ok: Boolean? = null
      )
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{functions}
    KOTLIN

    tab_component, tab_cases = emits['TabView']
    tabs = tab_cases.map { |node, _| tab_component.generate(node, 1, Set.new) }
                    .each_with_index.map { |code, i| "fun tabs#{i}(data: Data, viewModel: ViewModel) {\n#{code}\n}" }.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.tabview(tabs)}
      // A disabled TabView's semantics (the TabView universe declares no disabled()).
      fun SemanticsPropertyReceiver.disabled() {}
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      data class Data(val unread: Int? = null, val tabsOn: Boolean? = null)
      #{tabs}
    KOTLIN
  end

  it 'Dynamic mode\'s loading spinner (ComposeBuilder) is JsonUICircularProgressIndicator' do
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    code = builder.send(:generate_dynamic_view_content, 'demo/layout', { 'type' => 'View' }, 1)
    expect(direct_material3(code)).to eq([])
    expect(code).to include('JsonUICircularProgressIndicator()')
    expect(builder.instance_variable_get(:@required_imports)).to include(:jsonui_circular_progress_indicator)
  end

  it 'a new cell\'s loading spinner (CellGenerator) is JsonUICircularProgressIndicator, imported from KotlinJsonUI' do
    Dir.mktmpdir('m3wrap_cell') do |dir|
      config = { 'source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts',
                 'view_directory' => 'kotlin/com/example/app/views', 'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
                 'data_directory' => 'kotlin/com/example/app/data', 'package_name' => 'com.example.app', 'project_path' => dir }
      allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
      Dir.chdir(dir) do
        expect { KjuiTools::Compose::Generators::CellGenerator.new('ProbeCell').generate }.to output.to_stdout
        sources = Dir.glob(File.join(dir, '**', '*.kt')).map { |f| File.read(f) }
        generated = sources.find { |s| s.include?('SafeDynamicView(') }
        expect(generated).not_to be_nil
        expect(direct_material3(generated)).to eq([])
        expect(generated).to include('JsonUICircularProgressIndicator()')
        expect(generated).to include('import com.kotlinjsonui.components.JsonUICircularProgressIndicator')
        expect(generated).not_to include('import androidx.compose.material3.CircularProgressIndicator')
      end
    end
  end

  it 'the guard sees a direct call (it is not blind)' do
    expect(direct_material3("Switch(\n    checked = true,\n    colors = SwitchDefaults.colors()\n)")).to eq(['Switch(', 'SwitchDefaults'])
    expect(direct_material3("    Icon(painter = p, contentDescription = null)")).to eq(['Icon('])
    expect(direct_material3("JsonUISwitch(\n    checked = true\n)\nJsonUIIcon(painter = p)")).to eq([])
  end
end
