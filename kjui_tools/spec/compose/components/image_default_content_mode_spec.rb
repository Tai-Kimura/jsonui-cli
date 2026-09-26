# frozen_string_literal: true

require 'json'
require 'compose/components/image_component'
require 'compose/components/networkimage_component'
require 'compose/components/circleimage_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

# An image with no contentMode draws the declared default. The default is
# declared once, in shared/core/attribute_semantics.json
# (`semantics.image.defaultContentMode`, the 2026-08-03 user ruling), and
# every path's no-contentMode drawing is bound to it here: the value is read
# from the file, so a changed ruling moves the expectation (4f ruling,
# 2026-09-26; ticket image-content-mode-default-differs-by-path).
#
# The no-contentMode emit passes no contentScale, so the library's own
# default draws: ContentScale.Fit for Compose's Image(painter) and for coil's
# AsyncImage — measured in the bytecode KotlinJsonUI resolves
# (foundation-android 1.12.1 ImageKt; coil-compose-android 3.5.0
# SingletonAsyncImageKt: `ContentScale$Companion.getFit()` on the default
# path). That constant is the one thing here not read from the SSoT.
RSpec.describe 'kjui Compose codegen: an image with no contentMode' do
  shared_core = File.expand_path('../../../../shared/core', __dir__)
  declared = JSON.parse(File.read(File.join(shared_core, 'attribute_semantics.json'), encoding: 'UTF-8'))
                 .fetch('semantics').fetch('image').fetch('defaultContentMode')
  library_default = 'ContentScale.Fit'

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  components = {
    'Image' => KjuiTools::Compose::Components::ImageComponent,
    'NetworkImage' => KjuiTools::Compose::Components::NetworkImageComponent,
    'CircleImage' => KjuiTools::Compose::Components::CircleImageComponent
  }

  define_method(:scale_drawn) do |type, mode, extra = {}|
    node = { 'type' => type, 'id' => 'img', 'width' => 100, 'height' => 60 }.merge(extra)
    node[type == 'NetworkImage' ? 'url' : 'src'] ||= (type == 'NetworkImage' ? 'https://example.invalid/a.png' : 'probe_asset')
    node['contentMode'] = mode if mode
    code = components.fetch(type).generate(node, 0, Set.new)
    code[/contentScale = (ContentScale\.\w+)/, 1] || library_default
  end

  it "draws Image, NetworkImage and CircleImage with the scale the declared default (#{declared}) draws" do
    components.each_key do |type|
      expect(scale_drawn(type, nil)).to eq(scale_drawn(type, declared)), type
    end
    # A network CircleImage (AsyncImage) too.
    net = { 'url' => 'https://example.invalid/a.png' }
    expect(scale_drawn('CircleImage', nil, net)).to eq(scale_drawn('CircleImage', declared, net))
  end

  # CircleImage is an Image spelling (type_synonyms.json render_as) and
  # follows its contentMode (4f ruling, 2026-09-26); it drew Crop whatever
  # the mode was.
  it 'draws CircleImage with the scale Image draws, mode for mode' do
    [nil, declared, 'AspectFill', 'fill', 'center', 'top'].each do |mode|
      expect(scale_drawn('CircleImage', mode)).to eq(scale_drawn('Image', mode)), mode.inspect
    end
  end

  it 'draws another scale for another mode — the comparison can tell them apart' do
    other = declared.casecmp?('AspectFill') ? 'fit' : 'AspectFill'
    components.each_key do |type|
      expect(scale_drawn(type, other)).not_to eq(scale_drawn(type, nil)), type
    end
  end

  # What the arms above compare, handed to a compiler: Image and AsyncImage
  # carry Compose's and coil's parameter names (Image(painter,
  # contentDescription, modifier, alignment, contentScale, …), coil's
  # AsyncImage(model, contentDescription, modifier, …, alignment,
  # contentScale, …)), so a scale or an alignment in the wrong argument does
  # not type-check. Types only — a green says well-typed against these stubs.
  it 'compiles what each image emits with no contentMode, with the declared default and with a positional mode' do
    emits = []
    net = { 'url' => 'https://example.invalid/a.png' }
    [[nil, {}], [declared, {}], ['top', {}], [nil, net], [declared, net]].each do |mode, extra|
      components.each do |type, klass|
        next if type != 'CircleImage' && !extra.empty?

        node = { 'type' => type, 'id' => 'img', 'width' => 100, 'height' => 60 }.merge(extra)
        node[type == 'NetworkImage' ? 'url' : 'src'] ||= (type == 'NetworkImage' ? 'https://example.invalid/a.png' : 'probe_asset')
        node['contentMode'] = mode if mode
        emits << klass.generate(node, 0, Set.new)
      end
    end
    drawables = emits.join("\n").scan(/R\.drawable\.(\w+)/).flatten.uniq
    source = <<~KOTLIN
      interface Modifier { companion object : Modifier }
      class Dp(val value: Float)
      val Int.dp: Dp get() = Dp(toFloat())
      fun Modifier.testTag(tag: String): Modifier = this
      class SemanticsPropertyReceiver
      var SemanticsPropertyReceiver.testTagsAsResourceId: Boolean
          get() = false
          set(value) {}
      fun Modifier.semantics(mergeDescendants: Boolean = false, properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
      fun Modifier.size(width: Dp, height: Dp): Modifier = this
      fun Modifier.requiredWidth(width: Dp): Modifier = this
      fun Modifier.requiredHeight(height: Dp): Modifier = this
      interface Shape
      object CircleShape : Shape
      fun Modifier.clip(shape: Shape): Modifier = this
      class Painter
      fun painterResource(id: Int): Painter = Painter()
      object R { object drawable { #{drawables.map { |d| "const val #{d}: Int = 0" }.join('; ')} } }
      class ColorFilter
      interface ContentScale {
          companion object {
              val Crop = object : ContentScale {}; val Fit = object : ContentScale {}
              val FillBounds = object : ContentScale {}; val None = object : ContentScale {}
          }
      }
      interface Alignment {
          companion object {
              val Center = object : Alignment {}; val TopCenter = object : Alignment {}
              val BottomCenter = object : Alignment {}; val CenterStart = object : Alignment {}
              val CenterEnd = object : Alignment {}
          }
      }
      fun Image(painter: Painter, contentDescription: String?, modifier: Modifier = Modifier,
                alignment: Alignment = Alignment.Center, contentScale: ContentScale = ContentScale.Fit,
                alpha: Float = 1f, colorFilter: ColorFilter? = null) {}
      fun AsyncImage(model: Any?, contentDescription: String?, modifier: Modifier = Modifier,
                     placeholder: Painter? = null, error: Painter? = null, fallback: Painter? = error,
                     alignment: Alignment = Alignment.Center, contentScale: ContentScale = ContentScale.Fit,
                     alpha: Float = 1f, colorFilter: ColorFilter? = null) {}
      #{emits.each_with_index.map { |e, i| "fun emitted#{i}() {\n#{e}\n}" }.join("\n")}
    KOTLIN
    expect(source).to compile_as_kotlin
  end
end
