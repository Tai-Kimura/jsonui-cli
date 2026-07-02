# frozen_string_literal: true

# Container accessibility-identifier exposure (static SwiftUI codegen).
#
# Plain SwiftUI stacks are not accessibility elements: a bare
# .accessibilityIdentifier on a container never surfaces for the container
# itself and gets pushed down onto the nearest descendant element,
# clobbering that child's own identifier when the subtree holds a single
# element. Mirrors the SwiftJsonUI Dynamic-mode fix in
# DynamicModifierHelper.applyAccessibilityId:
#   - id-bearing containers become explicit accessibility containers
#     (.accessibilityElement(children: .contain)) so XCUITest can find them
#   - an invisible 0.5pt anchor overlay guarantees >= 2 accessibility
#     children so SwiftUI never merges nested single-child containers
#     (the merge drops the inner container's identifier)
#   - statically invisible components emit no identifier at all
#
# DEPTH BUDGET (device stack-overflow regression): the anchor overlay is a
# multi-layer modifier chain; emitted for EVERY id-bearing container it made
# one DEBUG body evaluation of a large screen exhaust the device main-thread
# stack (EXC_BAD_ACCESS code=2). The anchor is therefore emitted only where
# the merge hazard exists — containers that cannot be proven to keep >= 2
# accessibility children at runtime (accessibility_merge_hazard?). Containers
# with two or more guaranteed accessibility children get only the two flat
# modifiers (.contain + identifier).
require 'swiftui/converter_factory'
require 'swiftui/views/label_converter'
require 'swiftui/views/view_converter'

