# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require_relative '../spec_helper'
require 'react/converters/image_converter'
require 'react/converters/icon_label_converter'
require 'react/converters/network_image_converter'
require 'react/converters/text_field_converter'
require 'react/converters/text_view_converter'
require 'react/converters/view_converter'

# An attribute holding a binding is written as ONE JavaScript expression
# (BaseConverter#attribute_expression). Until 1.8.121 these sites took
# convert_binding's JSX-child form (`https://x/{data.id}.png`) and removed
# every brace to make an expression — text around a binding became code
# (`https://x/data.id.png`), a literal brace was lost, and IconLabel's icon,
# which was never converted, came out as `src={@img}`. Ticket
# codegen-string-literals-are-not-escaped-for-the-target-language,
# remaining 2.
#
# Each value below, through each site, is read back by node (esbuild's JSX
# transform) with data = { img: 'I', id: '7', w: 2 }; the value the element
# receives must be the text the author meant.
module BindingAttributeExpressionSpec
  C = RjuiTools::React::Converters
  CONFIG = { 'use_tailwind' => true, 'typescript' => true }.freeze
  ESBUILD = File.expand_path('../support/node_modules/esbuild', __dir__)

  VALUES = [
    ['a binding', '@{img}', 'I'],
    ['a binding with a default', "@{missing ?? 'D'}", 'D'],
    ['text around a binding', 'https://x/@{id}.png', 'https://x/7.png'],
    ['text around an unresolved binding', 'a/@{missing}/b', 'a//b'],
    ['special characters around a binding', "{q} `t` \\ @{id} ${n} it's", "{q} `t` \\ 7 ${n} it's"],
    ['braces and no binding', 'https://x/{id}.png', 'https://x/{id}.png'],
    ['a binding that is not an expression', '@{bad name}', '@{bad name}']
  ].freeze

  # [site, element tag, attribute a binding lands in, attribute a literal
  # lands in, emit]
  SITES = [
    ['Image src', '<img', 'src', 'src', ->(v) { C::ImageConverter.new({ 'type' => 'Image', 'src' => v }, CONFIG.dup).convert }],
    ['Image url', '<img', 'src', 'src', ->(v) { C::ImageConverter.new({ 'type' => 'Image', 'url' => v }, CONFIG.dup).convert }],
    ['IconLabel icon', '<img', 'src', 'src',
     ->(v) { C::IconLabelConverter.new({ 'type' => 'IconLabel', 'text' => 't', 'icon' => v }, CONFIG.dup).convert }],
    ['NetworkImage src', '<NetworkImage', 'src', 'src',
     ->(v) { C::NetworkImageConverter.new({ 'type' => 'NetworkImage', 'src' => v }, CONFIG.dup).convert }],
    ['NetworkImage placeholder', '<NetworkImage', 'placeholder', 'placeholder',
     lambda { |v|
       C::NetworkImageConverter.new({ 'type' => 'NetworkImage', 'src' => 'a.png', 'placeholder' => v }, CONFIG.dup).convert
     }],
    ['TextField text', '<input', 'value', 'defaultValue',
     ->(v) { C::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 'f', 'text' => v }, CONFIG.dup).convert }],
    ['TextField hint', '<input', 'placeholder', 'placeholder',
     ->(v) { C::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 'f', 'hint' => v }, CONFIG.dup).convert }],
    ['TextView text', '<textarea', 'value', 'defaultValue',
     ->(v) { C::TextViewConverter.new({ 'type' => 'TextView', 'id' => 'f', 'text' => v }, CONFIG.dup).convert }],
    ['TextView hint', '<textarea', 'placeholder', 'placeholder',
     ->(v) { C::TextViewConverter.new({ 'type' => 'TextView', 'id' => 'f', 'hint' => v }, CONFIG.dup).convert }]
  ].freeze

  NODE_PROGRAM = <<~JS
    const fs = require('fs');
    const esbuild = require(process.argv[2]);
    const jobs = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    const h = (type, props) => ({ props: props || {} });
    const data = { img: 'I', id: '7', w: 2 };
    const out = jobs.map((src) => {
      try {
        const code = esbuild.transformSync(`<x a=${src} />`, { loader: 'jsx', jsx: 'transform', jsxFactory: 'h' })
          .code.trim().replace(/;$/, '');
        return { value: new Function('h', 'data', `return (${code});`)(h, data).props.a };
      } catch (e) {
        return { error: String(e.message).split('\\n')[0] };
      }
    });
    process.stdout.write(JSON.stringify(out));
  JS

  module_function

  def unavailable_reason
    return 'node is not on PATH' unless system('which node > /dev/null 2>&1')
    return 'esbuild is not installed (npm ci --prefix rjui_tools/spec/support)' unless File.directory?(ESBUILD)

    nil
  end

  # The attribute's value as written on the element: `"…"` or a braced
  # expression, read to its closing brace (strings and template literals,
  # with their `${…}`, skipped).
  def attribute_source(emitted, tag, attr)
    start = emitted.index(tag) or return nil
    at = emitted.index(" #{attr}=", start) or return nil
    i = at + attr.length + 2
    return emitted[i..emitted.index('"', i + 1)] if emitted[i] == '"'
    return nil unless emitted[i] == '{'

    # Frames: [:code, brace depth], [:template], [:string, quote].
    stack = [[:code, 0]]
    j = i
    while j < emitted.length
      c = emitted[j]
      frame = stack.last
      case frame[0]
      when :code
        if c == '{'
          frame[1] += 1
        elsif c == '}'
          frame[1] -= 1
          if frame[1].zero?
            stack.pop
            return emitted[i..j] if stack.empty?
          end
        elsif c == '"' || c == "'"
          stack.push([:string, c])
        elsif c == '`'
          stack.push([:template])
        end
      when :template
        if c == '\\'
          j += 1
        elsif c == '`'
          stack.pop
        elsif c == '$' && emitted[j + 1] == '{'
          stack.push([:code, 1])
          j += 1
        end
      else
        if c == '\\'
          j += 1
        elsif c == frame[1]
          stack.pop
        end
      end
      j += 1
    end
    nil
  end
