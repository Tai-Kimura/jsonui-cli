# frozen_string_literal: true

# Every spec that asserts emitted Kotlin must hand it to a compiler — or say,
# by name, why it does not.
#
# WHY, AND WHY THIS FACE ESPECIALLY
#
# `dev-guide/release/compile-emitted-kotlin.sh` states it outright: the Kotlin
# emitter is the only one of the three whose output no check on this machine
# ever compiled. That script is a release procedure and covers only the
# branch-test runtime, so the data model — and every component emitter — had
# nothing behind it at all.
#
# What that cost is measured. `map_to_kotlin_type('Object')` returned
# `"Object"` and `format_default_value` returned a Ruby Hash, so the emitted
# line was
#
#     var profile: Object = {"name"=>"Grace"}
#
# Neither half is Kotlin. Every unit example was green, because they asserted
# the emitted TEXT. The same defect existed on iOS and was found there only
# when a conformance fixture reached the branch and failed a build; Android
# has no equivalent gate, so it was found by looking.
#
# THE RATCHET: a new spec asserting emitted Kotlin must compile it — it cannot
# be added here. An entry whose file now compiles, or no longer exists, fails
# as stale, so the list cannot quietly become a permanent exemption.
#
# The compiler comes from the Gradle cache (spec/support/kotlin_compiler.rb)
# and the arm SKIPS visibly where that cache is absent, which is why adding
# one is cheap on a maintainer's machine and harmless on a bare CI box.
#
# WHAT CONVERTING ONE OF THESE COSTS, measured rather than guessed:
#
#   - Component emitters produce `@Composable` code, and
#     `androidx.compose.runtime` is NOT in the Gradle cache here. But the
#     Compose compiler PLUGIN is not required to type-check it: a
#     hand-declared `annotation class Composable` plus stubs for the
#     composables the fragment calls compiles under plain kotlinc (verified).
#     So conversion is per-spec stub work, exactly as on the Swift side —
#     not a toolchain blocker.
#
#   - ⚠️ LIMIT OF THE CHECK: without the real plugin this verifies TYPES
#     against stubs. Compose-specific compiler rules — @Composable call
#     context, restartability, stability inference — are not checked. An arm
#     here says "this is well-typed Kotlin", not "this is valid Compose".
#     Anyone quoting a green from it should quote that sentence with it.
#
#   - Each arm costs ~27s (JVM start). 19 arms would add ~8 minutes to the
#     suite, so per-file arms should stay few and broad rather than many and
#     narrow.
RSpec.describe 'emitted Kotlin reaches a compiler' do
  EMIT_MARKERS_KT = ['expect(code)', 'expect(kotlin', 'expect(out'].freeze
  COMPILE_MARKER_KT = 'compile_as_kotlin'

  # A fragment needs a stub universe — the types it references — before a
  # compiler can read it, and that is per-shape work. Entries earn a more
  # specific reason as they are reviewed; none may be added.
  #
  # ⚠️ The marker list over-captures: a few of these assert resource or CLI
  # output rather than Kotlin. Deliberate — the predicate is cheap and
  # reproducible, and a file that turns out not to emit Kotlin leaves this
  # list by getting a truthful reason, not by vanishing from the population.
  UNCONVERTED = 'Kotlin fragment; stub universe not built yet'

  ALLOWLIST_KT = {
    'cli/commands/init_spec.rb' => UNCONVERTED,
    'compose/collection_cell_classes_spec.rb' => UNCONVERTED,
    'compose/components/checkbox_component_spec.rb' => UNCONVERTED,
    'compose/components/collection_cells_are_addressable_spec.rb' => UNCONVERTED,
    'compose/components/collection_component_spec.rb' => UNCONVERTED,
    'compose/components/container_component_spec.rb' => UNCONVERTED,
    'compose/components/flow_collection_scrolls_spec.rb' => UNCONVERTED,
    'compose/components/pair_scan_closure_spec.rb' => UNCONVERTED,
    'compose/components/radio_component_spec.rb' => UNCONVERTED,
    'compose/components/segment_component_spec.rb' => UNCONVERTED,
    'compose/components/switch_component_spec.rb' => UNCONVERTED,
    'compose/components/textfield_component_spec.rb' => UNCONVERTED,
    'compose/components/web_component_spec.rb' => UNCONVERTED,
    'compose/compose_builder_spec.rb' => UNCONVERTED,
    'compose/helpers/content_scale_helper_spec.rb' => UNCONVERTED,
    'compose/helpers/effect_style_helper_spec.rb' => UNCONVERTED,
    'compose/helpers/modifier_builder_spec.rb' => UNCONVERTED,
    'compose/helpers/tint_helper_spec.rb' => UNCONVERTED,
    'core/resources/color_manager_spec.rb' => UNCONVERTED
  }.freeze

  let(:root) { File.expand_path(__dir__) }

  def emit_specs(root)
    Dir.glob(File.join(root, '**', '*_spec.rb')).sort.filter_map do |path|
      body = File.read(path)
      next unless EMIT_MARKERS_KT.any? { |m| body.include?(m) }

      [path.sub("#{root}/", ''), body]
    end
  end

  it 'has no spec asserting emitted Kotlin that neither compiles nor is listed' do
    offenders = emit_specs(root).reject do |rel, body|
      body.include?(COMPILE_MARKER_KT) || ALLOWLIST_KT.key?(rel)
    end.map(&:first)

    expect(offenders).to be_empty,
                         "these assert emitted Kotlin with no compile arm. Add one " \
                         "(see spec/support/kotlin_compiler.rb):\n#{offenders.join("\n")}"
  end

  it 'has no allowlist entry whose file is gone' do
    stale = ALLOWLIST_KT.keys.reject { |rel| File.file?(File.join(root, rel)) }
    expect(stale).to be_empty, "delete these allowlist entries:\n#{stale.join("\n")}"
  end

  it 'has no allowlist entry that already compiles' do
    converted = ALLOWLIST_KT.keys.select do |rel|
      path = File.join(root, rel)
      File.file?(path) && File.read(path).include?(COMPILE_MARKER_KT)
    end
    expect(converted).to be_empty,
                         "these now compile — remove them from ALLOWLIST_KT:\n#{converted.join("\n")}"
  end

  it 'never grows' do
    expect(ALLOWLIST_KT.size).to be <= 19
  end
end
