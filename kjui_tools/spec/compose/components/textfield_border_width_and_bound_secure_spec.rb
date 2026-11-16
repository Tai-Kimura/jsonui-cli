# frozen_string_literal: true

require 'set'
require 'compose/components/textfield_component'
require_relative '../../support/kotlin_compiler'

# The outline's width reached nothing on Compose, written or bound: an outline was
# always Material's. A bound secure was left out of the call, so the text showed.
RSpec.describe 'kjui TextField: the outline width and a bound secure' do
  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  def emit(attrs, type = 'TextField')
    KjuiTools::Compose::Components::TextFieldComponent.generate({ 'type' => type, 'id' => 'f' }.merge(attrs), 0, Set.new)
  end

  it 'hands a written width to the field' do
    expect(emit('borderColor' => '#000000', 'borderWidth' => 3)).to include('borderWidth = 3.dp,')
    expect(emit('borderColor' => '#000000', 'borderWidth' => 1)).to include('borderWidth = 1.dp,')
  end

  it 'hands a bound width to the field' do
    code = emit('borderColor' => '#000000', 'borderWidth' => '@{w}')
    expect(code).to include('borderWidth = (data.w?.dp ?: 1.dp),')
    expect(code).not_to include('@{')
  end

  it 'writes no width for 0 or for none, and none when nothing is declared' do
    expect(emit('borderWidth' => 0)).to include('isOutlined = false,')
    expect(emit('borderWidth' => 0)).not_to include('borderWidth =')
    expect(emit('borderStyle' => 'none', 'borderWidth' => 3)).not_to include('borderWidth =')
    expect(emit({})).not_to include('borderWidth =')
  end

  it 'draws it on a TextView, which is the same field' do
    expect(emit({ 'borderColor' => '#000000', 'borderWidth' => 1 }, 'TextView')).to include('borderWidth = 1.dp,')
  end

  it 'follows the data with a bound secure' do
    code = emit('secure' => '@{v}')
    expect(code).to match(/isSecure = .*data\.v/)
    expect(code).not_to include('@{')
  end

  it 'keeps a written secure as it was' do
    expect(emit('secure' => true)).to include('isSecure = true,')
    expect(emit('secure' => false)).not_to include('isSecure')
    expect(emit({})).not_to include('isSecure')
  end

  it 'compiles what it writes' do
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = { 'w' => { 'class' => 'Int' }, 'v' => { 'class' => 'Boolean' } }
    args = emit('borderColor' => '#000000', 'borderWidth' => '@{w}', 'secure' => '@{v}')
           .lines.map(&:strip).select { |line| line.start_with?('borderWidth =', 'isSecure =') }
    expect(args.size).to eq(2)
    expect(<<~KOTLIN).to compile_as_kotlin
      class Dp
      val Int.dp: Dp get() = Dp()
      fun field(borderWidth: Dp? = null, isSecure: Boolean = false) {}
      class Data(val w: Int? = null, val v: Boolean? = null)
      fun draw(data: Data) = field(
        #{args.join("\n  ")}
      )
    KOTLIN
  ensure
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end
end
