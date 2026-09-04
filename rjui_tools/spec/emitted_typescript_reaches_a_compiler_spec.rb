# frozen_string_literal: true

# Every spec that asserts emitted TypeScript must hand it to a compiler — or
# say, by name, why it does not.
#
# WHY THIS FACE HAD NOTHING, AND WHY NOBODY NOTICED
#
# `dev-guide/release/compile-emitted-kotlin.sh` justified its own existence
# with "`tsc --noEmit` and `swiftc -parse` run in the suite, and nothing
# answers for Kotlin". Measured: nothing answered for TypeScript either. No
# matcher, no `spec/support` directory, no rjui spec invoking a compiler. A
# stale sentence was vouching for a face it did not cover, and it read as
# reassurance rather than as a claim to check.
#
# Parsing would not have been enough. On the Swift side `-parse` accepted
# `data.collectionDataSource.getCellData(...)` — a property nothing declares
# calling a method that exists nowhere — with zero errors; only `-typecheck`
# rejected it. rjui's one pre-existing check is a `@babel/parser` parse, which
# has exactly that blind spot (and is env-gated, so it skips by default).
#
# ⚠️ THE PREDICATE IS WIDER THAN THE ONE SPECIFIED, deliberately.
# `expect(code)` / `expect(ts…` / `expect(out…` captures 19 files here. rjui's
# converters return `result`, and adding `expect(result)` captures 57 — the
# 38 in between would have been invisible to this gate. A denominator decided
# by the reader's vocabulary rather than the producer's is the failure this
# whole ticket is about, so the gate reads the spelling rjui actually uses.
#
# THE RATCHET: a new spec asserting emitted TypeScript must compile it — it
# cannot be added here. An entry whose file now compiles, or no longer exists,
# fails as stale.
#
# 📌 An arm costs ~0.16s (tsc 5.9 with --skipLibCheck on one small file), so
# unlike the Kotlin arms (~27s of JVM start) these can be many and narrow.
RSpec.describe 'emitted TypeScript reaches a compiler' do
  EMIT_MARKERS_TS = ['expect(code)', 'expect(ts', 'expect(out', 'expect(result)'].freeze
  COMPILE_MARKER_TS = 'compile_as_typescript'

  # A fragment needs the types it references declared before tsc can read it,
  # and that is per-shape work. Entries earn a more specific reason as they
  # are reviewed; none may be added.
  UNCONVERTED = 'TSX fragment; ambient declarations not written yet'

  ALLOWLIST_TS = {
    'cli/commands/hotload_command_spec.rb' => UNCONVERTED,
    'cli/commands/string_manager_emit_spec.rb' => UNCONVERTED,
    'cli/commands/string_manager_plural_spec.rb' => UNCONVERTED,
    'core/resources/color_manager_spec.rb' => UNCONVERTED,
    'core/type_converter_spec.rb' => UNCONVERTED,
    'react/collection_data_source_ts_spec.rb' => UNCONVERTED,
    'react/converters/base_converter_font_spec_spec.rb' => UNCONVERTED,
    'react/converters/base_converter_id_binding_spec.rb' => UNCONVERTED,
    'react/converters/base_converter_maxheight_spec.rb' => UNCONVERTED,
    'react/converters/base_converter_spec.rb' => UNCONVERTED,
    'react/converters/bind_fallback_spec.rb' => UNCONVERTED,
    'react/converters/binding_literal_fallback_spec.rb' => UNCONVERTED,
    'react/converters/blur_converter_spec.rb' => UNCONVERTED,
    'react/converters/bound_value_emitters_spec.rb' => UNCONVERTED,
    'react/converters/button_converter_spec.rb' => UNCONVERTED,
    'react/converters/circle_view_converter_spec.rb' => UNCONVERTED,
    'react/converters/collection_converter_spec.rb' => UNCONVERTED,
    'react/converters/collection_key_expr_spec.rb' => UNCONVERTED,
    'react/converters/color_style_resolution_spec.rb' => UNCONVERTED,
    'react/converters/content_mode_vocabulary_spec.rb' => UNCONVERTED,
    'react/converters/embed_converter_spec.rb' => UNCONVERTED,
    'react/converters/extension_visibility_spec.rb' => UNCONVERTED,
    'react/converters/font_weight_numeric_face_spec.rb' => UNCONVERTED,
    'react/converters/gradient_view_converter_spec.rb' => UNCONVERTED,
    'react/converters/icon_label_converter_spec.rb' => UNCONVERTED,
    'react/converters/image_converter_spec.rb' => UNCONVERTED,
    'react/converters/include_converter_spec.rb' => UNCONVERTED,
    'react/converters/indicator_converter_spec.rb' => UNCONVERTED,
    'react/converters/invisible_class_scope_spec.rb' => UNCONVERTED,
    'react/converters/label_converter_spec.rb' => UNCONVERTED,
    'react/converters/network_image_converter_spec.rb' => UNCONVERTED,
    'react/converters/onclick_array_face_spec.rb' => UNCONVERTED,
    'react/converters/progress_converter_spec.rb' => UNCONVERTED,
    'react/converters/radio_converter_spec.rb' => UNCONVERTED,
    'react/converters/responsive_integration_spec.rb' => UNCONVERTED,
    'react/converters/scroll_view_converter_spec.rb' => UNCONVERTED,
    'react/converters/segment_converter_spec.rb' => UNCONVERTED,
    'react/converters/select_box_converter_spec.rb' => UNCONVERTED,
    'react/converters/slider_converter_spec.rb' => UNCONVERTED,
    'react/converters/switch_converter_spec.rb' => UNCONVERTED,
    'react/converters/tab_view_converter_spec.rb' => UNCONVERTED,
    'react/converters/text_field_converter_spec.rb' => UNCONVERTED,
    'react/converters/text_view_converter_spec.rb' => UNCONVERTED,
    'react/converters/toggle_converter_spec.rb' => UNCONVERTED,
    'react/converters/view_converter_spec.rb' => UNCONVERTED,
    'react/converters/web_converter_spec.rb' => UNCONVERTED,
    'react/data_model_generator_spec.rb' => UNCONVERTED,
    'react/framework_seam_spec.rb' => UNCONVERTED,
    'react/generators/converter_generator_spec.rb' => UNCONVERTED,
    'react/helpers/font_spec_helper_spec.rb' => UNCONVERTED,
    'react/helpers/string_manager_helper_spec.rb' => UNCONVERTED,
    'react/react_generator_dispatch_spec.rb' => UNCONVERTED,
    'react/react_generator_screen_marker_spec.rb' => UNCONVERTED,
    'react/react_generator_spec.rb' => UNCONVERTED,
    'react/react_generator_variant_spec.rb' => UNCONVERTED,
    'react/tailwind_mapper_spec.rb' => UNCONVERTED  }.freeze

  let(:root) { File.expand_path(__dir__) }

  def emit_specs(root)
    Dir.glob(File.join(root, '**', '*_spec.rb')).sort.filter_map do |path|
      body = File.read(path)
      next unless EMIT_MARKERS_TS.any? { |m| body.include?(m) }

      [path.sub("#{root}/", ''), body]
    end
  end

  it 'has no spec asserting emitted TypeScript that neither compiles nor is listed' do
    offenders = emit_specs(root).reject do |rel, body|
      body.include?(COMPILE_MARKER_TS) || ALLOWLIST_TS.key?(rel)
    end.map(&:first)

    expect(offenders).to be_empty,
                         "these assert emitted TypeScript with no compile arm. Add one " \
                         "(see spec/support/typescript_compiler.rb):\n#{offenders.join("\n")}"
  end

  it 'has no allowlist entry whose file is gone' do
    stale = ALLOWLIST_TS.keys.reject { |rel| File.file?(File.join(root, rel)) }
    expect(stale).to be_empty, "delete these allowlist entries:\n#{stale.join("\n")}"
  end

  it 'has no allowlist entry that already compiles' do
    converted = ALLOWLIST_TS.keys.select do |rel|
      path = File.join(root, rel)
      File.file?(path) && File.read(path).include?(COMPILE_MARKER_TS)
    end
    expect(converted).to be_empty,
                         "these now compile — remove them from ALLOWLIST_TS:\n#{converted.join("\n")}"
  end

  it 'never grows' do
    expect(ALLOWLIST_TS.size).to be <= 56
  end
end
