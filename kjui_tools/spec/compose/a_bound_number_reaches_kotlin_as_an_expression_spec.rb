# frozen_string_literal: true

require 'json'
require 'set'
require 'compose/compose_builder'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/bound_value'
require_relative '../support/kotlin_compiler'

# A binding on a value the shadow's Kotlin spells out. `radius` pasted it —
# `Shadow(radius = @{x}.dp)` does not compile — and the offsets and the opacity
# cast it, so a bound shadow drew at offset 0 and alpha 0 with no word from the
# build. The sweep is over the attribute table, so a new attribute or component
# is in it the day it is declared.
RSpec.describe 'a bound number reaches Kotlin as an expression' do
  DEFS = JSON.parse(File.read(File.expand_path('../../../shared/core/attribute_definitions.json', __dir__)))
  BOUND = '@{v}'
  NOT_VALUES = %w[_comment $jui id type style include data child children binding bindingScript partial variables
                  shared_data sectionHeader cellClasses headerClasses footerClasses sections].freeze

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  def shadow(value)
    KjuiTools::Compose::Helpers::ModifierBuilder.build_shadow({ 'shadow' => value }, Set.new, shape: 'RectangleShape').join
  end

  def unreadable(code)
    code.lines.map(&:strip).reject { |line| line.start_with?('//') }
        .select { |line| line.gsub(/"(?:[^"\\]|\\.)*"/, '""').include?('@{') }
  end

  def self.cases
    common = DEFS['common'].reject { |name, _| name.start_with?('_') }
    DEFS.flat_map do |type, own|
      next [] if %w[_comment common].include?(type) || !own.is_a?(Hash)

      common.merge(own).flat_map do |attr, definition|
        next [] if NOT_VALUES.include?(attr) || !definition.is_a?(Hash) || attr.start_with?('_')

        values = [BOUND]
        values += [[BOUND, BOUND], [BOUND, BOUND, BOUND, BOUND]] if Array(definition['type']).flatten.include?('array')
        (definition['properties'] || {}).each_key { |prop| values << { prop => BOUND, 'color' => '#000000' } }
        values.map { |value| [type, attr, value] }
      end
    end
  end

  it 'never writes a binding where Kotlin reads code, on any declared attribute of any type' do
    allow(KjuiTools::Core::Logger).to receive(:warn)
    builder = KjuiTools::Compose::ComposeBuilder.new
    leaks = self.class.cases.flat_map do |type, attr, value|
      code = begin
        builder.send(:generate_component, { 'type' => type, 'id' => 'p', attr => value }, 0).to_s
      rescue NoMethodError, TypeError
        ''
      end
      unreadable(code).map { |line| "#{type}.#{attr} #{value.inspect}: #{line}" }
    end
    expect(leaks).to eq([]), leaks.uniq.first(40).join("\n")
  end

  it 'draws a bound radius, offset and opacity from the data' do
    expect(shadow('radius' => BOUND)).to include('radius = data.v?.dp ?: 0.dp').or include('radius = (data.v')
    expect(shadow('radius' => 3, 'offsetX' => BOUND)).to match(/offset = DpOffset\(.*data\.v.*\.dp.*, 0\.0\.dp\)/)
    expect(shadow('radius' => 3, 'offsetY' => BOUND)).to match(/offset = DpOffset\(0\.0\.dp, .*data\.v/)
    expect(shadow('radius' => 3, 'opacity' => BOUND)).to include('alpha = (data.v?.toFloat() ?: 1.0f)')
  end

  it 'keeps the bytes of a written shadow' do
    expect(shadow('radius' => 3, 'offsetX' => 1, 'offsetY' => 2, 'opacity' => 0.4))
      .to eq('.dropShadow(shape = RectangleShape, shadow = Shadow(radius = 3.dp, offset = DpOffset(1.0.dp, 2.0.dp), alpha = 0.4f))')
    expect(shadow({})).to include('radius = 4.dp')
  end

  it 'says nextFocus and screen do not take a binding, and pastes them nowhere' do
    expect(KjuiTools::Core::Logger).to receive(:warn).with(/'nextFocus' .*does not take a binding/).at_least(:once)
    expect(KjuiTools::Core::Logger).to receive(:warn).with(/'screen' .*does not take a binding/).at_least(:once)
    builder = KjuiTools::Compose::ComposeBuilder.new
    expect(builder.send(:generate_component, { 'type' => 'TextField', 'id' => 'p', 'nextFocus' => BOUND }, 0)).not_to include('@{')
    expect(builder.send(:generate_component, { 'type' => 'Embed', 'id' => 'p', 'screen' => BOUND }, 0)).not_to include('@{')
  end

  it 'writes bound gradient stops as the data, written ones as they were' do
    builder = KjuiTools::Compose::ComposeBuilder.new
    node = { 'type' => 'GradientView', 'id' => 'p', 'gradient' => ['#000000', '#FFFFFF'] }
    expect(builder.send(:generate_component, node.merge('locations' => [BOUND, 1]), 0)).to match(/data\.v.*toFloat.* to .*1f to /m)
    expect(builder.send(:generate_component, node.merge('locations' => [0, 1]), 0)).to match(/0f to .*1f to /m)
  end

  it 'writes a bound padding on a SelectBox as its content padding' do
    builder = KjuiTools::Compose::ComposeBuilder.new
    expect(builder.send(:generate_component, { 'type' => 'SelectBox', 'id' => 'p', 'padding' => BOUND }, 0))
      .to match(/contentPadding = PaddingValues\(.*data\.v/)
    expect(builder.send(:generate_component, { 'type' => 'SelectBox', 'id' => 'p', 'padding' => 4 }, 0))
      .to include('contentPadding = PaddingValues(4.dp)')
  end

  STUBS = <<~KOTLIN
    class Dp
    val Int.dp: Dp get() = Dp()
    val Float.dp: Dp get() = Dp()
    val Double.dp: Dp get() = Dp()
    class DpOffset(val x: Dp, val y: Dp)
    class Shadow(val radius: Dp, val offset: DpOffset? = null, val alpha: Float = 1f)
    object RectangleShape
    class Modifier { fun dropShadow(shape: Any, shadow: Shadow): Modifier = this }
  KOTLIN

  { 'Int' => 'val v: Int = 1', 'Double' => 'val v: Double = 1.0', 'Float?' => 'val v: Float? = null', 'Int?' => 'val v: Int? = null' }.each do |name, property|
    it "compiles the shadow with the property declared #{name}" do
      type = name.delete('?')
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions =
        { 'v' => { 'class' => type }.merge(name.end_with?('?') ? {} : { 'defaultValue' => 1 }) }
      chain = shadow('radius' => BOUND, 'offsetX' => BOUND, 'offsetY' => BOUND, 'opacity' => BOUND)
      expect(<<~KOTLIN).to compile_as_kotlin
        #{STUBS}
        class Data(#{property})
        fun draw(data: Data, modifier: Modifier): Modifier = modifier#{chain}
      KOTLIN
    ensure
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
    end
  end
end
