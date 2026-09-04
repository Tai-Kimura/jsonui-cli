# frozen_string_literal: true

# An object entry is not a Segment item, and it used to reach the JSX as a
# Ruby Hash.
#
# `items: [{ "label": "opt_a", "value": "a" }]` emitted
# `<button …>{"label"=>"opt_a", "value"=>"a"}</button>` — `Hash#inspect`, not
# JavaScript — so `@babel/parser` rejected the generated file while the build
# exited 0 with no findings (measured 2026-09-04 on 1.8.38).
#
# What the entry SHOULD be is settled by the declaration, not by the report
# that found this. `shared/core/attribute_definitions.json` gives
# `Segment.items` no `items` sub-schema and describes "Static labels; an entry
# may be a strings key", where TabView.tabs and Collection.sections declare
# `{"type": "object"}` explicitly when they mean an object. Both dynamic
# runtimes agree: Android keeps `isJsonPrimitive` and maps the rest to null,
# iOS keeps String/NSNumber and compacts the rest away. An object entry
# renders as nothing on either.
#
# So the generator drops it too, and says which entry it dropped. Taking
# `label` — the first fix written here — would have given meaning to an input
# the SSoT does not declare; that decision belongs to the declaration.
#
# The string form was never broken. (The report said string entries are not
# resolved as strings keys; measured with the key in the file the resolver
# actually reads — `<layouts_directory>/Resources/strings.json`, not the
# per-language files — they are: `items: ["opt_a"]` emits `{$s.sampleOptA}`.)
require_relative '../../spec_helper'
require 'react/converters/segment_converter'
require 'core/attribute_validator'

