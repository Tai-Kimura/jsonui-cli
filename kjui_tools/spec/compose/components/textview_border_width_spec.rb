# frozen_string_literal: true

require 'set'
require 'compose/components/textview_component'
require_relative '../../support/kotlin_compiler'

# The outline's width did not reach a TextView on Compose, written or bound, while
# iOS and the web drew it. It draws through the same field as a TextField.
RSpec.describe 'kjui TextView: the outline width' do
  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end
  after { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  def emit(attrs)
    KjuiTools::Compose::Components::TextViewComponent.generate({ 'type' => 'TextView', 'id' => 'f' }.merge(attrs), 0, Set.new)
  end

  it 'writes a written width' do
    expect(emit('borderWidth' => 2, 'borderColor' => '#000000')).to include('borderWidth = 2.dp,')
  end

  it 'writes a width on the path with margins too' do
    code = emit('borderWidth' => 2, 'topMargin' => 4)
    expect(code).to include('CustomTextFieldWithMargins(')
    expect(code).to include('borderWidth = 2.dp,')
  end

  it 'writes a 0 as a width and keeps the outline on: the field draws no line' do
    code = emit('borderWidth' => 0)
    expect(code).to include('borderWidth = 0.dp,')
    expect(code).to include('isOutlined = true,')
  end

  it 'leaves an undeclared width out' do
    expect(emit('borderColor' => '#000000')).not_to include('borderWidth')
  end

  it 'compiles what it writes for a bound width' do
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = { 'w' => { 'class' => 'Int' } }
    args = emit('borderWidth' => '@{w}').lines.map(&:strip).select { |line| line.start_with?('borderWidth =') }
    expect(args.size).to eq(1)
    expect(<<~KOTLIN).to compile_as_kotlin
      class Dp
      val Int.dp: Dp get() = Dp()
      fun field(borderWidth: Dp? = null) {}
      class Data(val w: Int? = null)
      fun draw(data: Data) = field(
        #{args.join("\n  ")}
      )
    KOTLIN
  end
end
