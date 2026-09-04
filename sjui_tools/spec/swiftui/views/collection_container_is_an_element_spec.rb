# frozen_string_literal: true

require 'json'
require 'swiftui/views/collection_converter'

# A bare `.accessibilityIdentifier` on a view that is not itself an
# accessibility element is pushed DOWN onto its child elements. For a
# Collection whose emitted container is a plain VStack/HStack, that renames
# every cell to the collection's own id: `tapItem` can then address no index
# at all, and `assert visible <collection>` passes against a renamed cell, so
# the suite stays green while the address is gone. Measured on a consumer
# face; the same mechanism put `embed` in ACCESSIBILITY_CONTAINER_TYPES in
# 10.4.2.
#
# A Collection is not a container by TYPE — that is why it is not in that
# list and must not be added to it. Every lazy shape emits a ScrollView (or
# List / TabView / CollectionStackView), which IS an element and takes the
# identifier itself. `lazy: "none"` emits a bare stack, which is not.
#
# So the property below is a complete case analysis rather than a list of
# known-bad combinations: for EVERY declared (layout, lazy), the emitted
# collection either opens with a container that is an accessibility element,
# or its identifier is preceded by the anchor + `.contain` pair. A future arm
# that emits some new non-element container fails this without anyone
# remembering to extend the file.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  DEFS = JSON.parse(
    File.read(File.expand_path('../../../lib/core/attribute_definitions.json', __dir__))
  ).freeze

  def self.declared(attr)
    (DEFS.dig('Collection', attr, 'enum') || []).uniq
  end

  # Canonical spellings; the alias ones route to the same arm.
  LAYOUTS = (declared('layout') - %w[Flow LeftAligned leftAligned]).freeze
  LAZY = (declared('lazy') + [nil]).freeze   # nil = undeclared, the default

  # Containers that ARE accessibility elements on their own. A Collection
  # emitting one of these needs nothing; anything else has to be made one.
  ELEMENT_CONTAINERS = ['ScrollView(', 'List(', 'List {', 'TabView(',
                        'CollectionStackView('].freeze

  def emit(layout:, lazy:)
    component = { 'type' => 'Collection', 'id' => 'target',
                  'width' => 150, 'height' => 200,
                  'sections' => [{ 'cell' => 'probe_cell' }],
                  'items' => '@{items}' }
    component['layout'] = layout if layout
    component['lazy'] = lazy if lazy
    described_class.new(component).convert.to_s
  end

  describe 'every declared shape either is an element or is made one' do
    it 'covers more than one combination, or it measures nothing' do
      expect(LAYOUTS.size).to be >= 3
      expect(LAZY.size).to be >= 4
    end

    LAYOUTS.each do |layout|
      LAZY.each do |lazy|
        label = "layout=#{layout} lazy=#{lazy || '(default)'}"
        it label do
          code = emit(layout: layout, lazy: lazy)
          next unless code.include?('.accessibilityIdentifier("target")')

          if ELEMENT_CONTAINERS.any? { |c| code.include?(c) }
            next # the container is an element; the identifier lands on it
          end

          expect(code).to include('.accessibilityElement(children: .contain)'),
                          "#{label}: non-element container with a bare identifier — " \
                          'its cells will be renamed to "target"'
          expect(code).to include('.accessibilityElement(children: .ignore)'),
                          "#{label}: no merge anchor — with one cell, .contain alone merges"
        end
      end
    end
  end

  describe 'the two sides of the predicate' do
    # Named on their own so a failure says which side broke rather than
    # leaving the reader to decode a parameterised label.
    it 'lazy:none flow is made an element' do
      code = emit(layout: 'flow', lazy: 'none')
      expect(code).not_to include('ScrollView(')
      expect(code).to include('.accessibilityElement(children: .contain)')
      expect(code).to include('.accessibilityElement(children: .ignore)')
    end

    it 'default (lazy) flow is left alone — its ScrollView is the element' do
      code = emit(layout: 'flow', lazy: nil)
      expect(code).to include('ScrollView(')
      expect(code).not_to include('.accessibilityElement(children: .contain)')
    end

    it 'the anchor comes before the contain, which comes before the id' do
      # Order is the contract: SwiftUI applies modifiers outward, so an
      # identifier placed before `.contain` is the bare identifier again.
      code = emit(layout: 'flow', lazy: 'none')
      ignore = code.index('.accessibilityElement(children: .ignore)')
      contain = code.index('.accessibilityElement(children: .contain)')
      identifier = code.index('.accessibilityIdentifier("target")')
      expect([ignore, contain, identifier]).to all(be_truthy)
      expect(ignore).to be < contain
      expect(contain).to be < identifier
    end
  end

  describe 'Collection stays out of the type list' do
    # The list's own sentence is "types whose SwiftUI representation is a
    # plain layout container". Collection's representation is that for one
    # shape and not for the others, so putting it there would make the
    # sentence false and silently add an element to every scroll shape.
    it 'is not declared a container by type' do
      expect(described_class.const_get(:ACCESSIBILITY_CONTAINER_TYPES))
        .not_to include('collection')
    end
  end

  # See collection_converter_characterization_spec: emitted TEXT was asserted
  # here for years while the Swift did not compile. This arm hands the same
  # emission to a compiler.
  describe 'the emitted Swift type-checks', :swift_compile do
    it 'accepts the collection with its accessibility wrapping' do
      code = described_class.new(
        { 'type' => 'Collection', 'id' => 'target', 'columns' => 1,
          'sections' => [{ 'cell' => 'FooCell' }], 'items' => '@{items}' }
      ).convert.to_s
      stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB +
              EmittedSwift::COLLECTION_STACK_VIEW_STUB +
              cell_view_stub('FooCellView')
      expect(
        compilable_view(code, data: ['var items: CollectionDataSource? = nil'], stubs: stubs)
      ).to compile_as_swift
    end
  end
end
