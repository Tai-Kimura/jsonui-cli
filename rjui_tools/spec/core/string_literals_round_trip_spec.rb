# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require 'core/string_literals'

# The one TypeScript escaper every generator helper writes an author's text
# with (lib/core/string_literals.rb, a byte-identical copy of
# shared/core/string_literals.rb), in each of its forms — a "…" literal, a
# '…' literal, the inside of a template literal, and a JSX child — evaluated
# by node: the value must be the text.
# Ticket codegen-string-literals-are-not-escaped-for-the-target-language.
RSpec.describe 'JsonUIShared::StringLiterals (TypeScript)' do
  TEXTS = [
    "It`s {one} C:\\new ${y} \"q\" 'a' <b>",
    "tab\there\nnew\rline",
    "nul\u0000bell\u0007del\u007f",
    "ls\u2028ps\u2029",
    'plain text',
    '日本語と絵文字🔍'
  ].freeze

  L = JsonUIShared::StringLiterals

  def node_values(expressions)
    unless system('which node > /dev/null 2>&1')
      raise 'node is not on PATH in CI' if ENV['CI']

      skip 'node is not on PATH: the round trip is UNMEASURED here'
    end
    Dir.mktmpdir do |dir|
      file = File.join(dir, 'main.mjs')
      File.write(file, expressions.map { |e| "console.log(JSON.stringify([...(#{e})].map((c) => c.codePointAt(0))));" }.join("\n"))
      out, err, status = Open3.capture3('node', file)
      expect(status).to be_success, err
      out.lines.map { |l| JSON.parse(l) }
    end
  end

  {
    'a "…" literal' => ->(t) { L.ts(t) },
    "a '…' literal" => ->(t) { L.ts_single(t) },
    'a template literal' => ->(t) { "`#{L.ts_template_body(t)}`" },
    'a JSX child made an expression' => ->(t) { L.jsx_text("{#{t}")[1..-2] }
  }.each do |form, write|
    it "reads back as the text, in #{form}" do
      texts = form.start_with?('a JSX') ? TEXTS.map { |t| "{#{t}" } : TEXTS
      expect(node_values(TEXTS.map(&write))).to eq(texts.map(&:codepoints))
    end
  end

  it 'leaves a text with nothing special to JSX as it is, and a plain literal as it was' do
    expect(L.jsx_text('plain text')).to eq('plain text')
    expect(L.jsx_text('A & B')).to eq('A & B')
    expect(L.ts('plain text')).to eq('"plain text"')
  end

  # JSX text reads `&amp;` as `&`: an author's character reference stays
  # text only inside an expression.
  it 'puts a text holding a character reference in an expression' do
    expect(L.jsx_text('Tom &amp; Jerry')).to eq('{"Tom &amp; Jerry"}')
    expect(L.jsx_text('x &#123; y')).to eq('{"x &#123; y"}')
  end

  # The trap it replaces: in a gsub replacement STRING "\\`" is the text
  # before the match — the JSX escapers turned It`s into ItIts.
  it 'keeps a backtick, which the replacement-string spelling turned into the text before it' do
    expect('a`b'.gsub('`', '\\`')).to eq('aab')
    expect(node_values(["`#{L.ts_template_body('a`b')}`"])).to eq(['a`b'.codepoints])
  end
end
