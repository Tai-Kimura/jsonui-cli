# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'stringio'
require 'compose/compose_builder'
require 'compose/data_model_updater'
require 'core/stage_failures'
require_relative '../support/kotlin_compiler'

# An attribute that names something the generator has to know — the view another
# is placed against, a Radio's group, the field focus moves to, an Embed's screen
# — has no value yet when it is a binding. Android pasted it in:
# `top.linkTo(@{v}.bottom)` and `var selected@{v}` do not compile, and
# `radioGroups["@{g}"]` made the characters the group's name. Every face now reads
# it as absent and says so once (LayoutValidator.drop_name_slot_bindings!), on the
# tree `build_file` draws: styles merged, includes expanded.
RSpec.describe 'a bound name slot on the Android build path' do
  def built(*nodes, name: 'probe')
    Dir.mktmpdir('kjui_name_slot') do |dir|
      Dir.chdir(dir) do
        path = File.join(dir, "#{name}.json")
        File.write(path, JSON.generate(
                           'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
                           'child' => [{ 'data' => [{ 'name' => 'v', 'class' => 'String', 'defaultValue' => '' }] }, *nodes]
                         ))
        err = StringIO.new
        orig = $stderr
        $stderr = err
        begin
          KjuiTools::Compose::ComposeBuilder.new.build_file(path)
        ensure
          $stderr = orig
        end
        kotlin = Dir.glob(File.join(dir, '**', '*GeneratedView.kt')).map { |f| File.read(f) }.join("\n")
        yield kotlin, err.string
      end
    end
  end

  before { JsonUI::StageFailures.clear! }

  def size
    { 'width' => 'matchParent', 'height' => 40 }
  end

  %w[alignTopOfView alignBottomOfView alignLeftOfView alignRightOfView alignTopView alignBottomView
     alignLeftView alignRightView alignCenterHorizontalView alignCenterVerticalView].each do |slot|
    it "#{slot}: no linkTo against the binding, and a warning" do
      built({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', slot => '@{v}' }.merge(size)) do |kotlin, err|
        expect(kotlin).not_to be_empty
        expect(kotlin).not_to include('@{v}')
        expect(err).to include("'#{slot}' names a view and does not take a binding (@{v}); ignored.")
      end
    end
  end

  it 'a written view name is still linked' do
    built({ 'type' => 'Label', 'id' => 'anchor', 'text' => 'a' }.merge(size),
          { 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'alignBottomOfView' => 'anchor' }.merge(size)) do |kotlin, err|
      expect(kotlin).to include('top.linkTo(anchor.bottom')
      expect(err).not_to include('does not take')
    end
  end

  it 'Radio.group: the characters are not the group, and it reads as no group' do
    built({ 'type' => 'Radio', 'id' => 'r', 'text' => 'x', 'group' => '@{v}' }.merge(size)) do |bound, err|
      expect(bound).not_to include('@{v}')
      expect(err).to include("'group' names a radio group and does not take a binding (@{v}); ignored.")
      built({ 'type' => 'Radio', 'id' => 'r', 'text' => 'x' }.merge(size)) do |absent, _|
        # The path of the temp file is in the emit several ways; the group is what is compared.
        expect(bound.scan(/radioGroups\[[^\]]*\]/).uniq).to eq(absent.scan(/radioGroups\[[^\]]*\]/).uniq)
        expect(bound.scan(/radioGroups\[[^\]]*\]/)).not_to be_empty
      end
    end
  end

  it 'a written group is untouched' do
    built({ 'type' => 'Radio', 'id' => 'r', 'text' => 'x', 'group' => 'written' }.merge(size)) do |kotlin, err|
      expect(kotlin).to include('radioGroups["written"]')
      expect(err).not_to include('does not take')
    end
  end

  it 'an override in `responsive` is taken off too' do
    node = { 'type' => 'Label', 'id' => 'l', 'text' => 'x',
             'responsive' => { 'compact' => { 'alignTopOfView' => '@{v}' } } }.merge(size)
    built(node) do |kotlin, err|
      expect(kotlin).not_to include('@{v}')
      expect(err).to include("'alignTopOfView' names a view")
    end
  end

  it 'Embed.screen and TextField.nextFocus say so once, through the one rule' do
    built({ 'type' => 'Embed', 'id' => 'e', 'screen' => '@{v}' }.merge(size),
          { 'type' => 'TextField', 'id' => 't', 'text' => '@{v}', 'nextFocus' => '@{v}' }.merge(size)) do |kotlin, err|
      expect(kotlin).not_to include('focusRequester_@{v}')
      expect(err.scan("'screen' names a screen").size).to eq(1)
      expect(err.scan("'nextFocus' names a field").size).to eq(1)
    end
  end

  # The other two ways a node gets into the tree `build_file` draws.
  def in_project(files)
    Dir.mktmpdir('kjui_name_slot') do |dir|
      Dir.chdir(dir) do
        files.each { |name, body| File.write(File.join(dir, "#{name}.json"), JSON.generate(body)) }
        err = StringIO.new
        orig = $stderr
        $stderr = err
        begin
          builder = KjuiTools::Compose::ComposeBuilder.new
          builder.instance_variable_set(:@layouts_dir, dir)
          builder.build_file(File.join(dir, 'probe.json'))
        ensure
          $stderr = orig
        end
        yield Dir.glob(File.join(dir, '**', '*.kt')).map { |f| File.read(f) }.join("\n"), err.string
      end
    end
  end

  def screen_root(*nodes)
    { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'data' => [{ 'name' => 'v', 'class' => 'String', 'defaultValue' => '' }], 'child' => nodes }
  end

  it 'a slot inside an included layout is taken off the expanded tree' do
    part = screen_root({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'alignTopOfView' => '@{v}' }.merge(size))
    in_project('probe' => screen_root({ 'include' => 'part' }), 'part' => part.merge('partial' => true)) do |kotlin, err|
      expect(kotlin).to include('GENERATED_CODE_START')
      expect(kotlin).not_to include('linkTo(@{')
      expect(err).to include("'alignTopOfView' names a view")
    end
  end

  it 'a slot in a variant file is taken off too' do
    base = screen_root({ 'type' => 'Label', 'id' => 'l', 'text' => 'x' }.merge(size))
    variant = { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
                'child' => [{ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'alignLeftView' => '@{v}' }.merge(size)] }
    in_project('probe' => base, 'probe@regular' => variant) do |kotlin, err|
      expect(kotlin).to include('VariantGeneratedView')
      expect(kotlin).not_to include('linkTo(@{')
      expect(err).to include("'alignLeftView' names a view")
    end
  end

  it 'the Data does not declare a property named after the binding' do
    props = KjuiTools::Compose::DataModelUpdater.new.send(
      :extract_data_properties, { 'type' => 'Radio', 'id' => 'r', 'group' => '@{v}' }, [], {}
    )
    expect(props.map { |p| p['name'] }).to eq(['selectedRadiogroup'])
  end

  it 'the Data it declares compiles' do
    props = KjuiTools::Compose::DataModelUpdater.new.send(
      :extract_data_properties, { 'type' => 'Radio', 'id' => 'r', 'group' => '@{v}' }, [], {}
    )
    expect("class Data(#{props.map { |p| "var #{p['name']}: String = \"\"" }.join(', ')})").to compile_as_kotlin
  end
end
