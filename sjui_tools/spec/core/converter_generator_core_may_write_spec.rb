# frozen_string_literal: true

require 'core/converter_generator_core'
require 'stringio'
require 'tmpdir'

# The one overwrite decision every `g converter` writer goes through.
#
# Until 1.8.112 the six platform sub-generators each asked on their own with
# `gets.chomp`, so --skip-existing / JUI_SKIP_EXISTING / --force stopped at
# the converter file and a closed stdin raised NoMethodError on nil
# (jui-converter-scaffold-subgenerators-block-on-stdin). The canonical copy is
# shared/core/converter_generator_core.rb; the mirror spec pins the per-tool
# copies byte-identical, so pinning the behaviour once is enough.
RSpec.describe JsonUIShared::ConverterGeneratorCore do
  let(:dir) { Dir.mktmpdir('may_write') }
  let(:path) { File.join(dir, 'Thing.swift') }
  let(:logger) { double('logger', info: nil, warn: nil) }

  around do |example|
    saved_env = ENV.delete('JUI_SKIP_EXISTING')
    saved_stdin = $stdin
    example.run
  ensure
    $stdin = saved_stdin
    saved_env.nil? ? ENV.delete('JUI_SKIP_EXISTING') : ENV['JUI_SKIP_EXISTING'] = saved_env
    FileUtils.rm_rf(dir)
  end

  # A terminal a person types `input` into (then end-of-file).
  def terminal(input)
    StringIO.new(input).tap { |io| io.define_singleton_method(:tty?) { true } }
  end

  # A String is typed on a terminal; anything else is the stdin as given.
  def decide(options = {}, stdin: '')
    $stdin = stdin.is_a?(String) ? terminal(stdin) : stdin
    asks = options.empty? && !ENV['JUI_SKIP_EXISTING'] && $stdin.respond_to?(:tty?) && $stdin.tty?
    out = nil
    expect { out = described_class.may_write?(path, options, logger, noun: 'swift file') }
      .to output(asks ? /Overwrite\? \(y\/n\)/ : '').to_stdout
    out
  end

  # A stdin that fails the example if anything reads it — not a terminal,
  # like a pipe held open and never written.
  let(:untouchable_stdin) do
    Object.new.tap do |o|
      o.define_singleton_method(:gets) { raise 'stdin was read' }
      o.define_singleton_method(:tty?) { false }
    end
  end

  it 'writes a file that does not exist, without asking' do
    $stdin = untouchable_stdin
    expect(described_class.may_write?(path, {}, logger, noun: 'swift file')).to be true
  end

  context 'when the file exists' do
    before { File.write(path, '// hand-maintained') }

    it 'treats a terminal closed without an answer as "n" instead of raising' do
      expect(decide({}, stdin: '')).to be false
    end

    # Until 1.9.0 the prompt read any stdin: a pipe held open and never
    # written (an MCP server's child, an agent's shell) waited forever.
    it 'keeps it without asking or reading when stdin is not a terminal, and says so with --force' do
      expect(decide({}, stdin: untouchable_stdin)).to be false
      expect(decide({}, stdin: StringIO.new("y\n"))).to be false # "y" on a pipe is not an answer
      expect(logger).to have_received(:info)
        .with("Kept existing swift file: #{path} (stdin is not a terminal; --force replaces it)").twice
    end

    it 'overwrites on "y" and keeps on "n"' do
      expect(decide({}, stdin: "y\n")).to be true
      expect(decide({}, stdin: "N\n")).to be false
    end

    it 'skips without asking under JUI_SKIP_EXISTING=1' do
      ENV['JUI_SKIP_EXISTING'] = '1'
      expect(decide({}, stdin: untouchable_stdin)).to be false
      expect(logger).to have_received(:info).with(/Skipped existing swift file/)
    end

    it 'skips without asking under --skip-existing' do
      expect(decide({ skip_existing: true }, stdin: untouchable_stdin)).to be false
    end

    it 'overwrites without asking under --force' do
      expect(decide({ force: true }, stdin: untouchable_stdin)).to be true
    end

    it 'lets skip win over force, as the converter always has' do
      expect(decide({ force: true, skip_existing: true }, stdin: untouchable_stdin)).to be false
    end
  end
end
