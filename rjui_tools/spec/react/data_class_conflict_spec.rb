# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'stringio'

require_relative '../spec_helper'
require 'core/data_class_conflict'
require 'react/data_model_generator'

# One data name declared twice in the Data type rjui builds for a layout — its
# root's data, its data-only nodes, and (from jsonui-cli 1.9.6) its includes
# expanded inline, as sjui / kjui build theirs. Until 1.9.6 rjui wrote every
# declaration: the interface and createXxxData() each carried the name twice,
# which tsc rejects whether or not the types agree (TS2300, TS1117; ticket
# rjui-data-name-declared-twice-is-written-twice). It now keeps the first in
# document order, the root's data first, as sjui / kjui do, and says so when
# the types differ (ruling 2026-10-02: a warning on every face, not an error;
# data_class_conflict.rb — the same text as sjui / kjui).
#
# Types are compared as TypeScript writes them, so `Int` and `Float` (both
# `number`) are one type here although they are two on sjui / kjui.
#
# Across an include: until 1.9.6 a partial was its own component with its own
# Data type and the screen handed it nothing, so a screen and a partial
# declaring one name never met here. Ruling 2026-10-02 (an include draws the
# including layout's data — design-philosophy: the parent owns the VM): the
# screen's Data type carries its partials' declarations, so they meet, and
# warn, as on sjui / kjui (ticket rjui-include-does-not-read-the-screens-data).
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

  # Across an include: one Data type now — the screen's declaration is kept
  # and the partial's, with another type, is said out loud. The partial's own
  # Data type is still its own (it declares the name once).
  it 'warns across an include, as sjui / kjui do' do
    layout('parts/panel', 'type' => 'View', 'id' => 'panel_root', 'data' => [item('Int', 7)],
                          'child' => [{ 'type' => 'Label', 'id' => 'p', 'text' => '@{title}' }])
    layout('screen', 'type' => 'View', 'id' => 'root', 'data' => [item('String', 'a')],
                     'child' => [{ 'include' => 'parts/panel' }])

    printed, data = build
    partial_printed, partial = build('parts/panel')

    expect(warnings(printed)).to eq([JsonUIShared::DataClassConflict.message('screen.json', 'title', 'string', 'number')])
    expect(warnings(partial_printed)).to be_empty
    expect(members(data)).to eq([1, 1])
    expect(data).to include('title: string;')
    expect(partial).to include('title: number;')
  end

  # The boundary of that: under an id the partial's name is prefixed, so it
  # is another name in the screen's Data type and nothing meets.
  it 'says nothing across an include with an id' do
    layout('parts/panel', 'type' => 'View', 'id' => 'panel_root', 'data' => [item('Int', 7)],
                          'child' => [{ 'type' => 'Label', 'id' => 'p', 'text' => '@{title}' }])
    layout('screen', 'type' => 'View', 'id' => 'root', 'data' => [item('String', 'a')],
                     'child' => [{ 'include' => 'parts/panel', 'id' => 'panel' }])

    printed, data = build

    expect(warnings(printed)).to be_empty
    expect(data).to include('title: string;', 'panelTitle: number;')
  end
end
