# frozen_string_literal: true

require 'spec_helper'
require 'compose/helpers/bound_value'
require 'compose/helpers/modifier_builder'

# Plan 49 lane C. The two properties every one of these pins is defending:
#
#   1. a STATIC declaration emits exactly what it emitted before the guard
#      existed (the codegen-host tree diff proves it at 495-view scale; these
#      pin it at unit scale so a future edit fails here first);
#   2. a BOUND declaration emits Kotlin that compiles — the defect class 41
#      found was `@{v}.dp` in code position, `"@{v}"` passing Ruby truthiness,
#      and `"@{v}".to_f == 0.0` silently deleting a branch.
RSpec.describe KjuiTools::Compose::Helpers::BoundValue do
  described = KjuiTools::Compose::Helpers::BoundValue

  around do |example|
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
    example.run
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  def with_default_value(name, klass = 'Int')
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
      name => { 'name' => name, 'class' => klass, 'defaultValue' => '0' }
    }
    yield
  end

  describe '.dp' do
    it 'passes a numeric literal through untouched' do
      expect(described.dp(16)).to eq('16.dp')
      expect(described.dp(8.5)).to eq('8.5.dp')
      expect(described.dp('24')).to eq('24.dp')
    end

    it 'returns nil for an absent value so callers keep their emit-nothing branch' do
      expect(described.dp(nil)).to be_nil
      expect(described.dp('')).to be_nil
    end

    it 'coalesces a nullable bound property instead of dereferencing it' do
      # `data.gap.dp` does not compile when the generated property is `Int?`,
      # which is what DataModelUpdater emits without a defaultValue.
      expect(described.dp('@{gap}')).to eq('(data.gap?.dp ?: 0.dp)')
    end

    it 'dereferences directly when the data section gives the property a default' do
      with_default_value('gap') { expect(described.dp('@{gap}')).to eq('data.gap.dp') }
    end

    it 'evaluates an authored ?? default rather than passing it through' do
      # The old hand-rolled emit produced `data.gap ?? 10.dp` — `??` is not
      # Kotlin at all.
      expect(described.dp('@{gap ?? 10}')).to eq('(data.gap?.dp ?: 10.dp)')
    end

    it 'puts .dp INSIDE the elvis so Int and Double properties both resolve' do
      # `(data.x ?: 0).dp` would widen a `Double?` to `Comparable & Number`,
      # where `.dp` has no receiver.
      expect(described.dp('@{gap}')).to include('?.dp ?:').and include('.dp)')
    end
  end

  describe '.float' do
    it 'keeps the authored spelling for a static value' do
      # `1` must stay `1f`, not become `1.0f` — static output is byte-frozen.
      expect(described.float(1)).to eq('1f')
      expect(described.float(1.5)).to eq('1.5f')
    end

    it 'coalesces a nullable bound property' do
      expect(described.float('@{ratio}', fallback: 1)).to eq('(data.ratio?.toFloat() ?: 1.0f)')
    end
  end

  describe '.bool' do
    it 'reports the three static states' do
      expect(described.bool(true)).to eq(:on)
      expect(described.bool('true')).to eq(:on)
      expect(described.bool(false)).to eq(:off)
      expect(described.bool(nil)).to eq(:off)
    end

    it 'returns a runtime expression for a binding instead of freezing it ON' do
      # `"@{flag}"` is a non-empty String, so `if json_data['alignTop']` was
      # unconditionally true — 18 of the 41 findings were this exact shape.
      expect(described.bool('@{flag}')).to eq('(data.flag ?: false)')
    end

    it 'emits a real Kotlin negation for @{!flag}' do
      expect(described.bool('@{!flag}')).to eq('!(data.flag ?: false)')
    end
  end

  describe '.all_of' do
    it 'collapses to :off as soon as one conjunct is statically false' do
      expect(described.all_of(:on, :off, 'data.x')).to eq(:off)
    end

    it 'drops statically-true conjuncts from the runtime expression' do
      expect(described.all_of(:on, 'data.x')).to eq('data.x')
      expect(described.all_of('data.x', 'data.y')).to eq('(data.x && data.y)')
    end
  end

  describe '.text' do
    it 'quotes a literal' do
      expect(described.text('Hello')).to eq('"Hello"')
    end

    it 'interpolates a whole binding instead of leaking the characters @{...}' do
      expect(described.text('@{name}')).to eq('"${data.name ?: ""}"')
    end

    it 'interpolates a binding embedded in surrounding literal text' do
      expect(described.text('Hi @{name}!')).to eq('"Hi ${data.name ?: ""}!"')
    end
  end

  describe '.enum' do
    let(:mapping) { { 'center' => 'TextAlign.Center', 'left' => 'TextAlign.Start' } }

    it 'picks from the map for a static value' do
      expect(described.enum('center', mapping)).to eq('TextAlign.Center')
    end

    it 'emits nothing for a static value outside the vocabulary' do
      expect(described.enum('sideways', mapping)).to be_nil
    end

    it 'emits the whole map as a when so a binding is honoured at runtime' do
      result = described.enum('@{align}', mapping, bound_default: 'TextAlign.Unspecified')
      expect(result).to eq(
        'when (data.align ?: "") { "center" -> TextAlign.Center; ' \
        '"left" -> TextAlign.Start; else -> TextAlign.Unspecified }'
      )
    end

    it 'always closes the runtime when with an else — a when expression must be exhaustive' do
      expect(described.enum('@{align}', mapping, default: 'X')).to include('else -> X')
    end

    it 'drops the binding rather than emitting a non-exhaustive when' do
      # No usable else arm: a `when` expression without one does not compile,
      # and dropping the binding is the canonical unresolved-value behaviour.
      expect(described.enum('@{align}', mapping)).to be_nil
    end

    it 'folds case on both sides when the static path folded it' do
      # `toString()` first — the bound property need not be a String
      # (`fontWeight` accepts a number), and `Int.lowercase()` is a type error
      # the binding spelling cannot reveal.
      expect(described.enum('@{align}', mapping, bound_default: 'X', lowercase: true))
        .to include('data.align?.toString()?.lowercase()')
    end

    # Both halves of this have to hold at once: dropping the conversion
    # everywhere breaks the faces that bind a number, and keeping it
    # everywhere makes the compiler report a redundant conversion on the
    # faces that bind a String. The declared class is what decides, so
    # neither is a per-site judgement.
    it 'keeps the conversion when the data section declares a non-String' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'align' => { 'name' => 'align', 'class' => 'Int' }
      }
      expect(described.enum('@{align}', mapping, bound_default: 'X', lowercase: true))
        .to include('data.align?.toString()?.lowercase()')
    end

    it 'drops the conversion when the data section declares a String' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'align' => { 'name' => 'align', 'class' => 'String' }
      }
      result = described.enum('@{align}', mapping, bound_default: 'X', lowercase: true)
      expect(result).to include('data.align?.lowercase()')
      expect(result).not_to include('toString()')
    end

    it 'keeps the conversion for a path with no data definition' do
      # A dotted or bracketed path has no declaration to read, so it is not
      # known to be a String and must keep its conversion.
      expect(described.enum('@{item.align}', mapping, bound_default: 'X', lowercase: true))
        .to include('toString()')
    end

    # The subject is ONE decision, not a sequence of edits. Dropping the
    # conversion on its own left behind the safe call that existed only to
    # guard it, and the elvis that existed only to absorb its null — trading
    # one warning for another (measured downstream 2026-09-03). Every
    # declaration is pinned so a rule applied in isolation cannot pass.
    it 'emits a bare call chain for a non-null String' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'align' => { 'name' => 'align', 'class' => 'String', 'defaultValue' => 'regular' }
      }
      result = described.enum('@{align}', mapping, bound_default: 'X', lowercase: true)
      expect(result).to include('when (data.align.lowercase())')
      expect(result).not_to include('?.')
      expect(result).not_to include('toString()')
      expect(result).not_to include('?: ""')
    end

    it 'emits conversion without safe calls for a non-null non-String' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'align' => { 'name' => 'align', 'class' => 'Int', 'defaultValue' => 1 }
      }
      result = described.enum('@{align}', mapping, bound_default: 'X', lowercase: true)
      expect(result).to include('when (data.align.toString().lowercase())')
      expect(result).not_to include('?.')
    end

    it 'reads a class declared String? as a String, still safely called' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'align' => { 'name' => 'align', 'class' => 'String?', 'defaultValue' => 'x' }
      }
      result = described.enum('@{align}', mapping, bound_default: 'X', lowercase: true)
      expect(result).to include('data.align?.lowercase()')
      expect(result).not_to include('toString()')
    end
  end

  describe '.priority_modifier' do
    it 'resolves an all-static list in Ruby, emitting the winner verbatim' do
      result = described.priority_modifier([[:off, '.align(A)'], [:on, '.align(B)'], [:on, '.align(C)']])
      expect(result).to eq('.align(B)')
    end

    it 'emits nothing when no static guard holds' do
      expect(described.priority_modifier([[:off, '.align(A)']])).to be_nil
    end

    it 'becomes a when in the SAME priority order once one guard is dynamic' do
      result = described.priority_modifier([['data.x', '.align(A)'], [:on, '.align(B)']])
      expect(result).to eq('.then(when { data.x -> Modifier.align(A); else -> Modifier.align(B) })')
    end

    it 'falls back to a bare Modifier when the dynamic chain has no static tail' do
      result = described.priority_modifier([['data.x', '.align(A)'], [:off, '.align(B)']])
      expect(result).to eq('.then(when { data.x -> Modifier.align(A); else -> Modifier })')
    end
  end

  describe '.conditional_modifier' do
    it 'passes the fragment through when the flag is statically on' do
      expect(described.conditional_modifier(:on, '.clipToBounds()')).to eq('.clipToBounds()')
    end

    it 'emits nothing when the flag is statically off' do
      expect(described.conditional_modifier(:off, '.clipToBounds()')).to be_nil
    end

    it 'guards the fragment at runtime for a binding' do
      expect(described.conditional_modifier('data.c', '.clipToBounds()'))
        .to eq('.then(if (data.c) Modifier.clipToBounds() else Modifier)')
    end
  end
