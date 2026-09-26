# frozen_string_literal: true

require 'set'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../support/kotlin_compiler'

# `scrollAnimated` on the programmatic scroll (`scrollTo`), one answer on both
# Compose paths — the grid and the CollectionStack: a binding decides at run
# time, a literal `false` jumps (`scrollToItem`), absent or `true` animates
# (the declared default, "default: true"). sjui calls `scrollProxy.scrollTo`
# outside `withAnimation` for a literal false and rjui passes `false` to
# scrollCollectionToItem. Until 1.8.121 (measured on 8e4ea3ea, 2026-09-26)
# kjui read only the binding, so a literal false still animated on both
# paths. Ticket collection-attributes-declared-but-not-drawn-on-some-paths.
#
# The compile arm reads the scroll block against LazyGridState /
# LazyListState stubs whose two calls are transcribed from javap of
# foundation-android 1.12.1 (`scrollToItem(int, int, Continuation)` and
# `animateScrollToItem(int, int, Continuation)` on both, with `$default`
# forms): a transcription, not a compile against Compose.
RSpec.describe 'kjui codegen: scrollAnimated' do
  SCROLL_ANIMATED_PATHS = {
    'grid' => { 'cellClasses' => ['RowCell'], 'columns' => 2 },
    'stack' => { 'sections' => [{ 'cell' => 'RowCell' }] }
  }.freeze

  def emit(path, value)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    node = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'scrollTo' => '@{target}' }.merge(SCROLL_ANIMATED_PATHS[path])
    node['scrollAnimated'] = value unless value == :absent
    KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil)
  end

  # The state declaration through the end of the LaunchedEffect.
  def scroll_block(code)
    code[/^( *)val (?:gridState|collectionStackState) = .*?\n\1LaunchedEffect\(.*?\n\1\}\n/m] or raise "no scroll block in\n#{code}"
  end

  def calls(code)
    scroll_block(code).scan(/\b(animateScrollToItem|scrollToItem)\(/).flatten
  end

  SCROLL_ANIMATED_PATHS.each_key do |path|
    it "#{path}: absent and true animate, a literal false jumps, a binding chooses at run time" do
      expect(calls(emit(path, :absent))).to eq(['animateScrollToItem'])
      expect(calls(emit(path, true))).to eq(['animateScrollToItem'])
      expect(calls(emit(path, false))).to eq(['scrollToItem'])
      # The string "false" is not the declared boolean: it animates, as it
      # does on sjui (`scroll_animated == false`) and rjui (`== false`).
      expect(calls(emit(path, 'false'))).to eq(['animateScrollToItem'])
      bound = emit(path, '@{animated}')
      expect(calls(bound)).to eq(%w[animateScrollToItem scrollToItem])
      expect(scroll_block(bound)).to include('if (data.animated)')
    end
  end

  SCROLL_ANIMATED_STUBS = <<~KOTLIN
    annotation class Composable
    class LayoutInfo { val viewportStartOffset: Int = 0; val viewportEndOffset: Int = 0 }
    class LazyGridState {
        val layoutInfo = LayoutInfo()
        suspend fun scrollToItem(index: Int, scrollOffset: Int = 0) {}
        suspend fun animateScrollToItem(index: Int, scrollOffset: Int = 0) {}
    }
    class LazyListState {
        val layoutInfo = LayoutInfo()
        suspend fun scrollToItem(index: Int, scrollOffset: Int = 0) {}
        suspend fun animateScrollToItem(index: Int, scrollOffset: Int = 0) {}
    }
    fun rememberLazyGridState(): LazyGridState = LazyGridState()
    object androidx { object compose { object foundation { object lazy {
        fun rememberLazyListState(): LazyListState = LazyListState()
    } } } }
    fun LaunchedEffect(key1: Any?, block: suspend kotlinx.coroutines.CoroutineScope.() -> Unit) {}
    class Data(val target: Int? = null, val animated: Boolean = true)
  KOTLIN

  it 'every scroll block compiles against the two calls both states have' do
    functions = SCROLL_ANIMATED_PATHS.keys.product([:absent, true, false, '@{animated}']).each_with_index.map do |(path, value), index|
      "// #{path}, scrollAnimated #{value.inspect}\n@Composable fun scroll#{index}(data: Data) {\n#{scroll_block(emit(path, value))}}"
    end
    expect("#{SCROLL_ANIMATED_STUBS}\n#{functions.join("\n\n")}\n").to compile_as_kotlin
  end
end
