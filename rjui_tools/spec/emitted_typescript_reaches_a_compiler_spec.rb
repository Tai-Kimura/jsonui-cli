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

  # WHICH SPECS ARE IN, since 1.9.0: what a spec loads and describes, not
  # only how it spells its assertions — the rule sjui's and kjui's gates took
  # on 2026-09-25 (kjui-compiler-ratchet-misses-component-specs-that-assert-
  # through-expect-result). Twenty specs sat outside the markers here: five
  # already compiled, twelve were given a compile arm when they came in, and
  # three emit nothing a compiler can hold (their reasons are below). A spec
  # is in when it
  #   (a) requires a TypeScript-emitting file of lib — every file under
  #       lib/react except NOT_TS, derived below, so a new converter is in
  #       the day it exists;
  #   (b) describes a constant under RjuiTools::React that is not one of
  #       NOT_TS's; or
  #   (c) holds one of the markers, so no spec that was in leaves.
  LIB_TS = File.expand_path('../lib', __dir__)
  # Files under lib/react that emit no TypeScript, each read:
  NOT_TS = {
    'react/style_loader' => 'merges style JSON into a layout',
    'react/include_expander' => 'expands layout JSON includes, for the Data type (the include is drawn by converters/include_converter)',
    'react/converters/extensions/converter_mappings' => 'maps a type to its converter class name'
  }.freeze
  TS_LIB = Dir.glob(File.join(LIB_TS, 'react', '**', '*.rb'))
              .map { |f| f.sub("#{LIB_TS}/", '').sub(/\.rb\z/, '') }
              .reject { |f| NOT_TS.key?(f) }.freeze
  NOT_TS_CONSTANTS = %w[StyleLoader IncludeExpander].freeze

  def self.emits_typescript?(body)
    requires = body.scan(/^\s*require(?:_relative)?\s+['"]([^'"]+)['"]/).flatten
    loads = requires.any? { |r| TS_LIB.any? { |lib| r == lib || r.end_with?("/#{lib}") } }
    target = body[/^RSpec\.describe\s+([\w:]+)/, 1]
    describes = !target.nil? && target.start_with?('RjuiTools::React::') &&
                !NOT_TS_CONSTANTS.include?(target.split('::').last)
    loads || describes || EMIT_MARKERS_TS.any? { |m| body.include?(m) }
  end

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
    'react/tailwind_mapper_spec.rb' => UNCONVERTED,
    # In by what they load (2026-09-26), and nothing in them is code:
    'cli/stage_errors_reach_the_ledger_spec.rb' =>
      'reads the stage ledger and the log a build writes; it asserts no emitted TypeScript',
    'react/helpers/lucide_icon_helper_spec.rb' =>
      'a lucide-react component name; whether lucide-react exports it needs lucide-react, which ' \
      'spec/support does not install — a compile arm would declare the very names it checks',
    'react/tailwind_mapper_gravity_axis_spec.rb' =>
      'Tailwind class names inside a className string, where tsc takes any string'
  }.freeze

  let(:root) { File.expand_path(__dir__) }

  def emit_specs(root)
    # `map { }.compact`, not `filter_map`: CI ran this suite on Ruby 2.6 as
    # well until jsonui-cli 1.9.0 (the consumer floor then; 3.2 since),
    # where Array#filter_map does not exist —
    # 1.8.43's first candidate went red on exactly this line, on all three
    # faces, after six green suites on Ruby 3.2.
    Dir.glob(File.join(root, '**', '*_spec.rb')).sort.map do |path|
      rel = path.sub("#{root}/", '')
      next if rel == File.basename(__FILE__)

      body = File.read(path)
      next unless self.class.emits_typescript?(body)

      [rel, body]
    end.compact
  end

  # THE PREDICATE'S CONTROLS: specs the markers left out are in; code that
  # emits no TypeScript is out; nothing the markers found has left.
  it 'counts the specs the markers left out' do
    %w[react/converters/radio_bound_items_spec.rb react/generators/converter_binding_prop_spec.rb].each do |rel|
      body = File.read(File.join(root, rel))
      expect(EMIT_MARKERS_TS.any? { |m| body.include?(m) }).to be(false), rel
      expect(emit_specs(root).map(&:first)).to include(rel)
    end
  end

  it 'leaves out specs of code that emits no TypeScript' do
    names = emit_specs(root).map(&:first)
    %w[core/attribute_validator_spec.rb core/shared_core_mirror_spec.rb
       react/converters/raw_json_reads_spec.rb].each { |rel| expect(names).not_to include(rel) }
  end

  # NOT_TS is a line, and a line has two sides: the same spec shape, loading
  # or describing a file on each side of it.
  it 'draws the NOT_TS line where it says' do
    shape = ->(file, constant) { "require 'react/#{file}'\nRSpec.describe RjuiTools::React::#{constant} do\nend\n" }
    expect(self.class.emits_typescript?(shape.('style_loader', 'StyleLoader'))).to be(false)
    expect(self.class.emits_typescript?("require 'react/converters/extensions/converter_mappings'\n")).to be(false)
    expect(self.class.emits_typescript?(shape.('converters/label_converter', 'Converters::LabelConverter'))).to be(true)
    expect(self.class.emits_typescript?("require 'react/style_loader'\n")).to be(false)
    expect(self.class.emits_typescript?("RSpec.describe RjuiTools::React::StyleLoader do\nend\n")).to be(false)
    expect(self.class.emits_typescript?("RSpec.describe RjuiTools::React::TailwindMapper do\nend\n")).to be(true)
  end

  it 'keeps every spec the markers found' do
    by_marker = Dir.glob(File.join(root, '**', '*_spec.rb')).map do |path|
      rel = path.sub("#{root}/", '')
      next if rel == File.basename(__FILE__)

      rel if EMIT_MARKERS_TS.any? { |m| File.read(path).include?(m) }
    end.compact
    expect(by_marker - emit_specs(root).map(&:first)).to be_empty
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

  it 'has no allowlist entry the predicate no longer reaches' do
    # Stale by the POPULATION rather than by the file: an entry no rule
    # reaches is debt nothing can ever retire. Zero when written.
    unreachable = ALLOWLIST_TS.keys.select do |rel|
      path = File.join(root, rel)
      File.file?(path) && !self.class.emits_typescript?(File.read(path))
    end
    expect(unreachable).to be_empty,
                           "these are listed but no rule reaches them, so nothing " \
                           "can ever retire them:\n#{unreachable.join("\n")}"
  end

  it 'never grows' do
    # 58 = the 55 entries 1.8.120 held + the 3 reasons above (2026-09-26),
    # each one a spec that came in with the loads-and-describes rule. Not
    # 56 + 3: 56 had one entry of slack since 5a6cbb45 (2026-09-14) took
    # select_box_converter_spec out of the list and left the number where
    # it was. 57 the same day: embed_converter_spec compiles its events
    # (ticket rjui-embed-event-bridge-calls-an-undeclared-view-model), and
    # the number went down with it. From here it only goes down.
    expect(ALLOWLIST_TS.size).to be <= 57
  end
end
