# frozen_string_literal: true

# A generated view nobody calls is a silent hole.
#
# `kjui build` emits mechanisms INTO the generated view — the screen marker,
# and (2026-09-16) the WebView load signal's client. Both only reach the screen
# if the app renders that view. Two consumer faces, on two OSes, render a
# hand-written wrapper instead: `WebViewGeneratedView(` appears exactly once,
# at its own definition. The screen marker had already been lost the same way,
# months earlier, and the bypassing wrapper's own comment says so.
#
# So the build warns. These arms are the two directions plus the boundary that
# separates "measured zero" from "nothing to measure".
require 'compose/compose_builder'
require 'tmpdir'

RSpec.describe KjuiTools::Compose::ComposeBuilder do
  def build_with(source_path)
    b = described_class.allocate
    b.instance_variable_set(:@source_path, source_path)
    b
  end

  def warning_for(tree)
    Dir.mktmpdir do |root|
      src = File.join(root, 'src/main')
      tree.each do |rel, body|
        path = File.join(src, rel)
        FileUtils.mkdir_p(File.dirname(path))
        File.write(path, body)
      end
      generated = File.join(src, 'views/web_view/WebViewGeneratedView.kt')
      sink = StringIO.new
      $stdout = sink
      begin
        build_with(root).send(:warn_if_generated_view_is_unreferenced,
                              'WebView', generated, 'src/main')
      ensure
        $stdout = STDOUT
      end
      sink.string
    end
  end

  it 'warns when the only mention of the generated view is its own definition' do
    warning = warning_for(
      'views/web_view/WebViewGeneratedView.kt' => "@Composable\nfun WebViewGeneratedView() {}\n",
      'views/web_view/WebViewView.kt' => "@Composable\nfun WebViewView() { /* hand written */ }\n",
      'MainActivity.kt' => "fun main() { WebViewView() }\n"
    )
    expect(warning).to include('WebViewGeneratedView is never referenced')
    expect(warning).to include('2 other Kotlin file(s)')   # the count is measured, not assumed
  end

  it 'stays silent when something calls it' do
    warning = warning_for(
      'views/web_view/WebViewGeneratedView.kt' => "fun WebViewGeneratedView() {}\n",
      'MainActivity.kt' => "fun main() { WebViewGeneratedView() }\n"
    )
    expect(warning).to eq('')
  end

  # ⚠️ THE FALSE ALARM THIS AVOIDS. A view reached through a registry or a
  # function reference is referenced; a `Name(`-shaped predicate would call it
  # dead and teach readers to ignore the line.
  it 'counts a function reference as a reference' do
    warning = warning_for(
      'views/web_view/WebViewGeneratedView.kt' => "fun WebViewGeneratedView() {}\n",
      'Registry.kt' => "val screens = mapOf(\"web\" to ::WebViewGeneratedView)\n"
    )
    expect(warning).to eq('')
  end

  # 🔻 The boundary: zero files read is "unmeasured", not "unreferenced".
  it 'says nothing when there is no other Kotlin file to read' do
    warning = warning_for(
      'views/web_view/WebViewGeneratedView.kt' => "fun WebViewGeneratedView() {}\n"
    )
    expect(warning).to eq('')
  end

  it 'says nothing when the source directory does not exist' do
    Dir.mktmpdir do |root|
      sink = StringIO.new
      $stdout = sink
      begin
        build_with(root).send(:warn_if_generated_view_is_unreferenced,
                              'WebView', File.join(root, 'nope.kt'), 'src/main')
      ensure
        $stdout = STDOUT
      end
      expect(sink.string).to eq('')
    end
  end
end
