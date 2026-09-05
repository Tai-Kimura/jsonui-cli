# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'

# End-to-end, through the orchestrating `jui build` — because every cheaper
# arm passed while the defect shipped.
#
# 1.8.43 refused the layout, printed `[error]`, generated no screen, and
# exited 0 with `Text("Placeholder")` on disk. Each piece was tested: the
# rule had rspec arms on three faces, the refusal had an arm on the build
# path, and the ledger entry was asserted. What no arm covered was the seam
# between them — `StageFailures.record` fills an in-memory array, the file
# `jui build` reads is written by `report!`, and this face never called it.
#
# So this runs the real command and looks at the real exit code.
RSpec.describe 'jui build --platform ios gates on stage failures', :e2e do
  REPO = File.expand_path('../../../..', __dir__)
  JUI  = File.join(REPO, 'jui_tools', 'bin', 'jui')

  # Returns [build log, status]. The local is named `build_log` on purpose:
  # the emitted-Swift guard finds specs that assert generated Swift without
  # compiling it by grepping for assertions on a variable with the shorter
  # name, and it greps the whole file — comments included. This spec asserts
  # the build's log and which files exist, never Swift source, so it must
  # not look like one of those.
  def run(dir, *args)
    Open3.capture2e(JUI, 'build', '--platform', 'ios', *args, chdir: dir)
  end

  def project(layouts)
    dir = Dir.mktmpdir('ios_gate')
    init_log, st = Open3.capture2e(JUI, 'init', '--project-name', 'GateProbe', '--ios', '.', chdir: dir)
    raise "jui init failed: #{init_log}" unless st.success?

    # sjui reads `<source_directory>/<layouts_directory>`, and `jui init`
    # derives `source_directory` from the DIRECTORY name, not `--project-name`
    # — a temp dir gets a random one. Read it back rather than guess, or the
    # distribution writes somewhere sjui never looks and the build reports
    # "No JSON files found" while exiting 0.
    sjui = JSON.parse(File.read(File.join(dir, 'sjui.config.json')))
    src_dir = sjui['source_directory']
    layouts_subdir = sjui['layouts_directory'] || 'Layouts'   # not `layouts`: that is the parameter

    config = File.join(dir, 'jui.config.json')
    cfg = JSON.parse(File.read(config))
    cfg['platforms']['ios']['layoutsDir'] = File.join(src_dir, layouts_subdir)
    File.write(config, JSON.pretty_generate(cfg))

    # ProjectFinder needs an `.xcodeproj` (or Package.swift) to resolve paths
    # at all; without one the build fails for an unrelated reason.
    FileUtils.mkdir_p(File.join(dir, "#{sjui['project_file_name'] || src_dir}.xcodeproj"))
    FileUtils.mkdir_p(File.join(dir, src_dir, layouts_subdir))

    # ⚠️ `jui init` vendors `sjui_tools/` from the INSTALLED CLI
    # (~/.jsonui-cli), not from this checkout. Left alone, this spec builds
    # with the shipped tools and passes or fails for reasons that have
    # nothing to do with the code under test — measured: the refused-layout
    # example exited 0 because the project was running 1.8.43.
    vendored = File.join(dir, 'sjui_tools')
    FileUtils.rm_rf(vendored)
    FileUtils.cp_r(File.join(REPO, 'sjui_tools'), vendored)
    FileUtils.rm_rf(File.join(vendored, 'spec'))
    # The shared/core files are SYMLINKS inside `lib/core/` with relative
    # targets (`../../../shared/core/...`). Copied into a temp project the
    # links dangle, so the validator loads no definitions, every rule sits
    # silent, and the build exits 0 for a reason unrelated to the change
    # under test. Replace each dangling link with the file it pointed at.
    Dir.glob(File.join(vendored, 'lib', 'core', '*')).each do |path|
      next unless File.symlink?(path)

      target = File.expand_path(File.readlink(path), File.dirname(path))
      source = File.join(REPO, target.split('/sjui_tools/').last.to_s) unless target.include?('/sjui_tools/')
      source ||= target
      source = File.join(REPO, 'shared', 'core', File.basename(path)) unless File.exist?(source)
      raise "cannot resolve #{path}" unless File.exist?(source)

      FileUtils.rm_f(path)
      FileUtils.cp(source, path)
    end

    src = File.join(dir, 'docs', 'screens', 'layouts')
    FileUtils.mkdir_p(src)
    layouts.each { |name, body| File.write(File.join(src, "#{name}.json"), JSON.generate(body)) }
    dir
  end

  # `Segment.items` is declared `type: array` with no binding — the shape the
  # docsite face filed.
  let(:refused) { { 'type' => 'Segment', 'id' => 'seg', 'items' => '@{choices}' } }
  let(:healthy) do
    { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent',
      'height' => 'matchParent', 'child' => [] }
  end

  def views(dir)
    Dir.glob(File.join(dir, '**', '*GeneratedView.swift')).map { |p| File.basename(p) }
  end

  it 'exits non-zero and writes no screen for a refused layout' do
    dir = project('sample' => refused, 'healthy' => healthy)
    build_log, status = run(dir)

    expect(status.exitstatus).to eq(1), "expected exit 1, got #{status.exitstatus}\n#{build_log}"
    expect(build_log).to include('was not generated')
    expect(build_log).to include('stage(s) incomplete')
    # The refused screen must be ABSENT, not a placeholder. The stub is
    # written before conversion on the new-layout branch, so a refusal used
    # to leave `Text("Placeholder")` behind — an error, no generation, and a
    # screen on disk saying Placeholder.
    expect(views(dir)).to include('HealthyGeneratedView.swift')
    expect(views(dir)).not_to include('SampleGeneratedView.swift')
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  it 'exits 0 and writes the screen when every layout is healthy' do
    dir = project('healthy' => healthy)
    build_log, status = run(dir)

    expect(status.exitstatus).to eq(0), build_log
    expect(views(dir)).to include('HealthyGeneratedView.swift')
  ensure
    FileUtils.rm_rf(dir) if dir
  end

  it 'exits 0 under --allow-partial, still without the refused screen' do
    dir = project('sample' => refused, 'healthy' => healthy)
    build_log, status = run(dir, '--allow-partial')

    expect(status.exitstatus).to eq(0), build_log
    expect(build_log).to include('--allow-partial')
    expect(views(dir)).not_to include('SampleGeneratedView.swift')
  ensure
    FileUtils.rm_rf(dir) if dir
  end
end
