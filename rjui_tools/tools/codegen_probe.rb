#!/usr/bin/env ruby
# frozen_string_literal: true

# Converter-driving probe for the codegen differential check (plan 41).
#
# Reads a job file ({"jobs": [{"id": ..., "layout": {...}}, ...]}), runs the
# PRODUCTION converter over each layout hash, and writes the emitted source
# text back as JSON. Nothing is rendered and no project is scaffolded: the
# question this answers is "does the converter read this attribute and put it
# in the output", which is a property of the text alone.
#
# The entry point is deliberately the same one `spec/react/converters/*_spec.rb`
# drives — `<X>Converter.new(hash, config).convert` reached through the
# production dispatcher. Inventing a probe-only API would let the converter
# signature drift without anything failing; this way the probe breaks in the
# same commit the specs do.
#
# Usage: ruby tools/codegen_probe.rb <jobs.json> <results.json>

require 'json'

ROOT = File.expand_path('..', __dir__)
$LOAD_PATH.unshift(File.join(ROOT, 'lib'))

require 'react/converters/base_converter'
# get_converter_class resolves every type in one table, so every converter file
# has to be loaded before the first lookup (the table references the constants).
Dir[File.join(ROOT, 'lib', 'react', 'converters', '*.rb')].sort.each { |f| require f }

# The conformance web host builds with Tailwind, so this is the production
# configuration for the fixtures this probe mirrors.
CONFIG = { 'use_tailwind' => true }.freeze

def converter_class_for(type)
  dispatcher = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, CONFIG)
  dispatcher.send(:get_converter_class, type)
end

def emit(node)
  type = node['type'] || 'View'
  klass = converter_class_for(type)
  raise "no converter registered for type #{type.inspect}" if klass.nil?

  klass.new(node, CONFIG.dup).convert.to_s
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

File.write(out_path, JSON.generate('platform' => 'web', 'results' => results))
