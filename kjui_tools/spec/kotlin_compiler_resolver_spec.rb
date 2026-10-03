# frozen_string_literal: true

require 'fileutils'
require 'tmpdir'
require_relative 'support/kotlin_compiler'

# The harness compiles with the versions CI pins, found in their own cache
# directories, once per process (ticket kjui-spec-kotlinc-harness-globs-the-
# whole-gradle-cache-and-picks-the-newest-compiler). It took the newest jar
# under `caches/**` on every call: a developer machine's 2.4.20 where CI pins
# 2.1.0, and 13.4s a call over a 42G cache.
RSpec.describe KotlinCompiler do
  def place(home, group, artifact, version)
    dir = File.join(home, 'caches', 'modules-2', 'files-2.1', group, artifact, version, 'f00d')
    FileUtils.mkdir_p(dir)
    FileUtils.touch(File.join(dir, "#{artifact}-#{version}.jar"))
  end

  around do |example|
    saved = described_class.instance_variable_get(:@jars)
    described_class.instance_variable_set(:@jars, nil)
    example.run
  ensure
    described_class.instance_variable_set(:@jars, saved)
  end

  it 'reads the pinned versions from the fetch script CI runs' do
    script = File.read(described_class::FETCH_SCRIPT)
    lines = script[/^jars=\((.*?)^\)/m, 1].lines.grep(/^\s+"\S+ \S+ \S+ \h{64}"$/) # the rows, not the comments
    expect(described_class::PINNED.size).to eq(lines.size)
    expect(described_class::PINNED[%w[org.jetbrains.kotlin kotlin-compiler-embeddable]]).to eq(script[/kotlin-compiler-embeddable (\S+) /, 1])
    expect(described_class.compiler_version).to eq('2.1.0')
  end

  it 'takes the pinned compiler when a newer one is in the cache too (newest does not win)' do
    Dir.mktmpdir do |home|
      place(home, 'org.jetbrains.kotlin', 'kotlin-compiler-embeddable', '2.4.20')
      place(home, 'org.jetbrains.kotlin', 'kotlin-compiler-embeddable', '2.1.0')
      got = described_class.resolve('org.jetbrains.kotlin', 'kotlin-compiler-embeddable', home: home)
      expect(File.basename(got)).to eq('kotlin-compiler-embeddable-2.1.0.jar')
    end
  end

  it 'takes 1.10 when 1.10 is pinned and 1.9 is there too (a string sort takes 1.9)' do
    Dir.mktmpdir do |home|
      place(home, 'g', 'lib', '1.9')
      place(home, 'g', 'lib', '1.10')
      got = described_class.resolve('g', 'lib', home: home, pinned: { %w[g lib] => '1.10' })
      expect(File.basename(got)).to eq('lib-1.10.jar')
      expect(described_class.resolve('g', 'lib', home: home, pinned: { %w[g lib] => '1.9' })).to end_with('lib-1.9.jar')
    end
  end

  it 'finds nothing when only another version is in the cache' do
    Dir.mktmpdir do |home|
      place(home, 'org.jetbrains.kotlin', 'kotlin-compiler-embeddable', '2.4.20')
      expect(described_class.resolve('org.jetbrains.kotlin', 'kotlin-compiler-embeddable', home: home)).to be_nil
    end
  end

  it 'resolves each jar once per process' do
    calls = 0
    allow(described_class).to receive(:resolve).and_wrap_original { |m, *a, **k| calls += 1; m.call(*a, **k) }
    3.times { described_class.jar('org.jetbrains.kotlin', 'kotlin-stdlib') }
    expect(calls).to eq(1)
  end

  it 'names the pinned version and how to fetch it when a jar is missing, and fails under KJUI_REQUIRE_KOTLINC=1' do
    skip 'no JDK for the harness here' unless described_class.java_bin
    allow(described_class).to receive(:jar).and_return(nil)
    reason = described_class.find_unavailable_reason
    expect(reason).to include('kotlin-compiler-embeddable:2.1.0').and include('fetch_kotlin_compiler_jars.sh')

    saved = ENV['KJUI_REQUIRE_KOTLINC']
    ENV['KJUI_REQUIRE_KOTLINC'] = '1'
    expect { described_class.unavailable_reason }.to raise_error(described_class::Unavailable, /fetch_kotlin_compiler_jars/)
  ensure
    ENV['KJUI_REQUIRE_KOTLINC'] = saved
  end
end
