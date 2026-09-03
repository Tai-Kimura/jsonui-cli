# frozen_string_literal: true

require 'json'
require 'core/attribute_validator'

# `child`/`children` are declared `"type": "array"`, and every renderer also
# accepts a single node object as a one-element array — 164 nodes across 12
# layout trees rely on it. The declaration said only `array`, so the generic
# type check warned `expects array, got object` on working layouts, and the
# first fix silenced the check for those keys entirely: the false positive
# went away and so did the declaration's authority over them.
#
# `acceptsSingle: true` states the accepted form instead of hiding the
# mismatch, and the validator wraps at the boundary — the same
# `[value] unless is_a?(Array)` the renderers do, said once on the tool side.
# The declared type stays `array`, so the generated Kotlin/Swift/Ruby tables
# are untouched (that is why this shape was chosen over widening `type`).
#
# Only an object is wrapped. Wrapping a scalar would move the complaint about
# `"child": "notalist"` from `'child'` to `'child[0]'` — an index the author
# never wrote.
RSpec.describe KjuiTools::Core::AttributeValidator do
  DEFS = JSON.parse(
    File.read(File.expand_path('../../lib/core/attribute_definitions.json', __dir__))
  ).freeze

  def warnings_for(component)
    described_class.new(:compose).validate(component)
  end

  def view(child)
    { 'type' => 'View', 'id' => 'v', 'width' => 10, 'height' => 10, 'child' => child }
  end

  LABEL = { 'type' => 'Label', 'id' => 't' }.freeze

  describe 'where the flag may be declared' do
    # The ruling's condition: `acceptsSingle` belongs only on an array
    # attribute whose elements are objects. A scalar-array attribute picking
    # up the same name later would make "wrap or not" ambiguous, and the
    # place to stop that is the declaration, not the reader.
    #
    # The denominator is every attribute in the SSoT, so a new declaration
    # anywhere is checked without this file being touched.
    def self.every_declaration
      DEFS.flat_map do |component, attrs|
        next [] unless attrs.is_a?(Hash)
        attrs.filter_map do |name, entry|
          [component, name, entry] if entry.is_a?(Hash) && entry.key?('acceptsSingle')
        end
      end
    end

    it 'is declared somewhere, or the arms below prove nothing' do
      expect(self.class.every_declaration.size).to be >= 2
    end

    every_declaration.each do |component, name, entry|
      it "#{component}.#{name} declares an array of objects" do
        expect(Array(entry['type'])).to include('array'),
                                        "acceptsSingle on a non-array attribute"
        expect(entry['acceptsSingle']).to be(true)
        # No `items` on these; the element contract is "a component node",
        # which check_child_structure enforces. If a future declaration adds
        # `items`, it must not say the elements are scalars.
        items_type = Array(entry.dig('items', 'type'))
        expect(items_type - %w[object]).to be_empty,
                                          "acceptsSingle on an array of #{items_type.join('|')}"
      end

      it "#{component}.#{name} says so in its own description" do
        # The description is what `lookup_attribute` hands an MCP caller —
        # the one reader that surfaces the field verbatim.
        expect(entry['description']).to include('single component node')
      end
    end
  end

  describe 'the shorthand validates' do
    it 'accepts a single node object with no warning' do
      expect(warnings_for(view(LABEL)).grep(/child/)).to be_empty
    end

    it 'accepts an array of nodes, as before' do
      expect(warnings_for(view([LABEL])).grep(/child/)).to be_empty
    end
  end

  describe 'what the wrapping must not swallow' do
    it 'still names a scalar child, and as `child` not `child[0]`' do
      found = warnings_for(view('notalist')).grep(/child/)
      expect(found.size).to eq(1), "one defect, one sentence: #{found.inspect}"
      expect(found.first).to include("expects array, got string")
      expect(found.first).not_to include('child[0]')
    end

    it 'still names a non-node inside an array' do
      found = warnings_for(view(['notalist'])).grep(/child/)
      expect(found.size).to eq(1)
      expect(found.first).to include("'child[0]'")
    end
  end

  describe 'the declaration is the authority again' do
    # The first fix returned early for child/children in the generic type
    # check. That silenced the false positive by removing the declaration
    # from the decision. This arm is the control for having put it back: a
    # type violation on a DIFFERENT attribute must still be reported, so
    # "no warning on the shorthand" is not just the check being off.
    it 'reports a type violation on an attribute with no acceptsSingle' do
      found = warnings_for({ 'type' => 'View', 'id' => 'v', 'width' => 10,
                             'height' => 10, 'orientation' => %w[not a string] })
      expect(found.grep(/orientation/)).not_to be_empty
    end

    it 'does not wrap for an attribute that does not declare the flag' do
      # `sections` is an array attribute without `acceptsSingle`; a bare
      # object there is still a type violation.
      found = warnings_for({ 'type' => 'Collection', 'id' => 'c',
                             'width' => 10, 'height' => 10,
                             'sections' => { 'cell' => 'x' } })
      expect(found.grep(/sections/)).not_to be_empty
    end
  end
end
