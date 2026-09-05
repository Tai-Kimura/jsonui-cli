# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# The Compose build cache, and the gates that must survive it.
#
# `save_cache` rebuilt the layouts path as `<source_path>/assets/Layouts`
# while build.rb resolves `<source_path>/<source_directory>/…`. With a stock
# `source_directory` of `app/src/main` those are different directories,
# `File.exist?` was false for every layout, and `last_updated.json` stayed
# `{}` — measured on a probe project: 12 consecutive builds, "all cached" 0
# times. The cache was inert, which also meant the validation-skip defect on
# this face could not be measured at all.
#
# Everything resolves from this checkout: no installed CLI, `kjui_tools`
# symlinked so its relative `lib/core/*` links still point at `shared/core`.
RSpec.describe 'the Compose build cache' do
  REPO_ROOT = File.expand_path('../../..', __dir__)

  def project
    dir = Dir.mktmpdir('kjui_cache')
    File.write(File.join(dir, 'jui.config.json'), JSON.pretty_generate(
      'project_name' => 'KProbe', 'spec_directory' => 'docs/screens/json',
      'component_spec_directory' => 'docs/components/json', 'strings_file' => '',
      'type_map_file' => '.jsonui-type-map.json',
      'platforms' => { 'android' => { 'root' => '.', 'layoutsDir' => 'app/src/main/assets/Layouts', 'mode' => 'compose' } }
    ))
    File.write(File.join(dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => 'KProbe',
      'source_directory' => 'app/src/main', 'layouts_directory' => 'assets/Layouts',
      'styles_directory' => 'assets/Styles',
      'data_directory' => 'kotlin/com/example/app/data',
      'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'view_directory' => 'kotlin/com/example/app/views',
      'extension_directory' => 'kotlin/com/example/app/extensions',
      'adapter_directory' => 'kotlin/com/example/app/adapters',
      'resource_manager_directory' => 'app/src/main/kotlin/com/kotlinjsonui/generated',
      'package_name' => 'com.example.app',
      'string_files' => ['res/values/strings.xml'], 'use_network' => true
    ))
    File.write(File.join(dir, '.jsonui-type-map.json'), '{}')
    layouts = File.join(dir, 'app', 'src', 'main', 'assets', 'Layouts')
    styles = File.join(dir, 'app', 'src', 'main', 'assets', 'Styles')
    FileUtils.mkdir_p(layouts)
    FileUtils.mkdir_p(styles)
    File.write(File.join(styles, 'base.json'), JSON.generate('background' => '#EEEEEE'))
    # Only `styled` depends on the style, so touching it must not rebuild the
    # other two — a cache that invalidates everything is as useless as one
    # that invalidates nothing.
    File.write(File.join(layouts, 'styled.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent',
      'height' => 'matchParent', 'style' => 'base', 'child' => []
    ))
    File.write(File.join(layouts, 'sample.json'),
               JSON.generate('type' => 'Segment', 'id' => 'seg', 'items' => '@{choices}'))
    File.write(File.join(layouts, 'healthy.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent',
      'height' => 'matchParent', 'child' => []
    ))
    FileUtils.ln_s(File.join(REPO_ROOT, 'kjui_tools'), File.join(dir, 'kjui_tools'))
    dir
  end

  def kjui(dir, *args)
    Open3.capture2e('ruby', File.join(dir, 'kjui_tools', 'bin', 'kjui'), 'build', *args, chdir: dir)
  end

  def cache(dir)
    path = File.join(dir, '.kjui_cache', 'last_updated.json')
    File.exist?(path) ? JSON.parse(File.read(path)) : {}
  end

  def views(dir)
    Dir.glob(File.join(dir, '**', '*GeneratedView.kt'))
  end

  it 'records every layout on the first build' do
    dir = project
    kjui(dir)

    expect(cache(dir).keys.sort).to eq(%w[healthy sample styled])
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  it 'skips codegen on an unchanged second build' do
    dir = project
    kjui(dir)
    before = views(dir).map { |p| [p, File.mtime(p)] }.to_h
    expect(before).not_to be_empty, 'fixture generated nothing, so this asserts nothing'

    sleep 1.1 # stamps are second-granular; a same-second rebuild is invisible
    log, = kjui(dir)

    expect(log).to match(/all cached/), log
    rewritten = before.reject { |p, t| File.mtime(p) == t }
    expect(rewritten).to be_empty, "codegen ran on a cached build: #{rewritten.keys.inspect}"
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  it 'rebuilds only the layout that uses a touched style' do
    dir = project
    kjui(dir)
    before = views(dir).map { |p| [p, File.mtime(p)] }.to_h

    sleep 1.1
    FileUtils.touch(File.join(dir, 'app', 'src', 'main', 'assets', 'Styles', 'base.json'))
    kjui(dir)

    rewritten = before.reject { |p, t| File.mtime(p) == t }.keys.map { |p| File.basename(p) }
    expect(rewritten).to include('StyledGeneratedView.kt')
    expect(rewritten).not_to include('HealthyGeneratedView.kt')
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  # Measurable on this face only now that the cache works at all: the
  # all-cached run must still validate and still name a refused layout.
  it 'still validates and still records a refused layout when everything is cached' do
    dir = project
    kjui(dir)
    sleep 1.1

    log, status = kjui(dir, '--strict')

    expect(log).to match(/all cached/), log
    expect(log).to match(/Binding variable/), log
    expect(log).to include('was not generated'), log
    expect(log).to include('did not complete'), log
    expect(status.exitstatus).to eq(1), "cached --strict must fail like the first run\n#{log}"
  ensure
    FileUtils.rm_rf(dir) if dir
  end
end
