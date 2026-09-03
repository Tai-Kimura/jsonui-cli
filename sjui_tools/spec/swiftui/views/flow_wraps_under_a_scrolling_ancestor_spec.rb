# frozen_string_literal: true

require 'json'
require 'swiftui/json_to_swiftui_converter'

# Ruling (2026-09-03): a flow Collection with `lazy` in effect scrolls inside
# its own bounds, and "its own bounds" is literal. This codegen wrapped the
# default-lazy flow in a ScrollView unconditionally, so a wrapContent flow
# under a scrolling ancestor became an inner ScrollView that grew to the
# outer viewport's height inside the outer one (the corpus's
# flowOverflow__wrap picture on iOS), while Android wraps and lets the parent
# scroll. The rule the two faces now share: a wrapping flow under a scrolling
# ancestor takes the non-lazy container and the ancestor scrolls; a flow
# with bounds of its own (a number, matchParent) or with no scrolling
# ancestor in the tree keeps its ScrollView.
#
# The ancestor is a fact about the TREE, which a converter built on a bare
# component cannot see, so these arms go through the tree converter — the
# entry that marks every node under a ScrollView before conversion.
RSpec.describe SjuiTools::SwiftUI::JsonToSwiftUIConverter do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  before { allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data } }

  let(:converter) { described_class.new }

  def flow(height: 'wrapContent', lazy: nil)
    node = { 'type' => 'Collection', 'id' => 'target', 'layout' => 'flow', 'width' => 150,
             'sections' => [{ 'cell' => 'probe_cell' }], 'items' => '@{items}' }
    node['height'] = height unless height.nil?
    node['lazy'] = lazy if lazy
    node
  end

  def emit(tree)
    converter.convert_component(tree, 0).to_s
  end

  def scroll_views(code)
    code.scan('ScrollView(').size
  end

  describe 'a wrapContent flow under a ScrollView' do
    it 'takes the non-lazy container: the outer ScrollView is the only one' do
      code = emit({ 'type' => 'ScrollView', 'id' => 'root', 'child' => [flow] })
      expect(scroll_views(code)).to eq(1)
      expect(code).to include('FlowLayout(')
      # the outer one is the root's, above the collection
      expect(code.index('ScrollView(')).to be < code.index('FlowLayout(')
    end

    it 'keeps its cells addressable: the container is made an element' do
      # No ScrollView means a non-element container; without the anchor and
      # `.contain` a bare identifier is pushed down and renames every cell.
      code = emit({ 'type' => 'ScrollView', 'id' => 'root', 'child' => [flow] })
      ignore = code.index('.accessibilityElement(children: .ignore)')
      contain = code.index('.accessibilityElement(children: .contain)')
      identifier = code.index('.accessibilityIdentifier("target")')
      expect([ignore, contain, identifier]).to all(be_truthy)
      expect(ignore).to be < contain
      expect(contain).to be < identifier
      expect(code).to include('.accessibilityIdentifier("target_item_')
    end

    it 'sees the ancestor through intermediate Views' do
      tree = { 'type' => 'ScrollView', 'id' => 'root',
               'child' => [{ 'type' => 'View', 'id' => 'section',
                             'child' => [{ 'type' => 'View', 'id' => 'inner', 'child' => [flow] }] }] }
      expect(scroll_views(emit(tree))).to eq(1)
    end

    it 'treats an undeclared height as wrapContent' do
      code = emit({ 'type' => 'ScrollView', 'id' => 'root', 'child' => [flow(height: nil)] })
      expect(scroll_views(code)).to eq(1)
    end

    it 'reads the `Scroll` spelling of the container too' do
      code = emit({ 'type' => 'Scroll', 'id' => 'root', 'child' => [flow] })
      expect(scroll_views(code)).to eq(1)
    end
  end

  describe 'what is unchanged' do
    it 'no scrolling ancestor: the flow keeps its own ScrollView' do
      # root without an id: an id-bearing View is itself made a container
      # and would contribute a `.contain` of its own to the count below
      code = emit({ 'type' => 'View', 'child' => [flow] })
      expect(scroll_views(code)).to eq(1)
      expect(code.index('ScrollView(')).to be < code.index('FlowLayout(')
      expect(code).not_to include('.accessibilityElement(children: .contain)')
    end

    it 'a numeric height under a ScrollView has bounds of its own: two ScrollViews' do
      code = emit({ 'type' => 'ScrollView', 'id' => 'root', 'child' => [flow(height: 100)] })
      expect(scroll_views(code)).to eq(2)
    end

    it 'matchParent under a ScrollView keeps its ScrollView' do
      code = emit({ 'type' => 'ScrollView', 'id' => 'root', 'child' => [flow(height: 'matchParent')] })
      expect(scroll_views(code)).to eq(2)
    end

    it 'lazy:"none" under a ScrollView was already the non-lazy container' do
      code = emit({ 'type' => 'ScrollView', 'id' => 'root', 'child' => [flow(lazy: 'none')] })
      expect(scroll_views(code)).to eq(1)
      expect(code).to include('FlowLayout(')
    end

    it 'a vertical Collection under a ScrollView is not touched' do
      node = flow.merge('layout' => 'vertical')
      code = emit({ 'type' => 'ScrollView', 'id' => 'root', 'child' => [node] })
      expect(code).not_to include('FlowLayout(')
      expect(scroll_views(code)).to be >= 1
    end

    it 'a converter built on the bare component sees no ancestor' do
      code = SjuiTools::SwiftUI::Views::CollectionConverter.new(flow).convert.to_s
      expect(scroll_views(code)).to eq(1)
    end
  end

  describe 'the mark itself' do
    it 'is set on every descendant of a ScrollView and nowhere else' do
      tree = { 'type' => 'View', 'child' => [
        { 'type' => 'Label', 'text' => 'a' },
        { 'type' => 'ScrollView', 'child' => [{ 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'b' }] }] }
      ] }
      converter.mark_scrolling_ancestors(tree)
      key = SjuiTools::SwiftUI::Views::BaseViewConverter::SCROLLING_ANCESTOR_KEY
      expect(tree).not_to have_key(key)
      expect(tree['child'][0]).not_to have_key(key)
      scroll = tree['child'][1]
      expect(scroll).not_to have_key(key)
      expect(scroll['child'][0][key]).to be(true)
      expect(scroll['child'][0]['child'][0][key]).to be(true)
    end
  end
end
