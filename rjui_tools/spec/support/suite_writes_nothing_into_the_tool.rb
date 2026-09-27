# frozen_string_literal: true

require 'set'

# The suite leaves this checkout as it found it. Every process that runs the
# suite from here reads the same tool tree — the shards of a parallel run, a
# second run started beside the first — and the tool reads parts of it on
# every build (the converters under lib/react/converters/extensions and the styles under the working directory). Ported from kjui_tools (same file, same
# semantics), where two specs wrote scaffold files into lib/ while another
# shard was requiring them. Here attribute_validator_spec wrote its style
# fixtures into spec/fixtures/styles under the working directory (the
# checkout) and removed them after; on a checkout without spec/fixtures it
# left that directory behind (jsonui-cli 1.9.0: the styles go in a tmp dir).
#
# What this sees: a path under the tool that was not there when the suite
# started and is there when it ends — a file, or the directory a writer
# made and left. A write cleaned up to the last directory it made is not
# seen; the example that wrote is found by the path named.
module SuiteWritesNothingIntoTheTool
  ROOT = File.expand_path('../..', __dir__)
  # Written by the run itself: the example status file (spec_helper's
  # example_status_persistence_file_path).
  RUN_OUTPUT = %w[spec/.rspec_status].freeze
  # A project's directories under the working directory that a builder run
  # from here makes and leaves empty (kjui has two). None here: a full run
  # of this suite leaves none (measured when ported).
  PROJECT_DIRS = %w[].freeze

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
