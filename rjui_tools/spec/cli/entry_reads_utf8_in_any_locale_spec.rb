# frozen_string_literal: true

require 'fileutils'
require 'json'
require 'open3'
require 'rbconfig'
require 'tmpdir'

# rjui-build-crashes-at-startup-in-a-non-utf8-locale: sjui and kjui have set
# Encoding.default_external to UTF-8 in their bin since the first commit; rjui
# did not. With LANG unset (US-ASCII) on Ruby 3.3.1 / json 2.16.0,
# `rjui build` stopped at start-up parsing attribute_definitions.json.
RSpec.describe 'bin/rjui in a US-ASCII locale' do
  let(:bin) { File.expand_path('../../bin/rjui', __dir__) }

  around do |example|
    Dir.mktmpdir('rjui_c_locale') do |dir|
      @dir = dir
      example.run
    end
  end

  # Runs ruby under the C locale with a probe that prints, at exit, the
  # default_external the program left behind. Returns the process's
  # stdout + stderr as `log` — not emitted TypeScript, which the compile
  # gate (emitted_typescript_reaches_a_compiler_spec) finds by the names of
  # what is asserted (code / ts… / out… / result).
  def run_in_c_locale(*argv)
    probe = File.join(@dir, 'encoding_probe.rb')
    File.write(probe, "at_exit { STDERR.puts \"DEFAULT_EXTERNAL=\#{Encoding.default_external}\" }\n")
    env = { 'LANG' => 'C', 'LC_ALL' => 'C', 'LC_CTYPE' => nil,
            'RUBYOPT' => "#{ENV['RUBYOPT']} -r#{probe}".strip }
    out, err, status = Open3.capture3(env, RbConfig.ruby, *argv, chdir: @dir, stdin_data: '')
    [out + err, status]
  end

  def default_external_in(log)
    log[/^DEFAULT_EXTERNAL=(\S+)$/, 1]
  end

  it 'reads as UTF-8 although the locale says US-ASCII' do
    # The control: without rjui, this environment really is US-ASCII —
    # otherwise the next line would pass with or without the pin.
    control, = run_in_c_locale('-e', '')
    expect(default_external_in(control)).to eq('US-ASCII')

    log, = run_in_c_locale(bin, 'help')
    expect(default_external_in(log)).to eq('UTF-8')
  end

  # A raw UTF-8 --attribute-descriptions (typed by hand; `jui` sends it
  # \u-escaped) is binary under the C locale. rjui recorded it in the
  # attribute definition's marker, and Ruby 2.6.10 raised writing that — after
  # the converter and component were written. Ruby 3.3.1 wrote it; there the
  # last line (the marker no longer carries the JSON) is what tells.
  it 'writes a converter from a raw UTF-8 --attribute-descriptions' do
    log, status = run_in_c_locale(bin, 'g', 'converter', 'Probe', '--attributes', 'scale:Int',
                                     '--attribute-descriptions', '{"scale":"目盛りの数"}')
    expect(status.exitstatus).to eq(0), log
    defs = Dir.glob(File.join(@dir, '**', 'attribute_definitions', 'Probe.json'))
    expect(defs.size).to eq(1), log
    content = JSON.parse(File.read(defs.first, encoding: 'UTF-8'))
    expect(content['Probe']['scale']['description']).to eq('目盛りの数')
    expect(content['_generated']['generator']).not_to include('attribute-descriptions')
  end

  # Where the json gem re-encodes non-UTF-8 input (json 2.16.0 on 3.3.1 does;
  # 2.1.0 on 2.6.10 does not), this is the start-up failure itself. The
  # arm above is the one that tells the two apart on every Ruby.
  it 'builds a project in the C locale' do
    FileUtils.mkdir_p(File.join(@dir, 'src', 'Layouts'))
    File.write(File.join(@dir, 'src', 'Layouts', 'home.json'),
               JSON.generate('type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'hello' }]))

    log, status = run_in_c_locale(bin, 'build')
    expect(log).not_to include('InvalidByteSequenceError')
    expect(status.exitstatus).to eq(0), log
  end
end
