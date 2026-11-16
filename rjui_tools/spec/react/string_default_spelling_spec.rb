# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require 'core/type_converter'
require 'core/string_literals'
require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/data_model_generator'

# What a String defaultValue's spelling means, on every path rjui writes one
# (JsonUIShared::StringLiterals.default_text is the one reading):
#   bare (canonical)  the text as written
#   ''                empty
#   "…"               JSON's escapes; when they do not parse, the text
#                     between the quotes as written
#   '…'               the text between the quotes as written
# Each row (shared/core/string_default_vectors.json) is written by hand, not
# computed by default_text; the emitted expression is evaluated by node and
# must read back as it.
#
# Until 1.9.0 a quoted spelling passed through as written (`'it''s'` is
# not TS) and a bare one was quoted without escaping (`"Say "hi""`); the
# string-table lookup took off a quote at either end on its own. Ticket
# codegen-string-literals-are-not-escaped-for-the-target-language,
# remaining 1.
RSpec.describe 'a String defaultValue reads the same on every rjui path' do
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

  generator = RjuiTools::React::DataModelGenerator.allocate

  # One node process for every expression; when it does not parse, each
  # expression alone, so a failure names its rows.
  node_values = lambda do |expressions|
    run = lambda do |exprs|
      Dir.mktmpdir do |dir|
        file = File.join(dir, 'main.mjs')
        File.write(file, exprs.map { |e| "console.log(JSON.stringify([...(#{e})].map((c) => c.codePointAt(0))));" }.join("\n"))
        out, _, status = Open3.capture3('node', file)
        status.success? ? [:ok, out.lines.map { |l| JSON.parse(l) }] : [:not_parsed]
      end
    end
    status, got = run.(expressions)
    next got if status == :ok

    expressions.map do |e|
      s, g = run.([e])
      s == :ok ? g.first : "does not parse: #{e}"
    end
  end

  it 'the data default (probe: …): every spelling reads back as its text (node)' do
    unless system('which node > /dev/null 2>&1')
      raise 'node is not on PATH in CI' if ENV['CI']

      skip 'node is not on PATH: the round trip is UNMEASURED here'
    end
    emitted = rows.map { |_, spelling, _| generator.send(:format_default_value, spelling, 'string', 'String') }
    got = node_values.(emitted)
    aggregate_failures do
      rows.each_with_index do |(name, spelling, text), i|
        expect(got[i]).to eq(text.codepoints),
                          "#{name}: #{spelling} was written #{emitted[i]}, read back as " \
                          "#{got[i].is_a?(Array) ? got[i].pack('U*').inspect : got[i]}, want #{text.inspect}"
      end
    end
  end

  # The string-table lookup a default resolves through is asked for the
  # same text the default writes (not asked at all for an empty one).
  it 'looks the string table up with the same text' do
    asked = nil
    probe = RjuiTools::React::DataModelGenerator.allocate
    probe.define_singleton_method(:convert_string_key) { |text, warnings: nil| (asked = text) && nil }
    probe.define_singleton_method(:lookup_string_manager_by_value) { |_| nil }
    aggregate_failures do
      rows.each do |name, spelling, text|
        asked = nil
        probe.send(:string_default_expression, spelling, 'string')
        expect(asked.to_s).to eq(text), name
      end
    end
  end

  # The canonical spelling is untouched: a bare text comes out as it did.
  it 'writes a bare plain text as "text"' do
    expect(generator.send(:format_default_value, 'Hello World', 'string', 'String')).to eq('"Hello World"')
  end

  # Not a String: TypeConverter already wrote Color and Image defaults as
  # code (`"#FF0000"`, `"/images/x"`), and they pass through as before.
  it 'passes a Color or Image default through as TypeConverter wrote it' do
    expect(generator.send(:format_default_value, '"#FF0000"', 'string', 'Color')).to eq('"#FF0000"')
    expect(generator.send(:format_default_value, "'/images/x'", 'string', 'Image')).to eq("'/images/x'")
  end

  # A String? default reads as a String's, and none stays undefined
  # (vectors['optionalStrings']). Until 1.9.0 a String? default was written
  # as it stood, as code: `probe: Hello`.
  it 'the data default of a String?: every row reads back as its text, or undefined (node)' do
    unless system('which node > /dev/null 2>&1')
      raise 'node is not on PATH in CI' if ENV['CI']

      skip 'node is not on PATH: the round trip is UNMEASURED here'
    end
    optional_rows = vectors['optionalStrings']
    emitted = optional_rows.map { |row| generator.send(:format_default_value, row['spelling'], 'string | undefined', 'String?') }
    program = emitted.map do |e|
      "{ const v = (#{e}); console.log(v === undefined ? 'nil' : JSON.stringify([...v].map((c) => c.codePointAt(0)))); }"
    end.join("\n")
    got = Dir.mktmpdir do |dir|
      File.write(File.join(dir, 'main.mjs'), program)
      out, err, status = Open3.capture3('node', File.join(dir, 'main.mjs'))
      raise "does not parse:\n#{err}\n#{program}" unless status.success?

      out.lines.map(&:strip)
    end
    aggregate_failures do
      optional_rows.each_with_index do |row, i|
        want = row['text'].nil? ? 'nil' : row['text'].codepoints.to_s.delete(' ')
        expect(got[i]).to eq(want), "#{row['name']}: #{row['spelling'].inspect} was written #{emitted[i]}"
      end
    end
  end

  # tsc over every default written, under --strict, as the types the data
  # model declares them with: a String's is a `string`, a String?'s a
  # `string | undefined`. node reads the values back above; this is what a
  # consumer's compiler makes of the same text.
  it 'writes defaults that compile as the types the data model declares', :typescript_compile do
    strings = rows.map { |_, spelling, _| generator.send(:format_default_value, spelling, 'string', 'String') }
    optionals = vectors['optionalStrings'].map do |row|
      generator.send(:format_default_value, row['spelling'], 'string | undefined', 'String?')
    end
    source = strings.each_with_index.map { |e, i| "export const s#{i}: string = #{e};\n" }.join +
             optionals.each_with_index.map { |e, i| "export const o#{i}: string | undefined = #{e};\n" }.join
    expect(source).to compile_as_typescript
  end

  # A value written per platform ({ "swift": …, "kotlin": … }): the one
  # this platform gets, or — when the layout gives it none — the class's
  # vocabulary value and a WARNING naming the layout, the property and the
  # platform (ruling 2026-09-26). Until 1.9.0 the Hash went on as the
  # value, and rjui wrote `"{"swift"=>"eager", "kotlin"=>"lazy"}"`.
  describe 'a defaultValue written per platform' do
    converter = RjuiTools::Core::TypeConverter
    vectors['platforms'].each do |row|
      it "#{row['name']}: typescript gets #{row['expect']['typescript'].inspect}" do
        allow(converter).to receive(:report_warning)
        normalized = converter.normalize_data_property(
          { 'name' => 'probe', 'class' => row['class'], 'defaultValue' => row['defaultValue'] },
          'react', source: 'screens/probe.json'
        )
        value = normalized['defaultValue']
        # A String value is read as its spelling says, as the writer reads it.
        value = JsonUIShared::StringLiterals.default_text(value) if row['class'] == 'String' && value.is_a?(String)
        expect(value).to eq(row['expect']['typescript'])
        if row['warnFor'].include?('typescript')
          expect(converter).to have_received(:report_warning)
            .once.with(a_string_including("screens/probe.json: data 'probe'", 'but not typescript'))
        else
          expect(converter).not_to have_received(:report_warning)
        end
      end
    end
  end
end
