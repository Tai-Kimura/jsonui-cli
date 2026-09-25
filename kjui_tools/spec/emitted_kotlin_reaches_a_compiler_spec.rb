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
  # WHICH SPECS ARE IN: what a spec loads and describes, not how it spells
  # its assertions (kjui-compiler-ratchet-misses-component-specs-that-assert-
  # through-expect-result, 2026-09-25). The population used to be the specs
  # whose text held `expect(code)`, `expect(kotlin` or `expect(out` — and
  # component specs assert through `expect(result…)`, through a `let
  # (:described)`, through a helper like `type_for`. 21 component specs sat
  # outside, tabview_component_spec.rb among them (38 assertions, none on a
  # badge, no compile) — and the TabView badge that emitted uncompilable
  # Kotlin was there. A spelling added to the list leaks again at the next
  # spelling; a dependency does not.
  #
  # A spec is in when it
  #   (a) requires a Kotlin-emitting file of lib — derived from lib below,
  #       so a new component is in the day it exists;
  #   (b) describes a constant in a Kotlin-emitting namespace; or
  #   (c) holds one of the old spellings, so no spec that was in leaves.
  EMIT_MARKERS_KT = ['expect(code)', 'expect(kotlin', 'expect(out'].freeze
  COMPILE_MARKER_KT = 'compile_as_kotlin'
  LIB_KT = File.expand_path('../lib', __dir__)
  EMITTING_LIB_KT = (Dir.glob(File.join(LIB_KT, 'compose', '{components,generators,helpers}', '*.rb')) +
                     %w[compose/compose_builder.rb compose/data_model_updater.rb].map { |f| File.join(LIB_KT, f) })
                    .map { |f| f.sub("#{LIB_KT}/", '').sub(/\.rb\z/, '') }.freeze
  EMITTING_NAMESPACES_KT = %w[
    KjuiTools::Compose::Components:: KjuiTools::Compose::Generators:: KjuiTools::Compose::Helpers::
    KjuiTools::Compose::ComposeBuilder KjuiTools::Compose::DataModelUpdater
  ].freeze

  def self.emits_kotlin?(body)
    requires = body.scan(/^\s*require(?:_relative)?\s+['"]([^'"]+)['"]/).flatten
    loads = requires.any? { |r| EMITTING_LIB_KT.any? { |lib| r == lib || r.end_with?("/#{lib}") } }
    target = body[/^RSpec\.describe\s+([\w:]+)/, 1]
    describes = !target.nil? && EMITTING_NAMESPACES_KT.any? { |ns| target.start_with?(ns) }
    loads || describes || EMIT_MARKERS_KT.any? { |m| body.include?(m) }
  end

  # A fragment needs a stub universe — the types it references — before a
  # compiler can read it, and that is per-shape work. Entries earn a more
  # specific reason as they are reviewed; none may be added.
  #
  # Each reason starts with the order to convert in (p1 first: emitters that
  # assemble braces as strings or rewrite code with gsub, where today's two
  # uncompilable emits were; p4: helpers that return one expression). `—`:
  # not code — nothing to compile.
  #
  # ⚠️ The marker list over-captures: a few of these assert resource or CLI
  # output rather than Kotlin. Deliberate — the predicate is cheap and
  # reproducible, and a file that turns out not to emit Kotlin leaves this
  # list by getting a truthful reason, not by vanishing from the population.
  UNCONVERTED = 'Kotlin fragment; stub universe not built yet'
  FILE_EFFECTS = '— asserts which files a build writes, deletes or leaves byte-identical, not what the Kotlin in them says'

  ALLOWLIST_KT = {
    'cli/commands/build_prunes_deleted_layout_outputs_spec.rb' => FILE_EFFECTS,
    'cli/commands/init_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/blocking_layout_not_generated_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/collection_cell_classes_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/components/blurview_component_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/box_gravity_unnamed_axis_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/button_image_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/checkbox_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/circleimage_component_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/collection_cells_are_addressable_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/components/collection_component_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/components/constraintlayout_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/container_component_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/components/embed_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/flow_collection_scrolls_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/components/gradientview_component_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/handler_name_spelling_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/iconlabel_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/image_component_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/indicator_component_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/networkimage_component_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/pair_scan_closure_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/progress_component_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/radio_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/segment_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/slider_component_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/switch_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/table_component_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/components/text_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/textfield_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/textview_component_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/components/toggle_component_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/components/web_component_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/compose_builder_screen_marker_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/compose_builder_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/compose_builder_variant_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/data_model_updater_spec.rb' => "p1 — #{UNCONVERTED}",
    'compose/generators/cell_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/generators/converter_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/generators/dynamic_component_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/generators/kotlin_component_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/generators/scaffold_files_honor_overwrite_options_spec.rb' => FILE_EFFECTS,
    'compose/generators/scaffolds_carry_the_user_owned_header_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/generators/view_adapter_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/generators/view_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/helpers/binding_expression_spec.rb' => "p4 — #{UNCONVERTED}",
    'compose/helpers/bound_value_spec.rb' => "p4 — #{UNCONVERTED}",
    'compose/helpers/content_inset_helper_spec.rb' => "p4 — #{UNCONVERTED}",
    'compose/helpers/content_scale_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/helpers/effect_style_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/helpers/font_spec_helper_spec.rb' => "p4 — #{UNCONVERTED}",
    'compose/helpers/import_manager_spec.rb' => "p4 — #{UNCONVERTED}",
    'compose/helpers/resource_resolver_spec.rb' => "p4 — #{UNCONVERTED}",
    'compose/helpers/responsive_helper_spec.rb' => "p4 — #{UNCONVERTED}",
    'compose/helpers/shared_string_advice_spec.rb' => "p4 — #{UNCONVERTED}",
    'compose/helpers/tint_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'compose/helpers/visibility_helper_spec.rb' => "p2 — #{UNCONVERTED}",
    'compose/regen_idempotency_spec.rb' => FILE_EFFECTS,
    'compose/unreferenced_generated_view_spec.rb' => "p1 — #{UNCONVERTED}",
    'core/resources/color_manager_spec.rb' => "p3 — #{UNCONVERTED}",
  }.freeze

  let(:root) { File.expand_path(__dir__) }

  def emit_specs(root)
    # `map { }.compact`, not `filter_map`: CI runs this suite on Ruby 2.6 as
    # well (the consumer floor), where Array#filter_map does not exist —
    # 1.8.43's first candidate went red on exactly this line, on all three
    # faces, after six green suites on Ruby 3.2.
    Dir.glob(File.join(root, '**', '*_spec.rb')).sort.map do |path|
      rel = path.sub("#{root}/", '')
      next if rel == File.basename(__FILE__)

      body = File.read(path)
      next unless self.class.emits_kotlin?(body)

      [rel, body]
    end.compact
  end

  # THE PREDICATE'S CONTROLS. The spec that hid today's defect is in; code
  # that emits no Kotlin is out, including the frozen XML path's
  # ResourceResolver whose name the Compose one shares; nothing the old
  # spelling found has left.
  it 'counts tabview_component_spec.rb, which the old spelling left out' do
    rel = 'compose/components/tabview_component_spec.rb'
    body = File.read(File.join(root, rel))
    expect(EMIT_MARKERS_KT.any? { |m| body.include?(m) }).to be(false)
    expect(emit_specs(root).map(&:first)).to include(rel)
  end

  it 'leaves out specs of code that emits no Kotlin' do
    names = emit_specs(root).map(&:first)
    expect(names).not_to include('core/config_manager_spec.rb')
    expect(names).not_to include('xml/helpers/resource_resolver_spec.rb')
  end

  it 'keeps every spec the old spelling found' do
    by_spelling = Dir.glob(File.join(root, '**', '*_spec.rb')).map do |path|
      rel = path.sub("#{root}/", '')
      next if rel == File.basename(__FILE__)

      rel if EMIT_MARKERS_KT.any? { |m| File.read(path).include?(m) }
    end.compact
    expect(by_spelling - emit_specs(root).map(&:first)).to be_empty
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

  # 62, not 19: raised ONCE on 2026-09-25 to correct a false count, not to
  # grow (kjui-compiler-ratchet-misses-component-specs-that-assert-through-
  # expect-result). 19 was the size of a list drawn from a population the
  # old spelling predicate got wrong — 23 specs where the loads-and-describes
  # predicate counts 71. 43 entries joined, each with its reason; three
  # others got a compile arm instead (tabview_component_spec.rb and the two
  # section_extractor specs). From here it only goes down.
  it 'never grows' do
    expect(ALLOWLIST_KT.size).to be <= 62
  end
end
