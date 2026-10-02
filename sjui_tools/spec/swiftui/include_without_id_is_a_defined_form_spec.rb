# frozen_string_literal: true

require 'stringio'
require 'tmpdir'
require 'json'
require 'fileutils'
require 'core/attribute_validator'
require 'cli/commands/build'
require 'swiftui/json_to_swiftui_converter'

# An include without an id is a defined form (shared/core/include_ids_fixture.json,
# design U8: "an include without an id adds none"): the partial's ids and data
# names are the screen's own. kjui and rjui accept it silently, and the
# SwiftUI code sjui generates for it is right. sjui warned on every one
# ("Include '<path>' is missing 'id'") — the condition was only "include and
# no id" — from both of its checks: `jui build`'s and the `convert` command's.
# A face that keeps `jui build` at 0 warnings could not use the form. Ticket
# sjui-include-without-id-warns-unconditionally.
#
# Each example also draws a Collection with items and no sections next to the
# include: that warning comes from the same walk, so it is the arm's proof
# that the walk ran and reached the include's siblings — without it, "no
# include warning" would read the same from a check that never ran.
RSpec.describe 'an include without an id' do
  def screen(include_node)
    {
      'type' => 'View', 'id' => 'root', 'orientation' => 'vertical',
      'child' => [
        include_node,
        { 'type' => 'Collection', 'id' => 'list', 'items' => '@{items}' }
      ]
    }
  end

  def build_warnings(json)
    build = SjuiTools::CLI::Commands::Build.allocate
    build.send(:validate_json, json, SjuiTools::Core::AttributeValidator.new(:swiftui), 'screen')
  end

  def convert_output(json)
    out = StringIO.new
    $stdout = out
    SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.send(:validate_json_tree, json, 'screen')
    out.string
  ensure
    $stdout = STDOUT
  end

  context 'on the jui build path' do
    it 'does not warn' do
      warnings = build_warnings(screen('include' => 'parts/panel'))

      expect(warnings.grep(/Collection has 'items'/).size).to eq(1)
      expect(warnings.grep(/parts\/panel/)).to be_empty
    end

    it 'does not warn under a wrapper either' do
      wrapped = { 'type' => 'View', 'id' => 'wrap', 'visibility' => '@{panelVisibility}',
                  'child' => [{ 'include' => 'parts/panel' }] }
      warnings = build_warnings(screen(wrapped))

      expect(warnings.grep(/Collection has 'items'/).size).to eq(1)
      expect(warnings.grep(/parts\/panel/)).to be_empty
    end
  end

  context 'on the convert path' do
    it 'does not warn' do
      out = convert_output(screen('include' => 'parts/panel'))

      expect(out.scan(/Collection has 'items'/).size).to eq(1)
      expect(out).not_to include('parts/panel')
    end
  end

  it 'with an id does not warn on either path' do
    json = screen('include' => 'parts/panel', 'id' => 'panel')

    expect(build_warnings(json).grep(/parts\/panel/)).to be_empty
    expect(convert_output(json)).not_to include('parts/panel')
  end

  # What the warning was standing in for: two prefix-less partials binding the
  # same data name read the screen's one property, and that compiles. (Two
  # partials whose ids meet are stopped by `jui build`'s layout-id gate, on
  # the expanded tree, on every platform — not by this check.)
  context 'what it draws' do
    include EmittedSwift

    let(:dir) { Dir.mktmpdir('include_without_id') }

    before { SjuiTools::SwiftUI::IncludeExpander.layouts_root = dir }

    after do
      SjuiTools::SwiftUI::IncludeExpander.layouts_root = nil
      FileUtils.rm_rf(dir)
    end

    def partial(name)
      FileUtils.mkdir_p(File.join(dir, 'parts'))
      File.write(File.join(dir, 'parts', "#{name}.json"), JSON.generate(
        'type' => 'View', 'id' => "#{name}_root", 'partial' => true,
        'child' => [
          { 'data' => [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => '' }] },
          { 'type' => 'Label', 'id' => "#{name}_title", 'text' => '@{title}' }
        ]
      ))
    end

    def draw(includes)
      path = File.join(dir, 'screen.json')
      File.write(path, JSON.generate('type' => 'View', 'id' => 'root', 'orientation' => 'vertical',
                                     'child' => includes))
      SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path).first.to_s
    end

    it "reads the screen's own data, unprefixed, and compiles" do
      partial('style_app')
      partial('style_book')

      code = draw([{ 'include' => 'parts/style_app' }, { 'include' => 'parts/style_book' }])

      expect(code.scan('"\(data.title)"').size).to eq(2)
      expect(compilable_view(code, data: ['var title: String = ""'])).to compile_as_swift
    end

    # The control: the same partial under an id reads the prefixed name, so
    # the scan above tells the two forms apart.
    it 'reads the prefixed name under an id' do
      partial('style_app')

      code = draw([{ 'include' => 'parts/style_app', 'id' => 'app' }])

      expect(code).to include('"\(data.appTitle)"')
      expect(code).not_to include('data.title)')
    end
  end
end
