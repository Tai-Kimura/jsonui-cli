# frozen_string_literal: true

require 'spec_helper'
require 'compose/helpers/tint_helper'

# Plan 49 lane C. `common.tintColor` is the accent a node hands DOWN — sjui
# emits `.tint(...)` and rjui the CSS `accentColor`, both of which propagate to
# descendants. Compose's peer is `LocalContentColor`, a CompositionLocal, so
# this is a wrapper rather than a modifier. The first attempt at this attribute
# was a `drawWithContent` scrim, which painted the node and its children flat;
# it was withdrawn, and these pins are what stop it coming back.
RSpec.describe KjuiTools::Compose::Helpers::TintHelper do
  described = KjuiTools::Compose::Helpers::TintHelper
  resolver = KjuiTools::Compose::Helpers::ResourceResolver

  let(:plain) { "Box(\n    modifier = Modifier\n        .width(100.dp)\n) {\n}" }
  let(:weighted) { "Box(\n    modifier = Modifier\n        .weight(1f)\n        .width(100.dp)\n) {\n}" }

  around do |example|
    resolver.data_definitions = {}
    example.run
    resolver.data_definitions = {}
  end

  it 'returns the code untouched when no tint is declared' do
    expect(described.wrap_with_tint({}, plain, 0, Set.new)).to eq(plain)
    expect(described.wrap_with_tint({ 'tintColor' => '' }, plain, 0, Set.new)).to eq(plain)
  end

  it 'provides the colour to descendants rather than painting the node' do
    out = described.wrap_with_tint({ 'tintColor' => '#FF0000' }, plain, 0, Set.new)
    expect(out).to start_with('CompositionLocalProvider(LocalContentColor provides ')
    expect(out).not_to include('drawWithContent')
    expect(out).not_to include('BlendMode')
  end

  it 'parenthesises the colour — `provides` is infix and `?:` binds looser' do
    # `provides X ?: Y` parses as `(provides X) ?: Y`, which hands the infix a
    # `Color?` and makes the whole expression a `ProvidedValue?`. It stopped
    # the host build once already.
    resolver.data_definitions = { 'tint' => { 'name' => 'tint', 'class' => 'String' } }
    out = described.wrap_with_tint({ 'tintColor' => '@{tint}' }, plain, 0, Set.new)
    expect(out).to include('provides (')
    expect(out.lines.first).to match(/provides \(.*\)\) \{$/)
  end

  it 'compiles for a String-typed and a Color-typed bound property alike' do
    # Emitting the property bare is what stopped the ios host on the same
    # fixture: the binding survived, so codegen-effect passed it, and the type
    # did not.
    { 'String' => 'ColorManager', 'Color' => 'Color.Unspecified' }.each do |klass, marker|
      resolver.data_definitions = { 'tint' => { 'name' => 'tint', 'class' => klass } }
      out = described.wrap_with_tint({ 'tintColor' => '@{tint}' }, plain, 0, Set.new)
      expect(out).to include(marker)
    end
  end

  describe 'scope-bound modifiers' do
    # CompositionLocalProvider adds no layout node, but its content lambda is
    # not a Row/Column/BoxScope receiver — a wrapped child loses `weight` and
    # `align`. They move onto a Box so the scope call stays in the scope.
    it 'hoists weight onto a Box and keeps the provider inside' do
      out = described.wrap_with_tint({ 'tintColor' => '#FF0000' }, weighted, 0, Set.new)
      expect(out).to start_with("Box(\n    modifier = Modifier\n        .weight(1f)")
      expect(out).to include('CompositionLocalProvider(')
      expect(out.index('Box(')).to be < out.index('CompositionLocalProvider(')
    end

    it 'strips the hoisted modifier from the inner chain so it is not applied twice' do
      out = described.wrap_with_tint({ 'tintColor' => '#FF0000' }, weighted, 0, Set.new)
      expect(out.scan('.weight(1f)').length).to eq(1)
    end

    it 'adds no Box when the node carries no scope-bound modifier' do
      out = described.wrap_with_tint({ 'tintColor' => '#FF0000' }, plain, 0, Set.new)
      expect(out).to start_with('CompositionLocalProvider(')
    end
  end
end
