# frozen_string_literal: true

require 'json'
require 'stringio'
require 'react/react_generator'
require 'react/data_model_generator'
require_relative '../support/typescript_compiler'

# A value slot written as a binding was pasted into the markup: `data-testid="@{v}"`,
# `<img src="@{v}">`, a class named `@{v}`, `allow="@{v}; fullscreen"`. The page
# carried the characters. A bound onclick was an error comment, and the Data
# declared a property named `@{v}`, which is not JavaScript: the Data file did not
# parse. A binding is now the data's value at run time; a bound onclick stays
# refused (it takes a selector name) and declares nothing. A written value is
# written as it was.
RSpec.describe 'a bound value slot on the web build path' do
  def size
    { 'width' => 'matchParent', 'height' => 40 }
  end

  def json_for(node)
    { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => [{ 'data' => [{ 'name' => 'v', 'class' => 'String', 'defaultValue' => '' },
                               { 'name' => 'tap', 'class' => '(() -> Void)?' }] }, node.merge(size)] }
  end

  def built(node)
    err = StringIO.new
    orig = $stderr
    $stderr = err
    begin
      jsx = RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true }).generate('Probe', json_for(node)).to_s
    ensure
      $stderr = orig
    end
    yield jsx, err.string
  end

  # [node without the slot, slot, what the binding reaches, what a written 'w_name' reaches]
  BOUND_VALUE_CASES = [
    [{ 'type' => 'View', 'id' => 'x' }, 'testId', 'data-testid={data.v}', 'data-testid="w_name"'],
    [{ 'type' => 'Label', 'id' => 'x', 'text' => 'x' }, 'testId', 'data-testid={data.v}', 'data-testid="w_name"'],
    [{ 'type' => 'View', 'id' => 'x' }, 'className', "${data.v ?? ''}", ' w_name'],
    [{ 'type' => 'Button', 'id' => 'x', 'text' => 'x' }, 'className', "${data.v ?? ''}", ' w_name'],
    [{ 'type' => 'Button', 'id' => 'x', 'text' => 'x' }, 'href', '={data.v}><button', '="w_name"><button'],
    [{ 'type' => 'CheckBox', 'id' => 'x', 'text' => 'x' }, 'icon', '<img src={data.v}', '<img src="w_name"'],
    [{ 'type' => 'CheckBox', 'id' => 'x', 'text' => 'x' }, 'selectedIcon', '<img src={data.v}', '<img src="w_name"'],
    [{ 'type' => 'Radio', 'id' => 'x', 'text' => 'x', 'group' => 'g' }, 'icon', '<img src={data.v}', '<img src="w_name"'],
    [{ 'type' => 'NetworkImage', 'id' => 'x', 'url' => 'https://example.com/a.png' }, 'errorImage', 'errorImage={data.v}', 'errorImage="w_name"'],
    [{ 'type' => 'NetworkImage', 'id' => 'x', 'url' => 'https://example.com/a.png' }, 'defaultImage', 'defaultImage={data.v}', 'defaultImage="w_name"'],
    [{ 'type' => 'TextField', 'id' => 'x', 'text' => '@{v}' }, 'name', 'name={data.v}', 'name="w_name"'],
    [{ 'type' => 'TextField', 'id' => 'x', 'text' => '@{v}' }, 'pattern', 'pattern={data.v}', 'pattern="w_name"'],
    [{ 'type' => 'TextView', 'id' => 'x', 'text' => '@{v}' }, 'name', 'name={data.v}', 'name="w_name"'],
    [{ 'type' => 'TextView', 'id' => 'x', 'text' => '@{v}' }, 'pattern', 'new RegExp(`^(?:${data.v})$`)', "new RegExp('^(?:w_name)$')"],
    [{ 'type' => 'TextField', 'id' => 'x', 'text' => '@{v}' }, 'hintFont', 'placeholder:[font-family:var(--jui-hint-font)]', 'placeholder:[font-family:w_name]'],
    [{ 'type' => 'Slider', 'id' => 'x' }, 'trackTintColor', '[&::-webkit-slider-runnable-track]:bg-[var(--jui-track-tint)]', nil],
    [{ 'type' => 'Web', 'id' => 'x', 'url' => 'https://example.com' }, 'title', 'title={data.v}', 'title="w_name"'],
    [{ 'type' => 'Web', 'id' => 'x', 'url' => 'https://example.com' }, 'allow', "allow={`${data.v ?? ''}; fullscreen`}", 'allow="w_name; fullscreen"']
  ].freeze

  BOUND_VALUE_CASES.each do |node, slot, bound, written|
    it "#{node['type']}.#{slot}: a binding is the data's value" do
      built(node.merge(slot => '@{v}')) do |jsx|
        expect(jsx).not_to include('@{v}')
        expect(jsx).to include(bound)
      end
    end

    next unless written

    it "#{node['type']}.#{slot}: a written value is what it was" do
      built(node.merge(slot => 'w_name')) { |jsx| expect(jsx).to include(written) }
    end
  end

  it 'a bound className makes the class list a template literal' do
    built({ 'type' => 'View', 'id' => 'x', 'className' => '@{v}' }) do |jsx|
      expect(jsx).to match(/className=\{`[^`]*\$\{data\.v \?\? ''\}[^`]*`\}/)
      expect(jsx).not_to match(/className="[^"]*\$\{/)
    end
  end

  it 'a bound hintFont reaches the placeholder through a custom property' do
    built({ 'type' => 'TextField', 'id' => 'x', 'text' => '@{v}', 'hintFont' => '@{v}' }) do |jsx|
      expect(jsx).to include("'--jui-hint-font': data.v")
    end
  end

  # The lowercase onclick takes the bare selector name only (binding_semantics
  # contexts.nameRef): a binding there stays refused, and only the Data changes.
  it 'a bound onclick is no call' do
    built({ 'type' => 'View', 'id' => 'x', 'onclick' => '@{tap}' }) do |jsx|
      expect(jsx).not_to include('data.tap')
      expect(jsx).not_to include('onClick={')
    end
  end

  it 'in the array face only the bound name goes, with one warning' do
    built({ 'type' => 'View', 'id' => 'x', 'onclick' => ['confPush', '@{tap}'] }) do |jsx, err|
      expect(jsx).to include('data.confPush?.()')
      expect(jsx).not_to include('data.tap')
      expect(err.scan("'onclick' takes a bare handler name, not a binding (@{tap})").size).to eq(1)
    end
  end

  it 'a written onclick is the selector it was' do
    built({ 'type' => 'View', 'id' => 'x', 'onclick' => 'onTap' }) { |jsx| expect(jsx).to include('data.onTap?.(') }
  end

  it 'the Data declares no property named after a bound onclick' do
    data = RjuiTools::React::DataModelGenerator.new.send(:extract_onclick_actions, json_for('type' => 'View', 'onclick' => '@{tap}'))
    expect(data.to_a).to eq([])
    written = RjuiTools::React::DataModelGenerator.new.send(:extract_onclick_actions, json_for('type' => 'View', 'onclick' => 'onTap'))
    expect(written.to_a).to eq(['onTap'])
  end

  # A Data property named `@{tap}` did not parse; the bindings in attributes did
  # not either where they reached code position.
  it 'the generated file parses', :typescript_compile do
    built({ 'type' => 'View', 'id' => 'x', 'onclick' => '@{tap}', 'className' => '@{v}', 'testId' => '@{v}' }) do |jsx|
      expect("// @ts-nocheck\n#{jsx}").to compile_as_typescript
    end
  end
end
