# frozen_string_literal: true

# Stub universes for `compile_as_kotlin` (spec/support/kotlin_compiler.rb):
# the Compose names an emitter's output calls, declared as TYPES ONLY, so
# plain kotlinc can read the emit. What a green from one of these says is
# "this is well-typed Kotlin against these stubs" — not "this is valid
# Compose": @Composable call context, restartability and stability are the
# Compose compiler's, which is not here.
#
# The names an emit invents per layout (icons, drawables, tab views) are read
# off the emit itself rather than listed by hand, so a new shape cannot pass
# for want of a stub the list forgot.
module ComposeStubUniverse
  module_function

  # A TabView emit (TabviewComponent.generate), placed in functions of the
  # caller's own writing — `data` and `viewModel` are theirs to declare.
  def tabview(emitted)
    icons = emitted.scan(/Icons\.(?:Filled|Outlined)\.(\w+)/).flatten.uniq
    drawables = emitted.scan(/R\.drawable\.(\w+)/).flatten.uniq
    views = emitted.scan(/\b(\w+View)\(\)/).flatten.uniq
    <<~KOTLIN
      annotation class Composable
      interface Modifier { companion object : Modifier }
      class Dp
      class PaddingValues { fun calculateBottomPadding(): Dp = Dp() }
      fun Modifier.padding(bottom: Dp): Modifier = this
      class SemanticsPropertyReceiver
      var SemanticsPropertyReceiver.stateDescription: String
          get() = ""
          set(value) {}
      fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
      class Color(val argb: Int = 0)
      object android { object graphics { object Color { fun parseColor(hex: String): Int = 0 } } }
      class ImageVector
      class Painter
      fun painterResource(id: Int): Painter = Painter()
      object R { object drawable { #{drawables.map { |d| "const val #{d}: Int = 0" }.join('; ')} } }
      class ColorScheme { val primary = Color(); val onSurfaceVariant = Color() }
      object MaterialTheme { val colorScheme = ColorScheme() }
      class NavigationBarItemColors
      object NavigationBarItemDefaults {
          fun colors(selectedIconColor: Color, selectedTextColor: Color,
                     unselectedIconColor: Color, unselectedTextColor: Color) = NavigationBarItemColors()
      }
      interface RowScope
      fun Scaffold(bottomBar: () -> Unit = {}, content: (PaddingValues) -> Unit) {}
      fun NavigationBar(containerColor: Color? = null, content: RowScope.() -> Unit) {}
      fun RowScope.NavigationBarItem(selected: Boolean, onClick: () -> Unit, icon: () -> Unit,
                                     modifier: Modifier = Modifier, label: (() -> Unit)? = null,
                                     colors: NavigationBarItemColors = NavigationBarItemColors()) {}
      object Icons { object Filled; object Outlined }
      #{icons.map { |i| "val Icons.Filled.#{i}: ImageVector get() = ImageVector()\nval Icons.Outlined.#{i}: ImageVector get() = ImageVector()" }.join("\n")}
      fun Icon(imageVector: ImageVector, contentDescription: String?) {}
      fun Icon(painter: Painter, contentDescription: String?) {}
      fun BadgedBox(badge: () -> Unit, content: () -> Unit) {}
      fun Badge(content: () -> Unit) {}
      fun Text(text: String) {}
      fun Box(modifier: Modifier = Modifier, content: () -> Unit) {}
      class ProvidedValue
      class SafeAreaConfig(val ignoreBottom: Boolean = false)
      object LocalSafeAreaConfig { infix fun provides(value: SafeAreaConfig) = ProvidedValue() }
      fun CompositionLocalProvider(vararg values: ProvidedValue, content: () -> Unit) {}
      class MutableState<T>(var value: T)
      operator fun <T> MutableState<T>.getValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>): T = value
      operator fun <T> MutableState<T>.setValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>, v: T) { value = v }
      fun <T> remember(calculation: () -> T): T = calculation()
      fun <T> mutableStateOf(value: T) = MutableState(value)
      #{views.map { |v| "fun #{v}() {}" }.join("\n")}
    KOTLIN
  end

  # Whole component emits carrying every common stage — the 25 types (and
  # their other branches) common_stages_on_every_drawn_type_spec.rb draws with testTag, margins,
  # size, offset, alpha, shadow, background, cornerRadius, border, onClick,
  # enabled, userInteractionEnabled and paddings all declared. Each emit is
  # placed in a function of the caller's own writing — `data` and
  # `viewModel` are theirs to declare. Modifier extensions carry Compose's
  # parameter names and types (Dp, Color, Shape, Shadow), so a stage that
  # lands in the wrong argument, or outside the chain, does not type-check;
  # the component composables carry the parameter names these emits pass.
  def common_stages(emitted)
    drawables = emitted.scan(/R\.drawable\.(\w+)/).flatten.uniq
    icons = emitted.scan(/Icons\.(?:Filled|Outlined)\.(\w+)/).flatten.uniq
    screens = emitted.scan(/^\s*(\w+View)\(\s*$/).flatten.uniq
    <<~KOTLIN
      interface Modifier { companion object : Modifier }
      class Dp(val value: Float)
      val Int.dp: Dp get() = Dp(toFloat())
      val Double.dp: Dp get() = Dp(toFloat())
      val Float.dp: Dp get() = Dp(this)
      class Color(val argb: Int = 0) {
          fun copy(alpha: Float = 1f): Color = this
          companion object {
              val Transparent = Color(); val Unspecified = Color(); val Black = Color(); val Gray = Color()
          }
      }
      fun Color.toArgb(): Int = argb
      object android { object graphics { object Color { fun parseColor(hex: String): Int = 0 } } }
      class TextUnit { companion object { val Unspecified = TextUnit() } }
      val Int.sp: TextUnit get() = TextUnit()
      class FontFamily
      class FontWeight
      class FontStyle { companion object { val Normal = FontStyle() } }
      class FontSpec(val family: String?, val weight: String?, val size: Int?, val italic: Boolean)
      class ResolvedFont(val family: FontFamily?, val weight: FontWeight?, val size: TextUnit?, val style: FontStyle?)
      class TextStyle(val color: Color = Color(), val fontSize: TextUnit = TextUnit())
      interface Shape
      class RoundedCornerShape(val radius: Dp) : Shape
      object RectangleShape : Shape
      object CircleShape : Shape
      class DpOffset(val x: Dp, val y: Dp)
      class Shadow(val radius: Dp, val color: Color = Color(), val offset: DpOffset = DpOffset(0.dp, 0.dp), val alpha: Float = 1f)
      class Brush { companion object {
          fun verticalGradient(colors: List<Color>): Brush = Brush()
          fun horizontalGradient(colors: List<Color>): Brush = Brush()
          fun linearGradient(colors: List<Color>): Brush = Brush()
      } }
      class Role private constructor() { companion object { val Button = Role() } }
      class SemanticsPropertyReceiver { var testTagsAsResourceId: Boolean = false; fun disabled() {} }

      fun Modifier.testTag(tag: String): Modifier = this
      fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
      fun Modifier.padding(all: Dp): Modifier = this
      fun Modifier.padding(start: Dp = 0.dp, top: Dp = 0.dp, end: Dp = 0.dp, bottom: Dp = 0.dp): Modifier = this
      fun Modifier.padding(horizontal: Dp = 0.dp, vertical: Dp = 0.dp): Modifier = this
      fun Modifier.requiredWidth(width: Dp): Modifier = this
      fun Modifier.requiredHeight(height: Dp): Modifier = this
      fun Modifier.width(width: Dp): Modifier = this
      fun Modifier.height(height: Dp): Modifier = this
      fun Modifier.size(size: Dp): Modifier = this
      fun Modifier.size(width: Dp, height: Dp): Modifier = this
      fun Modifier.fillMaxSize(): Modifier = this
      fun Modifier.fillMaxWidth(): Modifier = this
      fun Modifier.absoluteOffset(x: Dp = 0.dp, y: Dp = 0.dp): Modifier = this
      fun Modifier.alpha(alpha: Float): Modifier = this
      fun Modifier.dropShadow(shape: Shape, shadow: Shadow): Modifier = this
      fun Modifier.border(width: Dp, color: Color, shape: Shape = RectangleShape): Modifier = this
      fun Modifier.clip(shape: Shape): Modifier = this
      fun Modifier.background(color: Color): Modifier = this
      fun Modifier.background(brush: Brush): Modifier = this
      fun Modifier.blur(radius: Dp): Modifier = this
      fun Modifier.then(other: Modifier): Modifier = this
      fun Modifier.clickable(
          enabled: Boolean = true,
          onClickLabel: String? = null,
          role: Role? = null,
          onClick: () -> Unit
      ): Modifier = this
      enum class PointerEventPass { Initial, Main, Final }
      class PointerInputChange { fun consume() {} }
      class PointerEvent(val changes: List<PointerInputChange>)
      interface AwaitPointerEventScope { suspend fun awaitPointerEvent(pass: PointerEventPass = PointerEventPass.Main): PointerEvent }
      interface PointerInputScope { suspend fun <R> awaitPointerEventScope(block: suspend AwaitPointerEventScope.() -> R): R }
      fun Modifier.pointerInput(key1: Any?, block: suspend PointerInputScope.() -> Unit): Modifier = this
      class FocusState(val isFocused: Boolean)
      fun Modifier.onFocusChanged(onFocusChanged: (FocusState) -> Unit): Modifier = this
      class FocusRequester { fun requestFocus() {} }
      fun Modifier.focusRequester(focusRequester: FocusRequester): Modifier = this

      interface RowScope { fun Modifier.weight(weight: Float, fill: Boolean = true): Modifier = this }
      interface BoxScope
      interface LazyGridScope
      interface PaddingValues { fun calculateBottomPadding(): Dp }
      fun PaddingValues(all: Dp): PaddingValues = object : PaddingValues { override fun calculateBottomPadding() = all }
      fun PaddingValues(start: Dp = 0.dp, top: Dp = 0.dp, end: Dp = 0.dp, bottom: Dp = 0.dp): PaddingValues =
          object : PaddingValues { override fun calculateBottomPadding() = bottom }
      class BorderStroke(val width: Dp, val color: Color)
      class ButtonColors
      object ButtonDefaults {
          fun buttonColors(containerColor: Color = Color(), contentColor: Color = Color(),
                           disabledContainerColor: Color = Color(), disabledContentColor: Color = Color()) = ButtonColors()
      }
      object Configuration {
          object Button {
              val defaultTextColor = Color(); val defaultBackgroundColor = Color(); val defaultCornerRadius: Int = 8
          }
          object TextField { val defaultTextColor = Color(); val defaultFontSize: Int = 16; val defaultCornerRadius: Int = 8 }
          object Font { fun resolve(spec: FontSpec) = ResolvedFont(null, null, null, null) }
      }
      fun Button(onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true,
                 shape: Shape = RectangleShape, colors: ButtonColors = ButtonColors(), border: BorderStroke? = null,
                 contentPadding: PaddingValues = PaddingValues(0.dp), content: RowScope.() -> Unit) {}
      fun Text(text: String, color: Color = Color(), fontFamily: FontFamily? = null, fontWeight: FontWeight? = null,
               fontSize: TextUnit = TextUnit(), fontStyle: FontStyle? = null, modifier: Modifier = Modifier) {}
      fun Spacer(modifier: Modifier = Modifier) {}
      fun RadioButton(selected: Boolean, onClick: (() -> Unit)?, modifier: Modifier = Modifier) {}
      fun IconToggleButton(checked: Boolean, onCheckedChange: (Boolean) -> Unit, modifier: Modifier = Modifier,
                           content: () -> Unit) {}
      fun Icon(painter: Painter, contentDescription: String?, tint: Color = Color()) {}
      fun Column(modifier: Modifier = Modifier, content: ColumnScope.() -> Unit) {}
      interface ColumnScope
      class LazyListState
      fun rememberLazyListState() = LazyListState()
      interface LazyListScope { fun item(content: () -> Unit) }
      fun LazyColumn(state: LazyListState = LazyListState(), modifier: Modifier = Modifier, content: LazyListScope.() -> Unit) {}
      fun Modifier.keyboardAvoidance(state: LazyListState, clearance: Int): Modifier = this
      fun Modifier.systemBarsPadding(): Modifier = this
      fun Modifier.statusBarsPadding(): Modifier = this
      fun Modifier.navigationBarsPadding(): Modifier = this
      fun Modifier.imePadding(): Modifier = this
      class Painter
      fun painterResource(id: Int): Painter = Painter()
      object R { object drawable { #{drawables.map { |d| "const val #{d}: Int = 0" }.join('; ')} } }
      class ContentScale { companion object { val Crop = ContentScale(); val Fit = ContentScale() } }
      fun Image(painter: Painter, contentDescription: String?, modifier: Modifier = Modifier,
                contentScale: ContentScale = ContentScale.Fit) {}
      fun AsyncImage(model: Any?, contentDescription: String?, modifier: Modifier = Modifier) {}
      fun Switch(checked: Boolean, onCheckedChange: ((Boolean) -> Unit)?, modifier: Modifier = Modifier, enabled: Boolean = true) {}
      fun Checkbox(checked: Boolean, onCheckedChange: ((Boolean) -> Unit)?, modifier: Modifier = Modifier, enabled: Boolean = true) {}
      fun Slider(value: Float, onValueChange: (Float) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true,
                 valueRange: ClosedFloatingPointRange<Float> = 0f..1f) {}
      fun LinearProgressIndicator(modifier: Modifier = Modifier) {}
      fun CircularProgressIndicator(modifier: Modifier = Modifier) {}
      fun SelectBox(value: String, onValueChange: (String) -> Unit, options: List<String>, modifier: Modifier = Modifier,
                    enabled: Boolean = true, backgroundColor: Color? = null, borderColor: Color? = null,
                    cornerRadius: Int? = null, contentPadding: PaddingValues? = null) {}
      fun Segment(selectedTabIndex: Int, modifier: Modifier = Modifier, enabled: Boolean = true,
                  containerColor: Color = Color(), content: () -> Unit) {}
      fun Tab(selected: Boolean, onClick: () -> Unit, enabled: Boolean = true, text: (() -> Unit)? = null) {}
      class GridCells { companion object { fun Fixed(count: Int) = GridCells() } }
      fun LazyVerticalGrid(columns: GridCells, modifier: Modifier = Modifier, content: LazyGridScope.() -> Unit) {}
      class Context
      class WebSettings { var javaScriptEnabled: Boolean = false }
      open class WebViewClient
      class KjuiWebViewClient : WebViewClient()
      class WebChromeClient
      class WebView(context: Context) {
          val settings = WebSettings()
          var webViewClient: WebViewClient? = null
          var webChromeClient: WebChromeClient? = null
          fun setBackgroundColor(color: Int) {}
          fun loadUrl(url: String) {}
      }
      fun <T> AndroidView(factory: (Context) -> T, modifier: Modifier = Modifier, update: (T) -> Unit = {}) {}
      fun Box(modifier: Modifier = Modifier, content: BoxScope.() -> Unit = {}) {}
      class Arrangement { companion object { fun spacedBy(space: Dp) = Arrangement() } }
      class Alignment { companion object { val CenterVertically = Alignment() } }
      fun Row(modifier: Modifier = Modifier, horizontalArrangement: Arrangement = Arrangement(),
              verticalAlignment: Alignment = Alignment(), content: RowScope.() -> Unit) {}
      class ImageVector
      object Icons { object Filled; object Outlined }
      #{icons.map { |i| "val Icons.Filled.#{i}: ImageVector get() = ImageVector()\nval Icons.Outlined.#{i}: ImageVector get() = ImageVector()" }.join("\n")}
      fun Icon(imageVector: ImageVector, contentDescription: String?) {}
      class ColorScheme { val primary = Color(); val onSurfaceVariant = Color() }
      object MaterialTheme { val colorScheme = ColorScheme() }
      class NavigationBarItemColors
      object NavigationBarItemDefaults {
          fun colors(selectedIconColor: Color, selectedTextColor: Color,
                     unselectedIconColor: Color, unselectedTextColor: Color) = NavigationBarItemColors()
      }
      fun Scaffold(modifier: Modifier = Modifier, bottomBar: () -> Unit = {}, content: (PaddingValues) -> Unit) {}
      fun NavigationBar(content: RowScope.() -> Unit) {}
      fun RowScope.NavigationBarItem(selected: Boolean, onClick: () -> Unit, icon: () -> Unit,
                                     label: (() -> Unit)? = null,
                                     colors: NavigationBarItemColors = NavigationBarItemColors()) {}
      class ProvidedValue
      class SafeAreaConfig(val ignoreBottom: Boolean = false, val ignoreTop: Boolean = false)
      object LocalSafeAreaConfig {
          val current = SafeAreaConfig()
          infix fun provides(value: SafeAreaConfig) = ProvidedValue()
      }
      fun CompositionLocalProvider(vararg values: ProvidedValue, content: () -> Unit) {}
      class MutableState<T>(var value: T)
      operator fun <T> MutableState<T>.getValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>): T = value
      operator fun <T> MutableState<T>.setValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>, v: T) { value = v }
      fun <T> remember(calculation: () -> T): T = calculation()
      fun <T> mutableStateOf(value: T) = MutableState(value)
      enum class EmbedNavigationMode { Delegate, Isolated }
      class EmbedScope { val viewModelStoreOwner = Any() }
      fun EmbedContainer(modifier: Modifier = Modifier, embedId: String, navigationMode: EmbedNavigationMode,
                         content: (EmbedScope) -> Unit) {}
      object androidx { object hilt { object lifecycle { object viewmodel { object compose {
          fun hiltViewModel(viewModelStoreOwner: Any, key: String? = null): Any = Any()
      } } } } }
      #{screens.map { |v| "fun #{v}(viewModel: Any) {}" }.join("\n")}
      class TextFieldBuffer { val length: Int = 0; fun replace(start: Int, end: Int, text: CharSequence) {} }
      class TextFieldState { val text: CharSequence = ""; fun edit(block: TextFieldBuffer.() -> Unit) {} }
      fun rememberTextFieldState(initialText: String = ""): TextFieldState = TextFieldState()
      fun LaunchedEffect(key1: Any?, block: suspend () -> Unit) {}
      class SoftwareKeyboardController { fun show() {} }
      object LocalSoftwareKeyboardController { val current: SoftwareKeyboardController? = null }
      fun CustomTextField(state: TextFieldState, modifier: Modifier = Modifier, shape: Shape = RectangleShape,
                          contentPadding: PaddingValues? = null, backgroundColor: Color? = null,
                          borderColor: Color? = null, isOutlined: Boolean = false, textStyle: TextStyle? = null,
                          maxLines: Int = 1, singleLine: Boolean = true, enabled: Boolean = true) {}
      fun CustomTextFieldWithMargins(state: TextFieldState, boxModifier: Modifier = Modifier,
                                     textFieldModifier: Modifier = Modifier, shape: Shape = RectangleShape,
                                     contentPadding: PaddingValues? = null, backgroundColor: Color? = null,
                                     borderColor: Color? = null, isOutlined: Boolean = false,
                                     textStyle: TextStyle? = null, maxLines: Int = 1, singleLine: Boolean = true,
                                     enabled: Boolean = true) {}
    KOTLIN
  end

  # A modifier chain holding `.clickable(...)` (ModifierBuilder.build_clickable),
  # for the tap-role spec: Modifier, Role and clickable with Compose's parameter
  # names, and the data members the emitted handlers call.
  def clickable(emitted)
    handlers = emitted.scan(/data\.(\w+)\?\.invoke\(\)/).flatten.uniq
    <<~KOTLIN
      interface Modifier { companion object : Modifier }
      class Role private constructor() { companion object { val Button = Role() } }
      fun Modifier.clickable(
          enabled: Boolean = true,
          onClickLabel: String? = null,
          role: Role? = null,
          onClick: () -> Unit
      ): Modifier = this
      class Data(#{handlers.map { |h| "val #{h}: (() -> Unit)? = null" }.join(', ')})
    KOTLIN
  end
end
