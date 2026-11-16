# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/react_generator'
require 'react/converters/network_image_converter'
require 'react/converters/label_converter'
require 'json'

# A tap inside another tap is the inner one's alone, as on iOS and Android,
# where the innermost tap target takes the touch (jsonui-cli 1.9.1). On the
# web a click bubbles: a card that opens on tap, holding a delete Button,
# opened itself when the Button was pressed. Through v1.8.120 the element
# handed its handler the click (`onClick={data.onDeleteTap}`) and a view
# model could stop it; 1.9.0 calls a handler as its data declares it, so an
# undeclared one got nothing and nothing stopped the click (measured on a
# consumer's E2E: the delete dialog was detached by the card's navigation).
#
# The rule (RjuiTools::React::NestedTaps, BaseConverter#can_tap_gated_click):
# the inner tap stops the click, inside canTap's gate; a tap whose handler is
# handed the event (declared `(Event)`, or the `name:` selector) leaves it to
# the handler; a tap with no tap around it is written as before.
RSpec.describe 'rjui: a tap inside another tap stops the click there' do
  let(:config) { { 'use_tailwind' => true, 'typescript' => true } }

  # Through the build entry, as `rjui build` converts a layout: it annotates
  # and stamps its copy of the tree, then converts it.
  def build(layout)
    RjuiTools::React::ReactGenerator.new(config).generate('Card', JSON.parse(JSON.generate(layout)))
  end

  # The line that opens the element with this id (the root's is
  # `id={id ?? "card"}`).
  def tag_of(out, id)
    out.lines.find { |l| l.match?(/<[A-Za-z][\w.]*\b[^\n]*\bid=(?:"#{id}"|\{id \?\? "#{id}"\})/) } or
      raise "no element #{id} in\n#{out}"
  end

  # The element's onClick attribute, braces balanced (its value holds `{ }`).
  def onclick_of(out, id)
    tag = tag_of(out, id)
    start = tag.index(' onClick={') or raise "no onClick on #{id}: #{tag}"
    depth = 0
    (start + ' onClick='.length...tag.length).each do |i|
      depth += 1 if tag[i] == '{'
      depth -= 1 if tag[i] == '}'
      return tag[start..i] if depth.zero?
    end
    raise "unbalanced onClick on #{id}: #{tag}"
  end

  STOP = 'e.stopPropagation();'

  let(:card) do
    {
      'type' => 'View', 'id' => 'card', 'onClick' => '@{onCardTap}', 'child' => [
        { 'type' => 'Label', 'id' => 'title', 'text' => 'Lot A' },
        { 'type' => 'View', 'id' => 'actions', 'child' => [
          { 'type' => 'Button', 'id' => 'deleteButton', 'text' => 'Delete', 'onClick' => '@{onDeleteTap}' },
          { 'type' => 'Label', 'id' => 'moreLabel', 'text' => 'More', 'onClick' => '@{onMoreTap}' },
          { 'type' => 'Image', 'id' => 'icon', 'srcName' => 'x', 'onclick' => 'onIconTap' },
          { 'type' => 'View', 'id' => 'help', 'onClick' => { 'action' => 'link', 'url' => 'https://example.invalid/help' } }
        ] }
      ]
    }
  end

  it 'the inner taps stop the click before they call; the card around them does not' do
    out = build(card)
    expect(onclick_of(out, 'deleteButton')).to eq(" onClick={(e) => { #{STOP} data.onDeleteTap?.(); }}")
    expect(onclick_of(out, 'moreLabel')).to eq(" onClick={(e) => { #{STOP} data.onMoreTap?.(); }}")
    expect(onclick_of(out, 'icon')).to eq(" onClick={(e) => { #{STOP} data.onIconTap?.(); }}")
    expect(onclick_of(out, 'help')).to eq(" onClick={(e) => { #{STOP} window.open('https://example.invalid/help', '_blank'); }}")
    expect(onclick_of(out, 'card')).to eq(' onClick={() => data.onCardTap?.()}')
  end

  # Control: a tap with no tap around it is written as in 1.9.0, byte for
  # byte — the same layout without the card's own tap.
  it 'without the tap around them, the same taps are written as before' do
    layout = JSON.parse(JSON.generate(card)).tap { |c| c.delete('onClick') }
    out = build(layout)
    expect(out).not_to include('stopPropagation')
    expect(onclick_of(out, 'deleteButton')).to eq(' onClick={() => data.onDeleteTap?.()}')
    expect(onclick_of(out, 'help')).to eq(" onClick={() => window.open('https://example.invalid/help', '_blank')}")
  end

  it 'a bound canTap gates the stop too: a closed gate is no tap, and the click goes on' do
    card['child'][1]['child'][0]['canTap'] = '@{canDelete}'
    expect(onclick_of(build(card), 'deleteButton'))
      .to eq(" onClick={(e) => { if (data.canDelete) { #{STOP} data.onDeleteTap?.(); } }}")
  end

  # The handler that is handed the event decides whether it goes on — the
  # way to let a click through on the web (ruled 2026-09-28).
  it 'a handler the data declares `(Event)` is handed the click and is not stopped' do
    card['data'] = [{ 'name' => 'onDeleteTap', 'class' => '((Event) -> Void)?' }]
    out = build(card)
    expect(onclick_of(out, 'deleteButton')).to eq(' onClick={(e) => data.onDeleteTap?.(e)}')
    expect(onclick_of(out, 'moreLabel')).to include(STOP)
  end

  it "the `name:` selector's sender is the event: not stopped" do
    card['child'][1]['child'][2]['onclick'] = 'onIconTap:'
    expect(onclick_of(build(card), 'icon')).to eq(' onClick={(e) => data.onIconTap?.(e)}')
  end

  # What is around the inner tap and is no tap does not count.
  it 'a card whose tap is shut (canTap false, enabled false) holds no tap: nothing is stopped' do
    [{ 'canTap' => false }, { 'enabled' => false }].each do |shut|
      out = build(card.merge(shut))
      expect(out).not_to include('stopPropagation'), shut.inspect
    end
  end

  # A stop between the card and the taps: nothing under it has a click to
  # stop (the stop is placed between two taps — on the card itself, the card
  # is no tap and nothing would be stamped whether or not the stop is read).
  it 'under userInteractionEnabled: false nothing has a click, so nothing is stamped' do
    card['child'][1]['userInteractionEnabled'] = false
    root = RjuiTools::React::NestedTaps.stamp!(JSON.parse(JSON.generate(card)))
    stamped = []
    walk = lambda do |n|
      stamped << n['id'] if n[RjuiTools::React::NestedTaps::KEY]
      JsonUIShared::TapAccessibility.children(n).each { |c| walk.call(c) }
    end
    walk.call(root)
    expect(stamped).to eq([])
  end

  it 'a tap inside a tap inside a tap: both inner ones stop' do
    card['child'][1]['onClick'] = '@{onActionsTap}'
    out = build(card)
    expect(onclick_of(out, 'actions')).to eq(" onClick={(e) => { #{STOP} data.onActionsTap?.(); }}")
    expect(onclick_of(out, 'deleteButton')).to include(STOP)
  end

  # The two built-ins whose onClick is a prop, not a DOM element's: they are
  # handed the click now, so the stop type-checks against the props they
  # declare. With the 1.9.0 `onClick?: () => void` it does not (TS2322).
  describe 'on a built-in component' do
    mouse_event = <<~TS
      declare namespace React {
        type CSSProperties = { [property: string]: string | number | undefined }
        interface MouseEvent<T = Element> { stopPropagation(): void; currentTarget: T }
        interface KeyboardEvent<T = Element> { key: string; currentTarget: T }
      }
      declare const data: { imageUrl?: string; onImageTapped?: () => void; notesText?: string; onNotesTapped?: () => void };
    TS

    it 'NetworkImage (whose own click hands nothing) stops, and compiles against NetworkImageProps', :typescript_compile do
      node = { 'type' => 'NetworkImage', 'id' => 'hero', 'src' => '@{imageUrl}', 'onClick' => '@{onImageTapped}',
               RjuiTools::React::NestedTaps::KEY => true }
      jsx = RjuiTools::React::Converters::NetworkImageConverter.new(node, { 'use_tailwind' => true }).convert
      expect(jsx).to include(" onClick={(e) => { #{STOP} data.onImageTapped?.(); }}")
      expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(<<~TS)
        #{mouse_event}
        #{TypeScriptCompiler.template_declarations('network_image.tsx', 'NetworkImageProps')}
        declare const NetworkImage: (props: NetworkImageProps) => JSX.Element;
      TS
    end

    it 'a linkable Label (LinkifyText) stops, and compiles against LinkifyTextProps', :typescript_compile do
      node = { 'type' => 'Label', 'id' => 'notes', 'linkable' => true, 'text' => '@{notesText}',
               'onClick' => '@{onNotesTapped}', RjuiTools::React::NestedTaps::KEY => true }
      jsx = RjuiTools::React::Converters::LabelConverter.new(node, { 'use_tailwind' => true }).convert
      expect(jsx).to include(" onClick={(e) => { #{STOP} data.onNotesTapped?.(); }}")
      expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(<<~TS)
        #{mouse_event}
        #{TypeScriptCompiler.template_declarations('linkify_text.tsx', 'LinkifyTextProps')}
        declare const LinkifyText: (props: LinkifyTextProps & { ref?: { current: HTMLSpanElement | null } }) => JSX.Element;
      TS
    end
  end
end
