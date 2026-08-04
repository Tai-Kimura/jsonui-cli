# frozen_string_literal: true

require_relative '../spec_helper'

# rjui runs under whatever `ruby` the consumer's shell resolves.
#
# `bin/rjui` is a bare `#!/usr/bin/env ruby` with no bundler and no gemspec, so
# nothing in the distribution pins an interpreter. `jui sync_tool` does copy this
# tool's `.ruby-version` (3.2.2) to the platform root, but that file only means
# anything to rbenv/asdf — a consumer without a Ruby version manager gets the
# system Ruby, which on macOS is still 2.6.
#
# The rule and its cost were already written down, in
# `kjui_tools/lib/compose/helpers/section_extractor.rb`: a `filter_map` under 2.6
# raised NoMethodError, the per-file rescue swallowed it as "Failed to process",
# and 252 layouts silently kept their PREVIOUS generated file. rjui has no such
# per-file rescue on the generation path, so the same call aborts the build
# loudly rather than quietly — louder, but still a broken build for that
# consumer.
#
# The warning existed and nobody re-read it. This is that warning in a form that
# cannot be un-read (lane C's finding, plan 49).
RSpec.describe 'Ruby baseline for the consumer interpreter' do
  lib_root = File.expand_path('../../lib', __dir__)

  # Method => the Ruby version that introduced it, and the 2.6 way to write it.
  # Only methods NEWER than the 2.6 floor belong here.
  #
  # Deliberately absent: `then` / `yield_self` (2.6 / 2.5). They read like modern
  # idioms but are on the floor — `blur_converter` uses `then` and is fine.
  TOO_NEW = {
    'filter_map' => ['2.7', 'map { … }.compact'],
    'tally' => ['2.7', 'group_by { … }.transform_values(&:size)'],
    'except' => ['3.0', 'reject { |k, _| … }'],
    'intersect?' => ['3.1', '!(a & b).empty?']
  }.freeze

  sources = Dir[File.join(lib_root, '**', '*.rb')].sort

  TOO_NEW.each do |method, (since, replacement)|
    it "does not call ##{method} (Ruby #{since}+, above the 2.6 floor)" do
      call = /\.#{Regexp.escape(method)}\b/

      offenders = sources.flat_map do |path|
        File.readlines(path).each_with_index.map do |line, index|
          next if line.lstrip.start_with?('#')
          next unless line.match?(call)

          "#{path.sub("#{lib_root}/", '')}:#{index + 1}"
        end.compact
      end

      expect(offenders).to be_empty, lambda {
        "`#{method}` is Ruby #{since}+ and rjui may run on the consumer's 2.6:\n  " +
          offenders.join("\n  ") + "\n\nWrite it as `#{replacement}` instead."
      }
    end
  end
end
