# frozen_string_literal: true

require 'json'
require 'set'
require 'tmpdir'
require 'core/logger'
require 'compose/generators/dynamic_component_generator'
require_relative '../../support/kotlin_compiler'

# kjui-dynamic-scaffold-reads-an-optional-number-as-its-base-default: the
# Dynamic wrapper `kjui g converter` scaffolds read a `T?` scalar prop with the
# non-null reader and the base type's default, so a prop the layout omits
# reached the component as 0 / 0.0 / 0f / 0L / false — not null, as the
# composable's `T? = null` and the iOS adapter read it. On Android Debug a
# component drew an omitted `trackHeight: Double?` 0 thick.
#
# The arm RUNS the scaffolded wrapper on the JVM against the real Gson and a
# stub of Compose / KotlinJsonUI, the component replaced by one that prints
# what it was given: the layout omits the prop, gives a literal, binds a
# value the data holds, and binds a name the data lacks.
RSpec.describe 'the kjui Dynamic wrapper and an optional scalar prop' do
  before do
    %i[info debug warn success error].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
  end

  OPTIONAL_SCALAR_PROPS = { 'h' => 'Double?', 'n' => 'Int?', 'f' => 'Float?', 'l' => 'Long?', 'b' => 'Bool?', 'w' => 'Double' }.freeze

  OPTIONAL_SCALAR_STUB = <<~KT
    import com.google.gson.JsonObject
    import com.google.gson.JsonParser
    @Target(AnnotationTarget.FUNCTION, AnnotationTarget.TYPE, AnnotationTarget.TYPE_PARAMETER)
    annotation class Composable
    open class Modifier { companion object : Modifier() }
    class Context
    object LocalContext { val current = Context() }
    object ModifierBuilder {
        fun buildModifier(json: JsonObject, data: Map<String, Any>, context: Context): Modifier = Modifier
        fun isBinding(s: String): Boolean = s.startsWith("@{") && s.endsWith("}")
        fun extractBindingProperty(s: String): String? = if (isBinding(s)) s.substring(2, s.length - 1) else null
    }
    @Composable fun DynamicView(json: JsonObject, data: Map<String, Any>) {}
    // The component: prints what the wrapper hands it.
    @Composable fun Bar(h: Double? = null, n: Int? = null, f: Float? = null, l: Long? = null, b: Boolean? = null, w: Double = 1.0,
                        modifier: Modifier = Modifier, content: @Composable () -> Unit = {}) {
        println("h=$h n=$n f=$f l=$l b=$b w=$w")
    }
  KT

  def wrapper
    Dir.mktmpdir('kjui_optional') do |dir|
      Dir.chdir(dir) do
        File.write('kjui.config.json', JSON.generate('package_name' => 'probe'))
        KjuiTools::Compose::Generators::DynamicComponentGenerator.new('Bar', { is_container: nil, attributes: OPTIONAL_SCALAR_PROPS })
                                                                .send(:dynamic_template)
      end
    end.lines.reject { |l| l =~ /\A\s*(package|import)\s/ }.join
       .gsub('com.kotlinjsonui.dynamic.DynamicView', 'DynamicView')
  end

  it 'reads null for an omitted optional prop, the value for a literal or a bound value, null for a name the data lacks' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    main = <<~KT
      fun main() {
          val data = mapOf<String, Any>("hv" to 2.5, "nv" to 3, "fv" to 1.5f, "lv" to 7L, "bv" to true)
          fun show(json: String) = DynamicBarComponent.create(JsonParser.parseString(json).asJsonObject, data)
          show("""{}""")
          show("""{"h": 4.0, "n": 2, "f": 0.5, "l": 9, "b": false, "w": 3.0}""")
          show("""{"h": "@{hv}", "n": "@{nv}", "f": "@{fv}", "l": "@{lv}", "b": "@{bv}"}""")
          show("""{"h": "@{missing}", "n": "@{missing}", "f": "@{missing}", "l": "@{missing}", "b": "@{missing}"}""")
      }
    KT
    run = KotlinCompiler.run(OPTIONAL_SCALAR_STUB + "\n" + wrapper + "\n" + main, libraries: [:gson])
    expect(run.errors).to eq([])
    expect(run.output.lines.map(&:strip)).to eq([
      # Through jsonui-cli 1.9.5: h=0.0 n=0 f=0.0 l=0 b=false — the base defaults.
      'h=null n=null f=null l=null b=null w=0.0',
      'h=4.0 n=2 f=0.5 l=9 b=false w=3.0',
      'h=2.5 n=3 f=1.5 l=7 b=true w=0.0',
      'h=null n=null f=null l=null b=null w=0.0'
    ])
  end

  it 'compiles (the ratchet: emitted_kotlin_reaches_a_compiler_spec)' do
    expect(OPTIONAL_SCALAR_STUB + "\n" + wrapper).to compile_as_kotlin(:gson)
  end
end
