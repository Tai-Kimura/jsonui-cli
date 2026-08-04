# frozen_string_literal: true

require 'spec_helper'
require 'compose/helpers/bound_value'

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
