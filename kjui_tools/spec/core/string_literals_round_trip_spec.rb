# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require 'core/string_literals'
require_relative '../support/kotlin_compiler'

# The one Kotlin escaper every generator helper writes an author's text with
# (lib/core/string_literals.rb, a byte-identical copy of
# shared/core/string_literals.rb): each text below, as the literal it writes,
# compiled with kotlinc and RUN on the JVM — the value must be the text.
# `$` is the character Kotlin reads as a template.
# Ticket codegen-string-literals-are-not-escaped-for-the-target-language.
RSpec.describe 'JsonUIShared::StringLiterals.kotlin' do
  TEXTS = [
    "Pay $x ${y} \\ \"hi\" \\(z) `b` {c} <d> it's",
    "tab\there\nnew\rline",
    "nul\u0000bell\u0007del\u007f back\b",
    'plain text',
    '日本語と絵文字🔍'
  ].freeze

  it 'writes a literal that reads back as the text, for every special character' do
    if (reason = KotlinCompiler.unavailable_reason)
      raise reason if ENV['CI']

      skip "#{reason}: the round trip is UNMEASURED here"
    end
    k = KotlinCompiler
    stdlib = k.newest('org.jetbrains.kotlin', 'kotlin-stdlib')
    compiler = [k.compiler_jar, stdlib, k.newest('org.jetbrains.kotlin', 'kotlin-reflect'),
                k.newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm'), k.newest('org.jetbrains', 'annotations'),
                k.newest('org.jetbrains.intellij.deps', 'trove4j')].compact.join(':')
    program = "fun main() {\n" + TEXTS.map do |text|
      "  println(#{JsonUIShared::StringLiterals.kotlin(text)}.codePoints().toArray().joinToString(\",\", \"[\", \"]\"))"
    end.join("\n") + "\n}\n"
    Dir.mktmpdir do |dir|
      File.write(File.join(dir, 'Main.kt'), program)
      out, err, status = Open3.capture3(k.java_bin, '-cp', compiler, 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                                        '-no-stdlib', '-cp', stdlib, '-d', File.join(dir, 'out'), File.join(dir, 'Main.kt'))
      expect(status).to be_success, (out + err)[-2000..]
      got, _, run = Open3.capture3(k.java_bin, '-cp', "#{File.join(dir, 'out')}:#{stdlib}", 'MainKt')
      expect(run).to be_success
      expect(got.lines.map { |l| JSON.parse(l) }).to eq(TEXTS.map(&:codepoints))
    end
  end

  it 'leaves a text with no special character as it was: `"text"`' do
    expect(JsonUIShared::StringLiterals.kotlin('plain text')).to eq('"plain text"')
  end

  it 'escapes `$`, which the quote helpers did not' do
    expect(JsonUIShared::StringLiterals.kotlin('Pay $x')).to eq('"Pay \\$x"')
  end
end
