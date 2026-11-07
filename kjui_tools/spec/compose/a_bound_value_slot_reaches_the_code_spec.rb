# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'stringio'
require 'compose/compose_builder'
require 'compose/data_model_updater'
require 'core/stage_failures'
require_relative '../support/kotlin_compiler'

# A drawable the layout names by a binding was frozen into a resource name:
# `R.drawable.img___v_`, which no app carries, so the build stopped (CheckBox,
# IconLabel and NetworkImage). A bound userAgent and html were the text "@{v}".
# A binding is now the data's value: a drawable looked up by its name at run
# time, a String handed over as it is. A written value is written as it was.
RSpec.describe 'a bound value slot on the Android build path' do
  def built(node, data: { 'name' => 'v', 'class' => 'String', 'defaultValue' => '' })
    Dir.mktmpdir('kjui_value_slot') do |dir|
      Dir.chdir(dir) do
        path = File.join(dir, 'probe.json')
        File.write(path, JSON.generate(
                           'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
                           'child' => [{ 'data' => [data] }, node.merge('width' => 'matchParent', 'height' => 40)]
                         ))
        err = StringIO.new
        orig = $stderr
        $stderr = err
        begin
          KjuiTools::Compose::ComposeBuilder.new.build_file(path)
        ensure
          $stderr = orig
        end
        yield Dir.glob(File.join(dir, '**', '*GeneratedView.kt')).map { |f| File.read(f) }.join("\n")
      end
    end
  end

  before { JsonUI::StageFailures.clear! }

  BOUND_DRAWABLE_LOOKUP = 'LocalContext.current.let { ctx -> ctx.resources.getIdentifier(data.v, "drawable", ctx.packageName) }'

  # [node without the slot, slot, what a written 'w_name' reaches]
  BOUND_DRAWABLE_CASES = [
    [{ 'type' => 'CheckBox', 'id' => 'c', 'text' => 'x' }, 'icon', 'R.drawable.w_name'],
    [{ 'type' => 'CheckBox', 'id' => 'c', 'text' => 'x' }, 'src', 'R.drawable.w_name'],
    [{ 'type' => 'CheckBox', 'id' => 'c', 'text' => 'x' }, 'selectedIcon', 'R.drawable.w_name'],
    [{ 'type' => 'IconLabel', 'id' => 'il', 'text' => 'x' }, 'icon_on', 'painterResource(id = R.drawable.w_name)'],
    [{ 'type' => 'IconLabel', 'id' => 'il', 'text' => 'x' }, 'icon_off', 'painterResource(id = R.drawable.w_name)'],
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'hint', 'placeholder = painterResource(R.drawable.w_name)'],
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'placeholder', 'placeholder = painterResource(R.drawable.w_name)'],
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'loadingImage', 'placeholder = painterResource(R.drawable.w_name)'],
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'errorImage', 'error = painterResource(R.drawable.w_name)'],
    [{ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png' }, 'defaultImage', 'fallback = painterResource(R.drawable.w_name)']
  ].freeze

  BOUND_DRAWABLE_CASES.each do |node, slot, written|
    it "#{node['type']}.#{slot}: a bound name is looked up at run time" do
      built(node.merge(slot => '@{v}')) do |kotlin|
        expect(kotlin).not_to include('@{v}')
        expect(kotlin).not_to include('img___v_')
        expect(kotlin).to include(BOUND_DRAWABLE_LOOKUP)
      end
    end

    it "#{node['type']}.#{slot}: a written name is the drawable it was" do
      built(node.merge(slot => 'w_name')) do |kotlin|
        expect(kotlin).to include(written)
        expect(kotlin).not_to include('getIdentifier')
      end
    end
  end

  it 'an unknown bound name draws nothing where the slot needs a Painter, and null where it is Optional' do
    built({ 'type' => 'IconLabel', 'id' => 'il', 'text' => 'x', 'icon_off' => '@{v}' }) do |kotlin|
      expect(kotlin).to include('if (id != 0) painterResource(id = id) else androidx.compose.ui.graphics.painter.ColorPainter(')
    end
    built({ 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://example.com/a.png', 'errorImage' => '@{v}' }) do |kotlin|
      expect(kotlin).to include('if (id != 0) painterResource(id = id) else null')
    end
  end

  it 'a bound name with no default is read as an empty name' do
    built({ 'type' => 'IconLabel', 'id' => 'il', 'text' => 'x', 'icon_off' => '@{v}' },
          data: { 'name' => 'v', 'class' => 'String' }) do |kotlin|
      expect(kotlin).to include('getIdentifier((data.v ?: ""), "drawable"')
    end
  end

  it 'Image: a bound fallback under a bound src is looked up too' do
    built({ 'type' => 'Image', 'id' => 'i', 'src' => '@{v}', 'defaultImage' => '@{v}' }) do |kotlin|
      expect(kotlin).not_to include('img___v_')
      expect(kotlin).to include("else #{BOUND_DRAWABLE_LOOKUP}")
    end
  end

  # The lookup is well-typed Kotlin against the names it calls (types only:
  # the Compose compiler is not here), both where a Painter is required and
  # where the slot is Optional.
  it 'the bound drawable lookup compiles, required and Optional' do
    resolver = KjuiTools::Compose::Helpers::ResourceResolver
    required = resolver.drawable_painter('@{v}', nil)
    optional = resolver.drawable_painter('@{v}', nil, empty: 'null')
    expect(<<~KOTLIN).to compile_as_kotlin.alongside(
      import androidx.compose.ui.graphics.painter.Painter
      class Resources { fun getIdentifier(name: String, type: String, pkg: String): Int = 0 }
      class Ctx { val resources = Resources(); val packageName = "p" }
      object LocalContext { val current = Ctx() }
      fun painterResource(id: Int): Painter = Painter()
      class Data(var v: String = "")
      fun probe(data: Data): Painter = #{required}
      fun probeOptional(data: Data): Painter? = #{optional}
    KOTLIN
      'Painter.kt' => "package androidx.compose.ui.graphics.painter\nopen class Painter\n" \
                      "class ColorPainter(val color: androidx.compose.ui.graphics.Color) : Painter()\n",
      'Color.kt' => "package androidx.compose.ui.graphics\nclass Color { companion object { val Transparent = Color() } }\n"
    )
  end

  it 'Web.userAgent: a binding is the data value, set again when it moves' do
    built({ 'type' => 'Web', 'id' => 'w', 'url' => 'https://example.com', 'userAgent' => '@{v}' }) do |kotlin|
      expect(kotlin).not_to include('@{v}')
      expect(kotlin).to include('settings.userAgentString = data.v')
      expect(kotlin).to include('if (webView.settings.userAgentString != userAgent) webView.settings.userAgentString = userAgent')
    end
    built({ 'type' => 'Web', 'id' => 'w', 'url' => 'https://example.com', 'userAgent' => 'UA' }) do |kotlin|
      expect(kotlin).to include('settings.userAgentString = "UA"')
      expect(kotlin).not_to include('val userAgent')
    end
  end

  it 'Web.html: a binding is loaded, and loaded again only when it moves' do
    built({ 'type' => 'Web', 'id' => 'w', 'html' => '@{v}' }) do |kotlin|
      expect(kotlin).not_to include('@{v}')
      expect(kotlin).to include('loadDataWithBaseURL(null, data.v, "text/html", "utf-8", null)')
      expect(kotlin).to include('if (webView.tag != html) {')
    end
    built({ 'type' => 'Web', 'id' => 'w', 'html' => '<p>x</p>' }) do |kotlin|
      expect(kotlin).to include('loadDataWithBaseURL(null, "<p>x</p>", "text/html", "utf-8", null)')
      expect(kotlin).not_to include('val html')
    end
  end
end
