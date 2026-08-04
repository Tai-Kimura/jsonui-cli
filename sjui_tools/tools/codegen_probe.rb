#!/usr/bin/env ruby
# frozen_string_literal: true

# Converter-driving probe for the codegen differential check (plan 41).
#
# See rjui_tools/tools/codegen_probe.rb for the contract. This is the SwiftUI
# side of it: `ConverterFactory#create_converter(hash, ...).convert`, the same
# layer `spec/swiftui/views/*_spec.rb` drives, with the same
# `validation_enabled = false` the specs set (attribute validation has its own
# suite; leaving it on would make the probe measure the validator).
#
# UIKit is NOT probed, and cannot be: the UIKit path applies attributes in the
# SwiftJsonUI Swift runtime straight off the layout JSON, so there is no Ruby
# codegen output to compare. That is the same blind spot
# `conformance/coverage.py` records for the `uikit` mode tag, and the Python
# side scopes uikit-only attributes out with a reason rather than reporting
# them as failures.
#
# Usage: ruby tools/codegen_probe.rb <jobs.json> <results.json>

require 'json'

ROOT = File.expand_path('..', __dir__)
$LOAD_PATH.unshift(File.join(ROOT, 'lib'))

require 'swiftui/converter_factory'

SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false

def emit(node)
  # A fresh factory per job: the factory owns a ViewRegistry and responsive
  # counters, and carrying them between jobs would make an emit depend on what
  # was probed before it — the comparison would then measure ordering.
  factory = SjuiTools::SwiftUI::ConverterFactory.new
  converter = factory.create_converter(node, 0, nil, factory, nil)
  raise "no converter for type #{node['type'].inspect}" if converter.nil?

  code = converter.convert.to_s

  # Part of a converter's emission leaves through `state_variables` rather
  # than the returned snippet — `json_to_swiftui_converter` concatenates them
  # into the generated file. `ProgressView(value: progressValue)` is the same
  # text for every declared progress; the declared value is in the `@State`
  # line. Comparing the snippet alone would report that as "the converter
  # emits a constant" when the value does travel, just not here.
  state = converter.respond_to?(:state_variables) ? Array(converter.state_variables) : []
  state.empty? ? code : ([code] + state.sort).join("\n")
end

jobs_path, out_path = ARGV
abort 'usage: codegen_probe.rb <jobs.json> <results.json>' if jobs_path.nil? || out_path.nil?

payload = JSON.parse(File.read(jobs_path))
results = payload.fetch('jobs').map do |job|
  begin
    { 'id' => job['id'], 'ok' => true, 'output' => emit(job['node']) }
  rescue StandardError, ScriptError => e
    { 'id' => job['id'], 'ok' => false, 'error' => "#{e.class}: #{e.message}" }
  end
end

File.write(out_path, JSON.generate('platform' => 'ios', 'results' => results))
