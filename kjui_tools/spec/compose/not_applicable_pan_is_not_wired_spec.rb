# frozen_string_literal: true

require 'set'
require 'json'
require 'compose/helpers/modifier_builder'
require_relative '../support/kotlin_compiler'

# Ruling 2026-10-03: onPan is not delivered on a TextField (and its synonyms
# EditText / Input), a TextView or a Slider — the component's own drag takes
# the gesture — and the build says so in the words every face prints
# (`common.onPan.notApplicableTo`, attribute_validator_core.rb). A TextView's
# pan was wired by kjui and called on Android alone (runtime census on conf_ci:
# 33–34 calls on kjui codegen and KotlinJsonUI Dynamic, 0 on iOS and web); it
# is not wired now, so the faces agree.
#
# The emitter reads the declaration through the validator (one reader): the
# swap arm adds a type to the declaration and expects the emitter to follow,
# which a list spelled in the emitter could not do.
RSpec.describe 'kjui codegen: onPan is not wired where the SSoT declares it not applicable' do
  PAN_MB = KjuiTools::Compose::Helpers::ModifierBuilder

  def pan(type)
    PAN_MB.build_pannable({ 'type' => type, 'onPan' => '@{h}' }, Set.new)
  end

  after { PAN_MB.instance_variable_set(:@not_applicable_validator, nil) }

  it 'emits no pan on each type the declaration names, and on their synonyms' do
    declared = KjuiTools::Core::AttributeValidator.new(:compose).definitions.dig('common', 'onPan', 'notApplicableTo').keys
    expect(declared).to include('TextField', 'TextView', 'Slider')
    (declared + %w[EditText Input]).each { |type| expect(pan(type)).to eq([]), type }
  end

  it 'still emits the pan on a type the declaration does not name (control)' do
    %w[Label View Button Image].each { |type| expect(pan(type).join).to include('detectDragGestures'), type }
  end

  it 'the pan it still emits compiles (control)' do
    chain = pan('Label').join
    expect(<<~KT).to compile_as_kotlin
      interface Modifier { companion object : Modifier }
      data class Offset(val x: Float, val y: Float) {
          operator fun plus(o: Offset) = Offset(x + o.x, y + o.y)
          companion object { val Zero = Offset(0f, 0f) }
      }
      class PointerInputChange { fun consume() {} }
      class PointerInputScope {
          fun detectDragGestures(onDragStart: (Offset) -> Unit = {}, onDrag: (PointerInputChange, Offset) -> Unit) {}
      }
      fun Modifier.pointerInput(key1: Any?, block: PointerInputScope.() -> Unit): Modifier = this
      class Data(val h: (() -> Unit)? = null)
      fun host(data: Data): Modifier = Modifier
      #{chain}
    KT
  end

  it 'follows the declaration when it changes' do
    validator = KjuiTools::Core::AttributeValidator.new(:compose)
    swapped = JSON.parse(JSON.generate(validator.definitions))
    swapped['common']['onPan']['notApplicableTo'] = { 'Label' => 'swapped for the arm' }
    validator.instance_variable_set(:@definitions, swapped)
    PAN_MB.instance_variable_set(:@not_applicable_validator, validator)
    expect(pan('Label')).to eq([])
    expect(pan('TextView').join).to include('detectDragGestures')
  end
end
