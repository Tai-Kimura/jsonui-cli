# frozen_string_literal: true

require 'stringio'
require 'core/logger'
require 'core/attribute_types'
require 'react/react_generator'
require 'react/generators/converter_generator'
require_relative '../../support/typescript_compiler'

# The DOM id a converter writes, under an include with an id (design U8) and
# for a bound id (`id: "@{field}"`): BaseConverter#build_id_attr gives both,
# and every built-in converter writes the id through it.
#
# Until jsonui-cli 2.5.32 the converter `rjui g converter` scaffolds wrote
# `id_attr = extract_id ? %( id="#{extract_id}") : ''` — the id as written —
# so a partial with a custom component, included twice, gave that component
# one DOM id twice (and a bound id was the literal text `@{field}`). The
# Segment's and the TabView's buttons (`<id>_tab_<n>`) and a Collection's
# cells (`<id>_item_<n>`) had the same gap. The
# converters projects already have from that scaffold are theirs and are not
# rewritten: rjui names each one, once a build. Ticket
# rjui-generated-converter-ignores-include-id-prefix.
RSpec.describe 'a converter writes the DOM id with the include prefix and the binding' do
  EXT_INCLUDE_ID = File.expand_path('../../../lib/react/converters/extensions', __dir__)

  # The line the scaffold wrote until 2.5.32, as the projects have it.
  OLD_ID_LINE = "id_attr = extract_id ? %( id=\"\#{extract_id}\") : ''"

  let(:off) { { 'use_tailwind' => true, 'typescript' => true } }
  let(:on) { off.merge('_include_id_prefix' => true) }

  def scaffold(name)
    code = RjuiTools::React::Generators::ConverterGenerator
           .new(name, { attributes: {}, is_container: false }, {}, 'spec').send(:converter_template)
    code = code.gsub(/require_relative '([^']+)'/) { "require '#{File.expand_path(Regexp.last_match(1), EXT_INCLUDE_ID)}'" }
    yield code if block_given?
    eval(code, TOPLEVEL_BINDING, "#{name.gsub(/([a-z])([A-Z])/, '\1_\2').downcase}_converter.rb") # rubocop:disable Security/Eval
    RjuiTools::React::Converters::Extensions.const_get("#{name}Converter")
  end

  # [jsx, what rjui printed]
  def run(klass, node, config)
    said = StringIO.new
    saved = $stdout
    $stdout = said
    jsx = klass.new(node, config).convert_node(0)
    [jsx, said.string]
  ensure
    $stdout = saved
  end

  before do
    base = RjuiTools::React::Converters::BaseConverter
    base.reset_id_written_as_written_named! if base.respond_to?(:reset_id_written_as_written_named!)
  end

  describe 'the scaffold' do
    it 'writes `id_attr = build_id_attr`, not the id as written' do
      code = RjuiTools::React::Generators::ConverterGenerator
             .new('IdLineProbe', { attributes: {}, is_container: false }, {}, 'spec').send(:converter_template)
      expect(code).to include('id_attr = build_id_attr')
      expect(code).not_to include(OLD_ID_LINE)
    end

    it "under an include with an id, the id takes the include's prefix" do
      klass = scaffold('IncludeIdPicker')
      jsx, said = run(klass, { 'type' => 'IncludeIdPicker', 'id' => 'csv_file_picker' }, on)
      expect(jsx).to include('id={jsonuiIncludeId(idPrefix, "csv_file_picker")}')
      expect(jsx).not_to include('id="csv_file_picker"')
      expect(said).not_to include('[converter-id]')
    end

    it 'a bound id is the bound value, with the prefix decision on and off' do
      klass = scaffold('BoundIdPicker')
      [on, off].each do |config|
        jsx, = run(klass, { 'type' => 'BoundIdPicker', 'id' => '@{picker_id}' }, config)
        expect(jsx).to include('id={String(data.picker_id)}')
        expect(jsx).not_to include('@{picker_id}')
      end
    end

    it 'control: off, a literal id is the literal it always was' do
      klass = scaffold('OffIdPicker')
      jsx, said = run(klass, { 'type' => 'OffIdPicker', 'id' => 'csv_file_picker' }, off)
      expect(jsx).to include('id="csv_file_picker"')
      expect(said).to eq('')
    end

    it 'the component with the scaffolded converter in it type-checks under --strict' do
      scaffold('TscIdPicker')
      partial = { 'type' => 'View', 'id' => 'card_root',
                  'child' => [{ 'type' => 'TscIdPicker', 'id' => 'csv_file_picker' },
                              { 'type' => 'TscIdPicker', 'id' => '@{picker_id}' }] }
      config = on.merge('_extension_converters' => {})
      generator = RjuiTools::React::ReactGenerator.new(config)
      generator.instance_variable_get(:@extension_converters)['TscIdPicker'] =
        RjuiTools::React::Converters::Extensions::TscIdPickerConverter
      out = generator.generate('Card', partial)
      expect(out).to include('id={jsonuiIncludeId(idPrefix, "csv_file_picker")}')
      expect(out).to match(/\{ data(?:: dataProp)?, id, idPrefix \}/)
      body = out.lines.reject { |l| l.start_with?('import ') }.join
      expect(body).to compile_as_typescript.with_ambient(<<~TS)
        declare function jsonuiIncludeId(prefix: string | undefined, name: string): string;
        declare const TscIdPicker: (props: { id?: string; className?: string }) => JSX.Element;
        interface CardData { picker_id?: string }
        declare function createCardData(): CardData;
        declare function useStringManager(): Record<string, string>;
      TS
    end
  end

  describe 'a converter a project already has from the old scaffold' do
    def old_scaffold(name)
      scaffold(name) { |code| code.sub!('id_attr = build_id_attr', OLD_ID_LINE) || raise('the line is not in the scaffold') }
    end

    it 'is not rewritten — rjui names it, once a build, with the line to write' do
      klass = old_scaffold('OldIdPicker')
      jsx, said = run(klass, { 'type' => 'OldIdPicker', 'id' => 'csv_file_picker' }, on)
      expect(jsx).to include('id="csv_file_picker"')
      lines = said.lines.grep(/\[converter-id\]/)
      expect(lines.size).to eq(1)
      expect(lines.first).to include('[WARN]')
      expect(lines.first).to include('old_id_picker_converter.rb (OldIdPickerConverter)')
      expect(lines.first).to include('id "csv_file_picker"')
      expect(lines.first).to include('`id_attr = build_id_attr`')

      _, again = run(klass, { 'type' => 'OldIdPicker', 'id' => 'other_picker' }, on)
      expect(again).not_to include('[converter-id]')

      RjuiTools::React::Converters::BaseConverter.reset_id_written_as_written_named!
      _, next_build = run(klass, { 'type' => 'OldIdPicker', 'id' => 'csv_file_picker' }, on)
      expect(next_build).to include('[converter-id]')
    end

    it 'names a bound id written as its literal text, with the prefix decision off too' do
      klass = old_scaffold('OldBoundPicker')
      _, said = run(klass, { 'type' => 'OldBoundPicker', 'id' => '@{picker_id}' }, off)
      expect(said).to include('[converter-id]')
      expect(said).to include('a bound id (@{picker_id})')
    end

    it 'control: nothing is said where the id it writes is the right one (off, a literal id; no id)' do
      klass = old_scaffold('OldQuietPicker')
      [[{ 'type' => 'OldQuietPicker', 'id' => 'csv_file_picker' }, off],
       [{ 'type' => 'OldQuietPicker' }, on]].each do |node, config|
        _, said = run(klass, node, config)
        expect(said).not_to include('[converter-id]')
      end
    end

    it "control: a built-in converter is not named (it is rjui's, and writes build_id_attr)" do
      _, said = run(RjuiTools::React::Converters::LabelConverter, { 'type' => 'Label', 'id' => 'x', 'text' => 't' }, on)
      expect(said).not_to include('[converter-id]')
    end
  end

  describe "a Collection's cells (`<id>_item_<n>`)" do
    let(:collection) { { 'type' => 'Collection', 'id' => 'rows', 'items' => '@{rows}', 'cellClasses' => ['RowCell'] } }

    it "under an include with an id, take the include's prefix before the suffix, as on iOS and Android" do
      jsx, = run(RjuiTools::React::Converters::CollectionConverter, collection, on)
      expect(jsx).to include('id={`${jsonuiIncludeId(idPrefix, "rows")}_item_${cellIndex}`}')
      expect(jsx).not_to include('id={`rows_item_')
    end

    it 'control: off, the ids they always had' do
      jsx, = run(RjuiTools::React::Converters::CollectionConverter, collection, off)
      expect(jsx).to include('id={`rows_item_${cellIndex}`}')
    end
  end

  describe "the Segment's and the TabView's buttons (`<id>_tab_<n>`)" do
    let(:segment) { { 'type' => 'Segment', 'id' => 'kind_seg', 'items' => %w[a b] } }
    let(:tabs) do
      { 'type' => 'TabView', 'id' => 'main_tabs',
        'tabs' => [{ 'title' => 'A', 'view' => 'a' }, { 'title' => 'B', 'view' => 'b' }] }
    end

    it "under an include with an id, take the include's prefix before the suffix (`heroKindSeg_tab_0`, as on iOS and Android)" do
      [[RjuiTools::React::Converters::SegmentConverter, segment, 'kind_seg'],
       [RjuiTools::React::Converters::TabViewConverter, tabs, 'main_tabs']].each do |klass, node, id|
        jsx, = run(klass, node, on)
        expect(jsx).to include("id={`${jsonuiIncludeId(idPrefix, \"#{id}\")}_tab_0`}")
        expect(jsx).to include("id={`${jsonuiIncludeId(idPrefix, \"#{id}\")}_tab_1`}")
        expect(jsx).not_to include("id=\"#{id}_tab_0\"")
      end
    end

    it 'control: off, the ids they always had' do
      [[RjuiTools::React::Converters::SegmentConverter, segment, 'kind_seg'],
       [RjuiTools::React::Converters::TabViewConverter, tabs, 'main_tabs']].each do |klass, node, id|
        jsx, = run(klass, node, off)
        expect(jsx).to include("id=\"#{id}_tab_0\"")
        expect(jsx).to include("id=\"#{id}_tab_1\"")
      end
    end

    it 'the partial with a Segment in it type-checks under --strict, idPrefix taken' do
      partial = { 'type' => 'View', 'id' => 'card_root', 'child' => [segment] }
      out = RjuiTools::React::ReactGenerator.new(on).generate('SegCard', partial)
      expect(out).to match(/\{ data(?:: dataProp)?, id, idPrefix \}/)
      body = out.lines.reject { |l| l.start_with?('import ') }.join
      expect(body).to compile_as_typescript.with_ambient(<<~TS)
        declare function jsonuiIncludeId(prefix: string | undefined, name: string): string;
        declare namespace React { type ReactNode = unknown }
        declare function useState<T>(initial: T): [T, (value: T) => void];
        interface SegCardData {}
        declare function useStringManager(): Record<string, string>;
      TS
    end
  end
end
