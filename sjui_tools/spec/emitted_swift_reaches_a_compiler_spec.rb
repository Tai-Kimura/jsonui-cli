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
  EMIT_MARKERS = ['expect(code)', 'expect(swift', 'expect(out'].freeze
  COMPILE_MARKER = 'compile_as_swift'

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

  ALLOWLIST = {
    'cli/commands/destroy_spec.rb' => UNCONVERTED,
    'core/resources/color_manager_spec.rb' => UNCONVERTED,
    'core/resources/string_manager_plural_spec.rb' => UNCONVERTED,
    'core/resources/string_manager_spec.rb' => UNCONVERTED,
    'swiftui/converter_factory_spec.rb' => UNCONVERTED,
    'swiftui/generators/adapter_generator_spec.rb' => UNCONVERTED,
    'swiftui/json_to_swiftui_converter_responsive_spec.rb' => UNCONVERTED,
    'swiftui/json_to_swiftui_converter_spec.rb' => UNCONVERTED,
    'swiftui/scrolling_cell_index_spec.rb' => UNCONVERTED,
    'swiftui/views/base_view_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/blur_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/bound_value_emission_spec.rb' => UNCONVERTED,
    'swiftui/views/button_converter_characterization_spec.rb' => UNCONVERTED,
    'swiftui/views/button_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/button_image_spec.rb' => UNCONVERTED,
    'swiftui/views/checkbox_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/collection_cell_identifier_single_site_spec.rb' => UNCONVERTED,
    'swiftui/views/container_accessibility_spec.rb' => UNCONVERTED,
    'swiftui/views/disabled_outside_the_accessibility_element_spec.rb' => UNCONVERTED,
    'swiftui/views/dynamic_component_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/embed_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/flow_wraps_under_a_scrolling_ancestor_spec.rb' => UNCONVERTED,
    'swiftui/views/frame_helper_spec.rb' => UNCONVERTED,
    'swiftui/views/gradient_view_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/hidden_binding_identifier_spec.rb' => UNCONVERTED,
    'swiftui/views/icon_label_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/image_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/include_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/indicator_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/label_converter_characterization_spec.rb' => UNCONVERTED,
    'swiftui/views/network_image_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/normalized_layout_spec.rb' => UNCONVERTED,
    'swiftui/views/pair_scan_closure_spec.rb' => UNCONVERTED,
    'swiftui/views/progress_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/radio_accessibility_label_spec.rb' => UNCONVERTED,
    'swiftui/views/radio_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/responsive_helper_spec.rb' => UNCONVERTED,
    'swiftui/views/scrollview_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/segment_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/selectbox_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/slider_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/tab_view_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/textfield_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/textview_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/toggle_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/view_converter_responsive_spec.rb' => UNCONVERTED,
    'swiftui/views/view_converter_spec.rb' => UNCONVERTED,
    'swiftui/views/web_converter_spec.rb' => UNCONVERTED,
    'uikit/json_loader_spec.rb' => UNCONVERTED
  }.freeze

  let(:root) { File.expand_path(__dir__) }

  def emit_specs(root)
    Dir.glob(File.join(root, '**', '*_spec.rb')).sort.filter_map do |path|
      body = File.read(path)
      next unless EMIT_MARKERS.any? { |m| body.include?(m) }

      [path.sub("#{root}/", ''), body]
    end
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

  it 'never grows' do
    # A number the report can quote without re-deriving it, and one that only
    # moves down. Raising it is a deliberate edit that shows up in review.
    expect(ALLOWLIST.size).to be <= 49
  end
end
