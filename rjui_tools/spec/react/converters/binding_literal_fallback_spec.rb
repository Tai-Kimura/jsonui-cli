#!/usr/bin/env ruby

# A binding that cannot be an expression must not reach the JavaScript.
#
# `@{ bad name }` produced `{`${data.bad name}`}` — a template expression
# JavaScript cannot parse — from a build that exited 0 and said nothing
# (measured 2026-09-04, 1.8.36 and 1.8.37). The validator now names it; this
# is the other half of the ruling: the generator falls back to the author's
# literal text, which is what an unclosed `@{…` has always done.
#
# The judgment comes from the shared predicate, not a second copy of the
# rule here: a validator that warns while a converter still emits is the
# shape that shipped.
require_relative '../../../lib/react/converters/label_converter'

RSpec.describe RjuiTools::React::Converters::LabelConverter do
  def emit(text)
    described_class.new({ 'class' => 'Label', 'width' => 'wrapContent',
                          'height' => 'wrapContent', 'text' => text },
                        { 'use_tailwind' => true }).convert(2)
  end

  it 'keeps a broken binding as literal text instead of writing invalid JS' do
    out = emit('@{ bad name }')
    expect(out).to include('@{ bad name }')
    expect(out).not_to include('${data.bad name}')
  end

  it 'still interpolates a usable binding' do
    # The control: the fallback must not swallow working bindings.
    expect(emit('@{title}')).to include('${data.title')
  end

  it 'still interpolates an operator form' do
    expect(emit('@{a ?? "x"}')).to include('${data.a')
  end

  it 'keeps the literal parts around a broken binding' do
    out = emit('before @{ bad name } after')
    expect(out).to include('before')
    expect(out).to include('after')
    expect(out).not_to include('${data.bad name}')
  end
end
