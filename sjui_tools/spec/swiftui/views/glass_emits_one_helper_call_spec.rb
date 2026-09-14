require 'stringio'
# frozen_string_literal: true

# `glass` is declared on `common` with `platform: swift` and
# `mode: ["uikit", "swiftui"]` — the first declaration in the file to pair
# those two modes. This is the SwiftUI codegen half.
#
# 🔻 ONE HELPER CALL, NEVER AN `if #available` IN GENERATED CODE.
# `.glassEffect` is `@available(iOS 26.0, …)`, so something has to check.
# Putting the check in the emitted source would copy it to every site that
# declares `glass`, and each copy asks the RUNNING OS — the rendered picture
# would then depend on the device, which is how a fallback stopped being
# reproducible in b7056242 and had to come out. The library holds the single
# check; this emitter writes `.sjuiGlassEffect(…)` and nothing else.
# (Ruling: iOS lane, 2026-09-14.)
#
# 🔻 `shape` IS PASSED THROUGH, NOT RESOLVED.
# `rounded(N)` and `rect` could be resolved statically. `capsule` and
# `circle` cannot — they depend on the laid-out height, which codegen does
# not know. Resolving the two that are knowable would split one mapping
# across two layers by an accident of what is statically available, so all
# four go to the helper as a string.
#
# ⚠️ THE DECLARED SET IS NOT HONOURED BY BOTH MODES, measured from the SDK:
#   SwiftUI  SwiftUICore.Glass       regular / clear / identity, and
#            `.glassEffect(_:in:)`   takes a shape          -> all four keys
#   UIKit    UIGlassEffectStyle      Regular / Clear only (no identity), and
#            UIGlassEffect is a UIVisualEffect subclass with NO shape
# So `identity` and `shape` are SwiftUI-only. This file is the SwiftUI path
# and passes everything through; the UIKit limits belong in the declaration's
# prose, one sentence per limit with the mode as its subject.

require 'swiftui/views/blur_converter'

# The helper this emitter calls does not exist in the library yet — the iOS
# lane implements it. So the stub below is a CONTRACT, not a mirror of
# something already written, and that is the opposite of how every other stub
# in spec/support works (those are transcribed from a real declaration, and
# the file says a stub accepting more than the library does lets a wrong
# argument list pass here and fail in a consumer build).
#
# 🔻 WHAT THAT MEANS FOR THIS ARM: compiling against this stub proves the
# emitted call is well-formed Swift AND that it matches THIS signature. It
# does NOT prove the library agrees, because the library has nothing to
# agree with yet. When `sjuiGlassEffect` lands, someone has to check the two
# against each other — that check does not exist and cannot exist today.
# Recorded rather than left implicit, because a green compile arm reads as
# "the library and the codegen agree" to anyone who did not write it.
GLASS_HELPER_CONTRACT = <<~SWIFT
  extension View {
      func sjuiGlassEffect(style: String? = nil,
                           tint: Color? = nil,
                           interactive: Bool? = nil,
                           shape: String? = nil) -> some View { self }
  }
SWIFT

