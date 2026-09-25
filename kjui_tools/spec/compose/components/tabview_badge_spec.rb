# frozen_string_literal: true

require 'compose/components/tabview_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

# A TabView tab's `badge`: what the emitter writes, and that it compiles.
#
# Two defects, both in the badge's emit (2026-09-25):
#
# 1. It did not compile. The badge was spliced in after the tab with
#    `code.gsub(/icon = \{/, …)` over the WHOLE string: every earlier tab got
#    the badge too, and the `BadgedBox(…) {` it opened was never closed. A
#    two-tab TabView with `badge: 3` on the second tab emitted 21 `{` against
#    19 `}`. tabview_component_spec.rb asserted this component's text 38
#    times and never a badge, and handed nothing to a compiler.
# 2. A screen reader never received it. Material3's NavigationBarItem clears
#    the icon slot's semantics — the badge inside it — whenever a label is
#    shown (`label != null && (alwaysShowLabel || selected)`). Measured on an
#    emulator (API 35, material3 1.4.0), the AccessibilityNodeInfo held the
#    badge's "3" 0 times; a `stateDescription` on the item carried it once,
#    the title still once. Without a label the slot is not cleared and the
#    badge already arrives, so a stateDescription there would say it twice.
#
# The value rule is the dynamic component's getBadgeValue: a number shows
# when its integer part is > 0, a string when it is not empty; a binding by
# the same rule at run time.
RSpec.describe KjuiTools::Compose::Components::TabviewComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  def tabs(*badges, show_labels: true)
    names = %w[Home Inbox News Chat Zero Sixth]
    json = { 'type' => 'TabView',
             'tabs' => badges.each_with_index.map do |b, i|
               tab = { 'title' => names[i], 'icon' => 'star' }
               tab['badge'] = b unless b == :none
               tab
             end }
    json['showLabels'] = false unless show_labels
    json
  end

  def items(result)
    result.split('NavigationBarItem(').drop(1).map { |item| item.split("\n            )\n").first }
  end

  describe 'where the badge goes' do
    it 'wraps only its own tab and closes every brace it opens' do
      result = described_class.generate(tabs(:none, 3, :none), 0, required_imports)
      expect(items(result).map { |i| i.scan('BadgedBox').size }).to eq([0, 1, 0])
      expect(result.count('{')).to eq(result.count('}'))
      expect(result.count('(')).to eq(result.count(')'))
    end

    it 'leaves a TabView without a badge free of any badge code' do
      result = described_class.generate(tabs(:none, :none), 0, required_imports)
      expect(result).not_to include('BadgedBox')
      expect(result).not_to include('semantics')
      expect(required_imports).not_to include(:semantics_state_description)
    end
  end

  describe 'the value rule (getBadgeValue)' do
    {
      3 => '"3"',
      2.7 => '"2"',
      'NEW' => '"NEW"',
      'say "hi" $x' => '"say \\"hi\\" \\$x"'
    }.each do |badge, literal|
      it "shows #{badge.inspect} as #{literal}" do
        result = described_class.generate(tabs(badge), 0, required_imports)
        expect(result).to include("BadgedBox(badge = { Badge { Text(#{literal}) } }) {")
        expect(result).to include("modifier = Modifier.semantics { stateDescription = #{literal} },")
      end
    end

    [0, -2, 0.4, '', true].each do |badge|
      it "shows no badge for #{badge.inspect}" do
        result = described_class.generate(tabs(badge), 0, required_imports)
        expect(result).not_to include('BadgedBox')
        expect(result).not_to include('stateDescription')
      end
    end

    it 'decides a bound badge at run time, once per tab, by the same rule' do
      result = described_class.generate(tabs(:none, '@{unread}'), 0, required_imports)
      expect(result).to include('val badge1: String? = when (val v: Any? = data.unread) {')
      expect(result).to include('is String -> v.ifEmpty { null }; else -> null }')
      expect(result).to include('modifier = if (badge1 != null) Modifier.semantics { stateDescription = badge1 } else Modifier,')
      expect(result).to include('if (badge1 != null) {')
      expect(result).to include('BadgedBox(badge = { Badge { Text(badge1) } }) {')
    end
  end

  describe 'the screen reader' do
    it 'puts the badge on the item only when a label is shown' do
      labelled = described_class.generate(tabs(3), 0, required_imports)
      expect(labelled.scan('stateDescription').size).to eq(1)
      expect(required_imports).to include(:semantics_state_description)

      unlabelled_imports = Set.new
      unlabelled = described_class.generate(tabs(3, show_labels: false), 0, unlabelled_imports)
      expect(unlabelled).to include('BadgedBox')           # the badge still shows
      expect(unlabelled).not_to include('stateDescription') # and is already announced
      expect(unlabelled_imports).not_to include(:semantics_state_description)
    end

    # The condition above is Material3's `label != null && (alwaysShowLabel
    # || selected)` read with alwaysShowLabel at its default. It holds only
    # while this emitter passes no alwaysShowLabel; the day it does, an
    # unselected tab keeps its icon semantics and the badge is said twice.
    it 'passes no alwaysShowLabel, which the label condition relies on' do
      result = described_class.generate(tabs(3, '@{n}', :none), 0, required_imports)
      expect(result).not_to include('alwaysShowLabel')
    end
  end

  # One broad arm: every badge shape, labelled and not, well-typed against
  # the TabView stub universe (spec/support/compose_stub_universe.rb). Types
  # against stubs only — not the Compose compiler's rules. Before the fix
  # this failed on the braces alone.
  it 'emits Kotlin that compiles, for every badge shape' do
    labelled = described_class.generate(tabs(:none, 3, 'NEW', '@{unread}', 0), 1, required_imports)
    unlabelled = described_class.generate(tabs(:none, 3, '@{unread}', show_labels: false), 1, Set.new)
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.tabview(labelled + unlabelled)}
      data class Data(val unread: Int? = null)

      fun labelled(data: Data) {
      #{labelled}
      }

      fun unlabelled(data: Data) {
      #{unlabelled}
      }
    KOTLIN
  end
end
