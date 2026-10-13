# frozen_string_literal: true

require 'json'
require 'set'
require_relative '../../lib/compose/compose_builder'
require_relative '../support/kotlin_compiler'

# responsive minWidth:N / maxWidth:N (jui-responsive-width-threshold-conditions):
# the window width the size classes already read (LocalWindowInfo's
# containerSize in dp, truncated to Int), compared with N — maxWidth `< N`,
# minWidth `>= N` — in the if / else if chain build_branches orders.
#
# The run arm executes the emitted conditions, in the emitted order, with the
# width expression swapped for a parameter, at every width case of
# shared/core/responsive_resolution_vectors.json, and asks which branch runs.
RSpec.describe KjuiTools::Compose::ComposeBuilder, 'responsive width conditions' do
  let(:builder) do
    b = described_class.new
    b.instance_variable_set(:@required_imports, Set.new)
    b.instance_variable_set(:@included_views, Set.new)
    b.instance_variable_set(:@custom_components, Set.new)
    b.instance_variable_set(:@responsive_functions, [])
    b.instance_variable_set(:@responsive_counter, 0)
    b
  end
  let(:width_expr) { described_class::INLINE_WIDTH_DP_EXPR }
  let(:vectors) do
    JSON.parse(File.read(File.expand_path('../../../shared/core/responsive_resolution_vectors.json', __dir__)))
  end

  it 'emits maxWidth as `< N` and minWidth as `>= N` against the window width' do
    expect(builder.send(:build_embed_inline_condition, 'maxWidth:700')).to eq("#{width_expr} < 700")
    expect(builder.send(:build_embed_inline_condition, 'minWidth:700')).to eq("#{width_expr} >= 700")
  end

  it 'draws a View per width condition, most narrowing first, in an inline chain' do
    json = { 'type' => 'View', 'orientation' => 'vertical', 'spacing' => 8,
             'responsive' => { 'minWidth:600' => { 'spacing' => 16 }, 'maxWidth:400' => { 'spacing' => 4 },
                               'minWidth:900' => { 'spacing' => 24 } },
             'child' => [{ 'type' => 'Text', 'text' => 'x' }] }
    code = builder.send(:generate_component, json, 0, nil)
    order = ["if (#{width_expr} < 400) {", "} else if (#{width_expr} >= 900) {",
             "} else if (#{width_expr} >= 600) {", '} else {']
    positions = order.map { |line| code.index(line) }
    expect(positions).to all(be_a(Integer)), code
    expect(positions).to eq(positions.sort)
    expect(code).not_to include('>= 840')
  end

  it 'runs the emitted chain to the winner the shared vectors name, at every width case' do
    cases = vectors['cases'].select { |c| c['env'].key?('width') && c['env']['width'] == c['env']['width'].to_i }
    expect(cases.size).to be >= 15
    functions = cases.each_with_index.map do |c, i|
      component = { 'type' => 'View', 'responsive' => c['keys'].to_h { |k| [k, {}] } }
      chain = JsonUIShared::ResponsiveResolver.build_branches(component).map do |branch|
        next '"base"' if branch[:size_class].nil?

        condition = builder.send(:build_embed_inline_condition, branch[:size_class]).sub(width_expr, 'w')
        "if (#{condition}) \"#{branch[:size_class]}\" else"
      end.join(' ')
      "fun pick#{i}(w: Int): String = #{chain}"
    end
    calls = cases.each_with_index.map { |c, i| "    println(pick#{i}(#{c['env']['width'].to_i}))" }
    source = "#{functions.join("\n")}\nfun main() {\n#{calls.join("\n")}\n}\n"
    skip("kotlinc: #{KotlinCompiler.unavailable_reason}") if KotlinCompiler.unavailable_reason && ENV['KJUI_REQUIRE_KOTLINC'] != '1'
    run = KotlinCompiler.run(source)
    expect(run.errors).to eq([])
    expect(run.output.lines.map(&:strip)).to eq(cases.map { |c| c['winner'] || 'base' })
  end
end
