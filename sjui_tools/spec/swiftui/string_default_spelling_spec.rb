# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require 'swiftui/data_model_updater'
require 'swiftui/helpers/string_manager_helper'
require 'uikit/json_loader'

# What a String defaultValue's spelling means, on every path sjui writes one
# (JsonUIShared::StringLiterals.default_text is the one reading):
#   bare (canonical)  the text as written
#   ''                empty
#   "…"               JSON's escapes; when they do not parse, the text
#                     between the quotes as written
#   '…'               the text between the quotes as written
# Each row's text is written out by hand, not computed by default_text; each
# path's output is compiled and RUN with swiftc, and must read back as it.
#
# Until 1.8.121 the SwiftUI face wrapped the spelling in quotes as it stood,
# so `"Test"` became the value `"Test"` with its quotes; the UIKit face
# passed `"…"` through as Swift, where `\u00e9` does not compile and `\(t)`
# interpolates. Ticket codegen-string-literals-are-not-escaped-for-the-target-
# language, remaining 1. The lookup rows below are remaining 3.
RSpec.describe 'a String defaultValue reads the same on every sjui path' do
  rows = [
    ['bare', 'Hello', 'Hello'],
    ['bare, every special character', %q{Say "hi" \ $x \(z) ${y} `b` it's}, %q{Say "hi" \ $x \(z) ${y} `b` it's}],
    ['bare, a quote at one end only', '"lead', '"lead'],
    ['bare, an apostrophe at one end only', "trail'", "trail'"],
    ['bare, one quote', '"', '"'],
    ["''", "''", ''],
    ['"" (JSON\'s empty)', '""', ''],
    ['"…"', '"Test"', 'Test'],
    ['"…" with no escape', '"Pay $x ${y} `b` {c} it\'s"', "Pay $x ${y} `b` {c} it's"],
    ['"…" with JSON\'s escapes', '"a\nb \"hi\" \\\\ \u00e9 \/ \t"', "a\nb \"hi\" \\ \u00e9 / \t"],
    ['"…" with an escape JSON does not have', '"C:\new \(t)"', 'C:\new \(t)'],
    ['"…" that is not JSON', '"a"b"', 'a"b'],
    ["'…'", "'Single'", 'Single'],
    ["'…' holding ''", "'it''s'", "it''s"],
    ["'…' holding a backslash", "'a\\nb'", 'a\nb']
  ]

  # The spellings in the table are Ruby literals: check the two that are
  # easy to misread before anything is measured with them.
  it 'spells its own rows as intended' do
    expect(rows[9][1].chars.first(4)).to eq(['"', 'a', '\\', 'n'])
    expect(rows[10][1]).to eq('"C:' + '\\' + 'new ' + '\\' + '(t)"')
  end

  no_strings = ->(object) { object.define_singleton_method(:load_strings_json) { {} } }

  swiftui = lambda do |spelling|
    updater = SjuiTools::SwiftUI::DataModelUpdater.allocate
    updater.instance_variable_set(:@mode, 'swiftui')
    no_strings.(updater)
    content = updater.send(:generate_data_content, 'Probe',
                           [{ 'name' => 'probe', 'class' => 'String', 'defaultValue' => spelling }])
    content[/^ *var probe: String = (.*)$/, 1]
  end

  uikit_loader = lambda do |spelling|
    loader = SjuiTools::UIKit::JsonLoader.allocate
    analyzer = Struct.new(:data_sets, :partial_bindings).new(
      [{ 'name' => 'probe', 'class' => 'String', 'defaultValue' => spelling }],
      [{ property_name: 'part', binding_class: 'PartBinding', shared_data_bindings: { 'k' => '@{probe}' } }]
    )
    loader.instance_variable_set(:@json_analyzer, analyzer)
    string_manager = Object.new
    string_manager.define_singleton_method(:string_registered?) { |_| false }
    loader.instance_variable_set(:@string_manager, string_manager)
    loader.define_singleton_method(:check_data_passed_to_partials) { |_| false }
    loader.define_singleton_method(:check_data_bound_to_collection) { |_| false }
    loader
  end

  paths = {
    'SwiftUI data model (var probe: String = …)' => swiftui,
    'UIKit data variable' => lambda { |spelling|
      uikit_loader.(spelling).send(:generate_data_variables, { super_binding: 'Binding' })[/^ *var probe: String = (.*)$/, 1]
    },
    'UIKit partial shared_data default' => lambda { |spelling|
      uikit_loader.(spelling).send(:generate_initializer)[/^ *self\.partBinding\.k = (.*)$/, 1]
    }
  }

  # Each path's expressions in one program; when it does not compile, each
  # row alone, so a failure names its rows.
  swift_values = lambda do |expressions|
    run = lambda do |exprs|
      program = "extension String { func localized() -> String { self } }\n" +
                exprs.map { |e| "print(Array((#{e}).unicodeScalars.map { $0.value }))" }.join("\n")
      Dir.mktmpdir do |dir|
        File.write(File.join(dir, 'main.swift'), "#{program}\n")
        _, err, status = Open3.capture3('swiftc', '-o', File.join(dir, 'main'), File.join(dir, 'main.swift'))
        next [:not_compiled, err] unless status.success?

        got, = Open3.capture3(File.join(dir, 'main'))
        [:ok, got.lines.map { |l| JSON.parse(l) }]
      end
    end
    status, got = run.(expressions)
    next got if status == :ok

    expressions.map do |e|
      s, g = run.([e])
      s == :ok ? g.first : "does not compile: #{e}"
    end
  end

  paths.each do |path_name, emit|
    it "#{path_name}: every spelling reads back as its text (swiftc)" do
      unless system('which swiftc > /dev/null 2>&1')
        raise 'swiftc is not on PATH in CI' if ENV['CI']

        skip 'swiftc is not on PATH: the round trip is UNMEASURED here'
      end
      emitted = rows.map { |_, spelling, _| emit.(spelling) }
      expect(emitted).to all(be_a(String))
      got = swift_values.(emitted)
      aggregate_failures do
        rows.each_with_index do |(name, spelling, text), i|
          expect(got[i]).to eq(text.codepoints),
                            "#{name}: #{spelling} was written #{emitted[i]}, read back as " \
                            "#{got[i].is_a?(Array) ? got[i].pack('U*').inspect : got[i]}, want #{text.inspect}"
        end
      end
    end
  end

  # The declarations as they stand in the Data model, compiled against the
  # library stubs (spec/support/emitted_swift.rb) — the round trips above
  # compile each expression alone.
  it 'writes declarations that compile in the Data model' do
    lines = rows.each_with_index.map do |(_, spelling, _), i|
      "var probe#{i}: String = #{swiftui.(spelling)}\nvar uikit#{i}: String = #{paths['UIKit data variable'].(spelling)}"
    end
    expect(compilable_data(lines.join("\n"))).to compile_as_swift
  end

  # The canonical spelling is untouched: a bare text comes out as it did.
  it 'writes a bare plain text as "text" on the SwiftUI and UIKit data paths' do
    expect(swiftui.('Hello World')).to eq('"Hello World"')
    expect(paths['UIKit data variable'].('Hello World')).to eq('"Hello World".localized()')
  end

  # Remaining 3: the lookup took every `"` out of the text, so a text
  # holding one missed the value the extractor stored — and matched a
  # DIFFERENT text that lacks the quotes.
  describe 'the strings.json lookup keeps the quotes inside the text' do
    helper = SjuiTools::SwiftUI::Helpers::StringManagerHelper
    lookup = lambda do |strings, text_content|
      instance = Class.new { include SjuiTools::SwiftUI::Helpers::StringManagerHelper }.new
      instance.define_singleton_method(:load_strings_json) { strings }
      instance.get_text_with_string_manager(text_content, warnings: false)
    end

    before { helper.current_namespaces = %w[screen] }
    after { helper.current_namespaces = [] }

    it 'finds the value the extractor stored with its quotes' do
      expect(lookup.({ 'screen' => { 'say_hi' => 'Say "hi"' } }, '"Say "hi""'))
        .to eq('StringManager.Screen.sayHi()')
    end

    it 'does not resolve to a value that lacks them' do
      expect(lookup.({ 'screen' => { 'say_hi' => 'Say hi' } }, '"Say "hi""')).to eq('"Say \"hi\""')
    end

    it 'finds it from a "…" data default too' do
      updater = SjuiTools::SwiftUI::DataModelUpdater.allocate
      updater.instance_variable_set(:@mode, 'swiftui')
      updater.define_singleton_method(:load_strings_json) { { 'screen' => { 'say_hi' => 'Say "hi"' } } }
      expect(updater.send(:format_default_value, '"Say \"hi\""', 'String')).to eq('StringManager.Screen.sayHi()')
    end
  end
end
