# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# A gate must answer "what does this tree say", not "when did this last run".
#
# The build cache filtered `files_to_update` by mtime and validation lived
# inside the codegen loop, so a second `sjui build --strict` over an untouched
# tree printed "No files need updating (all cached)", found nothing, and
# exited 0 — where the first run exited 1. Measured on 1.8.44: three
# consecutive runs, exit 0 with zero finding lines, after a --clean run exited
# 1 with six.
#
# The cache may still skip CODEGEN. That is what it is for.
#
# Everything is resolved from this checkout: no installed CLI, no `jui` on
# $PATH, `sjui_tools` symlinked so its relative `lib/core/*` links resolve.
RSpec.describe 'validation is not cached' do
  REPO_ROOT = File.expand_path('../../../..', __dir__)

  def project
    dir = Dir.mktmpdir('cache_gate')
    name = 'GateProbe'
    File.write(File.join(dir, 'jui.config.json'), JSON.pretty_generate(
      'project_name' => name, 'spec_directory' => 'docs/screens/json',
      'component_spec_directory' => 'docs/components/json', 'strings_file' => '',
      'type_map_file' => '.jsonui-type-map.json',
      'platforms' => { 'ios' => { 'root' => '.', 'layoutsDir' => "#{name}/Layouts", 'mode' => 'swiftui' } }
    ))
    File.write(File.join(dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => 'swiftui', 'project_name' => name, 'project_file_name' => name,
      'source_directory' => name, 'layouts_directory' => 'Layouts',
      'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
      'view_directory' => 'View', 'data_directory' => 'Data',
      'viewmodel_directory' => 'ViewModel',
      'resource_manager_directory' => 'ResourceManager',
      'string_files' => ["#{name}/Localizable.strings"], 'use_network' => true
    ))
    File.write(File.join(dir, '.jsonui-type-map.json'), '{}')
    FileUtils.mkdir_p(File.join(dir, "#{name}.xcodeproj"))
    layouts = File.join(dir, name, 'Layouts')
    FileUtils.mkdir_p(layouts)
    # refused by the shared validator (`Segment.items` takes no binding),
    # warned by the binding validator (`@{a}` with no data), and clean.
    File.write(File.join(layouts, 'sample.json'),
               JSON.generate('type' => 'Segment', 'id' => 'seg', 'items' => '@{choices}'))
    File.write(File.join(layouts, 'warned.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => [{ 'type' => 'Label', 'id' => 'lbl', 'text' => '@{a}' }]
    ))
    File.write(File.join(layouts, 'healthy.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent',
      'height' => 'matchParent', 'child' => []
    ))
    FileUtils.ln_s(File.join(REPO_ROOT, 'sjui_tools'), File.join(dir, 'sjui_tools'))
    dir
  end

  def sjui(dir, *args)
    Open3.capture2e('ruby', File.join(dir, 'sjui_tools', 'bin', 'sjui'), 'build', *args, chdir: dir)
  end

  # Run until the cache reports everything cached, so the examples below are
  # measuring the cached path and not merely a repeat build.
  # Build until the cache reports everything cached, so the examples below
  # measure the cached path rather than a plain repeat build.
  #
  # The `sleep` is load-bearing: the stamp and the layout mtimes have
  # one-second granularity, and a build run inside the same second as the
  # previous one still looks dirty. Without it the loop never settles —
  # measured: six back-to-back runs all said "Updating 3 of 3", and the same
  # tree said "all cached" on the next run a minute later.
  def settle(dir)
    8.times do
      log, = sjui(dir)
      return log if log.include?('No files need updating (all cached)')

      sleep 1.1
    end
    raise 'the cache never reported all-cached; this spec would assert nothing'
  end

  it 'reports findings on a cached run, and --strict still fails' do
    dir = project
    settle(dir)

    log, status = sjui(dir, '--strict')
    expect(log).to include('No files need updating (all cached)'), log
    expect(log).to match(/binding warning/), log
    expect(status.exitstatus).to eq(1), "cached --strict must fail like the first run\n#{log}"
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  it 'names a refused layout on a cached run and records it' do
    dir = project
    settle(dir)

    log, = sjui(dir)
    expect(log).to include('[error]'), log
    expect(log).to include('was not generated'), log
    expect(log).to include('stage(s) incomplete'), log
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  # The control: the cache must still do its job. If codegen stopped being
  # skipped, the examples above would pass for the wrong reason — validation
  # would be running because everything was being rebuilt.
  it 'still skips codegen on a cached run' do
    dir = project
    settle(dir)
    views = Dir.glob(File.join(dir, '**', '*GeneratedView.swift'))
    expect(views).not_to be_empty, 'fixture generated nothing, so this asserts nothing'
    before = views.map { |p| [p, File.mtime(p)] }.to_h

    sleep 1.1 # mtime granularity: a rewrite inside the same second is invisible
    log, = sjui(dir)
    expect(log).to include('No files need updating (all cached)'), log

    rewritten = before.reject { |p, t| File.mtime(p) == t }
    expect(rewritten).to be_empty, "codegen ran on a cached build: #{rewritten.keys.inspect}"
  ensure
    FileUtils.rm_rf(dir) if dir
  end
end
