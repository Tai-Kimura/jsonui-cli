# frozen_string_literal: true

require 'compose/helpers/resource_resolver'
require 'compose/helpers/binding_expression'

# Canonical `@{...}` parser + Kotlin emit (renderer SSoT 15, Phase 15-4).
# This helper is the single consolidation point for what used to be four
# duplicated "strip the ?? default" implementations.
RSpec.describe KjuiTools::Compose::Helpers::BindingExpression do
  after do
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  def with_definitions(defs)
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = defs
  end

  describe '.parse' do
    it 'parses a bare path' do
      p = described_class.parse('userName')
      expect(p.path).to eq('userName')
      expect(p.negated).to be false
      expect(p.has_default).to be false
    end

    it 'parses a double-quoted string default' do
      p = described_class.parse('userName ?? "Guest"')
      expect(p.path).to eq('userName')
      expect(p.default).to eq('Guest')
      expect(p.has_default).to be true
    end

    it 'parses a single-quoted string default (canonical-new spelling)' do
      p = described_class.parse("userName ?? 'Guest'")
      expect(p.default).to eq('Guest')
      expect(p.has_default).to be true
    end

    it 'parses defaults without surrounding whitespace' do
      p = described_class.parse('userName??"Guest"')
      expect(p.path).to eq('userName')
      expect(p.default).to eq('Guest')
    end

    it 'parses number and boolean defaults' do
      expect(described_class.parse('n ?? 42').default).to eq(42)
      expect(described_class.parse('r ?? 0.5').default).to eq(0.5)
      expect(described_class.parse('f ?? true').default).to eq(true)
      expect(described_class.parse('f ?? false').default).to eq(false)
    end

    it 'treats null default as no default (unresolved falls through)' do
      p = described_class.parse('x ?? null')
      expect(p.has_default).to be false
    end

    it 'fails closed on a second ?? (binding-double-default is a validator error)' do
      p = described_class.parse("a ?? 'x' ?? 'y'")
      expect(p.path).to eq('a')
      expect(p.has_default).to be false
    end

    it 'fails closed on an unquoted/invalid default literal' do
      p = described_class.parse('comment ?? ')
      expect(p.path).to eq('comment')
      expect(p.has_default).to be false
    end

    it 'parses negation' do
      p = described_class.parse('!isHidden')
      expect(p.negated).to be true
      expect(p.path).to eq('isHidden')
    end
  end

  describe '.interpolated_access (text context)' do
    it 'adds the canonical ?: "" fallback for nullable properties' do
      expect(described_class.interpolated_access('name')).to eq('"${data.name ?: ""}"')
    end

    it 'evaluates an authored ?? default on nullable properties' do
      expect(described_class.interpolated_access("name ?? 'Guest'")).to eq('"${data.name ?: "Guest"}"')
    end

    it 'emits plain access for non-null properties (data-section defaultValue merged first)' do
      with_definitions('name' => { 'name' => 'name', 'defaultValue' => 'X' })
      expect(described_class.interpolated_access('name')).to eq('"${data.name}"')
      expect(described_class.interpolated_access("name ?? 'Guest'")).to eq('"${data.name}"')
    end

    it 'emits a bare number default' do
      expect(described_class.interpolated_access('count ?? 42')).to eq('"${data.count ?: 42}"')
    end
  end

  describe '.value_access (typed value context)' do
    it 'emits plain access when no default is authored' do
      expect(described_class.value_access('url')).to eq('data.url')
    end

    it 'emits a parenthesized elvis for a nullable property with a default' do
      expect(described_class.value_access("url ?? 'x'")).to eq('(data.url ?: "x")')
      expect(described_class.value_access('count ?? 9')).to eq('(data.count ?: 9)')
    end

    it 'emits plain access for non-null properties even with an authored default (dead code)' do
      with_definitions('url' => { 'name' => 'url', 'defaultValue' => 'y' })
      expect(described_class.value_access("url ?? 'x'")).to eq('data.url')
    end

    context 'negatable (boolean value context)' do
      it 'emits a real Kotlin negation for non-null booleans' do
        with_definitions('isLogin' => { 'name' => 'isLogin', 'defaultValue' => false })
        expect(described_class.value_access('!isLogin', negatable: true)).to eq('!data.isLogin')
      end

      it 'coerces a bare nullable boolean before negating' do
        expect(described_class.value_access('!isLogin', negatable: true)).to eq('!(data.isLogin ?: false)')
      end

      it 'negates the defaulted access' do
        expect(described_class.value_access('!flag ?? true', negatable: true)).to eq('!(data.flag ?: true)')
      end

      it 'ignores negation when the context is not negatable (validator reports it)' do
        expect(described_class.value_access('!flag')).to eq('data.flag')
      end
    end
  end

  describe '.two_way_path' do
    it 'returns the flat path and strips invalid decorations tolerantly' do
      expect(described_class.two_way_path('text')).to eq('text')
      expect(described_class.two_way_path("text ?? 'x'")).to eq('text')
      expect(described_class.two_way_path('!flag')).to eq('flag')
    end
  end
end
