# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/react_generator'
require 'react/converters/select_box_converter'
require 'react/converters/text_field_converter'
require 'react/converters/text_view_converter'
require 'react/converters/segment_converter'

# A control the layout writes no cornerRadius on (the requester's ruling 2026-11-15, ticket
# jui-button-default-corner-radius-differs): a SelectBox is 8px (rounded-lg; it was rounded-md,
# 6px), as on iOS and Android; a TextField and a TextView are square. rjui.config's
# defaults.textField.cornerRadius / defaults.textView.cornerRadius are gone: written, they draw
# no corner.
RSpec.describe 'rjui: the corner a control draws with no cornerRadius' do
  let(:config) { { 'use_tailwind' => true } }
  let(:with_defaults) do
    config.merge('defaults' => { 'textField' => { 'cornerRadius' => 12 }, 'textView' => { 'cornerRadius' => 12 } })
  end

  # What a TextField / TextView with id "c" reaches outside itself: its ref and
  # the focus handler the ViewModel's data carries.
  def field_decl
    <<~TS
      declare const cRef: { current: HTMLInputElement | HTMLTextAreaElement | null };
      declare const data: { onCIsFocusedChange?: (focused: boolean) => void };
    TS
  end

  def corner_of(out)
    out.scan(/rounded[\w\-\[\]\.]*|borderRadius[^,}]*/).uniq
  end

  it 'emits TypeScript a compiler reads' do
    %w[SelectBox TextField TextView].each do |type|
      klass = RjuiTools::React::Converters.const_get("#{type}Converter")
      out = klass.new({ 'type' => type, 'id' => 'c', 'items' => %w[a b], 'hint' => 'x' }, with_defaults.dup).convert
      expect(TypeScriptCompiler.component(out)).to compile_as_typescript.with_ambient(field_decl)
    end
  end

  it 'draws a SelectBox at 8px' do
    out = RjuiTools::React::Converters::SelectBoxConverter.new({ 'type' => 'SelectBox', 'id' => 's', 'items' => %w[a b] }, config.dup).convert
    expect(out).to include('rounded-lg')
    expect(out).not_to include('rounded-md')
  end

  it 'draws a TextField square' do
    out = RjuiTools::React::Converters::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 't', 'hint' => 'x' }, config.dup).convert
    expect(corner_of(out)).to eq([])
  end

  it 'draws a TextView square' do
    out = RjuiTools::React::Converters::TextViewConverter.new({ 'type' => 'TextView', 'id' => 't', 'hint' => 'x' }, config.dup).convert
    expect(corner_of(out)).to eq([])
  end

  it 'draws no corner from defaults.textField.cornerRadius' do
    out = RjuiTools::React::Converters::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 't', 'hint' => 'x' }, with_defaults.dup).convert
    expect(corner_of(out)).to eq([])
  end

  # The other defaults still apply; any of them failed the build until 2.5.44.
  it "applies defaults.textField's and defaults.textView's fontColor, the layout's own winning" do
    cfg = config.merge('defaults' => { 'textField' => { 'fontColor' => '#123456' }, 'textView' => { 'fontColor' => '#123456' } })
    field = RjuiTools::React::Converters::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 't', 'hint' => 'x' }, cfg.dup).convert
    view = RjuiTools::React::Converters::TextViewConverter.new({ 'type' => 'TextView', 'id' => 't', 'hint' => 'x' }, cfg.dup).convert
    own = RjuiTools::React::Converters::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 't', 'hint' => 'x', 'fontColor' => '#654321' }, cfg.dup).convert
    expect(field).to include('123456')
    expect(view).to include('123456')
    expect(own).to include('654321')
    expect(own).not_to include('123456')
  end

  it 'draws no corner from defaults.textView.cornerRadius' do
    out = RjuiTools::React::Converters::TextViewConverter.new({ 'type' => 'TextView', 'id' => 't', 'hint' => 'x' }, with_defaults.dup).convert
    expect(corner_of(out)).to eq([])
  end

  # A declared cornerRadius is the only corner class (ticket
  # rjui-selectbox-default-corner-overrides-declared): Tailwind writes rounded-* in name order, so
  # a default beside it decided the corner by spelling — rounded-lg drew over rounded /
  # rounded-2xl / rounded-[Npx]. (A TextField or TextView writes the declared corner inline as well,
  # borderRadius, which no class beats: its borderStyle corner never won.)
  {
    'SelectBox' => { 'items' => %w[a b] }
  }.each do |label, extra|
    type = label.split.first
    { 4 => 'rounded', 0 => 'rounded-none', 16 => 'rounded-2xl', 10 => 'rounded-[10px]' }.each do |radius, cls|
      it "draws a #{label} with cornerRadius #{radius} at #{cls} alone" do
        klass = RjuiTools::React::Converters.const_get("#{type}Converter")
        out = klass.new({ 'type' => type, 'id' => 'c', 'cornerRadius' => radius }.merge(extra), config.dup).convert
        root = out[/className="[^"]*\b#{Regexp.escape(cls)}(?=[\s"])[^"]*"/]
        expect(root).not_to be_nil, out
        expect(root.scan(/(?<![\w:\[-])rounded(?:-[\w\[\]]+)?/)).to eq([cls])
      end
    end
  end

  # A Segment reads no cornerRadius (the requester's ruling 2026-11-16): its track and its
  # selected fill are capsules on every platform, as iOS draws them, whatever is declared.
  # Each label on one line, as iOS and Android draw a segment's (the requester's ruling 2026-11-15):
  # a 156-wide Segment wrapped a four-character Japanese label onto two lines.
  it "draws each Segment label on one line, cut with an ellipsis" do
    out = RjuiTools::React::Converters::SegmentConverter.new({ 'type' => 'Segment', 'id' => 'c', 'items' => %w[あいうえ かきく], 'width' => 156 }, config.dup).convert
    buttons = out.scan(/<button[^\n]*?className=\{`([^`]*)`\}[^\n]*?(<span[^\n]*?)<\/button>/)
    expect(buttons.size).to eq(2)
    buttons.each do |cls, label|
      expect(cls.split).to include('min-w-0')
      expect(cls.split.grep(/\Apx-/)).to eq(['px-1.5'])
      # The label's span truncates; the button cuts nothing (a short declared height kept its foot).
      expect(cls.split & %w[overflow-hidden truncate]).to eq([])
      expect(label).to match(/\A<span className="block min-w-0 truncate">.+<\/span>\z/)
    end
  end

  # A segment's label is 13 by default, as iOS and Android draw it (it was text-sm, 14, and a
  # 200-wide three-item Segment cut "Gamma"); a declared fontSize is used as written.
  it "draws a Segment's label at 13 unless fontSize is declared" do
    plain = RjuiTools::React::Converters::SegmentConverter.new({ 'type' => 'Segment', 'id' => 'c', 'items' => %w[A B] }, config.dup).convert
    sized = RjuiTools::React::Converters::SegmentConverter.new({ 'type' => 'Segment', 'id' => 'c', 'items' => %w[A B], 'fontSize' => 18 }, config.dup).convert
    plain.scan(/<button[^\n]*?className=\{`([^`]*)`\}/).flatten.each do |cls|
      expect(cls).not_to include('text-sm')
      expect(cls).to match(/13px|0\.8125rem/)
    end
    sized.scan(/<button[^\n]*?className=\{`([^`]*)`\}/).flatten.each { |cls| expect(cls).not_to match(/13px|0\.8125rem/) }
  end

  # Equal segments, each as wide as the widest label in a wrapContent Segment, as UISegmentedControl and
  # KotlinJsonUI divide it: a flex row of flex-1 min-w-0 buttons sized the Segment by its shortest label
  # and cut the others (2.5.45).
  it "lays a Segment's segments out as equal grid columns, the buttons not flex items" do
    out = RjuiTools::React::Converters::SegmentConverter.new({ 'type' => 'Segment', 'id' => 'c', 'width' => 'wrapContent', 'items' => %w[あ あいうえお] }, config.dup).convert
    track = out[/<div id="c" className="([^"]*)"/, 1]
    expect(track.split).to include('w-fit', 'grid', 'grid-flow-col', 'auto-cols-[minmax(0,1fr)]')
    expect(track.split).not_to include('flex')
    out.scan(/<button[^\n]*?className=\{`([^`]*)`\}/).flatten.each { |cls| expect(cls.split).not_to include('flex-1') }
  end

  # No width written is wrapContent on every face (2.5.47): the content's width, not the row's.
  it "draws a Segment with no width at its content's width" do
    out = RjuiTools::React::Converters::SegmentConverter.new({ 'type' => 'Segment', 'id' => 'c', 'items' => %w[あ あいうえお] }, config.dup).convert
    track = out[/<div id="c" className="([^"]*)"/, 1]
    expect(track.split).to include('w-fit')
    expect(track.split).not_to include('w-full')
  end

  # A declared height centres the label in the segment the track gives it: a quarter of the height
  # above and below was more than a 32-high Segment had, and cut the label's foot.
  it "centres a Segment's label in a declared height, and pads it with none" do
    fixed = RjuiTools::React::Converters::SegmentConverter.new({ 'type' => 'Segment', 'id' => 'c', 'items' => %w[A B], 'width' => 156, 'height' => 32 }, config.dup).convert
    free = RjuiTools::React::Converters::SegmentConverter.new({ 'type' => 'Segment', 'id' => 'c', 'items' => %w[A B] }, config.dup).convert
    fixed_buttons = fixed.scan(/<button[^\n]*?className=\{`([^`]*)`\}/).flatten
    expect(fixed_buttons.size).to eq(2)
    fixed_buttons.each do |cls|
      expect(cls.split).to include('flex', 'items-center', 'justify-center')
      expect(cls.split.grep(/\Apy-/)).to eq([])
    end
    free.scan(/<button[^\n]*?className=\{`([^`]*)`\}/).flatten.each { |cls| expect(cls.split).to include('py-2') }
  end

  it "draws a Segment's track as a capsule with a size class's cornerRadius" do
    node = { 'type' => 'Segment', 'id' => 'c', 'items' => %w[a b], 'responsive' => { 'regular' => { 'cornerRadius' => 4 } } }
    out = RjuiTools::React::Converters::SegmentConverter.new(node, config.dup).convert
    expect(out.scan(/(?<![\w\[-])rounded(?:-[\w\[\]]+)?/).uniq).to eq(['rounded-full']), out
  end

  [nil, 4, 0, 16, 10, '@{r}'].each do |radius|
    it "draws a Segment's track and fill as capsules with cornerRadius #{radius.inspect}" do
      node = { 'type' => 'Segment', 'id' => 'c', 'items' => %w[a b] }
      node['cornerRadius'] = radius unless radius.nil?
      out = RjuiTools::React::Converters::SegmentConverter.new(node, config.dup).convert
      corners = out.scan(/(?<![\w:\[-])rounded(?:-[\w\[\]]+)?/).uniq
      expect(corners).to eq(['rounded-full']), out
      expect(out).not_to include('borderRadius')
    end
  end
end
