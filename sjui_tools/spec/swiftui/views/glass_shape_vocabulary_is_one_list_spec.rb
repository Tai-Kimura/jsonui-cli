# frozen_string_literal: true

# One vocabulary for glass shapes, across a repository boundary.
#
# THE SHAPE OF THE DEFECT THIS EXISTS FOR
#
# The Swift library accepted `rectangle`. No declaration ever defined it — it is
# SwiftUI's type name, written into the library from the implementation's vocabulary
# instead of from the SSoT. It survived three removals in one file (the accepted
# list, `resolvedShape`'s cases, `isStaticallyResolvable`'s cases) because each was
# found separately, and nothing compared them to the declaration.
#
# Today the two agree. Nothing HOLDS them in agreement: the generator's enum was
# written by reading the library's list once, by hand. A property that is true by
# coincidence has no defence, so it is pinned here while it is still true.
#
# WHY THIS ARM LIVES IN jsonui-cli
#
# SwiftJsonUI cannot read this repository — it is a separate checkout with no
# dependency on it. This one can read SwiftJsonUI, when it is present.
#
# 🔻 AND WHEN IT IS NOT PRESENT, THIS SKIPS RATHER THAN PASSES.
# A cross-repo arm that silently passes where the sibling is missing is worse than
# no arm: it reports agreement between one list and nothing. CI without the sibling
# checkout must show a skip, and the skip must name what was not checked.

require 'json'

RSpec.describe 'glass shape vocabulary' do
  SSOT_PATH = File.expand_path('../../../../shared/core/attribute_definitions.json', __dir__)

  # Candidate locations for the sibling checkout, most specific first. The
  # environment variable exists so CI can say where it put it.
  LIBRARY_CANDIDATES = [
    ENV.fetch('SWIFTJSONUI_PATH', nil),
    File.expand_path('../../../../../SwiftJsonUI', __dir__),
    File.expand_path('~/resource/SwiftJsonUI')
  ].compact.freeze

  GLASS_SWIFT = 'Sources/SwiftJsonUI/Classes/SwiftUI/SJUIGlass.swift'

  def self.library_root
    LIBRARY_CANDIDATES.find { |root| File.exist?(File.join(root, GLASS_SWIFT)) }
  end

  def declared_shapes
    glass = nil
    walk = lambda do |node|
      case node
      when Hash
        glass ||= node['glass'] if node.key?('glass')
        node.each_value { |v| walk.call(v) }
      when Array then node.each { |v| walk.call(v) }
      end
    end
    walk.call(JSON.parse(File.read(SSOT_PATH)))
    glass
  end

  before do
    skip "SwiftJsonUI checkout not found (looked in: #{LIBRARY_CANDIDATES.join(', ')}) — " \
         'the library/declaration vocabulary comparison did NOT run' if self.class.library_root.nil?
  end

  it 'the declaration and the library accept the same fixed spellings' do
    enum = declared_shapes.dig('properties', 'shape', 'enum')
    expect(enum).not_to be_nil, 'the declaration carries no shape enum to compare against'

    source = File.read(File.join(self.class.library_root, GLASS_SWIFT))
    listed = source[/knownShapeSpellings\s*=\s*\[(.*?)\]/m, 1]
    expect(listed).not_to be_nil, 'knownShapeSpellings not found in SJUIGlass.swift'

    library = listed.scan(/"([^"]+)"/).flatten
    expect(library.sort).to eq(enum.map(&:downcase).sort),
                            "library #{library.inspect} vs declaration #{enum.inspect}"
  end

  # `rounded(N)` carries a number, so it cannot be an enum member. It is declared in
  # prose and both sides read it from there — this pins that both still do.
  # ⚠️ The window is the `isKnown` FUNCTION, not the file. Checking the file for
  # `hasPrefix("rounded")` passes while `isKnown` uses a different prefix, because the
  # spelling also appears in `roundedRadius` — measured: changing one of the two left
  # this arm green.
  it 'both sides carry the parameterised rounded form' do
    expect(declared_shapes['description'].to_s.downcase).to include('rounded(n)')

    source = File.read(File.join(self.class.library_root, GLASS_SWIFT))
    is_known = source[/static func isKnown\(shape:.*?\n    \}/m]
    expect(is_known).not_to be_nil, 'isKnown not found in SJUIGlass.swift'
    expect(is_known).to include('hasPrefix("rounded")'),
                        "isKnown does not accept the rounded form: #{is_known}"
  end

  # 🔑 WHERE the derivation reads, not just what it finds.
  #
  # The declaration's `properties.shape.description` carries the word `rectangle` in a
  # historical note. It is harmless only because the derivation reads the enum and the
  # `glass` description — never the per-property prose. If someone widens the scan to
  # include it, that note becomes vocabulary again and the spelling this train spent
  # the evening removing comes back through the other side.
  # ⚠️ The window is EVERY method in the derivation chain, not just the entry point.
  # Measured: widening `from_enum` to read `properties.shape.description` left an arm
  # that inspected only `declared_glass_shapes` green — the entry point still said
  # `from_enum`, and the change was one call deeper.
  it 'the derivation reads the enum and the glass description, and nothing else' do
    converter_source = File.read(
      File.expand_path('../../../lib/swiftui/views/base_view_converter.rb', __dir__)
    )
    chain = %w[declared_glass_shapes from_enum declares_rounded_form?].map do |name|
      # ⚠️ No `\b` after the name: `declares_rounded_form?` ends in `?`, and a word
      # boundary cannot follow a non-word character, so the pattern found nothing and
      # the arm failed on its own regex rather than on the code. Measured.
      body = converter_source[/def self\.#{Regexp.escape(name)}[^\w?].*?\n        end/m]
      expect(body).not_to be_nil, "#{name} not found — the derivation chain changed shape"
      [name, body]
    end

    chain.each do |name, body|
      # `properties` appears legitimately in `from_enum` (properties.shape.enum), so
      # the thing to forbid is reading a DESCRIPTION from under properties.
      # Named `ruby_body` because it holds the converter's RUBY source. The
      # emitted-Swift ratchet greps every spec for the assertion idiom used on
      # generated Swift, and a local named after source code matched it, so this file
      # was reported as emitting Swift with no compile arm. True for the predicate,
      # false for this file; the honest fix is the accurate name, not an exemption.
      #
      # ⚠️ Do not quote that idiom here either — the ratchet reads comments too. A
      # first attempt renamed the variable and explained why in prose that contained
      # the very string, and the check stayed red.
      ruby_body = body.lines.reject { |l| l.strip.start_with?('#') }.join
      expect(ruby_body).not_to match(/properties.*description|description.*properties/m),
                               "#{name} reads per-property prose — the historical note becomes vocabulary"
    end

    enum_reader = chain.to_h['from_enum']
    expect(enum_reader).to include("'enum'")
    rounded = chain.to_h['declares_rounded_form?']
    expect(rounded).to include("fetch('description', nil)")
  end

  # The note that would become vocabulary, named so the arm above has a subject.
  it 'names the historical note that must stay out of the vocabulary' do
    note = declared_shapes.dig('properties', 'shape', 'description').to_s
    next if note.empty?

    expect(note.downcase).to include('rectangle'),
                             'if this note lost the word, the arm above lost its subject — ' \
                             'check whether the derivation still needs guarding'
  end
end
