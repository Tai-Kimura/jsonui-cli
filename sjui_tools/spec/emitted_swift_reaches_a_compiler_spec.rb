# frozen_string_literal: true

# Every spec that asserts emitted Swift must hand it to a compiler — or say,
# by name, why it does not.
#
# WHY
#
# Three specs pinned `data.collectionDataSource.getCellData(for: "ItemCell")`
# for years. Nothing declares `collectionDataSource`, and `getCellData` has no
# implementation anywhere in SwiftJsonUI. Uncompilable Swift behind passing
# examples, found only when a conformance fixture finally reached that branch
# and failed the build.
#
# `swiftc -parse` would not have caught it — measured, zero errors, because
# the string is syntactically perfect. Only `-typecheck` rejects it, and that
# needs the types a fragment does not carry. Converting a spec is therefore
# real work (see spec/support/emitted_swift.rb), and this gate does not
# pretend otherwise. What it does is turn the REMAINING work from an
# unmeasured majority into a named list that can only shrink.
#
# THE RATCHET: a new spec asserting emitted Swift must compile it — it cannot
# be added here. An entry whose file now compiles, or no longer exists, fails
# as stale. So the list cannot quietly become a permanent exemption, which is
# the usual fate of an allowlist nobody trims.
RSpec.describe 'emitted Swift reaches a compiler' do
  # `expect(out` was a prefix, and it caught locals: `expect(outcome...`,
  # `expect(outer_idx...`. Narrowed 2026-09-10 after counting what leaves the
  # population — the only safe way to narrow a detector is to name the files
  # that stop being detected:
  #
  #   expect(code) 52 files / expect(swift 4 / expect(out 7
  #   narrowing drops exactly 2 files, and neither is lost:
  #     this file            — matches COMPILE_MARKER, so it was already exempt
  #                            (a source-reading check hits its own text)
  #     responsive_helper    — holds 19 `expect(code)`, so it stays in on that
  #   ALLOWLIST entries that leave the population: 0 of 49
  #
  # A spec that emits Swift into a local named `output` still matches.
  EMIT_MARKERS = ['expect(code)', 'expect(swift', 'expect(out)', 'expect(output'].freeze
  COMPILE_MARKER = 'compile_as_swift'

  # WHICH SPECS ARE IN, since 2026-09-25: what a spec loads and describes,
  # not only how it spells its assertions (kjui-compiler-ratchet-misses-
  # component-specs-that-assert-through-expect-result — found on kjui, and
  # this gate had the same predicate). The markers above counted 60 specs;
  # specs that assert through `expect(result…)` / `expect(emit…)` / `expect(
  # body…)` — the binding handlers, the view helpers, the generators — sat
  # outside. A spec is in when it
  #   (a) requires a Swift-emitting file of lib — every file under
  #       lib/swiftui and lib/uikit except NOT_SWIFT, derived below, so a new
  #       converter is in the day it exists;
  #   (b) describes a constant under SjuiTools::SwiftUI / SjuiTools::UIKit
  #       that is not one of NOT_SWIFT's; or
  #   (c) holds one of the markers, so no spec that was in leaves.
  # UIKit is in: it is not frozen (the only frozen emitter is kjui's XML).
  LIB = File.expand_path('../lib', __dir__)
  # Files under lib/swiftui and lib/uikit that emit no Swift, each read:
  NOT_SWIFT = {
    'swiftui/build_cache_manager' => 'build-cache timestamps',
    'uikit/build_cache_manager' => 'build-cache timestamps',
    'swiftui/include_expander' => 'expands layout JSON includes',
    'swiftui/style_loader' => 'merges style JSON into a layout',
    'swiftui/view_registry' => 'an in-memory map of views',
    'swiftui/collection_cell_index' => 'which layouts render as cells (an index of JSON)',
    'swiftui/scrolling_cell_index' => 'which layouts render in a scrolling collection (an index of JSON)',
    'swiftui/binding/binding_handler_registry' => 'picks a handler; emits nothing itself',
    'swiftui/views/attribute_vocabulary' => 'reads the SSoT vocabulary',
    'uikit/json_loader' => 'loads and validates layout JSON',
    'uikit/json_loader_config' => 'reads ignore sets from config',
    'uikit/json_analyzer' => 'validates layout JSON'
  }.freeze
  NOT_SWIFT_DIRS = ['uikit/tools/', 'uikit/xcode_project/destroyers/'].freeze # project-file surgery
  SWIFT_LIB = Dir.glob(File.join(LIB, '{swiftui,uikit}', '**', '*.rb'))
                 .map { |f| f.sub("#{LIB}/", '').sub(/\.rb\z/, '') }
                 .reject { |f| NOT_SWIFT.key?(f) || NOT_SWIFT_DIRS.any? { |d| f.start_with?(d) } }.freeze
  NOT_SWIFT_CONSTANTS = %w[BuildCacheManager IncludeExpander StyleLoader ViewRegistry CollectionCellIndex
                           ScrollingCellIndex BindingHandlerRegistry AttributeVocabulary JsonLoader
                           JsonLoaderConfig JsonAnalyzer].freeze

  def self.emits_swift?(body)
    requires = body.scan(/^\s*require(?:_relative)?\s+['"]([^'"]+)['"]/).flatten
    loads = requires.any? { |r| SWIFT_LIB.any? { |lib| r == lib || r.end_with?("/#{lib}") } }
    target = body[/^RSpec\.describe\s+([\w:]+)/, 1]
    describes = !target.nil? && target.start_with?('SjuiTools::SwiftUI::', 'SjuiTools::UIKit::') &&
                !NOT_SWIFT_CONSTANTS.include?(target.split('::').last)
    loads || describes || EMIT_MARKERS.any? { |m| body.include?(m) }
  end

  # The reason every current entry carries. A fragment needs a stub universe —
  # the types it references — before a compiler can read it, and that is
  # per-shape work. Entries earn a more specific reason as they are reviewed;
  # none may be added.
  #
  # ⚠️ The marker list over-captures: a few of these assert resource or CLI
  # output rather than Swift. That is deliberate — the predicate is a cheap,
  # reproducible one, and a file that turns out not to emit Swift leaves this
  # list by getting a truthful reason, not by being silently dropped from the
  # population.
  UNCONVERTED = 'Swift fragment; stub universe not built yet'
  FILE_EFFECTS = '— asserts which files a command writes, deletes or leaves in place, not what the Swift in them says'

  # Each reason starts with the order to convert in: p1 converters and code
  # that rewrites emitted code; p2 generators and binding handlers; p3 view
  # helpers; p4 CLI and setup. `—`: not code — nothing to compile.
  ALLOWLIST = {
    'cli/commands/build_prunes_deleted_layout_outputs_spec.rb' => FILE_EFFECTS,
    'cli/commands/build_spec.rb' => "p4 — #{UNCONVERTED}",
    'cli/commands/convert_spec.rb' => "p4 — #{UNCONVERTED}",
    'cli/commands/destroy_spec.rb' => "p4 — #{UNCONVERTED}",
    'cli/commands/generate_spec.rb' => "p4 — #{UNCONVERTED}",
    'core/resources/color_manager_spec.rb' => "p4 — #{UNCONVERTED}",
    'core/resources/string_manager_plural_spec.rb' => "p4 — #{UNCONVERTED}",
    'core/resources/string_manager_spec.rb' => "p4 — #{UNCONVERTED}",
    'swiftui/action_manager_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/binding/binding_expression_invalid_path_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/binding/button_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/binding/image_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/binding/label_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/binding/text_field_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/binding/toggle_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/binding/view_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/blocking_layout_not_generated_spec.rb' => "p4 — #{UNCONVERTED}",
    'swiftui/converter_factory_responsive_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/converter_factory_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/data_model_updater_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/generators/adapter_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/generators/collection_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/generators/converter_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/generators/scaffold_files_honor_overwrite_options_spec.rb' => FILE_EFFECTS,
    'swiftui/generators/scaffolds_carry_the_user_owned_header_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/generators/swift_component_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/generators/view_adapter_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/generators/view_generator_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/helpers/font_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/helpers/string_manager_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/json_to_swiftui_converter_responsive_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/json_to_swiftui_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/scrolling_cell_index_spec.rb' => "p4 — #{UNCONVERTED}",
    'swiftui/section_bounder_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/setup/hotloader_generator_spec.rb' => "p4 — #{UNCONVERTED}",
    'swiftui/setup/swiftui_setup_spec.rb' => FILE_EFFECTS,
    'swiftui/view_updater_responsive_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/view_updater_screen_marker_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/view_updater_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/view_updater_variant_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/alignment_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/alignment_wrapper_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/base_view_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/blur_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/bound_value_emission_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/button_converter_characterization_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/button_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/button_image_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/checkbox_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/child_renderer_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/child_rendering_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/collection_cell_identifier_single_site_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/color_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/container_accessibility_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/disabled_outside_the_accessibility_element_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/dynamic_component_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/embed_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/flow_wraps_under_a_scrolling_ancestor_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/frame_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/gradient_view_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/handler_name_spelling_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/views/hidden_binding_identifier_spec.rb' => "p2 — #{UNCONVERTED}",
    'swiftui/views/icon_label_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/image_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/include_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/indicator_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/input_lands_on_a_real_uikeyboardtype_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/label_converter_characterization_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/modifier_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/network_image_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/normalized_layout_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/pair_scan_closure_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/positioning_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/progress_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/radio_accessibility_label_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/radio_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/relative_positioning_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/responsive_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/safeareaview_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/segment_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/selectbox_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/slider_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/spacing_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/stack_alignment_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/tab_view_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/template_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/textfield_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/textview_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/toggle_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/view_converter_responsive_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/view_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/visibility_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'swiftui/views/web_converter_spec.rb' => "p1 — #{UNCONVERTED}",
    'swiftui/views/weighted_stack_helper_spec.rb' => "p3 — #{UNCONVERTED}",
    'uikit/binding_file_manager_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/button_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/check_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/collection_view_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/icon_label_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/image_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/label_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/network_image_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/radio_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/scroll_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/select_box_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/switch_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/text_field_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/handlers/text_view_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/import_module_manager_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/json_analyzer_spec.rb' => "p4 — #{UNCONVERTED}",
    'uikit/json_loader_spec.rb' => "p4 — #{UNCONVERTED}",
    'uikit/string_module_spec.rb' => "p3 — #{UNCONVERTED}",
    'uikit/ui_control_event_manager_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/view_binding_handler_factory_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/view_binding_handler_spec.rb' => "p2 — #{UNCONVERTED}",
    'uikit/xcode_project/app_delegate_hotloader_region_spec.rb' => "p4 — #{UNCONVERTED}",
    'uikit/xcode_project/generators/converter_generator_spec.rb' => "p2 — #{UNCONVERTED}",
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
      next unless self.class.emits_swift?(body)

      [rel, body]
    end.compact
  end

  # THE PREDICATE'S CONTROLS: two specs the markers left out are in; code
  # that emits no Swift is out; nothing the markers found has left.
  it 'counts the view helpers and binding handlers the markers left out' do
    %w[swiftui/views/visibility_helper_spec.rb swiftui/binding/button_binding_handler_spec.rb].each do |rel|
      body = File.read(File.join(root, rel))
      expect(EMIT_MARKERS.any? { |m| body.include?(m) }).to be(false), rel
      expect(emit_specs(root).map(&:first)).to include(rel)
    end
  end

  it 'leaves out specs of code that emits no Swift' do
    names = emit_specs(root).map(&:first)
    %w[core/base_path_spec.rb core/json_loader_spec.rb swiftui/build_cache_manager_spec.rb
       swiftui/style_loader_spec.rb].each { |rel| expect(names).not_to include(rel) }
  end

  it 'keeps every spec the markers found' do
    by_marker = Dir.glob(File.join(root, '**', '*_spec.rb')).map do |path|
      rel = path.sub("#{root}/", '')
      next if rel == File.basename(__FILE__)

      rel if EMIT_MARKERS.any? { |m| File.read(path).include?(m) }
    end.compact
    expect(by_marker - emit_specs(root).map(&:first)).to be_empty
  end

  it 'has no spec asserting emitted Swift that neither compiles nor is listed' do
    offenders = emit_specs(root).reject do |rel, body|
      body.include?(COMPILE_MARKER) || ALLOWLIST.key?(rel)
    end.map(&:first)

    expect(offenders).to be_empty,
                         "these assert emitted Swift with no compile arm. Add one " \
                         "(see spec/support/emitted_swift.rb):\n#{offenders.join("\n")}"
  end

  it 'has no allowlist entry whose file is gone' do
    stale = ALLOWLIST.keys.reject { |rel| File.file?(File.join(root, rel)) }
    expect(stale).to be_empty, "delete these allowlist entries:\n#{stale.join("\n")}"
  end

  it 'has no allowlist entry that already compiles' do
    # The shrink ratchet. Converting a spec without removing its entry leaves
    # the list overstating the debt, and a list that overstates is a list
    # nobody trusts enough to read.
    converted = ALLOWLIST.keys.select do |rel|
      path = File.join(root, rel)
      File.file?(path) && File.read(path).include?(COMPILE_MARKER)
    end
    expect(converted).to be_empty,
                         "these now compile — remove them from ALLOWLIST:\n#{converted.join("\n")}"
  end

  it 'has no allowlist entry the predicate no longer reaches' do
    # The two arms above ask whether an entry is stale by its FILE. This one
    # asks whether it is stale by the POPULATION: narrow a marker, or edit a
    # spec until it stops matching one, and its entry becomes debt that no
    # measurement can ever retire. 49 would then be partly a fiction, and the
    # ratchet would be guarding a number that had stopped meaning anything.
    #
    # Zero when written, which is why it could be added without turning red —
    # the moment to install a check is while it is still free.
    unreachable = ALLOWLIST.keys.select do |rel|
      path = File.join(root, rel)
      File.file?(path) && !self.class.emits_swift?(File.read(path))
    end
    expect(unreachable).to be_empty,
                           "these are listed but no marker reaches them, so nothing " \
                           "can ever retire them:\n#{unreachable.join("\n")}"
  end

  it 'never grows' do
    # A number the report can quote without re-deriving it, and one that only
    # moves down. Raising it is a deliberate edit that shows up in review.
    #
    # 117, not 49: raised ONCE on 2026-09-25 to correct a false count, not to
    # grow (kjui-compiler-ratchet-misses-component-specs-that-assert-through-
    # expect-result). 49 bounded a list drawn from the markers' population —
    # 60 specs where the loads-and-describes predicate counts 129. 69 entries
    # joined, each with its reason. From here it only goes down.
    expect(ALLOWLIST.size).to be <= 117
  end
end
