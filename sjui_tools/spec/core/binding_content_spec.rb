#!/usr/bin/env ruby

# The delimiters were only ever half the check.
#
# `@{ bad name }` closes correctly, so the old check passed it, and each
# generator interpolated the CONTENT verbatim into its own language: the web
# build emitted `\${data.bad name}` and exited 0, iOS wrote
# `"\\(data.bad name ?? "")"` and Android `"\${data.bad name ?: ""}"`. None of
# the three parse. Measured 2026-09-04 on 1.8.36 and again on 1.8.37 with the
# same fixture on all three faces (docs/bugs/fixtures/binding-delimiter-arms).
#
# iOS and Android even NOTICED — both split the content on the space and
# reported two undefined variables — and wrote the broken code anyway. Web
# said nothing at all. The check below is the shared half: every face warns,
# by attribute, before anyone reads generated code.
#
# What is refused is only what cannot be an expression anywhere: two values
# with nothing between them. Operators are untouched, which is what real
# bindings use. Measured with THIS rule over a consumer's layouts: 1877 live
# bindings, 0 juxtaposed pairs, 4 with whitespace and all of them operator
# forms. (A first count said 1980, which had folded in 103 prose examples
# from strings.json — text the site renders to explain binding syntax, not
# bindings that run. Same answer, wrong denominator.)
require_relative '../../lib/core/attribute_validator'

RSpec.describe SjuiTools::Core::AttributeValidator do
  let(:validator) { described_class.new(:all) }

  def warnings_for(text)
    validator.validate({ 'type' => 'Label', 'width' => 'wrapContent',
                         'height' => 'wrapContent', 'text' => text })
  end

  it 'refuses two values with nothing between them' do
    warnings = warnings_for('@{ bad name }')
    expect(warnings.join("\n")).to include('not an expression')
    expect(warnings.join("\n")).to include('bad name')
  end

  it 'says so for an empty binding, which is emitted as literal text' do
    expect(warnings_for('@{}').join("\n")).to include('empty binding')
  end

  it 'leaves a plain property alone' do
    expect(warnings_for('@{title}')).to be_empty
  end

  it 'leaves a padded property alone — the generators trim it' do
    # Measured: `@{ title }` emits `\${data.title ?? ""}`, so it is not broken
    # and must not warn. Whitespace alone is not the defect.
    expect(warnings_for('@{ title }')).to be_empty
  end

  it 'leaves operator forms alone' do
    ['@{a ?? "x"}', '@{cond ? a : b}', '@{x + y}', '@{!flag}', '@{data.user.name}'].each do |expr|
      expect(warnings_for(expr)).to be_empty, "expected no warning for #{expr}"
    end
  end

  it 'still refuses an unclosed binding, by its own message' do
    expect(warnings_for('@{unclosed').join("\n")).to include("doesn't end with")
  end

  it 'offers the same judgment to the generators, so the two cannot disagree' do
    # A validator that warns while a converter still emits is how this
    # reached a release.
    expect(JsonUIShared::AttributeValidatorCore.binding_content_problem('bad name')).to eq(:juxtaposed)
    expect(JsonUIShared::AttributeValidatorCore.binding_content_problem('')).to eq(:empty)
    expect(JsonUIShared::AttributeValidatorCore.binding_content_problem('title')).to be_nil
  end
end
