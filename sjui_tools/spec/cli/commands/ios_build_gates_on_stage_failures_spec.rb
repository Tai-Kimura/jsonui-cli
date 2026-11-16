# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# End-to-end, through the real orchestrating build — because every cheaper
# arm passed while the defect shipped.
#
# 1.8.43 refused the layout, printed `[error]`, generated no screen, and
# exited 0 with `Text("Placeholder")` on disk. The rule had rspec arms on
# three faces, the refusal had an arm on the build path, and the ledger entry
# was asserted. What no arm covered was the seam between them:
# `StageFailures.record` fills an in-memory array, the file the orchestrator
# reads is written by `report!`, and this face never called it.
#
# ⚠️ Everything here is resolved from THIS checkout. The first cut built its
# project with `jui init`, which vendors `sjui_tools/` from the installed CLI
# (`~/.jsonui-cli`) — so it measured the distributed copy, passed on a machine
# that had one, and failed in CI where none exists. The skeleton below is
# written by hand for that reason: no `jui` on $PATH, no `~/.jsonui-cli`, no
# `jui init`.
RSpec.describe 'the ios build gates on stage failures' do
  REPO = File.expand_path('../../../..', __dir__)

  # `resolve_tool` walks up from the project looking for
  # `sjui_tools/bin/sjui`. A symlink to the checkout satisfies it AND keeps
  # `lib/core/*` working: those are relative symlinks into `shared/core`, and
  # a copied tree leaves them dangling — the validator then loads zero
  # definitions, every rule sits silent, and the build exits 0 for a reason
  # that has nothing to do with the code under test.
  def link_checkout_tool(dir)
    FileUtils.ln_s(File.join(REPO, 'sjui_tools'), File.join(dir, 'sjui_tools'))
  end

  def write_skeleton(dir, layouts)
    name = 'GateProbe'
    File.write(File.join(dir, 'jui.config.json'), JSON.pretty_generate(
      'project_name' => name,
      'spec_directory' => 'docs/screens/json',
      'component_spec_directory' => 'docs/components/json',
      'strings_file' => '',
      'type_map_file' => '.jsonui-type-map.json',
      'platforms' => { 'ios' => { 'root' => '.', 'layoutsDir' => "#{name}/Layouts", 'mode' => 'swiftui' } }
    ))
    # `source_directory` is what sjui reads layouts under; the distribution
    # target above must name the same path or the build reports "No JSON
    # files found" and exits 0.
    File.write(File.join(dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => 'swiftui',
      'project_name' => name,
      'project_file_name' => name,
      'source_directory' => name,
      'layouts_directory' => 'Layouts',
      'resources_directory' => 'Resources',
      'styles_directory' => 'Styles',
      'view_directory' => 'View',
      'data_directory' => 'Data',
      'viewmodel_directory' => 'ViewModel',
      'resource_manager_directory' => 'ResourceManager',
      'string_files' => ["#{name}/Localizable.strings"],
      'use_network' => true
    ))
    File.write(File.join(dir, '.jsonui-type-map.json'), '{}')
    # ProjectFinder needs an `.xcodeproj` (or Package.swift) to resolve paths
    # at all; without one the build fails for an unrelated reason.
    FileUtils.mkdir_p(File.join(dir, "#{name}.xcodeproj"))
    FileUtils.mkdir_p(File.join(dir, name, 'Layouts'))

    src = File.join(dir, 'docs', 'screens', 'layouts')
    FileUtils.mkdir_p(src)
    layouts.each { |n, body| File.write(File.join(src, "#{n}.json"), JSON.generate(body)) }
  end

  def project(layouts)
    dir = Dir.mktmpdir('ios_gate')
    write_skeleton(dir, layouts)
    link_checkout_tool(dir)
    dir
  end

  # The python orchestrator, from the checkout. Never `jui` on $PATH: that is
  # the installed copy, and whether it exists is a property of the machine.
  def build(dir, *args)
    env = { 'PYTHONPATH' => File.join(REPO, 'jui_tools') }
    Open3.capture2e(env, 'python3', '-m', 'jui_cli.cli', 'build',
                    '--platform', 'ios', *args, chdir: dir)
  end

  # `Segment.items` is declared `type: array` with no binding — the shape the
  # docsite face filed.
  let(:refused) { { 'type' => 'Segment', 'id' => 'seg', 'items' => '@{choices}' } }
  let(:healthy) do
    { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent',
      'height' => 'matchParent', 'child' => [] }
  end

  def screens(dir)
    Dir.glob(File.join(dir, '**', '*GeneratedView.swift')).map { |p| File.basename(p) }
  end

  it 'exits non-zero and writes no screen for a refused layout' do
    dir = project('sample' => refused, 'healthy' => healthy)
    log, status = build(dir)

    expect(status.exitstatus).to eq(1), "expected exit 1, got #{status.exitstatus}\n#{log}"
    expect(log).to include('was not generated')
    expect(log).to include('stage(s) incomplete')
    # ABSENT, not a placeholder. The stub used to be written before
    # conversion, so a refusal left `Text("Placeholder")` behind: an error, no
    # generation, and a screen on disk saying Placeholder.
    expect(screens(dir)).to include('HealthyGeneratedView.swift')
    expect(screens(dir)).not_to include('SampleGeneratedView.swift')
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  it 'exits 0 and writes the screen when every layout is healthy' do
    dir = project('healthy' => healthy)
    log, status = build(dir)

    expect(status.exitstatus).to eq(0), log
    expect(screens(dir)).to include('HealthyGeneratedView.swift')
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  it 'exits 0 under --allow-partial, still without the refused screen' do
    dir = project('sample' => refused, 'healthy' => healthy)
    log, status = build(dir, '--allow-partial')

    expect(status.exitstatus).to eq(0), log
    expect(log).to include('--allow-partial')
    expect(screens(dir)).not_to include('SampleGeneratedView.swift')
  ensure
    FileUtils.rm_rf(dir) if dir
  end
end
