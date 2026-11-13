# frozen_string_literal: true

# The KotlinJsonUI declarations every text the generator emits now reads (the requester's P1, ticket
# jui-font-provider-not-reached-without-font-attributes-android-web): each component's text resolves its FontSpec
# through Configuration.Font.resolve, the app's fontProvider, and draws the result. A spec with a stub world of its
# own adds these, in the library's shapes, so the emitted call type-checks as it does against the library.
module FontProviderStub
  # FontSpec / ResolvedFont / Configuration.Font, and the font classes they carry.
  FONT = <<~KT
    class FontFamily
    class FontWeight { companion object {
        val Thin = FontWeight(); val ExtraLight = FontWeight(); val Light = FontWeight(); val Normal = FontWeight()
        val Medium = FontWeight(); val SemiBold = FontWeight(); val Bold = FontWeight(); val ExtraBold = FontWeight()
        val Black = FontWeight()
    } }
    class FontStyle { companion object { val Normal = FontStyle(); val Italic = FontStyle() } }
    class FontSpec(val family: String? = null, val weight: FontWeight? = null, val size: TextUnit? = null, val italic: Boolean = false)
    class ResolvedFont(val family: FontFamily? = null, val weight: FontWeight? = null, val size: TextUnit? = null, val style: FontStyle? = null)
    object Configuration { object Font { fun resolve(spec: FontSpec) = ResolvedFont(null, spec.weight, spec.size, FontStyle.Normal) } }
  KT

  # The current text style's weight, which a component naming no weight hands the provider (FontSpecHelper
  # DRAWN_WEIGHT), for a world with no TextStyle of its own.
  TEXT_STYLE = <<~KT
    class TextStyle(val fontWeight: FontWeight? = null)
    object LocalTextStyle { val current = TextStyle() }
  KT

  # TextUnit and the size rule's calls (KotlinJsonUI FontScaling), for a world that has none of them.
  SIZE = <<~KT
    class TextUnit { companion object { val Unspecified = TextUnit() } }
    val Int.sp: TextUnit get() = TextUnit()
    val Float.sp: TextUnit get() = TextUnit()
    val Double.sp: TextUnit get() = TextUnit()
    fun <T> jsonUIFontSize(size: T, fontScaling: Boolean? = null, maxFontScale: Float? = null): T = size
    fun jsonUILetterSpacing(fontScaling: Boolean? = null, maxFontScale: Float? = null): Any? = null
  KT
end