RSpec.describe RjuiTools::React::Converters::SegmentConverter do
  let(:config) { { 'use_tailwind' => true } }

  def convert(items, id: 's')
    described_class.new({ 'class' => 'Segment', 'id' => id, 'items' => items }, config).convert
  end

  def emit(items, id: 's')
    out = nil
    capture = StringIO.new
    original = $stdout
    $stdout = capture
    begin
      out = convert(items, id: id)
    ensure
      $stdout = original
    end
    [out, capture.string]
  end

  describe 'an object entry' do
    it 'is dropped, as both runtimes drop it' do
      jsx, = emit([{ 'label' => 'opt_a', 'value' => 'a' }])
      expect(jsx).not_to include('<button')
    end

    it 'never puts a Ruby Hash in the JSX' do
      jsx, = emit([{ 'label' => 'opt_a', 'value' => 'a' }])
      expect(jsx).not_to include('=>')
      expect(jsx).not_to include('"label"')
    end

    it 'is named once, by the validator the build already runs' do
      # The naming lives in the validator, not here. It runs on every path
      # that reaches this converter (build / watch / hotload all go through
      # BuildCommand, which validates), and it is the side that has the
      # layout path to print. This asserts the message a build prints for a
      # dropped entry, so the drop and the message cannot drift apart —
      # both come from `non_scalar_item_indices`.
      warnings = RjuiTools::Core::AttributeValidator.new(:react).validate(
        { 'type' => 'Segment', 'id' => 's', 'items' => [{ 'label' => 'opt_a' }] }
      )
      text = warnings.join("\n")
      expect(text).to include("'items[0]'")
      expect(text).to include("in 'Segment'")
      expect(text).to include('dropped from the generated output')
    end

    it 'is dropped without the converter printing a second warning' do
      # One drop, one message. The converter used to print its own, which
      # gave the same event two wordings in one build (measured 2026-09-04).
      _jsx, printed = emit([{ 'label' => 'opt_a', 'value' => 'a' }])
      expect(printed).to eq('')
    end
  end

  describe 'what survives' do
    it 'keeps string entries and resolves them as before' do
      jsx, warnings = emit(%w[opt_a opt_b])
      expect(jsx.scan('<button').size).to eq(2)
      expect(jsx).to include('>opt_a<')
      expect(warnings).to eq('')
    end

    it 'keeps numeric entries, which the runtimes also accept' do
      jsx, = emit([1, 2])
      expect(jsx.scan('<button').size).to eq(2)
    end

    it 'renumbers the survivors so key and tab id stay consecutive' do
      # The runtimes compact (mapNotNull / compactMap). A hole here would
      # leave React keys and `{id}_tab_{n}` ids with a gap.
      jsx, = emit(['a', { 'label' => 'b' }, 'c'])
      expect(jsx.scan('<button').size).to eq(2)
      expect(jsx).to include('key={0}')
      expect(jsx).to include('key={1}')
      expect(jsx).not_to include('key={2}')
      expect(jsx).to include('id="s_tab_0"')
      expect(jsx).to include('id="s_tab_1"')
    end
  end

  describe 'a bound items' do
    # `items` is declared type array with NO binding. sjui and kjui emit
    # zero elements for `"items": "@{…}"`; measured here, rjui does too —
    # and it did so before this change, because the extraction layer hands
    # the converter `[]` for a bound array. The converter now asks the
    # shared predicate about the raw value instead of relying on that.
    it 'generates no items, and the validator names it' do
      jsx, printed = emit('@{segmentOptions}')
      expect(jsx).not_to include('<button')
      expect(printed).to eq('')

      warnings = RjuiTools::Core::AttributeValidator.new(:react).validate(
        { 'type' => 'Segment', 'id' => 's', 'items' => '@{segmentOptions}' }
      )
      expect(warnings.join("\n")).to include('is a binding')
    end

    it 'obeys the shared rule, not the coercion that happens to empty it' do
      # Without this the predicate call above is indistinguishable from
      # absent: the extraction layer already returns `[]`, so removing the
      # rule would not change a single assertion. Here extraction hands
      # back a populated list while the raw value is still a binding — only
      # the shared rule can decide, and it says zero elements.
      conv = described_class.new(
        { 'class' => 'Segment', 'id' => 's', 'items' => '@{segmentOptions}' }, config
      )
      attrs = conv.attributes
      allow(attrs).to receive(:[]).and_wrap_original do |original, key|
        key == 'items' ? %w[a b] : original.call(key)
      end

      expect(conv.convert).not_to include('<button')
    end
  end

  describe 'the generated JSX parses' do
    # The arms above are the regression guard and always run. This is the
    # end-to-end claim, and it needs a JavaScript parser. rjui_tools has no
    # node_modules of its own, so point it at one:
    #
    #   JSONUI_BABEL_DIR=<a dir from which @babel/parser resolves> rspec …
    #
    # Without it the example is PENDING, not passing — a parse claim nobody
    # ran is not a green.
    def parser_path
      return @parser_path if defined?(@parser_path)

      require 'open3'
      dir = ENV['JSONUI_BABEL_DIR']
      dir = File.expand_path(dir) if dir && !dir.empty?
      out, _err, status = Open3.capture3(
        { 'NODE_PATH' => nil }.compact,
        'node', '-e',
        'try{console.log(require.resolve("@babel/parser"))}catch(e){process.exit(3)}',
        chdir: dir && File.directory?(dir) ? dir : Dir.pwd
      )
      @parser_path = status.success? ? out.strip : nil
    end

    def parses?(jsx)
      require 'open3'
      require 'tmpdir'
      Dir.mktmpdir do |dir|
        file = File.join(dir, 'Sample.jsx')
        File.write(file, "export default function Sample() {\n  return (\n<div>#{jsx}</div>\n  );\n}\n")
        script = File.join(dir, 'parse.js')
        File.write(script, <<~JS)
          const {parse} = require(#{parser_path.inspect});
          parse(require("fs").readFileSync(process.argv[2], "utf8"),
                {sourceType: "module", plugins: ["jsx", "typescript"]});
        JS
        Open3.capture3('node', script, file)[2].success?
      end
    end

    it 'parses with an object entry present, and the old output does not' do
      skip 'set JSONUI_BABEL_DIR to a directory where @babel/parser resolves' unless parser_path

      jsx, = emit([{ 'label' => 'opt_a', 'value' => 'a' }])
      expect(parses?(jsx)).to be(true), 'the generated JSX did not parse'

      # The control: the parser must reject what this used to emit, or the
      # green above says nothing about the parser.
      old = '<button key={0}>{"label"=>"opt_a", "value"=>"a"}</button>'
      expect(parses?(old)).to be(false), 'the parser accepted the pre-fix output — it is not discriminating'
    end
  end
end
