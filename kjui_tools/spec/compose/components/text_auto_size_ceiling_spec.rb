# frozen_string_literal: true

require 'set'
require 'compose/compose_builder'
require 'compose/components/text_component'
require_relative '../../support/kotlin_compiler'

# kjui-minimum-scale-factor-grows-text-past-its-font-size: `minimumScaleFactor`
# / `autoShrink` emitted TextAutoSize.StepBased(minFontSize = …) with no
# maxFontSize, so StepBased took its default 112.sp and a short Label grew to
# fill its box (seen on a device; KotlinJsonUI Dynamic, which had the same
# emit, measured a first glyph 160px wide beside 17px at 12sp). iOS's
# .minimumScaleFactor only shrinks: fontSize is the ceiling.
RSpec.describe 'kjui Label auto-size: fontSize is the ceiling' do
  def auto_size(node)
    KjuiTools::Compose::Components::TextComponent
      .generate({ 'type' => 'Label', 'id' => 'l', 'text' => 'Hi' }.merge(node), 0, Set.new)
      .lines.grep(/autoSize =/).map { |l| l.strip.chomp(',') }.first
  end

  it 'passes fontSize as maxFontSize, the factor of it as minFontSize' do
    # Through 1.9.5: autoSize = TextAutoSize.StepBased(minFontSize = 7.2.sp),
    expect(auto_size('fontSize' => 12, 'minimumScaleFactor' => 0.6))
      .to eq('autoSize = TextAutoSize.StepBased(minFontSize = 7.2.sp, maxFontSize = 12.0.sp)')
    expect(auto_size('autoShrink' => true))
      .to eq('autoSize = TextAutoSize.StepBased(minFontSize = 7.0.sp, maxFontSize = 14.0.sp)')
  end

  it 'passes a bound fontSize as both bounds' do
    expect(auto_size('fontSize' => '@{fs}', 'minimumScaleFactor' => 0.5)).to include('maxFontSize = ((data.fs?.toFloat() ?: 14.0f) * 1f).sp')
  end

  it 'emits no autoSize without minimumScaleFactor or autoShrink (control)' do
    expect(auto_size('fontSize' => 12)).to be_nil
  end

  it 'compiles against StepBased' do
    lines = [auto_size('fontSize' => 12, 'minimumScaleFactor' => 0.6), auto_size('fontSize' => '@{fs}', 'minimumScaleFactor' => 0.5)]
    expect(<<~KT).to compile_as_kotlin
      class TextUnit
      val Double.sp: TextUnit get() = TextUnit()
      val Float.sp: TextUnit get() = TextUnit()
      interface TextAutoSize { companion object { fun StepBased(minFontSize: TextUnit, maxFontSize: TextUnit): TextAutoSize = object : TextAutoSize {} } }
      class Data(val fs: Int? = null)
      fun Text(autoSize: TextAutoSize? = null) {}
      fun host(data: Data) {
          Text(
              #{lines[0]}
          )
          Text(
              #{lines[1]}
          )
      }
    KT
  end
end
