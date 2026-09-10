# frozen_string_literal: true

require 'json'
require 'open3'

# Run emitted code through a bundler's compile-time `define`, the way a
# consumer's production build does, and hand back what survives.
#
# WHY. `screenMarker` is gated on `process.env.NODE_ENV`, and the gate only
# works when the bundler replaces that expression at build time and folds the
# dead branch away. A string assertion that the source MENTIONS NODE_ENV says
# nothing about that. Measured 2026-09-10: the helper had carried
# `typeof process !== 'undefined' && process?.env?.NODE_ENV` since 2026-07-27
# — its own comment said it kept the literal form — and Next 16.2.10
# (Turbopack) shipped the marker in every web face's production build while
# the spec named 'gated on NODE_ENV' stayed green.
#
# esbuild stands in for the consumer bundlers here: its `define` follows the
# rule they all follow (a literal member expression is replaced; an optional
# chain or a `typeof` guard is not), and it runs inside a spec in well under a
# second. Turbopack was measured by hand and cannot run here.
#
# Installed beside tsc by `npm ci --prefix rjui_tools/spec/support`. When it
# is absent the example SKIPS through `mark_skipped!`, never a bare raise —
# see typescript_compiler.rb for why a bare raise would read as PASSED.
module BundlerDefine
  module_function

  SUPPORT_DIR = __dir__

  def esbuild_path
    File.join(SUPPORT_DIR, 'node_modules', '.bin', 'esbuild')
  end

  def unavailable_reason
    return 'node is not on PATH' unless system('which node > /dev/null 2>&1')
    unless File.executable?(esbuild_path)
      return 'esbuild is not installed (npm ci --prefix rjui_tools/spec/support)'
    end

    nil
  end

  def skip_unless_available!
    reason = unavailable_reason
    return unless reason

    message = "bundler define: #{reason}"
    example = RSpec.current_example
    RSpec::Core::Pending.mark_skipped!(example, message) if example
    raise RSpec::Core::Pending::SkipDeclaredInExample, message
  end

  # What a build leaves of `source` once `process.env.NODE_ENV` is the
  # compile-time constant `node_env`. `--minify-syntax` is the constant
  # folding: without it a replaced comparison is still a comparison and the
  # dead branch stays in the text, which is not what a consumer build ships.
  def fold(source, node_env:, loader: 'ts')
    out, err, status = Open3.capture3(
      esbuild_path, "--loader=#{loader}", '--format=esm', '--minify-syntax',
      "--define:process.env.NODE_ENV=#{JSON.generate(node_env)}",
      stdin_data: source
    )
    raise "esbuild failed (#{status.exitstatus}): #{err}" unless status.success?

    out
  end
end