RSpec.describe 'glass on the SwiftUI codegen path' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all)  { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  # Any converter that inherits the common modifier pass will do; Blur takes a
  # single argument, so it is the cheapest host for a `common` attribute.
  def emit(component)
    SjuiTools::SwiftUI::Views::BlurConverter.new({ 'type' => 'Blur' }.merge(component)).convert.to_s
  end

  # The emitted helper call, or nil. Use this ONLY where nil is a legitimate
  # answer — the three "emits nothing" arms.
  def glass_line(component)
    emit(component).lines.map(&:strip).find { |l| l.include?('sjuiGlassEffect') }
  end

  # 🔻 THE SAME LOOKUP, BUT A MISS IS A FAILURE.
  #
  # Every arm that asserts something ABOUT the emitted call — the equality
  # arms and, critically, the three compile arms — has to fail when there is
  # no call to assert about. Measured by triage: renaming the emitted
  # spelling in the implementation AND the assertions, leaving the stub's
  # `func sjuiGlassEffect` alone, made `find` return nil. The compile arms
  # then handed swiftc
  #
  #     Color.clear
  #             (nothing)
  #
  # which type-checks perfectly, so all three stayed GREEN while the string
  # arms went red. Adding this raise turned the same mutation from 7
  # failures into 13, and the six new ones include those three by name.
  #
  # THE GENERAL SHAPE: when a compile arm's subject is a line it went
  # LOOKING for, a failed search does not fail the arm — it empties it. The
  # arm keeps reporting that an empty program compiled. Type errors are
  # still caught (a raw String passed where `Color?` is expected does fail),
  # but a renamed or vanished emit is not. So a search that feeds an
  # assertion must map "not found" onto the assertion's failure.
  # The warning goes to stdout, so the arms that assert it have to capture it.
  def capture_stdout
    original = $stdout
    $stdout = StringIO.new
    yield
    $stdout.string
  ensure
    $stdout = original
  end

  def glass_line!(component)
    glass_line(component) or
      raise "no sjuiGlassEffect line emitted for #{component.inspect} — " \
            'without this the compile arms below would hand swiftc a view ' \
            'with no glass call in it, and pass'
  end

  describe 'when the attribute is not asking for glass' do
    it 'emits nothing when absent' do
      expect(glass_line({})).to be_nil
    end

    it 'emits nothing for false' do
      expect(glass_line('glass' => false)).to be_nil
    end

    it 'emits nothing for the string "false"' do
      # JSON from a layout can carry either; `true`/`false` arrive as strings
      # through some bound paths.
      expect(glass_line('glass' => 'false')).to be_nil
    end
  end

  describe 'the boolean form' do
    it 'emits the helper with no arguments' do
      expect(glass_line!('glass' => true)).to eq('.sjuiGlassEffect()')
    end
  end

  describe 'the object form' do
    it 'passes style through' do
      expect(glass_line!('glass' => { 'style' => 'clear' }))
        .to eq('.sjuiGlassEffect(style: "clear")')
    end

    # ⚠️ This pinned "pass through" as the SPEC when there was no口 to check a
    # spelling. There is one now: the emitter reads the declared vocabulary from
    # attribute_definitions.json and warns on anything outside it. What still passes
    # through is the RESOLUTION — capsule and circle depend on the laid-out size, so
    # the library resolves all four, and codegen writes the spelling verbatim.
    it 'passes shape through unresolved, including the height-dependent ones' do
      expect(glass_line!('glass' => { 'shape' => 'capsule' }))
        .to eq('.sjuiGlassEffect(shape: "capsule")')
      expect(glass_line!('glass' => { 'shape' => 'rounded(12)' }))
        .to eq('.sjuiGlassEffect(shape: "rounded(12)")')
    end

    it 'accepts every spelling the declaration defines, without warning' do
      declared = %w[capsule circle rect] + ['rounded(12)']
      declared.each do |spelling|
        output = capture_stdout { glass_line!('glass' => { 'shape' => spelling }) }
        expect(output).not_to include('not declared'), "#{spelling} was reported as undeclared"
      end
    end

    # `rounded(N)` cannot be an enum member — it carries a number — so the declaration
    # holds the three fixed words in `properties.shape.enum` and the parameterised form
    # in prose. A check that reads only the enum rejects every rounded() a consumer
    # writes: measured, that is exactly what happened before the prose branch existed.
    it 'accepts the parameterised rounded form, which the enum cannot hold' do
      output = capture_stdout { glass_line!('glass' => { 'shape' => 'rounded(24)' }) }
      expect(output).not_to include('not declared')
    end

    it 'warns about a spelling the declaration does not define, and still emits' do
      line = nil
      output = capture_stdout { line = glass_line!('glass' => { 'shape' => 'elipse' }) }
      expect(output).to include('not declared')
      expect(output).to include('elipse')
      # Still emitted: a typo degrades to the SDK default at render time rather than
      # failing the build. The warning is what makes it visible while it is fixable.
      expect(line).to eq('.sjuiGlassEffect(shape: "elipse")')
    end

    # 🔑 The arm that a hard-coded list cannot pass: swap the DECLARATION and check the
    # emitter's answers follow. Asserting the declaration's contents (below) proves the
    # file says what we think; only this proves the code reads it. Measured: replacing
    # the enum with a literal list left every other arm green.
    it 'follows the declaration when the declaration changes' do
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter
      invented = {
        'common' => {
          'glass' => {
            'description' => 'Liquid Glass. shape: hexagon|rounded(N)',
            'properties' => { 'shape' => { 'enum' => %w[hexagon] } }
          }
        }
      }
      allow(converter).to receive(:load_attribute_definitions).and_return(invented)
      converter.reset_declared_glass_shapes!

      # A spelling the real declaration defines is now undeclared...
      expect(capture_stdout { glass_line!('glass' => { 'shape' => 'capsule' }) })
        .to include('not declared')
      # ...and the invented one is accepted.
      expect(capture_stdout { glass_line!('glass' => { 'shape' => 'hexagon' }) })
        .not_to include('not declared')
    ensure
      RSpec::Mocks.space.proxy_for(converter).reset if defined?(converter)
      converter.reset_declared_glass_shapes!
    end

    # With no declared vocabulary the emitter cannot check anything, so every spelling
    # passes — correct, but it must not be silent. "Checked and fine" and "could not
    # check" have to be distinguishable, or a declaration that loses its enum turns the
    # validation off with nothing said.
    it 'says so when the declaration carries no vocabulary to check against' do
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter
      allow(converter).to receive(:load_attribute_definitions)
        .and_return('common' => { 'glass' => { 'description' => 'Liquid Glass.' } })
      converter.reset_declared_glass_shapes!

      output = capture_stdout { glass_line!('glass' => { 'shape' => 'hexagon' }) }
      expect(output).to include('were not checked')
      expect(output).to include('properties.shape.enum')
    ensure
      RSpec::Mocks.space.proxy_for(converter).reset if defined?(converter)
      converter.reset_declared_glass_shapes!
    end

    # The vocabulary is READ, never written here. If this file listed the spellings,
    # it would be a second list to keep in step — and the copy is what drifts: the
    # Swift library carried `rectangle`, which no declaration ever defined.
    it 'reads the vocabulary from the declaration, not from a list in the code' do
      definitions = File.expand_path('../../../lib/core/attribute_definitions.json', __dir__)
      declared = JSON.parse(File.read(definitions))
      glass = nil
      walk = lambda do |node|
        case node
        when Hash
          glass ||= node['glass'] if node.key?('glass')
          node.each_value { |v| walk.call(v) }
        when Array then node.each { |v| walk.call(v) }
        end
      end
      walk.call(declared)
      expect(glass.dig('properties', 'shape', 'enum')).to eq(%w[capsule circle rect])
      expect(glass['description'].to_s.downcase).to include('rounded(n)')
    end

    it 'emits interactive: false rather than dropping it' do
      # `false` is a value the author wrote, not an absence. The helper's own
      # default is what an ABSENT key means, and the two must stay
      # distinguishable in the generated source.
      expect(glass_line!('glass' => { 'interactive' => false }))
        .to eq('.sjuiGlassEffect(interactive: false)')
    end

    it 'routes tint through the colour helper, not as a raw string' do
      line = glass_line!('glass' => { 'tint' => '#FF0000' })
      expect(line).to include('tint: ')
      expect(line).not_to include('tint: "#FF0000"'), 'the hex reached Swift as a string literal'
      expect(line).to include('#FF0000')
    end

    it 'emits all four keys in a stable order' do
      line = glass_line!('glass' => { 'style' => 'regular', 'tint' => '#FF0000',
                                      'interactive' => true, 'shape' => 'capsule' })
      expect(line).to match(/\A\.sjuiGlassEffect\(style: .*, tint: .*, interactive: true, shape: .*\)\z/)
    end
  end

  describe 'what the generated code must NOT contain' do
    it 'never writes an availability check into the output' do
      %w[true regular].each do |_|
        out = emit('glass' => { 'style' => 'regular', 'shape' => 'capsule' })
        expect(out).not_to include('#available'),
                           'an availability check in generated code is duplicated per site ' \
                           'and asks the running OS, making the picture device-dependent'
        expect(out).not_to include('@available')
      end
    end

    it 'never writes the SwiftUI API directly' do
      out = emit('glass' => true)
      expect(out).not_to include('.glassEffect('),
                         'codegen must go through the library helper so the availability ' \
                         'check and the shape resolution live in one place'
      expect(out).not_to include('Glass.regular')
      expect(out).not_to include('UIGlassEffect')
    end

    it 'emits exactly one helper call per component' do
      out = emit('glass' => { 'style' => 'regular' })
      expect(out.scan('sjuiGlassEffect').size).to eq(1)
    end
  end

  describe 'the emitted call is Swift a compiler accepts' do
    # A string assert is not a compile. These hand the emitted modifier to
    # swiftc against the contract above, so an argument list that is merely
    # plausible fails here rather than in a consumer build.
    it 'the no-argument form type-checks' do
      expect(compilable_view("Color.clear\n#{glass_line!('glass' => true)}",
                             stubs: GLASS_HELPER_CONTRACT)).to compile_as_swift
    end

    it 'all four arguments type-check together' do
      line = glass_line!('glass' => { 'style' => 'regular', 'tint' => '#FF0000',
                                      'interactive' => true, 'shape' => 'capsule' })
      expect(compilable_view("Color.clear\n#{line}",
                             stubs: GLASS_HELPER_CONTRACT)).to compile_as_swift
    end

    it 'interactive: false type-checks (Bool?, not a truthy string)' do
      expect(compilable_view("Color.clear\n#{glass_line!('glass' => { 'interactive' => false })}",
                             stubs: GLASS_HELPER_CONTRACT)).to compile_as_swift
    end
  end

  describe 'where it sits among the other modifiers' do
    it 'comes after background and before cornerRadius' do
      # `.glassEffect` renders over whatever background is there and carries
      # its own shape, so it belongs between the background entries and the
      # clip. Asserted on the emitted order rather than on the constant, so a
      # reordering of MODIFIER_ORDER that changes the output fails here.
      out = emit('glass' => true, 'background' => '#00FF00', 'cornerRadius' => 8)
      bg    = out.index('.background(')
      glass = out.index('.sjuiGlassEffect(')
      clip  = out.index('.cornerRadius(')
      expect([bg, glass, clip]).to all(be_truthy)
      expect(bg).to be < glass
      expect(glass).to be < clip
    end

    it 'the slot exists in the declared order' do
      order = SjuiTools::SwiftUI::Views::ModifierBag::MODIFIER_ORDER
      expect(order).to include(:glass)
      expect(order.index(:gradient)).to be < order.index(:glass)
      expect(order.index(:glass)).to be < order.index(:corner_radius)
    end
  end
end
