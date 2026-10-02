# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'stringio'

require_relative '../spec_helper'
require 'core/data_class_conflict'
require 'react/data_model_generator'

# One data name declared twice in the Data type rjui builds for a layout file
# — its root's data and its data-only nodes. Until jsonui-cli 1.9.6 rjui
# wrote every declaration: the interface and createXxxData() each carried the
# name twice, which tsc rejects whether or not the types agree (TS2300,
# TS1117; ticket rjui-data-name-declared-twice-is-written-twice). It now keeps
# the first in document order, the root's data first, as sjui / kjui do, and
# says so when the types differ (ruling 2026-10-02: a warning on every face,
# not an error; data_class_conflict.rb — the same text as sjui / kjui).
#
# Types are compared as TypeScript writes them, so `Int` and `Float` (both
# `number`) are one type here although they are two on sjui / kjui.
#
# An include is NOT where two declarations meet on this face: a partial is its
# own component with its own Data type (createXxxData()), and the screen hands
# it data only through the include's `data` map. So a screen and a partial
# declaring one name with two types are two Data types here, and say nothing —
# on sjui / kjui, which expand includes into the screen's Data type, they warn.
RSpec.describe 'a data name declared twice (rjui)' do
  let(:dir) { Dir.mktmpdir('data_class_conflict') }

  before do
    %w[Layouts/parts Data Styles].each { |d| FileUtils.mkdir_p(File.join(dir, d)) }
    allow(RjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
      'source_path' => dir, 'layouts_directory' => 'Layouts', 'data_directory' => 'Data',
      'styles_directory' => 'Styles', 'typescript' => true
    )
  end

  after { FileUtils.rm_rf(dir) }

  def layout(name, tree)
    File.write(File.join(dir, 'Layouts', "#{name}.json"), JSON.generate(tree))
  end

  def item(klass, default)
    { 'name' => 'title', 'class' => klass, 'defaultValue' => default }
  end

  # The root declares first, its data-only child second.
  def screen(root_item, child_item)
    layout('screen', 'type' => 'View', 'id' => 'root', 'data' => [root_item],
                     'child' => [{ 'data' => [child_item] }, { 'type' => 'Label', 'id' => 'l', 'text' => '@{title}' }])
  end

  # [printed, the Data file of `name`]
  def build(name = 'screen')
    out = StringIO.new
    $stdout = out
    RjuiTools::React::DataModelGenerator.new.send(:process_json_file, File.join(dir, 'Layouts', "#{name}.json"))
    stem = name.split('/').last.split('_').map(&:capitalize).join
    [out.string.gsub(/\e\[[0-9;]*m/, ''), File.read(File.join(dir, 'Data', "#{stem}Data.ts"))]
  ensure
    $stdout = STDOUT
  end

  def warnings(printed)
    printed.lines.map(&:strip).grep(/\AWARNING: .*data property 'title' is declared as/)
  end

  # The name, once in the interface and once in createXxxData().
  def members(data)
    [data.scan(/^\s*title\??: (?!")/).size, data.scan(/^\s*title: "/).size + data.scan(/^\s*title: \d/).size]
  end

  it 'with two types: warns once, keeps the root\'s, writes it once, and compiles' do
    screen(item('String', 'a'), item('Int', 7))

    printed, data = build

    expect(warnings(printed)).to eq([JsonUIShared::DataClassConflict.message('screen.json', 'title', 'string', 'number')])
    expect(members(data)).to eq([1, 1])
    expect(data).to include('title: string;', 'title: "a"')
    expect(data).to compile_as_typescript
  end

  it 'with one type: says nothing, writes it once, and compiles' do
    screen(item('String', 'a'), item('String', 'b'))

    printed, data = build

    expect(warnings(printed)).to be_empty
    expect(members(data)).to eq([1, 1])
    expect(data).to include('title: "a"')
    expect(data).to compile_as_typescript
  end

  it 'compares the type it writes, not the spelling' do
    screen(item('Int', 1), item('Float', 2))

    printed, data = build

    expect(warnings(printed)).to be_empty
    expect(data).to include('title: number;', 'title: 1')
  end

  # The compiler's own control: the shape rjui wrote until 1.9.6 — the
  # member and the initial value twice — is what tsc rejects, so the two
  # `compile_as_typescript` arms above read the fix and not a lenient tsc.
  it 'writes what the name twice would not compile as' do
    layout('screen', 'type' => 'View', 'id' => 'root', 'data' => [item('String', 'a')])

    data = build.last.sub(/^(\s*title: string;\n)/) { "#{$1}#{$1}" }.sub(/^(\s*title: "a",\n)/) { "#{$1}#{$1}" }

    expect(members(data)).to eq([2, 2])
    expect(data).not_to compile_as_typescript
  end

  # The boundary: across an include, two Data types — nothing to say.
  it 'says nothing across an include' do
    layout('parts/panel', 'type' => 'View', 'id' => 'panel_root', 'data' => [item('Int', 7)],
                          'child' => [{ 'type' => 'Label', 'id' => 'p', 'text' => '@{title}' }])
    layout('screen', 'type' => 'View', 'id' => 'root', 'data' => [item('String', 'a')],
                     'child' => [{ 'include' => 'parts/panel' }])

    printed, data = build
    partial_printed, partial = build('parts/panel')

    expect(warnings(printed) + warnings(partial_printed)).to be_empty
    expect(data).to include('title: string;')
    expect(partial).to include('title: number;')
  end
end
