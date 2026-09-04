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

  GRADLE_MODULES = File.join(Dir.home, '.gradle', 'caches', 'modules-2', 'files-2.1')

  def newest(group, artifact)
    Dir.glob(File.join(GRADLE_MODULES, group, artifact, '**', "#{artifact}-*.jar"))
       .reject { |p| p.include?('sources') || p.include?('javadoc') }
       .sort.last
  end

  def compiler_jar
    Dir.glob(File.join(Dir.home, '.gradle', 'caches', '**',
                       'kotlin-compiler-embeddable-*.jar'))
       .reject { |p| p.include?('sources') }
       .sort.last
  end

  def java_bin
    # The Android Studio JBR on PATH is Java 25 and `/usr/libexec/java_home
    # -v 17` answers 21 here, so neither is asked.
    candidate = '/opt/homebrew/opt/openjdk@17/bin/java'
    File.executable?(candidate) ? candidate : nil
  end

  # nil when a compile can be attempted; otherwise why it cannot.
  def unavailable_reason
    return 'no JDK 17 at /opt/homebrew/opt/openjdk@17' unless java_bin
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

  def compile(source)
    stdlib   = newest('org.jetbrains.kotlin', 'kotlin-stdlib')
    reflect  = newest('org.jetbrains.kotlin', 'kotlin-reflect')
    annots   = newest('org.jetbrains', 'annotations')
    coroutin = newest('org.jetbrains.kotlinx', 'kotlinx-coroutines-core-jvm')
    trove    = newest('org.jetbrains.intellij.deps', 'trove4j')

    # The compiler's own classpath and the compiled file's target classpath
    # are different sets; conflating them fails inside the compiler with
    # NoClassDefFoundError instead of a diagnostic about the source.
    compiler_cp = [compiler_jar, stdlib, reflect, coroutin, annots, trove].compact.join(':')
    target_cp   = [stdlib, reflect, annots, coroutin].compact.join(':')

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
end

RSpec::Matchers.define :compile_as_kotlin do
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

    @result = KotlinCompiler.compile(source)
    @result.success?
  end

  failure_message do |source|
    "expected the emitted Kotlin to compile, but got:\n" \
      "#{@result.errors.map { |e| "  #{e}" }.join("\n")}\n\nSource:\n#{source}"
  end
end
