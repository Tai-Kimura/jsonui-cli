# frozen_string_literal: true

require 'core/attribute_validator'

# `child`/`children` are the one attribute family a renderer cannot skip and
# still draw the screen — the child IS the screen. Every renderer accepts a
# single node object as shorthand for a one-element array, and implements it
# as `[value] unless value.is_a?(Array)`: a negation of Array where it means
# "a node". So a String, number, null or boolean was wrapped just as happily,
# iterated over, matched nothing, and produced an empty view while the build
# said "Compose build completed!".
#
# Measured on 1.8.15 before this check existed, one View per row, android:
#
#   child                        validator   rendered children   exit
#   [{Label}]                    silent      1                   0
#   {Label}          shorthand   warned!     1                   0    ← false positive
#   "notalist" / 42 / null       warned      0                   0    ← green
#   ["notalist"] / [null]        SILENT      0                   0    ← green
#   [{Label}, "notalist"]        SILENT      1                   0    ← green, sibling vanished
#
# The last two rows had no signal at all: the declared type is `array`, and
# an array is what they are. The worst is the mixed one — a valid sibling
# renders, so the screen looks built.
RSpec.describe KjuiTools::Core::AttributeValidator do
  # Detection is asserted through `validate`'s returned warnings, NOT through
  # the new structural channel. Restoring the defect removes the channel's
  # methods, so channel-based arms would go red with NoMethodError — red for
  # a missing method is not red for a swallowed child, and an arm that
  # cannot tell those apart would pass a fix that only added the accessor.
  # Warnings exist in both versions, so these arms fail with the defect's own
  # shape: the message that names the node is simply not there.
  def warnings_for(child, extra = {})
    described_class.new(:compose).validate(
      { 'type' => 'View', 'id' => 'v', 'width' => 10, 'height' => 10,
        'child' => child }.merge(extra)
    ).grep(/child/)
  end

  def structural_errors_for(child)
    validator = described_class.new(:compose)
    validator.reset_structural_errors!
    validator.validate({ 'type' => 'View', 'id' => 'v', 'child' => child })
    validator.structural_errors
  end

  describe 'shapes that cannot be rendered' do
    {
      'a string' => 'notalist',
      'a number' => 42,
      'null' => nil,
      'a boolean' => true
    }.each do |label, value|
      it "says #{label} is not a node, in one message" do
        # Since `acceptsSingle` put the declaration back in charge of the
        # shape, the DECLARED-TYPE check reports a scalar child and the node
        # sentence stays on the structural channel — one defect, one warning.
        # Both halves are asserted: a version that dropped the structural
        # record would still pass the warning half, and the build would stop
        # failing.
        found = warnings_for(value)
        expect(found.size).to eq(1)
        expect(found.first).to include("'child' in 'View' expects array")
        expect(structural_errors_for(value).size).to eq(1)
        expect(structural_errors_for(value).first)
          .to include('must be a component node')
      end
    end

    it 'reports a non-node inside an array, which nothing reported before' do
      found = warnings_for(['notalist'])
      expect(found.size).to eq(1)
      expect(found.first).to include("'child[0]'")
      expect(found.first).to include('must be a component node')
    end

    it 'names the index, so a valid sibling does not hide the missing one' do
      found = warnings_for([{ 'type' => 'Label', 'id' => 'a' }, 'notalist'])
      expect(found.size).to eq(1)
      expect(found.first).to include("'child[1]'")
    end

    it 'reports every non-node in the array, not just the first' do
      found = warnings_for(['a', { 'type' => 'Label', 'id' => 'b' }, nil])
      expect(found.map { |e| e[/child\[\d\]/] }).to eq(%w[child[0] child[2]])
    end

    it 'also puts them on the structural channel a build can act on' do
      expect(structural_errors_for('notalist').size).to eq(1)
      expect(structural_errors_for(['notalist']).size).to eq(1)
    end
  end

  describe 'shapes that render, and must stay silent' do
    # The declaration says `"type": "array"`, so before this check the
    # shorthand drew "expects array, got object" — a warning on 164 nodes
    # across 12 layout trees that every renderer draws correctly. A signal
    # that fires on working input is not a signal.
    it 'accepts the single-node shorthand, with no warning at all' do
      expect(warnings_for({ 'type' => 'Label', 'id' => 't' })).to be_empty
    end

    it 'accepts an array of nodes' do
      expect(warnings_for([{ 'type' => 'Label', 'id' => 't' }])).to be_empty
    end

    it 'accepts an empty array' do
      expect(warnings_for([])).to be_empty
    end

    it 'accepts a data-only definition list, which is not a node list' do
      expect(warnings_for([{ 'data' => 'items' }])).to be_empty
    end

    it 'leaves the structural channel empty for all of them' do
      expect(structural_errors_for({ 'type' => 'Label', 'id' => 't' })).to be_empty
      expect(structural_errors_for([{ 'type' => 'Label', 'id' => 't' }])).to be_empty
      expect(structural_errors_for([])).to be_empty
    end
  end

  describe 'the channel itself' do
    # `validate` clears @warnings on every call and callers recurse into the
    # tree with ONE validator instance, so a per-call channel would only ever
    # describe the last node visited. These accumulate; the caller clears
    # them once per file. A test that only ever validates one node cannot
    # tell the two designs apart, so this one validates two.
    it 'accumulates across nodes instead of describing only the last one' do
      validator = described_class.new(:compose)
      validator.reset_structural_errors!
      validator.validate({ 'type' => 'View', 'id' => 'first', 'child' => 'bad1' })
      validator.validate({ 'type' => 'View', 'id' => 'second', 'child' => 'bad2' })
      expect(validator.structural_errors.size).to eq(2)
    end

    it 'clears on request, so one file does not fail the next' do
      validator = described_class.new(:compose)
      validator.validate({ 'type' => 'View', 'id' => 'v', 'child' => 'bad' })
      expect(validator).to be_structural_errors
      validator.reset_structural_errors!
      expect(validator).not_to be_structural_errors
    end

    it 'reaches the warning summary for what nothing else reports' do
      # A non-node INSIDE an array is invisible to the declared-type check —
      # an array is what it is — so this one has to carry its own warning.
      validator = described_class.new(:compose)
      warnings = validator.validate({ 'type' => 'View', 'id' => 'v',
                                      'child' => ['bad'] })
      expect(warnings.grep(/must be a component node/).size).to eq(1)
    end

    it 'says the defect once, whichever channel owns it' do
      # Two checks can see a scalar child — the declared type and the node
      # rule — and for a while both spoke. One defect, one sentence: the
      # type check warns, the node rule records without warning again.
      validator = described_class.new(:compose)
      validator.reset_structural_errors!
      warnings = validator.validate({ 'type' => 'View', 'id' => 'v', 'child' => 'bad' })
      expect(warnings.grep(/child/).size).to eq(1)
      expect(validator.structural_errors.size).to eq(1)
    end
  end
end
