# frozen_string_literal: true

require 'open3'
require 'tmpdir'

# Type-check emitted TypeScript from the suite.
#
# WHY THIS DID NOT EXIST, AND WHY THE ABSENCE WAS INVISIBLE
#
# `dev-guide/release/compile-emitted-kotlin.sh` justified itself by saying
# "`tsc --noEmit` and `swiftc -parse` run in the suite, and nothing answers
# for Kotlin". Measured: nothing answered for TypeScript either. There was no
# matcher, no `spec/support` directory, and no rjui spec invoked a compiler.
# The claim had gone stale and was reassuring the reader on a face it did not
# cover.
#
# One rjui spec parses emitted JSX with `@babel/parser`. Parsing is not
# enough, and that is measured rather than assumed: on the Swift side
# `swiftc -parse` accepted `data.collectionDataSource.getCellData(...)` with
# zero errors — a property nothing declares calling a method that exists
# nowhere — and only `-typecheck` rejected it. The same class of defect in
# emitted TSX passes a parser untouched.
#
# WHERE THE COMPILER COMES FROM
#
# `spec/support/package.json` pins it as a devDependency, installed with
# `npm ci --prefix rjui_tools/spec/support`. It cannot reach a consumer:
# `jui sync_tool` deletes `spec/` by default and the distribution does not
# ship it, so nothing here becomes part of rjui_tools as distributed.
#
# When the install is absent the example SKIPS — recorded through
# `mark_skipped!`, never a bare raise, because a bare raise ends an example as
# PASSED and "no compiler here" would then look exactly like "compiled fine".
module TypeScriptCompiler
  module_function

  SUPPORT_DIR = __dir__

  def tsc_path
    File.join(SUPPORT_DIR, 'node_modules', '.bin', 'tsc')
  end

  def unavailable_reason
    return 'node is not on PATH' unless system('which node > /dev/null 2>&1')
    unless File.executable?(tsc_path)
      return 'typescript is not installed (npm ci --prefix rjui_tools/spec/support)'
    end

    nil
  end

  # Minimal ambient declarations so a TSX fragment can be checked without
  # pulling React itself in. Deliberately small: every type a fragment needs
  # is declared by the spec that emits it, because a permissive stub accepts
  # output the real consumer build would reject.
  AMBIENT = <<~TS
    declare namespace JSX {
      interface Element {}
      interface IntrinsicElements { [name: string]: any }
      interface ElementChildrenAttribute { children: {} }
    }
    declare const React: any;
  TS

  Result = Struct.new(:success, :errors) do
    def success?
      success
    end
  end

  # `--strict` on purpose: the emitted code lands in consumer projects that
  # run strict, and a check looser than the consumer's is a check that passes
  # what the consumer rejects.
  def compile(source, ambient: AMBIENT)
    Dir.mktmpdir('rjui_ts') do |dir|
      File.write(File.join(dir, 'ambient.d.ts'), ambient)
      File.write(File.join(dir, 'Emitted.tsx'), source)
      out, err, = Open3.capture3(
        # `--jsx react` (classic), not `react-jsx`: the automatic runtime
        # requires `react/jsx-runtime` to resolve, and React is deliberately
        # not installed here — the point is to type-check emitted code, not to
        # vendor a UI framework into the spec support. Classic mode only needs
        # `React` in scope, which the ambient declares.
        tsc_path, '--noEmit', '--strict', '--jsx', 'react',
        '--target', 'ES2020', '--moduleResolution', 'bundler', '--module', 'esnext',
        '--skipLibCheck',
        File.join(dir, 'ambient.d.ts'), File.join(dir, 'Emitted.tsx')
      )
      text = "#{out}\n#{err}"
      errors = text.lines.select { |l| l.include?('error TS') }.map(&:strip)
      Result.new(errors.empty?, errors)
    end
  end
end

RSpec::Matchers.define :compile_as_typescript do
  match do |source|
    if (reason = TypeScriptCompiler.unavailable_reason)
      message = "compile_as_typescript: #{reason}"
      example = RSpec.current_example
      RSpec::Core::Pending.mark_skipped!(example, message) if example
      raise RSpec::Core::Pending::SkipDeclaredInExample, message
    end

    @result = TypeScriptCompiler.compile(source, ambient: @ambient || TypeScriptCompiler::AMBIENT)
    @result.success?
  end

  chain :with_ambient do |ambient|
    @ambient = "#{TypeScriptCompiler::AMBIENT}\n#{ambient}"
  end

  failure_message do |source|
    "expected the emitted TypeScript to type-check, but got:\n" \
      "#{@result.errors.map { |e| "  #{e}" }.join("\n")}\n\nSource:\n#{source}"
  end
end
