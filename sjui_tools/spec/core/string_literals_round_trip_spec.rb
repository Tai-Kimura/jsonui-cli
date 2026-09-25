# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require 'core/string_literals'

# The one Swift escaper every generator helper writes an author's text with
# (lib/core/string_literals.rb, a byte-identical copy of
# shared/core/string_literals.rb): each text below, as the literal it writes,
# compiled and RUN with swiftc and read back — the value must be the text.
# Ticket codegen-string-literals-are-not-escaped-for-the-target-language.
RSpec.describe 'JsonUIShared::StringLiterals.swift' do
  TEXTS = [
    "Say \"hi\" \\ $x ${y} \\(z) `b` {c} <d> it's",
    "tab\there\nnew\rline",
    "nul\u0000bell\u0007del\u007f",
    "ls\u2028ps\u2029",
    'plain text',
    '日本語と絵文字🔍'
  ].freeze

  it 'writes a literal that reads back as the text, for every special character' do
    unless system('which swiftc > /dev/null 2>&1')
      raise 'swiftc is not on PATH in CI' if ENV['CI']

      skip 'swiftc is not on PATH: the round trip is UNMEASURED here'
    end
    program = TEXTS.map do |text|
      "print(Array((#{JsonUIShared::StringLiterals.swift(text)}).unicodeScalars.map { $0.value }))"
    end.join("\n")
    Dir.mktmpdir do |dir|
      File.write(File.join(dir, 'main.swift'), "#{program}\n")
      out, err, status = Open3.capture3('swiftc', '-o', File.join(dir, 'main'), File.join(dir, 'main.swift'))
      expect(status).to be_success, out + err
      got, _, run = Open3.capture3(File.join(dir, 'main'))
      expect(run).to be_success
      expect(got.lines.map { |l| JSON.parse(l) }).to eq(TEXTS.map(&:codepoints))
    end
  end

  it 'leaves a text with no special character as it was: `"text"`' do
    expect(JsonUIShared::StringLiterals.swift('plain text')).to eq('"plain text"')
  end

  # The trap it replaces: a gsub replacement string reads `\\` as ONE
  # backslash, so this spelling left `\` undoubled and `\(` interpolating.
  it 'doubles a backslash, which the replacement-string spelling did not' do
    expect('a\\b'.gsub('\\', '\\\\')).to eq('a\\b')
    expect(JsonUIShared::StringLiterals.swift('a\\b')).to eq('"a\\\\b"')
  end
end
