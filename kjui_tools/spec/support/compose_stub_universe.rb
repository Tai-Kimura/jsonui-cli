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
      interface RowScope
      interface BoxScope
      // KotlinJsonUI's tab wrappers (com.kotlinjsonui.components, >= 2.66.0), with the parameters of
      // JsonUIMaterialControls.kt. No material3 Scaffold / NavigationBar / NavigationBarItem / Icon / BadgedBox is
      // declared, so an emit that went back to calling material3 directly does not resolve here (ticket
      // kjui-wrap-material3-calls-next).
      fun JsonUITabScaffold(modifier: Modifier = Modifier, bottomBar: () -> Unit = {}, content: (PaddingValues) -> Unit) {}
      fun JsonUITabBar(modifier: Modifier = Modifier, containerColor: Color = Color(), content: RowScope.() -> Unit) {}
      fun RowScope.JsonUITabBarItem(selected: Boolean, onClick: () -> Unit, icon: () -> Unit,
                                    modifier: Modifier = Modifier, enabled: Boolean = true, label: (() -> Unit)? = null,
                                    selectedIconColor: Color = Color(), selectedTextColor: Color = Color(),
                                    unselectedIconColor: Color = Color(), unselectedTextColor: Color = Color()) {}
      object Icons { object Filled; object Outlined }
      #{icons.map { |i| "val Icons.Filled.#{i}: ImageVector get() = ImageVector()\nval Icons.Outlined.#{i}: ImageVector get() = ImageVector()" }.join("\n")}
      fun JsonUIIcon(imageVector: ImageVector, contentDescription: String?, modifier: Modifier = Modifier, tint: Color = Color()) {}
      fun JsonUIIcon(painter: Painter, contentDescription: String?, modifier: Modifier = Modifier, tint: Color = Color()) {}
      fun JsonUIBadgedBox(badge: String, modifier: Modifier = Modifier, content: BoxScope.() -> Unit) {}
      fun Text(text: String, fontFamily: Any? = null, fontWeight: Any? = null, fontStyle: Any? = null, fontSize: Any? = null, letterSpacing: Any? = null, lineHeight: Any? = null, maxLines: Int = Int.MAX_VALUE, overflow: Any? = null) {}
      fun Box(modifier: Modifier = Modifier, content: () -> Unit) {}
      class ProvidedValue
      class SafeAreaConfig(val ignoreBottom: Boolean = false)
      object LocalSafeAreaConfig { infix fun provides(value: SafeAreaConfig) = ProvidedValue() }
      // KotlinJsonUI's com.kotlinjsonui.core.LocalJsonUITint / jsonUITintOr: a
      // container's tintColor handed down (InheritedTint), and the read a
      // control makes where it declares no accent of its own.
      object LocalJsonUITint {
          val current = Color()
          infix fun provides(value: Color) = ProvidedValue()
      }
      fun jsonUITintOr(fallback: Color): Color = fallback
      // KotlinJsonUI's com.kotlinjsonui.core.jsonUIFontSize: every text size through the text size rule.
      fun <T> jsonUIFontSize(size: T, fontScaling: Boolean? = null, maxFontScale: Float? = null): T = size
      fun jsonUILetterSpacing(fontScaling: Boolean? = null, maxFontScale: Float? = null): Any? = null
      fun jsonUILineHeight(fontSize: Any? = null, fontScaling: Boolean? = null, maxFontScale: Float? = null, lineHeight: Any? = null): Nothing = throw IllegalStateException()
      fun CompositionLocalProvider(vararg values: ProvidedValue, content: () -> Unit) {}
      class MutableState<T>(var value: T)
      operator fun <T> MutableState<T>.getValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>): T = value
      operator fun <T> MutableState<T>.setValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>, v: T) { value = v }
      fun <T> remember(calculation: () -> T): T = calculation()
      // A bound field's passed data, read in its effects (TextInputWriteBack).
      fun <T> rememberUpdatedState(newValue: T): MutableState<T> = MutableState(newValue)
      fun <T> mutableStateOf(value: T) = MutableState(value)
      // The effect a TabView's onValueChange is called from (on a change of
      // the selection, ruling 2026-10-02).
      fun LaunchedEffect(key1: Any?, block: suspend () -> Unit) {}
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
      class Dp(val value: Float) { companion object { val Infinity = Dp(Float.POSITIVE_INFINITY) } }
      val Int.dp: Dp get() = Dp(toFloat())
      val Double.dp: Dp get() = Dp(toFloat())
      val Float.dp: Dp get() = Dp(this)
      class Color(val argb: Int = 0) {
          fun copy(alpha: Float = 1f, letterSpacing: Any? = null, lineHeight: Any? = null): Color = this
          companion object {
              val Transparent = Color(); val Unspecified = Color(); val Black = Color(); val Gray = Color()
          }
      }
      fun Color.toArgb(): Int = argb
      object android { object graphics { object Color { fun parseColor(hex: String): Int = 0 } } }
      class TextUnit { companion object { val Unspecified = TextUnit() } }
      val Int.sp: TextUnit get() = TextUnit()
      val Float.sp: TextUnit get() = TextUnit()
      val Double.sp: TextUnit get() = TextUnit()
      class FontFamily
      class FontWeight { companion object {
          val Thin = FontWeight(); val ExtraLight = FontWeight(); val Light = FontWeight(); val Normal = FontWeight()
          val Medium = FontWeight(); val SemiBold = FontWeight(); val Bold = FontWeight(); val ExtraBold = FontWeight()
          val Black = FontWeight()
      } }
      class FontStyle { companion object { val Normal = FontStyle(); val Italic = FontStyle() } }
      class TextOverflow { companion object { val Ellipsis = TextOverflow(); val Clip = TextOverflow() } }
      // KotlinJsonUI's FontSpec: what a component declares, handed to Configuration.Font.resolve (the app's fontProvider).
      class FontSpec(val family: String? = null, val weight: FontWeight? = null, val size: TextUnit? = null, val italic: Boolean = false)
      class ResolvedFont(val family: FontFamily?, val weight: FontWeight?, val size: TextUnit?, val style: FontStyle?)
      class TextStyle(val color: Color = Color(), val fontSize: TextUnit = TextUnit(), val letterSpacing: Any? = null,
                      val fontFamily: FontFamily? = null, val fontWeight: FontWeight? = null, val fontStyle: FontStyle? = null,
                      textAlign: Any? = null, lineHeight: Any? = null, shadow: Any? = null) {
          fun copy(lineHeight: Any? = null, letterSpacing: Any? = null, fontSize: TextUnit = TextUnit(),
                   fontFamily: FontFamily? = null, fontWeight: FontWeight? = null, fontStyle: FontStyle? = null,
                   color: Color = Color(), textAlign: Any? = null, shadow: Any? = null): TextStyle = this
      }
      object LocalTextStyle { val current = TextStyle() }
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
      fun Modifier.clipToBounds(): Modifier = this
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
      class PointerInputChange { fun consume() {}; val pressed: Boolean = false }
      class PointerEvent(val changes: List<PointerInputChange>)
      fun PointerEvent.calculateZoom(): Float = 1f
      interface ViewConfiguration { val longPressTimeoutMillis: Long }
      interface AwaitPointerEventScope {
          val viewConfiguration: ViewConfiguration
          suspend fun awaitPointerEvent(pass: PointerEventPass = PointerEventPass.Main): PointerEvent
          suspend fun <T> withTimeout(timeMillis: Long, block: suspend AwaitPointerEventScope.() -> T): T
      }
      class PointerEventTimeoutCancellationException : Exception()
      suspend fun AwaitPointerEventScope.awaitFirstDown(requireUnconsumed: Boolean = true,
                                                        pass: PointerEventPass = PointerEventPass.Main): PointerInputChange = PointerInputChange()
      interface PointerInputScope { suspend fun <R> awaitPointerEventScope(block: suspend AwaitPointerEventScope.() -> R): R }
      suspend fun PointerInputScope.awaitEachGesture(block: suspend AwaitPointerEventScope.() -> Unit) {}
      suspend fun AwaitPointerEventScope.waitForUpOrCancellation(pass: PointerEventPass = PointerEventPass.Main): PointerInputChange? = null
      class Offset(val x: Float, val y: Float) {
          operator fun plus(other: Offset): Offset = this
          companion object { val Zero = Offset(0f, 0f) }
      }
      // KotlinJsonUI's jsonUIPanGesture (>= 2.65.0): onPan is emitted as this, never as a bare detectDragGestures.
      fun Modifier.jsonUIPanGesture(key: Any?, onPan: (Offset) -> Unit): Modifier = this
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
      fun PaddingValues(horizontal: Dp, vertical: Dp): PaddingValues =
          object : PaddingValues { override fun calculateBottomPadding() = vertical }
      fun Modifier.heightIn(min: Dp = 0.dp, max: Dp = Dp.Infinity): Modifier = this
      class BorderStroke(val width: Dp, val color: Color)
      class MutableInteractionSource
      object Configuration {
          object Button {
              val defaultTextColor = Color(); val defaultBackgroundColor = Color(); val defaultCornerRadius: Int = 0
          }
          object TextField { val defaultTextColor = Color(); val defaultFontSize: Int = 16; val defaultPlaceholderColor = Color() }
          object Font { fun resolve(spec: FontSpec) = ResolvedFont(null, null, null, null) }
      }
      // KotlinJsonUI's wrappers of the material3 controls (com.kotlinjsonui.components, >= 2.66.0), with the
      // parameters of JsonUIMaterialControls.kt: the colours flat, no material3 *Colors type. No material3 Button,
      // RadioButton, Switch, Checkbox, Icon, IconToggleButton, IconButton, progress indicator, divider, Scaffold or
      // NavigationBar is declared, so an emit that went back to calling one directly does not resolve here (ticket
      // kjui-wrap-material3-calls-next).
      fun JsonUIButton(onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true,
                       shape: Shape = RectangleShape, containerColor: Color = Color.Unspecified,
                       contentColor: Color = Color.Unspecified, disabledContainerColor: Color = Color.Unspecified,
                       disabledContentColor: Color = Color.Unspecified, border: BorderStroke? = null,
                       contentPadding: PaddingValues = PaddingValues(0.dp), interactionSource: MutableInteractionSource? = null,
                       content: RowScope.() -> Unit) {}
      fun Text(text: String, color: Color = Color(), fontFamily: FontFamily? = null, fontWeight: FontWeight? = null,
               fontSize: TextUnit = TextUnit(), fontStyle: FontStyle? = null, modifier: Modifier = Modifier,
               style: TextStyle? = null, letterSpacing: Any? = null, lineHeight: Any? = null,
               maxLines: Int = Int.MAX_VALUE, overflow: Any? = null) {}
      fun Spacer(modifier: Modifier = Modifier) {}
      fun JsonUIRadioButton(selected: Boolean, onClick: (() -> Unit)?, modifier: Modifier = Modifier, enabled: Boolean = true,
                            selectedColor: Color = Color.Unspecified, unselectedColor: Color = Color.Unspecified) {}
      fun JsonUIIconToggleButton(checked: Boolean, onCheckedChange: (Boolean) -> Unit, modifier: Modifier = Modifier,
                                 enabled: Boolean = true, content: () -> Unit) {}
      fun JsonUIIconButton(onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, content: () -> Unit) {}
      fun JsonUIIcon(painter: Painter, contentDescription: String?, modifier: Modifier = Modifier, tint: Color = Color()) {}
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
      class WindowInsets { companion object }
      class WindowInsetsSides {
          operator fun plus(sides: WindowInsetsSides): WindowInsetsSides = this
          companion object {
              val Top = WindowInsetsSides(); val Bottom = WindowInsetsSides()
              val Start = WindowInsetsSides(); val End = WindowInsetsSides()
          }
      }
      val WindowInsets.Companion.systemBars: WindowInsets get() = WindowInsets()
      fun WindowInsets.only(sides: WindowInsetsSides): WindowInsets = this
      fun Modifier.windowInsetsPadding(insets: WindowInsets): Modifier = this
      class Painter
      fun painterResource(id: Int): Painter = Painter()
      object R { object drawable { #{drawables.map { |d| "const val #{d}: Int = 0" }.join('; ')} } }
      class ContentScale { companion object { val Crop = ContentScale(); val Fit = ContentScale() } }
      fun Image(painter: Painter, contentDescription: String?, modifier: Modifier = Modifier,
                contentScale: ContentScale = ContentScale.Fit) {}
      fun AsyncImage(model: Any?, contentDescription: String?, modifier: Modifier = Modifier) {}
      // KotlinJsonUI 2.60.0 com.kotlinjsonui.image.KjuiNetworkImage: every NetworkImage emits it.
      fun KjuiNetworkImage(model: Any?, contentDescription: String?, modifier: Modifier = Modifier,
                           contentScale: ContentScale = ContentScale.Fit, alignment: Alignment = Alignment.Center,
                           placeholder: Int = 0, error: Int = 0, fallback: Int = 0,
                           loadingRenderer: String? = null, loadingDelayMillis: Int = 200, transitionMillis: Int = -1,
                           onLoadStateChange: ((String) -> Unit)? = null) {}
      fun JsonUISwitch(checked: Boolean, onCheckedChange: ((Boolean) -> Unit)?, modifier: Modifier = Modifier, enabled: Boolean = true,
                       checkedTrackColor: Color = Color.Unspecified, uncheckedTrackColor: Color = Color.Unspecified,
                       checkedThumbColor: Color = Color.Unspecified, uncheckedThumbColor: Color = Color.Unspecified,
                       checkedBorderColor: Color = Color.Unspecified, uncheckedBorderColor: Color = Color.Unspecified) {}
      fun JsonUICheckbox(checked: Boolean, onCheckedChange: ((Boolean) -> Unit)?, modifier: Modifier = Modifier, enabled: Boolean = true,
                         checkedColor: Color = Color.Unspecified, uncheckedColor: Color = Color.Unspecified,
                         checkmarkColor: Color = Color.Unspecified) {}
      class SliderColors
      object SliderDefaults {
          fun colors(thumbColor: Color = Color(), activeTrackColor: Color = Color(), inactiveTrackColor: Color = Color()) = SliderColors()
      }
      // KotlinJsonUI's JsonUISlider (>= 2.65.0), not material3's Slider: the codegen calls only this, so an emit that
      // went back to material3's deprecated value form does not resolve here (ticket kjui-slider-deprecated-in-material3-1-5)
      fun JsonUISlider(value: Float, onValueChange: (Float) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true,
                       valueRange: ClosedFloatingPointRange<Float> = 0f..1f, steps: Int = 0,
                       onValueChangeFinished: (() -> Unit)? = null, thumbColor: Color = Color.Unspecified,
                       activeTrackColor: Color = Color.Unspecified, inactiveTrackColor: Color = Color.Unspecified) {}
      // determinate with `progress`, indeterminate without it
      fun JsonUILinearProgressIndicator(modifier: Modifier = Modifier, progress: (() -> Float)? = null, color: Color = Color(),
                                        trackColor: Color = Color()) {}
      fun JsonUICircularProgressIndicator(modifier: Modifier = Modifier, color: Color = Color(), strokeWidth: Dp = 0.dp) {}
      fun JsonUIDivider(modifier: Modifier = Modifier, thickness: Dp = 1.dp, color: Color = Color()) {}
      fun SelectBox(value: String, onValueChange: (String) -> Unit, resolvedFont: Any? = null, options: List<String>, modifier: Modifier = Modifier,
                    enabled: Boolean = true, backgroundColor: Color? = null, borderColor: Color? = null,
                    cornerRadius: Int? = null, contentPadding: PaddingValues? = null, fontSize: Int = 16) {}
      fun DateSelectBox(value: String, onValueChange: (String) -> Unit, resolvedFont: Any? = null, modifier: Modifier = Modifier,
                        datePickerMode: String = "date", minuteInterval: Int = 1, enabled: Boolean = true,
                        cornerRadius: Int? = null, fontSize: Int = 16) {}
      fun Segment(selectedTabIndex: Int, modifier: Modifier = Modifier, enabled: Boolean = true,
                  containerColor: Color? = null, contentColor: Color? = null, selectedContentColor: Color? = null,
                  indicatorColor: Color? = null, cornerRadius: Dp? = null, content: () -> Unit) {}
      fun Tab(selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, text: (() -> Unit)? = null) {}
      fun SegmentTab(selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, text: () -> Unit) {}
      class GridCells { companion object { fun Fixed(count: Int) = GridCells() } }
      fun LazyVerticalGrid(columns: GridCells, modifier: Modifier = Modifier, contentPadding: PaddingValues? = null,
                           verticalArrangement: Arrangement = Arrangement(), horizontalArrangement: Arrangement = Arrangement(),
                           content: LazyGridScope.() -> Unit) {}
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
      fun Box(modifier: Modifier = Modifier, contentAlignment: Alignment = Alignment(), content: BoxScope.() -> Unit = {}) {}
      class Arrangement { companion object { fun spacedBy(space: Dp) = Arrangement() } }
      class Alignment { companion object { val CenterVertically = Alignment(); val Center = Alignment() } }
      fun Row(modifier: Modifier = Modifier, horizontalArrangement: Arrangement = Arrangement(),
              verticalAlignment: Alignment = Alignment(), content: RowScope.() -> Unit) {}
      class ImageVector
      object Icons { object Filled; object Outlined }
      #{icons.map { |i| "val Icons.Filled.#{i}: ImageVector get() = ImageVector()\nval Icons.Outlined.#{i}: ImageVector get() = ImageVector()" }.join("\n")}
      fun JsonUIIcon(imageVector: ImageVector, contentDescription: String?, modifier: Modifier = Modifier, tint: Color = Color()) {}
      class ColorScheme { val primary = Color(); val onSurfaceVariant = Color() }
      object MaterialTheme { val colorScheme = ColorScheme() }
      fun JsonUITabScaffold(modifier: Modifier = Modifier, bottomBar: () -> Unit = {}, content: (PaddingValues) -> Unit) {}
      fun JsonUITabBar(modifier: Modifier = Modifier, containerColor: Color = Color(), content: RowScope.() -> Unit) {}
      fun RowScope.JsonUITabBarItem(selected: Boolean, onClick: () -> Unit, icon: () -> Unit,
                                    modifier: Modifier = Modifier, enabled: Boolean = true, label: (() -> Unit)? = null,
                                    selectedIconColor: Color = Color.Unspecified, selectedTextColor: Color = Color.Unspecified,
                                    unselectedIconColor: Color = Color.Unspecified, unselectedTextColor: Color = Color.Unspecified) {}
      fun JsonUIBadgedBox(badge: String, modifier: Modifier = Modifier, content: BoxScope.() -> Unit) {}
      class ProvidedValue
      class SafeAreaConfig(val ignoreBottom: Boolean = false, val ignoreTop: Boolean = false)
      object LocalSafeAreaConfig {
          val current = SafeAreaConfig()
          infix fun provides(value: SafeAreaConfig) = ProvidedValue()
      }
      // KotlinJsonUI's com.kotlinjsonui.core.LocalInteractionStopped: a node
      // whose userInteractionEnabled is false or bound, holding a Collection,
      // an Embed or a TabView tab, provides it (ComposeBuilder
      // #provide_interaction_stop).
      object LocalInteractionStopped {
          val current = false
          infix fun provides(value: Boolean) = ProvidedValue()
      }
      // KotlinJsonUI's com.kotlinjsonui.core.LocalJsonUITint / jsonUITintOr: a
      // container's tintColor handed down (InheritedTint), and the read a
      // control makes where it declares no accent of its own.
      object LocalJsonUITint {
          val current = Color()
          infix fun provides(value: Color) = ProvidedValue()
      }
      fun jsonUITintOr(fallback: Color): Color = fallback
      // KotlinJsonUI's com.kotlinjsonui.core.jsonUIFontSize: every text size through the text size rule.
      fun <T> jsonUIFontSize(size: T, fontScaling: Boolean? = null, maxFontScale: Float? = null): T = size
      fun jsonUILetterSpacing(fontScaling: Boolean? = null, maxFontScale: Float? = null): Any? = null
      fun jsonUILineHeight(fontSize: Any? = null, fontScaling: Boolean? = null, maxFontScale: Float? = null, lineHeight: Any? = null): Nothing = throw IllegalStateException()
      fun CompositionLocalProvider(vararg values: ProvidedValue, content: () -> Unit) {}
      class MutableState<T>(var value: T)
      operator fun <T> MutableState<T>.getValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>): T = value
      operator fun <T> MutableState<T>.setValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>, v: T) { value = v }
      fun <T> remember(calculation: () -> T): T = calculation()
      // A bound field's passed data, read in its effects (TextInputWriteBack).
      fun <T> rememberUpdatedState(newValue: T): MutableState<T> = MutableState(newValue)
      fun <T> mutableStateOf(value: T) = MutableState(value)
      // The view's map of unbound single-Radio groups (ComposeBuilder
      // RADIO_GROUP_SELECTIONS_DECLARATION, declared once per view file).
      object LocalRadioGroupSelections { val current: MutableMap<String, String> = mutableMapOf() }
      enum class EmbedNavigationMode { Delegate, Isolated }
      class EmbedScope { val viewModelStoreOwner = Any() }
      fun EmbedContainer(modifier: Modifier = Modifier, embedId: String, params: Map<String, Any> = emptyMap(),
                         navigationMode: EmbedNavigationMode, content: (EmbedScope) -> Unit) {}
      object androidx { object hilt { object lifecycle { object viewmodel { object compose {
          fun hiltViewModel(viewModelStoreOwner: Any, key: String? = null): Any = Any()
      } } } } }
      #{screens.map { |v| "fun #{v}(viewModel: Any) {}" }.join("\n")}
      class TextFieldBuffer { val length: Int = 0; fun replace(start: Int, end: Int, text: CharSequence) {} }
      class TextFieldState { val text: CharSequence = ""; fun edit(block: TextFieldBuffer.() -> Unit) {} }
      fun rememberTextFieldState(initialText: String = ""): TextFieldState = TextFieldState()
      class TextChanges { suspend fun collectLatest(action: suspend (String) -> Unit) {} }
      fun snapshotFlow(block: () -> String): TextChanges = TextChanges()
      fun LaunchedEffect(key1: Any?, block: suspend () -> Unit) {}
      class SoftwareKeyboardController { fun show() {} }
      object LocalSoftwareKeyboardController { val current: SoftwareKeyboardController? = null }
      fun CustomTextField(state: TextFieldState, modifier: Modifier = Modifier, shape: Shape = RectangleShape,
                          placeholder: (() -> Unit)? = null,
                          contentPadding: PaddingValues? = null, backgroundColor: Color? = null,
                          borderColor: Color? = null, isOutlined: Boolean = false, textStyle: TextStyle? = null,
                          maxLines: Int = 1, singleLine: Boolean = true, enabled: Boolean = true,
                          // KotlinJsonUI CustomTextField.kt:48-51 (rel/2.43.1)
                          onFocus: (() -> Unit)? = null, onBlur: (() -> Unit)? = null,
                          onBeginEditing: (() -> Unit)? = null, onEndEditing: (() -> Unit)? = null,
                          // KotlinJsonUI CustomTextField.kt (fix/textfield-border-width)
                          borderWidth: Dp? = null) {}
      fun CustomTextFieldWithMargins(state: TextFieldState, boxModifier: Modifier = Modifier,
                          placeholder: (() -> Unit)? = null,
                                     textFieldModifier: Modifier = Modifier, shape: Shape = RectangleShape,
                                     contentPadding: PaddingValues? = null, backgroundColor: Color? = null,
                                     borderColor: Color? = null, isOutlined: Boolean = false,
                                     textStyle: TextStyle? = null, maxLines: Int = 1, singleLine: Boolean = true,
                                     enabled: Boolean = true,
                                     // KotlinJsonUI CustomTextField.kt:231-234 (rel/2.43.1)
                                     onFocus: (() -> Unit)? = null, onBlur: (() -> Unit)? = null,
                                     onBeginEditing: (() -> Unit)? = null, onEndEditing: (() -> Unit)? = null,
                                     borderWidth: Dp? = null) {}
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
