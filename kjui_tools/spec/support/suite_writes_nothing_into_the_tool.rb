# frozen_string_literal: true

require 'set'

# The suite leaves this checkout as it found it. Every process that runs the
# suite from here reads the same tool tree — the shards of a parallel run, a
# second run started beside the first (CI runs one process, so it never
# raced there) — and the tool reads parts of it on
# every build: ComposeBuilder.new requires lib/compose/components/extensions/
# component_mappings.rb when the file is there, and AttributeValidator reads
# extension definitions under the working directory. Two specs wrote there
# and removed their files afterwards (converter_generator_spec: the mapping,
# the converters and their definitions; attribute_validator_spec: a
# TestCustomComponent definition under kjui_tools/kjui_tools/lib); another
# shard building meanwhile raised on the half-there registry, and
# bound_values_reach_the_kotlin_spec counted what an emit raised as the
# node's own. Both left their directories behind, empty.
#
# What this sees: a path under the tool that was not there when the suite
# started and is there when it ends — a file, or the directory a writer
# made and left. A write cleaned up to the last directory it made is not
# seen; the example that wrote is found by the path named.
module SuiteWritesNothingIntoTheTool
  ROOT = File.expand_path('../..', __dir__)
  # Written by the run itself: coverage (SimpleCov) and the example status file.
  RUN_OUTPUT = %w[coverage spec/.rspec_status].freeze
  # A project's directories under the working directory: what a builder or
  # generator makes when a spec runs it from here with no project config —
  # ComposeBuilder.new makes src/main/kotlin/views (FileUtils.mkdir_p), and
  # others make src/main/assets/{Layouts,Styles}, src/main/kotlin/<package>
  # and app/src/main/kotlin/<package>/views. Left empty they hold nothing
  # another process reads; directories only — a file under them is reported.
  PROJECT_DIRS = %w[src app].freeze

  def self.paths
    Dir.glob('**/*', File::FNM_DOTMATCH, base: ROOT).reject do |path|
      File.basename(path).match?(/\A\.\.?\z/) ||
        RUN_OUTPUT.any? { |out| path == out || path.start_with?("#{out}/") } ||
        (PROJECT_DIRS.include?(path.split('/').first) && File.directory?(File.join(ROOT, path)))
    end.to_set
  end

  def self.record
    @before = paths
  end

  def self.added
    @before ? (paths - @before).sort : []
  end
end

RSpec.configure do |config|
  config.before(:suite) { SuiteWritesNothingIntoTheTool.record }
  config.after(:suite) do
    added = SuiteWritesNothingIntoTheTool.added
    unless added.empty?
      raise "the suite wrote into the tool it tests (#{SuiteWritesNothingIntoTheTool::ROOT}); " \
            "a spec writes in a directory of its own: #{added.first(20).join(', ')}"
    end
  end
end
