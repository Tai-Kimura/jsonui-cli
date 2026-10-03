# frozen_string_literal: true

require 'tmpdir'

# A spec file leaves the process as it found it. Around every top-level
# example group (one spec file's describe) this takes the process-wide state
# the tool's code keeps: the working directory, ENV, and every instance and
# class variable of the tool's own modules and classes. After the group it
# names what the group changed and fails there, in the spec that did it.
#
# Why (found in sjui_tools; this is the same guard): a spec that leaves such
# state behind makes whichever spec runs next pass or fail by the seed.
# sjui's build_spec left the include expander's layouts
# root at its own tmp Layouts, and json_to_swiftui_converter_spec,
# state_names_are_unique_spec and the layouts-root spec failed after it on
# some seeds and on some shard layouts ("Include file not found:
# <build_test tmp>/Layouts/part.json"), while each passed alone. An
# order-dependent failure is reported in the victim; this reports it in the
# leaker, every run, whatever the order.
#
# What is not a leak: a cache a module fills on first use from the tool's
# own files (the attribute definitions, the synonym table) — the same value
# whichever spec fills it. Those are listed in CACHES with why; a new one is
# added there, with its reason, never to make a real leak pass. A value that
# names a temporary directory is a leak even in a listed cache. A variable
# that is nil is the same as one never set (what an attr_accessor or `||=`
# reads). A module first loaded during the group (a `require` inside an
# example) sets its load-time defaults then; of its variables only a value
# naming a temporary directory is a leak. What spec_helper resets itself
# (the log level, the stage ledger) is listed in MANAGED.
#
# A spec that has to change such state keeps it and puts it back:
#   before(:context) { @kept = ProcessStateGuard.keep(SomeModule) }
#   after(:context)  { ProcessStateGuard.put_back(@kept) }
module ProcessStateGuard
  NAMESPACES = %w[RjuiTools JsonUIShared JsonUI].freeze

  # "Module.@ivar" => why it may be filled by whichever spec runs first.
  CACHES = {
    'JsonUIShared::ComponentAliases.@tables' => 'alias table read from lib/core/attribute_definitions.json, keyed by its path',
    'JsonUIShared::LayoutValidator.@definitions' => 'lib/core/attribute_definitions.json',
    'JsonUIShared::EnumSpelling.@definitions' => 'lib/core/attribute_definitions.json',
    'JsonUIShared::BindFold.@definitions' => 'lib/core/attribute_definitions.json',
    'JsonUIShared::BindFold.@synonyms' => 'lib/core/type_synonyms.json',
    'JsonUIShared::TypeSynonyms.@entries' => 'lib/core/type_synonyms.json, keyed by its path',
    'JsonUIShared::TypeSynonyms.@app_types' => "the tool's own extension converters (lib/react/converters/extensions)",
    'RjuiTools::Core::TypeConverter.@type_mapping' => "lib's type_mapping.json",
    'RjuiTools::React::Helpers::FontSpecHelper.@weight_mapping' => 'shared/core/font_weight_mapping.json beside the tool',
    'RjuiTools::React::Converters::ConverterTable.@table' => "the tool's converter table (lib/react/converters)"
  }.freeze

  # The generated attribute tables (lib/core/generated/attributes): each
  # module memoizes its rows and alias map from its own constants.
  CACHE_PATTERNS = [/\AJsonUI::Generated::\w+Attributes\.@(rows|alias_map)\z/].freeze

  # "Module.@ivar" => where spec_helper resets it. Whatever a spec leaves
  # there, the next one does not see it.
  MANAGED = {
    'JsonUI::StageFailures.@entries' => 'the stage ledger, emptied at the start of every spec file',
    'JsonUI::StageFailures.@written' => 'the stage ledger, emptied at the start of every spec file',
    'JsonUI::StageFailures.@blocked_layouts' => 'the stage ledger, emptied at the start of every spec file'
  }.freeze

  module_function

  def cache?(key)
    CACHES.key?(key) || CACHE_PATTERNS.any? { |re| key.match?(re) }
  end

  def modules
    ObjectSpace.each_object(Module).select do |m|
      name = begin
        m.name
      rescue StandardError
        nil
      end
      name && NAMESPACES.any? { |ns| name == ns || name.start_with?("#{ns}::") }
    end
  end

  def fingerprint(value)
    [value.class, value.hash]
  rescue StandardError
    [value.class, value.object_id]
  end

  # A copy to show later: the variable may be mutated in place.
  def copy(value)
    value.is_a?(Hash) || value.is_a?(Array) || value.is_a?(String) ? value.dup : value
  end

  # Every instance and class variable of `mods`, to put back with put_back.
  def keep(*mods)
    mods.map do |m|
      ivars = m.instance_variables.to_h { |iv| [iv, copy(m.instance_variable_get(iv))] }
      cvars = m.respond_to?(:class_variables) ? m.class_variables(false).to_h { |cv| [cv, copy(m.class_variable_get(cv))] } : {}
      [m, ivars, cvars]
    end
  end

  def put_back(kept)
    kept.each do |m, ivars, cvars|
      (m.instance_variables - ivars.keys).each { |iv| m.remove_instance_variable(iv) }
      ivars.each { |iv, v| m.instance_variable_set(iv, v) }
      cvars.each { |cv, v| m.class_variable_set(cv, v) }
    end
  end

  def snapshot
    state = { 'Dir.pwd' => [String, Dir.pwd], 'ENV' => [Hash, ENV.to_h.hash] }
    values = {}
    loaded = modules
    values[:modules] = loaded.map(&:name)
    loaded.each do |m|
      m.instance_variables.each do |iv|
        key = "#{m.name}.#{iv}"
        value = m.instance_variable_get(iv)
        next if value.nil?

        values[key] = copy(value)
        state[key] = fingerprint(value)
      end
      next unless m.respond_to?(:class_variables)

      m.class_variables(false).each do |cv|
        key = "#{m.name}.#{cv}"
        value = m.class_variable_get(cv)
        next if value.nil?

        values[key] = copy(value)
        state[key] = fingerprint(value)
      end
    end
    [state, values]
  end

  def tmp_path?(value)
    text = begin
      value.inspect
    rescue StandardError
      ''
    end
    [Dir.tmpdir, File.realpath(Dir.tmpdir)].uniq.any? { |t| text.include?(t) }
  end

  def show(value)
    text = begin
      value.inspect
    rescue StandardError => e
      "<#{e.class}>"
    end
    text.length > 160 ? "#{text[0, 150]}…" : text
  end

  # What the group changed: [key, before, after] for each.
  def changes(before, after)
    (before_state, before_values) = before
    (after_state, after_values) = after
    loaded_before = before_values[:modules]
    (before_state.keys | after_state.keys).sort.map do |key|
      next if before_state[key] == after_state[key]

      next if MANAGED.key?(key)

      owner = key.split('.').first
      next if key.include?('.') && !loaded_before.include?(owner) && !tmp_path?(after_values[key])

      is_new = !before_state.key?(key)
      # A listed cache may be filled, refilled or emptied (it reloads from
      # the same files) — unless it now names a temporary directory.
      next if cache?(key) && !(after_state.key?(key) && tmp_path?(after_values[key]))

      shown_before = is_new ? '(unset)' : show(before_values.fetch(key, before_state[key]))
      shown_after = after_state.key?(key) ? show(after_values.fetch(key, after_state[key])) : '(unset)'
      [key, shown_before, shown_after]
    end.compact
  end
end

RSpec.configure do |config|
  config.before(:context) do
    @process_state_before = ProcessStateGuard.snapshot if self.class.superclass == RSpec::Core::ExampleGroup
  end

  config.after(:context) do
    next unless @process_state_before

    found = ProcessStateGuard.changes(@process_state_before, ProcessStateGuard.snapshot)
    next if found.empty?

    lines = found.map { |key, was, now| "  #{key}: #{was} -> #{now}" }
    message = "#{self.class.metadata[:file_path]} left process-wide state changed (restore it in the spec " \
              "that changes it; a cache filled from the tool's own files goes in ProcessStateGuard::CACHES):\n" \
              "#{lines.join("\n")}"
    if (report = ENV['PROCESS_STATE_GUARD_REPORT'])
      File.open(report, 'a') { |f| f.puts(message) }
    else
      raise message
    end
  end
end
