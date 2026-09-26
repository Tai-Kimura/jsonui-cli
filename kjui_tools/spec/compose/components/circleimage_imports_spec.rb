# frozen_string_literal: true

require 'set'
require 'compose/components/circleimage_component'
require 'compose/components/image_component'
require 'compose/helpers/import_manager'
require_relative '../../support/kotlin_compiler'

# Every name a CircleImage emit calls is imported by the keys it adds. The
# local branch added none of Image / painterResource / R, and the network
# branch's errorImage none of painterResource / R, so a screen whose only
# image was a local CircleImage did not compile. Measured: the 35 Image
# conformance layouts, drawn as CircleImage, built with `build_file` and
# compiled against Compose and KotlinJsonUI — every one failed on the three
# names; the other 1134 conformance layouts compiled clean of any missing
# import (jsonui-cli 1.9.0).
#
# The needed keys are read off the emit: each import line the ImportManager
# map holds names a symbol, and a symbol the emit calls must come in with
# one of the keys that import it.
RSpec.describe 'kjui CircleImage imports what it emits' do
  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  map = KjuiTools::Compose::Helpers::ImportManager.get_imports_map('com.example.app')
  providers = Hash.new { |h, k| h[k] = Set.new }
  map.each { |key, lines| Array(lines).each { |l| (s = l[/\.(\w+)\z/, 1]) && providers[s] << key } }
  watched = { 'Image' => /(?<![\w.])Image\(/, 'painterResource' => /(?<![\w.])painterResource\(/,
              'AsyncImage' => /(?<![\w.])AsyncImage\(/, 'R' => /(?<![\w.])R\.drawable\./ }

  missing = lambda do |klass, node|
    imports = Set.new
    code = klass.generate(node, 0, imports)
    watched.select { |_, pat| code.match?(pat) }.keys.reject { |sym| providers[sym].intersect?(imports) }
  end

  shapes = {
    'local' => { 'type' => 'CircleImage', 'id' => 'a', 'src' => 'avatar' },
    'local, contentMode' => { 'type' => 'CircleImage', 'id' => 'a', 'src' => 'avatar', 'contentMode' => 'top' },
    'network' => { 'type' => 'CircleImage', 'id' => 'a', 'url' => 'https://example.invalid/a.png' },
    'network, errorImage' => { 'type' => 'CircleImage', 'id' => 'a', 'url' => 'https://example.invalid/a.png',
                               'errorImage' => 'broken' }
  }

  shapes.each do |name, node|
    it "#{name}: imports every name it calls" do
      expect(missing.call(KjuiTools::Compose::Components::CircleImageComponent, node)).to eq([])
    end
  end

  # The emits, handed to a compiler against stubs with Compose's and coil's
  # parameter names (types only: the imports themselves are what the arms
  # above read; the whole-file compile was the measurement).
  it 'emits Kotlin that compiles, every shape' do
    body = shapes.values.each_with_index.map do |node, i|
      "fun emitted#{i}() {\n#{KjuiTools::Compose::Components::CircleImageComponent.generate(node, 0, Set.new)}\n}"
    end.join("\n")
    drawables = body.scan(/R\.drawable\.(\w+)/).flatten.uniq
    expect(<<~KOTLIN).to compile_as_kotlin
      interface Modifier { companion object : Modifier }
      class Dp(val value: Float)
      val Int.dp: Dp get() = Dp(toFloat())
      fun Modifier.testTag(tag: String): Modifier = this
      class SemanticsPropertyReceiver
      var SemanticsPropertyReceiver.testTagsAsResourceId: Boolean
          get() = false
          set(value) {}
      fun Modifier.semantics(mergeDescendants: Boolean = false, properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
      fun Modifier.size(size: Dp): Modifier = this
      interface Shape
      object CircleShape : Shape
      fun Modifier.clip(shape: Shape): Modifier = this
      class Painter
      fun painterResource(id: Int): Painter = Painter()
      object R { object drawable { #{drawables.map { |d| "const val #{d}: Int = 0" }.join('; ')} } }
      interface ContentScale { companion object { val Fit = object : ContentScale {}; val None = object : ContentScale {} } }
      interface Alignment { companion object { val Center = object : Alignment {}; val TopCenter = object : Alignment {} } }
      fun Image(painter: Painter, contentDescription: String?, modifier: Modifier = Modifier,
                alignment: Alignment = Alignment.Center, contentScale: ContentScale = ContentScale.Fit) {}
      fun AsyncImage(model: Any?, contentDescription: String?, modifier: Modifier = Modifier,
                     error: Painter? = null, alignment: Alignment = Alignment.Center,
                     contentScale: ContentScale = ContentScale.Fit) {}
      #{body}
    KOTLIN
  end

  it 'the check reads the emit: it sees what each shape calls, and Image passes it' do
    code = KjuiTools::Compose::Components::CircleImageComponent.generate(shapes['network, errorImage'], 0, Set.new)
    expect(watched.keys.select { |s| code.match?(watched[s]) }).to contain_exactly('AsyncImage', 'painterResource', 'R')
    expect(missing.call(KjuiTools::Compose::Components::ImageComponent,
                        { 'type' => 'Image', 'id' => 'a', 'srcName' => 'avatar' })).to eq([])
  end
end
