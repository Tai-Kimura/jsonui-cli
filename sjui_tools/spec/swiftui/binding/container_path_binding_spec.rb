# frozen_string_literal: true

require 'swiftui/binding/binding_expression'

# A binding path that reads THROUGH an untyped JSON container is not member
# access, and an inline default has to have the declared type of the property.
#
# Both emitted Swift that does not compile:
#
#     data.profile.name        // [String: Any] has no member 'name'
#     data.profile.meta.age    // nested, same
#     data.items[0].title      // 'Any' has no member 'title'
#     data.missing.name        // [String: Any]? has no member 'name'
#     data.label ?? 42         // cannot convert 'Int' to 'String'
#
# Neither is new. They became REACHABLE when the data model stopped emitting a
# Ruby Hash literal (a syntax error there meant type-checking never got as far
# as the view), and reachable only because the codegen host's staging predicate
# changed from a class filter to "does this fixture need a driver" — these five
# fixtures are `interactive` and had never been through a compiler.
#
# ⚠️ What decides the first case is the declared CLASS OF THE PATH ROOT, not
# the shape of the path. `a.b` is correct member access when `a` is a project
# model type and uncompilable when `a` is `Object`; the two are spelled
# identically in the layout. Reading the declaration is the only way to tell,
# which is why these examples set the definitions store rather than passing
# paths alone.
#
# The traversal is not reimplemented here. `DynamicBindingResolver` is
# documented as the ONE implementation of the canonical binding-resolution
# semantics, it is `public`, and it is unconditionally compiled, so the static
# face calls it: the bounds check (`items[99]` is unresolved, not a crash), the
# flat-key rule, AnyCodable unwrapping and the canonical text stringification
# (an integral Double renders "1", not "1.0") come with it instead of becoming
# a second copy to keep in step.
RSpec.describe 'binding paths through JSON containers' do
  BE = SjuiTools::SwiftUI::Binding::BindingExpression

  # Mirrors the real declarations verbatim (SwiftJsonUI
  # DynamicBindingResolver.swift:357/378/392). The swiftc arm type-checks the
  # emitted CALL SITE against these, so a call that names the wrong argument
  # label or coalesces against the wrong type fails here.
  RESOLVER_STUB = <<~SWIFT
    enum SwiftJsonUI {
        enum DynamicBindingResolver {
            static func resolveString(expression innerRaw: String, data: [String: Any]) -> String? { nil }
            static func resolveBool(expression innerRaw: String, data: [String: Any]) -> Bool? { nil }
            static func resolveDouble(expression innerRaw: String, data: [String: Any]) -> Double? { nil }
        }
    }
  SWIFT

  def define(defs)
    Thread.current[:sjui_data_definitions] = defs
  end

  after { Thread.current[:sjui_data_definitions] = nil }

  let(:containers) do
    {
      'profile' => { 'class' => 'Object',
                     'defaultValue' => { 'name' => 'Grace', 'meta' => { 'age' => 36 } } },
      'items' => { 'class' => 'Array', 'defaultValue' => [{ 'title' => 'First' }] },
      'missing' => { 'class' => 'Object' },
      'model' => { 'class' => 'MyProfileModel' },
      'label' => { 'class' => 'String' },
      'count' => { 'class' => 'Int' },
      'flag' => { 'class' => 'Bool' }
    }
  end

  it 'keeps the container class list in step with the type converter' do
    # The emitter carries its own copy: TypeConverter requires config_manager
    # and project_finder, and this module is kept free of anything that
    # touches the filesystem. That copy is only safe if a divergence fails
    # here — the converter decides the Swift TYPE, this list decides how the
    # path is READ, and a class in one but not the other is exactly the
    # combination that emits member access on a dictionary again.
    require 'core/type_converter'
    expect(BE::JSON_CONTAINER_CLASSES)
      .to eq(SjuiTools::Core::TypeConverter::JSON_CONTAINER_CLASSES)
  end

  describe 'which paths are a traversal' do
    before { define(containers) }

    it 'treats a path into a declared container as one' do
      expect(BE.container_traversal?('profile.name')).to be true
      expect(BE.container_traversal?('profile.meta.age')).to be true
      expect(BE.container_traversal?('items[0].title')).to be true
      expect(BE.container_traversal?('missing.name')).to be true
    end

    it 'leaves a bracket index on a declared array as one too' do
      # `data.items[0]` is `Any`, which cannot be coalesced or interpolated
      # usefully either — the defect does not need a trailing member.
      expect(BE.container_traversal?('items[0]')).to be true
    end

    it 'does NOT treat member access on a project model as one' do
      # Control, and the reason the class has to be read: identical shape,
      # correct Swift. Rerouting this would break every model-typed binding.
      expect(BE.container_traversal?('model.name')).to be false
    end

    it 'does NOT treat the container itself as one' do
      # Control: `@{profile}` names one declared property. Only reading
      # THROUGH it is the defect.
      expect(BE.container_traversal?('profile')).to be false
      expect(BE.container_traversal?('items')).to be false
    end

    it 'does NOT treat an undeclared root as one' do
      # Control. Nothing is known about it, so nothing is changed: it keeps
      # whatever the context did before.
      expect(BE.container_traversal?('unknown.name')).to be false
    end

    it 'is false with no definitions at all' do
      # Control for the store being absent (unit callers, early build).
      define({})
      expect(BE.container_traversal?('profile.name')).to be false
    end
  end

  describe 'the emitted text expression' do
    before { define(containers) }

    it 'resolves a container path through the canonical resolver' do
      expect(BE.swift_text_expr('profile.name')).to eq(
        'SwiftJsonUI.DynamicBindingResolver.resolveString(expression: "profile.name", ' \
        'data: ["profile": data.profile as Any]) ?? ""'
      )
    end

    it 'passes the whole nested path, not just the first hop' do
      expect(BE.swift_text_expr('profile.meta.age')).to include('expression: "profile.meta.age"')
    end

    it 'passes a bracket index through unchanged' do
      out = BE.swift_text_expr('items[0].title')
      expect(out).to include('expression: "items[0].title"')
      expect(out).to include('["items": data.items as Any]')
    end

    it 'hands the inline default to the resolver rather than coalescing twice' do
      # The resolver parses '??' itself, so the emitted trailing '?? ""' is
      # only the unresolved-and-no-default case. A second Swift coalesce of
      # the default here would apply it at the wrong precedence.
      out = BE.swift_text_expr('profile.name ?? "anon"')
      expect(out).to include('expression: "profile.name ?? \\"anon\\""')
      # Count the Swift coalesces OUTSIDE the expression literal — the
      # literal carries a '??' of its own, which is the point.
      outside = out.sub(/expression: "(?:[^"\\]|\\.)*"/, 'expression: <>')
      expect(outside.scan('??').length).to eq(1)
    end

    it 'keeps plain member access for a model-typed root' do
      # Control: the emission that was always right stays byte-identical.
      expect(BE.swift_text_expr('model.name')).to eq('data.model.name ?? ""')
    end
  end

  describe 'the inline default takes the declared type' do
    before { define(containers) }

    it 'quotes a number written against a String property' do
      expect(BE.swift_text_expr('label ?? 42')).to eq('data.label ?? "42"')
    end

    it 'quotes a bool written against a String property' do
      expect(BE.swift_text_expr('label ?? true')).to eq('data.label ?? "true"')
    end

    it 'leaves a matching literal alone' do
      # Controls: coercion fires on MISMATCH only.
      expect(BE.swift_text_expr('label ?? "x"')).to eq('data.label ?? "x"')
      expect(BE.swift_number_expr('count ?? 7')).to eq('data.count ?? 7')
    end

    it 'drops a default that cannot be repaired, for the context literal' do
      # A string against an Int property: nothing quotes it into place, so
      # the context's own literal is emitted rather than a coalesce whose
      # sides have different types.
      expect(BE.swift_bool_expr('flag ?? "yes"')).to eq('(data.flag ?? false)')
    end

    it 'leaves an unknown class alone' do
      # Control: nothing is declared about a model type's literals.
      expect(BE.swift_text_expr('model ?? 42')).to eq('data.model ?? 42')
    end
  end

  describe 'the other value contexts' do
    before { define(containers) }

    it 'uses the bool resolver in a bool context' do
      expect(BE.swift_bool_expr('profile.enabled')).to eq(
        '(SwiftJsonUI.DynamicBindingResolver.resolveBool(expression: "profile.enabled", ' \
        'data: ["profile": data.profile as Any]) ?? false)'
      )
    end

    it 'passes negation to the resolver, which is where it is canonical' do
      expect(BE.swift_bool_expr('!profile.enabled')).to include('expression: "!profile.enabled"')
    end

    it 'uses the double resolver in a numeric context' do
      expect(BE.swift_number_expr('profile.width')).to eq(
        'SwiftJsonUI.DynamicBindingResolver.resolveDouble(expression: "profile.width", ' \
        'data: ["profile": data.profile as Any]) ?? 0'
      )
    end

    it 'refuses a non-path in a numeric context instead of interpolating it' do
      # The other three contexts already refused; this one interpolated and
      # emitted Swift that does not compile.
      expect(BE.swift_number_expr('bad name')).to eq('0')
    end

    it 'passes an unresolved container path straight to VisibilityWrapper' do
      # It takes `String?` and Visibility(from:) maps nil to .visible, so no
      # fallback literal is invented here.
      expect(BE.swift_visibility_param('@{profile.state}')).to eq(
        'SwiftJsonUI.DynamicBindingResolver.resolveString(expression: "profile.state", ' \
        'data: ["profile": data.profile as Any])'
      )
    end

    it 'fails closed in the generic value context' do
      # KNOWN GAP, asserted so it is a decision rather than an oversight:
      # swift_value_expr feeds String positions (hint, colour hex, url) and
      # Bool ones (enabled) from one expression, so there is no resolver to
      # choose. It emits the literal token — the same fail-closed answer a
      # non-path already gets — instead of member access that cannot compile.
      expect(BE.swift_value_expr('profile.name')).to eq('"@{profile.name}"')
    end
  end

  describe 'the emitted Swift compiles', :swift_compile do
    # The gate the unit examples cannot be. Every failed candidate above
    # emitted *something*; only a compiler says whether the call site agrees
    # with the resolver's signatures and whether the coalesced types match.
    before { define(containers) }

    it 'type-checks every emitted form' do
      text_container  = BE.swift_text_expr('profile.meta.age')
      text_indexed    = BE.swift_text_expr('items[0].title')
      text_optional   = BE.swift_text_expr('missing.name')
      text_default    = BE.swift_text_expr('label ?? 42')
      bool_container  = BE.swift_bool_expr('profile.enabled')
      number_container = BE.swift_number_expr('profile.width')
      visibility      = BE.swift_visibility_param('@{profile.state}')

      expect(<<~SWIFT).to compile_as_swift
        #{RESOLVER_STUB}

        struct TestData {
            var profile: [String: Any] = ["name": "Grace", "meta": ["age": 36]]
            var items: [Any] = [["title": "First"]]
            var missing: [String: Any]? = nil
            var label: String? = nil
            var count: Int = 0
            var flag: Bool = false
        }

        func check(_ data: TestData) {
            let a: String = #{text_container}
            let b: String = #{text_indexed}
            let c: String = #{text_optional}
            let d: String = #{text_default}
            let e: Bool = #{bool_container}
            let f: Double = #{number_container}
            let g: String? = #{visibility}
            _ = (a, b, c, d, e, f, g)
        }
      SWIFT
    end

    it 'still type-checks the model-typed control' do
      # The path that was always correct has to stay correct: if the
      # container branch swallowed it, this is where that shows.
      define('model' => { 'class' => 'MyProfileModel' })
      expr = BE.swift_text_expr('model.name')

      expect(<<~SWIFT).to compile_as_swift
        struct MyProfileModel { var name: String? = nil }
        struct TestData { var model = MyProfileModel() }

        func check(_ data: TestData) {
            let a: String = #{expr}
            _ = a
        }
      SWIFT
    end
  end
end
