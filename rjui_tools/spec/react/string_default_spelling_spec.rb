# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../spec_helper'
require 'react/data_model_generator'

# What a String defaultValue's spelling means, on every path rjui writes one
# (JsonUIShared::StringLiterals.default_text is the one reading):
#   bare (canonical)  the text as written
#   ''                empty
#   "…"               JSON's escapes; when they do not parse, the text
#                     between the quotes as written
#   '…'               the text between the quotes as written
# Each row's text is written out by hand, not computed by default_text; the
# emitted expression is evaluated by node and must read back as it.
#
# Until 1.8.121 a quoted spelling passed through as written (`'it''s'` is
# not TS) and a bare one was quoted without escaping (`"Say "hi""`); the
# string-table lookup took off a quote at either end on its own. Ticket
# codegen-string-literals-are-not-escaped-for-the-target-language,
# remaining 1.
RSpec.describe 'a String defaultValue reads the same on every rjui path' do
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
end
