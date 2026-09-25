# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require 'core/type_converter'
require 'core/string_literals'
require 'compose/data_model_updater'
require_relative '../support/kotlin_compiler'

# What a String defaultValue's spelling means, on every path kjui writes one
# (JsonUIShared::StringLiterals.default_text is the one reading):
#   bare (canonical)  the text as written
#   ''                empty
#   "…"               JSON's escapes; when they do not parse, the text
#                     between the quotes as written
#   '…'               the text between the quotes as written
# Each row (shared/core/string_default_vectors.json) is written by hand, not
# computed by default_text; each path's output is compiled with kotlinc and
# RUN on the JVM, and must read back as it.
#
# Until 1.8.121 a `"…"` default was passed through as written, so a `$` in
# it became a template and `\/` did not compile; the strings.xml key was
# looked up with the same text. Ticket codegen-string-literals-are-not-
# escaped-for-the-target-language, remaining 1.
RSpec.describe 'a String defaultValue reads the same on every kjui path' do
  # The table every reader is measured with — the three generators here,
  # SwiftJsonUI and KotlinJsonUI's dynamic mode from their vendored copy.
  vectors = JSON.parse(File.read(File.expand_path('../../../shared/core/string_default_vectors.json', __dir__)))
  rows = vectors['spellings'].map { |row| row.values_at('name', 'spelling', 'text') }

  # The table's JSON spells the two easiest to misread as intended.
  it 'reads its rows as intended' do
    spelling = ->(name) { rows.find { |row| row[0] == name }[1] }
    expect(spelling.("\"…\" with JSON's escapes").chars.first(4)).to eq(['"', 'a', '\\', 'n'])
    expect(spelling.('"…" with an escape JSON does not have')).to eq('"C:' + '\\' + 'new ' + '\\' + '(t)"')
  end

  updater = KjuiTools::Compose::DataModelUpdater.allocate
  updater.instance_variable_set(:@resolved_string_defaults, {})

  paths = {
    'the field default (var probe: String = …)' => ->(s) { updater.send(:format_default_value, s, 'String') },
    'the fromMap fallback' => lambda { |s|
      updater.send(:from_map_fallback, { 'name' => 'probe', 'defaultValue' => s }, 'String', '""')
    }
  }

  kotlin_values = lambda do |expressions|
    k = KotlinCompiler
    stdlib = k.newest('org.jetbrains.kotlin', 'kotlin-stdlib')
    compiler = [k.compiler_jar, stdlib, k.newest('org.jetbrains.kotlin', 'kotlin-reflect'),
                k.newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm'), k.newest('org.jetbrains', 'annotations'),
                k.newest('org.jetbrains.intellij.deps', 'trove4j')].compact.join(':')
    run = lambda do |exprs|
      program = "fun main() {\n" + exprs.map do |e|
        "  println((#{e}).codePoints().toArray().joinToString(\",\", \"[\", \"]\"))"
      end.join("\n") + "\n}\n"
      Dir.mktmpdir do |dir|
        File.write(File.join(dir, 'Main.kt'), program)
        _, _, status = Open3.capture3(k.java_bin, '-cp', compiler, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                                      '-no-stdlib', '-cp', stdlib, '-d', File.join(dir, 'out'), File.join(dir, 'Main.kt'))
        next [:not_compiled] unless status.success?

        got, = Open3.capture3(k.java_bin, '-cp', "#{File.join(dir, 'out')}:#{stdlib}", 'MainKt')
        [:ok, got.lines.map { |l| JSON.parse(l) }]
      end
    end
    status, got = run.(expressions)
    next got if status == :ok

    # Each row alone, so a failure names its rows.
    expressions.map do |e|
      s, g = run.([e])
      s == :ok ? g.first : "does not compile: #{e}"
    end
  end

  paths.each do |path_name, emit|
    it "#{path_name}: every spelling reads back as its text (kotlinc + JVM)" do
      if (reason = KotlinCompiler.unavailable_reason)
        raise reason if ENV['CI']

        skip "#{reason}: the round trip is UNMEASURED here"
      end
      emitted = rows.map { |_, spelling, _| emit.(spelling) }
      expect(emitted).to all(be_a(String))
      got = kotlin_values.(emitted)
      aggregate_failures do
        rows.each_with_index do |(name, spelling, text), i|
          expect(got[i]).to eq(text.codepoints),
                            "#{name}: #{spelling} was written #{emitted[i]}, read back as " \
                            "#{got[i].is_a?(Array) ? got[i].pack('U*').inspect : got[i]}, want #{text.inspect}"
        end
      end
    end
  end

  # The strings.xml key a default resolves through is looked up with the
  # same text the field writes (nil and "" both mean no lookup).
  it 'looks the strings.xml key up with the same text' do
    aggregate_failures do
      rows.each do |name, spelling, text|
        expect(updater.send(:string_default_inner, spelling).to_s).to eq(text), name
      end
    end
  end

  # The fields as they stand in a Data class, compiled (the round trips
  # above compile each expression alone).
  it 'writes fields that compile in a Data class' do
    fields = rows.each_with_index.map do |(_, spelling, _), i|
      "    var probe#{i}: String = #{updater.send(:format_default_value, spelling, 'String')}"
    end
    expect("data class ProbeData(\n#{fields.join(",\n")}\n)\n").to compile_as_kotlin
  end

  # The canonical spelling is untouched: a bare text comes out as it did.
  it 'writes a bare plain text as "text"' do
    expect(updater.send(:format_default_value, 'Hello World', 'String')).to eq('"Hello World"')
  end

  # A value written per platform ({ "swift": …, "kotlin": … }): the one
  # this platform gets, or — when the layout gives it none — the class's
  # vocabulary value and a WARNING naming the layout, the property and the
  # platform (ruling 2026-09-26). Until 1.8.121 the Hash went on as the
  # value, and rjui wrote `"{"swift"=>"eager", "kotlin"=>"lazy"}"`.
  describe 'a defaultValue written per platform' do
    converter = KjuiTools::Core::TypeConverter
    vectors['platforms'].each do |row|
      it "#{row['name']}: kotlin gets #{row['expect']['kotlin'].inspect}" do
        allow(converter).to receive(:report_warning)
        normalized = converter.normalize_data_property(
          { 'name' => 'probe', 'class' => row['class'], 'defaultValue' => row['defaultValue'] },
          'compose', source: 'screens/probe.json'
        )
        value = normalized['defaultValue']
        # A String value is read as its spelling says, as the writer reads it.
        value = JsonUIShared::StringLiterals.default_text(value) if row['class'] == 'String' && value.is_a?(String)
        expect(value).to eq(row['expect']['kotlin'])
        if row['warnFor'].include?('kotlin')
          expect(converter).to have_received(:report_warning)
            .once.with(a_string_including("screens/probe.json: data 'probe'", 'but not kotlin'))
        else
          expect(converter).not_to have_received(:report_warning)
        end
      end
    end
  end
end