end

# Plan 49 lane C, #11a. The claim that "the validator rejects a `??` in these
# contexts anyway" did not survive being measured: `binding-two-way-complex`
# only fires for attributes DECLARED `binding_direction: "two-way"`, and of the
# 25 (component, attribute) pairs read by a hand-rolled regex, 9 are not. Eight
# of them emitted `data.x ?? y` — Kotlin has no `??` — with nothing reporting
# it. These pin the shape at the shared root; the per-component call sites are
# pinned in their own specs.
RSpec.describe 'binding contexts the validator does not guard' do
  let(:builder) { KjuiTools::Compose::Helpers::ModifierBuilder }

  around do |example|
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
    example.run
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe 'ModifierBuilder.boolean_expression — the shared root of the enabled family' do
    it 'evaluates an authored ?? default instead of splicing it in' do
      expect(builder.boolean_expression('@{on ?? true}')).to eq('(data.on ?: true)')
    end

    it 'coalesces a bare nullable read so the gate takes a Boolean' do
      expect(builder.boolean_expression('@{on}')).to eq('(data.on ?: false)')
    end

    it 'emits a real negation for @{!on}' do
      expect(builder.boolean_expression('@{!on}')).to eq('!(data.on ?: false)')
    end

    it 'keeps absent distinct from an explicit false' do
      # Absent means "no gate at all"; a declared false means "gate, shut".
      expect(builder.boolean_expression(nil)).to be_nil
      expect(builder.boolean_expression(false)).to eq('false')
      expect(builder.boolean_expression(true)).to be_nil
    end

    it 'never lets `??` reach the output' do
      %w[@{on} @{!on} @{on\ ??\ true} @{on\ ??\ false}].each do |v|
        expect(builder.boolean_expression(v.tr('\\', '')).to_s).not_to include('??')
      end
    end
  end

  describe 'path-only contexts (write-back keys, handler names)' do
    it 'strips an authored default from a property NAME' do
      # The name is a map key / a `data.<name>` receiver — a `??` inside it is
      # not part of the name.
      expect(KjuiTools::Compose::Helpers::BindingExpression.path_only('sel ?? "A"')).to eq('sel')
      expect(KjuiTools::Compose::Helpers::BindingExpression.path_only('!flag')).to eq('flag')
    end
  end
end
