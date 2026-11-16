# frozen_string_literal: true

require 'json'
require 'open3'
require 'rbconfig'
require 'tmpdir'
require_relative '../../spec_helper'
require 'core/config_manager'

# rjui-clean-keeps-a-helper-the-running-version-no-longer-emits.
#
# The helpers `rjui build` writes at the top of src/generated/ were written
# every build and never pruned: a helper this build does not write stayed.
# Measured by the docsite lane: a 1.9.0 build then a v1.8.120 `--clean`
# build left includeId.ts; and at one version, a `jui build` that turns the
# include prefix on (JSONUI_INCLUDE_ID_PREFIX=on) followed by a standalone
# `rjui build` leaves it too. Every build now deletes a top-level file that
# carries @generated with `Generator: rjui build` and that no emitter wrote
# this run; a file under another generator's @generated is named and kept,
# and a file without the sentinel is the user's and is left alone.
RSpec.describe 'rjui build: generated helpers this build no longer writes' do
  def rjui(dir, *args, env: {})
    out, status = Open3.capture2e(env, RbConfig.ruby, File.expand_path('../../../bin/rjui', __dir__), *args, chdir: dir)
    raise "rjui #{args.join(' ')}: #{out}" unless status.success?

    out.gsub(/\e\[[0-9;]*m/, '')
  end

  def helpers(dir)
    Dir.children(File.join(dir, 'src/generated')).select { |n| File.file?(File.join(dir, 'src/generated', n)) }.sort
  end

  def marked(generator)
    "/* eslint-disable */\n" \
      "// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT\n" \
      "// ║  Source:    oldHelper (a helper an earlier version wrote)\n" \
      "// ║  Generator: #{generator}\n" \
      "export const x = 1;\n"
  end

  # A TypeScript project built once with the include prefix on (the helper
  # emitted), then handed to the block.
  def project
    Dir.mktmpdir('rjui_helpers') do |dir|
      File.write(File.join(dir, 'rjui.config.json'),
                 JSON.pretty_generate(RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => true)))
      rjui(dir, 'init')
      rjui(dir, 'g', 'view', 'home_screen')
      rjui(dir, 'build', env: { 'JSONUI_INCLUDE_ID_PREFIX' => 'on' })
      yield dir
    end
  end

  it 'a standalone build after an include-prefix build deletes includeId.ts and names it' do
    project do |dir|
      first = helpers(dir)
      expect(first).to include('includeId.ts')
      log = rjui(dir, 'build')
      expect(helpers(dir)).to eq(first - ['includeId.ts'])
      expect(log).to include('Pruned 1 generated helper(s) this build no longer writes:')
      expect(log).to include('  - src/generated/includeId.ts')
    end
  end

  it 'the helpers this build writes, and the outputs other stages own, all survive' do
    project do |dir|
      rjui(dir, 'build')
      expect(helpers(dir)).to include(
        'ColorManager.ts', 'StringManager.ts', 'autoShrink.ts', 'cellIdGenerator.ts', 'collectionScroll.ts',
        'dateFormat.ts', 'interactionStop.ts', 'partialText.ts', 'relativePosition.ts', 'screenMarker.ts', 'theme.css'
      )
    end
  end

  it 'the build that emits includeId keeps it' do
    project do |dir|
      rjui(dir, 'build', env: { 'JSONUI_INCLUDE_ID_PREFIX' => 'on' })
      expect(helpers(dir)).to include('includeId.ts')
    end
  end

  it "a helper a later version dropped (rjui build's mark, no emitter) is deleted — the forward direction" do
    project do |dir|
      old = File.join(dir, 'src/generated/oldHelper.ts')
      File.write(old, marked('rjui build'))
      rjui(dir, 'build', env: { 'JSONUI_INCLUDE_ID_PREFIX' => 'on' })
      expect(File.exist?(old)).to be(false)
    end
  end

  it 'a file the user wrote there (no @generated) survives, unnamed' do
    project do |dir|
      mine = File.join(dir, 'src/generated/index.ts')
      File.write(mine, "export * from './screenMarker';\n")
      log = rjui(dir, 'build')
      expect(File.read(mine)).to eq("export * from './screenMarker';\n")
      expect(log).not_to include('src/generated/index.ts')
    end
  end

  it "another generator's @generated file is kept and named" do
    project do |dir|
      other = File.join(dir, 'src/generated/apiClient.ts')
      File.write(other, marked('openapi-codegen'))
      log = rjui(dir, 'build')
      expect(File.exist?(other)).to be(true)
      expect(log).to include('  - src/generated/apiClient.ts: delete it by hand if nothing imports it')
    end
  end

  it 'ColorManager survives a build whose colour stage failed and did not rewrite it' do
    project do |dir|
      File.write(File.join(dir, 'src/Layouts/Resources/colors.json'), '{ not json')
      log, = Open3.capture2e(RbConfig.ruby, File.expand_path('../../../bin/rjui', __dir__), 'build', chdir: dir)
      expect(log).to match(/colors/i)
      expect(helpers(dir)).to include('ColorManager.ts', 'theme.css')
    end
  end
end
