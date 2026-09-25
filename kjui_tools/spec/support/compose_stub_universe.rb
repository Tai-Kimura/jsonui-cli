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