RSpec.describe 'container accessibilityIdentifier emission' do
  ANCHOR_OVERLAY = '.overlay(alignment: .topLeading) {'

  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  let(:factory) { SjuiTools::SwiftUI::ConverterFactory.new }

  def convert(component)
    factory.create_converter(component).convert
  end

  def two_labels
    [{ 'type' => 'Label', 'text' => 'One' },
     { 'type' => 'Label', 'text' => 'Two' }]
  end

  describe 'id-bearing containers' do
    %w[View SafeAreaView Scroll ScrollView Blur BlurView GradientView].each do |type|
      it "emits an explicit accessibility container for #{type}" do
        code = convert({ 'type' => type, 'id' => 'root',
                         'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

        expect(code).to include('.accessibilityElement(children: .contain)')
        expect(code).to include('.accessibilityIdentifier("root")')
        # container element must be established before the identifier
        expect(code.index('.accessibilityElement(children: .contain)'))
          .to be < code.index('.accessibilityIdentifier("root")')
      end

      it "emits the invisible anchor overlay for a single-child #{type} (merge hazard)" do
        code = convert({ 'type' => type, 'id' => 'root',
                         'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

        expect(code).to include(ANCHOR_OVERLAY)
        expect(code).to include('Color.clear')
        expect(code).to include('.frame(width: 0.5, height: 0.5)')
        expect(code).to include('.accessibilityElement(children: .ignore)')
      end

      it "emits NO anchor overlay for a multi-child #{type} (no merge hazard)" do
        code = convert({ 'type' => type, 'id' => 'root', 'child' => two_labels })

        expect(code).to include('.accessibilityElement(children: .contain)')
        expect(code).to include('.accessibilityIdentifier("root")')
        expect(code).not_to include(ANCHOR_OVERLAY)
      end
    end

    it 'keeps a nested single-child container id queryable (anchor on both levels)' do
      code = convert({
                       'type' => 'View', 'id' => 'root',
                       'child' => [
                         { 'type' => 'View', 'id' => 'inner',
                           'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] }
                       ]
                     })

      expect(code).to include('.accessibilityIdentifier("root")')
      expect(code).to include('.accessibilityIdentifier("inner")')
      expect(code.scan('.accessibilityElement(children: .contain)').length).to eq(2)
      # one anchor overlay per hazardous (single-child) container
      expect(code.scan(ANCHOR_OVERLAY).length).to eq(2)
    end

    it 'emits no accessibility modifiers for a container without id' do
      code = convert({ 'type' => 'View',
                       'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

      expect(code).not_to include('.accessibilityIdentifier(')
      expect(code).not_to include('.accessibilityElement(children: .contain)')
      expect(code).not_to include(ANCHOR_OVERLAY)
    end
  end

  describe 'merge-hazard detection (conservative static approximation)' do
    it 'anchors an empty container' do
      code = convert({ 'type' => 'View', 'id' => 'root', 'child' => [] })

      expect(code).to include(ANCHOR_OVERLAY)
      expect(code).to include('.accessibilityIdentifier("root")')
    end

    it 'anchors when a child may vanish at runtime (visibility binding)' do
      code = convert({ 'type' => 'View', 'id' => 'root',
                       'child' => [
                         { 'type' => 'Label', 'text' => 'One' },
                         { 'type' => 'Label', 'text' => 'Two',
                           'visibility' => '@{isShown}' }
                       ] })

      expect(code).to include(ANCHOR_OVERLAY)
    end

    it 'anchors when a child is statically invisible' do
      code = convert({ 'type' => 'View', 'id' => 'root',
                       'child' => [
                         { 'type' => 'Label', 'text' => 'One' },
                         { 'type' => 'Label', 'text' => 'Two',
                           'visibility' => 'invisible' }
                       ] })

      expect(code).to include(ANCHOR_OVERLAY)
    end

    it 'anchors when a child is an include (unknown subtree)' do
      # Unexpanded includes never reach the converters (process_includes runs
      # first), so probe the hazard predicate directly: an include child must
      # not count as a guaranteed accessibility element.
      converter = factory.create_converter(
        { 'type' => 'View', 'id' => 'root',
          'child' => [
            { 'type' => 'Label', 'text' => 'One' },
            { 'include' => 'some_partial' }
          ] }
      )

      expect(converter.send(:accessibility_merge_hazard?)).to be(true)
    end

    it 'anchors when a child is data-driven and may be empty (Collection)' do
      code = convert({ 'type' => 'View', 'id' => 'root',
                       'child' => [
                         { 'type' => 'Label', 'text' => 'One' },
                         { 'type' => 'Collection', 'id' => 'list',
                           'cellClasses' => [], 'items' => '@{items}' }
                       ] })

      expect(code.scan(ANCHOR_OVERLAY).length).to be >= 1
    end

    it 'counts a guaranteed element inside an id-less plain container' do
      code = convert({ 'type' => 'View', 'id' => 'root',
                       'child' => [
                         { 'type' => 'Label', 'text' => 'One' },
                         { 'type' => 'View',
                           'child' => [{ 'type' => 'Label', 'text' => 'Two' }] }
                       ] })

      expect(code).not_to include(ANCHOR_OVERLAY)
    end

    it 'sums promoted descendants of a single id-less wrapper (no anchor)' do
      code = convert({ 'type' => 'View', 'id' => 'root',
                       'child' => [
                         { 'type' => 'View', 'child' => two_labels }
                       ] })

      expect(code).not_to include(ANCHOR_OVERLAY)
    end

    it 'counts an id-bearing container child as an element itself' do
      code = convert({ 'type' => 'View', 'id' => 'root',
                       'child' => [
                         { 'type' => 'Label', 'text' => 'One' },
                         { 'type' => 'View', 'id' => 'section', 'child' => two_labels }
                       ] })

      # root has 2 guaranteed children (Label + explicit container) -> no
      # anchor; "section" itself has 2 Labels -> no anchor either
      expect(code).not_to include(ANCHOR_OVERLAY)
      expect(code.scan('.accessibilityElement(children: .contain)').length).to eq(2)
    end

    it 'does not count a decorative empty container child' do
      code = convert({ 'type' => 'View', 'id' => 'root',
                       'child' => [
                         { 'type' => 'Label', 'text' => 'One' },
                         { 'type' => 'View', 'height' => 1,
                           'background' => '#CCCCCC' } # divider: no a11y element
                       ] })

      expect(code).to include(ANCHOR_OVERLAY)
    end
  end

  describe 'depth budget regression (device stack overflow)' do
    # Regression for the on-device stack exhaustion: 44 anchor sites on one
    # screen pushed a single DEBUG body evaluation past the device main
    # thread stack. A representative many-container screen (all containers
    # with >= 2 guaranteed accessibility children, the dominant real-world
    # shape) must emit ZERO anchor overlays — the per-site cost is bounded to
    # the two flat accessibility modifiers.
    it 'emits no anchor overlay on a 44-container screen without merge hazards' do
      container_count = 44
      # depth-44 chain: every container holds 2 Labels + the next container
      component = { 'type' => 'View', 'id' => 'c44', 'child' => two_labels }
      (container_count - 1).downto(1) do |i|
        component = { 'type' => 'View', 'id' => "c#{i}",
                      'child' => two_labels + [component] }
      end

      code = convert(component)

      expect(code.scan('.accessibilityIdentifier(').length).to eq(container_count)
      expect(code.scan('.accessibilityElement(children: .contain)').length)
        .to eq(container_count)
      # THE regression assertion: anchor overlays are O(hazard sites), not
      # O(all containers). This fixture has no hazard sites.
      expect(code.scan(ANCHOR_OVERLAY).length).to eq(0)
    end

    it 'bounds anchor overlays to exactly the hazardous sites in a mixed screen' do
      hazard = { 'type' => 'View', 'id' => 'single',
                 'child' => [{ 'type' => 'Label', 'text' => 'Only' }] }
      safe = { 'type' => 'View', 'id' => 'multi', 'child' => two_labels }
      component = { 'type' => 'View', 'id' => 'root',
                    'child' => [hazard, safe, safe.merge('id' => 'multi2')] }

      code = convert(component)

      # root has 3 explicit-container children -> safe; only "single" anchors
      expect(code.scan(ANCHOR_OVERLAY).length).to eq(1)
      expect(code.scan('.accessibilityElement(children: .contain)').length).to eq(4)
    end
  end

  describe 'non-container components' do
    it 'keeps the bare identifier for Label (real accessibility element)' do
      code = convert({ 'type' => 'Label', 'id' => 'title', 'text' => 'Hi' })

      expect(code).to include('.accessibilityIdentifier("title")')
      expect(code).not_to include('.accessibilityElement(children: .contain)')
      expect(code).not_to include(ANCHOR_OVERLAY)
    end
  end

  describe 'statically invisible components' do
    # Explicit accessibility containers ignore an ancestor
    # .accessibilityHidden(true), so an invisible container must not create
    # one; the library VisibilityWrapper collapses + hides the subtree.
    it 'emits no identifier for an invisible container' do
      code = convert({ 'type' => 'View', 'id' => 'ghost', 'visibility' => 'invisible',
                       'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

      expect(code).not_to include('.accessibilityIdentifier(')
      expect(code).not_to include('.accessibilityElement(children: .contain)')
    end

    it 'emits no identifier for an invisible non-container' do
      code = convert({ 'type' => 'Label', 'id' => 'ghost', 'visibility' => 'invisible',
                       'text' => 'Hi' })

      expect(code).not_to include('.accessibilityIdentifier(')
    end

    it 'still emits the identifier when visibility is a binding' do
      code = convert({ 'type' => 'View', 'id' => 'root',
                       'visibility' => '@{rootVisibility}',
                       'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

      expect(code).to include('.accessibilityIdentifier("root")')
      expect(code).to include('.accessibilityElement(children: .contain)')
    end
  end
end
