# frozen_string_literal: true

require 'compose/compose_builder'
require 'json'
require_relative '../support/kotlin_compiler'

# The disabled colours follow `enabled` whether it is written or bound (ticket
# 2026-10-23-bound-enabled-disabled-colors-three-faces). Compose drew no
# View's disabledBackground at all, and a Text's disabledFontColor only for a
# literal `enabled: false`. Now the emit chooses by the binding —
# `if (<enabled>) <base> else <disabled>` — and a literal false takes the
# disabled colour alone, as iOS and the web draw it.
#
# The drawn arm is DisabledColoursProbeTest in KotlinJsonUI's conformance-host
# (the emission pasted, the pixels read with `enabled` true and false); this
# one keeps the direction of the choice in jsonui-cli's own gate.
module BoundEnabledComposeColours
  def blue = 'Color(android.graphics.Color.parseColor("#0000FF"))'
  def grey = 'Color(android.graphics.Color.parseColor("#999999"))'
  def ink = 'Color(android.graphics.Color.parseColor("#123456"))'
  def dim = 'Color(android.graphics.Color.parseColor("#555555"))'
  def on_ = '(data.on ?: false)'
end

RSpec.describe 'kjui disabled colours follow a bound enabled' do
  include BoundEnabledComposeColours

  def emit(node)
    KjuiTools::Compose::Components::TextComponent.reset_counter!
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, JSON.parse(JSON.generate(node)), 0)
  end

  def view(extra)
    emit({ 'type' => 'View', 'id' => 'v', 'width' => 60, 'height' => 40, 'disabledBackground' => '#999999' }.merge(extra))
  end

  def text(extra)
    emit({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'disabledFontColor' => '#555555' }.merge(extra))
  end

  def background(code) = code[/^\s*\.background\((.*)\)$/, 1]
  def font_colour(code) = code[/^\s*color = (.*),$/, 1]

  describe 'a View' do
    it 'a bound enabled: the base while true, disabledBackground while false (fixed and bound base)' do
      expect(background(view('background' => '#0000FF', 'enabled' => '@{on}'))).to eq("if (#{on_}) #{blue} else #{grey}")
      expect(background(view('background' => '@{bg}', 'enabled' => '@{on}'))).to eq("if (#{on_}) data.bg ?: Color.Unspecified else #{grey}")
    end

    it 'no base background: disabledBackground while false, transparent while true' do
      expect(background(view('enabled' => '@{on}'))).to eq("if (#{on_}) Color.Transparent else #{grey}")
    end

    it 'a literal false: disabledBackground alone, never the base' do
      code = view('background' => '#0000FF', 'enabled' => false)
      expect(background(code)).to eq(grey)
      expect(code).not_to include('#0000FF')
    end

    it 'no enabled: the base alone, no choice' do
      code = view('background' => '#0000FF')
      expect(background(code)).to eq(blue)
      expect(code).not_to include('#999999')
    end
  end

  describe 'a Text' do
    it 'a bound enabled: fontColor while true, disabledFontColor while false' do
      expect(font_colour(text('fontColor' => '#123456', 'enabled' => '@{on}'))).to eq("if (#{on_}) #{ink} else #{dim}")
    end

    it 'a literal false: disabledFontColor alone, never the base' do
      code = text('fontColor' => '#123456', 'enabled' => false)
      expect(font_colour(code)).to eq(dim)
      expect(code).not_to include('#123456')
    end
  end

  # The chosen colours type-check as Compose takes them (a Color, where the
  # base may be a bound nullable one). ⚠️ Against stubs: Color and
  # android.graphics.Color are declared here, types only.
  it 'the chosen colours compile' do
    exprs = [
      background(view('background' => '#0000FF', 'enabled' => '@{on}')),
      background(view('background' => '@{bg}', 'enabled' => '@{on}')),
      background(view('enabled' => '@{on}')),
      background(view('background' => '#0000FF', 'enabled' => false)),
      font_colour(text('fontColor' => '#123456', 'enabled' => '@{on}')),
      font_colour(text('fontColor' => '@{fg}', 'enabled' => '@{on}'))
    ]
    expect(exprs).to all(be_a(String))
    expect(<<~KOTLIN).to compile_as_kotlin
      class Color(val argb: Int = 0) { companion object { val Unspecified = Color(); val Transparent = Color() } }
      object android { object graphics { object Color { fun parseColor(hex: String): Int = 0 } } }
      class Data(val on: Boolean? = null, val bg: Color? = null, val fg: Color? = null)
      #{exprs.each_with_index.map { |e, i| "fun colour#{i}(data: Data): Color = #{e}" }.join("\n")}
    KOTLIN
  end
end
