# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../spec_helper'
require 'core/string_literals'
require 'react/react_generator'
require 'react/converters/network_image_converter'
require 'react/converters/embed_converter'
require 'react/helpers/font_spec_helper'

# Every place rjui writes an author's text into generated TS/TSX goes through
# JsonUIShared::StringLiterals (lib/core/string_literals.rb). Each row below
# is one such path, reached with the smallest input, carrying SPECIMEN — a
# text with every character some literal form treats specially. A row pins
# the form the path emits, then node evaluates what was emitted (a JSX child
# or attribute through esbuild's JSX transform, a JS literal as is), in ONE
# process for the whole table: the value must be the text.
#
# Before 1.8.121 the paths escaped for themselves, and two gsub traps hid in
# them: `gsub('\\', '\\\\')` does not double a backslash, and in a
# replacement STRING "\\`" is the text before the match — LabelConverter
# turned It`s {one} C:\new into ItIts and a newline. Ticket
# codegen-string-literals-are-not-escaped-for-the-target-language.
#
# Each path also has a plain-text example: a text with nothing special comes
# out byte for byte as it always did, so regenerating a layout changes
# nothing.
module StringLiteralPathsSpec
  SPECIMEN = "It`s {one} C:\\new ${y} \"q\" <b> &amp; 'a'"
  PLAIN = 'Plain text'
  # Nothing JSX text would wrap, but a JSX attribute string cannot hold it.
  QUOTED = "say \"hi\" & C:\\new"
  L = JsonUIShared::StringLiterals
  C = RjuiTools::React::Converters
  CONFIG = { 'use_tailwind' => true, 'typescript' => true }.freeze

  module_function

  def convert(klass, node)
    klass.new(node, CONFIG.dup).convert
  end

  FORM_NAMES = { template_expr: '{`…`}', ts_expr: '{"…"}', single: "'…'", double: '"…"', template: '`…`' }.freeze

  # The emitted fragment each form stands for.
  def form_fragment(form, text)
    case form
    when :template_expr then "{`#{L.ts_template_body(text)}`}"
    when :ts_expr then "{#{L.ts(text)}}"
    when :single then L.ts_single(text)
    when :double then L.ts(text)
    else raise ArgumentError, form.to_s
    end
  end

  # at: [:child, open tag]           — the JSX child of the first such element
  #     [:attr, open tag, attribute] — that attribute's value on it
  #     [:js, text before it]        — the JS literal that follows
  PATHS = [
    { path: 'Label text', at: [:child, '<span'], form: :template_expr, plain: PLAIN,
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'text' => t) } },
    { path: "Label text with only { } ' (the {`…`} form it always had)", text: "It's {one}", at: [:child, '<span'], form: :template_expr,
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'text' => t) } },
    { path: 'Label text with < >', text: "a <b> \"q\" C:\\new $y", at: [:child, '<span'], form: :ts_expr,
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'text' => t) } },
    { path: 'Label text with a character reference', text: 'Tom &amp; Jerry', at: [:child, '<span'], form: :ts_expr,
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'text' => t) } },
    { path: 'Label hint', at: [:child, '<span'], form: :template_expr, plain: PLAIN,
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'text' => '', 'hint' => t, 'hintAttributes' => { 'fontColor' => '#FF0000' }) } },
    { path: 'Label hint font', at: [:js, 'fontFamily: '], form: :single, plain: "'#{PLAIN}'",
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'text' => '', 'hint' => 'h', 'hintAttributes' => { 'fontColor' => '#FF0000', 'font' => t }) } },
    { path: 'Label linkable text', at: [:attr, '<LinkifyText', 'text'], form: :template_expr, plain: "{`#{PLAIN}`}",
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'linkable' => true, 'text' => t) } },
    { path: 'Label partial range literal', at: [:js, 'range: '], form: :single, plain: "'#{PLAIN}'",
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'text' => 'body', 'partialAttributes' => [{ 'range' => t, 'fontColor' => '#FF0000' }]) } },
    { path: 'data-testid', at: [:attr, '<span', 'data-testid'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'text' => 'x', 'testId' => t) } },
    { path: 'data-tag', at: [:attr, '<span', 'data-tag'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::LabelConverter, 'type' => 'Label', 'text' => 'x', 'tag' => t) } },
    # A hint JSX text would wrap (braces, `'`, `<>`) keeps the expression
    # that wrapping gives it; any other text is the attribute's own.
    { path: 'TextField placeholder', at: [:attr, '<input', 'placeholder'], form: :template_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::TextFieldConverter, 'type' => 'TextField', 'hint' => t) } },
    { path: 'TextField placeholder with a quote', text: QUOTED, at: [:attr, '<input', 'placeholder'], form: :ts_expr,
      emit: ->(t) { convert(C::TextFieldConverter, 'type' => 'TextField', 'hint' => t) } },
    { path: 'TextField defaultValue', at: [:attr, '<input', 'defaultValue'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::TextFieldConverter, 'type' => 'TextField', 'text' => t) } },
    { path: 'TextField pattern', at: [:attr, '<input', 'pattern'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::TextFieldConverter, 'type' => 'TextField', 'pattern' => t) } },
    { path: 'TextView placeholder', at: [:attr, '<textarea', 'placeholder'], form: :template_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::TextViewConverter, 'type' => 'TextView', 'hint' => t) } },
    { path: 'TextView placeholder with a quote', text: QUOTED, at: [:attr, '<textarea', 'placeholder'], form: :ts_expr,
      emit: ->(t) { convert(C::TextViewConverter, 'type' => 'TextView', 'hint' => t) } },
    { path: 'TextView defaultValue', at: [:attr, '<textarea', 'defaultValue'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::TextViewConverter, 'type' => 'TextView', 'text' => t) } },
    { path: 'Button link href', at: [:attr, '<Link', 'href'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::ButtonConverter, 'type' => 'Button', 'text' => 'Go', 'href' => t) } },
    { path: 'Button image alt', at: [:attr, '<img', 'alt'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::ButtonConverter, 'type' => 'Button', 'image' => t) } },
    { path: 'Image alt', at: [:attr, '<img', 'alt'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::ImageConverter, 'type' => 'Image', 'src' => 'a.png', 'alt' => t) } },
    { path: 'NetworkImage src', at: [:attr, '<NetworkImage', 'src'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::NetworkImageConverter, 'type' => 'NetworkImage', 'url' => t) } },
    { path: 'NetworkImage placeholder', at: [:attr, '<NetworkImage', 'placeholder'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::NetworkImageConverter, 'type' => 'NetworkImage', 'url' => 'a.png', 'hint' => t) } },
    { path: 'Web src', at: [:attr, '<iframe', 'src'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::WebConverter, 'type' => 'Web', 'url' => t) } },
    { path: 'Web srcDoc', at: [:attr, '<iframe', 'srcDoc'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::WebConverter, 'type' => 'Web', 'html' => t) } },
    { path: 'Web title', at: [:attr, '<iframe', 'title'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::WebConverter, 'type' => 'Web', 'url' => 'https://example.com', 'title' => t) } },
    { path: 'SelectBox option value', at: [:attr, '<option', 'value'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::SelectBoxConverter, 'type' => 'SelectBox', 'items' => [t]) } },
    { path: 'SelectBox option label', at: [:child, '<option'], form: :ts_expr, plain: PLAIN,
      emit: ->(t) { convert(C::SelectBoxConverter, 'type' => 'SelectBox', 'items' => [t]) } },
    { path: 'SelectBox defaultValue', at: [:attr, '<select', 'defaultValue'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::SelectBoxConverter, 'type' => 'SelectBox', 'items' => ['a'], 'selectedValue' => t) } },
    { path: 'SelectBox dateStringFormat', at: [:js, 'toIsoDateValue(data.d, '], form: :single, plain: "'#{PLAIN}'",
      emit: ->(t) { convert(C::SelectBoxConverter, 'type' => 'SelectBox', 'selectItemType' => 'Date', 'selectedDate' => '@{d}', 'dateStringFormat' => t) } },
    { path: 'Radio item value', at: [:attr, '<input', 'value'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::RadioConverter, 'type' => 'Radio', 'id' => 'r', 'items' => [t, 'other'], 'onValueChange' => '@{pick}') } },
    { path: 'Radio item label', at: [:child, '<span'], form: :ts_expr, plain: PLAIN,
      emit: ->(t) { convert(C::RadioConverter, 'type' => 'Radio', 'id' => 'r', 'items' => [t, 'other'], 'onValueChange' => '@{pick}') } },
    { path: 'Radio onValueChange argument', at: [:js, 'data.pick?.('], form: :double, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::RadioConverter, 'type' => 'Radio', 'id' => 'r', 'items' => [t, 'other'], 'onValueChange' => '@{pick}') } },
    { path: 'CheckBox value', at: [:attr, '<input', 'value'], form: :ts_expr, plain: "\"#{PLAIN}\"",
      emit: ->(t) { convert(C::ToggleConverter, 'type' => 'Check', 'value' => t) } },
    { path: 'TabView tab title', at: [:child, '<span className="text-xs mt-1"'], form: :template_expr, plain: PLAIN,
      emit: ->(t) { convert(C::TabViewConverter, 'type' => 'TabView', 'id' => 'tabs', 'tabs' => [{ 'title' => t }]) } },
    { path: 'TabView tab badge', at: [:child, '<span className="absolute'], form: :ts_expr, plain: PLAIN,
      emit: ->(t) { convert(C::TabViewConverter, 'type' => 'TabView', 'id' => 'tabs', 'tabs' => [{ 'title' => 'A', 'badge' => t }]) } },
    { path: 'TabView panel text', at: [:child, '<div className="p-4"'], form: :ts_expr, suffix: ' content', plain: "#{PLAIN} content",
      fragment: ->(t) { "{#{L.ts("#{t} content")}}" },
      emit: ->(t) { convert(C::TabViewConverter, 'type' => 'TabView', 'id' => 'tabs', 'tabs' => [{ 'title' => t }]) } },
    { path: 'Include data param', at: [:js, 'p: '], form: :double, plain: "\"#{PLAIN}\"",
      emit: ->(t) { C::IncludeConverter.new({ 'include' => 'part', 'data' => { 'p' => t } }, CONFIG.dup).convert_node(2) } },
    # The text around a binding; node evaluates it with data.x = 'X'.
    { path: 'Include interpolated data param', at: [:js, 'q: '], form: :template, suffix: ' X', plain: "`#{PLAIN} ${data.x}`",
      fragment: ->(t) { "`#{L.ts_template_body("#{t} ")}${data.x}`" },
      emit: ->(t) { C::IncludeConverter.new({ 'include' => 'part', 'data' => { 'q' => "#{t} @{x}" } }, CONFIG.dup).convert_node(2) } },
    { path: 'Font spec family (js_string)', at: [:js, 'family: '], form: :single, plain: "'#{PLAIN}'",
      emit: ->(t) { RjuiTools::React::Helpers::FontSpecHelper.build_resolve_spread(family: t) } },
    { path: 'Embed param', at: [:js, 'p: '], form: :single, plain: "'#{PLAIN}'",
      emit: ->(t) { convert(C::EmbedConverter, 'type' => 'Embed', 'screen' => 'other', 'params' => { 'p' => t }) } },
    { path: 'onClick link url', at: [:js, 'window.open('], form: :single, plain: "'#{PLAIN}'",
      emit: ->(t) { convert(C::ViewConverter, 'type' => 'View', 'onClick' => { 'action' => 'link', 'url' => t }) } }
  ].freeze

  # --- locating the fragment in the emitted source -------------------------

  # Just past the JS string / template literal that opens at i.
  def literal_end(src, i)
    quote = src[i]
    j = i + 1
    while j < src.length
      return j + 1 if src[j] == quote

      j += src[j] == '\\' ? 2 : 1
    end
    src.length
  end

  # Just past the balanced {…} that opens at i, stepping over literals.
  def braces_end(src, i)
    depth = 0
    j = i
    while j < src.length
      if ['"', "'", '`'].include?(src[j])
        j = literal_end(src, j)
        next
      end
      depth += 1 if src[j] == '{'
      depth -= 1 if src[j] == '}'
      j += 1
      return j if depth.zero?
    end
    src.length
  end

  # Just past the `>` that closes the open tag starting at i.
  def open_tag_end(src, i)
    j = i
    while j < src.length
      case src[j]
      when '"' then j = (src.index('"', j + 1) || src.length) + 1
      when '{' then j = braces_end(src, j)
      when '>' then return j + 1
      else j += 1
      end
    end
    src.length
  end

  def locate(src, at)
    kind, anchor, name = at
    start = src.index(anchor) or return nil
    case kind
    when :child
      tag = anchor[/\A<([\w.]+)/, 1]
      from = open_tag_end(src, start)
      to = src.index("</#{tag}>", from) or return nil
      src[from...to]
    when :attr
      eq = src.index(" #{name}=", start) or return nil
      i = eq + name.length + 2
      stop = src[i] == '{' ? braces_end(src, i) : (src.index('"', i + 1) || src.length) + 1
      src[i...stop]
    when :js
      i = start + anchor.length
      ['"', "'", '`'].include?(src[i]) ? src[i...literal_end(src, i)] : nil
    end
  end

  # --- node --------------------------------------------------------------

  ESBUILD = File.expand_path('../support/node_modules/esbuild', __dir__)

  NODE_PROGRAM = <<~JS
    const fs = require('fs');
    const esbuild = require(process.argv[2]);
    const jobs = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    const h = (type, props, ...children) => ({ props: props || {}, children });
    const run = (js) => new Function('h', 'data', `return (${js});`)(h, { x: 'X' });
    const jsx = (src) =>
      run(esbuild.transformSync(src, { loader: 'jsx', jsx: 'transform', jsxFactory: 'h' }).code.trim().replace(/;$/, ''));
    const out = jobs.map(({ kind, src }) => {
      try {
        if (kind === 'js') return { value: run(src) };
        if (kind === 'attr') return { value: jsx(`<x a=${src} />`).props.a };
        const kids = jsx(`<x>${src}</x>`).children;
        if (kids.every((k) => typeof k === 'string')) return { value: kids.join('') };
        return { error: `not text: ${JSON.stringify(kids)}` };
      } catch (e) {
        return { error: String(e.message).split('\\n')[0] };
      }
    });
    process.stdout.write(JSON.stringify(out));
  JS

  def unavailable_reason
    return 'node is not on PATH' unless system('which node > /dev/null 2>&1')
    return 'esbuild is not installed (npm ci --prefix rjui_tools/spec/support)' unless File.directory?(ESBUILD)

    nil
  end

  # Every row's emitted source, fragment, and — in one node process — the
  # value node reads out of the fragment.
  def measure
    rows = PATHS.map do |row|
      text = row[:text] || SPECIMEN
      emitted = row[:emit].call(text)
      { emitted: emitted, fragment: locate(emitted, row[:at]) }
    rescue StandardError => e
      { error: "#{e.class}: #{e.message}" }
    end
    return [rows, unavailable_reason] if unavailable_reason

    jobs = PATHS.each_index.select { |i| rows[i][:fragment] }
    Dir.mktmpdir('rjui_string_literal_paths') do |dir|
      File.write(File.join(dir, 'main.js'), NODE_PROGRAM)
      File.write(File.join(dir, 'jobs.json'),
                 JSON.generate(jobs.map { |i| { kind: PATHS[i][:at][0].to_s, src: rows[i][:fragment] } }))
      out, err, status = Open3.capture3('node', File.join(dir, 'main.js'), ESBUILD, File.join(dir, 'jobs.json'))
      raise "node failed: #{err}" unless status.success?

      JSON.parse(out).each_with_index { |result, k| rows[jobs[k]][:node] = result }
    end
    [rows, nil]
  end
end

RSpec.describe 'Author text in generated TS/TSX, path by path' do
  table = StringLiteralPathsSpec

  before(:context) do
    @rows, @unavailable = table.measure
  end

  table::PATHS.each_with_index do |row, i|
    text = row[:text] || table::SPECIMEN
    expected_fragment = row[:fragment] ? row[:fragment].call(text) : table.form_fragment(row[:form], text)

    it "#{row[:path]}: emits #{table::FORM_NAMES.fetch(row[:form])}, which node reads back as the text" do
      measured = @rows[i]
      raise measured[:error] if measured[:error]

      if @unavailable
        raise @unavailable if ENV['CI']

        expect(measured[:fragment]).to eq(expected_fragment)
        skip "#{@unavailable}: the round trip is UNMEASURED here"
      end
      result = measured[:node] || { 'error' => 'no fragment located' }
      aggregate_failures do
        expect(measured[:fragment]).to eq(expected_fragment),
                                       "expected #{expected_fragment}\n     got #{measured[:fragment].inspect}\nin:\n#{measured[:emitted]}"
        expect(result['error']).to be_nil, "node could not read #{measured[:fragment].inspect}: #{result['error']}"
        expect(result['value']).to eq("#{text}#{row[:suffix]}")
      end
    end

    next unless row[:plain]

    it "#{row[:path]}: a plain text comes out as it always did" do
      emitted = row[:emit].call(table::PLAIN)
      expect(table.locate(emitted, row[:at])).to eq(row[:plain])
    end
  end
end
