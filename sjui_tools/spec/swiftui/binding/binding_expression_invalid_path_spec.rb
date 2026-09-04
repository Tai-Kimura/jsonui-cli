# frozen_string_literal: true

require 'swiftui/binding/binding_expression'

# `@{ bad name }` compiled to `"\(data.bad name ?? "")"`, which swiftc
# rejects, from a build that exited 0 (measured 2026-09-04). The validator
# had already noticed — it reported 'bad' and 'name' as undefined variables
# — but the emitter wrote the file anyway. Whatever else it does, a
# generator must not write a file that cannot be parsed.
RSpec.describe SjuiTools::SwiftUI::Binding::BindingExpression do
  described = SjuiTools::SwiftUI::Binding::BindingExpression

  describe '.emittable_path?' do
    it 'accepts the shapes the grammar allows' do
      %w[title data user.name items[0] items[10].label _x9].each do |path|
        expect(described.emittable_path?(path)).to be(true), path
      end
    end

    it 'rejects anything that is not a path' do
      ['bad name', '', ' ', 'a b.c', 'x +', 'foo()', '1abc', 'a..b', 'a.'].each do |path|
        expect(described.emittable_path?(path)).to be(false), path.inspect
      end
    end
  end

  describe 'text context' do
    it 'refuses an invalid path instead of emitting it' do
      expect(described.swift_text_expr('bad name')).to be_nil
    end

    it 'still emits a valid path' do
      # Control: the refusal is about the path, not about the context.
      expect(described.swift_text_expr('title')).to eq('data.title ?? ""')
    end
  end

  describe 'value contexts' do
    it 'falls back to the author text as a literal' do
      expect(described.swift_value_expr('bad name')).to eq('"@{bad name}"')
    end

    it 'falls back to false in a boolean position' do
      # No literal fits every value position; a boolean one takes false.
      expect(described.swift_bool_expr('bad name')).to eq('false')
    end

    it 'still emits a valid path in both' do
      expect(described.swift_value_expr('flag')).to eq('data.flag')
      expect(described.swift_bool_expr('flag')).to eq('(data.flag ?? false)')
    end
  end

  describe 'the emitted Swift' do
    it 'has no bare space after data. for any rejected inner' do
      # The property that actually matters: whatever we emit, it must not
      # be `data.<two words>`.
      ['bad name', 'a b.c', 'x +'].each do |inner|
        [described.swift_value_expr(inner), described.swift_bool_expr(inner)].each do |emitted|
          expect(emitted).not_to match(/data\.\S*\s/), "#{inner.inspect} -> #{emitted}"
        end
      end
    end
  end
end
