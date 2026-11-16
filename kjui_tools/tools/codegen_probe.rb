#!/usr/bin/env ruby
# frozen_string_literal: true

# Converter-driving probe for the codegen differential check (plan 41).
#
# See rjui_tools/tools/codegen_probe.rb for the contract. This is the Compose
# side of it. Unlike the other two trees, kjui dispatches through
# `ComposeBuilder#generate_component` rather than a per-component constructor,
# so that is what the probe drives — the specs exercise the components one
# level below it (`Components::XComponent.generate`), and going through the
# builder additionally covers the container/visibility wrapping that only it
# applies.
#
# `ComposeBuilder.new` reads project configuration and creates its output
# directory, which a probe has no project for. The two lookups are stubbed the
# same way `spec/spec_helper` stubs them, and the output directory is a
# throwaway temp dir. Per-job state (import set, name counters, data
# definitions) is reset exactly where `build` resets it, or an emit would
# depend on what was probed before it.
#
# XML mode is NOT probed: it is frozen (Compose-only since 2026-07-03) and its
# defects are won't-fix, so a differential over it would only produce findings
# nobody will act on.
#
# Usage: ruby tools/codegen_probe.rb <jobs.json> <results.json>

require 'json'
require 'tmpdir'
require 'set'

ROOT = File.expand_path('..', __dir__)
$LOAD_PATH.unshift(File.join(ROOT, 'lib'))

require 'compose/compose_builder'

PROBE_HOME = Dir.mktmpdir('kjui-codegen-probe')

KjuiTools::Core::ConfigManager.define_singleton_method(:load_config) { {} }
KjuiTools::Core::ProjectFinder.define_singleton_method(:get_full_source_path) { PROBE_HOME }
KjuiTools::Core::ProjectFinder.define_singleton_method(:get_package_name) { 'com.example.app' }

BUILDER = KjuiTools::Compose::ComposeBuilder.new

Components = KjuiTools::Compose::Components
Helpers = KjuiTools::Compose::Helpers

def reset_builder_state(node, data)
  BUILDER.instance_variable_set(:@required_imports, Set.new)
  BUILDER.instance_variable_set(:@included_views, Set.new)
  BUILDER.instance_variable_set(:@custom_components, Set.new)
  BUILDER.instance_variable_set(:@responsive_functions, [])
  BUILDER.instance_variable_set(:@responsive_counter, 0)

  Components::TextComponent.reset_counter!
  Components::TextFieldComponent.reset_counter!
  Components::TextViewComponent.reset_counter!
  Components::ButtonComponent.reset_counter!
  Components::ConstraintLayoutComponent.reset_counter!

  # The `data` section travels with the job because it lives on the layout
  # ROOT while the probe converts the target node: without it a Collection's
  # cell bindings resolve against an empty definition table.
  definitions = {}
  BUILDER.send(:extract_data_properties, { 'data' => data, 'type' => 'View' }).each do |prop|
    definitions[prop['name']] = prop
  end
  Helpers::ResourceResolver.data_definitions = definitions
end

def emit(node, data)
  reset_builder_state(node, data)
  code = BUILDER.send(:generate_component, node, 0).to_s

  # Imports are part of the generated file and are the only output some
  # attributes produce, so they belong in the compared text. The set mixes
  # Symbols and Strings, so it is ordered by the rendered form.
  imports = Array(BUILDER.instance_variable_get(:@required_imports)).map(&:to_s).sort
  imports.empty? ? code : ([code] + imports).join("\n")
end

jobs_path, out_path = ARGV
abort 'usage: codegen_probe.rb <jobs.json> <results.json>' if jobs_path.nil? || out_path.nil?

payload = JSON.parse(File.read(jobs_path))
results = payload.fetch('jobs').map do |job|
  begin
    { 'id' => job['id'], 'ok' => true, 'output' => emit(job['node'], job['data'] || []) }
  rescue StandardError, ScriptError => e
    { 'id' => job['id'], 'ok' => false, 'error' => "#{e.class}: #{e.message}" }
  end
end

File.write(out_path, JSON.generate('platform' => 'android', 'results' => results))
