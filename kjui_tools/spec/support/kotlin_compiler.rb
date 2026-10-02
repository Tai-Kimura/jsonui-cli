# frozen_string_literal: true

require 'open3'
require 'tmpdir'

# Compile emitted Kotlin from the suite.
#
# `dev-guide/release/compile-emitted-kotlin.sh` says it plainly: the Kotlin
# emitter is the only one of the three whose output no check on this machine
# ever compiled — `tsc --noEmit` and `swiftc` run in the suites, and nothing
# answers for Kotlin. That script is a release procedure and covers only the
# branch-test runtime, so the DATA MODEL emitter had no compiler behind it at
# all. What that costs is measured: `map_to_kotlin_type('Object')` returned
# `"Object"` and `format_default_value` returned a Ruby Hash, so the emitted
# line was
#
#     var profile: Object = {"name"=>"Grace"}
#
# — neither half Kotlin — and every unit example was green, because they
# asserted the emitted TEXT.
#
# There is no `kotlinc` on PATH here. The compiler is taken from the Gradle
# cache the way the release script takes it, and the example SKIPS (visibly,
# in the count) when that cache is absent, rather than passing.
module KotlinCompiler
  module_function

  # GRADLE_USER_HOME is Gradle's own override of ~/.gradle; CI fills a cache
  # at the default place with .github/scripts/fetch_kotlin_compiler_jars.sh.
  GRADLE_HOME = ENV.fetch('GRADLE_USER_HOME') { File.join(Dir.home, '.gradle') }
  GRADLE_MODULES = File.join(GRADLE_HOME, 'caches', 'modules-2', 'files-2.1')

  def newest(group, artifact)
    Dir.glob(File.join(GRADLE_MODULES, group, artifact, '**', "#{artifact}-*.jar"))
       .reject { |p| p.include?('sources') || p.include?('javadoc') }
       .sort.last
  end

  def compiler_jar
    Dir.glob(File.join(GRADLE_HOME, 'caches', '**',
                       'kotlin-compiler-embeddable-*.jar'))
       .reject { |p| p.include?('sources') }
       .sort.last
  end

  HOMEBREW_JAVA = '/opt/homebrew/opt/openjdk@17/bin/java'
  # The JDKs the pinned compiler (kotlin-compiler-embeddable 2.1.0) is
  # measured on: 17 on the release machine, 21 on Linux (2026-09-28).
  ACCEPTED_JAVA_MAJORS = (17..21).freeze

  # The `java` a compile runs on, in this order:
  #   1. KOTLINC_JAVA — an explicit path, taken as given (CI sets it to the
  #      setup-java JDK);
  #   2. Homebrew's openjdk@17 — the release machine. Its Android Studio JBR
  #      on PATH is Java 25 and `/usr/libexec/java_home -v 17` answers 21, so
  #      neither PATH nor java_home is asked;
  #   3. JAVA_HOME, when its `release` file names a major in
  #      ACCEPTED_JAVA_MAJORS (a JAVA_HOME pointing at that JBR is refused).
  def java_bin
    return @java_bin if defined?(@java_bin)

    candidates = [explicit_java, HOMEBREW_JAVA, java_home_java].compact
    @java_bin = candidates.find { |c| File.executable?(c) }
  end

  def explicit_java
    path = ENV.fetch('KOTLINC_JAVA', '')
    path.empty? ? nil : path
  end

  def java_home_java
    home = ENV.fetch('JAVA_HOME', '')
    return nil if home.empty?

    release = File.join(home, 'release')
    version = File.exist?(release) && File.read(release)[/^JAVA_VERSION="(\d+)/, 1]
    version && ACCEPTED_JAVA_MAJORS.cover?(version.to_i) ? File.join(home, 'bin', 'java') : nil
  end

  # A JVM started while JAVA_TOOL_OPTIONS (or JDK_JAVA_OPTIONS) is set writes
  # "Picked up JAVA_TOOL_OPTIONS: …" to stderr before anything else, so an arm
  # that reads the merged output of an emitted `main` finds that line too.
  # Drop it; it is the JVM's, not the program's.
  JVM_NOTICE = /^(?:NOTE: )?Picked up (?:JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS|_JAVA_OPTIONS):.*\R?/.freeze

  def strip_jvm_notices(text)
    text.to_s.gsub(JVM_NOTICE, '')
  end

  # Open3.capture2e on `java_bin`, with the JVM's notices dropped from the
  # merged output (an arm that parses a `main`'s lines would otherwise read
  # "Picked up JAVA_TOOL_OPTIONS: …" as one of them).
  def java_capture2e(*args)
    out, status = Open3.capture2e(java_bin, *args)
    [strip_jvm_notices(out), status]
  end

  # Raised instead of a skip when KJUI_REQUIRE_KOTLINC=1 (CI's kjui leg sets
  # it once it has fetched the compiler): a leg that is meant to compile must
  # not go back to pending without anyone seeing it.
  class Unavailable < StandardError; end

  # nil when a compile can be attempted; otherwise why it cannot.
  def unavailable_reason
    reason = find_unavailable_reason
    if reason && ENV['KJUI_REQUIRE_KOTLINC'] == '1'
      raise Unavailable, "KJUI_REQUIRE_KOTLINC=1 and the Kotlin compiler is unavailable: #{reason}"
    end

    reason
  end

  def find_unavailable_reason
    unless java_bin
      return 'no JDK 17 at /opt/homebrew/opt/openjdk@17, no KOTLINC_JAVA, ' \
             "no JAVA_HOME with Java #{ACCEPTED_JAVA_MAJORS.min}-#{ACCEPTED_JAVA_MAJORS.max}"
    end
    return 'no kotlin-compiler-embeddable in the Gradle cache' unless compiler_jar

    missing = REQUIRED.reject { |g, a| newest(g, a) }
    return "not in the Gradle cache: #{missing.map { |g, a| "#{g}:#{a}" }.join(', ')}" if missing.any?

    nil
  end

  REQUIRED = [
    %w[org.jetbrains.kotlin kotlin-stdlib],
    %w[org.jetbrains.kotlin kotlin-reflect],
    %w[org.jetbrains annotations],
    %w[org.jetbrains.kotlinx kotlinx-coroutines-core-jvm]
  ].freeze

  Result = Struct.new(:success, :errors) do
    def success?
      success
    end
  end

  # Libraries a source may compile against beyond the stdlib, by name — for
  # emitted code that calls them for real (the Dynamic wrappers read Gson).
  LIBRARIES = { gson: %w[com.google.code.gson gson] }.freeze

  def compile(source, libraries: [])
    stdlib   = newest('org.jetbrains.kotlin', 'kotlin-stdlib')
    reflect  = newest('org.jetbrains.kotlin', 'kotlin-reflect')
    annots   = newest('org.jetbrains', 'annotations')
    coroutin = newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
    trove    = newest('org.jetbrains.intellij.deps', 'trove4j')

    # The compiler's own classpath and the compiled file's target classpath
    # are different sets; conflating them fails inside the compiler with
    # NoClassDefFoundError instead of a diagnostic about the source.
    compiler_cp = [compiler_jar, stdlib, reflect, coroutin, annots, trove].compact.join(':')
    extra       = libraries.map { |lib| newest(*LIBRARIES.fetch(lib)) }
    target_cp   = ([stdlib, reflect, annots, coroutin] + extra).compact.join(':')

    Dir.mktmpdir('kjui_kotlin') do |dir|
      file = File.join(dir, 'Emitted.kt')
      File.write(file, source)
      out, err, = Open3.capture3(
        java_bin, '-cp', compiler_cp,
        'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
        '-no-stdlib', '-cp', target_cp, '-d', File.join(dir, 'out'), file
      )
      text = "#{out}\n#{err}"
      errors = text.lines.select { |l| l.include?('error:') }.map(&:strip)
      Result.new(errors.empty?, errors)
    end
  end

  Run = Struct.new(:success, :errors, :output) do
    def success?
      success
    end
  end

  # Compiles `source` (a file with a top-level `fun main()`) and runs it on
  # the JVM: for an arm that asks what emitted code DOES — a gate that calls
  # when it is open and not when it is shut — not only that it type-checks.
  # `libraries` as for compile (LIBRARIES): on the compile and the run
  # classpath both.
  def run(source, libraries: [])
    stdlib   = newest('org.jetbrains.kotlin', 'kotlin-stdlib')
    reflect  = newest('org.jetbrains.kotlin', 'kotlin-reflect')
    annots   = newest('org.jetbrains', 'annotations')
    coroutin = newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
    trove    = newest('org.jetbrains.intellij.deps', 'trove4j')
    compiler_cp = [compiler_jar, stdlib, reflect, coroutin, annots, trove].compact.join(':')
    extra       = libraries.map { |lib| newest(*LIBRARIES.fetch(lib)) }
    target_cp   = ([stdlib, reflect, annots, coroutin] + extra).compact.join(':')

    Dir.mktmpdir('kjui_kotlin_run') do |dir|
      file = File.join(dir, 'Emitted.kt')
      File.write(file, source)
      out_dir = File.join(dir, 'out')
      out, err, = Open3.capture3(
        java_bin, '-cp', compiler_cp,
        'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
        '-no-stdlib', '-cp', target_cp, '-d', out_dir, file
      )
      errors = "#{out}\n#{err}".lines.select { |l| l.include?('error:') }.map(&:strip)
      return Run.new(false, errors, '') unless errors.empty?

      stdout, stderr, status = Open3.capture3(java_bin, '-cp', "#{out_dir}:#{target_cp}", 'EmittedKt')
      Run.new(status.success?, status.success? ? [] : [strip_jvm_notices(stderr).strip], stdout)
    end
  end
end

RSpec::Matchers.define :compile_as_kotlin do |*libraries|
  match do |source|
    # Skipped, not passed and not failed. Recorded BEFORE raising, as `skip`
    # itself does: a bare raise ends the example as PASSED, which is how an
    # unavailable compiler would otherwise look identical to a green one.
    if (reason = KotlinCompiler.unavailable_reason)
      message = "compile_as_kotlin: #{reason}; this example runs where the Gradle cache carries Kotlin"
      example = RSpec.current_example
      RSpec::Core::Pending.mark_skipped!(example, message) if example
      raise RSpec::Core::Pending::SkipDeclaredInExample, message
    end
    missing = libraries.reject { |lib| KotlinCompiler.newest(*KotlinCompiler::LIBRARIES.fetch(lib)) }
    unless missing.empty?
      message = "compile_as_kotlin: not in the Gradle cache: #{missing.join(', ')}"
      raise KotlinCompiler::Unavailable, message if ENV['KJUI_REQUIRE_KOTLINC'] == '1'

      example = RSpec.current_example
      RSpec::Core::Pending.mark_skipped!(example, message) if example
      raise RSpec::Core::Pending::SkipDeclaredInExample, message
    end

    @result = KotlinCompiler.compile(source, libraries: libraries)
    @result.success?
  end

  failure_message do |source|
    "expected the emitted Kotlin to compile, but got:\n" \
      "#{@result.errors.map { |e| "  #{e}" }.join("\n")}\n\nSource:\n#{source}"
  end
end
