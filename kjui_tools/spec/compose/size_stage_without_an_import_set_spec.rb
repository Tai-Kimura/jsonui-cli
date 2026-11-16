# frozen_string_literal: true

require 'set'
require 'compose/compose_builder'
require 'compose/helpers/modifier_builder'
require_relative '../support/kotlin_compiler'

# kjui-build-size-without-required-imports-emits-an-unimported-biasalignment:
# `ModifierBuilder.build_size(json_data, parent_type = nil, required_imports
# = nil)` is public, and an app converter written from the template before
# 2026-08-05 calls it with ONE argument. The size stage registered the import
# of what it emitted only through the set it was handed, so with none the
# names were emitted and their imports were not: `BiasAlignment` (a child a
# View container places, jsonui-cli 1.9.16) and `Dp.Infinity` (a bound
# maxWidth / maxHeight). The Android build then failed on a call the
# signature says is complete.
#
# The arm is a compile, not a string: the emit goes into a file whose import
# section is the one ComposeBuilder writes, against stubs that live in the
# names' own packages — so a name the file does not import does not resolve.
# Without its own package a stub would be found whether or not the emit
# imports it, and the arm could not tell the two apart (the last example
# shows that it does).
RSpec.describe 'kjui codegen: the size stage compiles when no import set is given' do
  MB = KjuiTools::Compose::Helpers::ModifierBuilder unless defined?(MB)

  # One node per name: a child its View container places, and a bound max.
  NODES = [
    { 'type' => 'View', 'width' => 300, 'height' => 300,
      KjuiTools::Compose::Helpers::ModifierBuilder::OVERFLOW_BIAS_KEY => [0.0, 1.0] },
    { 'type' => 'View', 'width' => 'matchParent', 'maxWidth' => '@{w}',
      'height' => 'matchParent', 'maxHeight' => '@{h}' }
  ].freeze

  # The stubs a probe's chain calls, in their own packages. Compose's types
  # where the chain passes them (BiasAlignment.Horizontal is an
  # Alignment.Horizontal), so an argument in the wrong place does not type-check.
  HAND_STUBS = {
    'androidx.compose.ui' => <<~KOTLIN,
      package androidx.compose.ui
      interface Modifier { companion object : Modifier }
      object Alignment { interface Horizontal; interface Vertical }
      class BiasAlignment(val horizontalBias: Float, val verticalBias: Float) {
          class Horizontal(val bias: Float) : Alignment.Horizontal
          class Vertical(val bias: Float) : Alignment.Vertical
      }
    KOTLIN
    'androidx.compose.ui.unit' => <<~KOTLIN,
      package androidx.compose.ui.unit
      class Dp(val value: Float) { companion object { val Infinity = Dp(Float.POSITIVE_INFINITY) } }
      val Int.dp: Dp get() = Dp(toFloat())
    KOTLIN
    'androidx.compose.foundation.layout' => <<~KOTLIN
      package androidx.compose.foundation.layout
      import androidx.compose.ui.Alignment
      import androidx.compose.ui.Modifier
      import androidx.compose.ui.unit.Dp
      fun Modifier.wrapContentWidth(align: Alignment.Horizontal, unbounded: Boolean = false): Modifier = this
      fun Modifier.wrapContentHeight(align: Alignment.Vertical, unbounded: Boolean = false): Modifier = this
      fun Modifier.requiredWidth(width: Dp): Modifier = this
      fun Modifier.requiredHeight(height: Dp): Modifier = this
      fun Modifier.widthIn(min: Dp = Dp(0f), max: Dp = Dp.Infinity): Modifier = this
      fun Modifier.heightIn(min: Dp = Dp(0f), max: Dp = Dp.Infinity): Modifier = this
      fun Modifier.fillMaxWidth(): Modifier = this
      fun Modifier.fillMaxHeight(): Modifier = this
    KOTLIN
  }.freeze
  HAND_NAMES = {
    'androidx.compose.ui' => %w[Modifier Alignment BiasAlignment],
    'androidx.compose.ui.unit' => %w[Dp dp]
  }.freeze

  # The file as ComposeBuilder writes it: its base imports plus what the set
  # registered, around a function whose chain is the emit.
  def probe(modifiers, import_set)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, import_set)
    builder.instance_variable_set(:@package_name, 'com.example.app')
    head = builder.send(:update_imports, "package com.example.app\n\nimport androidx.compose.ui.Modifier\n\n")
    "#{head}\nclass ProbeData(val w: Int?, val h: Int?)\n\n" \
      "fun probe(data: ProbeData): Modifier = Modifier\n#{modifiers.map { |m| "    #{m}" }.join("\n")}\n"
  end

  # Every other line of that import section resolves to a placeholder in its
  # package, so what can fail to resolve is only what the chain names.
  def stubs_for(source)
    files = HAND_STUBS.transform_keys { |pkg| "#{pkg}.kt" }
    source.scan(/^import ([\w.]+)\.(\w+|\*)$/).each_with_index do |(pkg, name), i|
      next if HAND_STUBS.key?(pkg) && (name == '*' || HAND_NAMES.fetch(pkg, []).include?(name))

      decl = name == '*' ? "class Placeholder#{i}" : (name.match?(/\A[A-Z]/) ? "class #{name}" : "val #{name} = 0")
      files["placeholder_#{i}.kt"] = "package #{pkg}\n#{decl}\n"
    end
    files
  end

  def emit(import_set) = NODES.flat_map { |node| MB.build_size(node.dup, nil, import_set) }

  it 'compiles when the caller passes no import set' do
    source = probe(NODES.flat_map { |node| MB.build_size(node.dup) }, Set.new)
    expect(source).to compile_as_kotlin.alongside(stubs_for(source))
  end

  it 'compiles with the set a built-in component passes (control: the stubs carry the chain)' do
    set = Set.new
    source = probe(emit(set), set)
    expect(source).to compile_as_kotlin.alongside(stubs_for(source))
  end

  it 'keeps the short names, and their imports, when a set is given' do
    set = Set.new
    out = emit(set)
    expect(out.join).to include('align = BiasAlignment.Horizontal(0.0f)', '?: Dp.Infinity)')
    expect(out.join).not_to include('androidx.')
    expect(set).to include(:bias_alignment, :dp_infinity)
  end

  # The arm's own control: the short names with their imports dropped must
  # NOT compile — otherwise a green above would not say the imports were found.
  it 'does not compile the short names without their imports (control: the arm can see a missing import)' do
    if (reason = KotlinCompiler.unavailable_reason)
      skip "compile_as_kotlin: #{reason}"
    end
    source = probe(emit(Set.new), Set.new)
    result = KotlinCompiler.compile(source, files: stubs_for(source))
    expect(result).not_to be_success
    expect(result.errors.join("\n")).to include("'BiasAlignment'").and include("'Dp'")
  end
end