end

RSpec.describe 'an attribute holding a binding is one expression' do
  spec = BindingAttributeExpressionSpec

  before(:context) do
    @unavailable = spec.unavailable_reason
    @rows = spec::SITES.flat_map do |site, tag, bound_attr, literal_attr, emit|
      spec::VALUES.map do |name, value, text|
        emitted = emit.(value)
        attr = value.include?('@{') ? bound_attr : literal_attr
        { site: site, name: name, value: value, text: text, emitted: emitted,
          source: spec.attribute_source(emitted, tag, attr) }
      rescue StandardError => e
        { site: site, name: name, value: value, text: text, error: "#{e.class}: #{e.message}" }
      end
    end
    next if @unavailable

    jobs = @rows.each_index.select { |i| @rows[i][:source] }
    Dir.mktmpdir('rjui_binding_attribute') do |dir|
      File.write(File.join(dir, 'main.js'), spec::NODE_PROGRAM)
      File.write(File.join(dir, 'jobs.json'), JSON.generate(jobs.map { |i| @rows[i][:source] }))
      out, err, status = Open3.capture3('node', File.join(dir, 'main.js'), spec::ESBUILD, File.join(dir, 'jobs.json'))
      raise "node failed: #{err}" unless status.success?

      JSON.parse(out).each_with_index { |result, k| @rows[jobs[k]][:node] = result }
    end
  end

  spec::SITES.each do |site, *|
    it "#{site}: every value reads back as the text (node)" do
      if @unavailable
        raise @unavailable if ENV['CI']

        skip "#{@unavailable}: the round trip is UNMEASURED here"
      end
      aggregate_failures do
        @rows.select { |r| r[:site] == site }.each do |r|
          raise r[:error] if r[:error]

          result = r[:node] || { 'error' => "no attribute located in:\n#{r[:emitted]}" }
          expect(result['value']).to eq(r[:text]),
                                     "#{r[:name]}: #{r[:value]} was written #{r[:source]}, " \
                                     "node read #{result['error'] ? "an error: #{result['error']}" : result['value'].inspect}"
        end
      end
    end

    # A binding alone is written as it always was.
    it "#{site}: a binding alone comes out as it did" do
      row = @rows.find { |r| r[:site] == site && r[:value] == '@{img}' }
      expect(row[:source]).to eq('{data.img}')
    end
  end

  # borderWidth reads a number, so text around a binding means nothing
  # there; the binding alone is the case, and it comes out as it did.
  it 'writes a bound borderWidth as the binding in px' do
    emitted = spec::C::ViewConverter.new(
      { 'type' => 'View', 'borderWidth' => '@{w}', 'borderColor' => '#000000' }, spec::CONFIG.dup
    ).convert
    expect(emitted).to include('borderWidth: `${data.w}px`')
  end

  # The locator reads what it claims to: a template literal's `${…}` and a
  # brace inside a string do not end the expression.
  it 'locates a whole expression' do
    src = '<img src={`a${data.x ?? "}"}b`} alt="" />'
    expect(spec.attribute_source(src, '<img', 'src')).to eq('{`a${data.x ?? "}"}b`}')
    expect(spec.attribute_source('<img src="x{y}" />', '<img', 'src')).to eq('"x{y}"')
  end
end
