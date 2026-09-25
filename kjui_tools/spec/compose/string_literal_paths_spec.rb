# frozen_string_literal: true

require 'set'
require 'tmpdir'
require 'rexml/document'
require 'core/string_literals'
require 'core/resources/string_manager'
require 'compose/compose_builder'
require 'compose/data_model_updater'
require 'compose/components/text_component'
require 'compose/components/textview_component'
require 'compose/components/textfield_component'
require 'compose/components/button_component'
require 'compose/components/circleimage_component'
require 'compose/components/iconlabel_component'
require 'compose/components/networkimage_component'
require 'compose/components/tabview_component'
require 'compose/components/web_component'
require 'compose/components/webview_component'
require 'compose/components/selectbox_component'
require 'compose/components/table_component'
require 'compose/components/radio_component'
require 'compose/components/embed_component'
require 'compose/components/collection_component'
require 'compose/helpers/binding_expression'
require 'compose/helpers/bound_value'
require 'compose/helpers/font_spec_helper'
require 'compose/helpers/image_accessibility_helper'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'
require_relative '../support/kotlin_compiler'

# Every path by which kjui writes a layout author's text into generated
# Kotlin goes through ONE escaper, JsonUIShared::StringLiterals (ticket
# codegen-string-literals-are-not-escaped-for-the-target-language). Before it,
# over twenty helpers and inline writers each escaped for themselves and
# disagreed: almost none escaped `$`, so the text `Pay $x now` became the
# Kotlin template `"Pay $x now"` — an unresolved reference, or a wrong value
# when an `x` is in scope. One row per path, named by the path; a new writer
# that hand-quotes an author's text needs a row here.
#
# A row asserts the emit CONTAINS the escaper's output at the position the
# path writes it, so a path that stops calling the escaper goes red. What the
# escaper's output means is answered once, by a compiler, in the last example.
RSpec.describe 'author text reaches generated Kotlin through the one escaper' do
  # `\`, `"`, `$` (both template forms), a tab and a newline — each of which
  # at least one of the old writers let through.
  STRING_PATH_SPECIMEN = %q{Pay $x ${y} \ "q"} + "\tend\nnext"
  # What `.inspect` gets wrong beyond that: it writes `\#` (not a Kotlin
  # escape) before `{`/`$`, and `\e` (not a Kotlin escape either).
  STRING_PATH_INSPECT_SPECIMEN = '#{a} #$b' + "\e\u0001"
  # A `??` default lives inside `@{...}`, which ends at the first `}` and
  # whose default is a quoted literal: the specimen without braces or `'`.
  STRING_PATH_DEFAULT_SPECIMEN = STRING_PATH_SPECIMEN.delete('{}')
  STRING_PATH_PLAIN = 'plain text'

  # Locals, not constants: a constant here would be Object's, shared with
  # every other spec file.
  components = KjuiTools::Compose::Components
  helpers = KjuiTools::Compose::Helpers

  # name => { emit:, kind:, around:, specimen:, inspect: }
  #   kind   — :literal (the path writes a whole literal: the escaper's
  #            `kotlin`) or :body (the path writes the quotes: `kotlin_body`)
  #   around — the Kotlin the literal sits in, `%s` marking it
  STRING_LITERAL_PATHS = {}
  def self.path(name, kind: :literal, around: '%s', specimen: STRING_PATH_SPECIMEN, inspect: false, &emit)
    STRING_LITERAL_PATHS[name] = { emit: emit, kind: kind, around: around, specimen: specimen, inspect: inspect }
  end

  def self.label(json)
    KjuiTools::Compose::Components::TextComponent.generate({ 'type' => 'Label' }.merge(json), 0, Set.new)
  end

  def self.updater
    KjuiTools::Compose::DataModelUpdater.allocate
  end

  # ---- helpers every text path reaches ---------------------------------
  path('ResourceResolver.quote — Label.text via process_text', around: 'text = %s,') { |t| label('text' => t) }
  path('BindingExpression.quote — a `??` default', around: '?: %s}',
       specimen: STRING_PATH_DEFAULT_SPECIMEN) { |t| helpers::ResourceResolver.process_text("@{name ?? '#{t}'}") }
  path('BoundValue.escaped_run — a literal run beside a binding', kind: :body, around: '"%s${') do |t|
    helpers::BoundValue.text("#{t}@{price}")
  end
  path('ComposeBuilder#quote — process_data_binding') do |t|
    KjuiTools::Compose::ComposeBuilder.new.send(:process_data_binding, t)
  end
  path('TextComponent.escape_string — Label.text with partialAttributes', kind: :body, around: 'text = "%s",') do |t|
    label('text' => t, 'partialAttributes' => [{ 'range' => [0, 1], 'fontColor' => '#FF0000' }])
  end
  path('TextViewComponent.quote — TextView.text', around: 'rememberTextFieldState(initialText = %s') do |t|
    components::TextViewComponent.generate({ 'type' => 'TextView', 'text' => t }, 0, Set.new)
  end
  path('ButtonComponent.quote — an icon-only Button contentDescription', around: 'contentDescription = %s') do |t|
    components::ButtonComponent.generate({ 'type' => 'Button', 'image' => t }, 0, Set.new)
  end
  path('CircleImageComponent.quote — CircleImage.url', around: 'model = %s,') do |t|
    components::CircleImageComponent.generate({ 'type' => 'CircleImage', 'url' => t }, 0, Set.new)
  end
  path('IconLabelComponent.quote — IconLabel.contentDescription', around: 'contentDescription = %s,') do |t|
    components::IconLabelComponent.generate({ 'type' => 'IconLabel', 'text' => 'a', 'icon' => 'x', 'contentDescription' => t }, 0, Set.new)
  end
  path('NetworkImageComponent.quote — NetworkImage.url', around: 'model = %s,') do |t|
    components::NetworkImageComponent.generate({ 'type' => 'NetworkImage', 'url' => t }, 0, Set.new)
  end
  path('NetworkImageComponent.quote — NetworkImage.headers value', around: '.add("k", %s)') do |t|
    components::NetworkImageComponent.generate({ 'type' => 'NetworkImage', 'url' => 'u', 'headers' => { 'k' => t } }, 0, Set.new)
  end
  path('ImageAccessibilityHelper — the control-role fallback') do |t|
    helpers::ImageAccessibilityHelper.content_description({ 'type' => 'Image', JsonUIShared::ImageAccessibility::ROLE_KEY => 'control' }, t)
  end

  # ---- TabView ---------------------------------------------------------
  def self.tabview(tab)
    KjuiTools::Compose::Components::TabviewComponent.generate({ 'type' => 'TabView', 'tabs' => [tab] }, 0, Set.new)
  end
  path('TabView tab.title — icon contentDescription', around: 'contentDescription = %s') { |t| tabview('title' => t) }
  path('TabView tab.title — label', around: 'label = { Text(%s) },') { |t| tabview('title' => t) }
  path('TabView tab.title — content placeholder', kind: :body, around: 'Text("%s content")') { |t| tabview('title' => t) }
  path('TabView tab.badge — kotlin_string_literal', around: 'Badge { Text(%s) }') { |t| tabview('title' => 'a', 'badge' => t) }

  # ---- data model defaults ----------------------------------------------
  path('DataModelUpdater String defaultValue — bare') { |t| updater.send(:format_default_value, t, 'String') }
  path("DataModelUpdater String defaultValue — 'single-quoted'") { |t| updater.send(:format_default_value, "'#{t}'", 'String') }
  path('DataModelUpdater kotlin_string_literal — a Map default value', around: '"k" to %s') do |t|
    updater.send(:format_default_value, { 'k' => t }, 'Object')
  end
  path('DataModelUpdater CollectionDataSource — cell value (was .inspect)', around: 'to %s)', inspect: true) do |t|
    updater.send(:collection_data_source_literal, [{ 'k' => t }])
  end
  path('DataModelUpdater CollectionDataSource — cell key (was .inspect)', around: 'mapOf(%s to', inspect: true) do |t|
    updater.send(:collection_data_source_literal, [{ t => 1 }])
  end
  path('DataModelUpdater CollectionDataSource — cell view name (was .inspect)', around: 'viewName = %s,', inspect: true) do |t|
    updater.send(:collection_data_source_literal, { 'sections' => [{ 'cell' => t, 'cells' => [] }] })
  end

  # ---- Web / WebView ------------------------------------------------------
  path('WebComponent url', around: 'loadUrl(%s)') { |t| components::WebComponent.generate({ 'type' => 'Web', 'url' => t }, 0, Set.new) }
  path('WebComponent userAgent', around: 'settings.userAgentString = %s') do |t|
    components::WebComponent.generate({ 'type' => 'Web', 'url' => 'u', 'userAgent' => t }, 0, Set.new)
  end
  path('WebComponent.kotlin_string — html', around: 'loadDataWithBaseURL(null, %s,') do |t|
    components::WebComponent.generate({ 'type' => 'Web', 'html' => t }, 0, Set.new)
  end
  path('WebviewComponent url', around: 'loadUrl(%s)') { |t| components::WebviewComponent.generate({ 'type' => 'WebView', 'url' => t }, 0, Set.new) }
  path('WebviewComponent userAgent', around: 'settings.userAgentString = %s') do |t|
    components::WebviewComponent.generate({ 'type' => 'WebView', 'url' => 'u', 'userAgent' => t }, 0, Set.new)
  end

  # ---- SelectBox ------------------------------------------------------------
  def self.selectbox(json)
    KjuiTools::Compose::Components::SelectBoxComponent.generate({ 'type' => 'SelectBox' }.merge(json), 0, Set.new)
  end
  path('SelectBox items — shown for a bound selectedIndex', around: 'listOf(%s).getOrElse') do |t|
    selectbox('items' => [t], 'selectedIndex' => '@{i}')
  end
  path('SelectBox items — written back for a bound selectedIndex', around: 'listOf(%s).indexOf(newValue)') do |t|
    selectbox('items' => [t], 'selectedIndex' => '@{i}', 'onValueChange' => '@{onPick}')
  end
  path('SelectBox items — a static selectedIndex', around: 'value = %s,') { |t| selectbox('items' => [t], 'selectedIndex' => 0) }
  path('SelectBox options', around: 'options = listOf(%s),') { |t| selectbox('options' => [t]) }
  path('SelectBox options — a Hash label', around: 'options = listOf(%s),') { |t| selectbox('options' => [{ 'label' => t }]) }
  path('SelectBox dateFormat', around: 'dateFormat = %s,') { |t| selectbox('selectItemType' => 'Date', 'dateFormat' => t) }
  path('SelectBox datePickerMode', around: 'datePickerMode = %s,') { |t| selectbox('selectItemType' => 'Date', 'datePickerMode' => t) }
  path('SelectBox datePickerStyle', around: 'datePickerStyle = %s,') { |t| selectbox('selectItemType' => 'Date', 'datePickerStyle' => t) }

  # ---- Table / Radio / Embed ---------------------------------------------------
  path('Table header column', around: 'text = %s,') { |t| components::TableComponent.generate({ 'type' => 'Table', 'header' => [t] }, 0, Set.new) }
  def self.radio(json)
    KjuiTools::Compose::Components::RadioComponent.generate({ 'type' => 'Radio', 'id' => 'target' }.merge(json), 0, Set.new)
  end
  path('Radio options value — written to the binding', around: 'mapOf("sel" to %s))') { |t| radio('options' => [t], 'bind' => '@{sel}') }
  path('Radio options value — compared for selected', around: '== %s),') { |t| radio('options' => [t], 'bind' => '@{sel}') }
  path('Radio options value — the onValueChange argument', around: 'invoke("target", %s)') do |t|
    radio('options' => [t], 'onValueChange' => '@{onPick}')
  end
  path('Radio options label', around: 'Text(%s)') { |t| radio('options' => [{ 'value' => 'v', 'label' => t }]) }
  path('Radio items value — written to the binding', around: 'mapOf("sel" to %s))') { |t| radio('items' => [t], 'selectedValue' => '@{sel}') }
  path('Radio items value — compared for selected', around: '== %s,') { |t| radio('items' => [t], 'selectedValue' => '@{sel}') }
  path('Radio items label', around: 'Text(%s, color') { |t| radio('items' => [t], 'selectedValue' => '@{sel}') }
  path('Radio group text (items form)', around: 'Text(%s, color') { |t| radio('items' => ['a'], 'text' => t) }
  path('Radio item id — written to the group', around: 'mapOf("selectedRadiogroup" to %s))') { |t| radio('id' => t, 'text' => 'a') }
  path('Embed params value', around: '"k" to %s') do |t|
    components::EmbedComponent.generate({ 'type' => 'Embed', 'screen' => 'child', 'params' => { 'k' => t } }, 0, Set.new)
  end

  # ---- fonts, ids ---------------------------------------------------------------
  path('FontSpecHelper fontFamily (was .inspect)', inspect: true) { |t| helpers::FontSpecHelper.build_font_spec_args({ 'fontFamily' => t }, Set.new)[:family] }
  path('FontSpecHelper font as a family name (was .inspect)', inspect: true) do |t|
    helpers::FontSpecHelper.build_font_spec_args({ 'font' => t }, Set.new)[:family]
  end
  path('ModifierBuilder.build_test_tag id', around: '.testTag(%s)') { |t| helpers::ModifierBuilder.build_test_tag({ 'id' => t }).join }
  path('ModifierBuilder.get_event_handler_invocation viewId', around: 'invoke(%s)') do |t|
    helpers::ModifierBuilder.get_event_handler_invocation('@{onPick}', t, nil)
  end
  path('CollectionComponent cell testTag (the id; `$cellIndex` is the emitter\'s)', kind: :body,
       around: '.testTag("%s_item_$cellIndex")') { |t| components::CollectionComponent.cell_test_tag_modifier(t, 'cellIndex', 0) }

  let(:source_dir) { Dir.mktmpdir('string_literal_paths') }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(source_dir)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('probe')
    helpers::ResourceResolver.data_definitions = { 'onPick' => { 'class' => '(String, String) -> Unit' } }
    components::TextComponent.counter = 0
    components::ButtonComponent.reset_counter!
  end

  after { FileUtils.rm_rf(source_dir) }

  def expected(row, text)
    escaped = row[:kind] == :body ? JsonUIShared::StringLiterals.kotlin_body(text) : JsonUIShared::StringLiterals.kotlin(text)
    row[:around].sub('%s') { escaped }
  end

  STRING_LITERAL_PATHS.each do |name, row|
    it name do
      expect(row[:emit].call(row[:specimen])).to include(expected(row, row[:specimen]))
    end

    next unless row[:inspect]

    it "#{name}, for what .inspect wrote wrongly" do
      expect(row[:emit].call(STRING_PATH_INSPECT_SPECIMEN)).to include(expected(row, STRING_PATH_INSPECT_SPECIMEN))
    end
  end

  # The other half of the contract: a text with none of Kotlin's special
  # characters is written exactly as before. The expectation is spelled by
  # hand, not by the escaper.
  it 'writes a plain text as it always did, on every path' do
    aggregate_failures do
      STRING_LITERAL_PATHS.each do |name, row|
        written = row[:kind] == :body ? STRING_PATH_PLAIN : %("#{STRING_PATH_PLAIN}")
        expect(row[:emit].call(STRING_PATH_PLAIN)).to include(row[:around].sub('%s') { written }), name
      end
    end
  end

  # strings.xml is an Android resource, not Kotlin: aapt reads `\` as an
  # escape, drops an unescaped `"`, rejects a bare `'` and reads a leading `@`
  # / `?` as a reference; REXML folds a raw tab or newline. The expected
  # values are spelled by hand, and read back PARSED — what aapt is handed.
  describe 'the strings.xml writer' do
    def strings_xml(entries)
      Dir.mktmpdir do |dir|
        resources = File.join(dir, 'src/main/assets/Layouts/Resources')
        FileUtils.mkdir_p(resources)
        manager = KjuiTools::Core::Resources::StringManager.new({ 'source_directory' => 'src/main' }, dir, resources)
        manager.instance_variable_set(:@strings_data, { 'probe' => entries })
        allow(KjuiTools::Core::Logger).to receive(:info)
        allow(KjuiTools::Core::Logger).to receive(:debug)
        manager.send(:update_strings_xml, 'values')
        REXML::Document.new(File.read(File.join(dir, 'src/main/res/values/strings.xml'))).root
      end
    end

    def value_of(root, name)
      root.elements.to_a('string').find { |e| e.attributes['name'] == name }&.text
    end

    it 'escapes a <string> for aapt' do
      root = strings_xml('k' => STRING_PATH_SPECIMEN, 'plain' => STRING_PATH_PLAIN)
      expect(value_of(root, 'probe_k')).to eq('Pay $x ${y} \\\\ \\"q\\"\\tend\\nnext')
      expect(value_of(root, 'probe_plain')).to eq('plain text')
    end

    it 'escapes a leading @ or ? and an apostrophe' do
      root = strings_xml('at' => '@home', 'q' => '?why', 'apos' => "Don't")
      expect([value_of(root, 'probe_at'), value_of(root, 'probe_q'), value_of(root, 'probe_apos')])
        .to eq(['\\@home', '\\?why', "Don\\'t"])
    end

    it 'escapes a <plurals> item the same way' do
      root = strings_xml('n' => { 'en' => { 'plural' => { 'one' => "#{STRING_PATH_SPECIMEN} {count}", 'other' => 'x' } } })
      item = root.elements["plurals[@name='probe_n']"].elements.to_a('item').find { |i| i.attributes['quantity'] == 'one' }
      expect(item.text).to eq('Pay $x ${y} \\\\ \\"q\\"\\tend\\nnext %d')
    end
  end

  # What the rows above assert — that the escaper's output is where the text
  # was — says nothing about whether that output is Kotlin. This hands one
  # fragment from each kind of emit, cut from the emitted code, to kotlinc
  # (spec/support/kotlin_compiler.rb): a template `$x` is an unresolved
  # reference, `\ ` an illegal escape, a raw newline an unterminated literal.
  # Plain expressions, so no Compose stubs are needed beyond `data`. Types
  # only — not the Compose compiler's rules.
  it 'emits fragments that compile as Kotlin' do
    t = STRING_PATH_SPECIMEN
    # Non-greedy and multiline, so a literal that a raw newline broke across
    # lines is still cut whole and reaches the compiler.
    cut = lambda do |code, pattern|
      m = code.match(pattern)
      expect(m).not_to be_nil, "no #{pattern.inspect} in:\n#{code}"
      m[1]
    end
    tab = self.class.tabview('title' => t)
    fragments = {
      'text' => cut.call(self.class.label('text' => t), /^\s*text = (.*?),$/m),
      'button' => cut.call(components::ButtonComponent.generate({ 'type' => 'Button', 'text' => t }, 0, Set.new), /^\s*Text\((.*?)\)$/m),
      'hint' => cut.call(components::TextFieldComponent.generate({ 'type' => 'TextField', 'hint' => t }, 0, Set.new), /^\s*text = (.*?),$/m),
      'tabTitle' => cut.call(tab, /label = \{ Text\((.*?)\) \},$/m),
      'selectItems' => cut.call(self.class.selectbox('options' => [t, 'b']), /options = (listOf\(.*?\)),$/m),
      'dataDefault' => self.class.updater.send(:format_default_value, t, 'String'),
      'bindingDefault' => helpers::ResourceResolver.process_text("@{name ?? '#{STRING_PATH_DEFAULT_SPECIMEN}'}")
    }
    expect(<<~KOTLIN).to compile_as_kotlin
      class Data(val name: String? = null)
      val data = Data()
      #{fragments.map { |name, fragment| "val #{name}: Any = #{fragment}" }.join("\n")}
    KOTLIN
  end
end
