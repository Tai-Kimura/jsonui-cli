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
# ⚠️⚠️ The traversal is resolved by `JsonUIBindingPath` and NEVER by
# `DynamicBindingResolver`. Both are `public` and both carry the canonical
# semantics, but `DynamicBindingResolver` is inside `#if DEBUG`, and generated
# code is distributed and built for RELEASE. Emitting a reference to it
# compiles under DEBUG — so every gate goes green — and breaks in the
# consumer's release build. Measured 2026-09-05: the conformance host builds
# SwiftJsonUI with DEBUG undefined and failed five views with "Type
# 'SwiftJsonUI' has no member 'DynamicBindingResolver'", which is the same
# condition a consumer's release build is in. There is an explicit example
# below asserting the DEBUG-only spelling never appears.
RSpec.describe 'binding paths through JSON containers' do
  BE = SjuiTools::SwiftUI::Binding::BindingExpression

  # Mirrors the real declarations (SwiftJsonUI JsonUIBindingPath.swift). The
  # swiftc arm type-checks the emitted CALL SITE against these, so a call that
  # names a wrong label or coalesces against the wrong type fails here.
  RESOLVER_STUB = <<~SWIFT
    enum SwiftJsonUI {
        enum JsonUIBindingPath {
            static func resolve(path: String, in data: [String: Any],
                                unwrap: (Any?) -> Any? = { $0 }) -> Any? { nil }
            static func stringify(_ value: Any?) -> String? { nil }
            static func bool(_ value: Any?) -> Bool? { nil }
            static func double(_ value: Any?) -> Double? { nil }
        }
    }
  SWIFT

  def define(defs)
    Thread.current[:sjui_data_definitions] = defs
  end

  def resolve_call(path, coercion, root)
    'SwiftJsonUI.JsonUIBindingPath.' \
      "#{coercion}(SwiftJsonUI.JsonUIBindingPath.resolve(path: \"#{path}\", " \
      "in: [\"#{root}\": data.#{root} as Any]))"
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
      # usefully either — the defect does not need a trailing member. It is
      # also the case that COMPILED before this change while trapping at
      # runtime on an out-of-range index.
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

  describe 'the DEBUG-only resolver is never named' do
    before { define(containers) }

    # The regression this file exists to prevent a second time. Every context
    # that can emit a container read is checked, because one context left on
    # the old spelling produces generated code that passes every gate the
    # project runs and fails in the consumer's release build.
    it 'emits JsonUIBindingPath, never DynamicBindingResolver' do
      emitted = [
        BE.swift_text_expr('profile.name'),
        BE.swift_text_expr('profile.meta.age ?? "x"'),
        BE.swift_bool_expr('profile.enabled'),
        BE.swift_bool_expr('!profile.enabled'),
        BE.swift_number_expr('profile.width'),
        BE.swift_value_expr('profile.name'),
        BE.swift_value_expr('profile.enabled', kind: :bool),
        BE.swift_value_expr('profile.width', kind: :number),
        BE.swift_visibility_param('@{profile.state}'),
        BE.swift_visibility_param('@{!profile.hidden}')
      ]
      expect(emitted).to all(include('JsonUIBindingPath'))
      offenders = emitted.select { |e| e.include?('DynamicBindingResolver') }
      expect(offenders).to be_empty,
                           "these name the #if DEBUG type:\n#{offenders.join("\n")}"
    end
  end

  describe 'the emitted text expression' do
    before { define(containers) }

    it 'resolves a container path through the canonical resolver' do
      expect(BE.swift_text_expr('profile.name'))
        .to eq("(#{resolve_call('profile.name', 'stringify', 'profile')} ?? \"\")")
    end

    it 'passes the whole nested path, not just the first hop' do
      expect(BE.swift_text_expr('profile.meta.age')).to include('path: "profile.meta.age"')
    end

    it 'passes a bracket index through unchanged' do
      out = BE.swift_text_expr('items[0].title')
      expect(out).to include('path: "items[0].title"')
      expect(out).to include('["items": data.items as Any]')
    end

    it 'applies the inline default here, in canonical text form' do
      # The release-available core is resolution and coercion only — it has
      # no expression parser — so the default is emitted rather than passed
      # along. It still has to render the way a resolved value would.
      expect(BE.swift_text_expr('profile.name ?? "anon"')).to end_with('?? "anon")')
      expect(BE.swift_text_expr('profile.age ?? 42')).to end_with('?? "42")')
      expect(BE.swift_text_expr('profile.age ?? 42.0')).to end_with('?? "42")')
      expect(BE.swift_text_expr('profile.ok ?? true')).to end_with('?? "true")')
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

    it 'uses the bool coercion in a bool context' do
      expect(BE.swift_bool_expr('profile.enabled'))
        .to eq("(#{resolve_call('profile.enabled', 'bool', 'profile')} ?? false)")
    end

    it 'applies negation here, since the core coerces rather than parses' do
      expect(BE.swift_bool_expr('!profile.enabled'))
        .to eq("!(#{resolve_call('profile.enabled', 'bool', 'profile')} ?? false)")
    end

    it 'uses the double coercion in a numeric context' do
      expect(BE.swift_number_expr('profile.width'))
        .to eq("#{resolve_call('profile.width', 'double', 'profile')} ?? 0")
    end

    it 'refuses a non-path in a numeric context instead of interpolating it' do
      # The other three contexts already refused; this one interpolated and
      # emitted Swift that does not compile.
      expect(BE.swift_number_expr('bad name')).to eq('0')
    end

    it 'passes an unresolved container path straight to VisibilityWrapper' do
      # It takes `String?` and Visibility(from:) maps nil to .visible, so no
      # fallback literal is invented here.
      expect(BE.swift_visibility_param('@{profile.state}'))
        .to eq(resolve_call('profile.state', 'stringify', 'profile'))
    end

    it 'resolves a container path in the generic value context by kind' do
      # This position feeds String (hint, colour hex, url) and Bool
      # (`isEnabled:`) and numeric (relative positioning) alike, so the
      # caller names the type it is about to consume. Emitting the literal
      # token instead COMPILES, which is worse than failing: the view renders
      # "@{profile.name}" as its own text and every gate stays green.
      expect(BE.swift_value_expr('profile.name'))
        .to eq("(#{resolve_call('profile.name', 'stringify', 'profile')} ?? \"\")")
      expect(BE.swift_value_expr('profile.enabled', kind: :bool))
        .to eq("(#{resolve_call('profile.enabled', 'bool', 'profile')} ?? false)")
      expect(BE.swift_value_expr('profile.width', kind: :number))
        .to eq("(#{resolve_call('profile.width', 'double', 'profile')} ?? 0)")
    end

    it 'never leaves a raw @{ } token in a value position' do
      # The shape that looks green and is not: it compiles, and the literal
      # is rendered to the user.
      %i[string bool number].each do |kind|
        expect(BE.swift_value_expr('profile.name', kind: kind)).not_to include('@{')
      end
    end

    it 'still emits the literal for something that is not a path at all' do
      # Control: fail-closed is still right where no path exists.
      expect(BE.swift_value_expr('bad name')).to eq('"@{bad name}"')
    end
  end

  describe 'the emitted Swift compiles', :swift_compile do
    # The gate the unit examples cannot be. Every failed candidate above
    # emitted *something*; only a compiler says whether the call site agrees
    # with the resolver's signatures and whether the coalesced types match.
    before { define(containers) }

    it 'type-checks every emitted form' do
      exprs = {
        'String' => [
          BE.swift_text_expr('profile.meta.age'),
          BE.swift_text_expr('items[0].title'),
          BE.swift_text_expr('missing.name'),
          BE.swift_text_expr('label ?? 42'),
          BE.swift_text_expr('profile.age ?? 42'),
          BE.swift_value_expr('profile.name')
        ],
        'Bool' => [
          BE.swift_bool_expr('profile.enabled'),
          BE.swift_bool_expr('!profile.enabled'),
          BE.swift_value_expr('profile.enabled', kind: :bool)
        ],
        'Double' => [
          BE.swift_number_expr('profile.width'),
          BE.swift_value_expr('profile.width', kind: :number)
        ],
        'String?' => [BE.swift_visibility_param('@{profile.state}')]
      }
      n = 0
      body = exprs.flat_map do |type, list|
        list.map { |e| n += 1; "    let v#{n}: #{type} = #{e}" }
      end.join("\n")

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
        #{body}
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
