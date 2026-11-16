# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../../lib/cli/commands/build_command'
require 'tmpdir'

# The screen marker's production gate — canon: shared/core/screen_identity.json
# → marker.buildGating.platforms.web.
#
# The canon requires the literal `process.env.NODE_ENV` form because that is
# the one expression bundlers replace at build time. From 2026-07-27 to
# 2026-09-10 the helper carried
#
#     typeof process !== 'undefined' && process?.env?.NODE_ENV === 'production'
#
# — written to satisfy a `| undefined` declaration — while its own comment and
# its commit message said it kept the literal form. Nothing pinned the
# difference: the one spec that named the gate asserted an import line.
# Measured on 2026-09-10 with Next 16.2.10 (Turbopack, `next build` +
# `next start`, an element mounted on the client): the production chunk kept
# `i.default?.env?.NODE_ENV==="production"?{}:{"data-screen":…}` — `process`
# resolved to the bundler's polyfill, whose `env` is empty in a browser — and
# the marker rendered. Every web face builds with that bundler. esbuild's
# define kept it too: `typeof process < "u" ? {} : {"data-screen": id}`.
#
# So these are the arms the canon asks for: the text has the literal form and
# none of the spellings that defeat replacement; it type-checks without
# @types/node and beside a global `process`; and a production define FOLDS the
# marker away while a development define keeps it. The fold arms run through
# esbuild (spec/support/bundler_define.rb), and the previous form goes through
# the same arm as a control, so the arm is known to see the defect it guards.
RSpec.describe 'the generated screenMarker helper' do
  def emit(typescript:)
    Dir.mktmpdir('rjui_marker') do |dir|
      instance = RjuiTools::CLI::Commands::BuildCommand.allocate
      instance.instance_variable_set(:@config, {
                                       'typescript' => typescript,
                                       'generated_directory' => File.join(dir, 'generated')
                                     })
      instance.send(:emit_screen_marker_helper)
      return File.read(File.join(dir, 'generated', typescript ? 'screenMarker.ts' : 'screenMarker.js'))
    end
  end

  let(:ts) { emit(typescript: true) }
  let(:js) { emit(typescript: false) }

  # The form shipped from a2f06144 (2026-07-27) until 2026-09-10 — the
  # control for the fold arms. An arm that cannot turn red on this text is
  # not measuring the property.
  let(:previous_form) do
    <<~TS
      declare const process: { env?: { NODE_ENV?: string } } | undefined;
      export function screenMarker(screenId: string): Record<string, string> {
        if (typeof process !== 'undefined' && process?.env?.NODE_ENV === 'production') {
          return {};
        }
        return { 'data-screen': screenId };
      }
    TS
  end

  describe 'text' do
    it 'keeps the literal process.env.NODE_ENV form the canon requires' do
      expect(ts).to include("process.env.NODE_ENV === 'production'")
      expect(js).to include("process.env.NODE_ENV === 'production'")
    end

    it 'has none of the spellings that defeat compile-time replacement' do
      [ts, js].each do |code|
        expect(code).not_to include('typeof process')
        expect(code).not_to include('?.env')
        expect(code).not_to include('globalThis')
      end
    end

    it 'declares process as a module-scoped shape that allows the plain member read (TypeScript only)' do
      expect(ts).to include('declare const process: { env: { NODE_ENV?: string } };')
      expect(js).not_to include('declare')
    end
  end

  describe 'type-check' do
    it 'compiles under --strict with no @types/node' do
      expect(ts).to compile_as_typescript
    end

    it 'compiles beside a global process declaration, the @types/node shape' do
      expect(ts).to compile_as_typescript.with_ambient(
        'declare var process: { env: Record<string, string | undefined>; platform: string };'
      )
    end
  end

  describe 'compile-time replacement (esbuild define, standing in for the consumer bundlers)' do
    before { BundlerDefine.skip_unless_available! }

    it 'a production define folds the marker away' do
      expect(BundlerDefine.fold(ts, node_env: 'production')).not_to include('data-screen')
    end

    it 'a development define keeps it' do
      expect(BundlerDefine.fold(ts, node_env: 'development')).to include('data-screen')
    end

    it 'the JavaScript variant folds the same way' do
      expect(BundlerDefine.fold(js, node_env: 'production', loader: 'js')).not_to include('data-screen')
      expect(BundlerDefine.fold(js, node_env: 'development', loader: 'js')).to include('data-screen')
    end

    it 'CONTROL: the previous typeof-guarded form survives the same production define' do
      # The defect this file exists for, fed through the arm above. Should a
      # future esbuild fold `typeof process` away, this passes the define and
      # the arm has lost its discriminator — it then needs a new control.
      expect(BundlerDefine.fold(previous_form, node_env: 'production')).to include('data-screen')
    end
  end
end
