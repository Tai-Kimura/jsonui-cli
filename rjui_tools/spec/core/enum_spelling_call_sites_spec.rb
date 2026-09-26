# frozen_string_literal: true

require_relative '../../lib/core/enum_spelling'

# Every EnumSpelling call in this tool's lib names an attribute that is an
# enum where it asks: a literal section declares it (its own declaration or
# common's — the validator's lookup, not EnumSpelling's every-section
# fallback), and a section read off the node (`@component['type']`) names an
# attribute some section declares. A call that names a section or an
# attribute nothing declares answers nil for every value, so every value
# would draw the default — silently, since the validator judges the node,
# not the call.
#
# The same file in sjui_tools, kjui_tools and rjui_tools spec/core.
RSpec.describe 'EnumSpelling call sites' do
  lib = File.expand_path('../../lib', __dir__)
  spelling = JsonUIShared::EnumSpelling

  # Calls whose attribute is not a literal, each with why.
  computed_attribute = {
    'swiftui/scrolling_cell_index.rb' => "`key` is 'layout' or 'orientation', both Collection's",
    'swiftui/views/text_style_helper.rb' => '`attribute` is what its callers name (declared_vocabulary)',
    'compose/helpers/bound_value.rb' => 'declared_mapping: its callers name the pair (declared:)',
    'compose/components/textview_component.rb' => "keyboardType or input, both TextView's",
    'react/converters/base_converter.rb' => 'declared_table: its callers name the attribute',
    'compose/components/text_component.rb' => 'compose_text_align: textAlign, or %w[highlightAttributes textAlign]',
    'react/converters/label_converter.rb' => 'align_classes: textAlign, or %w[highlightAttributes textAlign]',
    'react/tailwind_mapper.rb' => 'map_text_align: textAlign, or its callers\' path'
  }

  # The top-level arguments of the call whose `(` or `[` ends at *start*.
  def self.arguments(line, start)
    depth = 1
    args = ['']
    line[start..].each_char do |char|
      depth += 1 if '([{'.include?(char)
      depth -= 1 if ')]}'.include?(char)
      break if depth.zero?

      if char == ',' && depth == 1
        args << ''
      else
        args[-1] += char
      end
    end
    args.map(&:strip)
  end

  # [relative path, line, section source, attribute source] for each call —
  # EnumSpelling's own, and the helpers that hand it a pair: a `declared:`
  # argument ([section, attribute]), declared_table(map, attribute) and
  # declared_vocabulary(attribute, map), which judge on the node's type.
  def self.calls_in(source, path = '(snippet)')
    found = []
    source.each_line.with_index(1) do |line, number|
      line.scan(/EnumSpelling\.(?:lowered|declared)\(/) do
        found << [path, number, *arguments(line, Regexp.last_match.end(0)).last(2)]
      end
      line.scan(/declared: %w\[(\w+) (\w+)\]/) { |section, attribute| found << [path, number, "'#{section}'", "'#{attribute}'"] }
      line.scan(/declared: \[/) do
        args = arguments(line, Regexp.last_match.end(0))
        found << [path, number, args[0].sub(/ \|\| '\w+'\z/, ''), args[1]]
      end
      next if line =~ /^\s*def /

      line.scan(/declared_table\(/) { found << [path, number, 'node', arguments(line, Regexp.last_match.end(0))[1]] }
      line.scan(/declared_vocabulary\(/) { found << [path, number, 'node', arguments(line, Regexp.last_match.end(0))[0]] }
    end
    found.reject { |_, _, _, attribute| attribute.nil? }
  end

  def self.literal(source)
    source[/\A'([^']*)'\z/, 1] || source[/\A"([^"]*)"\z/, 1]
  end

  # A path to an enum declared inside an object: %w[underline lineStyle].
  def self.path_literal(source)
    words = source[/\A%w\[([\w ]+)\]\z/, 1]
    words && words.split
  end

  # The offence a call makes, or nil.
  def self.offence(spelling, section, attribute)
    name = literal(attribute) || path_literal(attribute)
    return nil if name.nil?

    path = Array(name)
    owner = literal(section)
    if owner
      declared = [owner, 'common'].any? { |s| spelling.spellings_of(spelling.entry_at(spelling.definitions[s], path)) }
      declared ? nil : "#{owner}.#{path.join('.')} is not an enum on #{owner} or common"
    else
      spelling.declared(nil, path).empty? ? "no section declares #{path.join('.')} as an enum" : nil
    end
  end

  calls = Dir[File.join(lib, '**', '*.rb')].sort.reject { |f| File.basename(f) == 'enum_spelling.rb' }.flat_map do |file|
    calls_in(File.read(file, encoding: 'UTF-8'), file.delete_prefix("#{lib}/"))
  end

  it 'reads the definitions and finds the calls' do
    expect(spelling.definitions).not_to be_empty
    expect(calls).not_to be_empty
  end

  it 'names, for each call, a section and an attribute declared as an enum there' do
    offences = calls.map do |path, line, section, attribute|
      problem = self.class.offence(spelling, section, attribute)
      "#{path}:#{line} #{problem}" if problem
    end.compact
    expect(offences).to be_empty, offences.join("\n")
  end

  it 'names a literal attribute, except where the file says why not' do
    computed = calls.reject { |_, _, _, attribute| self.class.literal(attribute) || self.class.path_literal(attribute) }.map(&:first).uniq
    expect(computed - computed_attribute.keys).to be_empty, "a computed attribute with no reason: #{computed - computed_attribute.keys}"
  end

  # The instrument, against what it must tell apart: an argument holding
  # its own parentheses, a section that declares the attribute only through
  # common, one that does not declare it at all, and a node's type.
  describe 'the checker itself' do
    def offence_of(snippet)
      section, attribute = self.class.calls_in(snippet).first.last(2)
      self.class.offence(JsonUIShared::EnumSpelling, section, attribute)
    end

    it 'splits the arguments at the top level' do
      expect(self.class.calls_in("x = EnumSpelling.lowered(g.to_s.strip, 'common', 'gravity') }").first.last(2))
        .to eq(["'common'", "'gravity'"])
    end

    it 'passes a declaration of the section or common, and a node-typed section' do
      expect(offence_of("EnumSpelling.lowered(v, 'View', 'orientation')")).to be_nil
      expect(offence_of("EnumSpelling.lowered(v, 'Collection', 'gravity')")).to be_nil
      expect(offence_of("EnumSpelling.lowered(v, @component['type'], 'textAlign')")).to be_nil
    end

    it 'names a section that declares no such enum, and an attribute no section does' do
      expect(offence_of("EnumSpelling.lowered(v, 'Label', 'orientation')")).to include('Label.orientation')
      expect(offence_of("EnumSpelling.lowered(v, @component['type'], 'fontSize')")).to include('fontSize')
    end

    it 'reads the pair a helper is handed, and judges it the same way' do
      expect(offence_of("enum(v, M, declared: %w[TextField contentType])")).to be_nil
      expect(offence_of("enum(v, M, declared: %w[TextField contentTyp])")).to include('TextField.contentTyp')
      expect(offence_of("enum(v, M, declared: [json_data['type'] || 'Label', 'textAlign'])")).to be_nil
      expect(offence_of("js(declared_table(CONTENT_MODE_OBJECT_FIT, 'contentModes'))")).to include('contentModes')
      expect(offence_of("bound_enum(v, declared_vocabulary('input', KEYBOARD_TYPES), exact: true,")).to be_nil
    end

    it 'reads a path to an enum declared inside an object' do
      expect(offence_of("EnumSpelling.lowered(v, 'Label', %w[underline lineStyle])")).to be_nil
      expect(offence_of("EnumSpelling.lowered(v, 'Label', %w[highlightAttributes textAlign])")).to be_nil
      expect(offence_of("EnumSpelling.lowered(v, 'Label', %w[underline lineStyles])")).to include('Label.underline.lineStyles')
    end
  end
end
