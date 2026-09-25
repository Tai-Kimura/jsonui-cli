# frozen_string_literal: true

require 'fileutils'
require 'tmpdir'
require 'core/string_literals'
require 'core/resources/string_manager'
require 'swiftui/converter_factory'
require 'swiftui/views/include_converter'
require 'swiftui/data_model_updater'
require 'swiftui/view_updater'
require 'swiftui/binding/binding_expression'
require 'swiftui/binding/binding_handler_registry'

# Every path that writes an author's text into generated Swift as a string
# literal writes it through ONE escaper, JsonUIShared::StringLiterals
# (lib/core/string_literals.rb); the Localizable.strings writer applies that
# format's own escapes.
#
# Until 1.8.121 each path escaped for itself and most did it wrong: a gsub
# replacement '\\\\' is ONE backslash, so `C:\new \(total)` became a newline
# and an interpolation; `.inspect` wrote `\#{` and `\e`, which Swift rejects;
# several escaped `"` only, or nothing at all. The specimen holds each
# character one of them got wrong. Ticket
# codegen-string-literals-are-not-escaped-for-the-target-language.
#
# One row per path: the smallest input that reaches it, and the fragment the
# output must contain. *kind* says how the text is written there — a whole
# literal (:swift), the inside of one the caller quotes (:body), or a
# Localizable.strings value (:strings).
RSpec.describe 'author text in generated Swift goes through the shared escaper' do
  specimen = %q{Say "hi" \ $x \(z) `b` {c}} + "\ttab\nnew"
  # Ruby's `.inspect` spells every character of the specimen the way Swift
  # does, so a path that wrote `.inspect` passes on it. This one it spells
  # differently (`\#{`, `\#$`, `\#@`, `\e`, `\u0001`, `\x7F`), and a path
  # that escaped nothing writes its control characters raw.
  inspect_specimen = '#{a} #$b #@c' + "\e\u0001\u007f"
  plain = 'plain text'
  lit = JsonUIShared::StringLiterals
  views = SjuiTools::SwiftUI::Views
  handlers = SjuiTools::SwiftUI::Binding
  expr = SjuiTools::SwiftUI::Binding::BindingExpression

  # The .strings escapes, written out: `\\ \" \n \r \t`, no `\u{}`.
  strings_specimen = 'Say \"hi\" \\\\ $x \\\\(z) `b` {c}\\ttab\\nnew'

  # A converter's output, with the state variables it declares.
  convert = lambda do |klass, component|
    converter = klass.new(component, 0, nil)
    [converter.convert, *Array(converter.state_variables)].join("\n")
  end

  data_model = lambda do |property|
    updater = SjuiTools::SwiftUI::DataModelUpdater.allocate
    updater.instance_variable_set(:@mode, 'swiftui')
    updater.send(:generate_data_content, 'Probe', [{ 'name' => 'probe' }.merge(property)])
  end

  interp = ->(b) { "\"#{b} \\(" }

  paths = [
    ['Label text', :swift, ->(t) { convert.(views::LabelConverter, { 'type' => 'Label', 'text' => t }) }],
    ['Label text around a binding (literal segments)', :body,
     ->(t) { convert.(views::LabelConverter, { 'type' => 'Label', 'text' => "#{t} @{name}" }) }, interp],
    ['Label text that is not a binding path', :body,
     ->(t) { convert.(views::LabelConverter, { 'type' => 'Label', 'text' => "@{#{t}}" }) }, ->(b) { "\"@{#{b}}\"" }],
    ['Label hint', :swift,
     lambda { |t|
       convert.(views::LabelConverter,
                { 'type' => 'Label', 'text' => '', 'hint' => t, 'hintAttributes' => { 'fontColor' => '#FF0000' } })
     }],
    ['Label partialAttributes range', :swift,
     lambda { |t|
       convert.(views::LabelConverter,
                { 'type' => 'Label', 'text' => 'x', 'partialAttributes' => [{ 'range' => t, 'fontColor' => '#FF0000' }] })
     }, ->(s) { "textPattern: #{s}" }],
    ['TextField hint', :swift,
     ->(t) { convert.(views::TextFieldConverter, { 'type' => 'TextField', 'id' => 'f', 'hint' => t }) }],
    ['TextField literal text (initial value)', :swift,
     ->(t) { convert.(views::TextFieldConverter, { 'type' => 'TextField', 'id' => 'f', 'text' => t }) },
     ->(s) { "String = #{s}" }],
    ['TextView hint', :swift,
     ->(t) { convert.(views::TextViewConverter, { 'type' => 'TextView', 'id' => 'v', 'hint' => t }) },
     ->(s) { "hint: #{s}" }],
    ['TextView literal text (initial value)', :swift,
     ->(t) { convert.(views::TextViewConverter, { 'type' => 'TextView', 'id' => 'v', 'text' => t }) },
     ->(s) { "String = #{s}" }],
    ['Button text', :swift,
     ->(t) { convert.(views::ButtonConverter, { 'type' => 'Button', 'text' => t }) }, ->(s) { "text: #{s}" }],
    ['Button text around a binding (literal segments)', :body,
     ->(t) { convert.(views::ButtonConverter, { 'type' => 'Button', 'text' => "#{t} @{name}" }) }, interp],
    ['Toggle text', :swift,
     ->(t) { convert.(views::ToggleConverter, { 'type' => 'Switch', 'id' => 's', 'text' => t }) },
     ->(s) { "Text(#{s})" }],
    ['CheckBox text', :swift,
     ->(t) { convert.(views::CheckboxConverter, { 'type' => 'CheckBox', 'id' => 'c', 'text' => t }) },
     ->(s) { "label: #{s}" }],
    ['Radio item', :swift,
     ->(t) { convert.(views::RadioConverter, { 'type' => 'Radio', 'id' => 'r', 'items' => [t] }) },
     ->(s) { "Text(#{s})" }],
    ['Radio label', :swift,
     ->(t) { convert.(views::RadioConverter, { 'type' => 'Radio', 'id' => 'r', 'text' => t, 'items' => ['a'] }) },
     ->(s) { "Text(#{s})" }],
    ['Radio selectedValue', :swift,
     lambda { |t|
       convert.(views::RadioConverter, { 'type' => 'Radio', 'id' => 'r', 'items' => ['a'], 'selectedValue' => t })
     }],
    ['Radio value (single radio)', :swift,
     ->(t) { convert.(views::RadioConverter, { 'type' => 'Radio', 'id' => 'r', 'value' => t }) }],
    ['SelectBox item', :swift,
     ->(t) { convert.(views::SelectBoxConverter, { 'type' => 'SelectBox', 'id' => 's', 'items' => [t] }) },
     ->(s) { "items: [#{s}]" }],
    ['SelectBox prompt', :swift,
     ->(t) { convert.(views::SelectBoxConverter, { 'type' => 'SelectBox', 'id' => 's', 'prompt' => t }) },
     ->(s) { "prompt: #{s}" }],
    ['Segment item', :swift,
     ->(t) { convert.(views::SegmentConverter, { 'type' => 'Segment', 'id' => 'g', 'items' => [t] }) },
     ->(s) { "Text(#{s})" }],
    ['TabView title', :swift,
     ->(t) { convert.(views::TabViewConverter, { 'type' => 'TabView', 'tabs' => [{ 'title' => t }] }) },
     ->(s) { "Label(#{s}, systemImage:" }],
    ['TabView badge', :swift,
     ->(t) { convert.(views::TabViewConverter, { 'type' => 'TabView', 'tabs' => [{ 'title' => 'a', 'badge' => t }] }) },
     ->(s) { ".badge(#{s})" }],
    ['IconLabel text', :swift,
     ->(t) { convert.(views::IconLabelConverter, { 'type' => 'IconLabel', 'text' => t }) }, ->(s) { "text: #{s}" }],
    ['Image accessibilityLabel', :swift,
     ->(t) { convert.(views::ImageConverter, { 'type' => 'Image', 'src' => 'pic', 'alt' => t }) },
     ->(s) { ".accessibilityLabel(Text(#{s}))" }],
    ['alert title', :swift,
     lambda { |t|
       convert.(views::ViewConverter,
                { 'type' => 'View', 'alert' => { 'isPresented' => '@{shown}', 'title' => t, 'actions' => '@{acts}' } })
     }, ->(s) { ".alert(\n        #{s}," }],
    ['alert message', :swift,
     lambda { |t|
       convert.(views::ViewConverter,
                { 'type' => 'View',
                  'alert' => { 'isPresented' => '@{shown}', 'title' => 'a', 'message' => t, 'actions' => '@{acts}' } })
     }, ->(s) { "Text(#{s})" }],
    ['accessibilityIdentifier', :swift,
     ->(t) { convert.(views::LabelConverter, { 'type' => 'Label', 'id' => t, 'text' => 'x' }) },
     ->(s) { ".accessibilityIdentifier(#{s})" }],
    ['Collection cell accessibilityIdentifier', :body,
     lambda { |t|
       converter = views::CollectionConverter.new({ 'type' => 'Collection', 'id' => t }, 0, nil)
       converter.send(:apply_cell_item_identifier, 'index')
       converter.instance_variable_get(:@generated_code).join("\n")
     }, ->(b) { ".accessibilityIdentifier(\"#{b}_item_\\(index)\")" }],
    ['NetworkImage url', :swift,
     ->(t) { convert.(views::NetworkImageConverter, { 'type' => 'NetworkImage', 'url' => t }) }, ->(s) { "url: #{s}" }],
    ['NetworkImage hint', :swift,
     lambda { |t|
       convert.(views::NetworkImageConverter, { 'type' => 'NetworkImage', 'url' => 'u', 'hint' => t })
     }, ->(s) { "placeholder: #{s}" }],
    ['NetworkImage header value', :swift,
     lambda { |t|
       convert.(views::NetworkImageConverter, { 'type' => 'NetworkImage', 'url' => 'u', 'headers' => { 'k' => t } })
     }, ->(s) { "\"k\": #{s}" }],
    ['Web url', :swift,
     ->(t) { convert.(views::WebConverter, { 'type' => 'Web', 'url' => t }) }, ->(s) { "URL(string: #{s})" }],
    ['Web html', :swift,
     ->(t) { convert.(views::WebConverter, { 'type' => 'Web', 'html' => t }) }, ->(s) { "html: #{s}" }],
    ['Include literal data param', :swift,
     lambda { |t|
       convert.(views::IncludeConverter, { 'type' => 'Include', 'include' => 'child', 'data' => { 'k' => t } })
     }, ->(s) { "\"k\": #{s}" }],
    ['Embed literal param', :swift,
     lambda { |t|
       convert.(views::EmbedConverter, { 'type' => 'Embed', 'screen' => 'counter', 'params' => { 'k' => t } })
     }, ->(s) { "\"k\": #{s}" }],
    ['data-model String default', :swift,
     ->(t) { data_model.({ 'class' => 'String', 'defaultValue' => t }) }, ->(s) { "var probe: String = #{s}" }],
    ['data-model Object default value', :swift,
     ->(t) { data_model.({ 'class' => 'Object', 'defaultValue' => { 'k' => t } }) }, ->(s) { "[\"k\": #{s}]" }],
    ['data-model CollectionDataSource cell value', :swift,
     ->(t) { data_model.({ 'class' => 'CollectionDataSource', 'defaultValue' => [{ 'k' => t }] }) },
     ->(s) { "[\"k\": #{s}]" }],
    ['binding ?? default (text position)', :swift,
     ->(t) { expr.swift_text_expr(%(specimenProbe ?? "#{t}")) }, ->(s) { "data.specimenProbe ?? #{s}" }],
    ['binding ?? default (value position)', :swift,
     ->(t) { expr.swift_value_expr(%(specimenProbe ?? "#{t}")) }, ->(s) { "data.specimenProbe ?? #{s}" }],
    ['LabelBindingHandler literal text', :swift, ->(t) { handlers::LabelBindingHandler.new.get_text_content({ 'text' => t }) }],
    ['ButtonBindingHandler literal text', :swift, ->(t) { handlers::ButtonBindingHandler.new.get_button_text({ 'text' => t }) }],
    ['TextFieldBindingHandler literal text', :swift,
     ->(t) { handlers::TextFieldBindingHandler.new.get_text_binding({ 'text' => t }) }, ->(s) { ".constant(#{s})" }],
    ['ToggleBindingHandler literal label', :swift, ->(t) { handlers::ToggleBindingHandler.new.get_label({ 'text' => t }) }],
    ['CheckboxBindingHandler literal label', :swift,
     ->(t) { handlers::CheckboxBindingHandler.new.get_label({ 'text' => t }) }],
    ['ViewUpdater Label text', :swift,
     ->(t) { SjuiTools::SwiftUI::ViewUpdater.new.send(:generate_swiftui_code, { 'type' => 'Label', 'text' => t }) },
     ->(s) { "Text(#{s})" }],
    ['ViewUpdater Button text', :swift,
     ->(t) { SjuiTools::SwiftUI::ViewUpdater.new.send(:generate_swiftui_code, { 'type' => 'Button', 'text' => t }) },
     ->(s) { "Text(#{s})" }],
    ['Localizable.strings value', :strings,
     lambda { |t|
       Dir.mktmpdir do |dir|
         path = File.join(dir, 'en.lproj', 'Localizable.strings')
         FileUtils.mkdir_p(File.dirname(path))
         SjuiTools::Core::Resources::StringManager.allocate.send(:update_strings_file, path, { 'screen' => { 'k' => t } })
         File.read(path)
       end
     }, ->(v) { %("screen_k" = "#{v}";) }]
  ].freeze

  # The .strings format has no escape for the second specimen's characters,
  # so the writer passes it through as it is.
  literal_for = {
    swift: { specimen => lit.swift(specimen), inspect_specimen => lit.swift(inspect_specimen),
             plain => '"plain text"' },
    body: { specimen => lit.swift_body(specimen), inspect_specimen => lit.swift_body(inspect_specimen),
            plain => 'plain text' },
    strings: { specimen => strings_specimen, inspect_specimen => inspect_specimen, plain => 'plain text' }
  }.freeze

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  before do
    %i[info debug warn success].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
  end

  paths.each do |name, kind, emit, fragment|
    fragment ||= ->(s) { s }

    it name do
      aggregate_failures do
        [specimen, inspect_specimen].each do |text|
          expect(emit.(text)).to include(fragment.(literal_for[kind][text]))
        end
      end
    end
  end

  # The rows above pin text. These are also handed to swiftc as emitted, for
  # the paths whose output type-checks against the shared stubs
  # (spec/support/swift_compiler.rb, emitted_swift.rb) — the pre-1.8.121
  # output did not: a raw newline ends a Swift literal.
  it 'writes literals that compile where they stand' do
    [specimen, inspect_specimen].each do |text|
      view = [
        views::LabelConverter.new({ 'type' => 'Label', 'id' => text, 'text' => text }, 0, nil).convert,
        views::LabelConverter.new({ 'type' => 'Label', 'text' => 'x', 'partialAttributes' => [{ 'range' => text }] },
                                  0, nil).convert,
        views::ImageConverter.new({ 'type' => 'Image', 'src' => 'pic', 'alt' => text }, 0, nil).convert,
        "Text(#{expr.swift_text_expr(%(specimenProbe ?? "#{text}"))})"
      ].join("\n")
      expect(compilable_view("VStack {\n#{view}\n}", data: ['var specimenProbe: String? = nil'])).to compile_as_swift

      declarations = [{ 'name' => 'probeText', 'class' => 'String', 'defaultValue' => text },
                      { 'name' => 'probeObject', 'class' => 'Object', 'defaultValue' => { 'k' => text } }]
                     .map { |property| data_model.(property)[/^ *var #{property['name']}: .*$/] }
      expect(compilable_data(declarations.join("\n"))).to compile_as_swift
    end
  end

  # Byte identity: a text with nothing to escape comes out as `"text"` on
  # every path, so regenerating such a layout changes nothing.
  it 'writes a plain text as "plain text" on every path' do
    expect(lit.swift(plain)).to eq('"plain text"')
    aggregate_failures do
      paths.each do |name, kind, emit, fragment|
        fragment ||= ->(s) { s }
        expect(emit.(plain)).to include(fragment.(literal_for[kind][plain])), name
      end
    end
  end
end
