# frozen_string_literal: true

require 'ripper'
require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# The generator writes Kotlin, not the Ruby that should have computed it.
# CircleImage's background and border and Web's border put the Ruby call
# itself into the emit —
#
#     .background(Helpers::ResourceResolver.process_color('#3366CC', required_imports))
#
# — string text where `#{...}` was meant: it does not compile
# (docs/bugs/kjui-codegen-writes-ruby-expressions-into-kotlin.md). The family
# is read two ways that share nothing: the SOURCE, lexed (a Ruby-only token
# in a string literal's content, outside `#{}`), and the OUTPUT (the same
# tokens in what every declared type emits with every common stage).
RSpec.describe 'kjui codegen writes no Ruby expression into the Kotlin it emits' do
  lib = File.expand_path('../../lib', __dir__)
  ruby_only = /Helpers::|required_imports|\bjson_data\b|\bprocess_(?:color|text|dimension)\(/

  # String-literal content (Ripper's tstring_content — the text outside any
  # `#{}`) that holds a Ruby-only token, as "file:line: text".
  hits_in = lambda do |source, name|
    # `map { }.compact`, not `filter_map`: CI runs this suite on Ruby 2.6.
    Ripper.lex(source).map do |(line, _col), type, text, _state|
      "#{name}:#{line}: #{text.strip}" if type == :on_tstring_content && text.match?(ruby_only)
    end.compact
  end

  # This generator's product IS Ruby: it writes the converter classes a
  # project adds (`jui g converter`), so Ruby in its strings is the output.
  emits_ruby = { 'compose/generators/converter_generator.rb' => 'writes Ruby converter source' }

  it 'the lexer tells text from code (both sides of the boundary)' do
    code = %q(x = ".background(#{Helpers::ResourceResolver.process_color(c, required_imports)})")
    text = %q(x = ".background(Helpers::ResourceResolver.process_color('#{c}', required_imports))")
    expect(hits_in.call(code, 'code')).to be_empty
    expect(hits_in.call(text, 'text').size).to eq(2)
  end

  it 'no generator source writes a Ruby expression as text' do
    files = Dir.glob(File.join(lib, '**', '*.rb')).sort
    expect(files.size).to be > 100
    hits = files.flat_map do |path|
      rel = path.sub("#{lib}/", '')
      next [] if emits_ruby.key?(rel)

      hits_in.call(File.read(path), rel)
    end
    expect(hits).to be_empty, "Ruby written as Kotlin text:\n#{hits.join("\n")}"
  end

  # The exclusion still has a reason: that file does write Ruby.
  it 'the Ruby-emitting generator it leaves out still writes Ruby' do
    emits_ruby.each_key do |rel|
      expect(hits_in.call(File.read(File.join(lib, rel)), rel)).not_to be_empty
    end
  end

  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'p.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, comp, 0).to_s
  end

  every_stage = {
    'id' => 'n', 'margins' => [7, 7, 7, 7], 'width' => 111, 'height' => 53, 'offsetX' => 3, 'offsetY' => 3,
    'alpha' => 0.5, 'shadow' => '#000000|0|2|0.5|4', 'background' => '#3366CC', 'cornerRadius' => 6,
    'borderColor' => '#FF0000', 'borderWidth' => 2, 'onClick' => '@{onTap}', 'enabled' => false,
    'userInteractionEnabled' => false, 'paddings' => [5, 5, 5, 5]
  }

  # The population is what the codegen DRAWS, not what the SSoT declares:
  # CircleImage and WebView are dispatched and not declared, so a declared-
  # type sweep never emits them — the first run of this arm, on 24f7fad0,
  # found Web and missed CircleImage for exactly that reason. The dispatch is
  # read off generate_component's own `when` list; the declared types join it
  # so a declared type that is not drawn is still emitted (its TODO comment).
  it 'no type the codegen draws or the SSoT declares emits a Ruby expression, with every common stage declared' do
    builder = File.read(File.join(lib, 'compose', 'compose_builder.rb'))
    dispatch = builder[/def generate_component\(.*?\n      end\n/m]
                      .scan(/^\s*when ((?:'[A-Z]\w*'(?:,\s*)?)+)/).flatten.flat_map { |w| w.scan(/'(\w+)'/).flatten }
    defs = JSON.parse(File.read(File.expand_path('../../../shared/core/attribute_definitions.json', __dir__)))
    declared = (defs.keys - %w[common]).select { |k| defs[k].is_a?(Hash) && !k.start_with?('_', '$') }
    types = (dispatch | declared).sort
    expect(dispatch.size).to be >= 30
    expect(declared.size).to be >= 29
    expect(types).to include('CircleImage', 'WebView', 'Web')
    leaked = types.map do |type|
      code = emit.call({ 'type' => type }.merge(every_stage))
      "#{type}: #{code[ruby_only]}" if code.match?(ruby_only)
    end.compact
    expect(leaked).to be_empty
  end

  it 'CircleImage draws its border on the circle and its background, in Kotlin' do
    code = emit.call('type' => 'CircleImage', 'srcName' => 'a', 'background' => '#3366CC',
                     'borderColor' => '#FF0000', 'borderWidth' => 2, 'cornerRadius' => 6)
    expect(code).to include('.border(2.dp, Color(android.graphics.Color.parseColor("#FF0000")), CircleShape)')
    expect(code).to include('.background(Color(android.graphics.Color.parseColor("#3366CC")))')
  end

  it 'Web draws its border in the background slot, in Kotlin' do
    code = emit.call('type' => 'Web', 'url' => 'about:blank', 'borderColor' => '#FF0000', 'borderWidth' => 2,
                     'cornerRadius' => 6, 'onClick' => '@{onTap}', 'paddings' => [5, 5, 5, 5])
    border = code.index('.border(2.dp, Color(android.graphics.Color.parseColor("#FF0000")), RoundedCornerShape(6.dp))')
    expect(border).not_to be_nil, code
    expect(border).to be < code.index('.clickable')
    expect(border).to be < code.index('.padding(top = 5.dp')
  end

  # Each place, with its neighbours declared, type-checks (stubs:
  # ComposeStubUniverse.common_stages — "well-typed Kotlin", not "valid
  # Compose").
  it 'compiles the three places' do
    places = {
      'CircleImage background' => { 'type' => 'CircleImage', 'srcName' => 'a', 'background' => '#3366CC' },
      'CircleImage border' => { 'type' => 'CircleImage', 'srcName' => 'a', 'borderColor' => '#FF0000',
                                'borderWidth' => 2, 'cornerRadius' => 6 },
      'Web border' => { 'type' => 'Web', 'url' => 'about:blank', 'borderColor' => '#FF0000', 'borderWidth' => 2 },
      'Web border, rounded' => { 'type' => 'Web', 'url' => 'about:blank', 'borderColor' => '#FF0000',
                                 'borderWidth' => 2, 'cornerRadius' => 6 }
    }
    emitted = places.map.with_index do |(label, node), i|
      "// #{label}\nfun place#{i}(data: Data, viewModel: ViewModel) {\n#{emit.call(node)}\n}"
    end.join("\n\n")
    expect(emitted).to include('CircleShape)', 'RectangleShape)')
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data
      class ViewModel
      #{emitted}
    KOTLIN
  end
end
